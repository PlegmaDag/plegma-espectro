import sqlite3
import json
import os
import time as _time
from datetime import datetime

# =============================================================================
# PLEGMA DAG DB — V4.3 (ESTADO DETERMINÍSTICO / PÓS-QUÂNTICO)
# Diretriz: ALV_ZKDAG_BNG_GENESIS_2026_FAIRLAUNCH
# Segurança: BLAKE3 Hegemônico | Zk-Press Ready
# =============================================================================

try:
    import blake3 as _b3
except ImportError:
    raise RuntimeError("[FALHA FATAL] Módulo blake3 ausente no DB PLEGMA.")

DB_PATH = os.path.join(os.path.dirname(__file__), "plegma_data.db")

def get_connection():
    """Helper de conexão único para o núcleo PLEGMA."""
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=15000")
    return conn

def inicializar_banco():
    """Consolida a infraestrutura de tabelas para o Trilema PLEGMA."""
    with get_connection() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS transactions (
                tx_hash TEXT PRIMARY KEY, sender TEXT, receiver TEXT, amount REAL, 
                parents TEXT, timestamp INTEGER, signature TEXT, zk_proof_size INTEGER, node_type TEXT
            );
            CREATE TABLE IF NOT EXISTS tips (tx_hash TEXT PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS network_state (key TEXT PRIMARY KEY, value TEXT);

            CREATE TABLE IF NOT EXISTS plgg_balances (
                plg_address TEXT PRIMARY KEY, 
                balance REAL DEFAULT 0.0, 
                genesis_balance REAL DEFAULT 0.0, 
                updated_at INTEGER
            );
            
            CREATE TABLE IF NOT EXISTS plgg_vesting (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                plg_address     TEXT NOT NULL,
                amount          REAL NOT NULL,
                usdt_pago       REAL NOT NULL,
                tx_hash_externo TEXT NOT NULL UNIQUE,
                purchase_date   REAL NOT NULL,
                release_date    REAL NOT NULL,
                status          TEXT NOT NULL DEFAULT 'LOCKED'
            );

            CREATE TABLE IF NOT EXISTS pending_purchases (
                ref_id TEXT PRIMARY KEY, plg_address TEXT, usdt_amount REAL, 
                plgg_amount REAL, created_at REAL, status TEXT DEFAULT 'AGUARDANDO'
            );
            CREATE TABLE IF NOT EXISTS tx_externas_processadas (
                tx_hash TEXT PRIMARY KEY, data_processamento REAL
            );
            CREATE TABLE IF NOT EXISTS swap_orders (
                ref_id TEXT PRIMARY KEY, tipo TEXT, plg_address TEXT,
                polygon_address TEXT, plg_amount REAL, usdc_amount REAL,
                taxa REAL, created_at REAL, status TEXT, tx_hash_polygon TEXT
            );

            CREATE TABLE IF NOT EXISTS bans (
                uidg       TEXT PRIMARY KEY,
                confiscado REAL DEFAULT 0.0,
                motivo     TEXT,
                banned_at  REAL
            );

            CREATE TABLE IF NOT EXISTS sessions (
                plg_address TEXT,
                token       TEXT PRIMARY KEY,
                created_at  INTEGER,
                expires_at  INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_sessions_lookup
                ON sessions (plg_address, token, expires_at);

            CREATE TABLE IF NOT EXISTS nonces (
                nonce       TEXT PRIMARY KEY,
                status      TEXT DEFAULT 'PENDING',
                plg_address TEXT,
                created_at  INTEGER,
                expires_at  INTEGER
            );

            CREATE TABLE IF NOT EXISTS fundacao_registros (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                hash_inscricao TEXT UNIQUE NOT NULL,
                carteira_plg   TEXT NOT NULL,
                created_at     REAL NOT NULL,
                status         TEXT NOT NULL DEFAULT 'PENDENTE',
                aprovado_em    REAL
            );
            -- hash_inscricao e carteira_plg são IMUTÁVEIS após inserção.
            -- Apenas 'status' e 'aprovado_em' podem ser actualizados (via aprovar_inscricao_fundacao).
            -- Gatilho que proíbe UPDATE em hash_inscricao ou carteira_plg:
            CREATE TRIGGER IF NOT EXISTS trg_fundacao_imutavel
                BEFORE UPDATE OF hash_inscricao, carteira_plg ON fundacao_registros
            BEGIN
                SELECT RAISE(ABORT, 'IMUTAVEL: hash_inscricao e carteira_plg nao podem ser alterados apos registo');
            END;

            CREATE TABLE IF NOT EXISTS miner_vesting (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                plg_address  TEXT NOT NULL,
                amount       REAL NOT NULL,
                release_date TEXT NOT NULL,
                status       TEXT NOT NULL DEFAULT 'LOCKED',
                node_type    TEXT NOT NULL DEFAULT 'VALIDATOR',
                pool         TEXT NOT NULL DEFAULT 'VALIDATOR_POOL',
                node_id      TEXT,
                created_at   REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS nos_rede (
                plg_address TEXT NOT NULL,
                node_id     TEXT NOT NULL,
                node_type   TEXT NOT NULL DEFAULT 'VALIDATOR',
                last_seen   REAL NOT NULL,
                PRIMARY KEY (plg_address, node_id)
            );

            CREATE TABLE IF NOT EXISTS plg_transfers (
                tx_hash   TEXT PRIMARY KEY,
                sender    TEXT NOT NULL,
                receiver  TEXT NOT NULL,
                amount    REAL NOT NULL,
                timestamp REAL NOT NULL,
                status    TEXT NOT NULL DEFAULT 'confirmed'
            );
            CREATE INDEX IF NOT EXISTS idx_plg_transfers_sender   ON plg_transfers (sender);
            CREATE INDEX IF NOT EXISTS idx_plg_transfers_receiver ON plg_transfers (receiver);

            CREATE TABLE IF NOT EXISTS mine_validated_txs (
                ref_tx_hash  TEXT PRIMARY KEY,
                mine_tx_hash TEXT NOT NULL,
                miner_addr   TEXT NOT NULL,
                validated_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS plgg_ofertas (
                oferta_id      TEXT PRIMARY KEY,
                vendedor       TEXT NOT NULL,
                comprador      TEXT NOT NULL,
                amount_plgg    REAL NOT NULL,
                preco_unitario REAL NOT NULL,
                status         TEXT NOT NULL DEFAULT 'PENDENTE',
                created_at     REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_plgg_ofertas_comprador ON plgg_ofertas (comprador, status);
            CREATE INDEX IF NOT EXISTS idx_plgg_ofertas_vendedor  ON plgg_ofertas (vendedor,  status);

        """)
        # Colunas adicionadas em migrações seguras (ignoradas se já existirem)
        for _col in [
            "ALTER TABLE miner_vesting ADD COLUMN categoria TEXT DEFAULT ''",
            "ALTER TABLE miner_vesting ADD COLUMN score INTEGER DEFAULT 0",
            "ALTER TABLE fundacao_registros ADD COLUMN nome_projeto   TEXT DEFAULT ''",
            "ALTER TABLE fundacao_registros ADD COLUMN segmento       TEXT DEFAULT ''",
            "ALTER TABLE fundacao_registros ADD COLUMN localizacao    TEXT DEFAULT ''",
            "ALTER TABLE fundacao_registros ADD COLUMN descricao      TEXT DEFAULT ''",
            "ALTER TABLE fundacao_registros ADD COLUMN responsavel    TEXT DEFAULT ''",
            "ALTER TABLE fundacao_registros ADD COLUMN tempo_atuacao  TEXT DEFAULT ''",
            "ALTER TABLE fundacao_registros ADD COLUMN instagram      TEXT DEFAULT ''",
            "ALTER TABLE fundacao_registros ADD COLUMN facebook       TEXT DEFAULT ''",
            "ALTER TABLE fundacao_registros ADD COLUMN youtube        TEXT DEFAULT ''",
            "ALTER TABLE fundacao_registros ADD COLUMN tiktok         TEXT DEFAULT ''",
            "ALTER TABLE fundacao_registros ADD COLUMN site           TEXT DEFAULT ''",
            "ALTER TABLE fundacao_registros ADD COLUMN link_video     TEXT DEFAULT ''",
            "ALTER TABLE fundacao_registros ADD COLUMN plg_address_submitter TEXT DEFAULT ''",
            # V4.5 — Web3 anchor (Genesis)
            "ALTER TABLE pending_purchases ADD COLUMN evm_address TEXT DEFAULT ''",
            "ALTER TABLE pending_purchases ADD COLUMN tx_hash     TEXT DEFAULT ''",
            "ALTER TABLE pending_purchases ADD COLUMN anchor_id   TEXT DEFAULT ''",
            # V4.6 — Auditoria de fluxo DAG: Aerarium por tx + hash ZK real
            "ALTER TABLE transactions ADD COLUMN aerarium_amount REAL DEFAULT 0",
            "ALTER TABLE transactions ADD COLUMN zk_proof_hash   TEXT DEFAULT ''",
        ]:
            try:
                conn.execute(_col)
            except Exception:
                pass

# --- TRANSAÇÕES DAG ---

def salvar_transacao(tx: dict):
    """Persiste um vértice DAG na tabela transactions."""
    with get_connection() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO transactions
               (tx_hash, sender, receiver, amount, parents, timestamp, signature,
                zk_proof_size, node_type, aerarium_amount, zk_proof_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                tx["tx_hash"],
                tx.get("sender", ""),
                tx.get("receiver", ""),
                tx.get("amount", 0.0),
                json.dumps(tx.get("parents", [])),
                tx.get("timestamp", 0),
                tx.get("signature", ""),
                tx.get("zk_proof_size", 0),
                tx.get("node_type", ""),
                tx.get("aerarium_amount", 0.0),
                tx.get("zk_proof_hash", ""),
            )
        )

def carregar_transacoes() -> dict:
    """Carrega todas as transações do banco como dict {tx_hash: dict}."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT tx_hash, sender, receiver, amount, parents, timestamp, signature, zk_proof_size, node_type FROM transactions"
        ).fetchall()
    result = {}
    for row in rows:
        tx = dict(row)
        tx["parents"] = json.loads(tx["parents"]) if tx["parents"] else []
        result[tx["tx_hash"]] = tx
    return result

# --- TIPS DAG ---

def salvar_tips(tips: list):
    """Substitui a fronteira do DAG (tips) no banco."""
    with get_connection() as conn:
        conn.execute("DELETE FROM tips")
        for tx_hash in tips:
            conn.execute("INSERT OR IGNORE INTO tips (tx_hash) VALUES (?)", (tx_hash,))

def carregar_tips() -> list:
    """Retorna a lista de tx_hash que formam a fronteira atual do DAG."""
    with get_connection() as conn:
        rows = conn.execute("SELECT tx_hash FROM tips").fetchall()
    return [row["tx_hash"] for row in rows]

# --- GESTÃO DE ESTADO ---

def salvar_estado(key: str, value):
    with get_connection() as conn:
        conn.execute("INSERT OR REPLACE INTO network_state (key, value) VALUES (?, ?)", 
                     (key, json.dumps(value)))

def carregar_estado(key: str, default=None):
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM network_state WHERE key = ?", (key,)).fetchone()
    return json.loads(row["value"]) if row else default

# --- PROTOCOLO GENESIS PLG-G ($R=G/N) ---

def salvar_saldo_plgg(address: str, balance: float):
    """Atualiza o saldo líquido disponível (Unlock)."""
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO plgg_balances (plg_address, balance, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(plg_address) DO UPDATE SET 
                balance = excluded.balance, 
                updated_at = excluded.updated_at
        """, (address, balance, int(_time.time())))

def salvar_saldo_plgg_genesis(address: str, amount: float):
    """Registra saldo na reserva Gênese alvo de Vesting."""
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO plgg_balances (plg_address, genesis_balance, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(plg_address) DO UPDATE SET 
                genesis_balance = excluded.genesis_balance, 
                updated_at = excluded.updated_at
        """, (address, amount, int(_time.time())))

def carregar_saldo_plgg(address: str) -> float:
    with get_connection() as conn:
        row = conn.execute("SELECT balance FROM plgg_balances WHERE plg_address=?", (address,)).fetchone()
    return row['balance'] if row else 0.0

def carregar_saldo_plgg_genesis(address: str) -> float:
    with get_connection() as conn:
        row = conn.execute("SELECT genesis_balance FROM plgg_balances WHERE plg_address=?", (address,)).fetchone()
    return row['genesis_balance'] if row else 0.0

def salvar_pending_purchase(data: dict):
    with get_connection() as conn:
        conn.execute("""INSERT OR REPLACE INTO pending_purchases
                        (ref_id, plg_address, usdt_amount, plgg_amount, created_at, status,
                         evm_address, tx_hash, anchor_id)
                        VALUES (?,?,?,?,?,?,?,?,?)""",
                     (data['ref_id'], data['plg_address'], data['usdt_amount'],
                      data['plgg_amount'], data['created_at'], data['status'],
                      str(data.get('evm_address', '')).lower(),
                      str(data.get('tx_hash', '')).lower(),
                      data.get('anchor_id', '')))

def buscar_pending_purchase(ref_id: str):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT ref_id, plg_address, usdt_amount, plgg_amount, status, created_at, "
            "evm_address, tx_hash, anchor_id "
            "FROM pending_purchases WHERE ref_id=?",
            (ref_id,)).fetchone()
    return dict(row) if row else None

def atualizar_status_pending(ref_id: str, novo_status: str):
    """Atualiza o status da intenção de compra no banco."""
    with get_connection() as conn:
        conn.execute("UPDATE pending_purchases SET status = ? WHERE ref_id = ?", (novo_status, ref_id))

# --- WEB3 ANCHOR (Genesis · V4.5) ---

def ancorar_pending_purchase(ref_id: str, tx_hash: str, evm_address: str, anchor_id: str) -> bool:
    """Vincula determinísticamente uma intenção (ref_id) a um tx_hash Polygon e EVM sender.
    Retorna True se ancorou (linha estava AGUARDANDO sem tx_hash).
    Não altera status — o monitor confirma quando a tx é vista on-chain."""
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE pending_purchases "
            "SET tx_hash = ?, evm_address = ?, anchor_id = ? "
            "WHERE ref_id = ? AND status = 'AGUARDANDO' AND (tx_hash IS NULL OR tx_hash = '')",
            (tx_hash.lower(), evm_address.lower(), anchor_id, ref_id)
        )
        return cur.rowcount == 1

def buscar_pending_por_tx_hash(tx_hash: str) -> dict | None:
    """Busca intenção ancorada pelo tx_hash Polygon. Match determinístico exato."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT ref_id, plg_address, usdt_amount, plgg_amount, status, created_at, "
            "evm_address, tx_hash, anchor_id "
            "FROM pending_purchases WHERE tx_hash = ?",
            (tx_hash.lower(),)
        ).fetchone()
    return dict(row) if row else None

def buscar_pending_por_evm(evm_address: str, valor: float, tolerancia: float = 0.02) -> dict | None:
    """Fallback determinístico: match por endereço EVM remetente + valor (com tolerância USDC)."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT ref_id, plg_address, usdt_amount, plgg_amount, status, created_at, "
            "evm_address, tx_hash, anchor_id "
            "FROM pending_purchases "
            "WHERE evm_address = ? AND status = 'AGUARDANDO' AND (tx_hash IS NULL OR tx_hash = '') "
            "ORDER BY created_at ASC",
            (evm_address.lower(),)
        ).fetchall()
    for r in rows:
        if abs(float(r["usdt_amount"]) - valor) <= tolerancia:
            return dict(r)
    return None

# --- GESTÃO DE VESTING (LOCK-UP 30 DIAS) ---

def salvar_plgg_vesting(entry: dict):
    """Registra contrato de vesting conforme regra de 30 dias [cite: 2026-03-02]."""
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO plgg_vesting 
                (plg_address, amount, usdt_pago, tx_hash_externo, purchase_date, release_date, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            entry['plg_address'], 
            entry['amount'], 
            entry['usdt_pago'], 
            entry['tx_hash_externo'], 
            entry['purchase_date'], 
            entry['release_date'], 
            entry.get('status', 'LOCKED')
        ))

