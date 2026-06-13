import paramiko
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from daemon_config import NODES, SSH_KEY

REMOTE = """
import sys, json
sys.path.insert(0, '/root/PLEGMA_CORE')

# 1. Verificar se monitor_pagamentos tem thread ativa
try:
    import monitor_pagamentos as mp
    import threading

    # Verificar threads
    all_threads = threading.enumerate()
    monitor_threads = [t for t in all_threads if 'monitor' in t.name.lower() or 'pagamento' in t.name.lower()]
    daemon_threads  = [t for t in all_threads if t.daemon]

    print(f"Threads totais: {len(all_threads)}")
    print(f"Threads daemon: {len(daemon_threads)}")
    print(f"Threads monitor: {len(monitor_threads)}")
    for t in all_threads:
        print(f"  Thread: {t.name} | daemon={t.daemon} | alive={t.is_alive()}")

    # Estado do monitor
    print()
    print(f"mp._carteira    = {getattr(mp, '_carteira', 'N/A')}")
    print(f"mp._ativo       = {getattr(mp, '_ativo', 'N/A')}")
    print(f"mp._thread      = {getattr(mp, '_thread', 'N/A')}")

except Exception as e:
    print(f"Erro importando monitor: {e}")

# 2. Verificar se há processo Python do core rodando com monitor
print()
print("=== Processos Python ativos ===")
import subprocess
r = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
for line in r.stdout.split('\\n'):
    if 'python' in line.lower() or 'uvicorn' in line.lower():
        print(' ', line[:120])
"""

key = paramiko.Ed25519Key.from_private_key_file(SSH_KEY)
c   = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(NODES['eur']['ip'], username='root', pkey=key, timeout=12)

sftp = c.open_sftp()
with sftp.open('/tmp/chk_mon.py', 'w') as f:
    f.write(REMOTE)
sftp.close()

_, stdout, stderr = c.exec_command('cd /root/PLEGMA_CORE && python3 /tmp/chk_mon.py; rm -f /tmp/chk_mon.py')
print("=== EUR — estado do monitor ===")
print(stdout.read().decode())
e = stderr.read().decode()
if e: print('ERR:', e[:300])
c.close()
