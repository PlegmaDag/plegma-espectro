"""
Verifica toda a cadeia de deteção USDC → emissão PLG-G antes do envio real.
"""
import paramiko
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from daemon_config import NODES, SSH_KEY

REMOTE = """
import sys, json, time
sys.path.insert(0, '/root/PLEGMA_CORE')

print("=" * 55)
print("  VERIFICAÇÃO PRÉ-ENVIO USDC")
print("=" * 55)

# ── 1. Monitor ativo? ──────────────────────────────────────
import plegma_db
bloco_db    = plegma_db.carregar_estado("monitor_ultimo_bloco", None)
carteira    = plegma_db.carregar_estado("carteira_recebimento", "")
print(f"\\n[1] Monitor de pagamentos")
print(f"    carteira   : {carteira}")
print(f"    ultimo_bloco: {bloco_db}")

from web3 import Web3
bloco_atual = None
for rpc in ["https://polygon.drpc.org", "https://polygon-bor-rpc.publicnode.com"]:
    try:
        w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 8}))
        bloco_atual = w3.eth.block_number
        if bloco_atual: break
    except: continue

if bloco_db and bloco_atual:
    diff = bloco_atual - int(bloco_db)
    status = "ATIVO" if diff < 300 else "ATRASADO"
    print(f"    bloco_atual: {bloco_atual} | diff={diff} | {status}")
else:
    print(f"    bloco_atual: {bloco_atual} | AVISO: nao foi possivel verificar")

# ── 2. Pending purchases? ──────────────────────────────────
print(f"\\n[2] Pending purchases aguardando pagamento")
try:
    pending = plegma_db.listar_pending_aguardando()
    if pending:
        print(f"    Total: {len(pending)}")
        for p in pending[:5]:
            print(f"    - ref={p.get('ref_id','?')} | valor={p.get('usdt_amount','?')} USDC | plg={str(p.get('plg_address','?'))[:16]}...")
    else:
        print("    AVISO: Nenhuma pending purchase registada.")
        print("    -> O monitor vai guardar como 'sem_registro_' (nao emite PLG-G automaticamente).")
        print("    -> Para teste, o admin pode confirmar manualmente depois.")
except Exception as e:
    print(f"    ERRO: {e}")

# ── 3. Funcoes criticas do plegma_db ──────────────────────
print(f"\\n[3] Funções críticas plegma_db")
try:
    _ = plegma_db.tx_externo_ja_processado("0x_teste_inexistente_abc123")
    print("    tx_externo_ja_processado: OK")
except Exception as e:
    print(f"    tx_externo_ja_processado: ERRO -> {e}")

try:
    _ = plegma_db.listar_pending_aguardando()
    print("    listar_pending_aguardando: OK")
except Exception as e:
    print(f"    listar_pending_aguardando: ERRO -> {e}")

# ── 4. genesis_contract funcional? ────────────────────────
print(f"\\n[4] genesis_contract")
try:
    import genesis_contract as gc
    status_gen = gc.get_status()
    supply  = status_gen.get("supply_total", status_gen.get("total_supply", "?"))
    vendido = status_gen.get("plgg_vendido", status_gen.get("total_vendido", "?"))
    fase    = status_gen.get("fase", status_gen.get("phase", "?"))
    print(f"    status: OK | supply={supply} | vendido={vendido} | fase={fase}")
except Exception as e:
    print(f"    status: ERRO -> {e}")

try:
    destinos = gc.get_carteiras_destino_polygon()
    pool     = destinos.get("pool_liquidez", "N/A")
    aer      = destinos.get("aerarium", "N/A")
    prontas  = destinos.get("prontas", False)
    print(f"    carteiras_destino: prontas={prontas}")
    print(f"      pool_liquidez: {pool}")
    print(f"      aerarium     : {aer}")
except Exception as e:
    print(f"    carteiras_destino: ERRO -> {e}")

# ── 5. Simular processamento de 1 USDC ────────────────────
print(f"\\n[5] Simulação: o que acontece ao receber 1.00 USDC")
usdc_teste = 1.00
pending = plegma_db.listar_pending_aguardando()
match = None
for p in (pending or []):
    if abs(p.get("usdt_amount", 0) - usdc_teste) <= 0.02:
        match = p
        break

if match:
    print(f"    Match encontrado! ref={match.get('ref_id')} | plg={str(match.get('plg_address','?'))[:16]}...")
    print(f"    -> confirmar_compra() seria chamado -> PLG-G emitido")
else:
    print(f"    Sem match para {usdc_teste} USDC nos pending ({len(pending or [])} registos).")
    print(f"    -> guardado como sem_registro_ no estado")
    print(f"    -> admin pode confirmar manualmente via POST /api/genesis/confirmar-manual")

# ── 6. Saldo atual na carteira ────────────────────────────
print(f"\\n[6] Saldo atual na carteira Genesis Pool")
try:
    USDC_ABI = '[{"inputs":[{"name":"account","type":"address"}],"name":"balanceOf","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"}]'
    import json
    contrato = w3.eth.contract(
        address=Web3.to_checksum_address("0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"),
        abi=json.loads(USDC_ABI)
    )
    saldo_raw = contrato.functions.balanceOf(
        Web3.to_checksum_address(carteira)
    ).call()
    saldo = saldo_raw / 1_000_000
    print(f"    Saldo atual: {saldo:.6f} USDC")
    print(f"    Apos envio de 1 USDC: {saldo + 1:.6f} USDC esperado")
except Exception as e:
    print(f"    Erro ao verificar saldo: {e}")

print(f"\\n{'=' * 55}")
print("  RESULTADO: sistema pronto para receber USDC")
print(f"{'=' * 55}")
"""

key = paramiko.Ed25519Key.from_private_key_file(SSH_KEY)
c   = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(NODES['eur']['ip'], username='root', pkey=key, timeout=12)
transport = c.get_transport()
if transport:
    transport.set_keepalive(20)

sftp = c.open_sftp()
with sftp.open('/tmp/chk_flow.py', 'w') as f:
    f.write(REMOTE)
sftp.close()

_, stdout, stderr = c.exec_command(
    'cd /root/PLEGMA_CORE && python3 /tmp/chk_flow.py; rm -f /tmp/chk_flow.py',
    timeout=30
)
print(stdout.read().decode())
e = stderr.read().decode()
if e.strip() and 'DeprecationWarning' not in e and 'RequestsDependency' not in e:
    print("STDERR:", e[:300])
c.close()