def carregar_vesting_por_usuario(plg_address: str) -> list:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, plg_address, amount, usdt_pago, tx_hash_externo, purchase_date, release_date, status FROM plgg_vesting WHERE plg_address = ? ORDER BY release_date ASC",
            (plg_address,)
        ).fetchall()
    return [dict(r) for r in rows]

def carregar_vesting() -> dict:
    """Retorna todos os contratos de vesting agrupados por plg_address: {address: [entries]}."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, plg_address, amount, usdt_pago, tx_hash_externo, purchase_date, release_date, status FROM plgg_vesting ORDER BY release_date ASC"
        ).fetchall()
    resultado: dict = {}
    for r in rows:
        entry = dict(r)
        addr = entry.get("plg_address", "")
        if addr not in resultado:
            resultado[addr] = []
        resultado[addr].append(entry)
    return resultado

def atualizar_status_plgg_vesting(tx_hash_externo: str, novo_status: str):
    """Actualiza o status de um contrato de vesting PLG-G pelo tx_hash_externo."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE plgg_vesting SET status = ? WHERE tx_hash_externo = ?",
            (novo_status, tx_hash_externo)
        )

def marcar_socio_genesis(plg_address: str):
    salvar_estado(f"socio_genesis_{plg_address}", True)

# --- BRIDGE E INTEROPERABILIDADE ---

