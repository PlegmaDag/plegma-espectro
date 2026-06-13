#!/usr/bin/env python3
"""
PLEGMA ORCHESTRATOR — Deploy Agent
SSH para EUR/BR/MAL/SIN: copia ficheiros + reinicia serviços.
Backup automático antes de cada deploy; rollback se serviço cair.
"""

import time
import paramiko
from pathlib import Path
from . import BaseAgent, AgentResult

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from daemon_config import NODES, SSH_KEY, SERVICES
import event_log

_HEALTH_WAIT   = 35   # segundos a aguardar após restart antes de verificar saúde
_REMOTE_CORE   = "/root/PLEGMA_CORE"


def _connect(ip: str) -> paramiko.SSHClient | None:
    try:
        key = paramiko.Ed25519Key.from_private_key_file(SSH_KEY)
        c   = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        c.connect(ip, username="root", pkey=key, timeout=15)
        transport = c.get_transport()
        if transport:
            transport.set_keepalive(20)
        return c
    except Exception as e:
        event_log.log("deploy", "ssh_fail", "WARN", f"{ip}: {e}")
        return None


def _run(client: paramiko.SSHClient, cmd: str, timeout: int = 60) -> tuple[int, str]:
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out  = stdout.read().decode().strip()
    err  = stderr.read().decode().strip()
    code = stdout.channel.recv_exit_status()
    return code, out or err


def _service_active(client: paramiko.SSHClient, svc: str) -> bool:
    rc, out = _run(client, f"systemctl is-active {svc} 2>/dev/null")
    return rc == 0 and out.strip() == "active"


def _backup_file(client: paramiko.SSHClient, remote_path: str) -> str | None:
    """Cria backup do ficheiro remoto. Retorna caminho do backup."""
    backup = f"{remote_path}.bak"
    rc, _ = _run(client, f"cp -f {remote_path} {backup} 2>/dev/null")
    return backup if rc == 0 else None


def _restore_backup(client: paramiko.SSHClient, backup: str, original: str) -> bool:
    rc, _ = _run(client, f"cp -f {backup} {original} 2>/dev/null")
    return rc == 0


def _ensure_remote_dir(sftp, remote_path: str):
    """Garante que todas as pastas do caminho remoto existem via SFTP."""
    parts = remote_path.rsplit("/", 1)
    if len(parts) < 2:
        return
    remote_dir = parts[0]
    dirs = remote_dir.lstrip("/").split("/")
    current = ""
    for d in dirs:
        current += "/" + d
        try:
            sftp.stat(current)
        except IOError:
            try:
                sftp.mkdir(current)
            except IOError:
                pass  # já existe ou sem permissão — ignorar


def _upload_file(client: paramiko.SSHClient, local_path: str, remote_path: str) -> bool:
    try:
        sftp = client.open_sftp()
        sftp.put(local_path, remote_path)
        sftp.close()
        return True
    except Exception as e:
        event_log.log("deploy", "upload_fail", "WARN", f"upload falhou: {e}")
        return False


def _restart_service(client: paramiko.SSHClient, svc: str) -> bool:
    rc, _ = _run(client, f"systemctl restart {svc}", timeout=30)
    return rc == 0


