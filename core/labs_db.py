"""
labs_db.py — Votações on-chain simplificadas para o módulo LABS PLEGMA (V4.0)
Hegemonia BLAKE3 imposta. hashlib banido.
"""
import sqlite3, time, os

# ── Blindagem de Oráculo Determinístico (Hard Fail) ─────────
try:
    import blake3 as _blake3
except ImportError:
    raise RuntimeError("[FALHA FATAL] Módulo blake3 ausente no Labs DB.")

DB_PATH = os.path.join(os.path.dirname(__file__), 'labs.db')

def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def inicializar():
    with _get_conn() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS propostas (
            id TEXT PRIMARY KEY,
            titulo TEXT NOT NULL,
            descricao TEXT NOT NULL,
            autor TEXT NOT NULL,
            timestamp INTEGER NOT NULL,
            votos_sim INTEGER DEFAULT 0,
            votos_nao INTEGER DEFAULT 0,
            status TEXT DEFAULT 'ativa'
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS votos_proposta (
            proposta_id TEXT NOT NULL,
            voter TEXT NOT NULL,
            voto INTEGER NOT NULL,
            timestamp INTEGER NOT NULL,
            PRIMARY KEY (proposta_id, voter)
        )''')
        conn.commit()

def criar_proposta(titulo: str, descricao: str, autor: str) -> dict:
    ts = int(time.time())
    # Determinismo BLAKE3 - Geração de ID Pós-Quântico
    prop_id = _blake3.blake3(f"{titulo}{autor}{ts}".encode()).hexdigest()[:12].upper()
    
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO propostas (id, titulo, descricao, autor, timestamp) VALUES (?,?,?,?,?)",
            (prop_id, titulo, descricao, autor, ts)
        )
        conn.commit()
    return {"id": prop_id, "titulo": titulo, "descricao": descricao, "autor": autor, "timestamp": ts, "status": "ativa"}

def listar_propostas() -> list:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT id, titulo, descricao, autor, timestamp, votos_sim, votos_nao, status"
            " FROM propostas ORDER BY timestamp DESC"
        ).fetchall()
    return [dict(r) for r in rows]

def votar_proposta(proposta_id: str, voter: str, voto: int) -> dict:
    """voto: 1=sim, 0=nao. 1 voto por carteira por proposta."""
    with _get_conn() as conn:
        existing = conn.execute(
            "SELECT 1 FROM votos_proposta WHERE proposta_id=? AND voter=?", (proposta_id, voter)
        ).fetchone()
        if existing:
            return {"erro": "Voce ja votou nesta proposta. 1 pessoa = 1 voto."}
        ts = int(time.time())
        conn.execute(
            "INSERT INTO votos_proposta (proposta_id, voter, voto, timestamp) VALUES (?,?,?,?)",
            (proposta_id, voter, voto, ts)
        )
        if voto == 1:
            conn.execute("UPDATE propostas SET votos_sim=votos_sim+1 WHERE id=?", (proposta_id,))
        else:
            conn.execute("UPDATE propostas SET votos_nao=votos_nao+1 WHERE id=?", (proposta_id,))
        conn.commit()
        prop = dict(conn.execute(
            "SELECT id, titulo, descricao, autor, timestamp, votos_sim, votos_nao, status"
            " FROM propostas WHERE id=?", (proposta_id,)
        ).fetchone())
    return {"status": "voto_registrado", "proposta": prop}

inicializar()