def tx_externo_ja_processado(tx_hash: str) -> bool:
    with get_connection() as conn:
        row = conn.execute("SELECT 1 FROM tx_externas_processadas WHERE tx_hash=?", (tx_hash,)).fetchone()
    return row is not None

def registrar_tx_externa(tx_hash: str):
    with get_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO tx_externas_processadas (tx_hash, data_processamento) VALUES (?, ?)", 
                     (tx_hash, _time.time()))

def atualizar_swap_order_status(ref, st, tx=""):
    with get_connection() as conn:
        conn.execute("UPDATE swap_orders SET status=?, tx_hash_polygon=? WHERE ref_id=?", (st, tx, ref))

# --- SWAP ORDERS ---

def salvar_swap_order(order: dict):
    """Regista uma nova ordem de swap PLG/USDC."""
    with get_connection() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO swap_orders
               (ref_id, tipo, plg_address, polygon_address, plg_amount, usdc_amount, taxa, created_at, status, tx_hash_polygon)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                order.get("ref_id", ""),
                order.get("tipo", ""),
                order.get("plg_address", ""),
                order.get("polygon_address", ""),
                order.get("plg_amount", 0.0),
                order.get("usdc_amount", 0.0),
                order.get("taxa", 0.0),
                order.get("created_at", _time.time()),
                order.get("status", "AGUARDANDO"),
                order.get("tx_hash_polygon", ""),
            )
        )

