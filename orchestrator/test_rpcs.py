import paramiko
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from daemon_config import NODES, SSH_KEY

REMOTE = """
from web3 import Web3
import time

RPCS = [
    "https://polygon-mainnet.public.blastapi.io",
    "https://gateway.tenderly.co/public/polygon",
    "https://polygon.drpc.org",
    "https://polygon-rpc.com",
    "https://rpc-mainnet.matic.quiknode.pro",
    "https://matic-mainnet.chainstacklabs.com",
    "https://rpc.ankr.com/polygon",
    "https://endpoints.omniatech.io/v1/matic/mainnet/public",
]

print("Testando RPCs Polygon:")
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
        err = str(e)
        if len(err) > 80:
            err = err[:80] + "..."
        print(f"  ERR {rpc} | {err}")

print(f"\\nRPCs funcionais: {len(ok)}/{len(RPCS)}")
"""

key = paramiko.Ed25519Key.from_private_key_file(SSH_KEY)
# Testar só no EUR (representativo)
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(NODES['eur']['ip'], username='root', pkey=key, timeout=12)

sftp = c.open_sftp()
with sftp.open('/tmp/test_rpcs.py', 'w') as f:
    f.write(REMOTE)
sftp.close()

_, stdout, stderr = c.exec_command('python3 /tmp/test_rpcs.py; rm -f /tmp/test_rpcs.py', timeout=60)
print(stdout.read().decode())
c.close()
