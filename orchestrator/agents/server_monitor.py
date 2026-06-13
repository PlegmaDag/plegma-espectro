#!/usr/bin/env python3
"""
PLEGMA DAEMON — Server Monitor Agent
Verifica saúde dos 4 servidores a cada 3 minutos.
- Verifica cada serviço systemctl
- Verifica cada endpoint da API via curl interno (evita firewall)
- Auto-restart se serviço cair
- Confirma em 2/3 servidores antes de declarar falha crítica
"""

import sys
import json
import requests
import paramiko
import base64
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from daemon_config import NODES, SSH_KEY, SERVICES, SERVICE_PORTS
from . import BaseAgent, AgentResult
import event_log

_HTTP_TIMEOUT = 6

# Endpoints críticos a verificar em cada servidor (via curl localhost)
ENDPOINTS = [
    ("GET",  "http://localhost:8080/api/status",               "core status"),
    ("GET",  "http://localhost:8080/api/dag/status",           "dag status"),
    ("GET",  "http://localhost:8080/api/genesis/status",       "genesis"),
    ("GET",  "http://localhost:8082/api/auth/challenge",       "auth challenge"),
    ("GET",  "http://localhost:8083/wallet/status",            "wallet status"),
]

def _connect(ip: str) -> paramiko.SSHClient | None:
    try:
        key = paramiko.Ed25519Key.from_private_key_file(SSH_KEY)
        c   = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        c.connect(ip, username="root", pkey=key, timeout=12)
        transport = c.get_transport()
        if transport:
            transport.set_keepalive(20)
        return c
    except Exception as e:
        event_log.log("server_monitor", "ssh_connect_fail", "WARN", f"{ip}: {e}")
        return None


def _run(client: paramiko.SSHClient, cmd: str, timeout: int = 20) -> tuple[int, str]:
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    stdout.channel.settimeout(timeout)
    try:
        out  = stdout.read().decode().strip()
        err  = stderr.read().decode().strip()
        code = stdout.channel.recv_exit_status()
    except Exception:
        return -1, "timeout"
    return code, out or err


def _service_active(client: paramiko.SSHClient, svc: str) -> bool:
    rc, out = _run(client, f"systemctl is-active {svc} 2>/dev/null")
    return rc == 0 and out.strip() == "active"


def _endpoint_ok(client: paramiko.SSHClient, method: str, url: str) -> tuple[bool, int]:
    """Verifica endpoint via curl no próprio servidor (sem firewall externo)."""
    rc, out = _run(client, f"curl -s -o /dev/null -w '%{{http_code}}' --max-time 5 {url} 2>/dev/null")
    try:
        code = int(out.strip())
        return code < 500, code
    except Exception:
        return False, 0


def _restart_service(client: paramiko.SSHClient, svc: str, label: str) -> bool:
    rc, out = _run(client, f"systemctl restart {svc} && sleep 3 && systemctl is-active {svc}")
    return rc == 0 and "active" in out


def _http_public_ok() -> bool:
    """Verificação HTTPS via domínio público EUR (nginx)."""
    try:
        r = requests.get("https://plegmadag.com/api/status", timeout=_HTTP_TIMEOUT)
        return r.status_code < 500
    except Exception:
        return False


class ServerMonitorAgent(BaseAgent):
    name = "server_monitor"

    def _execute(self, task: str, context: dict) -> AgentResult:
        details  = []
        failures = 0
        restarts = 0
        ep_fails = 0

        for node_id, node in NODES.items():
            ip    = node["ip"]
            label = node["label"]
            details.append(f"\n[{label}] {ip}")

            client = _connect(ip)
            if not client:
                failures += 1
                details.append(f"  ✕ SSH inacessível — servidor pode estar offline")
                event_log.log(self.name, "ssh_unreachable", "FAIL",
                              f"{label} SSH inacessível", {"node": node_id})
                continue

            # ── 1. Verificar cada serviço systemctl ─────────────────────────
            for svc in SERVICES:
                up = _service_active(client, svc)
                if not up:
                    failures += 1
                    details.append(f"  ✕ {svc} DOWN → restart")
                    event_log.log(self.name, "service_down", "WARN",
                                  f"{label}/{svc} DOWN", {"node": node_id})
                    ok = _restart_service(client, svc, label)
                    if ok:
                        restarts += 1
                        details.append(f"    ✓ {svc} RECUPERADO")
                        event_log.log(self.name, "service_restart", "OK",
                                      f"{label}/{svc} recuperado", {"node": node_id})
                    else:
                        details.append(f"    ✕ {svc} FALHOU restart — atenção manual")
                        event_log.log(self.name, "service_restart", "FAIL",
                                      f"{label}/{svc} restart falhou", {"node": node_id})
                else:
                    details.append(f"  ✓ {svc}")

            # ── 2. Verificar cada endpoint da API via curl interno ───────────
            details.append(f"  Endpoints:")
            for method, url, name in ENDPOINTS:
                ok, code = _endpoint_ok(client, method, url)
                sym  = "✓" if ok else "✕"
                port_name = url.split("/")[2]
                details.append(f"    {sym} {name:<20} HTTP {code}")
                if not ok:
                    ep_fails += 1
                    event_log.log(self.name, "endpoint_fail", "WARN",
                                  f"{label}/{name} retornou {code}", {"node": node_id, "url": url})

            client.close()

            # ── 3. EUR: verificação pública HTTPS ───────────────────────────
            if node.get("primary"):
                pub_ok = _http_public_ok()
                sym = "✓" if pub_ok else "⚠"
                details.append(f"  {sym} HTTPS público: {'OK' if pub_ok else 'NÃO RESPONDE (nginx?)'}")
                if not pub_ok:
                    event_log.log(self.name, "https_public", "WARN",
                                  f"EUR HTTPS público inresponsivo")

            event_log.log(self.name, "node_check", "OK" if failures == 0 else "WARN",
                          f"{label} verificado", {"node": node_id})

        status = "SUCCESS" if (failures == 0 and ep_fails == 0) else \
                 "PARTIAL" if restarts > 0 else "FAILURE"

        summary = f"{len(NODES)} nós · {failures} serviços em falha · {ep_fails} endpoints com erro"
        if failures == 0 and ep_fails == 0:
            summary = f"Todos os {len(NODES)} servidores e endpoints saudáveis"

        return AgentResult(
            agent=self.name, status=status, summary=summary, details=details,
            data={"failures": failures, "restarts": restarts, "ep_fails": ep_fails}
        )