def swap_tx_ja_processada(tx_hash: str) -> bool:
    with get_connection() as conn:
        row = conn.execute("SELECT 1 FROM swap_orders WHERE tx_hash_polygon = ?", (tx_hash,)).fetchone()
    return row is not None

def buscar_swap_order_pendente_por_valor(usdc_valor: float, tolerancia: float = 0.01) -> dict | None:
    """Busca swap order pendente cujo usdc_amount esteja dentro da tolerância."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT ref_id, tipo, plg_address, polygon_address, plg_amount, usdc_amount, taxa, created_at, status, tx_hash_polygon FROM swap_orders WHERE status = 'AGUARDANDO' ORDER BY created_at ASC"
        ).fetchall()
    for r in rows:
        d = dict(r)
        if abs(d.get("usdc_amount", 0) - usdc_valor) <= tolerancia:
            return d
    return None

def listar_swap_orders(limite: int = 50) -> list:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT ref_id, tipo, plg_address, polygon_address, plg_amount, usdc_amount, taxa, created_at, status, tx_hash_polygon FROM swap_orders ORDER BY created_at DESC LIMIT ?",
            (limite,)
        ).fetchall()
    return [dict(r) for r in rows]

# --- VALIDAÇÃO DE TXS POR MINERADORES ---

def is_tx_validada(ref_tx_hash: str) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM mine_validated_txs WHERE ref_tx_hash = ?", (ref_tx_hash,)
        ).fetchone()
    return row is not None

def marcar_tx_validada(ref_tx_hash: str, mine_tx_hash: str, miner_addr: str):
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO mine_validated_txs (ref_tx_hash, mine_tx_hash, miner_addr, validated_at) "
            "VALUES (?, ?, ?, ?)",
            (ref_tx_hash, mine_tx_hash, miner_addr, _time.time())
        )

# --- OFERTAS P2P PLG-G ---

def salvar_plgg_oferta(oferta: dict):
    with get_connection() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO plgg_ofertas
               (oferta_id, vendedor, comprador, amount_plgg, preco_unitario, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (oferta['oferta_id'], oferta['vendedor'], oferta['comprador'],
             oferta['amount_plgg'], oferta['preco_unitario'],
             oferta.get('status', 'PENDENTE'), oferta.get('created_at', _time.time()))
        )

def carregar_plgg_oferta(oferta_id: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT oferta_id, vendedor, comprador, amount_plgg, preco_unitario, status, created_at "
            "FROM plgg_ofertas WHERE oferta_id = ?",
            (oferta_id,)
        ).fetchone()
    return dict(row) if row else None

def atualizar_status_plgg_oferta(oferta_id: str, status: str):
    with get_connection() as conn:
        conn.execute(
            "UPDATE plgg_ofertas SET status = ? WHERE oferta_id = ?",
            (status, oferta_id)
        )

# --- TRANSAÇÕES POR ADDRESS ---

def buscar_transacoes_por_address(address: str) -> list:
    """Retorna transações onde o address é sender ou receiver."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT tx_hash, sender, receiver, amount, parents, timestamp,
                      signature, zk_proof_size, node_type,
                      COALESCE(aerarium_amount, 0) AS aerarium_amount,
                      COALESCE(zk_proof_hash, '')  AS zk_proof_hash
               FROM transactions
               WHERE sender = ? OR receiver = ?
               ORDER BY timestamp DESC""",
            (address, address)
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["de"]   = d["sender"]
        d["para"] = d["receiver"]
        result.append(d)
    return result


def buscar_vesting_por_address(address: str) -> list:
    """Retorna apenas dados de vesting (plgg_vesting + miner_vesting) para merge em nós secundários."""
    result = []
    with get_connection() as conn:
        # PLG-G Genesis
        rows = conn.execute(
            """SELECT tx_hash_externo AS tx_hash, plg_address, amount, usdt_pago,
                      purchase_date AS timestamp, release_date, status
               FROM plgg_vesting WHERE plg_address = ? ORDER BY purchase_date DESC""",
            (address,)
        ).fetchall()
        for r in rows:
            d = dict(r)
            result.append({
                "tx_hash": d.get("tx_hash", ""), "de": "GENESIS_CONTRACT", "para": address,
                "sender": "GENESIS_CONTRACT", "receiver": address,
                "amount": d.get("amount", 0), "timestamp": d.get("timestamp", 0),
                "node_type": "GENESIS", "status": d.get("status", "LOCKED"),
                "usdt_pago": d.get("usdt_pago", 0), "release_date": d.get("release_date", ""),
                "fonte": "GENESIS",
            })
        # PLG Minerado
        rows = conn.execute(
            """SELECT id, amount, release_date, status, node_type, pool,
                      COALESCE(node_id, '') AS node_id,
                      COALESCE(categoria, '') AS categoria,
                      created_at AS timestamp
               FROM miner_vesting WHERE plg_address = ? ORDER BY created_at DESC""",
            (address,)
        ).fetchall()
        for r in rows:
            d = dict(r)
            nid = d.get("node_id", "")
            if nid.startswith("ANCHOR_"):
                fonte_mining = f"NÓ ÂNCORA · {nid}"
            elif nid.upper().startswith(("APP", "MOB")):
                fonte_mining = "APP MÓVEL"
            elif nid:
                fonte_mining = f"MINERADOR PC · {nid[:12]}"
            else:
                fonte_mining = "REDE"
            result.append({
                "tx_hash": f"MINING_{d['id']}", "de": "MINING_REWARD", "para": address,
                "sender": "MINING_REWARD", "receiver": address,
                "amount": d.get("amount", 0), "timestamp": d.get("timestamp", 0),
                "node_type": d.get("node_type", "VALIDATOR"),
                "status": d.get("status", "LOCKED"),
                "release_date": d.get("release_date", ""),
                "node_id": nid, "categoria": d.get("categoria", ""),
                "fonte": fonte_mining,
            })
    result.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    return result


# --- GENESIS STATUS ---

def is_socio_genesis(plg_address: str) -> bool:
    return bool(carregar_estado(f"socio_genesis_{plg_address}", False))

def marcar_status_genesis_perdido(plg_address: str):
    salvar_estado(f"genesis_perdido_{plg_address}", True)

def status_genesis_perdido(plg_address: str) -> bool:
    return bool(carregar_estado(f"genesis_perdido_{plg_address}", False))

# --- PENDING PURCHASES ---

def listar_pending_aguardando() -> list:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT ref_id, plg_address, usdt_amount, plgg_amount, tx_hash, created_at, status FROM pending_purchases WHERE status = 'AGUARDANDO' ORDER BY created_at ASC"
        ).fetchall()
    return [dict(r) for r in rows]

# --- FUNDAÇÃO (privacidade: só hash + carteira na rede) ---
# CONTRATO: hash_inscricao + carteira_plg são imutáveis após inserção.
# Caso aprovada, SOMENTE essa carteira tem direito a receber recursos da Fundação.
# O trigger 'trg_fundacao_imutavel' na DDL impõe isso ao nível do SQLite.

def salvar_inscricao_fundacao(entry: dict) -> int:
    """Regista inscrição completa. Hash BLAKE3 sobre campos públicos garante imutabilidade."""
    carteira = str(entry.get("carteira_plg", "")).strip()
    hash_inscricao = str(entry.get("hash_inscricao", "")).strip()
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT OR IGNORE INTO fundacao_registros
               (hash_inscricao, carteira_plg, created_at,
                nome_projeto, segmento, localizacao, descricao, responsavel,
                tempo_atuacao, instagram, facebook, youtube, tiktok, site,
                link_video, plg_address_submitter)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                hash_inscricao,
                carteira,
                entry.get("created_at", _time.time()),
                str(entry.get("nome_projeto",   ""))[:300],
                str(entry.get("segmento",       ""))[:50],
                str(entry.get("localizacao",    ""))[:200],
                str(entry.get("descricao",      ""))[:500],
                str(entry.get("responsavel",    ""))[:200],
                str(entry.get("tempo_atuacao",  ""))[:100],
                str(entry.get("instagram",      ""))[:300],
                str(entry.get("facebook",       ""))[:300],
                str(entry.get("youtube",        ""))[:300],
                str(entry.get("tiktok",         ""))[:300],
                str(entry.get("site",           ""))[:300],
                str(entry.get("link_video",     ""))[:500],
                str(entry.get("plg_address_submitter", ""))[:128],
            )
        )
        if cur.lastrowid:
            return cur.lastrowid
        row = conn.execute("SELECT id FROM fundacao_registros WHERE hash_inscricao=?", (hash_inscricao,)).fetchone()
        return row["id"] if row else 0

def aprovar_inscricao_fundacao(hash_inscricao: str) -> bool:
    """Marca a inscrição como APROVADA. Só altera 'status' — hash e carteira permanecem intactos.
    Retorna False se o hash não existir ou já estiver APROVADA."""
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE fundacao_registros SET status='APROVADA', aprovado_em=? WHERE hash_inscricao=? AND status='PENDENTE'",
            (_time.time(), hash_inscricao)
        )
        return cur.rowcount == 1

def rejeitar_inscricao_fundacao(hash_inscricao: str) -> bool:
    """Marca a inscrição como REJEITADA. Hash e carteira permanecem intactos."""
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE fundacao_registros SET status='REJEITADA' WHERE hash_inscricao=? AND status='PENDENTE'",
            (hash_inscricao,)
        )
        return cur.rowcount == 1

def desvincular_inscricao_fundacao(hash_inscricao: str) -> bool:
    """Reverte uma inscrição APROVADA para PENDENTE, removendo-a da lista pública.
    Hash e carteira permanecem intactos — o trigger SQLite garante imutabilidade."""
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE fundacao_registros SET status='PENDENTE', aprovado_em=NULL WHERE hash_inscricao=? AND status='APROVADA'",
            (hash_inscricao,)
        )
        return cur.rowcount == 1

def carteira_fundacao_aprovada(carteira_plg: str) -> dict | None:
    """Verifica se uma carteira pertence a uma inscrição APROVADA."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, hash_inscricao, carteira_plg, nome_projeto, segmento, created_at, aprovado_em "
            "FROM fundacao_registros WHERE carteira_plg=? AND status='APROVADA'",
            (carteira_plg,)
        ).fetchone()
    return dict(row) if row else None

