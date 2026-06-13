"""
PLEGMA DAG — Core API V5.0 (FastAPI + uvicorn)
Substitui core_vm.py/_ThreadingHTTPServer por ASGI assíncrono.
Motor determinístico/pós-quântico (core_dag, lattice_shield, zk_press) intacto.
"""
import gzip
import json
import logging
import math
import os
import re
import threading
import time
import asyncio

_log = logging.getLogger(__name__)
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, Request, Query, Path as FPath
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

# ── Módulos do protocolo (intactos) ──────────────────────────────────────────
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from genesis import GenesisVertex
from core_dag import PlegmaDAG
from sentinela import check_priority, Vigia, Crivo, Escudo, SentinelaCore
from tx_verifier import verificar_tx, verificar_sessao_header
import genesis_contract
import monitor_pagamentos
import plegma_db
import gossip
import social_db
import labs_db
import network_phase

try:
    import blake3 as _blake3
except ImportError:
    raise RuntimeError("[FALHA FATAL] Módulo blake3 ausente no Core API.")

def _b3_hash(data: bytes) -> str:
    return _blake3.blake3(data).hexdigest()

# ── Constantes de Autenticação Admin ─────────────────────────────────────────
FOUNDER_ADDRESS   = "PLG198840FFDD9FA7A8AEA2747C994B152B88A49F7C"
ADMIN_SESSION_TTL = 28800   # 8 horas
ADMIN_NONCE_TTL   = 300     # 5 minutos

def _check_admin(key: str) -> bool:
    """Verifica se key é um session token válido emitido via QR auth."""
    if not key:
        return False
    session = plegma_db.carregar_estado(f"admin_session:{key}", None)
    if session and isinstance(session, dict):
        if session.get("expires_at", 0) > time.time():
            return True
    return False

# ── Config email ──────────────────────────────────────────────────────────────
NOTIFY_EMAIL_TO  = os.environ.get("PLEGMA_NOTIFY_EMAIL", "plegmadag@proton.me")
NOTIFY_SMTP_HOST = os.environ.get("PLEGMA_SMTP_HOST", "")
NOTIFY_SMTP_PORT = int(os.environ.get("PLEGMA_SMTP_PORT", "587"))
NOTIFY_SMTP_USER = os.environ.get("PLEGMA_SMTP_USER", "")
NOTIFY_SMTP_PASS = os.environ.get("PLEGMA_SMTP_PASS", "")

def _notificar_inscricao_fundacao(entry: dict):
    campos_excluir = {"website_url", "ip_origem", "status"}
    corpo = "\n".join(f"{k}: {v}" for k, v in entry.items() if k not in campos_excluir)

    # Fallback: regista em ficheiro local (garante que nada se perde mesmo sem SMTP)
    try:
        log_path = os.path.join(os.path.dirname(__file__), "fundacao_inscricoes.log")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"=== {entry.get('nome_projeto','?')} — {entry.get('hash_inscricao','')[:16]} ===\n")
            f.write(corpo + "\n\n")
    except Exception:
        pass

    if not NOTIFY_SMTP_HOST or not NOTIFY_SMTP_USER:
        return
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[PLEGMA Fundação] Nova inscrição — {entry.get('nome_projeto','?')}"
        msg["From"]    = NOTIFY_SMTP_USER
        msg["To"]      = NOTIFY_EMAIL_TO
        msg.attach(MIMEText(
            f"Nova inscrição recebida na PLEGMA Fundação.\n\n{corpo}",
            "plain", "utf-8"
        ))
        with smtplib.SMTP(NOTIFY_SMTP_HOST, NOTIFY_SMTP_PORT, timeout=10) as s:
            s.ehlo(); s.starttls(); s.login(NOTIFY_SMTP_USER, NOTIFY_SMTP_PASS)
            s.sendmail(NOTIFY_SMTP_USER, NOTIFY_EMAIL_TO, msg.as_string())
    except Exception:
        pass

# ── Estado global (idêntico ao core_vm) ──────────────────────────────────────
_genesis          = GenesisVertex()
dag               = PlegmaDAG(_genesis.hash, launch_date=datetime.fromtimestamp(network_phase.GENESIS_LAUNCH_TS))
_sentinela        = SentinelaCore()
_MOTOR_START_TS   = time.time()

_challenges: dict                 = {}
_verified_challenges: dict        = {}
_verified_challenges_lock         = asyncio.Lock()
_miner_states: dict               = {}
_rate_limit_fundacao: dict        = {}
_RATE_LIMIT_MAX                   = 3
_RATE_LIMIT_WINDOW                = 3600
_rate_limit_challenge: dict       = {}
_rate_limit_challenge_lock        = asyncio.Lock()
_CHALLENGE_MAX                    = 10
_CHALLENGE_WINDOW                 = 60
_nonces_transferencia: dict       = {}
_nonces_lock                      = asyncio.Lock()
_NONCE_TTL                        = 1800
_seed_backups: dict               = {}
_seed_backups_lock                = asyncio.Lock()
_AERARIUM_G_VALIDATOR             = 1_000.0
_AERARIUM_G_PROVER                =   667.0
_mine_last_ts: dict               = {}   # node_id → último timestamp de mining
_MINE_COOLDOWN                    = 86400  # 24h: PLG só pode ser gerado uma vez por dia por validador
_TRANSFER_AERARIUM_FEE            = 0.0   # Estatuto §6 aplica-se só a mineração; transferências P2P não têm taxa Aerarium

# ── Batch Write Queue (persistência assíncrona) ───────────────────────────────
_MAX_TIPS      = 1000          # espelho de core_dag.MAX_TIPS
_BATCH_WINDOW  = 0.050         # janela de acumulação: 50 ms
_BATCH_MAX     = 500           # flush antecipado se batch atingir 500 ops
_write_queue: asyncio.Queue    = asyncio.Queue(maxsize=50_000)
_dag_topo_lock: asyncio.Lock   = asyncio.Lock()

_PMR_NUCLEO = [
    {"id": "2.1", "modulo": "IA no núcleo — agente de consenso autônomo",          "critico": True,  "ok": False},
    {"id": "2.2", "modulo": "Agentes autônomos (mineração, reputação, slashing)",   "critico": True,  "ok": False},
    {"id": "2.3", "modulo": "PlegmaVM — smart contracts completos",                 "critico": True,  "ok": False},
    {"id": "2.4", "modulo": "Dilithium3 real via FFI C no app mobile",              "critico": True,  "ok": True},
    {"id": "2.5", "modulo": "Pacto dos 5 — recuperação social de chaves",           "critico": False, "ok": False},
    {"id": "2.6", "modulo": "Cartão de débito integrado",                           "critico": False, "ok": False},
    {"id": "2.7", "modulo": "Auditoria de segurança externa independente",          "critico": False, "ok": False},
]
_META_NOS_ATIVOS = 100_000
_QUORUM_BURN     = 0.67

# ── Helpers ───────────────────────────────────────────────────────────────────
def _ok(data: dict, status: int = 200) -> JSONResponse:
    return JSONResponse(content=data, status_code=status)

def _err(msg: str, status: int = 400) -> JSONResponse:
    return JSONResponse(content={"erro": msg}, status_code=status)

async def _registrar_nonce(nonce: str) -> bool:
    agora = time.time()
    async with _nonces_lock:
        expirados = [k for k, ts in _nonces_transferencia.items() if agora - ts > _NONCE_TTL]
        for k in expirados:
            del _nonces_transferencia[k]
        if nonce in _nonces_transferencia:
            return False
        _nonces_transferencia[nonce] = agora
        return True

async def _check_rl_challenge(ip: str) -> bool:
    now = time.time()
    async with _rate_limit_challenge_lock:
        janela = [t for t in _rate_limit_challenge.get(ip, []) if now - t < _CHALLENGE_WINDOW]
        if len(janela) >= _CHALLENGE_MAX:
            _rate_limit_challenge[ip] = janela
            return False
        janela.append(now)
        _rate_limit_challenge[ip] = janela
        return True

def _check_rl_fundacao(ip: str) -> bool:
    now = time.time()
    janela = [t for t in _rate_limit_fundacao.get(ip, []) if now - t < _RATE_LIMIT_WINDOW]
    if len(janela) >= _RATE_LIMIT_MAX:
        _rate_limit_fundacao[ip] = janela
        return False
    janela.append(now)
    _rate_limit_fundacao[ip] = janela
    return True

# Lockout progressivo para endpoints de autenticação admin (anti brute-force).
# Conta falhas consecutivas mais recentes por IP e aplica espera exponencial.
_auth_attempts: dict       = {}
_auth_attempts_lock        = asyncio.Lock()
_AUTH_ATTEMPTS_WINDOW      = 86_400       # janela de 24h
_AUTH_ATTEMPTS_RETENTION   = 7 * 86_400   # apaga histórico com >7 dias
_AUTH_ATTEMPTS_FILE        = os.path.join(os.path.dirname(__file__), "plegma_auth_attempts.json")
_AUTH_LOCKOUT_TIERS        = [            # (falhas, espera_segundos)
    (3,    60),
    (5,   900),
    (7,  3_600),
    (10, 86_400),
]

async def _check_auth_lockout(ip: str) -> tuple[bool, int]:
    """Devolve (permitido, retry_after_seg). Não regista tentativa — só avalia."""
    now = time.time()
    async with _auth_attempts_lock:
        history = [(t, ok) for t, ok in _auth_attempts.get(ip, [])
                   if now - t < _AUTH_ATTEMPTS_WINDOW]
        _auth_attempts[ip] = history
    failures = 0
    last_failure_ts = 0.0
    for ts, success in reversed(history):
        if success:
            break
        failures += 1
        if ts > last_failure_ts:
            last_failure_ts = ts
    lockout = 0
    for threshold, duration in _AUTH_LOCKOUT_TIERS:
        if failures >= threshold:
            lockout = duration
    if lockout == 0:
        return True, 0
    elapsed = now - last_failure_ts
    if elapsed >= lockout:
        return True, 0
    return False, int(lockout - elapsed)

async def _record_auth_attempt(ip: str, success: bool) -> None:
    now = time.time()
    async with _auth_attempts_lock:
        history = _auth_attempts.get(ip, [])
        history.append((now, success))
        cutoff = now - _AUTH_ATTEMPTS_RETENTION
        _auth_attempts[ip] = [h for h in history if h[0] > cutoff]

