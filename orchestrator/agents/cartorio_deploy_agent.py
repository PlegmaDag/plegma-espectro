#!/usr/bin/env python3
"""
PLEGMA ORCHESTRATOR — Cartório Deploy Agent
Deploy do Plegma Timestamp nos nós de produção via SSH/SFTP (paramiko).

Uso:
  python daemon.py --run cartorio_deploy            # todos os 4 nós
  python daemon.py --run cartorio_deploy            # com context {"node": "eur"}

Fases por nó:
  1. Criar directórios remotos
  2. Transferir ficheiros via SFTP (backend + frontend)
  3. Instalar dependências Python (venv isolado)
  4. Escrever .env de produção
  5. Instalar config nginx + reload
  6. Expandir certificado SSL (certbot --expand)
  7. Instalar + (re)iniciar serviço systemd
  8. Health check final
"""

import sys
import io
import time
import logging
from pathlib import Path

import paramiko

sys.path.insert(0, str(Path(__file__).parent.parent))
from daemon_config import (
    NODES, SSH_KEY, SSH_USER,
    CARTORIO_PORT, CARTORIO_SERVICE, CARTORIO_REMOTE,
    CARTORIO_DOMAIN, CARTORIO_LOCAL, ROOT,
)
from . import BaseAgent, AgentResult
import event_log

log = logging.getLogger("plegma.cartorio_deploy")

# ── Ficheiros a transferir ────────────────────────────────────────────────────

_BACKEND = [
    "backend/__init__.py",
    "backend/main.py",
    "backend/models.py",
    "backend/database.py",
    "backend/plegma_adapter.py",
    "backend/certificate.py",
    "backend/payment_service.py",
    "backend/api_keys_service.py",
    "backend/pdf_engine.py",
]

_FRONTEND = [
    "frontend/index.html",
    "frontend/verify.html",
    "frontend/api-keys.html",
    "frontend/plegma_crypto.js",
    "frontend/plegma_crypto.wasm",
    "frontend/plegma_crypto_bridge.js",
]

# .env de produção (placeholders para carteiras — editar no servidor após deploy)
_ENV_PROD = f"""PLEGMA_MOCK_MODE=false
PLEGMA_RPC_URL=http://localhost:8080
PLEGMA_CORE_PATH=/root/PLEGMA_CORE
PLEGMA_CARTORIO_WALLET=PLG_SUBSTITUIR_CARTEIRA_CARTORIO
PLEGMA_AUTHOR_WALLET=PLG198840FFDD9FA7A8AEA2747C994B152B88A49F7C
PLEGMA_AERARIUM_WALLET=PLG_SUBSTITUIR_CARTEIRA_AERARIUM
PAYMENT_ENABLED=true
PLG_PAYMENT_AMOUNT=2
PAYMENT_SESSION_EXPIRE_MINUTES=10
DATABASE_URL={CARTORIO_REMOTE}/cartorio.db
BASE_URL=https://{CARTORIO_DOMAIN}
CORS_ORIGINS=https://{CARTORIO_DOMAIN},https://plegmadag.com
PLG_USD_RATE=0.10
API_KEY_MIN_LOCK_USD=10
"""

# Serviço systemd
_SYSTEMD_UNIT = f"""[Unit]
Description=Plegma Timestamp
After=network.target plegma-core.service
Wants=plegma-core.service

[Service]
Type=simple
User=root
WorkingDirectory={CARTORIO_REMOTE}/backend
EnvironmentFile={CARTORIO_REMOTE}/.env
ExecStart={CARTORIO_REMOTE}/venv/bin/uvicorn main:app --host 0.0.0.0 --port {CARTORIO_PORT} --workers 2
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier={CARTORIO_SERVICE}

[Install]
WantedBy=multi-user.target
"""

# Config nginx (lida do ficheiro local)
_NGINX_CONF_LOCAL = ROOT / "_nginx_cartorio.conf"
_NGINX_CONF_REMOTE = "/etc/nginx/sites-enabled/cartorio.conf"

# Dependências Python
_PIP_PACKAGES = (
    "fastapi 'uvicorn[standard]' aiosqlite blake3 httpx "
    "fpdf2 'qrcode[pil]' pillow python-dotenv python-multipart "
    "pypdf reportlab python-docx"
)


