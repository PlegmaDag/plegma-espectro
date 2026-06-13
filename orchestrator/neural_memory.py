#!/usr/bin/env python3
"""
PLEGMA ORCHESTRATOR — Memória Neural
SQLite + BLAKE3 fingerprints de padrões de tarefas
100% local · sem rede · determinístico
"""

import sqlite3
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import List

try:
    import blake3 as _b3
    def _fp(data: str) -> str:
        return _b3.blake3(data.encode()).hexdigest()[:16]
except ImportError:
    def _fp(data: str) -> str:
        return hashlib.sha3_256(data.encode()).hexdigest()[:16]

DB_PATH = Path(__file__).parent / "neural_memory.db"


@dataclass
class Pattern:
    fingerprint:    str
    task_type:      str
    context_sample: str
    agent_used:     str
    outcome:        str
    duration_ms:    int
    count:          int
    last_seen:      str


class NeuralMemory:
    def __init__(self, db_path: Path = DB_PATH):
        self._db = sqlite3.connect(str(db_path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS patterns (
                fingerprint    TEXT PRIMARY KEY,
                task_type      TEXT NOT NULL,
                context_sample TEXT,
                agent_used     TEXT NOT NULL,
                outcome        TEXT NOT NULL,
                duration_ms    INTEGER DEFAULT 0,
                count          INTEGER DEFAULT 1,
                created_at     TEXT NOT NULL,
                last_seen      TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_type    ON patterns(task_type);
            CREATE INDEX IF NOT EXISTS idx_agent   ON patterns(agent_used);
            CREATE INDEX IF NOT EXISTS idx_outcome ON patterns(outcome);
        """)
        self._db.commit()

    def fingerprint(self, task_type: str, context: str = "") -> str:
        return _fp(f"{task_type}:{context[:64]}")

    def store(self, task_type: str, context: str, agent_used: str,
              outcome: str, duration_ms: int = 0):
        fp  = self.fingerprint(task_type, context)
        now = datetime.now(timezone.utc).isoformat()
        self._db.execute("""
            INSERT INTO patterns
                (fingerprint, task_type, context_sample, agent_used, outcome,
                 duration_ms, count, created_at, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
            ON CONFLICT(fingerprint) DO UPDATE SET
                count       = count + 1,
                last_seen   = excluded.last_seen,
                outcome     = excluded.outcome,
                duration_ms = excluded.duration_ms,
                agent_used  = excluded.agent_used
        """, (fp, task_type, context[:120], agent_used, outcome,
              duration_ms, now, now))
        self._db.commit()

    def recall(self, task_type: str, context: str = "",
               limit: int = 5) -> List[Pattern]:
        rows = self._db.execute(
            """SELECT fingerprint, task_type, context_sample, agent_used,
                      outcome, duration_ms, count, last_seen
               FROM patterns
               WHERE task_type = ?
               ORDER BY count DESC, last_seen DESC
               LIMIT ?""",
            (task_type, limit)
        ).fetchall()
        return [Pattern(**dict(r)) for r in rows]

    def recall_by_agent(self, agent: str, limit: int = 10) -> List[Pattern]:
        rows = self._db.execute(
            """SELECT fingerprint, task_type, context_sample, agent_used,
                      outcome, duration_ms, count, last_seen
               FROM patterns
               WHERE agent_used = ?
               ORDER BY last_seen DESC
               LIMIT ?""",
            (agent, limit)
        ).fetchall()
        return [Pattern(**dict(r)) for r in rows]

    def stats(self) -> dict:
        r = self._db.execute(
            """SELECT COUNT(*) as padroes,
                      COALESCE(SUM(count), 0)  as execucoes,
                      COALESCE(SUM(CASE WHEN outcome = 'SUCCESS' THEN count ELSE 0 END), 0) as sucessos
               FROM patterns"""
        ).fetchone()
        return dict(r) if r else {"padroes": 0, "execucoes": 0, "sucessos": 0}

    def close(self):
        self._db.close()
