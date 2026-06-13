#!/usr/bin/env python3
"""
PLEGMA DAEMON — Briefing Agent
Gera relatório de texto sobre tudo o que aconteceu nas últimas horas.
Executa às 05:00 e às 17:00 UTC — salva em relatorios/briefing_*.txt
"""

import sys
import time
import json
import requests
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent))
from daemon_config import NODES, API_PRIMARY, ORCHESTRATOR
from . import BaseAgent, AgentResult
import event_log

_TIMEOUT     = 8
_RELATORIOS  = ORCHESTRATOR / "relatorios"
_RELATORIOS.mkdir(exist_ok=True)
_KEEP_MAX    = 60   # mantém últimos 60 briefings (~30 dias × 2/dia)


def _get(ip: str, path: str, port: int = 8080) -> dict:
    try:
        r = requests.get(f"http://{ip}:{port}{path}", timeout=_TIMEOUT)
        return r.json() if r.status_code == 200 else {}
    except Exception:
        return {}


def _eventos_recentes(horas: int = 12) -> list[dict]:
    since = time.time() - horas * 3600
    try:
        import sqlite3
        from event_log import DB_PATH
        con  = sqlite3.connect(str(DB_PATH), timeout=5)
        rows = con.execute(
            "SELECT ts, agent, action, status, summary FROM events "
            "WHERE ts > ? ORDER BY ts ASC",
            (since,)
        ).fetchall()
        con.close()
        return [{"ts": r[0], "agent": r[1], "action": r[2],
                 "status": r[3], "summary": r[4]} for r in rows]
    except Exception:
        return []


def _ultimas_linhas_log(n: int = 40) -> list[str]:
    from daemon_config import DAEMON_LOG
    try:
        lines = Path(DAEMON_LOG).read_text(encoding="utf-8", errors="replace").splitlines()
        return lines[-n:]
    except Exception:
        return []


def _snapshots_servidores() -> list[dict]:
    snaps = []
    for nid, node in NODES.items():
        ip = node["ip"]
        s  = {
            "label":   node["label"],
            "ip":      ip,
            "status":  _get(ip, "/api/status"),
            "dag":     _get(ip, "/api/dag/status"),
            "genesis": _get(ip, "/api/genesis/status"),
        }
        s["online"] = bool(s["status"])
        snaps.append(s)
    return snaps


