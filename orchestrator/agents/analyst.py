#!/usr/bin/env python3
"""
PLEGMA DAEMON — Analyst Agent
Coleta métricas de todos os servidores via SSH (curl interno),
gera relatório horário e detecta anomalias.
"""

import sys
import time
import json
import paramiko
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
from daemon_config import NODES, SSH_KEY, LOG_DIR
from . import BaseAgent, AgentResult
import event_log

_TIMEOUT    = 10
_REPORT_DIR = LOG_DIR / "reports"
_REPORT_DIR.mkdir(exist_ok=True)


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
        event_log.log("analyst", "ssh_fail", "WARN", f"{ip}: {e}")
        return None


def _curl(client: paramiko.SSHClient, url: str) -> dict:
    """Executa curl localhost no servidor e devolve JSON ou {}."""
    _, stdout, _ = client.exec_command(
        f"curl -s --max-time {_TIMEOUT} {url} 2>/dev/null",
        timeout=_TIMEOUT + 5
    )
    stdout.channel.settimeout(_TIMEOUT + 5)
    try:
        raw = stdout.read().decode().strip()
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


def _collect_node(node_id: str, node: dict) -> dict:
    ip    = node["ip"]
    label = node["label"]
    snap  = {"node": node_id, "label": label, "ip": ip, "ts": time.time()}

    client = _connect(ip)
    if not client:
        snap["status"]  = {}
        snap["dag"]     = {}
        snap["genesis"] = {}
        snap["miner"]   = {}
        snap["online"]  = False
        return snap

    try:
        snap["status"]  = _curl(client, "http://localhost:8080/api/status")
        snap["genesis"] = _curl(client, "http://localhost:8080/api/genesis/status")
        snap["online"]  = bool(snap["status"])
    finally:
        client.close()

    return snap


def _detect_anomalies(snapshots: list[dict]) -> list[str]:
    anomalies = []
    online    = [s for s in snapshots if s["online"]]

    if len(online) < len(snapshots):
        offline = [s["label"] for s in snapshots if not s["online"]]
        anomalies.append(f"Servidores offline: {', '.join(offline)}")

    heights = {}
    for s in online:
        h = s["status"].get("total_transacoes") or s["status"].get("tips_pendentes") or 0
        if h:
            heights[s["label"]] = h

    if heights:
        max_h = max(heights.values())
        min_h = min(heights.values())
        if max_h - min_h > 10:
            anomalies.append(f"Divergência DAG: max={max_h} min={min_h} ({max_h - min_h} blocos)")

    return anomalies


class AnalystAgent(BaseAgent):
    name = "analyst"

    def _execute(self, task: str, context: dict) -> AgentResult:
        details  = []
        ts_start = time.time()
        periodo  = context.get("periodo", "manual")
        label    = context.get("label", "snapshot manual")

        details.append(f"Período: {label}")

        snapshots = [_collect_node(nid, n) for nid, n in NODES.items()]
        online    = sum(1 for s in snapshots if s["online"])

        total_txs = 0
        total_nos = 0
        for s in snapshots:
            total_txs += s["status"].get("total_transacoes", 0)
            total_nos += s["status"].get("nos_ativos", 0)
            ok   = "✓" if s["online"] else "✕"
            txs  = s["status"].get("total_transacoes", 0)
            nos  = s["status"].get("nos_ativos", 0)
            tips = s["status"].get("tips_pendentes", 0)
            details.append(f"  {ok} {s['label']}: txs={txs} nós={nos} tips={tips}")

        anomalies = _detect_anomalies(snapshots)
        for a in anomalies:
            details.append(f"  ⚠ ANOMALIA: {a}")
            event_log.log(self.name, "anomaly", "WARN", a)

        # Eventos das últimas 12h do audit log
        eventos_12h = event_log.recent(limit=200)
        ts_12h_ago  = ts_start - 43200
        eventos_periodo = [
            e for e in eventos_12h
            if isinstance(e.get("ts"), (int, float)) and e["ts"] >= ts_12h_ago
        ]
        falhas = [e for e in eventos_periodo if e.get("status") in ("FAIL", "WARN")]
        details.append(f"\nEventos últimas 12h: {len(eventos_periodo)} · falhas/alertas: {len(falhas)}")
        for f in falhas[:10]:
            details.append(f"  ⚠ [{f.get('agent','')}] {f.get('action','')} — {f.get('summary','')[:80]}")

        gen    = snapshots[0]["genesis"]
        supply = gen.get("supply_total", 0)
        socios = gen.get("socios", gen.get("total_socios", 0))

        report = {
            "ts":             ts_start,
            "ts_human":       datetime.fromtimestamp(ts_start).isoformat(),
            "periodo":        periodo,
            "label":          label,
            "servers_online": online,
            "total_servers":  len(snapshots),
            "total_txs":      total_txs,
            "total_peers":    total_nos,
            "supply":         supply,
            "socios":         socios,
            "anomalies":      anomalies,
            "eventos_12h":    len(eventos_periodo),
            "falhas_12h":     len(falhas),
            "snapshots":      snapshots,
        }

        # Nome do ficheiro inclui período
        fname = f"report_{periodo}_{int(ts_start)}.json"
        report_file = _REPORT_DIR / fname
        report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2))

        # Manter últimos 4 relatórios por período (2 dias) + 10 manuais
        for p in ("noturno", "diurno"):
            old = sorted(_REPORT_DIR.glob(f"report_{p}_*.json"))[:-4]
            for f in old:
                f.unlink(missing_ok=True)
        old_manual = sorted(_REPORT_DIR.glob("report_manual_*.json"))[:-10]
        for f in old_manual:
            f.unlink(missing_ok=True)

        event_log.log(self.name, "metrics_report", "OK",
                      f"[{periodo}] {online}/{len(snapshots)} servidores · {total_txs} txs · {len(anomalies)} anomalias",
                      {"online": online, "total_txs": total_txs, "anomalies": len(anomalies), "periodo": periodo})

        summary = f"[{label}] {online}/{len(snapshots)} servidores · {total_txs} txs · supply {supply:,.0f} $PLG"
        if anomalies:
            summary += f" · ⚠ {len(anomalies)} anomalias"

        details.append(f"\nRelatório: {report_file.name}")
        return AgentResult(
            agent=self.name, status="SUCCESS", summary=summary,
            details=details,
            data={"online": online, "total_txs": total_txs, "anomalies": len(anomalies), "periodo": periodo}
        )