# ── Helpers SSH / SFTP ────────────────────────────────────────────────────────

def _connect(ip: str) -> "paramiko.SSHClient | None":
    try:
        key = paramiko.Ed25519Key.from_private_key_file(SSH_KEY)
        c   = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        c.connect(ip, username=SSH_USER, pkey=key, timeout=20)
        t = c.get_transport()
        if t:
            t.set_keepalive(30)
        return c
    except Exception as e:
        log.error(f"SSH connect {ip}: {e}")
        return None


def _ssh(client: "paramiko.SSHClient", cmd: str, timeout: int = 120) -> tuple[int, str]:
    _, out, err = client.exec_command(cmd, timeout=timeout)
    out.channel.settimeout(timeout)
    try:
        stdout = out.read().decode(errors="replace").strip()
        stderr = err.read().decode(errors="replace").strip()
        rc     = out.channel.recv_exit_status()
        return rc, stdout or stderr
    except Exception:
        return -1, "timeout"


def _sftp_put_bytes(sftp: "paramiko.SFTPClient", data: bytes, remote_path: str) -> bool:
    try:
        with sftp.open(remote_path, "wb") as f:
            f.write(data)
        return True
    except Exception as e:
        log.error(f"SFTP put {remote_path}: {e}")
        return False


def _sftp_put_file(sftp: "paramiko.SFTPClient", local: Path, remote: str) -> bool:
    try:
        sftp.put(str(local), remote)
        return True
    except Exception as e:
        log.error(f"SFTP put {local} → {remote}: {e}")
        return False


# ── Deploy de um nó ───────────────────────────────────────────────────────────

