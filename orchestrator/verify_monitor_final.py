"""
Verificação final — confirma monitor ativo e bloco atualizado.
"""
import paramiko
import time
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from daemon_config import NODES, SSH_KEY

time.sleep(90)

REMOTE = """
import sys
sys.path.insert(0, '/root/PLEGMA_CORE')
import plegma_db

bloco_db = plegma_db.carregar_estado("monitor_ultimo_bloco", None)
carteira = plegma_db.carregar_estado("carteira_recebimento", "")

from web3 import Web3
RPCS = [
    "https://polygon.drpc.org",
    "https://rpc-mainnet.matic.quiknode.pro",
    "https://polygon-bor-rpc.publicnode.com",
]
bloco_atual = None
for rpc in RPCS:
    try:
        w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 8}))
        bloco_atual = w3.eth.block_number
        if bloco_atual:
            break
    except:
        continue

if bloco_atual and bloco_db:
    diff = bloco_atual - int(bloco_db)
    # Polygon ~2 blocks/seg, 90s = ~180 blocos. Se diff < 300 = monitor atualizou
    status = "ATIVO" if diff < 300 else "ATRASADO"
    print(f"bloco_db={bloco_db} | bloco_atual={bloco_atual} | diff={diff} | {status}")
else:
    print(f"bloco_db={bloco_db} | bloco_atual={bloco_atual}")

print(f"carteira={carteira[:20] if carteira else 'NAO_CONFIGURADA'}...")
"""

key = paramiko.Ed25519Key.from_private_key_file(SSH_KEY)

print("=== Verificação final do monitor (após 90s) ===")
all_ok = True
for node_id, node in NODES.items():
    try:
        c = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        c.connect(node['ip'], username='root', pkey=key, timeout=12)
        transport = c.get_transport()
        if transport:
            transport.set_keepalive(20)

        sftp = c.open_sftp()
        with sftp.open('/tmp/vmon.py', 'w') as f:
            f.write(REMOTE)
        sftp.close()

        _, stdout, stderr = c.exec_command('cd /root/PLEGMA_CORE && python3 /tmp/vmon.py; rm -f /tmp/vmon.py', timeout=20)
        out = stdout.read().decode().strip()
        c.close()

        is_ok = "ATIVO" in out
        if not is_ok:
            all_ok = False
        sym = "✓" if is_ok else "✗"
        print(f"[{node['label']}] {sym} {out}")
    except Exception as e:
        print(f"[{node['label']}] ERRO: {e}")
        all_ok = False

print()
if all_ok:
    print("MONITOR DE PAGAMENTOS: ATIVO em todos os servidores")
    print("Carteira monitorada: 0xd8422d6936be77179dc33c7c2ffceef4c34fb183")
    print("Pronto para receber o $1 USDC de teste.")
else:
    print("ATENÇÃO: algum servidor pode estar com o monitor inativo.")
