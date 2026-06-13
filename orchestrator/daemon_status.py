#!/usr/bin/env python3
"""
PLEGMA DAEMON — Status CLI
Mostra eventos recentes do audit log e estado dos agentes.

Uso:
  python daemon_status.py              ← últimos 20 eventos
  python daemon_status.py --agent analyst
  python daemon_status.py --tail 50
  python daemon_status.py --stats
"""

import sys
import argparse
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import event_log

STATUS_COLOR = {"OK": "\033[32m", "WARN": "\033[33m", "FAIL": "\033[31m", "RESET": "\033[0m"}


def _fmt_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def _color(text: str, status: str) -> str:
    if not sys.stdout.isatty():
        return text
    c = STATUS_COLOR.get(status, "")
    return f"{c}{text}{STATUS_COLOR['RESET']}"


def main():
    parser = argparse.ArgumentParser(description="PLEGMA Daemon — Status do Audit Log")
    parser.add_argument("--agent",  default=None, help="Filtrar por agente")
    parser.add_argument("--tail",   type=int, default=20, help="Número de eventos")
    parser.add_argument("--stats",  action="store_true", help="Estatísticas gerais")
    args = parser.parse_args()

    if args.stats:
        s = event_log.stats()
        print(f"\n⬡ PLEGMA Daemon — Audit Log Stats")
        print(f"  Total eventos: {s.get('total', 0)}")
        last = s.get("last_ts")
        if last:
            print(f"  Último evento: {_fmt_ts(last)}")
        print(f"\n  Por agente:")
        for ag, cnt in sorted(s.get("by_agent", {}).items(), key=lambda x: -x[1]):
            print(f"    {ag:<22} {cnt}")
        print()
        return

    events = event_log.recent(limit=args.tail, agent=args.agent)
    if not events:
        print("Nenhum evento no audit log.")
        return

    filter_str = f" [{args.agent}]" if args.agent else ""
    print(f"\n⬡ PLEGMA Daemon — Últimos {len(events)} eventos{filter_str}")
    print(f"  {'Timestamp':<20} {'Agente':<18} {'Acção':<22} {'Status':<6}  Resumo")
    print("  " + "─" * 90)

    for ev in reversed(events):
        ts     = _fmt_ts(ev["ts"])
        agent  = ev["agent"][:17]
        action = ev["action"][:21]
        status = ev["status"]
        summary = (ev["summary"] or "")[:45]
        colored_status = _color(f"{status:<6}", status)
        print(f"  {ts}  {agent:<18} {action:<22} {colored_status}  {summary}")

    print()


if __name__ == "__main__":
    main()
