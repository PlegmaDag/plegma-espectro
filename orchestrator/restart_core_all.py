import paramiko
import time
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from daemon_config import NODES, SSH_KEY

key = paramiko.Ed25519Key.from_private_key_file(SSH_KEY)

def restart_node(node_id, node):
    try:
        c = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        c.connect(node['ip'], username='root', pkey=key, timeout=12)
        transport = c.get_transport()
        if transport:
            transport.set_keepalive(20)

        print(f"[{node['label']}] Reiniciando plegma-core...")
        _, stdout, stderr = c.exec_command('systemctl restart plegma-core', timeout=20)
        stdout.read()

        time.sleep(8)

        # Verificar se está ativo
        _, stdout2, _ = c.exec_command('systemctl is-active plegma-core')
        status = stdout2.read().decode().strip()

        # Verificar se monitor iniciou (log recente)
        _, stdout3, _ = c.exec_command(
            'journalctl -u plegma-core -n 30 --no-pager 2>/dev/null | tail -30'
        )
        logs = stdout3.read().decode()

        c.close()
        return status, logs
    except Exception as e:
        return "error", str(e)

# Reiniciar todos em sequência (evitar carga simultânea)
for node_id, node in NODES.items():
    status, logs = restart_node(node_id, node)
    print(f"[{node['label']}] status={status}")
    # Mostrar últimas linhas relevantes
    for line in logs.split('\n'):
        if any(kw in line for kw in ['MONITOR', 'monitor', 'Started', 'Active', 'error', 'Error', 'Failed', 'Exception']):
            print(f"  {line.strip()[:120]}")
    print()

print("Aguardando 30s para monitor iniciar...")
time.sleep(30)

# Verificação final — HTTP status
print("\n=== Verificação final ===")
import urllib.request
import json

for node_id, node in NODES.items():
    try:
        c = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        c.connect(node['ip'], username='root', pkey=key, timeout=12)

        _, stdout, _ = c.exec_command(
            'curl -s --max-time 5 http://localhost:8080/api/status 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get(\'online\', d.get(\'status\', \'ok\')))" 2>/dev/null || echo "err"'
        )
        api_ok = stdout.read().decode().strip()

        # Verificar monitor ativo via log
        _, stdout2, _ = c.exec_command(
            'journalctl -u plegma-core -n 100 --no-pager 2>/dev/null | grep -i "MONITOR" | tail -5'
        )
        mon_lines = stdout2.read().decode().strip()

        c.close()
        print(f"[{node['label']}] API={api_ok} | Monitor logs: {mon_lines[:120] if mon_lines else '(nenhum no journal)'}")
    except Exception as e:
        print(f"[{node['label']}] ERRO: {e}")
