"""
social_db.py — Armazenamento de posts da rede social PLEGMA V4.0
Posts são armazenados em SQLite e selados com BLAKE3.
"""
import sqlite3, json, time, os

# ── Blindagem de Oráculo Determinístico (Hard Fail) ─────────
try:
    import blake3 as _blake3
except ImportError:
    raise RuntimeError("[FALHA FATAL] Módulo blake3 ausente no Social DB.")

DB_PATH = os.environ.get('SOCIAL_DB_PATH_OVERRIDE') or os.path.join(os.path.dirname(__file__), 'social.db')

def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def inicializar():
    """Cria tabelas se não existirem."""
    with _get_conn() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS posts (
            id TEXT PRIMARY KEY,
            author TEXT NOT NULL,
            conteudo TEXT NOT NULL,
            timestamp INTEGER NOT NULL,
            respeit INTEGER DEFAULT 0,
            ruido INTEGER DEFAULT 0,
            parent_id TEXT DEFAULT NULL,
            pinned INTEGER DEFAULT 0
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS votos (
            post_id TEXT NOT NULL,
            voter TEXT NOT NULL,
            tipo INTEGER NOT NULL,
            PRIMARY KEY (post_id, voter)
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS profiles (
            profile_id  TEXT PRIMARY KEY,
            plg_address TEXT NOT NULL UNIQUE,
            avatar      TEXT NOT NULL,
            cover       TEXT NOT NULL,
            bio         TEXT NOT NULL DEFAULT '',
            created_at  INTEGER NOT NULL
        )''')
        conn.commit()

def criar_post(author: str, conteudo: str, parent_id: str = None) -> dict:
    """Cria um novo post selado com BLAKE3."""
    if not author or not conteudo:
        return {"erro": "author e conteudo sao obrigatorios"}
    if len(conteudo) > 500:
        return {"erro": "Post muito longo (max 500 chars)"}
    
    ts = int(time.time())
    # Geração de ID Determinística V4.0
    post_id = _blake3.blake3(f"{author}{conteudo}{ts}".encode()).hexdigest()[:16].upper()
    
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO posts (id, author, conteudo, timestamp, parent_id) VALUES (?,?,?,?,?)",
            (post_id, author, conteudo, ts, parent_id)
        )
        conn.commit()
    return {"id": post_id, "author": author, "conteudo": conteudo, "timestamp": ts, "respeit": 0, "ruido": 0}

def listar_posts(limit: int = 20, offset: int = 0, author: str = None) -> list:
    with _get_conn() as conn:
        if author:
            rows = conn.execute(
                "SELECT id, author, conteudo, timestamp, respeit, ruido, parent_id, pinned FROM posts WHERE author=? ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                (author, limit, offset)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, author, conteudo, timestamp, respeit, ruido, parent_id, pinned FROM posts ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                (limit, offset)
            ).fetchall()
    return [dict(r) for r in rows]

def votar(post_id: str, voter: str, tipo: int) -> dict:
    """tipo: 1=respeit, -1=ruido. Idempotente."""
    with _get_conn() as conn:
        existing = conn.execute(
            "SELECT tipo FROM votos WHERE post_id=? AND voter=?", (post_id, voter)
        ).fetchone()
        if existing:
            if existing['tipo'] == tipo:
                conn.execute("DELETE FROM votos WHERE post_id=? AND voter=?", (post_id, voter))
            else:
                conn.execute("UPDATE votos SET tipo=? WHERE post_id=? AND voter=?", (tipo, post_id, voter))
        else:
            conn.execute("INSERT INTO votos (post_id, voter, tipo) VALUES (?,?,?)", (post_id, voter, tipo))
        
        votos = conn.execute("SELECT tipo, COUNT(*) as c FROM votos WHERE post_id=? GROUP BY tipo", (post_id,)).fetchall()
        respeit = next((v['c'] for v in votos if v['tipo'] == 1), 0)
        ruido = next((v['c'] for v in votos if v['tipo'] == -1), 0)
        conn.execute("UPDATE posts SET respeit=?, ruido=? WHERE id=?", (respeit, ruido, post_id))
        conn.commit()
    return {"post_id": post_id, "respeit": respeit, "ruido": ruido}


def apagar_post(post_id: str, author: str) -> dict:
    """Apaga post. Só o autor pode apagar. Apaga também os votos associados."""
    if not post_id or not author:
        return {"erro": "post_id e author obrigatorios"}
    with _get_conn() as conn:
        row = conn.execute("SELECT author FROM posts WHERE id=?", (post_id,)).fetchone()
        if not row:
            return {"erro": "post_nao_encontrado"}
        if row["author"] != author:
            return {"erro": "sem_permissao"}
        conn.execute("DELETE FROM votos WHERE post_id=?", (post_id,))
        conn.execute("DELETE FROM posts WHERE id=? AND author=?", (post_id, author))
        conn.commit()
    return {"ok": True, "post_id": post_id}


def criar_perfil(plg_address: str, avatar: str, cover: str, bio: str) -> dict:
    """Cria perfil de utilizador. Retorna dict com profile_id ou {'erro': ...}."""
    if not plg_address or not plg_address.strip():
        return {"erro": "plg_address obrigatorio"}
    if not avatar or not cover:
        return {"erro": "avatar e cover obrigatorios"}
    if len(bio) > 100:
        return {"erro": "bio_muito_longa"}
    ts = int(time.time())
    profile_id = _blake3.blake3(f"{plg_address}{ts}".encode()).hexdigest()[:16].upper()
    try:
        with _get_conn() as conn:
            conn.execute(
                "INSERT INTO profiles (profile_id, plg_address, avatar, cover, bio, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (profile_id, plg_address.strip(), avatar.strip(), cover.strip(), bio.strip(), ts)
            )
            conn.commit()
    except sqlite3.IntegrityError:
        return {"erro": "perfil_ja_existe"}
    return {
        "profile_id": profile_id,
        "plg_address": plg_address.strip(),
        "avatar": avatar.strip(),
        "cover": cover.strip(),
        "bio": bio.strip(),
        "created_at": ts
    }


def obter_perfil(plg_address: str) -> dict | None:
    """Retorna perfil ou None se não existir."""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT profile_id, plg_address, avatar, cover, bio, created_at "
            "FROM profiles WHERE plg_address=?",
            (plg_address,)
        ).fetchone()
    return dict(row) if row else None


inicializar()