def _deploy_to_node(node_id: str, ip: str, label: str,
                    ficheiro: str | None, restart_only: bool,
                    remote_path_override: str | None = None,
                    static_only: bool = False) -> dict:
    """Deploy para um nó: backup → upload → restart → health-check → rollback se necessário.
    remote_path_override: caminho remoto completo (substitui REMOTE_CORE/<filename>).
    static_only: não reinicia serviço (para ficheiros estáticos como APK/HTML).
    """
    result = {"node": node_id, "label": label, "ip": ip,
              "ok": False, "details": [], "rolled_back": False}

    client = _connect(ip)
    if not client:
        result["details"].append(f"  ✕ SSH inacessível")
        return result

    try:
        backup_path = None

        # ── 1. Upload do ficheiro (se fornecido) — sempre que ficheiro presente ──
        if ficheiro:
            filename    = Path(ficheiro).name
            remote_path = remote_path_override or f"{_REMOTE_CORE}/{filename}"

            # Garante que a diretoria remota existe (aguarda conclusão)
            remote_dir = remote_path.rsplit("/", 1)[0] if "/" in remote_path else remote_path
            _run(client, f"mkdir -p {remote_dir}")

            backup_path = _backup_file(client, remote_path)
            if backup_path:
                result["details"].append(f"  ✓ backup → {backup_path}")
            else:
                result["details"].append(f"  ⚠ sem backup (ficheiro pode ser novo)")

            ok = _upload_file(client, ficheiro, remote_path)
            if not ok:
                result["details"].append(f"  ✕ upload falhou")
                return result
            result["details"].append(f"  ✓ {filename} → {remote_path}")

        # ── 2. Restart (ignorado para ficheiros estáticos) ───────────────
        if static_only:
            result["ok"] = True
            result["details"].append(f"  ✓ ficheiro estático — sem restart necessário")
            event_log.log("deploy", "deploy_ok", "OK",
                          f"{label} deploy estático bem-sucedido", {"node": node_id})
        else:
            svc = "plegma-core"
            ok  = _restart_service(client, svc)
            if not ok:
                result["details"].append(f"  ✕ restart {svc} falhou")
                if backup_path:
                    _restore_and_restart(client, backup_path,
                                         remote_path_override or f"{_REMOTE_CORE}/{Path(ficheiro).name}" if ficheiro else "",
                                         svc, result)
                return result
            result["details"].append(f"  ↺ {svc} a reiniciar...")

            # ── 3. Health-check após {_HEALTH_WAIT}s ─────────────────────
            time.sleep(_HEALTH_WAIT)

            all_up = True
            for s in SERVICES:
                active = _service_active(client, s)
                sym = "✓" if active else "✕"
                result["details"].append(f"  {sym} {s}")
                if not active:
                    all_up = False

            if all_up:
                result["ok"] = True
                result["details"].append(f"  ✓ saúde confirmada após {_HEALTH_WAIT}s")
                event_log.log("deploy", "deploy_ok", "OK",
                              f"{label} deploy bem-sucedido", {"node": node_id})
            else:
                result["details"].append(f"  ✕ serviço(s) em falha — a reverter")
                event_log.log("deploy", "deploy_fail", "FAIL",
                              f"{label} serviço caiu após deploy", {"node": node_id})

                if backup_path and ficheiro:
                    _restore_and_restart(client, backup_path,
                                         remote_path_override or f"{_REMOTE_CORE}/{Path(ficheiro).name}",
                                         svc, result)
                    result["rolled_back"] = True

    finally:
        client.close()

    return result


def _restore_and_restart(client, backup_path: str, original_path: str,
                          svc: str, result: dict):
    if original_path and _restore_backup(client, backup_path, original_path):
        result["details"].append(f"  ↺ backup restaurado")
        ok = _restart_service(client, svc)
        time.sleep(15)
        active = _service_active(client, svc)
        if active:
            result["details"].append(f"  ✓ {svc} restaurado e activo")
            event_log.log("deploy", "rollback_ok", "OK",
                          f"rollback bem-sucedido em {result.get('label', '')}")
        else:
            result["details"].append(f"  ✕ rollback FALHOU — intervenção manual necessária")
            event_log.log("deploy", "rollback_fail", "FAIL",
                          f"rollback falhou em {result.get('label', '')}")
    else:
        result["details"].append(f"  ✕ rollback impossível — sem backup válido")


class DeployAgent(BaseAgent):
    name = "deploy"

    def _execute(self, task: str, context: dict) -> AgentResult:
        task_lower           = task.lower()
        details              = []
        ficheiro             = context.get("ficheiro")
        remote_path_override = context.get("remote_path")
        static_only          = context.get("static_only", False)
        restart_only         = any(w in task_lower for w in ("restart", "reiniciar", "reboot"))

        # Deploy estático (landing/APK) → só EUR serve ficheiros estáticos
        if static_only:
            targets = ["eur"]
        else:
            targets = [n for n in NODES if n in task_lower]
            if not targets:
                targets = list(NODES.keys())

        if not restart_only and not ficheiro:
            return AgentResult(
                agent=self.name, status="FAILURE",
                summary="Forneça --ficheiro para deploy ou use 'reiniciar' para restart.",
                details=[], data={}
            )

        sucessos    = 0
        rollbacks   = 0

        for nid in targets:
            node  = NODES[nid]
            ip    = node["ip"]
            label = node["label"]
            details.append(f"\n[{label}] {ip}")

            res = _deploy_to_node(nid, ip, label, ficheiro, restart_only,
                                  remote_path_override=remote_path_override,
                                  static_only=static_only)
            details.extend(res["details"])

            if res["ok"]:
                sucessos += 1
            if res.get("rolled_back"):
                rollbacks += 1

        total = len(targets)
        status = "SUCCESS" if sucessos == total else \
                 "PARTIAL" if sucessos > 0 else "FAILURE"

        summary = f"{sucessos}/{total} nós actualizados"
        if rollbacks:
            summary += f" · {rollbacks} revertidos automaticamente"

        return AgentResult(
            agent=self.name, status=status, summary=summary,
            details=details,
            data={"sucessos": sucessos, "total": total, "rollbacks": rollbacks, "nos": targets}
        )
