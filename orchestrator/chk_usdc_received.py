"""
Verifica se o USDC chegou e o estado do monitor. Scan manual na Polygon.
"""
import paramiko, time, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from daemon_config import NODES, SSH_KEY

REMOTE = """
import sys, json, time
sys.path.insert(0, '/root/PLEGMA_CORE')
import plegma_db
from web3 import Web3

CARTEIRA   = "0xd8422d6936be77179dc33c7c2ffceef4c34fb183"
USDC_ADDR  = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"
USDC_ABI   = json.loads('[{"anonymous":false,"inputs":[{"indexed":true,"name":"from","type":"address"},{"indexed":true,"name":"to","type":"address"},{"indexed":false,"name":"value","type":"uint256"}],"name":"Transfer","type":"event"},{"inputs":[{"name":"account","type":"address"}],"name":"balanceOf","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"}]')

# Conectar ao melhor RPC disponivel
w3 = None
for rpc in ["https://polygon.drpc.org", "https://polygon-bor-rpc.publicnode.com", "https://rpc-mainnet.matic.quiknode.pro"]:
    try:
        _w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 12}))
        _ = _w3.eth.block_number
        w3 = _w3
        print(f"RPC: {rpc}")
        break
    except: continue

if not w3:
    print("ERRO: sem RPC disponivel")
    exit(1)

contrato = w3.eth.contract(address=Web3.to_checksum_address(USDC_ADDR), abi=USDC_ABI)

# 1. Saldo atual
saldo_raw = contrato.functions.balanceOf(Web3.to_checksum_address(CARTEIRA)).call()
saldo_usdc = saldo_raw / 1_000_000
print(f"\\nSaldo USDC atual: {saldo_usdc:.6f} USDC")

# 2. Scan manual — ultimos 500 blocos para encontrar Transfer
bloco_atual = w3.eth.block_number
from_blk = bloco_atual - 500
print(f"\\nScan Transfer eventos: bloco {from_blk} → {bloco_atual}")

try:
    eventos = contrato.events.Transfer.get_logs(
        fromBlock=from_blk, toBlock=bloco_atual,
        argument_filters={"to": Web3.to_checksum_address(CARTEIRA)}
    ) if hasattr(Web3, '__version__') and int(getattr(Web3, '__version__', '6').split('.')[0] if isinstance(getattr(Web3, '__version__', '6'), str) else '6') < 7 else contrato.events.Transfer.get_logs(
        from_block=from_blk, to_block=bloco_atual,
        argument_filters={"to": Web3.to_checksum_address(CARTEIRA)}
    )
except Exception as e:
    # fallback get_logs
    try:
        eventos = contrato.events.Transfer.get_logs(fromBlock=from_blk, toBlock=bloco_atual, argument_filters={"to": Web3.to_checksum_address(CARTEIRA)})
    except:
        eventos = contrato.events.Transfer.get_logs(from_block=from_blk, to_block=bloco_atual, argument_filters={"to": Web3.to_checksum_address(CARTEIRA)})

if eventos:
    print(f"Transferencias encontradas: {len(eventos)}")
    for ev in eventos:
        tx  = ev["transactionHash"].hex()
        val = ev["args"]["value"] / 1_000_000
        blk = ev["blockNumber"]
        print(f"  TX: {tx}")
        print(f"  Valor: {val:.6f} USDC | Bloco: {blk}")
        ja_proc = plegma_db.tx_externo_ja_processado(tx)
        print(f"  Ja processado: {ja_proc}")
else:
    print("Nenhuma transferencia nos ultimos 500 blocos.")
    print("(pode ainda nao ter confirmado na blockchain, aguarde 1-2 min)")

# 3. Estado no DB
print(f"\\nEstado no DB:")
print(f"  monitor_ultimo_bloco: {plegma_db.carregar_estado('monitor_ultimo_bloco', None)}")

# sem_registro entries
import sqlite3
try:
    db_path = None
    import plegma_db as _pd
    # tentar encontrar o path da db
    for attr in ['DB_PATH', '_DB', 'DB']:
        if hasattr(_pd, attr):
            db_path = getattr(_pd, attr)
            break
    if not db_path:
        import inspect, os
        src = inspect.getfile(_pd)
        db_path = os.path.join(os.path.dirname(src), 'plegma.db')

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("SELECT chave, valor FROM network_state WHERE chave LIKE 'sem_registro_%' ORDER BY chave DESC LIMIT 5")
    rows = cur.fetchall()
    conn.close()
    if rows:
        print(f"  sem_registro entries: {len(rows)}")
        for k, v in rows:
            print(f"    {k}: {v[:80]}")
    else:
        print("  sem_registro entries: nenhuma")
except Exception as e:
    print(f"  sem_registro check: {e}")
"""

key = paramiko.Ed25519Key.from_private_key_file(SSH_KEY)
c   = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(NODES['eur']['ip'], username='root', pkey=key, timeout=12)
transport = c.get_transport()
if transport:
    transport.set_keepalive(20)

sftp = c.open_sftp()
with sftp.open('/tmp/chk_recv.py', 'w') as f:
    f.write(REMOTE)
sftp.close()

_, stdout, stderr = c.exec_command(
    'cd /root/PLEGMA_CORE && python3 /tmp/chk_recv.py; rm -f /tmp/chk_recv.py',
    timeout=30
)
print(stdout.read().decode())
e = stderr.read().decode()
if e.strip() and 'DeprecationWarning' not in e and 'RequestsDependency' not in e:
    print("STDERR:", e[:200])
c.close()