def _formatar_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def gerar_briefing(periodo_horas: int = 12) -> str:
    agora      = time.time()
    dt_agora   = datetime.fromtimestamp(agora, tz=timezone.utc)
    hora_slot  = "05:00" if dt_agora.hour < 12 else "17:00"

    eventos    = _eventos_recentes(periodo_horas)
    snaps      = _snapshots_servidores()
    log_lines  = _ultimas_linhas_log(30)

    online     = [s for s in snaps if s["online"]]
    n_online   = len(online)
    n_total    = len(snaps)

    # Métricas agregadas
    total_txs   = 0
    max_dag_h   = 0
    total_peers = 0
    socios      = 0
    supply      = 0.0

    for s in snaps:
        dag = s.get("dag", {})
        total_txs   += dag.get("total_transacoes", 0) or dag.get("vertices", 0) or 0
        h            = dag.get("height") or dag.get("vertices") or 0
        max_dag_h    = max(max_dag_h, h)
        total_peers += s["status"].get("peers", 0) or 0

    gen_data = online[0]["genesis"] if online else {}
    socios   = gen_data.get("total_socios", 0) or 0
    supply   = gen_data.get("supply_circulante", 0) or 0.0

    # Contagem de eventos por agente
    agentes_count: dict[str, int] = {}
    erros = []
    for ev in eventos:
        agentes_count[ev["agent"]] = agentes_count.get(ev["agent"], 0) + 1
        if ev["status"] in ("FAIL", "ERROR", "WARN"):
            erros.append(ev)

    sep = "═" * 60

    linhas = [
        sep,
        f"  ⬡ PLEGMA DAG — BRIEFING {hora_slot}  {dt_agora.strftime('%d/%m/%Y')}",
        sep,
        "",
        "RESUMO EXECUTIVO",
        f"  Servidores activos : {n_online}/{n_total}",
        f"  DAG height máx.    : {max_dag_h}",
        f"  Total transacções  : {total_txs:,}",
        f"  Peers conectados   : {total_peers}",
        f"  Sócios Genesis     : {socios}",
        f"  Supply circulante  : {supply:,.0f} $PLG",
        "",
    ]

    # Estado dos servidores
    linhas.append("ESTADO DOS SERVIDORES")
    for s in snaps:
        ok    = "✓ ONLINE " if s["online"] else "✕ OFFLINE"
        dag   = s.get("dag", {})
        h     = dag.get("height") or dag.get("vertices") or 0
        peers = s["status"].get("peers", 0) if s["online"] else 0
        fase  = s["status"].get("fase", "?") if s["online"] else "?"
        linhas.append(f"  {ok}  [{s['label']:3}]  {s['ip']:<18}  DAG={h}  peers={peers}  fase={fase}")
    linhas.append("")

    # Actividade do daemon
    linhas.append(f"ACTIVIDADE DO DAEMON (últimas {periodo_horas}h — {len(eventos)} eventos)")
    if agentes_count:
        for ag, cnt in sorted(agentes_count.items(), key=lambda x: -x[1]):
            linhas.append(f"  {ag:<22} {cnt} evento(s)")
    else:
        linhas.append("  (sem eventos registados neste período)")
    linhas.append("")

    # Erros e alertas
    if erros:
        linhas.append(f"ALERTAS / ERROS ({len(erros)})")
        for ev in erros[-10:]:   # últimos 10
            ts_str = _formatar_ts(ev["ts"])
            summ   = (ev["summary"] or "")[:100]
            linhas.append(f"  [{ts_str}] [{ev['agent']}] {ev['status']}: {summ}")
        linhas.append("")
    else:
        linhas.append("ALERTAS / ERROS")
        linhas.append("  Nenhum erro nas últimas 12h ✓")
        linhas.append("")

    # Últimas linhas do log
    linhas.append("EXTRACTO DO LOG (últimas 30 linhas)")
    for linha in log_lines:
        linhas.append("  " + linha[:120])
    linhas.append("")

    linhas += [
        sep,
        f"  Gerado em: {_formatar_ts(agora)}",
        f"  Próximo briefing: {hora_slot.replace('05', '17') if hora_slot == '05:00' else '05:00'} UTC",
        sep,
        "",
    ]

    return "\n".join(linhas)


class BriefingAgent(BaseAgent):
    name = "briefing"

    def _execute(self, task: str, context: dict) -> AgentResult:
        periodo = context.get("horas", 12)
        texto   = gerar_briefing(periodo)

        # Nome do ficheiro: briefing_YYYYMMDD_HHMM.txt
        dt_now   = datetime.now(tz=timezone.utc)
        filename = f"briefing_{dt_now.strftime('%Y%m%d_%H%M')}.txt"
        filepath = _RELATORIOS / filename
        filepath.write_text(texto, encoding="utf-8")

        # Limpeza: mantém apenas os últimos _KEEP_MAX
        antigos = sorted(_RELATORIOS.glob("briefing_*.txt"))[:-_KEEP_MAX]
        for f in antigos:
            f.unlink(missing_ok=True)

        event_log.log(self.name, "briefing_gerado", "OK",
                      f"Relatório {filename} gerado ({len(texto)} chars)")

        linhas = texto.splitlines()
        resumo_lines = [l for l in linhas[1:8] if l.strip()]
        details = [f"Ficheiro: relatorios/{filename}"] + resumo_lines

        return AgentResult(
            agent=self.name, status="SUCCESS",
            summary=f"Briefing gerado → {filename}",
            details=details,
            data={"file": str(filepath), "chars": len(texto)}
        )