def _load_auth_attempts() -> None:
    global _auth_attempts
    if not os.path.exists(_AUTH_ATTEMPTS_FILE):
        return
    try:
        with open(_AUTH_ATTEMPTS_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        now = time.time()
        cutoff = now - _AUTH_ATTEMPTS_RETENTION
        loaded = {}
        for ip, history in raw.items():
            filtered = [(float(ts), bool(ok)) for ts, ok in history if float(ts) > cutoff]
            if filtered:
                loaded[ip] = filtered
        _auth_attempts = loaded
        _log.info(f"[AUTH-RL] {len(_auth_attempts)} IP(s) carregados de persistência.")
    except Exception as exc:
        _log.warning(f"[AUTH-RL] Falha ao carregar histórico: {exc}")

def _save_auth_attempts() -> None:
    try:
        now = time.time()
        cutoff = now - _AUTH_ATTEMPTS_RETENTION
        data = {
            ip: [[ts, ok] for ts, ok in history if ts > cutoff]
            for ip, history in list(_auth_attempts.items())
            if any(ts > cutoff for ts, ok in history)
        }
        with open(_AUTH_ATTEMPTS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception as exc:
        _log.warning(f"[AUTH-RL] Falha ao salvar histórico: {exc}")

async def _auth_persist_loop() -> None:
    while True:
        await asyncio.sleep(300)
        await asyncio.to_thread(_save_auth_attempts)

# Rate limit genérico por (bucket, key) com janela deslizante.
# Usado em endpoints públicos não cobertos por _check_rl_challenge/_fundacao.
_rate_limit_generic: dict        = {}
_rate_limit_generic_lock         = asyncio.Lock()

async def _check_rl_generic(bucket: str, key: str, max_req: int, window: int) -> bool:
    now = time.time()
    composite = f"{bucket}:{key}"
    async with _rate_limit_generic_lock:
        janela = [t for t in _rate_limit_generic.get(composite, []) if now - t < window]
        if len(janela) >= max_req:
            _rate_limit_generic[composite] = janela
            return False
        janela.append(now)
        _rate_limit_generic[composite] = janela
        return True

def _update_topology_memory(tx_hash: str, parents: list) -> None:
    """Replica a parte em-memória de PlegmaDAG._atualizar_topologia (sem I/O).
    Deve ser chamada dentro de _dag_topo_lock. dag.tips é um set thread-safe."""
    with dag._tips_lock:
        dag.tips.add(tx_hash)
        for parent in parents:
            if parent != dag.genesis_hash:
                dag.tips.discard(parent)
        if len(dag.tips) > _MAX_TIPS:
            removiveis = sorted(dag.tips - {dag.genesis_hash})
            for h in removiveis[:len(dag.tips) - _MAX_TIPS]:
                dag.tips.discard(h)

async def _enqueue(write_fn, blake3_key: str) -> None:
    """Enfileira um write SQLite com chave determinística BLAKE3.
    write_fn(conn) executa a operação sem auto-commit."""
    await _write_queue.put((write_fn, blake3_key))

async def _db_writer_loop() -> None:
    """Background asyncio task: drena _write_queue a cada 50 ms e faz
    um único commit ACID por batch, ordenado por blake3_key (determinismo).
    Em caso de falha: rollback + gossip resync."""
    while True:
        await asyncio.sleep(_BATCH_WINDOW)
        batch: list = []
        while len(batch) < _BATCH_MAX:
            try:
                batch.append(_write_queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        if not batch:
            continue
        # Ordenação determinística: BLAKE3 key garante paridade entre nós
        batch.sort(key=lambda x: x[1])

        def _commit(b):
            conn = plegma_db.get_connection()
            try:
                for fn, _ in b:
                    fn(conn)
                conn.commit()
            except Exception as exc:
                conn.rollback()
                raise exc
            finally:
                conn.close()

        try:
            await asyncio.to_thread(_commit, batch)
        except Exception as e:
            logging.error(f"[BATCH WRITER] FALHA ACID: {e} — gossip resync acionado")
            threading.Thread(
                target=gossip.sincronizar_com_peers, args=(dag,), daemon=True
            ).start()

def _tx_para_dict(tx) -> dict:
    if hasattr(tx, 'to_dict'):
        return tx.to_dict()
    return tx

def _get_pmr_status() -> dict:
    try:
        nos_ativos = dag.get_status().get('nos_ativos', 0)
    except Exception:
        nos_ativos = 0
    c1_ok = nos_ativos >= _META_NOS_ATIVOS
    c1_pct = min(100, int((nos_ativos / _META_NOS_ATIVOS) * 100))
    criticos_pendentes = [x for x in _PMR_NUCLEO if x['critico'] and not x['ok']]
    todos_criticos_ok  = len(criticos_pendentes) == 0
    itens_ok           = sum(1 for x in _PMR_NUCLEO if x['ok'])
    c2_pct = int((itens_ok / len(_PMR_NUCLEO)) * 100)
    c3_ok, c3_pct = False, 0
    score = int((c1_pct + c2_pct + c3_pct) / 3)
    burn_possivel = c1_ok and todos_criticos_ok and c3_ok
    if burn_possivel:
        mensagem = "Todas as condições satisfeitas. Burn da Chave DEUS pode ser iniciado."
    elif not todos_criticos_ok:
        mensagem = f"Itens críticos pendentes bloqueiam o burn: {', '.join([x['id'] for x in criticos_pendentes])}"
    elif not c1_ok:
        mensagem = f"Rede em fase de crescimento ({nos_ativos:,}/{_META_NOS_ATIVOS:,} nós). Chave DEUS ativa."
    else:
        mensagem = "Aguardando aprovação da comunidade (quórum ≥ 67%)."
    return {
        "score_pmr": score, "burn_possivel": burn_possivel, "chave_deus_ativa": True,
        "condicao_rede": {"ok": c1_ok, "nos_ativos": nos_ativos, "meta": _META_NOS_ATIVOS, "progresso_pct": c1_pct},
        "condicao_nucleo": {"ok": todos_criticos_ok, "itens_total": len(_PMR_NUCLEO), "itens_ok": itens_ok,
                            "criticos_pendentes": len(criticos_pendentes), "checklist": _PMR_NUCLEO, "progresso_pct": c2_pct},
        "condicao_consenso": {"ok": c3_ok, "quorum_minimo": f"{int(_QUORUM_BURN*100)}%", "proposta_ativa": False, "progresso_pct": c3_pct},
        "mensagem": mensagem,
    }

def _init_seed_backup_db():
    with plegma_db.get_connection() as sc:
        sc.execute(
            "CREATE TABLE IF NOT EXISTS seed_backups ("
            "anchor_id TEXT PRIMARY KEY, plg_address TEXT NOT NULL, "
            "seed_hash TEXT NOT NULL UNIQUE, payload TEXT, created_at TEXT NOT NULL)"
        )
        sc.commit()
        rows = sc.execute(
            "SELECT anchor_id, plg_address, seed_hash, created_at, payload FROM seed_backups"
        ).fetchall()
    for row in rows:
        _seed_backups[row[2]] = {
            "anchor_id": row[0], "plg_address": row[1],
            "seed_hash": row[2], "created_at": row[3],
            "payload"  : row[4],
        }
    _log.info(f"[SEED] {len(_seed_backups)} backup(s) ZK ancorado(s).")

# ── Lifespan (startup/shutdown) ────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    _log.info("==================================================")
    _log.info(" [!] CORE API PLEGMA V5.0 PÓS-QUÂNTICO (FastAPI) ")
    _log.info("==================================================")
    # Tudo em background com timeout — yield acontece sempre em < 5s
    import threading as _threading
    try:
        await asyncio.wait_for(asyncio.to_thread(_init_seed_backup_db), timeout=10)
    except Exception:
        pass
    try:
        await asyncio.wait_for(asyncio.to_thread(_load_auth_attempts), timeout=5)
    except Exception:
        pass
    _threading.Thread(target=gossip.sincronizar_com_peers, args=(dag,), daemon=True).start()
    _threading.Thread(target=gossip.iniciar_loop_reconexao, args=(dag, 300), daemon=True).start()
    _threading.Thread(target=monitor_pagamentos.iniciar, daemon=True).start()
    try:
        network_phase.iniciar_watchdog()
    except Exception:
        pass
    asyncio.create_task(_db_writer_loop())
    asyncio.create_task(_auth_persist_loop())
    try:
        _hn = os.uname().nodename
    except AttributeError:
        _hn = os.environ.get("COMPUTERNAME") or "anchor"
    _nid = os.environ.get("PLEGMA_NODE_ADDRESS") or (
        "PLG" + _b3_hash((_hn + "anchor").encode())[:40].upper()
    )
    _hb_payload = json.dumps({
        "node_id"   : f"ANCHOR_{_hn[:8]}",
        "metadata"  : {"plg_address": _nid, "node_type": "ANCHOR"},
        "public_key": "", "signature": ""
    }).encode()

    async def _self_heartbeat():
        import urllib.request as _urllib_req
        while True:
            # registo local
            try:
                await asyncio.to_thread(
                    plegma_db.upsert_no_ativo, _nid, f"ANCHOR_{_hn[:8]}", "ANCHOR"
                )
            except Exception:
                pass
            # broadcast para todos os peers (regista este nó em cada DB remota)
            for _peer in gossip.carregar_peers():
                def _post_hb(_url=_peer):
                    try:
                        _req = _urllib_req.Request(
                            _url.rstrip('/') + '/api/node/heartbeat',
                            data=_hb_payload, method='POST'
                        )
                        _req.add_header('Content-Type', 'application/json')
                        with _urllib_req.urlopen(_req, timeout=5): pass
                    except Exception:
                        pass
                await asyncio.to_thread(_post_hb)
            await asyncio.sleep(60)
    asyncio.create_task(_self_heartbeat())
    yield
    await asyncio.to_thread(_save_auth_attempts)

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="PLEGMA DAG API", version="5.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://plegmadag.com", "https://www.plegmadag.com", "https://plagmadag.com"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

def _get_ip(request: Request) -> str:
    fwd = request.headers.get("X-Forwarded-For", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "0.0.0.0"

# =============================================================================
# GET endpoints
# =============================================================================

@app.get("/api/rede/fase")
async def rede_fase():
    return await asyncio.to_thread(network_phase.get_status)

@app.get("/api/node/map")
async def node_map(request: Request):
    data = await asyncio.to_thread(network_phase.get_node_map)
    payload    = json.dumps(data, separators=(",", ":")).encode()
    compressed = gzip.compress(payload)
    if "gzip" in request.headers.get("Accept-Encoding", ""):
        return Response(
            content=compressed,
            media_type="application/json",
            headers={"Content-Encoding": "gzip", "Content-Length": str(len(compressed))},
        )
    return Response(content=payload, media_type="application/json")

@app.get("/api/status")
@app.get("/api/dag/status")
async def status():
    st = await asyncio.to_thread(dag.get_status)
    fase_info   = await asyncio.to_thread(network_phase.get_status)
    node_counts = await asyncio.to_thread(plegma_db.get_node_counts)
    # nos_mineradores = Provers/ANCHORs apenas. Total activos = provers + validadores.
    _total_ativos = node_counts["nos_mineradores"] + node_counts["validadores"]
    try:
        import psutil as _ps
        _cpu  = round(_ps.cpu_percent(interval=None), 1)
        _mem  = round(_ps.virtual_memory().percent, 1)
        _du   = _ps.disk_usage('/')
        _disk = round(_du.percent, 1)
        _disk_used_gb  = round(_du.used  / 1_073_741_824, 1)
        _disk_total_gb = round(_du.total / 1_073_741_824, 1)
    except Exception:
        _cpu = _mem = _disk = _disk_used_gb = _disk_total_gb = None
    return {
        "rede": "PLEGMA DAG (SYS-ZKDAG)", "status": "ONLINE",
        "nos_ativos": _total_ativos, "nos_ancoras": node_counts["ancoras"],
        "nos_mineradores": node_counts["nos_mineradores"],
        "validadores_ativos": node_counts["validadores"],
        "recompensa_validator_atual": round(_AERARIUM_G_VALIDATOR / max(1, node_counts["validadores"]), 6),
        "recompensa_prover_atual": round(_AERARIUM_G_PROVER / max(1, node_counts["nos_mineradores"]), 6),
        "total_transacoes": st["total_transacoes"],
        "tips_pendentes": st["tips_pendentes"],
        "total_aceitas": st["total_aceitas"],
        "total_rejeitadas": st["total_rejeitadas"],
        "dificuldade": "Adaptativa",
        "genesis_hash": _genesis.hash,
        "rede_fase": fase_info["fase"],
        "transacoes_ativas": fase_info["transacoes_ativas"],
        "launch_ts_utc": fase_info["launch_ts_utc"],
        "launch_madrid": fase_info["launch_madrid"],
        "cpu_pct": _cpu, "mem_pct": _mem,
        "disk_pct": _disk, "disk_used_gb": _disk_used_gb,
        "disk_total_gb": _disk_total_gb,
        "motor_start_ts": _MOTOR_START_TS,
        "network_start_ts": network_phase.FASE_ZERO_START_TS,
        # Cada miner ativo cicla ~1 hash/5s = 0.2 H/s; validadores contribuem 0.08 H/s
        "hashrate_rede": round(node_counts["nos_mineradores"] * 0.2 + node_counts["validadores"] * 0.08, 3),
        # PLG supply — actualizados a cada mining e consultados pelo dashboard
        "plg_supply_total" : 21_000_000_000,
        "plg_minerado_total": await asyncio.to_thread(plegma_db.get_plg_minerado_total),
        "plg_nao_emitido"  : 21_000_000_000 - await asyncio.to_thread(plegma_db.get_plg_minerado_total),
    }

@app.get("/api/sentinela/status")
async def sentinela_status():
    vigia = Vigia(); crivo = Crivo(); escudo = Escudo()
    return {
        "sentinela": "ATIVO",
        "agentes": {
            "vigia":  {"ativo": True, "jurisdicoes_bloqueadas": vigia.banned_jurisdictions, "max_nos_por_ip": vigia.MAX_MOBILE_NODES_PER_IP},
            "crivo":  {"ativo": True, "overflow_protection": True, "reentrancy_protection": True},
            "escudo": {"ativo": True, "nos_monitorados": len(escudo.reputation_system), "slashing_ativo": True},
        },
    }

@app.get("/api/cluster/status")
async def cluster_status():
    _CLUSTER_REMOTE = [
        {"id": "usa", "url": "http://209.126.7.120:8080"},
        {"id": "mum", "url": "http://217.217.251.206:8080"},
        {"id": "sin", "url": "http://82.197.70.189:8080"},
    ]
    t0 = time.time()
    try:
        import psutil as _ps
        _cpu  = round(_ps.cpu_percent(interval=None), 1)
        _mem  = round(_ps.virtual_memory().percent, 1)
        _du   = _ps.disk_usage('/')
        _disk = round(_du.percent, 1)
        _dug  = round(_du.used  / 1_073_741_824, 1)
        _dtg  = round(_du.total / 1_073_741_824, 1)
    except Exception:
        _cpu = _mem = _disk = _dug = _dtg = None
    st    = await asyncio.to_thread(dag.get_status)
    nc    = await asyncio.to_thread(plegma_db.get_node_counts)
    eu    = {
        "id": "eu", "online": True,
        "latency_ms": round((time.time() - t0) * 1000),
        "nos_ativos": len(await asyncio.to_thread(gossip.carregar_peers)) + 1,
        "nvm_count": nc.get("nos_mineradores", 0) + nc.get("validadores", 0),
        "total_transacoes": st.get("total_transacoes"),
        "tips_pendentes": st.get("tips_pendentes"),
        "rede_fase": network_phase.get_fase_atual(),
        "cpu_pct": _cpu, "mem_pct": _mem, "disk_pct": _disk,
        "disk_used_gb": _dug, "disk_total_gb": _dtg,
        "motor_start_ts": _MOTOR_START_TS,
        "network_start_ts": network_phase.FASE_ZERO_START_TS,
    }
    def _ping(no):
        _t = time.time()
        try:
            import urllib.request as _ur
            with _ur.urlopen(f"{no['url']}/api/status", timeout=5) as r:
                d = json.loads(r.read())
            return {
                "id": no["id"], "online": True,
                "latency_ms": round((time.time() - _t) * 1000),
                "nos_ativos": d.get("nos_ativos"),
                "nvm_count": (d.get("nos_mineradores", 0) or 0) + (d.get("validadores_ativos", 0) or 0),
                "total_transacoes": d.get("total_transacoes"),
                "tips_pendentes": d.get("tips_pendentes"),
                "rede_fase": d.get("rede_fase"),
                "cpu_pct": d.get("cpu_pct"), "mem_pct": d.get("mem_pct"),
                "disk_pct": d.get("disk_pct"), "disk_used_gb": d.get("disk_used_gb"),
                "disk_total_gb": d.get("disk_total_gb"), "motor_start_ts": d.get("motor_start_ts"),
            }
        except Exception as e:
            return {"id": no["id"], "online": False, "latency_ms": None, "erro": str(e)}

    remote = await asyncio.gather(*[asyncio.to_thread(_ping, no) for no in _CLUSTER_REMOTE])
    resultados = [eu] + list(remote)
    online = sum(1 for r in resultados if r["online"])
    return {"nos": resultados, "online": online, "total": len(resultados)}

@app.get("/api/lastBlock")
async def last_block():
    return await asyncio.to_thread(dag.get_status)

@app.get("/api/genesis/status")
async def genesis_status():
    return await asyncio.to_thread(genesis_contract.get_status)

@app.get("/api/genesis/governance")
async def genesis_governance():
    return await asyncio.to_thread(genesis_contract.get_governance_status)

@app.get("/api/governance/maturity")
async def governance_maturity():
    return await asyncio.to_thread(_get_pmr_status)

@app.get("/api/genesis/liquidity_status")
async def genesis_liquidity_status():
    return await asyncio.to_thread(genesis_contract.get_liquidity_status)

@app.get("/api/genesis/ultimo_preco")
async def genesis_ultimo_preco():
    return await asyncio.to_thread(genesis_contract.get_ultimo_preco_plgg)

@app.get("/api/genesis/burn")
async def genesis_burn():
    return await asyncio.to_thread(genesis_contract.get_burn_status)

@app.post("/api/genesis/burn")
async def genesis_burn_execute(request: Request):
    dados, err = await _parse_body(request)
    if err: return err
    if not await asyncio.to_thread(_check_admin, dados.get("admin_key", "")):
        return _err("Acesso não autorizado.", 403)
    return await asyncio.to_thread(genesis_contract.queimar_plgg_nao_vendido)

@app.get("/api/peer/hashes")
async def peer_hashes():
    return {"hashes": list(dag.transactions.keys())}

@app.get("/api/labs/propostas")
async def labs_propostas():
    return {"propostas": await asyncio.to_thread(labs_db.listar_propostas)}

@app.get("/api/genesis/saldo")
async def genesis_saldo(address: str = Query(...)):
    return await asyncio.to_thread(genesis_contract.get_saldo_liberado, address)

@app.get("/api/priority")
async def priority(address: str = Query(...)):
    resultado   = await asyncio.to_thread(check_priority, address)
    status_sg   = await asyncio.to_thread(genesis_contract.get_status_socio_genesis, address)
    resultado["socio_genesis"]            = status_sg["socio_genesis"]
    resultado["selo_genesis_ativo"]       = status_sg["selo_ativo"]
    resultado["status_genesis_perdido"]   = status_sg["status_perdido"]
    return resultado

@app.get("/api/peer/vertex/{tx_hash}")
async def peer_vertex(tx_hash: str = FPath(...)):
    # 1. Procura em memória (rápido)
    tx = dag.transactions.get(tx_hash)
    if tx:
        return _tx_para_dict(tx)
    # 2. Fallback: procura em SQLite transactions (cobre reinicios e gossip)
    try:
        with plegma_db.get_connection() as conn:
            row = conn.execute(
                """SELECT tx_hash, sender, receiver, amount, parents, timestamp,
                          signature, zk_proof_size, node_type,
                          COALESCE(aerarium_amount, 0) AS aerarium_amount,
                          COALESCE(zk_proof_hash, '')  AS zk_proof_hash
                   FROM transactions WHERE tx_hash = ?""",
                (tx_hash,)
            ).fetchone()
            if row:
                d = dict(row)
                d["de"]   = d.get("sender", "")
                d["para"] = d.get("receiver", "")
                return d
            # 3. Fallback: plg_transfers (transferências P2P confirmadas)
            row2 = conn.execute(
                """SELECT tx_hash, sender, receiver, amount, timestamp, status
                   FROM plg_transfers WHERE tx_hash = ?""",
                (tx_hash,)
            ).fetchone()
            if row2:
                d2 = dict(row2)
                return {
                    "tx_hash"   : d2["tx_hash"],
                    "sender"    : d2["sender"],
                    "receiver"  : d2["receiver"],
                    "de"        : d2["sender"],
                    "para"      : d2["receiver"],
                    "amount"    : d2["amount"],
                    "timestamp" : d2["timestamp"],
                    "node_type" : "TRANSFER",
                    "status"    : d2.get("status", "confirmed"),
                }
    except Exception:
        pass
    return _err("Vertice nao encontrado.", 404)

@app.get("/api/wallet/status")
async def wallet_status(address: str = Query(...)):
    """Status unificado da carteira — fonte canônica para App, Dashboard, Console e Admin.

    Retorna 2 saldos distintos (não confundir):
      • saldo_plg   — PLG mainnet (mineração R=G/N pós-Genesis). 0 antes do launch.
      • saldo_plgg  — PLG-G governança Genesis (total = liberado + bloqueado).
    """
    try:
        plgg = await asyncio.to_thread(genesis_contract.get_saldo_liberado, address)
    except Exception:
        plgg = {"saldo_total": 0, "saldo_liberado": 0, "saldo_bloqueado": 0, "proximo_unlock": None}
    try:
        plg_mining = await asyncio.to_thread(plegma_db.carregar_saldo_plg, address)
    except Exception:
        plg_mining = {"total": 0.0, "locked": 0.0, "liberado": 0.0}
    try:
        txs = await asyncio.to_thread(plegma_db.buscar_transacoes_por_address, address)
    except Exception:
        txs = []

    # PLG mainnet — lido de miner_vesting (DNA de mineração garantido)
    historico = []
    for tx in txs[-5:]:
        tx_d = tx if isinstance(tx, dict) else (tx.to_dict() if hasattr(tx, 'to_dict') else {})
        if tx_d.get("node_type") in ("GENESIS", "VALIDATOR", "PROVER"):
            continue  # apenas transferências P2P no histórico
        historico.append({
            "hash": tx_d.get("tx_hash", tx_d.get("hash", "")),
            "de": tx_d.get("de", tx_d.get("remetente", "")),
            "para": tx_d.get("para", tx_d.get("destinatario", "")),
            "amount": tx_d.get("amount", tx_d.get("valor", 0)),
            "timestamp": tx_d.get("timestamp", ""),
        })
    return {
        "address"             : address,
        "saldo_plg"           : plg_mining["total"],               # PLG total minerado (locked + liberado)
        "saldo_plg_liberado"  : plg_mining["liberado"],            # PLG disponível (vesting expirado)
        "saldo_plg_locked"    : plg_mining["locked"],              # PLG em vesting (30 dias)
        # Campos PLG-G completos — todas as UIs leem daqui
        "saldo_plgg"          : plgg.get("saldo_total", 0),       # total (locked + liberado)
        "saldo_plgg_liberado" : plgg.get("saldo_liberado", 0),
        "saldo_plgg_bloqueado": plgg.get("saldo_bloqueado", 0),
        "plgg_proximo_unlock" : plgg.get("proximo_unlock"),
        "historico_resumido"  : historico,
    }

_MASTER_NODE  = "http://213.199.42.88:8080"   # EUR — nó mestre (vesting data)
_MY_IP        = None

def _get_my_ip() -> str:
    global _MY_IP
    if _MY_IP is None:
        import socket
        try:
            _MY_IP = socket.gethostbyname(socket.gethostname())
        except Exception:
            _MY_IP = "127.0.0.1"
    return _MY_IP

def _buscar_vesting_master(address: str) -> list:
    """Busca miner_vesting + plgg_vesting no nó mestre (EUR) via HTTP interno."""
    import urllib.request, json as _json
    try:
        url = f"{_MASTER_NODE}/api/wallet/extrato_vesting?address={address}"
        req = urllib.request.Request(url, headers={"X-Internal": "1"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return _json.loads(resp.read().decode()).get("vesting", [])
    except Exception:
        return []

@app.get("/api/wallet/extrato_vesting")
async def wallet_extrato_vesting(address: str = Query(...)):
    """Endpoint interno — retorna apenas dados de vesting (miner + plgg) para merge em outros nós."""
    try:
        txs = await asyncio.to_thread(plegma_db.buscar_vesting_por_address, address)
    except Exception:
        txs = []
    return {"address": address, "vesting": txs}

@app.get("/api/wallet/extrato")
async def wallet_extrato(address: str = Query(...), filtro: str = Query(default="")):
    try:
        txs = await asyncio.to_thread(plegma_db.buscar_transacoes_por_address, address)
    except Exception:
        txs = []

    # Se não estamos no nó mestre e não há dados de vesting locais,
    # buscá-los no EUR e fundir com as transações locais
    my_ip = _get_my_ip()
    if "213.199.42.88" not in my_ip:
        tem_vesting = any(
            (tx.get("node_type") or "").upper() in ("GENESIS", "VALIDATOR", "PROVER")
            for tx in txs
        )
        if not tem_vesting:
            vesting_master = await asyncio.to_thread(_buscar_vesting_master, address)
            txs = txs + vesting_master
            txs.sort(key=lambda x: x.get("timestamp", 0), reverse=True)

    # Mapa filtro → node_types aceites
    _filtro_map = {
        "GENESIS"          : {"GENESIS"},
        "PLG-G"            : {"GENESIS"},
        "MINERADO"         : {"VALIDATOR", "PROVER"},
        "ENVIADO"          : {"TRANSFER"},
        "RECEBIDO"         : {"TRANSFER"},
        "VESTING_LIBERADO" : {"VESTING_LIBERADO"},
    }
    tipos_aceites = _filtro_map.get(filtro.upper(), None) if filtro else None

    extrato = []
    for tx_d in txs:
        node_type = (tx_d.get("node_type") or "").upper()

        if tipos_aceites and node_type not in tipos_aceites:
            if filtro.upper() == "ENVIADO"  and not (node_type == "TRANSFER" and tx_d.get("de") == address):
                continue
            if filtro.upper() == "RECEBIDO" and not (node_type == "TRANSFER" and tx_d.get("para") == address):
                continue
            if filtro.upper() not in ("ENVIADO", "RECEBIDO"):
                continue

        extrato.append({
            "hash"         : tx_d.get("tx_hash", ""),
            "de"           : tx_d.get("de",   tx_d.get("sender",   "")),
            "para"         : tx_d.get("para", tx_d.get("receiver", "")),
            "amount"       : tx_d.get("amount", 0),
            "status"       : tx_d.get("status", "confirmada"),
            "timestamp"    : tx_d.get("timestamp", ""),
            "node_type"    : node_type,
            "fonte"        : tx_d.get("fonte", ""),
            "release_date" : tx_d.get("release_date", ""),
            "usdt_pago"    : tx_d.get("usdt_pago", 0),
            "node_id"      : tx_d.get("node_id", ""),
            "categoria"    : tx_d.get("categoria", ""),
        })
    return {"address": address, "transacoes": extrato, "total": len(extrato)}

@app.get("/api/wallet/seed-backup")
async def wallet_seed_backup_get(seed_hash: str = Query(...)):
    async with _seed_backups_lock:
        entry = _seed_backups.get(seed_hash)
    if entry:
        return {"ok": True, "anchor_id": entry["anchor_id"], "plg_address": entry["plg_address"],
                "created_at": entry["created_at"], "payload": entry.get("payload")}

    # Fallback: consultar outros nós da rede antes de retornar 404
    _PEER_NODES = [
        "http://213.199.42.88:8080",
        "http://209.126.7.120:8080",
        "http://217.217.251.206:8080",
        "http://82.197.70.189:8080",
    ]
    import socket, urllib.request
    my_ip = socket.gethostbyname(socket.gethostname())
    confirmations = []
    for peer_base in _PEER_NODES:
        peer_ip = peer_base.split("//")[1].split(":")[0]
        if peer_ip == my_ip or peer_ip == "127.0.0.1":
            continue
        try:
            url = f"{peer_base}/api/wallet/seed-backup?seed_hash={seed_hash}"
            req = urllib.request.Request(url, headers={"X-Peer-Query": "1"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode())
                    if data.get("ok"):
                        confirmations.append(data)
        except Exception:
            pass

    if len(confirmations) >= 2:
        # Consenso: 2+ servidores confirmam a seed — retornar e cache local
        found = confirmations[0]
        async with _seed_backups_lock:
            _seed_backups[seed_hash] = {
                "anchor_id":   found["anchor_id"],
                "plg_address": found["plg_address"],
                "seed_hash":   seed_hash,
                "created_at":  found["created_at"],
                "payload":     found.get("payload"),
            }
        _log.info(f"[SEED] Fallback: seed {seed_hash[:16]}… encontrada em {len(confirmations)} peers")
        return {"ok": True, **found}
    elif len(confirmations) == 1:
        _log.info(f"[SEED] Fallback parcial: apenas 1 peer confirmou seed {seed_hash[:16]}… — retornando com aviso")
        return {"ok": True, "warning": "confirmacao_parcial", **confirmations[0]}

    return _err("Backup nao encontrado em nenhum servidor da rede.", 404)

@app.get("/api/miner/status")
async def miner_status(address: str = Query(...)):
    blocos_minerados = blocos_aceitos = 0
    for tx_hash, tx in dag.transactions.items():
        tx_d = tx if isinstance(tx, dict) else (tx.to_dict() if hasattr(tx, 'to_dict') else {})
        minerador = tx_d.get("minerador", tx_d.get("miner", tx_d.get("de", "")))
        if minerador == address:
            blocos_minerados += 1
            if tx_d.get("status", "aceita") == "aceita":
                blocos_aceitos += 1
    taxa = (blocos_aceitos / blocos_minerados * 100) if blocos_minerados > 0 else 0.0
    try:
        boost = (await asyncio.to_thread(check_priority, address)).get("boost", 1.0)
    except Exception:
        boost = 1.0
    return {
        "address": address, "blocos_minerados": blocos_minerados, "blocos_aceitos": blocos_aceitos,
        "taxa_aprovacao_pct": round(taxa, 2), "boost_plgg": boost, "estado": _miner_states.get(address, "running"),
    }

@app.get("/api/auth/status")
async def auth_status(nonce: str = Query(...)):
    async with _verified_challenges_lock:
        entry = _verified_challenges.get(nonce)
        if entry and time.time() <= entry["expires_at"]:
            del _verified_challenges[nonce]
            return {"status": "verified", "token": entry["token"], "plg_address": entry["address"], "address": entry["address"]}
        elif entry:
            del _verified_challenges[nonce]
            return {"status": "expired"}
    return {"status": "pendente"}

@app.get("/api/auth/challenge")
async def auth_challenge(request: Request):
    ip = _get_ip(request)
    if not await _check_rl_challenge(ip):
        return _err("Muitas requisições. Aguarde 60 segundos.", 429)
    ts_now = int(time.time())
    nonce  = _b3_hash(f"{ip}{time.time_ns()}".encode())[:32]
    expires_at     = ts_now + 300
    challenge_data = f"SYS_AUTH_{nonce}_{ts_now}"
    _challenges[nonce] = {"challenge_data": challenge_data, "expires_at": expires_at, "address": None}
    message = f"plegma://auth?nonce={nonce}&data={challenge_data}&callback=https://api.plegmadag.com/api/auth/verify"
    return {"nonce": nonce, "message": message, "expires_at": expires_at}

@app.get("/api/social/posts")
async def social_posts(limit: int = Query(20), author: Optional[str] = Query(None)):
    posts = await asyncio.to_thread(social_db.listar_posts, limit, author=author)
    return {"posts": posts, "total": len(posts)}

@app.get("/api/social/profile")
async def social_profile_get(plg: str = Query(...)):
    perfil = await asyncio.to_thread(social_db.obter_perfil, plg.strip())
    if perfil is None:
        return _err("perfil_nao_encontrado", 404)
    return perfil

@app.get("/api/rede/feed")
async def rede_feed(limite: int = Query(20)):
    limite = min(max(limite, 1), 100)
    feed   = []
    def _fetch_dag_feed():
        with plegma_db.get_connection() as c:
            return c.execute(
                "SELECT tx_hash, sender, receiver, amount, timestamp FROM transactions ORDER BY timestamp DESC LIMIT ?",
                (limite,)
            ).fetchall()
    for r in await asyncio.to_thread(_fetch_dag_feed):
        feed.append({"tipo": "PLG", "token": "PLG",
                     "de": (r["sender"] or "")[:8] + "…", "para": (r["receiver"] or "")[:8] + "…",
                     "amount": r["amount"], "hash": (r["tx_hash"] or "")[:16], "ts": r["timestamp"]})
    def _fetch_plgg_feed():
        with plegma_db.get_connection() as c:
            return c.execute(
                "SELECT plg_address, amount, purchase_date, status FROM plgg_vesting ORDER BY purchase_date DESC LIMIT ?",
                (limite,)
            ).fetchall()
    for r in await asyncio.to_thread(_fetch_plgg_feed):
        addr = r["plg_address"] or ""
        feed.append({"tipo": "PLG-G", "token": "PLG-G",
                     "addr": addr[:8] + "…" + addr[-6:],
                     "amount": r["amount"], "ts": int(r["purchase_date"]), "status": r["status"]})
    feed.sort(key=lambda x: x.get("ts", 0), reverse=True)
    return {"feed": feed[:limite], "total": len(feed)}

@app.get("/api/fundacao/aprovadas")
async def fundacao_aprovadas():
    """Endpoint público — lista instituições aprovadas (campos públicos, sem dados privados)."""
    try:
        lista = await asyncio.to_thread(plegma_db.listar_fundacao_aprovadas)
        return {"instituicoes": lista}
    except Exception as e:
        return _err(str(e), 500)

@app.get("/api/fundacao/verificar")
async def fundacao_verificar(carteira: str = Query(...)):
    def _check():
        return plegma_db.carteira_fundacao_aprovada(carteira)
    reg = await asyncio.to_thread(_check)
    if reg:
        return {"aprovada": True, "hash_inscricao": reg["hash_inscricao"],
                "carteira_plg": reg["carteira_plg"], "aprovado_em": reg["aprovado_em"]}
    return {"aprovada": False}

# ── AUTENTICAÇÃO ADMIN VIA QR + DILITHIUM3 ────────────────────────────────────

@app.get("/api/admin/auth/challenge")
async def admin_auth_challenge():
    ts    = int(time.time())
    nonce = _b3_hash(f"ADMIN_NONCE:{FOUNDER_ADDRESS}:{ts}".encode())
    await asyncio.to_thread(plegma_db.salvar_estado, f"admin_nonce:{nonce}",
                            {"expires_at": ts + ADMIN_NONCE_TTL, "used": False})
    qr_data = f"plegma://auth?nonce={nonce}&role=admin"
    return {"nonce": nonce, "qr_data": qr_data, "expires_in": ADMIN_NONCE_TTL}

@app.get("/api/admin/auth/qr")
async def admin_auth_qr(nonce: str = Query(...)):
    qr_data = f"plegma://auth?nonce={nonce}&role=admin"
    try:
        import io, qrcode
        qr = qrcode.QRCode(version=None,
                           error_correction=qrcode.constants.ERROR_CORRECT_M,
                           box_size=1, border=2)
        qr.add_data(qr_data)
        qr.make(fit=True)
        matrix = qr.get_matrix()
        n    = len(matrix)
        cell = 200 / n
        rects = "".join(
            f'<rect x="{x*cell:.1f}" y="{y*cell:.1f}" width="{cell:.1f}" height="{cell:.1f}" fill="#00f2ff"/>'
            for y, row in enumerate(matrix) for x, val in enumerate(row) if val
        )
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200"'
               f' style="background:#0d0d14;border-radius:8px">{rects}</svg>')
        return Response(content=svg, media_type="image/svg+xml",
                        headers={"Cache-Control": "no-store"})
    except ImportError:
        # Fallback: SVG com o texto do nonce (instalar qrcode para QR real)
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200"'
               f' style="background:#0d0d14;border-radius:8px">'
               f'<text x="100" y="100" text-anchor="middle" fill="#00f2ff"'
               f' font-size="8" font-family="monospace">'
               f'{nonce[:16]}...</text></svg>')
        return Response(content=svg, media_type="image/svg+xml",
                        headers={"Cache-Control": "no-store"})

@app.post("/api/admin/auth/verify")
async def admin_auth_verify(request: Request):
    ip = _get_ip(request)
    allowed, retry_after = await _check_auth_lockout(ip)
    if not allowed:
        return _err(f"Demasiadas tentativas. Aguarde {retry_after}s.", 429)
    dados, err = await _parse_body(request)
    if err:
        await _record_auth_attempt(ip, False)
        return err
    address   = str(dados.get("address", "")).strip()
    nonce     = str(dados.get("nonce", "")).strip()
    signature = str(dados.get("signature", "")).strip()
    pubkey    = str(dados.get("pubkey", "")).strip()

    if address != FOUNDER_ADDRESS:
        await _record_auth_attempt(ip, False)
        return _err("Endereço não autorizado.", 403)

    nonce_data = await asyncio.to_thread(plegma_db.carregar_estado, f"admin_nonce:{nonce}", None)
    if not nonce_data:
        await _record_auth_attempt(ip, False)
        return _err("Nonce inválido ou expirado.", 403)
    if nonce_data.get("used", False):
        await _record_auth_attempt(ip, False)
        return _err("Nonce já utilizado.", 403)
    if nonce_data.get("expires_at", 0) < time.time():
        await _record_auth_attempt(ip, False)
        return _err("Nonce expirado.", 403)

    if pubkey:
        ok, motivo = await asyncio.to_thread(
            verificar_tx, address, pubkey, signature, nonce
        )
        if not ok:
            await _record_auth_attempt(ip, False)
            return _err(f"Assinatura inválida: {motivo}", 403)

    # Marcar nonce como usado
    nonce_data["used"] = True
    await asyncio.to_thread(plegma_db.salvar_estado, f"admin_nonce:{nonce}", nonce_data)

    # Emitir session token
    ts    = int(time.time())
    token = _b3_hash(f"ADMIN_SESSION:{nonce}:{FOUNDER_ADDRESS}:{ts}".encode())
    await asyncio.to_thread(plegma_db.salvar_estado, f"admin_session:{token}",
                            {"address": address, "created_at": ts,
                             "expires_at": ts + ADMIN_SESSION_TTL})
    await asyncio.to_thread(plegma_db.salvar_estado, f"admin_nonce_result:{nonce}",
                            {"token": token})
    await _record_auth_attempt(ip, True)
    return {"status": "autenticado", "token": token, "expires_in": ADMIN_SESSION_TTL}

@app.get("/api/admin/auth/status")
async def admin_auth_status(nonce: str = Query(...)):
    result = await asyncio.to_thread(plegma_db.carregar_estado,
                                     f"admin_nonce_result:{nonce}", None)
    if result and result.get("token"):
        return {"autenticado": True, "token": result["token"]}
    return {"autenticado": False}

@app.post("/api/admin/auth/password")
async def admin_auth_password(request: Request):
    ip = _get_ip(request)
    allowed, retry_after = await _check_auth_lockout(ip)
    if not allowed:
        return _err(f"Demasiadas tentativas. Aguarde {retry_after}s.", 429)
    dados, err = await _parse_body(request)
    if err:
        await _record_auth_attempt(ip, False)
        return err
    senha = str(dados.get("password", "")).strip()
    if not senha:
        await _record_auth_attempt(ip, False)
        return _err("Senha obrigatória.", 400)
    stored_hash = await asyncio.to_thread(plegma_db.carregar_estado, "admin_password_hash", None)
    if not stored_hash or _b3_hash(senha.encode()) != stored_hash:
        await _record_auth_attempt(ip, False)
        return _err("Senha incorreta.", 403)
    ts    = int(time.time())
    token = _b3_hash(f"ADMIN_SESSION:PWD:{FOUNDER_ADDRESS}:{ts}".encode())
    await asyncio.to_thread(plegma_db.salvar_estado, f"admin_session:{token}",
                            {"address": FOUNDER_ADDRESS, "created_at": ts,
                             "expires_at": ts + ADMIN_SESSION_TTL})
    await _record_auth_attempt(ip, True)
    return {"token": token, "expires_in": ADMIN_SESSION_TTL}

@app.get("/api/admin/auth/pending")
async def admin_auth_pending():
    current = await asyncio.to_thread(plegma_db.carregar_estado, "admin_pending_current", None)
    if not current or current.get("expires_at", 0) < time.time():
        return {"pending": False}
    nonce      = current.get("nonce", "")
    nonce_data = await asyncio.to_thread(plegma_db.carregar_estado, f"admin_nonce:{nonce}", None)
    if not nonce_data or nonce_data.get("used", False):
        return {"pending": False}
    return {"pending": True, "nonce": nonce}

# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/admin/downloads")
async def admin_downloads(admin_key: Optional[str] = Query(None)):
    if not await asyncio.to_thread(_check_admin, admin_key or ""):
        return _err("Acesso não autorizado.", 403)
    return {"status": "ok", "acesso": "mestre"}

@app.get("/api/transactions")
async def transactions(limit: int = Query(50)):
    limit = min(limit, 200)
    def _fetch():
        with plegma_db.get_connection() as c:
            rows = c.execute(
                "SELECT tx_hash, sender, receiver, amount, node_type, zk_proof_size, timestamp, "
                "COALESCE(zk_proof_hash, '') AS zk_proof_hash, "
                "COALESCE(aerarium_amount, 0) AS aerarium_amount, "
                "COALESCE(parents, '[]') AS parents "
                "FROM transactions ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]
    try:
        txs = await asyncio.to_thread(_fetch)
        return {"transactions": txs, "total": len(txs)}
    except Exception as e:
        return _err(str(e), 500)

@app.get("/api/fundacao/inscricoes")
async def fundacao_inscricoes(admin_key: Optional[str] = Query(None)):
    if not await asyncio.to_thread(_check_admin, admin_key or ""):
        return _err("Acesso não autorizado.", 403)
    def _fetch():
        with plegma_db.get_connection() as c:
            rows = c.execute(
                "SELECT id, hash_inscricao, carteira_plg, created_at, status, aprovado_em, "
                "nome_projeto, segmento, localizacao, descricao, responsavel, tempo_atuacao, "
                "instagram, facebook, youtube, tiktok, site, link_video, plg_address_submitter "
                "FROM fundacao_registros ORDER BY created_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]
    try:
        return {"inscricoes": await asyncio.to_thread(_fetch)}
    except Exception as e:
        return _err(str(e), 500)

@app.get("/api/genesis/socios")
async def genesis_socios():
    def _fetch():
        with plegma_db.get_connection() as c:
            rows = c.execute(
                "SELECT plg_address, genesis_balance FROM plgg_balances WHERE genesis_balance > 0 ORDER BY genesis_balance DESC"
            ).fetchall()
            return [dict(r) for r in rows]
    try:
        rows = await asyncio.to_thread(_fetch)
        socios = []
        for r in rows:
            addr = r["plg_address"]
            socios.append({
                "plg_address": addr,
                "genesis_balance": r["genesis_balance"],
                "is_genesis": await asyncio.to_thread(plegma_db.is_socio_genesis, addr),
            })
        return {"socios": socios}
    except Exception as e:
        return _err(str(e), 500)

# =============================================================================
# POST endpoints
# =============================================================================

async def _parse_body(request: Request):
    """Lê e valida o body JSON com limite de 64KB."""
    body = await request.body()
    if len(body) > 65_536:
        return None, _err("Corpo da requisicao excede limite de 64 KB.", 413)
    if not body:
        body = b"{}"
    try:
        dados = json.loads(body.decode("utf-8"))
        if not isinstance(dados, dict):
            return None, _err("Body deve ser JSON Object.", 400)
        return dados, None
    except Exception:
        return None, _err("JSON invalido.", 400)

@app.post("/api/genesis/registrar")
async def genesis_registrar(request: Request):
    dados, err = await _parse_body(request)
    if err: return err
    if not dados.get("plg_address") or not dados.get("usdt_amount"):
        return _err("Campos: plg_address, usdt_amount")
    addr = str(dados["plg_address"])
    if len(addr) > 128 or not re.fullmatch(r'[A-Za-z0-9_\-]{8,128}', addr):
        return _err("Endereço inválido.")
    evm_addr = str(dados.get("evm_address", "")).lower().strip()
    if evm_addr and not re.fullmatch(r'0x[0-9a-f]{40}', evm_addr):
        return _err("evm_address inválido — esperado 0x + 40 hex.")
    result = await asyncio.to_thread(
        genesis_contract.registrar_intencao, addr, float(dados["usdt_amount"]), evm_addr
    )
    return _ok(result, 201)

@app.post("/api/genesis/ancorar")
async def genesis_ancorar(request: Request):
    dados, err = await _parse_body(request)
    if err: return err
    for campo in ("ref_id", "tx_hash", "evm_address"):
        if not dados.get(campo):
            return _err(f"Campo obrigatório: {campo}")
    tx_hash = str(dados["tx_hash"]).lower().strip()
    if not re.fullmatch(r'0x[0-9a-f]{64}', tx_hash):
        return _err("tx_hash inválido — esperado 0x + 64 hex.")
    evm_addr = str(dados["evm_address"]).lower().strip()
    if not re.fullmatch(r'0x[0-9a-f]{40}', evm_addr):
        return _err("evm_address inválido — esperado 0x + 40 hex.")
    result = await asyncio.to_thread(
        genesis_contract.ancorar_tx_polygon,
        str(dados["ref_id"]), tx_hash, evm_addr
    )
    if result.get("erro"):
        return _err(result["erro"], 409)
    return _ok(result)

@app.post("/api/genesis/transferir")
async def genesis_transferir(request: Request):
    dados, err = await _parse_body(request)
    if err: return err
    for c in ["de", "para", "amount", "nonce"]:
        if not dados.get(c): return _err(f"Falta {c}")
    if dados["de"] == dados["para"]: return _err("Auto-transferencia proibida.")
    nonce_str = str(dados["nonce"]).lower()
    if len(nonce_str) != 64 or not all(c in '0123456789abcdef' for c in nonce_str):
        return _err("Nonce invalido.")
    if not await _registrar_nonce(nonce_str): return _err("Replay detectado.", 409)
    result = await asyncio.to_thread(
        genesis_contract.transferir_plgg,
        dados["de"], dados["para"], float(dados["amount"]),
        dados.get("confirmado", False),
        float(dados["preco_unitario"]) if dados.get("preco_unitario") else None,
        dados.get("signature"), dados.get("public_key")
    )
    return result

@app.post("/api/genesis/activate_governance")
async def genesis_activate_governance():
    return await asyncio.to_thread(genesis_contract.activate_governance)

@app.post("/api/genesis/liquidity_injection")
async def genesis_liquidity_injection():
    return await asyncio.to_thread(genesis_contract.liquidity_injection)

@app.post("/api/genesis/configurar")
async def genesis_configurar(request: Request):
    dados, err = await _parse_body(request)
    if err: return err
    if not await asyncio.to_thread(_check_admin, dados.get("admin_key", "")):
        return _err("Acesso não autorizado.", 403)
    if not dados.get("carteira"): return _err("Campo carteira obrigatorio.")
    await asyncio.to_thread(monitor_pagamentos.configurar, dados["carteira"])
    await asyncio.to_thread(monitor_pagamentos.iniciar)
    return {"status": "Monitor iniciado.", "carteira": dados["carteira"]}

@app.post("/api/timestamp/registar")
async def timestamp_registar(request: Request):
    """
    Regista hash de documento na DAG como transação TIMESTAMP.
    Chamado pelo serviço Plegma Cartório após confirmação de pagamento.
    Cria vértice real na DAG com node_type=TIMESTAMP e zk_proof_hash=doc_hash.
    Requer admin_key para autorização (chamada servidor-para-servidor).
    """
    dados, err = await _parse_body(request)
    if err: return err

    # Autorização: aceita chamada de localhost OU service_key configurada
    req_ip      = _get_ip(request)
    service_key = os.environ.get("CARTORIO_SERVICE_KEY", "")
    req_key     = str(dados.get("admin_key", dados.get("service_key", "")))
    is_local    = req_ip in ("127.0.0.1", "::1", "localhost")
    is_auth     = is_local or (service_key and req_key == service_key)
    if not is_auth:
        return _err("Acesso não autorizado.", 403)

    doc_hash    = str(dados.get("doc_hash", "")).strip()
    zk_proof    = str(dados.get("zk_proof", "")).strip()
    user_wallet = str(dados.get("user_wallet", "")).strip()
    payment_tx  = str(dados.get("payment_tx", "")).strip()
    cartorio_w  = str(dados.get("cartorio_wallet", "CARTORIO")).strip()

    if not doc_hash or len(doc_hash) < 32:
        return _err("doc_hash inválido.")

    ts_now     = time.time()
    # tx_hash determinístico: BLAKE3(TIMESTAMP:doc_hash:cartorio:ts)
    tx_hash_ts = _b3_hash(f"TIMESTAMP:{doc_hash}:{cartorio_w}:{ts_now}".encode())
    # zk_proof_hash encadeia doc_hash + payment_tx — prova de existência
    zk_hash_ts = _b3_hash(f"{doc_hash}:{payment_tx}".encode()) if payment_tx else _b3_hash(doc_hash.encode())

    parents_tips = list(dag.tips)[:2]
    _ta_novo     = dag._total_aceitas + 1

    def _write_timestamp(conn,
                         _txh=tx_hash_ts, _cw=cartorio_w, _uw=user_wallet,
                         _zkh=zk_hash_ts, _dh=doc_hash, _zk=zk_proof,
                         _par=parents_tips, _ts=ts_now, _ta=_ta_novo):
        conn.execute(
            """INSERT OR IGNORE INTO transactions
               (tx_hash, sender, receiver, amount, parents, timestamp, signature,
                zk_proof_size, node_type, aerarium_amount, zk_proof_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (_txh, _cw, _uw or _cw, 0.0, json.dumps(_par), int(_ts),
             _dh, len(_zk), "TIMESTAMP", 0.0, _zkh)
        )
        conn.execute(
            "INSERT INTO network_state (key, value) VALUES ('total_aceitas', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(_ta),)
        )

    bkey = _b3_hash(f"timestamp:{tx_hash_ts}".encode())
    await _enqueue(_write_timestamp, bkey)

    # Actualiza topologia DAG em memória
    async with _dag_topo_lock:
        _update_topology_memory(tx_hash_ts, parents_tips)
        dag.transactions[tx_hash_ts] = {
            "tx_hash"      : tx_hash_ts,
            "sender"       : cartorio_w,
            "receiver"     : user_wallet or cartorio_w,
            "amount"       : 0.0,
            "parents"      : parents_tips,
            "timestamp"    : int(ts_now),
            "node_type"    : "TIMESTAMP",
            "zk_proof_hash": zk_hash_ts,
            "aerarium_amount": 0.0,
        }
    dag._total_aceitas = _ta_novo

    def _write_ts_tips(conn, _tips=list(dag.tips)):
        conn.execute("DELETE FROM tips")
        for th in _tips:
            conn.execute("INSERT OR IGNORE INTO tips (tx_hash) VALUES (?)", (th,))
    await _enqueue(_write_ts_tips, f"tips_{bkey}")

    # Propaga para todos os peers (gossip)
    gossip.broadcast_vertice({
        "tx_hash"        : tx_hash_ts,
        "sender"         : cartorio_w,
        "receiver"       : user_wallet or cartorio_w,
        "amount"         : 0.0,
        "parents"        : parents_tips,
        "timestamp"      : int(ts_now),
        "node_type"      : "TIMESTAMP",
        "zk_proof_hash"  : zk_hash_ts,
        "aerarium_amount": 0.0,
        "signature"      : doc_hash,   # fingerprint do documento como "assinatura"
        "zk_proof_size"  : len(zk_proof),
    })

    return _ok({
        "status"        : "TIMESTAMP_REGISTADO",
        "tx_hash"       : tx_hash_ts,
        "doc_hash"      : doc_hash,
        "zk_proof_hash" : zk_hash_ts,
        "parents"       : parents_tips,
        "timestamp"     : int(ts_now),
        "network"       : "plegmadag-mainnet",
    }, 201)


@app.post("/api/node/heartbeat")
async def node_heartbeat(request: Request):
    dados, err = await _parse_body(request)
    if err: return err
    ip = _get_ip(request)
    result = await asyncio.to_thread(
        network_phase.registrar_heartbeat,
        dados.get("node_id", ""), ip,
        dados.get("metadata", {}),
        dados.get("public_key", ""),
        dados.get("signature", "")
    )
    _status = result.pop("code", 200) if not result.get("ok", True) else 200
    return _ok(result, _status)

@app.post("/api/rede/ativar")
async def rede_ativar(request: Request):
    dados, err = await _parse_body(request)
    if err: return err
    chave_ok = await asyncio.to_thread(plegma_db.carregar_estado, "admin_key", None)
    if not chave_ok or dados.get("admin_key", "") != chave_ok:
        return _err("admin_key inválida.", 403)
    return await asyncio.to_thread(network_phase.ativar_genesis, True)

@app.get("/api/pending_txs")
async def pending_txs(limite: int = Query(default=10, ge=1, le=50)):
    """Lista transações P2P reais (sender≠receiver) ainda não validadas por minerador.
    Usada pelo miner_engine e por futuros APKs para selecionar tx a provar com ZK."""
    with plegma_db.get_connection() as _conn:
        rows = _conn.execute(
            """SELECT t.tx_hash, t.sender, t.receiver, t.amount, t.node_type, t.timestamp
               FROM transactions t
               WHERE t.sender != t.receiver
                 AND t.node_type IN ('TRANSFER', 'PLGG_TRANSFER')
                 AND t.tx_hash NOT IN (SELECT ref_tx_hash FROM mine_validated_txs)
               ORDER BY t.timestamp DESC LIMIT ?""",
            (limite,)
        ).fetchall()
    return _ok({"pending": [dict(r) for r in rows], "total": len(rows)})

@app.post("/api/mine")
async def mine(request: Request):
    dados, err = await _parse_body(request)
    if err: return err
    # Rate limit persistente: máx 1 reward por 24h por node_id (in-memory + DB)
    _nid_rl  = str(dados.get("node_id", dados.get("sender", "unknown")))
    _now_rl  = time.time()
    _rl_key  = f"mine_last_ts:{_nid_rl}"
    # Verificar in-memory primeiro (previne race condition em concurrent requests)
    _mem_ts  = _mine_last_ts.get(_nid_rl, 0.0)
    _db_ts   = float(await asyncio.to_thread(plegma_db.carregar_estado, _rl_key, 0.0) or 0.0)
    _last_ts = max(_mem_ts, _db_ts)   # usa o mais recente
    if _now_rl - _last_ts < _MINE_COOLDOWN:
        _resta_h = int((_MINE_COOLDOWN - (_now_rl - _last_ts)) / 3600)
        _resta_m = int((_MINE_COOLDOWN - (_now_rl - _last_ts)) % 3600 / 60)
        return _err(f"Rate limit: próximo reward em {_resta_h}h {_resta_m}m.", 429)
    _mine_last_ts[_nid_rl] = _now_rl  # bloquear in-memory imediatamente
    await asyncio.to_thread(plegma_db.salvar_estado, _rl_key, _now_rl)
    if not await asyncio.to_thread(network_phase.is_transacoes_permitidas):
        fase = await asyncio.to_thread(network_phase.get_status)
        return _ok({"erro": "Rede em TESTNET — apenas faucet disponível.",
                    "fase": fase["fase"], "segundos_restantes": fase["segundos_para_launch"]}, 503)
    ausentes = [c for c in ["sender", "receiver", "amount", "signature", "public_key"]
                if not dados.get(c) and dados.get(c) != 0]
    if ausentes: return _err(f"Ausentes: {', '.join(ausentes)}")
    zk_size = int(dados.get("zk_proof_size", 0))
    if zk_size > 22 * 1024:
        return _err(f"Estatuto de Compressão violado: Prova ZK de {zk_size} bytes excede o teto de 22KB.")
    if math.isnan(dados["amount"]) or math.isinf(dados["amount"]) or dados["amount"] < 0:
        return _err("Valor amount invalido.")
    tx_mensagem = f"{dados['sender']}:{dados['receiver']}:{dados['amount']}"
    ok_sig, motivo_sig = await asyncio.to_thread(verificar_tx, dados["sender"], dados["public_key"], dados["signature"], tx_mensagem)
    if not ok_sig: return _err(f"Assinatura inválida: {motivo_sig}", 401)
    ip = _get_ip(request)
    sentinela_ok = await asyncio.to_thread(
        _sentinela.processar_transacao,
        dados["sender"], ip, "XX", dados.get("public_key", "")[:32], "MINERADOR", tx_mensagem, float(dados["amount"])
    )
    if not sentinela_ok: return _err("Transacao rejeitada pelo Sentinela.", 403)
    miner_address = dados.get("miner_address") or dados["sender"]
    priority = await asyncio.to_thread(check_priority, miner_address)
    if priority["max_mineradores"] == 0:
        return _err("Carteira sem PLG-G Genesis. Mínimo 10 PLG-G para 1 minerador ($1 USDC).", 403)
    incoming_node_id = dados.get("node_id", "")
    is_known_node = incoming_node_id and await asyncio.to_thread(
        plegma_db.node_id_ja_registado, miner_address, incoming_node_id
    )
    if not is_known_node:
        nos_ativos = await asyncio.to_thread(plegma_db.contar_mineradores_por_dono, miner_address)
        if nos_ativos >= priority["max_mineradores"]:
            return _err("Limite de mineradores atingido.", 403)
    ntype = str(dados.get("node_type", "VALIDATOR")).upper()
    G = _AERARIUM_G_VALIDATOR if ntype == "VALIDATOR" else _AERARIUM_G_PROVER
    counts = await asyncio.to_thread(plegma_db.get_node_counts)
    N = max(1, counts["validadores"] if ntype == "VALIDATOR" else (counts["nos_mineradores"] - counts["validadores"]))
    recompensa_base = round((G / N) * priority["boost"], 6)

    # ── Validação de ref_tx_hash (transação real referenciada) ───────────────────
    ref_tx_hash = str(dados.get("ref_tx_hash", "")).strip()
    if ref_tx_hash:
        # Verifica se a tx existe e é real (sender≠receiver)
        with plegma_db.get_connection() as _refconn:
            ref_row = _refconn.execute(
                "SELECT sender, receiver, amount FROM transactions "
                "WHERE tx_hash = ? AND sender != receiver "
                "AND node_type IN ('TRANSFER','PLGG_TRANSFER')",
                (ref_tx_hash,)
            ).fetchone()
        if not ref_row:
            return _err("ref_tx_hash inválido ou não é uma transação P2P real.", 400)
        if await asyncio.to_thread(plegma_db.is_tx_validada, ref_tx_hash):
            return _err("Transação já foi validada por outro minerador.", 409)
        recompensa = recompensa_base  # reward completo por validar tx real
    else:
        recompensa = recompensa_base  # reward completo — rate limit e PLG-G são a protecção

    # ── Validação criptográfica concluída — enfileira I/O, responde 202 ────────
    ts_vesting  = time.time()
    release_iso = (datetime.now() + timedelta(days=30)).isoformat()
    node_id_val = dados.get("node_id", "")
    # Chave determinística BLAKE3: ancoragem à transação validada
    bkey      = _b3_hash(f"vesting:{miner_address}:{ts_vesting}".encode())
    # Hash ZK real da prova: BLAKE3(sender:receiver:amount:ts) — determinístico
    zk_hash   = _b3_hash(f"{dados['sender']}:{dados['receiver']}:{dados['amount']}:{ts_vesting}".encode())
    # aerarium_amount = recompensa que o Aerarium distribui ao minerador por este vértice
    aerarium_amount = recompensa

    # Constrói o vértice completo para gravação na DAG
    tx_hash_mine = _b3_hash(f"mine:{dados['sender']}:{dados['receiver']}:{dados['amount']}:{ts_vesting}".encode())
    parents_tips = list(dag.tips)[:2]   # referencia os 2 tips actuais (topologia DAG)

    _ta_novo = dag._total_aceitas + 1
    def _write_mine(conn,
                    _ma=miner_address, _r=recompensa, _ri=release_iso,
                    _nt=ntype, _ni=node_id_val, _ts=ts_vesting,
                    _txh=tx_hash_mine, _zkh=zk_hash, _ae=aerarium_amount,
                    _par=parents_tips, _s=dados["sender"], _rec=dados["receiver"],
                    _amt=dados["amount"], _sig=dados.get("signature",""),
                    _zksz=dados.get("zk_proof_size", 0), _ta=_ta_novo):
        conn.execute(
            """INSERT INTO miner_vesting
               (plg_address, amount, release_date, status, node_type, pool,
                node_id, categoria, score, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (_ma, _r, _ri, "LOCKED", _nt, f"{_nt}_POOL", _ni, "", 0, _ts)
        )
        conn.execute(
            """INSERT OR IGNORE INTO transactions
               (tx_hash, sender, receiver, amount, parents, timestamp, signature,
                zk_proof_size, node_type, aerarium_amount, zk_proof_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (_txh, _s, _rec, _amt, json.dumps(_par), int(_ts),
             _sig, _zksz, _nt, _ae, _zkh)
        )
        # Actualiza contadores de rede (atomic com a tx — sem race condition)
        atual = conn.execute(
            "SELECT COALESCE(CAST(value AS REAL), 0.0) FROM network_state WHERE key = 'plg_minerado_total'"
        ).fetchone()
        novo = round((atual[0] if atual else 0.0) + _r, 6)
        conn.execute(
            "INSERT INTO network_state (key, value) VALUES ('plg_minerado_total', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(novo),)
        )
        conn.execute(
            "INSERT INTO network_state (key, value) VALUES ('total_aceitas', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(_ta),)
        )

    await _enqueue(_write_mine, bkey)

    # Marca a tx referenciada como validada (evita double-reward)
    if ref_tx_hash:
        await asyncio.to_thread(plegma_db.marcar_tx_validada, ref_tx_hash, tx_hash_mine, miner_address)

    # Actualiza topologia DAG em-memória e regista tx no dict local
    async with _dag_topo_lock:
        _update_topology_memory(tx_hash_mine, parents_tips)
        dag.transactions[tx_hash_mine] = {
            "tx_hash": tx_hash_mine, "sender": dados["sender"],
            "receiver": dados["receiver"], "amount": dados["amount"],
            "parents": parents_tips, "timestamp": int(ts_vesting),
            "signature": dados.get("signature", ""),
            "zk_proof_size": dados.get("zk_proof_size", 0),
            "node_type": ntype, "aerarium_amount": aerarium_amount,
            "zk_proof_hash": zk_hash,
        }
        tips_snapshot_mine = list(dag.tips)
    dag._total_aceitas = _ta_novo

    def _write_mine_tips(conn, _tips=tips_snapshot_mine):
        conn.execute("DELETE FROM tips")
        for th in _tips:
            conn.execute("INSERT OR IGNORE INTO tips (tx_hash) VALUES (?)", (th,))
    await _enqueue(_write_mine_tips, f"tips_{bkey}")

    # Propaga o vértice imediatamente para todos os peers
    gossip.broadcast_vertice({
        "tx_hash"        : tx_hash_mine,
        "sender"         : dados["sender"],
        "receiver"       : dados["receiver"],
        "amount"         : dados["amount"],
        "parents"        : parents_tips,
        "timestamp"      : int(ts_vesting),
        "signature"      : dados.get("signature", ""),
        "public_key"     : dados.get("public_key", ""),
        "zk_proof_size"  : dados.get("zk_proof_size", 0),
        "node_type"      : ntype,
        "aerarium_amount": aerarium_amount,
        "zk_proof_hash"  : zk_hash,
    })

    return _ok({
        "status": "Vertice aceito", "sender": dados["sender"],
        "receiver": dados["receiver"], "amount": dados["amount"],
        "tx_hash": tx_hash_mine, "zk_proof_hash": zk_hash,
        "aerarium_amount": aerarium_amount, "parents": parents_tips,
        "recompensa_minerador": recompensa, "boost": priority["boost"],
        "categoria_genesis": priority["categoria"]
    }, 202)

@app.post("/api/peer/vertex")
async def peer_vertex_post(request: Request):
    dados, err = await _parse_body(request)
    if err: return err
    if not await asyncio.to_thread(network_phase.is_transacoes_permitidas):
        return _err("Fase Zero.", 503)
    if not dados.get("tx_hash"): return _err("tx_hash ausente.")
    _ANCHOR_PEER_IPS = {"213.199.42.88", "209.126.7.120", "217.217.251.206", "82.197.70.189"}
    _is_genesis_peer = (dados.get("node_type") == "GENESIS"
                        and dados.get("sender", "").startswith("GENESIS"))
    _is_anchor_peer  = _get_ip(request) in _ANCHOR_PEER_IPS
    if not _is_genesis_peer and not _is_anchor_peer:
        if not all(dados.get(c) for c in ["sender", "public_key", "signature"]):
            return _err("Campos obrigatorios ausentes.")
        tx_mensagem = f"{dados['sender']}:{dados.get('receiver','')}:{dados.get('amount',0)}"
        ok_sig, motivo = await asyncio.to_thread(verificar_tx, dados["sender"], dados["public_key"], dados["signature"], tx_mensagem)
        if not ok_sig: return _err(f"Rejeitado: {motivo}", 403)
    tx_hash = dados.get("tx_hash")
    if tx_hash not in dag.transactions:
        # ── 1. Memória: fonte imediata da verdade ─────────────────────────────
        dag.transactions[tx_hash] = dados
        async with _dag_topo_lock:
            _update_topology_memory(tx_hash, dados.get("parents", []))
            tips_snapshot = list(dag.tips)  # captura atómica para persistência

        # ── 2. SQLite: queued para commit em batch ────────────────────────────
        ts_now = time.time()
        bkey   = _b3_hash(f"vertex:{tx_hash}:{ts_now}".encode())

        # zk_proof_hash determinístico: BLAKE3(tx_hash:sender:receiver:amount)
        _zk_hash_peer = _b3_hash(f"{dados.get('tx_hash','')}:{dados.get('sender','')}:{dados.get('receiver','')}:{dados.get('amount',0)}".encode())

        def _write_tx(conn, _d=dados, _zkh=_zk_hash_peer):
            conn.execute(
                """INSERT OR REPLACE INTO transactions
                   (tx_hash, sender, receiver, amount, parents, timestamp,
                    signature, zk_proof_size, node_type, aerarium_amount, zk_proof_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (_d["tx_hash"], _d.get("sender", ""), _d.get("receiver", ""),
                 _d.get("amount", 0.0), json.dumps(_d.get("parents", [])),
                 _d.get("timestamp", 0), _d.get("signature", ""),
                 _d.get("zk_proof_size", 0), _d.get("node_type", ""),
                 _d.get("aerarium_amount", 0.0), _zkh)
            )

        def _write_tips(conn, _tips=tips_snapshot):
            conn.execute("DELETE FROM tips")
            for th in _tips:
                conn.execute("INSERT OR IGNORE INTO tips (tx_hash) VALUES (?)", (th,))

        await _enqueue(_write_tx,   bkey)
        await _enqueue(_write_tips, "tips_" + bkey)

    return _ok({"status": "aceito"}, 201)

@app.post("/api/wallet/transferir")
async def wallet_transferir(request: Request):
    ip = _get_ip(request)
    if not await _check_rl_generic("transferir_ip", ip, 30, 60):
        return _err("Muitas transferencias deste IP. Aguarde 60s.", 429)
    dados, err = await _parse_body(request)
    if err: return err
    for c in ["de", "para", "amount", "signature", "public_key", "nonce"]:
        if dados.get(c) is None or str(dados.get(c)).strip() == "":
            return _err(f"Falta {c}")
    if not await _check_rl_generic("transferir_plg", str(dados["de"]), 10, 60):
        return _err("Muitas transferencias desta carteira. Aguarde 60s.", 429)
    if dados["de"] == dados["para"]: return _err("Auto-transferencia.")
    try:
        amt = float(dados["amount"])
        if math.isnan(amt) or math.isinf(amt) or amt <= 0:
            raise ValueError
    except (ValueError, TypeError):
        return _err("Campo 'amount' invalido.")
    nonce_str = str(dados["nonce"]).lower()
    if len(nonce_str) != 64 or not all(c in '0123456789abcdef' for c in nonce_str):
        return _err("Nonce invalido.")
    if not await _registrar_nonce(nonce_str): return _err("Replay detectado.", 409)

    tx_mensagem = f"{dados['de']}:{dados['para']}:{amt}"
    ok_sig, motivo_sig = await asyncio.to_thread(
        verificar_tx, dados["de"], dados["public_key"], dados["signature"], tx_mensagem
    )
    if not ok_sig: return _err(f"Assinatura invalida: {motivo_sig}", 401)

    saldo = await asyncio.to_thread(plegma_db.carregar_saldo_plg, dados["de"])
    if saldo["liberado"] < amt:
        return _err(f"Saldo insuficiente. Disponivel: {saldo['liberado']:.6f} PLG", 400)

    ts      = time.time()
    tx_hash = _b3_hash(f"TRANSFER:{dados['de']}:{dados['para']}:{amt}:{ts}".encode())
    parents = list(dag.tips)[:2]

    def _write_transfer(conn, _de=dados["de"], _para=dados["para"], _amt=amt,
                        _tx=tx_hash, _sig=dados["signature"], _ts=ts, _par=parents):
        conn.execute(
            "INSERT OR IGNORE INTO plg_transfers (tx_hash, sender, receiver, amount, timestamp, status) "
            "VALUES (?, ?, ?, ?, ?, 'confirmed')",
            (_tx, _de, _para, _amt, _ts)
        )
        conn.execute(
            """INSERT OR IGNORE INTO transactions
               (tx_hash, sender, receiver, amount, parents, timestamp, signature,
                zk_proof_size, node_type, aerarium_amount, zk_proof_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (_tx, _de, _para, _amt, json.dumps(_par), int(_ts), _sig,
             0, 'TRANSFER', _TRANSFER_AERARIUM_FEE, '')
        )

    bkey = _b3_hash(f"transfer:{tx_hash}".encode())
    await _enqueue(_write_transfer, bkey)

    async with _dag_topo_lock:
        _update_topology_memory(tx_hash, parents)

    gossip.broadcast_vertice({
        "tx_hash"      : tx_hash,
        "sender"       : dados["de"],
        "receiver"     : dados["para"],
        "amount"       : amt,
        "parents"      : parents,
        "timestamp"    : int(ts),
        "signature"    : dados["signature"],
        "public_key"   : dados["public_key"],
        "zk_proof_size": 0,
        "node_type"    : "TRANSFER",
    })

    return _ok({
        "status"  : "ok",
        "tx_hash" : tx_hash,
        "de"      : dados["de"],
        "para"    : dados["para"],
        "amount"  : amt,
        "timestamp": int(ts),
    }, 201)

@app.post("/api/wallet/seed-backup")
async def wallet_seed_backup_post(request: Request):
    ip = _get_ip(request)
    if not await _check_rl_generic("seed_backup_ip", ip, 5, 300):
        return _err("Muitas gravacoes de backup. Aguarde 5min.", 429)
    dados, err = await _parse_body(request)
    if err: return err
    plg    = str(dados.get("plg_address", "")).strip()
    s_hash = str(dados.get("seed_hash", "")).strip().lower()
    pay    = dados.get("payload", "")
    if not re.match(r'^PLG[0-9A-F]{40}$', plg) or not re.match(r'^[0-9a-f]{64}$', s_hash) or not (1024 <= len(pay) <= 65536):
        return _err("Dados invalidos ou fora das margens ZK.")
    created_at = int(time.time())
    anchor_id  = "zk_seed_" + _b3_hash(f"{plg}{s_hash}{created_at}".encode())[:16]
    def _save():
        with plegma_db.get_connection() as sc:
            sc.execute(
                "INSERT OR REPLACE INTO seed_backups (anchor_id, plg_address, seed_hash, payload, created_at) VALUES (?, ?, ?, ?, ?)",
                (anchor_id, plg, s_hash, pay, created_at)
            )
    try:
        await asyncio.to_thread(_save)
    except Exception as e:
        return _err(str(e), 500)
    async with _seed_backups_lock:
        _seed_backups[s_hash] = {"anchor_id": anchor_id, "plg_address": plg, "seed_hash": s_hash, "created_at": created_at, "payload": pay}
    await asyncio.to_thread(plegma_db.upsert_no_ativo, plg, f"WALLET_{plg}", "WALLET")
    return _ok({"ok": True, "anchor_id": anchor_id, "zk_size": len(pay), "created_at": created_at}, 201)

@app.post("/api/miner/pause")
async def miner_pause(request: Request):
    dados, err = await _parse_body(request)
    if err: return err
    if not dados.get("address"): return _err("Falta address.")
    _miner_states[dados["address"]] = "paused"
    return {"address": dados["address"], "status": "paused"}

@app.post("/api/miner/resume")
async def miner_resume(request: Request):
    dados, err = await _parse_body(request)
    if err: return err
    if not dados.get("address"): return _err("Falta address.")
    _miner_states[dados["address"]] = "running"
    return {"address": dados["address"], "status": "running"}

@app.post("/api/auth/verify")
async def auth_verify(request: Request):
    ip = _get_ip(request)
    if not await _check_rl_generic("auth_verify_ip", ip, 20, 60):
        return _err("Muitas verificacoes. Aguarde 60s.", 429)
    dados, err = await _parse_body(request)
    if err: return err
    challenge_key = dados.get("nonce") or dados.get("challenge_id")
    address = dados.get("plg_address") or dados.get("address")
    if not all([challenge_key, address]):
        return _err("Faltam campos.")
    challenge = _challenges.get(challenge_key)
    if not challenge or time.time() > challenge["expires_at"]:
        return _err("Desafio invalido/expirado.", 401)
    token = _b3_hash(f"SYS_TOKEN{address}{time.time_ns()}".encode())
    del _challenges[challenge_key]
    await asyncio.to_thread(plegma_db.salvar_sessao, address, token, 3600)
    valid_until = int(time.time()) + 3600
    async with _verified_challenges_lock:
        _verified_challenges[challenge_key] = {"token": token, "address": address, "expires_at": valid_until}
    return {"status": "autenticado", "token": token, "valid_until": valid_until, "session_token": token}

@app.post("/api/auth/validate-session")
async def auth_validate_session(request: Request):
    dados, err = await _parse_body(request)
    if err: return err
    plg = str(dados.get("plg_address", "")).strip()
    token = str(dados.get("token", "")).strip()
    if not plg or not token:
        return _err("Faltam campos.")
    valid = await asyncio.to_thread(plegma_db.validar_sessao, plg, token)
    if valid:
        return {"status": "valid", "plg_address": plg}
    return _err("Sessao invalida.", 401)

@app.post("/api/social/post")
async def social_post(request: Request):
    ip = _get_ip(request)
    if not await _check_rl_generic("social_post_ip", ip, 10, 60):
        return _err("Muitos posts. Aguarde 60s.", 429)
    dados, err = await _parse_body(request)
    if err: return err
    result = await asyncio.to_thread(social_db.criar_post, dados.get("author"), dados.get("conteudo"), dados.get("parent_id"))
    return _ok(result, 201)

@app.post("/api/social/post/apagar")
async def social_post_apagar(request: Request):
    ip = _get_ip(request)
    if not await _check_rl_generic("social_apagar_ip", ip, 30, 60):
        return _err("Muitas remocoes. Aguarde 60s.", 429)
    dados, err = await _parse_body(request)
    if err: return err
    plg = str(dados.get("author", "")).strip()
    pid = str(dados.get("post_id", "")).strip()
    if not plg or not pid: return _err("author e post_id obrigatorios.")
    resultado = await asyncio.to_thread(social_db.apagar_post, pid, plg)
    if "erro" in resultado:
        s = 403 if resultado["erro"] == "sem_permissao" else 404 if resultado["erro"] == "post_nao_encontrado" else 400
        return _ok(resultado, s)
    return resultado

@app.post("/api/social/votar")
async def social_votar(request: Request):
    ip = _get_ip(request)
    if not await _check_rl_generic("social_votar_ip", ip, 60, 60):
        return _err("Muitos votos. Aguarde 60s.", 429)
    dados, err = await _parse_body(request)
    if err: return err
    if not dados.get("voter") or str(dados.get("voter", "")).startswith("anon_"):
        return _err("autenticacao_necessaria", 401)
    return await asyncio.to_thread(social_db.votar, dados.get("post_id"), dados.get("voter"), dados.get("tipo"))

@app.post("/api/social/profile")
async def social_profile_post(request: Request):
    ip = _get_ip(request)
    if not await _check_rl_generic("social_profile_ip", ip, 5, 60):
        return _err("Muitas alteracoes de perfil. Aguarde 60s.", 429)
    dados, err = await _parse_body(request)
    if err: return err
    plg    = str(dados.get("plg_address", "")).strip()
    avatar = str(dados.get("avatar", "")).strip()
    cover  = str(dados.get("cover", "")).strip()
    bio    = str(dados.get("bio", "")).strip()
    if not plg or not avatar or not cover:
        return _err("plg_address, avatar e cover obrigatorios")
    resultado = await asyncio.to_thread(social_db.criar_perfil, plg, avatar, cover, bio)
    if "erro" in resultado:
        s = 409 if resultado["erro"] == "perfil_ja_existe" else 400
        return _ok(resultado, s)
    return _ok(resultado, 201)

@app.post("/api/labs/proposta")
async def labs_proposta(request: Request):
    ip = _get_ip(request)
    if not await _check_rl_generic("labs_proposta_ip", ip, 5, 3600):
        return _err("Muitas propostas. Aguarde 1h.", 429)
    dados, err = await _parse_body(request)
    if err: return err
    result = await asyncio.to_thread(labs_db.criar_proposta, dados.get("titulo"), dados.get("descricao", ""), dados.get("autor"))
    return _ok(result, 201)

@app.post("/api/labs/votar")
async def labs_votar(request: Request):
    ip = _get_ip(request)
    if not await _check_rl_generic("labs_votar_ip", ip, 60, 60):
        return _err("Muitos votos. Aguarde 60s.", 429)
    dados, err = await _parse_body(request)
    if err: return err
    return await asyncio.to_thread(labs_db.votar_proposta, dados.get("proposta_id"), dados.get("voter"), dados.get("voto"))

@app.post("/api/fundacao/inscricao")
async def fundacao_inscricao(request: Request):
    dados, err = await _parse_body(request)
    if err: return err
    # Honeypot anti-bot
    if dados.get("website_url", "") != "":
        return _ok({"status": "ok", "id": 0}, 201)
    ip = _get_ip(request)
    if not _check_rl_fundacao(ip): return _err("Muitas tentativas.", 429)
    campos_obrig = ["segmento", "nome_projeto", "tempo_atuacao", "localizacao", "descricao", "carteira_plg", "responsavel", "link_video"]
    if any(not str(dados.get(c, "")).strip() for c in campos_obrig):
        return _err("Campos ausentes.")
    redes = ["instagram", "facebook", "youtube", "tiktok", "site"]
    if not any(str(dados.get(r, "")).strip() for r in redes):
        return _err("Uma rede social obrigatoria.")
    entry = {k: str(dados.get(k, "")).strip()[:500] for k in dados}
    entry["ip_origem"] = ip
    entry["created_at"] = time.time()
    campos_hash = {k: v for k, v in entry.items() if k not in ("website_url", "ip_origem", "status", "created_at")}
    payload_bytes = json.dumps(campos_hash, sort_keys=True, ensure_ascii=False).encode("utf-8")
    hash_inscricao = _b3_hash(payload_bytes)
    entry["hash_inscricao"] = hash_inscricao
    try:
        inscricao_id = await asyncio.to_thread(plegma_db.salvar_inscricao_fundacao, entry)
        threading.Thread(target=_notificar_inscricao_fundacao, args=(entry,), daemon=True).start()
        return _ok({"status": "ok", "id": inscricao_id, "hash_inscricao": hash_inscricao}, 201)
    except Exception:
        return _err("Erro ao registrar.", 500)

@app.post("/api/shield/download_register")
async def shield_download_register(request: Request):
    dados, err = await _parse_body(request)
    if err: return err
    try:
        log_path = os.path.join(os.path.dirname(__file__), "shield_downloads.log")
        def _write():
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"{int(time.time())}\t{str(dados.get('version',''))[:32]}\t"
                        f"{str(dados.get('platform',''))[:32]}\t{str(dados.get('plg_address',''))[:128]}\n")
        await asyncio.to_thread(_write)
    except Exception:
        pass
    return {"status": "ok", "ts": int(time.time())}

@app.post("/api/admin/fundacao/aprovar")
async def admin_fundacao_aprovar(request: Request):
    dados, err = await _parse_body(request)
    if err: return err
    if not await asyncio.to_thread(_check_admin, dados.get("admin_key", "")):
        return _err("Acesso não autorizado.", 403)
    hash_insc = str(dados.get("hash_inscricao", "")).strip()
    if not hash_insc: return _err("hash_inscricao obrigatorio.")
    ok = await asyncio.to_thread(plegma_db.aprovar_inscricao_fundacao, hash_insc)
    if ok:
        reg = await asyncio.to_thread(plegma_db.buscar_inscricao_fundacao, hash_insc)
        return {"status": "APROVADA", "carteira_plg": reg["carteira_plg"], "hash_inscricao": hash_insc}
    return _err("Hash nao encontrado ou ja processado.", 404)

@app.post("/api/admin/fundacao/rejeitar")
async def admin_fundacao_rejeitar(request: Request):
    dados, err = await _parse_body(request)
    if err: return err
    if not await asyncio.to_thread(_check_admin, dados.get("admin_key", "")):
        return _err("Acesso não autorizado.", 403)
    hash_insc = str(dados.get("hash_inscricao", "")).strip()
    if not hash_insc: return _err("hash_inscricao obrigatorio.")
    ok = await asyncio.to_thread(plegma_db.rejeitar_inscricao_fundacao, hash_insc)
    return {"status": "REJEITADA" if ok else "nao_encontrado"}

@app.post("/api/admin/fundacao/desvincular")
async def admin_fundacao_desvincular(request: Request):
    dados, err = await _parse_body(request)
    if err: return err
    if not await asyncio.to_thread(_check_admin, dados.get("admin_key", "")):
        return _err("Acesso não autorizado.", 403)
    hash_insc = str(dados.get("hash_inscricao", "")).strip()
    if not hash_insc: return _err("hash_inscricao obrigatorio.")
    ok = await asyncio.to_thread(plegma_db.desvincular_inscricao_fundacao, hash_insc)
    if ok:
        return {"status": "ok"}
    return _err("Hash nao encontrado ou nao esta APROVADA.", 404)

# =============================================================================
# Entrada
# =============================================================================
if __name__ == "__main__":
    import uvicorn
    porta = int(os.environ.get("PLEGMA_PORT", 8080))
    _log.info(f"[API] Iniciando uvicorn na porta {porta}")
    uvicorn.run("core_api:app", host="0.0.0.0", port=porta, workers=1, log_level="warning")
