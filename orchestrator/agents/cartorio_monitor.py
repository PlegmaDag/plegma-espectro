#!/usr/bin/env python3
"""
PLEGMA ORCHESTRATOR — Cartório Digital Monitor
Verifica saúde do serviço plegma-cartorio nos 4 nós de produção.
Executado a cada 5 minutos pelo daemon.
"""

import sys
import paramiko
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from daemon_config import NODES, SSH_KEY, CARTORIO_PORT, CARTORIO_SERVICE
from . import BaseAgent, AgentResult
import event_log

_TIMEOUT = 10

_ENDPOINTS = [
    ("GET", f"http://localhost:{CARTORIO_PORT}/health",              "health"),
    ("GET", f"http://localhost:{CARTORIO_PORT}/api/keys/config",     "api-keys config"),
    ("GET", f"http://localhost:{CARTORIO_PORT}/api/distribution/model", "dist model"),
]


def _connect(ip: str) -> "paramiko.SSHClient | None":
    try:
        key = paramiko.Ed25519Key.from_private_key_file(SSH_KEY)
        c   = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        c.connect(ip, username="root", pkey=key, timeout=12)
        t = c.get_transport()
        if t:
            t.set_keepalive(20)
        return c
    except Exception as e:
        event_log.log("cartorio_monitor", "ssh_connect_fail", "WARN", f"{ip}: {e}")
        return None


def _run_ssh(client: "paramiko.SSHClient", cmd: str) -> tuple[int, str]:
    _, stdout, stderr = client.exec_command(cmd, timeout=15)
    stdout.channel.settimeout(15)
    try:
        out  = stdout.read().decode().strip()
        err  = stderr.read().decode().strip()
        code = stdout.channel.recv_exit_status()
        return code, out or err
    except Exception:
        return -1, "timeout"


def _service_active(client: "paramiko.SSHClient") -> bool:
    rc, out = _run_ssh(client, f"systemctl is-active {CARTORIO_SERVICE} 2>/dev/null")
    return rc == 0 and out.strip() == "active"


def _endpoint_ok(client: "paramiko.SSHClient", url: str) -> tuple[bool, int]:
    rc, out = _run_ssh(client, f"curl -s -o /dev/null -w '%{{http_code}}' --max-time 5 '{url}' 2>/dev/null")
    try:
        code = int(out.strip())
        return code < 400, code
    except Exception:
        return False, 0


class CartorioMonitorAgent(BaseAgent):
    name = "cartorio_monitor"

    def _execute(self, task: str, context: dict) -> AgentResult:
        results  = []
        failures = []

        for label, node in NODES.items():
            ip    = node["ip"]
            node_results = {"node": node["label"], "ip": ip}

            client = _connect(ip)
            if not client:
                node_results["status"]  = "SSH_FAIL"
                failures.append(f"{node['label']}: SSH falhou")
                results.append(node_results)
                continue

            try:
                # 1. Verificar serviço systemd
                active = _service_active(client)
                node_results["service_active"] = active

                if not active:
                    # Auto-restart
                    rc, _ = _run_ssh(client, f"systemctl restart {CARTORIO_SERVICE}")
                    restarted = rc == 0
                    node_results["restarted"] = restarted
                    if restarted:
                        event_log.log("cartorio_monitor", "auto_restart", "WARN",
                                      f"{node['label']}: {CARTORIO_SERVICE} reiniciado")
                    else:
                        failures.append(f"{node['label']}: serviço inactivo, restart falhou")

                # 2. Verificar endpoints
                ep_results = {}
                for _, url, name in _ENDPOINTS:
                    ok, code = _endpoint_ok(client, url)
                    ep_results[name] = {"ok": ok, "code": code}
                    if not ok:
                        failures.append(f"{node['label']}/{name}: HTTP {code}")

                node_results["endpoints"] = ep_results
                node_results["status"]    = "OK" if active and all(
                    v["ok"] for v in ep_results.values()
                ) else "DEGRADED"

            finally:
                client.close()

            results.append(node_results)
            event_log.log("cartorio_monitor", "check", node_results["status"], node["label"])

        ok_nodes = sum(1 for r in results if r.get("status") == "OK")
        status   = "SUCCESS" if ok_nodes == len(NODES) else ("PARTIAL" if ok_nodes > 0 else "FAILURE")

        return AgentResult(
            agent=self.name,
            status=status,
            summary=f"Cartório Digital: {ok_nodes}/{len(NODES)} nós OK",
            details=failures,
            data={"nodes": results},
        )
