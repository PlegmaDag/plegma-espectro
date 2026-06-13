#!/usr/bin/env python3
"""
PLEGMA DAEMON — Event Log
Audit trail SQLite de todas as acções autónomas do daemon.
"""

import sqlite3
import time
import json
from pathlib import Path

DB_PATH = Path(__file__).parent / "daemon_events.db"


def _conn():
    con = sqlite3.connect(str(DB_PATH), timeout=10)
    con.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            ts         REAL    NOT NULL,
            agent      TEXT    NOT NULL,
            action     TEXT    NOT NULL,
            status     TEXT    NOT NULL,
            summary    TEXT,
            data_json  TEXT
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_ts    ON events(ts)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_agent ON events(agent)")
    con.commit()
    return con


def log(agent: str, action: str, status: str, summary: str = "", data: dict = None):
    """Regista um evento no audit trail."""
    try:
        con = _conn()
        con.execute(
            "INSERT INTO events (ts, agent, action, status, summary, data_json) VALUES (?,?,?,?,?,?)",
            (time.time(), agent, action, status, summary, json.dumps(data or {}))
        )
        con.commit()
        con.close()
    except Exception:
        pass  # log nunca deve crashar o daemon


def recent(limit: int = 50, agent: str = None) -> list[dict]:
    """Retorna eventos recentes."""
    try:
        con = _conn()
        if agent:
            rows = con.execute(
                "SELECT ts,agent,action,status,summary FROM events WHERE agent=? ORDER BY ts DESC LIMIT ?",
                (agent, limit)
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT ts,agent,action,status,summary FROM events ORDER BY ts DESC LIMIT ?",
                (limit,)
            ).fetchall()
        con.close()
        return [{"ts": r[0], "agent": r[1], "action": r[2], "status": r[3], "summary": r[4]} for r in rows]
    except Exception:
        return []


def stats() -> dict:
    """Estatísticas gerais do audit log."""
    try:
        con = _conn()
        total  = con.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        by_agent = con.execute(
            "SELECT agent, COUNT(*) FROM events GROUP BY agent ORDER BY COUNT(*) DESC"
        ).fetchall()
        last_ts = con.execute("SELECT MAX(ts) FROM events").fetchone()[0]
        con.close()
        return {"total": total, "by_agent": dict(by_agent), "last_ts": last_ts}
    except Exception:
        return {}
