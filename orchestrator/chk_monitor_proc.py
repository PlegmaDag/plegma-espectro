import paramiko
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from daemon_config import NODES, SSH_KEY

CMDS = """
# PID do core_api
PID=$(pgrep -f 'core_api.py' | head -1)
echo "=== PID core_api: $PID ==="

# Threads do processo (thread count indica monitor em background)
echo "=== Threads do processo ==="
ls /proc/$PID/task/ 2>/dev/null | wc -l
cat /proc/$PID/status | grep -E 'Threads|VmRSS'

# Conexoes de rede do processo (Polygon RPC usa HTTPS/443)
echo "=== Conexões de rede ==="
ss -tnp | grep "pid=$PID" | head -20

# Logs do core (últimas 40 linhas que mencionem monitor ou pagamento)
echo "=== Logs monitor/pagamento ==="
journalctl -u plegma-core --since '1 hour ago' --no-pager 2>/dev/null | grep -i -E 'monitor|pagamento|deposit|polygon|usdc|web3' | tail -20

# Se não houver journalctl, tentar stderr do processo
echo "=== Ficheiro de log se existir ==="
ls /root/PLEGMA_CORE/*.log 2>/dev/null
tail -30 /root/PLEGMA_CORE/core.log 2>/dev/null || echo "(sem core.log)"

# Verificar startup do core_api com strace (rapido)
echo "=== Verificar se monitor_pagamentos foi importado ==="
grep -r 'iniciar\|monitor_pagamentos\|carteira_recebimento' /root/PLEGMA_CORE/core_api.py | head -20
"""

key = paramiko.Ed25519Key.from_private_key_file(SSH_KEY)
c   = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(NODES['eur']['ip'], username='root', pkey=key, timeout=12)
transport = c.get_transport()
if transport:
    transport.set_keepalive(20)

_, stdout, stderr = c.exec_command(CMDS)
print(stdout.read().decode())
e = stderr.read().decode()
if e.strip(): print('ERR:', e[:200])
c.close()