def _deploy_node(ip: str, label: str) -> tuple[bool, list[str]]:
    steps  = []
    errors = []

    client = _connect(ip)
    if not client:
        return False, [f"SSH falhou para {label} ({ip})"]

    try:
        sftp = client.open_sftp()

        # 1. Criar directórios
        log.info(f"[{label}] Criar directórios")
        rc, _ = _ssh(client, f"mkdir -p {CARTORIO_REMOTE}/backend {CARTORIO_REMOTE}/frontend")
        if rc != 0:
            errors.append(f"{label}: mkdir falhou"); return False, errors
        steps.append("dirs OK")

        # 2. Transferir backend
        log.info(f"[{label}] Transferir backend ({len(_BACKEND)} ficheiros)")
        errs = 0
        for rel in _BACKEND:
            local = CARTORIO_LOCAL / rel.replace("/", "\\")
            if not local.exists():
                log.warning(f"  não encontrado: {local}"); errs += 1; continue
            if not _sftp_put_file(sftp, local, f"{CARTORIO_REMOTE}/{rel}"):
                errs += 1
        if errs:
            errors.append(f"{label}: {errs} ficheiros backend falharam")
        else:
            steps.append("backend OK")

        # 3. Transferir frontend
        log.info(f"[{label}] Transferir frontend ({len(_FRONTEND)} ficheiros)")
        for rel in _FRONTEND:
            local = CARTORIO_LOCAL / rel.replace("/", "\\")
            if local.exists():
                _sftp_put_file(sftp, local, f"{CARTORIO_REMOTE}/{rel}")
        steps.append("frontend OK")

        # 4. Escrever .env (apenas se não existir — preserva carteiras já configuradas)
        rc, _ = _ssh(client, f"test -f {CARTORIO_REMOTE}/.env && echo EXISTS || echo MISSING")
        if "MISSING" in _[1] if isinstance(_, tuple) else "":
            _sftp_put_bytes(sftp, _ENV_PROD.encode(), f"{CARTORIO_REMOTE}/.env")
            steps.append(".env criado")
        else:
            # Ficheiro existe — actualizar apenas BASE_URL e CORS_ORIGINS
            _ssh(client, f"sed -i 's|^BASE_URL=.*|BASE_URL=https://{CARTORIO_DOMAIN}|' {CARTORIO_REMOTE}/.env")
            _ssh(client, f"sed -i 's|^CORS_ORIGINS=.*|CORS_ORIGINS=https://{CARTORIO_DOMAIN},https://plegmadag.com|' {CARTORIO_REMOTE}/.env")
            steps.append(".env actualizado")

        # 4b. Forçar escrita .env se test falhou (lógica simplificada)
        rc2, out2 = _ssh(client, f"test -f {CARTORIO_REMOTE}/.env && echo YES || echo NO")
        if "NO" in out2:
            _sftp_put_bytes(sftp, _ENV_PROD.encode(), f"{CARTORIO_REMOTE}/.env")
            steps.append(".env escrito")

        # 5. Instalar dependências Python
        log.info(f"[{label}] Instalar dependências Python (pode demorar ~2min)")
        # Verifica se venv/bin/uvicorn já existe
        rc_chk, _ = _ssh(client, f"test -f {CARTORIO_REMOTE}/venv/bin/uvicorn && echo OK || echo MISSING")
        if "MISSING" in _:
            log.info(f"[{label}]   venv/uvicorn não encontrado — iniciando instalação")

            # a) Detectar versão Python
            rc, pyver = _ssh(client, "python3 -c \"import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')\"")
            pyver = pyver.strip()
            log.info(f"[{label}]   Python detectado: {pyver}")

            # b) Instalar python3-venv e python3.X-venv (chamada SSH separada, sem pipe)
            rc_apt, out_apt = _ssh(client,
                f"DEBIAN_FRONTEND=noninteractive apt-get install -y python3-venv python{pyver}-venv",
                timeout=120)
            log.info(f"[{label}]   apt-get rc={rc_apt} | {out_apt[-150:]}")
            if rc_apt != 0:
                errors.append(f"{label}: apt-get python3-venv falhou rc={rc_apt}")
                log.error(f"[{label}] apt FALHOU: {out_apt[-200:]}")

            # c) Recriar venv limpo
            rc, out = _ssh(client,
                f"rm -rf {CARTORIO_REMOTE}/venv && python3 -m venv {CARTORIO_REMOTE}/venv")
            log.info(f"[{label}]   venv create rc={rc}")
            if rc != 0:
                errors.append(f"{label}: python3 -m venv falhou rc={rc} — {out[-150:]}")
                log.error(f"[{label}] venv create FALHOU: {out}")
            else:
                # d) Pip install (chamada separada com timeout longo)
                rc, out = _ssh(client,
                    f"{CARTORIO_REMOTE}/venv/bin/pip install --upgrade pip -q && "
                    f"{CARTORIO_REMOTE}/venv/bin/pip install {_PIP_PACKAGES}",
                    timeout=300)
                log.info(f"[{label}]   pip install rc={rc} | {out[-200:]}")
                if rc != 0:
                    errors.append(f"{label}: pip install falhou rc={rc} — {out[-200:]}")
                    log.error(f"[{label}] pip FALHOU: {out[-300:]}")
                else:
                    steps.append("pip OK (instalado)")
        else:
            log.info(f"[{label}]   venv já existe com uvicorn — pulando pip install")
            steps.append("pip OK (já instalado)")

        # 6. Nginx config
        log.info(f"[{label}] Configurar nginx")
        if _NGINX_CONF_LOCAL.exists():
            _sftp_put_file(sftp, _NGINX_CONF_LOCAL, _NGINX_CONF_REMOTE)
            rc, out = _ssh(client, "nginx -t 2>&1 && systemctl reload nginx 2>&1")
            if rc == 0:
                steps.append("nginx OK")
            else:
                errors.append(f"{label}: nginx reload falhou — {out[:100]}")
        else:
            errors.append(f"{label}: {_NGINX_CONF_LOCAL} não encontrado localmente")

        # 7. Expandir certificado SSL
        log.info(f"[{label}] Expandir certificado SSL")
        cert_cmd = (
            f"certbot certonly --nginx "
            f"-d plegmadag.com -d www.plegmadag.com -d api.plegmadag.com "
            f"-d {CARTORIO_DOMAIN} "
            f"--non-interactive --expand 2>&1 | tail -3"
        )
        rc, out = _ssh(client, cert_cmd, timeout=120)
        if rc == 0:
            steps.append("SSL OK")
        else:
            errors.append(f"{label}: certbot — {out[:150]}")

        # 8. Serviço systemd
        log.info(f"[{label}] Configurar serviço {CARTORIO_SERVICE}")
        _sftp_put_bytes(
            sftp,
            _SYSTEMD_UNIT.encode(),
            f"/etc/systemd/system/{CARTORIO_SERVICE}.service",
        )
        rc, out = _ssh(
            client,
            f"systemctl daemon-reload && "
            f"systemctl enable {CARTORIO_SERVICE} && "
            f"systemctl restart {CARTORIO_SERVICE} 2>&1"
        )
        if rc != 0:
            errors.append(f"{label}: systemctl restart falhou — {out[:150]}")
        else:
            steps.append("service OK")

        # 9. Health check (aguarda 8s para o serviço arrancar)
        log.info(f"[{label}] Health check")
        time.sleep(8)
        rc, out = _ssh(
            client,
            f"curl -s --max-time 10 http://localhost:{CARTORIO_PORT}/health 2>/dev/null"
        )
        if rc == 0 and '"status"' in out:
            steps.append(f"health OK — {out[:80]}")
            log.info(f"[{label}] ✓ HEALTH OK: {out[:80]}")
        else:
            # Capturar logs do serviço para diagnóstico
            _, journal = _ssh(client, f"journalctl -u {CARTORIO_SERVICE} -n 30 --no-pager 2>&1")
            _, svc_status = _ssh(client, f"systemctl status {CARTORIO_SERVICE} --no-pager 2>&1 | head -20")
            log.error(f"[{label}] HEALTH FALHOU (curl rc={rc}, resposta='{out[:100]}')")
            log.error(f"[{label}] Status serviço:\n{svc_status}")
            log.error(f"[{label}] Journal:\n{journal[-800:]}")
            errors.append(
                f"{label}: health falhou rc={rc} | "
                f"status={svc_status[:150]} | "
                f"journal={journal[-300:]}"
            )

        sftp.close()

    except Exception as e:
        errors.append(f"{label}: excepção — {e}")
        log.exception(f"[{label}] Deploy excepção")
    finally:
        client.close()

    success = len(errors) == 0
    return success, errors if not success else steps


