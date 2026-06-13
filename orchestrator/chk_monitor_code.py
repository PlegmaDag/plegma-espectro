import paramiko
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from daemon_config import NODES, SSH_KEY

CMDS = """
echo "=== monitor_pagamentos.py ==="
cat /root/PLEGMA_CORE/monitor_pagamentos.py

echo ""
echo "=== Ultimas linhas do journal plegma-core ==="
journalctl -u plegma-core -n 80 --no-pager 2>/dev/null | tail -80

echo ""
echo "=== Verificar se web3 consegue conectar Polygon ==="
python3 -c "
from web3 import Web3
w = Web3(Web3.HTTPProvider('https://polygon-rpc.com'))
print('Polygon connected:', w.is_connected())
try:
    block = w.eth.block_number
    print('Current block:', block)
except Exception as e:
    print('Block error:', e)
" 2>&1
"""

key = paramiko.Ed25519Key.from_private_key_file(SSH_KEY)
c   = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(NODES['eur']['ip'], username='root', pkey=key, timeout=12)
transport = c.get_transport()
if transport:
    transport.set_keepalive(20)

_, stdout, stderr = c.exec_command(CMDS, timeout=30)
print(stdout.read().decode())
e = stderr.read().decode()
if e.strip(): print('ERR:', e[:300])
c.close()
