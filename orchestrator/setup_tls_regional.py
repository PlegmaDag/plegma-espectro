#!/usr/bin/env python3
"""
PLEGMA ORCHESTRATOR — Setup TLS Subdomínios Regionais
Configura nginx + certbot para br/mal/sin.plegmadag.com em cada nó.

PRÉ-REQUISITO: A-records DNS devem estar criados no Njalla:
  usa.plegmadag.com → 209.126.7.120
  mum.plegmadag.com → 217.217.251.206
  sin.plegmadag.com → 82.197.70.189

Uso: python setup_tls_regional.py [--check-only]
"""
import subprocess
import sys
import socket
import tempfile
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from daemon_config import NODES, SSH_KEY, SSH_USER
import paramiko

_OPTS = ["-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=10", "-i", SSH_KEY]

# Mapeamento nó → subdomínio regional
_SUBDOMAIN_MAP = {
    "usa": "usa.plegmadag.com",
    "mum": "mum.plegmadag.com",
    "sin": "sin.plegmadag.com",
}

# Config HTTP-only para certbot emitir o cert (fase 1)
_NGINX_HTTP_ONLY = """\
server {{
    listen 80;
    listen [::]:80;
    server_name {subdomain};
    location / {{
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }}
}}
"""

# Config HTTPS completa (fase 2 — após cert emitido)
_NGINX_HTTPS = """\
map $http_origin $cors_origin_{safe} {{
    default                      "";
    "https://plegmadag.com"      "https://plegmadag.com";
    "https://www.plegmadag.com"  "https://www.plegmadag.com";
    "null"                       "null";
    ""                           "";
}}

server {{
    listen 80;
    listen [::]:80;
    server_name {subdomain};
    return 301 https://$host$request_uri;
}}

server {{
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name {subdomain};

    ssl_certificate     /etc/letsencrypt/live/{subdomain}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/{subdomain}/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;

    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
    add_header X-Content-Type-Options    "nosniff"       always;
    add_header X-Frame-Options           "DENY"           always;
    add_header Referrer-Policy           "no-referrer"    always;
    add_header X-Plegma-Protocol         "DAG-V4-PQC"    always;

    location /api/auth/ {{
        proxy_pass       http://127.0.0.1:8082;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        add_header Access-Control-Allow-Origin  $cors_origin_{safe} always;
        add_header Access-Control-Allow-Methods 'GET, POST, OPTIONS' always;
        add_header Access-Control-Allow-Headers 'Content-Type, Authorization' always;
    }}

    location /wallet/ {{
        proxy_pass       http://127.0.0.1:8083;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        add_header Access-Control-Allow-Origin  $cors_origin_{safe} always;
        add_header Access-Control-Allow-Methods 'GET, POST, OPTIONS' always;
        add_header Access-Control-Allow-Headers 'Content-Type, Authorization' always;
    }}

    location /shield/ {{
        proxy_pass       http://127.0.0.1:8085;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        add_header Access-Control-Allow-Origin  $cors_origin_{safe} always;
        add_header Access-Control-Allow-Methods 'GET, POST, OPTIONS' always;
        add_header Access-Control-Allow-Headers 'Content-Type' always;
    }}

    location / {{
        proxy_pass       http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        add_header Access-Control-Allow-Origin  $cors_origin_{safe} always;
        add_header Access-Control-Allow-Methods 'GET, POST, OPTIONS' always;
        add_header Access-Control-Allow-Headers 'Content-Type, Authorization' always;
    }}
}}
"""


def _connect(ip: str) -> paramiko.SSHClient:
    key = paramiko.Ed25519Key.from_private_key_file(SSH_KEY)
    c   = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(ip, username=SSH_USER, pkey=key, timeout=15)
    return c


def _ssh(ip: str, cmd: str, timeout: int = 30) -> tuple[int, str]:
    r = subprocess.run(
        ["ssh"] + _OPTS + [f"{SSH_USER}@{ip}", cmd],
        capture_output=True, text=True, timeout=timeout
    )
    return r.returncode, (r.stdout + r.stderr).strip()


def _upload_text(client: paramiko.SSHClient, content: str, remote_path: str) -> bool:
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.conf',
                                         delete=False, encoding='utf-8') as f:
            f.write(content)
            tmp = f.name
        sftp = client.open_sftp()
        sftp.put(tmp, remote_path)
        sftp.close()
        os.unlink(tmp)
        return True
    except Exception as e:
        print(f"    sftp erro: {e}")
        return False