def buscar_inscricao_fundacao(hash_inscricao: str) -> dict | None:
    """Lê um registo completo pelo hash."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, hash_inscricao, carteira_plg, created_at, status, aprovado_em, "
            "nome_projeto, segmento, localizacao, descricao, responsavel, tempo_atuacao, "
            "instagram, facebook, youtube, tiktok, site, link_video, plg_address_submitter "
            "FROM fundacao_registros WHERE hash_inscricao=?",
            (hash_inscricao,)
        ).fetchone()
    return dict(row) if row else None

def listar_fundacao_aprovadas() -> list:
    """Retorna todas as inscrições APROVADAS com campos públicos (sem ip_origem)."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT hash_inscricao, carteira_plg, nome_projeto, segmento, localizacao, "
            "descricao, responsavel, aprovado_em, created_at "
            "FROM fundacao_registros WHERE status='APROVADA' ORDER BY aprovado_em DESC"
        ).fetchall()
    return [dict(r) for r in rows]

# --- BANS / SLASHING ---

def salvar_ban(uidg: str, confiscado: float, motivo: str):
    """Persiste banimento permanente de nó infrator (Protocolo Slashing)."""
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO bans (uidg, confiscado, motivo, banned_at) VALUES (?, ?, ?, ?)",
            (uidg, confiscado, motivo, _time.time())
        )

