"""
Deploy Web App Plegma (app.plegmadag.com)
Este script transfere o build do Flutter Web para o servidor de produção (EUR)
"""
import paramiko
import sys
import os
from pathlib import Path

# Adiciona o caminho local para poder importar o daemon_config
sys.path.insert(0, str(Path(__file__).parent))
from daemon_config import NODES, SSH_KEY

def transfer_dir(sftp, local_dir, remote_dir):
    """Função recursiva para enviar uma diretoria inteira via SFTP"""
    for root, dirs, files in os.walk(local_dir):
        # Calcula o caminho relativo para replicar no servidor
        rel_path = os.path.relpath(root, local_dir)
        if rel_path == ".":
            remote_path = remote_dir
        else:
            remote_path = f"{remote_dir}/{rel_path.replace(os.sep, '/')}"
        
        # Cria a diretoria remotamente se não existir
        try:
            sftp.stat(remote_path)
        except IOError:
            sftp.mkdir(remote_path)
            
        for file in files:
            local_file = os.path.join(root, file)
            remote_file = f"{remote_path}/{file}"
            print(f"  Enviando: {rel_path}/{file}" if rel_path != "." else f"  Enviando: {file}")
            sftp.put(local_file, remote_file)

# O build do Flutter fica na pasta build/web
LOCAL_WEB_DIR = r"D:\PROJETO_Plegma_DAG\plegma_app\build\web"
REMOTE_WEB_DIR = "/var/www/plegmadag.com/html/app"

# Ficheiro de configuração do Nginx
LOCAL_NGINX_CONF = r"D:\PROJETO_Plegma_DAG\_nginx_app.conf"
REMOTE_NGINX_CONF = "/etc/nginx/sites-available/app.plegmadag.com"

key = paramiko.Ed25519Key.from_private_key_file(SSH_KEY)

# Servidor principal (Nginx front-end)
node = NODES["eur"]
print(f"\n[Deploy App Web] Conectando a {node['label']} ({node['ip']})...")

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
try:
    c.connect(node["ip"], username="root", pkey=key, timeout=12)
except Exception as e:
    print(f"Erro ao conectar: {e}")
    sys.exit(1)

transport = c.get_transport()
if transport:
    transport.set_keepalive(20)

sftp = c.open_sftp()

print("\n1. Preparando diretoria remota...")
c.exec_command(f"mkdir -p {REMOTE_WEB_DIR}")

# Verifica se o build local existe
if not os.path.exists(LOCAL_WEB_DIR):
    print(f"\nERRO: Pasta de build não encontrada em {LOCAL_WEB_DIR}")
    print("Execute 'flutter build web --web-renderer html --release' primeiro!")
    sftp.close()
    c.close()
    sys.exit(1)

print("\n2. Transferindo arquivos do Web App...")
transfer_dir(sftp, LOCAL_WEB_DIR, REMOTE_WEB_DIR)

print("\n3. Transferindo configuração do Nginx...")
if os.path.exists(LOCAL_NGINX_CONF):
    sftp.put(LOCAL_NGINX_CONF, REMOTE_NGINX_CONF)
    
    # Ativa o site no nginx
    print("   Ativando site no Nginx...")
    c.exec_command(f"ln -sf {REMOTE_NGINX_CONF} /etc/nginx/sites-enabled/")
    
    # Executa o certbot (se o DNS já estiver propagado)
    print("\n   [NOTA] Para gerar o certificado SSL automaticamente (quando o DNS estiver pronto), rode no servidor:")
    print("   certbot --nginx -d app.plegmadag.com")
else:
    print(f"  ERRO: Configuração do nginx não encontrada em {LOCAL_NGINX_CONF}")

print("\n4. Reiniciando Nginx...")
stdin, stdout, stderr = c.exec_command("nginx -t && systemctl restart nginx")
err = stderr.read().decode().strip()
if "successful" in err or "test is successful" in err:
    print("  Nginx test OK, restarted.")
else:
    print(f"  Aviso ao reiniciar o Nginx: {err}")

sftp.close()
c.close()

print("\n✓ Deploy finalizado com sucesso!")
