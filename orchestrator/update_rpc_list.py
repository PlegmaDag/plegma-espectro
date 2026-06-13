"""
Atualiza apenas a lista POLYGON_RPCS em monitor_pagamentos.py em todos os servidores.
"""
import paramiko
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from daemon_config import NODES, SSH_KEY

PATCH = """
import sys
sys.path.insert(0, '/root/PLEGMA_CORE')

# Ler ficheiro atual
with open('/root/PLEGMA_CORE/monitor_pagamentos.py', 'r') as f:
    content = f.read()

OLD = '''POLYGON_RPCS = [
    "https://rpc.ankr.com/polygon",
    "https://polygon-mainnet.public.blastapi.io",
    "https://gateway.tenderly.co/public/polygon",
    "https://polygon.drpc.org",
    "https://polygon-rpc.com",
    "https://rpc-mainnet.matic.quiknode.pro",
]'''

NEW = '''POLYGON_RPCS = [
    "https://polygon.drpc.org",
    "https://rpc-mainnet.matic.quiknode.pro",
    "https://polygon-bor-rpc.publicnode.com",
    "https://polygon.api.onfinality.io/public",
    "https://polygon.rpc.subquery.network/public",
]'''

if OLD in content:
    content = content.replace(OLD, NEW)
    with open('/root/PLEGMA_CORE/monitor_pagamentos.py', 'w') as f:
        f.write(content)
    print("OK: POLYGON_RPCS atualizado")
else:
    # Verificar se ja tem a lista nova
    if 'polygon.drpc.org' in content and 'publicnode.com' in content:
        print("OK: lista ja atualizada")
    else:
        # Mostrar o que temos para diagnostico
        idx = content.find('POLYGON_RPCS')
        print(f"AVISO: padrao nao encontrado. Secao atual:")
        print(content[idx:idx+300] if idx >= 0 else "POLYGON_RPCS nao encontrado")

# Verificar sintaxe
import subprocess
r = subprocess.run(['python3', '-m', 'py_compile', '/root/PLEGMA_CORE/monitor_pagamentos.py'],
                   capture_output=True, text=True)
if r.returncode == 0:
    print("Sintaxe: OK")
else:
    print(f"Sintaxe: ERRO -> {r.stderr[:200]}")
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
        with sftp.open('/tmp/patch_rpcs.py', 'w') as f:
            f.write(PATCH)
        sftp.close()

        _, stdout, stderr = c.exec_command('python3 /tmp/patch_rpcs.py; rm -f /tmp/patch_rpcs.py', timeout=15)
        out = stdout.read().decode().strip()
        err = stderr.read().decode().strip()

        print(f"[{node['label']}] {out}")
        if err and 'DeprecationWarning' not in err:
            print(f"  ERR: {err[:100]}")
        c.close()
    except Exception as e:
        print(f"[{node['label']}] ERRO: {e}")

print("\nReiniciando plegma-core para carregar nova lista RPC...")

# Reiniciar
for node_id, node in NODES.items():
    try:
        c = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        c.connect(node['ip'], username='root', pkey=key, timeout=12)
        c.exec_command('systemctl restart plegma-core', timeout=10)
        import time; time.sleep(2)
        _, s, _ = c.exec_command('systemctl is-active plegma-core')
        status = s.read().decode().strip()
        c.close()
        print(f"[{node['label']}] {status}")
    except Exception as e:
        print(f"[{node['label']}] ERRO: {e}")