def carregar_bans() -> dict:
    """Retorna dict {uidg: {score: -1, staked: 0.0}} de todos os banidos."""
    with get_connection() as conn:
        rows = conn.execute("SELECT uidg FROM bans").fetchall()
    return {row["uidg"]: {"score": -1, "staked": 0.0} for row in rows}

def is_banido(uidg: str) -> bool:
    """Verifica se um UIDG está banido permanentemente."""
    with get_connection() as conn:
        row = conn.execute("SELECT 1 FROM bans WHERE uidg = ?", (uidg,)).fetchone()
    return row is not None

# --- SESSÕES AUTH ---

def salvar_sessao(plg_address: str, token: str, ttl_segundos: int = 86400):
    """Grava token de sessão com TTL determinístico."""
    now = int(_time.time())
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO sessions (plg_address, token, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (plg_address, token, now, now + ttl_segundos)
        )

def validar_sessao(plg_address: str, token: str) -> bool:
    """Retorna True se o token pertence ao endereço e ainda não expirou."""
    now = int(_time.time())
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM sessions WHERE plg_address = ? AND token = ? AND expires_at > ?",
            (plg_address, token, now)
        ).fetchone()
    return row is not None

def revogar_sessao(plg_address: str, token: str):
    """Remove sessão activa (logout)."""
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM sessions WHERE plg_address = ? AND token = ?",
            (plg_address, token)
        )