def _run(client: paramiko.SSHClient, cmd: str, timeout: int = 60) -> tuple[int, str]:
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out  = stdout.read().decode().strip()
    err  = stderr.read().decode().strip()
    code = stdout.channel.recv_exit_status()
    return code, out or err


def _dns_ok(subdomain: str, expected_ip: str) -> bool:
    try:
        resolved = socket.gethostbyname(subdomain)
        return resolved == expected_ip
    except Exception:
        return False


def main():
    check_only = "--check-only" in sys.argv
    print("⬡ PLEGMA — Setup TLS Subdomínios Regionais\n")

    all_dns_ok = True
    for nid, subdomain in _SUBDOMAIN_MAP.items():
        node = NODES[nid]
        ip   = node["ip"]
        ok   = _dns_ok(subdomain, ip)
        sym  = "✓" if ok else "✕"
        print(f"  {sym} DNS {subdomain} → {ip} {'(OK)' if ok else '(NAO RESOLVE)'}")
        if not ok:
            all_dns_ok = False

    if not all_dns_ok:
        print("\n⚠  DNS não propagado. Criar A-records no Njalla:")
        for nid, subdomain in _SUBDOMAIN_MAP.items():
            print(f"     {subdomain} → {NODES[nid]['ip']}")
        print("\nVoltar a correr após propagação (5-60 min).")
        return

    if check_only:
        print("\n✓ DNS OK — pronto para instalar. Correr sem --check-only para configurar.")
        return

    print()
    for nid, subdomain in _SUBDOMAIN_MAP.items():
        node  = NODES[nid]
        ip    = node["ip"]
        label = node.get("label", nid)
        safe  = nid

        print(f"[{label}] {ip} — {subdomain}")
        config_path  = f"/etc/nginx/sites-available/{subdomain}"
        enabled_path = f"/etc/nginx/sites-enabled/{subdomain}"

        try:
            client = _connect(ip)
        except Exception as e:
            print(f"  ✕ SSH falhou: {e}")
            continue

        # ── FASE 1: config HTTP-only (upload via SFTP) ──
        http_config = _NGINX_HTTP_ONLY.format(subdomain=subdomain)
        ok = _upload_text(client, http_config, config_path)
        print(f"  {'✓' if ok else '✕'} config HTTP-only carregada")
        if not ok:
            client.close(); continue

        rc, _ = _run(client, f"ln -sf {config_path} {enabled_path}")
        rc, out = _run(client, "nginx -t 2>&1 && nginx -s reload 2>&1")
        ok_http = rc == 0
        print(f"  {'✓' if ok_http else '✕'} nginx HTTP reload: {out[:100] if not ok_http else 'OK'}")
        if not ok_http:
            client.close(); continue

        # ── FASE 2: certbot emite cert (nginx já serve :80) ──
        certbot_cmd = (
            f"certbot certonly --nginx -d {subdomain} "
            f"--non-interactive --agree-tos --email admin@plegmadag.com "
            f"--no-eff-email 2>&1"
        )
        print(f"  → certbot (até 120s)...")
        rc, out = _run(client, certbot_cmd, timeout=120)
        ok_cert = rc == 0
        print(f"  {'✓' if ok_cert else '✕'} certbot: {out[-200:]}")
        if not ok_cert:
            _run(client, f"rm -f {enabled_path}")
            _run(client, "nginx -s reload 2>/dev/null")
            client.close(); continue

        # ── FASE 3: config HTTPS completa (upload via SFTP) ──
        https_config = _NGINX_HTTPS.format(subdomain=subdomain, safe=safe)
        ok = _upload_text(client, https_config, config_path)
        print(f"  {'✓' if ok else '✕'} config HTTPS carregada")
        if ok:
            rc, out = _run(client, "nginx -t 2>&1")
            ok_tls = rc == 0
            print(f"  {'✓' if ok_tls else '✕'} nginx -t TLS: {out[:100] if not ok_tls else 'OK'}")
            if ok_tls:
                _run(client, "nginx -s reload")
                print(f"  ✓ nginx activo com TLS ✓")

        client.close()
        print()

    print("⬡ Setup concluído.")


if __name__ == "__main__":
    main()
