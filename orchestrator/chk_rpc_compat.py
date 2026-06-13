import paramiko
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from daemon_config import NODES, SSH_KEY

REMOTE = """
import sys
sys.path.insert(0, '/root/PLEGMA_CORE')

# Testar versao web3 e RPC
from web3 import Web3
print(f"web3 version: {Web3.api}")

# Testar 1rpc.io/matic
try:
    w3 = Web3(Web3.HTTPProvider('https://1rpc.io/matic', request_kwargs={"timeout": 15}))
    block = w3.eth.block_number
    print(f"1rpc.io/matic: OK | bloco atual: {block}")
except Exception as e:
    print(f"1rpc.io/matic: FALHOU -> {e}")

# Testar API de get_logs (v6 vs v7)
import json
USDC_ABI = json.loads('[{"anonymous":false,"inputs":[{"indexed":true,"name":"from","type":"address"},{"indexed":true,"name":"to","type":"address"},{"indexed":false,"name":"value","type":"uint256"}],"name":"Transfer","type":"event"}]')

try:
    w3 = Web3(Web3.HTTPProvider('https://1rpc.io/matic', request_kwargs={"timeout": 15}))
    contrato = w3.eth.contract(
        address=Web3.to_checksum_address("0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"),
        abi=USDC_ABI
    )
    bloco_atual = w3.eth.block_number

    # Testar com snake_case (v7)
    try:
        eventos = contrato.events.Transfer.get_logs(
            from_block=bloco_atual - 5,
            to_block=bloco_atual
        )
        print(f"snake_case (v7 style): OK | {len(eventos)} eventos")
    except Exception as e:
        print(f"snake_case (v7 style): FALHOU -> {type(e).__name__}: {e}")

    # Testar com camelCase (v6)
    try:
        eventos2 = contrato.events.Transfer.get_logs(
            fromBlock=bloco_atual - 5,
            toBlock=bloco_atual
        )
        print(f"camelCase (v6 style): OK | {len(eventos2)} eventos")
    except Exception as e:
        print(f"camelCase (v6 style): FALHOU -> {type(e).__name__}: {e}")

except Exception as e:
    print(f"Erro geral: {e}")
"""

for node_id, node in NODES.items():
    try:
        key = paramiko.Ed25519Key.from_private_key_file(SSH_KEY)
        c   = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        c.connect(node['ip'], username='root', pkey=key, timeout=12)
        transport = c.get_transport()
        if transport:
            transport.set_keepalive(20)

        sftp = c.open_sftp()
        with sftp.open('/tmp/chk_rpc.py', 'w') as f:
            f.write(REMOTE)
        sftp.close()

        _, stdout, stderr = c.exec_command('cd /root/PLEGMA_CORE && python3 /tmp/chk_rpc.py; rm -f /tmp/chk_rpc.py', timeout=30)
        out = stdout.read().decode()
        err = stderr.read().decode()

        print(f"\n=== {node['label']} ===")
        print(out)
        if err.strip():
            print("ERR:", err[:200])
        c.close()
    except Exception as e:
        print(f"\n=== {node['label']} === FALHOU: {e}")
