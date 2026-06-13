import paramiko
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from daemon_config import NODES, SSH_KEY

REMOTE = """
from web3 import Web3

RPCS = [
    "https://polygon.llamarpc.com",
    "https://polygon-bor-rpc.publicnode.com",
    "https://polygon.api.onfinality.io/public",
    "https://rpc.polyflow.app",
    "https://polygon-mainnet.g.alchemy.com/v2/demo",
    "https://polygon.meowrpc.com",
    "https://polygon.rpc.subquery.network/public",
]

print("Testando RPCs adicionais:")
ok = []
for rpc in RPCS:
    try:
        w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 8}))
        bloco = w3.eth.block_number
        if bloco and bloco > 0:
            print(f"  OK  {rpc} | bloco={bloco}")
            ok.append(rpc)
        else:
            print(f"  ERR {rpc} | bloco={bloco}")
    except Exception as e:
        err = str(e)[:80]
        print(f"  ERR {rpc} | {err}")

print(f"\\nOK: {len(ok)}")
for r in ok:
    print(f'  "{r}",')
"""

key = paramiko.Ed25519Key.from_private_key_file(SSH_KEY)
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(NODES['eur']['ip'], username='root', pkey=key, timeout=12)

sftp = c.open_sftp()
with sftp.open('/tmp/test_rpcs2.py', 'w') as f:
    f.write(REMOTE)
sftp.close()

_, stdout, _ = c.exec_command('python3 /tmp/test_rpcs2.py; rm -f /tmp/test_rpcs2.py', timeout=60)
print(stdout.read().decode())
c.close()