def limpar_sessoes_expiradas():
    """Purga sessões expiradas (manutenção periódica)."""
    now = int(_time.time())
    with get_connection() as conn:
        conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))

def obter_token_sessao_por_address(plg_address: str) -> str | None:
    """Retorna o token de sessão activo mais recente para um endereço, ou None se inexistente/expirado."""
    now = int(_time.time())
    with get_connection() as conn:
        row = conn.execute(
            "SELECT token FROM sessions WHERE plg_address = ? AND expires_at > ? ORDER BY created_at DESC LIMIT 1",
            (plg_address, now)
        ).fetchone()
    return row["token"] if row else None

# --- NONCES AUTH ---

def salvar_nonce_auth(nonce: str, ttl_segundos: int = 300):
    now = int(_time.time())
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO nonces (nonce, status, created_at, expires_at) VALUES (?, 'pending', ?, ?)",
            (nonce, now, now + ttl_segundos)
        )

def obter_nonce_auth(nonce: str) -> dict | None:
    now = int(_time.time())
    with get_connection() as conn:
        row = conn.execute(
            "SELECT status, plg_address, created_at, expires_at FROM nonces WHERE nonce = ? AND expires_at > ?",
            (nonce, now)
        ).fetchone()
    if not row:
        return None
    return {
        "status"     : row[0],
        "plg_address": row[1],
        "created_at" : float(row[2]),
        "expires_at" : float(row[3]),
    }

def marcar_nonce_verificado(nonce: str, plg_address: str) -> bool:
    now = int(_time.time())
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE nonces SET status = 'verified', plg_address = ? "
            "WHERE nonce = ? AND status = 'pending' AND expires_at > ?",
            (plg_address, nonce, now)
        )
        return cur.rowcount == 1

def remover_nonce_auth(nonce: str):
    with get_connection() as conn:
        conn.execute("DELETE FROM nonces WHERE nonce = ?", (nonce,))

def limpar_nonces_expirados():
    now = int(_time.time())
    with get_connection() as conn:
        conn.execute("DELETE FROM nonces WHERE expires_at <= ?", (now,))

# --- MINERADORES ---

def salvar_vesting(plg_address: str, entry: dict):
    """Regista recompensa de vesting ou vínculo de prover para um nó."""
    import time as _t
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO miner_vesting
               (plg_address, amount, release_date, status, node_type, pool, node_id, categoria, score, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                plg_address,
                entry.get("amount", 0.0),
                entry.get("release_date", ""),
                entry.get("status", "LOCKED"),
                entry.get("node_type", "VALIDATOR"),
                entry.get("pool", "VALIDATOR_POOL"),
                entry.get("node_id", ""),
                entry.get("categoria", ""),
                int(entry.get("score", 0)),
                _t.time(),
            )
        )

