"""
Verifica se o monitor está ativo consultando:
1. Thread count do processo plegma-core (thread daemon = monitor)
2. Valor de monitor_ultimo_bloco no DB (se monitorando, está atualizado)
3. Conexões TCP do processo aos RPCs Polygon
"""
import paramiko
import time
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from daemon_config import NODES, SSH_KEY

REMOTE = """
import sys, time
sys.path.insert(0, '/root/PLEGMA_CORE')

# 1. Verificar DB — monitor_ultimo_bloco
import plegma_db

bloco_db = plegma_db.carregar_estado("monitor_ultimo_bloco", None)
carteira = plegma_db.carregar_estado("carteira_recebimento", "")
print(f"monitor_ultimo_bloco: {bloco_db}")
print(f"carteira_recebimento: {carteira[:20] if carteira else 'NAO_CONFIGURADA'}...")

# 2. Thread count do processo core_api
import subprocess
pid_out = subprocess.run(['pgrep', '-f', 'core_api.py'], capture_output=True, text=True)
pid = pid_out.stdout.strip().split()[0] if pid_out.stdout.strip() else None
if pid:
    try:
        with open(f'/proc/{pid}/status') as f:
            for line in f:
                if 'Threads' in line:
                    print(f"core_api PID {pid} threads: {line.strip()}")
                    break
    except Exception as e:
        print(f"Erro lendo /proc: {e}")

# 3. Conexões de rede ao polygon
net_out = subprocess.run(
    ['ss', '-tnp', f'pid={pid}'],
    capture_output=True, text=True
)
polygon_conns = [l for l in net_out.stdout.split('\\n') if 'ankr' in l or 'blast' in l or 'tenderly' in l or 'polygon' in l.lower() or '443' in l]
if polygon_conns:
    print(f"Conexões Polygon: {len(polygon_conns)}")
    for l in polygon_conns[:5]:
        print(f"  {l[:100]}")
else:
    # Verificar todas conexoes TCP do processo
    all_conns = [l for l in net_out.stdout.split('\\n') if l.strip() and 'LISTEN' not in l and 'Local' not in l]
    print(f"Total conexões TCP do processo: {len(all_conns)}")
    for l in all_conns[:5]:
        print(f"  {l[:100]}")

# 4. Verificar bloco Polygon agora para comparar
try:
    from web3 import Web3
    w3 = Web3(Web3.HTTPProvider('https://rpc.ankr.com/polygon', request_kwargs={"timeout": 10}))
    bloco_atual = w3.eth.block_number
    print(f"Bloco Polygon atual: {bloco_atual}")
    if bloco_db:
        diff = bloco_atual - int(bloco_db)
        print(f"Diferença (bloco_atual - monitor_db): {diff} blocos")
        if diff < 200:
            print("STATUS: Monitor ATIVO (bloco recente no DB)")
        else:
            print(f"STATUS: Monitor possivelmente atrasado ou inativo ({diff} blocos atrás)")
except Exception as e:
    print(f"Erro checando bloco Polygon: {e}")
"""

key = paramiko.Ed25519Key.from_private_key_file(SSH_KEY)

for node_id, node in NODES.items():
    try:
        c = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        c.connect(node['ip'], username='root', pkey=key, timeout=12)
        transport = c.get_transport()
        if transport:
            transport.set_keepalive(20)

        sftp = c.open_sftp()
        with sftp.open('/tmp/chk_db.py', 'w') as f:
            f.write(REMOTE)
        sftp.close()

        _, stdout, stderr = c.exec_command(
            'cd /root/PLEGMA_CORE && python3 /tmp/chk_db.py; rm -f /tmp/chk_db.py',
            timeout=30
        )
        out = stdout.read().decode()
        err = stderr.read().decode()

        print(f"\n=== {node['label']} ===")
        print(out)
        if err.strip() and 'DeprecationWarning' not in err and 'RequestsDependencyWarning' not in err:
            print("ERR:", err[:200])
        c.close()
    except Exception as e:
        print(f"\n=== {node['label']} === ERRO: {e}")