# ── Agente ────────────────────────────────────────────────────────────────────

class CartorioDeployAgent(BaseAgent):
    name = "cartorio_deploy"

    def _execute(self, task: str, context: dict) -> AgentResult:
        # Permite filtrar por nó: context = {"node": "eur"}
        target = context.get("node", "").lower()
        nodes  = {k: v for k, v in NODES.items() if not target or k == target}

        if not nodes:
            return AgentResult(
                agent=self.name, status="FAILURE",
                summary=f"Nó '{target}' não reconhecido. Usar: {list(NODES.keys())}",
            )

        log.info(f"Deploy Plegma Timestamp → {[v['label'] for v in nodes.values()]}")
        event_log.log(self.name, "deploy_start", "INFO",
                      f"Nós: {list(nodes.keys())} | Domínio: {CARTORIO_DOMAIN}")

        ok_nodes  = []
        fail_nodes = []
        all_details = []

        for key, node in nodes.items():
            label = node["label"]
            log.info(f"\n{'═'*50}\n  {label} ({node['ip']})\n{'═'*50}")
            success, details = _deploy_node(node["ip"], label)

            all_details.extend([f"[{label}] {d}" for d in details])

            if success:
                ok_nodes.append(label)
                event_log.log(self.name, "deploy_node_ok", "OK", label)
            else:
                fail_nodes.append(label)
                event_log.log(self.name, "deploy_node_fail", "FAIL",
                               f"{label}: {'; '.join(details[:2])}")

        total   = len(nodes)
        status  = "SUCCESS" if len(ok_nodes) == total else ("PARTIAL" if ok_nodes else "FAILURE")
        summary = (
            f"Deploy Plegma Timestamp: {len(ok_nodes)}/{total} nós OK"
            + (f" | Falhas: {', '.join(fail_nodes)}" if fail_nodes else "")
        )

        if fail_nodes:
            all_details.append(
                f"ATENÇÃO: editar {CARTORIO_REMOTE}/.env nos servidores "
                f"para definir PLEGMA_CARTORIO_WALLET e PLEGMA_AERARIUM_WALLET"
            )

        log.info(f"\n{'═'*50}\n  {summary}\n{'═'*50}")
        return AgentResult(
            agent=self.name,
            status=status,
            summary=summary,
            details=all_details,
        )
