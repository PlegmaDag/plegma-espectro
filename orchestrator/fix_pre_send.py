"""
Prepara o sistema para receber 1 USDC de teste:
1. Reinicia plegma-core em EUR para reanimar o monitor
2. Cria pending purchase de 1.00 USDC para o endereço de teste do admin
3. Confirma que o monitor voltou a sincronizar
"""
import paramiko
import time
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from daemon_config import NODES, SSH_KEY, ADMIN_KEY

key = paramiko.Ed25519Key.from_private_key_file(SSH_KEY)

def connect(ip):
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(ip, username='root', pkey=key, timeout=12)
    transport = c.get_transport()
    if transport:
        transport.set_keepalive(20)
    return c

# ── 1. Reiniciar plegma-core em EUR ─────────────────────────────────────────
print("=== PASSO 1: Reiniciar plegma-core EUR (reanimar monitor) ===")
c = connect(NODES['eur']['ip'])
_, stdout, _ = c.exec_command('systemctl restart plegma-core', timeout=15)
stdout.read()
time.sleep(10)
_, stdout, _ = c.exec_command('systemctl is-active plegma-core')
status = stdout.read().decode().strip()
print(f"plegma-core EUR: {status}")
c.close()

# ── 2. Criar pending purchase de 1.00 USDC ───────────────────────────────────
print("\n=== PASSO 2: Criar pending purchase de 1.00 USDC ===")
# Usar um endereço PLG de teste do admin para verificar o fluxo
# Este é o endereço que vai receber o PLG-G quando o pagamento for confirmado

REMOTE_CREATE = """
import sys, json, time
sys.path.insert(0, '/root/PLEGMA_CORE')
import plegma_db

# Verificar se ja existe pending para 1.00 USDC
pending = plegma_db.listar_pending_aguardando()
existing = [p for p in pending if abs(p.get("usdt_amount", 0) - 1.00) <= 0.02]

if existing:
    print(f"OK: ja existe pending de ~1 USDC: ref={existing[0].get('ref_id')}")
else:
    # Criar pending purchase de teste
    # Gerar ref_id unico
    import hashlib
    ref_id = "TEST_" + hashlib.blake2b(str(time.time()).encode(), digest_size=8).hexdigest()

    # Calcular quantos PLG-G por 1 USDC
    gen_status = {}
    try:
        import genesis_contract as gc
        gen_status = gc.get_status()
    except:
        pass

    preco_usdc = gen_status.get("preco_usdc", gen_status.get("price_usdc", 0.01))
    if not preco_usdc or preco_usdc == 0:
        preco_usdc = 0.01  # default: 0.01 USDC por PLG-G

    plgg_quantidade = 1.00 / preco_usdc  # PLG-G a emitir

    # Endereço PLG do admin para receber o PLG-G de teste
    # Usar um endereco generico de teste (sem efeito real em TESTNET)
    PLG_TEST_ADDR = "PLG_ADMIN_TEST_0000000000000000000000000000001"

    try:
        plegma_db.registrar_pending_purchase(
            ref_id=ref_id,
            plg_address=PLG_TEST_ADDR,
            usdt_amount=1.00,
            plgg_quantidade=plgg_quantidade,
            ts=time.time()
        )
        print(f"OK: pending criada | ref={ref_id} | 1.00 USDC -> {plgg_quantidade:.2f} PLG-G -> {PLG_TEST_ADDR}")
    except Exception as e:
        # Tentar schema alternativo
        try:
            conn = plegma_db._get_conn()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO pending_purchases (ref_id, plg_address, usdt_amount, plgg_quantidade, ts, status) "
                "VALUES (?, ?, ?, ?, ?, 'aguardando')",
                (ref_id, PLG_TEST_ADDR, 1.00, plgg_quantidade, time.time())
            )
            conn.commit()
            conn.close()
            print(f"OK (insert direto): ref={ref_id} | 1.00 USDC -> {plgg_quantidade:.2f} PLG-G")
        except Exception as e2:
            print(f"ERRO ao criar pending: {e} | {e2}")
            # Inspecionar schema da tabela
            try:
                conn = plegma_db._get_conn()
                cur = conn.cursor()
                cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [r[0] for r in cur.fetchall()]
                print(f"Tabelas: {tables}")
                if 'pending_purchases' in tables:
                    cur.execute("PRAGMA table_info(pending_purchases)")
                    cols = [(r[1], r[2]) for r in cur.fetchall()]
                    print(f"Schema pending_purchases: {cols}")
                conn.close()
            except Exception as e3:
                print(f"Erro inspecao: {e3}")
"""

c = connect(NODES['eur']['ip'])
sftp = c.open_sftp()
with sftp.open('/tmp/create_pending.py', 'w') as f:
    f.write(REMOTE_CREATE)
sftp.close()

_, stdout, stderr = c.exec_command(
    'cd /root/PLEGMA_CORE && python3 /tmp/create_pending.py; rm -f /tmp/create_pending.py',
    timeout=20
)
print(stdout.read().decode())
e = stderr.read().decode()
if e.strip() and 'DeprecationWarning' not in e:
    print("STDERR:", e[:300])
c.close()

# ── 3. Aguardar 30s e verificar bloco do monitor ─────────────────────────────
print("\n=== PASSO 3: Verificar monitor apos restart (30s) ===")
time.sleep(30)

REMOTE_CHECK = """
import sys
sys.path.insert(0, '/root/PLEGMA_CORE')
import plegma_db
from web3 import Web3

bloco_db = plegma_db.carregar_estado("monitor_ultimo_bloco", None)
carteira  = plegma_db.carregar_estado("carteira_recebimento", "")

for rpc in ["https://polygon.drpc.org", "https://polygon-bor-rpc.publicnode.com"]:
    try:
        w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 8}))
        bloco_atual = w3.eth.block_number
        if bloco_atual: break
    except: continue

diff = bloco_atual - int(bloco_db) if bloco_db and bloco_atual else 9999
status = "ATIVO" if diff < 300 else "ATRASADO"
print(f"Monitor: bloco_db={bloco_db} | atual={bloco_atual} | diff={diff} | {status}")
print(f"Carteira: {carteira}")

pending = plegma_db.listar_pending_aguardando()
match_1 = [p for p in pending if abs(p.get("usdt_amount", 0) - 1.00) <= 0.02]
print(f"Pending para 1.00 USDC: {len(match_1)} registo(s)")
for p in match_1:
    print(f"  ref={p.get('ref_id')} | {p.get('usdt_amount')} USDC | {str(p.get('plg_address',''))[:24]}...")
"""

c = connect(NODES['eur']['ip'])
sftp = c.open_sftp()
with sftp.open('/tmp/chk2.py', 'w') as f:
    f.write(REMOTE_CHECK)
sftp.close()

_, stdout, _ = c.exec_command(
    'cd /root/PLEGMA_CORE && python3 /tmp/chk2.py; rm -f /tmp/chk2.py',
    timeout=20
)
print(stdout.read().decode())
c.close()
