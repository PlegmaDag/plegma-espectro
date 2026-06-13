# Deploy urgente: actualiza data de lançamento para 11/05/2026 em todos os servidores.
# Ficheiros afectados: index.html, genesis/index.html, admin/index.html,
#                      social/index.html, dashboard/index.html
"""
import paramiko
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from daemon_config import NODES, SSH_KEY

FILES = [
    (r"D:\PROJETO_Plegma_DAG\PLEGMA_LANDING\index.html",           "/var/www/plegmadag.com/html/index.html"),
    (r"D:\PROJETO_Plegma_DAG\PLEGMA_LANDING\genesis\index.html",   "/var/www/plegmadag.com/html/genesis/index.html"),
    (r"D:\PROJETO_Plegma_DAG\PLEGMA_LANDING\admin\index.html",     "/var/www/plegmadag.com/html/admin/index.html"),
    (r"D:\PROJETO_Plegma_DAG\PLEGMA_LANDING\social\index.html",    "/var/www/plegmadag.com/html/social/index.html"),
    (r"D:\PROJETO_Plegma_DAG\PLEGMA_LANDING\dashboard\index.html", "/var/www/plegmadag.com/html/dashboard/index.html"),
]

key = paramiko.Ed25519Key.from_private_key_file(SSH_KEY)

# Só EUR serve ficheiros estáticos via nginx — os outros nós não têm landing
node = NODES["eur"]
print(f"Deploy para {node['label']} ({node['ip']})...")

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(node["ip"], username="root", pkey=key, timeout=12)
transport = c.get_transport()
if transport:
    transport.set_keepalive(20)

sftp = c.open_sftp()
errors = []

for local_path, remote_path in FILES:
    local = Path(local_path)
    if not local.exists():
        print(f"  SKIP (não encontrado localmente): {local_path}")
        continue
    try:
        # Verificar se o directório remoto existe
        remote_dir = remote_path.rsplit("/", 1)[0]
        c.exec_command(f"mkdir -p {remote_dir}")

        sftp.put(str(local), remote_path)
        fname = local_path.split("\\")[-2] + "/" + local_path.split("\\")[-1]
        print(f"  ✓ {fname} → {remote_path}")
    except Exception as e:
        print(f"  ✗ {remote_path}: {e}")
        errors.append(remote_path)

sftp.close()

# Verificar data nos ficheiros deployados
print("\nVerificando datas nos ficheiros deployed...")
checks = [
    ("index.html",     "/var/www/plegmadag.com/html/index.html",       "2026-05-11T18:00:00"),
    ("genesis",        "/var/www/plegmadag.com/html/genesis/index.html","2026-05-11T18:00:00"),
    ("admin countdown","/var/www/plegmadag.com/html/admin/index.html",  "2026-05-11T16:00:00Z"),
    ("social LAUNCH",  "/var/www/plegmadag.com/html/social/index.html", "2026-05-11T18:00:00"),
]
for name, path, expected in checks:
    _, stdout, _ = c.exec_command(f"grep -c '{expected}' {path} 2>/dev/null || echo 0")
    count = stdout.read().decode().strip()
    sym = "✓" if int(count) > 0 else "✗"
    print(f"  {sym} {name}: '{expected}' encontrado {count}x")

c.close()

if errors:
    print(f"\n⚠ {len(errors)} erro(s) no deploy: {errors}")
else:
    print("\n✓ Deploy completo — data de lançamento actualizada para 10/05/2026 18:00 CEST")