def upsert_no_ativo(plg_address: str, node_id: str, node_type: str = "VALIDATOR"):
    """Regista ou atualiza presença de um nó ativo na rede (via heartbeat)."""
    import time as _t
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO nos_rede (plg_address, node_id, node_type, last_seen)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(plg_address, node_id) DO UPDATE SET
                 node_type = excluded.node_type,
                 last_seen = excluded.last_seen""",
            (plg_address, node_id, node_type, _t.time())
        )

def get_node_counts() -> dict:
    """Retorna contagem de nós ativos por categoria.
    nos_mineradores = TODOS os nós que mineram: âncoras (ANCHOR+VALIDATOR) + provers externos.
    ancoras         = subconjunto de infraestrutura (ANCHOR type) para display separado.
    validadores     = subconjunto VALIDATOR para cálculo de recompensa R=G/N.
    """
    import time as _t
    HEARTBEAT_TTL = 900
    _WALLET_ONLY  = {'WALLET'}
    limite = _t.time() - HEARTBEAT_TTL
    with get_connection() as conn:
        vest_provers = conn.execute(
            "SELECT COUNT(DISTINCT plg_address) FROM miner_vesting WHERE node_type != 'VALIDATOR'"
        ).fetchone()[0] or 0
        vest_validators = conn.execute(
            "SELECT COUNT(DISTINCT plg_address) FROM miner_vesting WHERE node_type = 'VALIDATOR'"
        ).fetchone()[0] or 0
        vest_addrs = {r[0] for r in conn.execute(
            "SELECT DISTINCT plg_address FROM miner_vesting"
        ).fetchall()}
        hb_rows = conn.execute(
            "SELECT plg_address, node_type FROM nos_rede WHERE last_seen >= ?", (limite,)
        ).fetchall()
    hb_ancoras    = sum(1 for r in hb_rows if r[1] == 'ANCHOR')
    # hb_new: heartbeat nodes não em vest_addrs e não puramente WALLET
    # Inclui ANCHOR e VALIDATOR (nós âncora que mineram) além de PROVER/DESKTOP/MINER
    hb_new        = [r for r in hb_rows if r[0] not in vest_addrs and r[1] not in _WALLET_ONLY]
    hb_provers    = sum(1 for r in hb_new if r[1] not in ('VALIDATOR', 'ANCHOR'))
    hb_validators = sum(1 for r in hb_new if r[1] == 'VALIDATOR')
    hb_anchors_n  = sum(1 for r in hb_new if r[1] == 'ANCHOR')
    # nos_mineradores = apenas Provers/ANCHORs (geram provas ZK). Validadores são contados separadamente.
    return {
        "nos_mineradores": vest_provers + hb_provers + hb_anchors_n,
        "validadores"    : vest_validators + hb_validators,
        "ancoras"        : hb_ancoras,
    }

def contar_mineradores_por_dono(plg_address: str) -> int:
    """Conta quantos nós mineradores únicos (DISTINCT node_id) um endereço possui."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(DISTINCT node_id) FROM miner_vesting "
            "WHERE plg_address = ? AND node_id IS NOT NULL AND node_id != ''",
            (plg_address,)
        ).fetchone()
    return row[0] if row else 0

def node_id_ja_registado(plg_address: str, node_id: str) -> bool:
    """Verifica se um node_id já está registado para este endereço (dispositivo conhecido)."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM miner_vesting WHERE plg_address = ? AND node_id = ? LIMIT 1",
            (plg_address, node_id)
        ).fetchone()
    return row is not None


def _release_ts(val) -> float:
    """Converte release_date (float Unix ou str ISO) para Unix timestamp float."""
    if val is None:
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        pass
    from datetime import datetime as _dt
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return _dt.strptime(str(val), fmt).timestamp()
        except ValueError:
            pass
    return 0.0

def salvar_plg_transfer(tx_hash: str, sender: str, receiver: str, amount: float) -> None:
    """Regista uma transferência P2P real de PLG na tabela plg_transfers."""
    import time as _t
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO plg_transfers (tx_hash, sender, receiver, amount, timestamp, status) "
            "VALUES (?, ?, ?, ?, ?, 'confirmed')",
            (tx_hash, sender, receiver, amount, _t.time())
        )

def carregar_saldo_plg(address: str) -> dict:
    """Saldo PLG: mineração desbloqueada + PLG recebido via transfer - PLG enviado via transfer."""
    import time as _t
    agora = _t.time()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, amount, status, release_date FROM miner_vesting WHERE plg_address = ?",
            (address,)
        ).fetchall()
        # Auto-liberta entradas cujo lockup expirou
        ids_liberar = [r[0] for r in rows if r[2] == 'LOCKED' and agora >= _release_ts(r[3])]
        if ids_liberar:
            conn.execute(
                f"UPDATE miner_vesting SET status='RELEASED' WHERE id IN ({','.join('?'*len(ids_liberar))})",
                ids_liberar
            )
        # Saldo de transferências P2P
        sent_row = conn.execute(
            "SELECT COALESCE(SUM(amount), 0.0) FROM plg_transfers WHERE sender = ?", (address,)
        ).fetchone()
        recv_row = conn.execute(
            "SELECT COALESCE(SUM(amount), 0.0) FROM plg_transfers WHERE receiver = ?", (address,)
        ).fetchone()
    total    = sum(r[1] for r in rows)
    locked   = sum(r[1] for r in rows if r[2] == 'LOCKED' and agora < _release_ts(r[3]))
    minerado_liberado = total - locked
    enviado  = float(sent_row[0]) if sent_row else 0.0
    recebido = float(recv_row[0]) if recv_row else 0.0
    liberado = max(0.0, minerado_liberado - enviado + recebido)
    return {"total": round(total + recebido - enviado, 6),
            "locked": round(locked, 6),
            "liberado": round(liberado, 6)}

def get_plg_minerado_total() -> float:
    """Soma total de PLG em miner_vesting (minerado pelo protocolo, com DNA garantido)."""
    with get_connection() as conn:
        row = conn.execute("SELECT COALESCE(SUM(amount), 0.0) FROM miner_vesting").fetchone()
    return round(float(row[0]), 6)

def listar_mineradores_ativos(ttl_segundos: int = 900) -> list:
    """Retorna PLG addresses de nós com heartbeat recente (excluindo WALLET)."""
    import time as _t
    limite = _t.time() - ttl_segundos
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT plg_address FROM nos_rede WHERE last_seen >= ? AND node_type != 'WALLET'",
            (limite,)
        ).fetchall()
    return [r[0] for r in rows]


# Inicialização do Banco V4.3
inicializar_banco()