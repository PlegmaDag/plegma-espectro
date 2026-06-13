#!/usr/bin/env python3
"""
PLEGMA DAEMON — Network Sync Agent
Verifica replicação de dados críticos entre os 4 servidores.
Detecta divergência de estado (DAG height, genesis supply, seed backups).
"""

import sys
import time
import requests
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from daemon_config import NODES, SSH_KEY, SSH_USER
from . import BaseAgent, AgentResult
import event_log

_TIMEOUT = 8
_SSH_OPTS = ["-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=10", "-i", SSH_KEY]


def _get(ip: str, path: str, port: int = 8080) -> dict | None:
    try:
        r = requests.get(f"http://{ip}:{port}{path}", timeout=_TIMEOUT)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


def _ssh_query(ip: str, cmd: str) -> str:
    try:
        proc = subprocess.run(
            ["ssh"] + _SSH_OPTS + [f"{SSH_USER}@{ip}", cmd],
            capture_output=True, text=True, timeout=20
        )
        return (proc.stdout or "").strip()
    except Exception:
        return ""


def _count_seeds(ip: str) -> int:
    """Conta seed backups no DB do servidor."""
    out = _ssh_query(ip,
        "python3 -c \"import sqlite3; c=sqlite3.connect('/root/PLEGMA_CORE/plegma_data.db').cursor(); "
        "c.execute('SELECT COUNT(*) FROM seed_backups_v2'); print(c.fetchone()[0])\" 2>/dev/null"
    )
    try:
        return int(out.strip())
    except Exception:
        return -1


class NetworkSyncAgent(BaseAgent):
    name = "network_sync"

    def _execute(self, task: str, context: dict) -> AgentResult:
        details    = []
        divergences = 0

        node_data = {}
        for nid, node in NODES.items():
            ip    = node["ip"]
            label = node["label"]
            dag   = _get(ip, "/api/dag/status") or {}
            gen   = _get(ip, "/api/genesis/status") or {}
            seeds = _count_seeds(ip)

            node_data[nid] = {
                "label":   label,
                "ip":      ip,
                "height":  dag.get("height") or dag.get("vertices") or 0,
                "supply":  gen.get("supply_circulante", 0),
                "socios":  gen.get("total_socios", 0),
                "seeds":   seeds,
            }
            details.append(
                f"  {label}: DAG={node_data[nid]['height']} "
                f"supply={node_data[nid]['supply']:,.0f} "
                f"seeds={seeds}"
            )

        vals = list(node_data.values())

        # 1. Divergência DAG
        heights = [v["height"] for v in vals if v["height"] > 0]
        if heights and (max(heights) - min(heights)) > 15:
            divergences += 1
            msg = f"DAG desincronizado: max={max(heights)} min={min(heights)}"
            details.append(f"\n  ⚠ {msg}")
            event_log.log(self.name, "dag_divergence", "WARN", msg,
                          {"max": max(heights), "min": min(heights)})

        # 2. Divergência de supply (não deve variar entre nós)
        supplies = [v["supply"] for v in vals if v["supply"] > 0]
        if supplies and (max(supplies) - min(supplies)) > 1000:
            divergences += 1
            msg = f"Supply divergente: max={max(supplies):,.0f} min={min(supplies):,.0f}"
            details.append(f"  ⚠ {msg}")
            event_log.log(self.name, "supply_divergence", "WARN", msg)

        # 3. Divergência de seed backups
        seed_counts = {nid: d["seeds"] for nid, d in node_data.items() if d["seeds"] >= 0}
        if seed_counts:
            max_seeds = max(seed_counts.values())
            for nid, cnt in seed_counts.items():
                if cnt < max_seeds:
                    label = node_data[nid]["label"]
                    divergences += 1
                    msg = f"{label} tem {cnt} seed backups vs max={max_seeds}"
                    details.append(f"  ⚠ SEED SYNC: {msg}")
                    event_log.log(self.name, "seed_sync_lag", "WARN", msg,
                                  {"node": nid, "count": cnt, "expected": max_seeds})

        # 4. Sócios
        socios_list = [v["socios"] for v in vals if v["socios"] > 0]
        if socios_list and max(socios_list) != min(socios_list):
            divergences += 1
            msg = f"Contagem de sócios inconsistente: {socios_list}"
            details.append(f"  ⚠ {msg}")
            event_log.log(self.name, "socios_divergence", "WARN", msg)

        event_log.log(self.name, "sync_check", "OK" if divergences == 0 else "WARN",
                      f"Verificação de sync: {divergences} divergências",
                      {"divergences": divergences})

        status  = "SUCCESS" if divergences == 0 else "PARTIAL"
        summary = f"Sync: {len(NODES)} nós · {divergences} divergências detectadas"
        if divergences == 0:
            summary = f"Todos os {len(NODES)} nós sincronizados"

        return AgentResult(
            agent=self.name, status=status, summary=summary,
            details=details, data={"divergences": divergences}
        )
