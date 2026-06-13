"""
PLEGMA — Controlador de Fase da Rede V4.1 (PÓS-QUÂNTICO / HEGEMONIA BLAKE3)
=====================================
Fases:

  FASE_ZERO      → Pré-testnet (reservado, não utilizado actualmente).

  TESTNET        → Fase de pré-lançamento (encerrada — faucet desativado).
                   Mantida apenas como estado-marker até o watchdog promover a GENESIS_ATIVO.
                   Transações de valor real bloqueadas (503).

  GENESIS_ATIVO  → Lançamento Real — Transações desbloqueadas, Genesis Reserve
                   aberta, R=G/N inicia. Lock-up obrigatório de 30 dias.
                   Início: 09 MAI 2026 · 18:00 Madrid (CEST = UTC+2)

  MAINNET_PLENA  → Governança ativa (Dia 31+), pool Aerarium PLG/USDC aberta.

Ativação automática GENESIS_ATIVO:
  09 MAI 2026 · 18:00 Madrid (CEST = UTC+2) = 16:00 UTC
  Unix timestamp: 1778342400
"""

import blake3
import logging
import time
import threading
from datetime import datetime

import plegma_db

_log = logging.getLogger(__name__)

# ML-DSA-65 primeiro (FIPS 204) — compatível com o app Android (PQClean ml-dsa-65).
# Fallback: Dilithium3 Round 3 — para nós Python legados.
try:
    from dilithium_py.ml_dsa import ML_DSA_65 as _Dilithium3
    _DILITHIUM_OK = True
except ImportError:
    try:
        from dilithium_py.dilithium import Dilithium3 as _Dilithium3
        _DILITHIUM_OK = True
    except ImportError:
        _Dilithium3   = None
        _DILITHIUM_OK = False

# DagSealEngine — selo de integridade para /api/node/map
try:
    from zk_press import DagSealEngine as _ZkPressEngine
    _zk_engine  = _ZkPressEngine()
    _ZK_OK      = True
except Exception:
    _zk_engine  = None
    _ZK_OK      = False

# =============================================================================
# CONSTANTES
# =============================================================================

FASE_ZERO_START_TS   = 1775750400
FASE_ZERO_START_ISO  = "2026-04-09T16:00:00Z"
FASE_ZERO_START_BRTC = "09/04/2026 18:00 CEST (Madrid)"

GENESIS_LAUNCH_TS   = 1778515200
GENESIS_LAUNCH_ISO  = "2026-05-11T16:00:00Z"
GENESIS_LAUNCH_BRTC = "11/05/2026 18:00 CEST (Madrid)"

FASE_ZERO     = "FASE_ZERO"
TESTNET       = "TESTNET"
GENESIS_ATIVO = "GENESIS_ATIVO"
MAINNET_PLENA = "MAINNET_PLENA"

# Fases em que transações de valor real são bloqueadas
_FASES_SEM_TX = {FASE_ZERO, TESTNET}

HEARTBEAT_TTL      = 900
HASH_BUCKET_SECS   = 5

_fase_lock          = threading.Lock()
_watchdog_iniciado  = False


# =============================================================================
# CONSULTA DE FASE
# =============================================================================

def get_fase_atual() -> str:
    return plegma_db.carregar_estado("rede_fase", TESTNET)

def is_transacoes_permitidas() -> bool:
    return get_fase_atual() not in _FASES_SEM_TX

def get_status() -> dict:
    fase  = get_fase_atual()
    agora = time.time()
    secs  = max(0.0, GENESIS_LAUNCH_TS - agora)
    return {
        "fase"                  : fase,
        "modo"                  : "PRE_LAUNCH" if fase in (TESTNET, FASE_ZERO) else "LEDGER_ATIVO",
        "transacoes_ativas"     : fase not in _FASES_SEM_TX,
        "fase_zero_start_ts"    : FASE_ZERO_START_TS,
        "fase_zero_start_madrid": FASE_ZERO_START_BRTC,
        "launch_ts_utc"         : GENESIS_LAUNCH_TS,
        "launch_iso"            : GENESIS_LAUNCH_ISO,
        "launch_madrid"         : GENESIS_LAUNCH_BRTC,
        "segundos_para_launch"  : round(secs),
        "node_map"              : get_node_map(),
    }


# =============================================================================
# HEARTBEAT / NODE DISCOVERY
# =============================================================================

def registrar_heartbeat(node_id: str, ip: str, metadata: dict = None,
                         public_key_hex: str = "", signature_hex: str = "") -> dict:
    import re as _re2
    if not node_id:
        return {"ok": False, "erro": "node_id obrigatório.", "code": 400}

    meta         = metadata or {}
    meta_address = str(meta.get("plg_address", "")).strip()
    plg_valido   = bool(_re2.match(r'^PLG[0-9A-F]{40}$', meta_address))

    # Verificação Dilithium3 — tenta sempre que possível.
    # Fallback para validação por endereço PLG (TESTNET) quando bibliotecas C/Python
    # usam specs diferentes (PQClean original vs ML-DSA FIPS 204).
    sig_ok = False
    if _DILITHIUM_OK and public_key_hex and signature_hex:
        try:
            pub_key   = bytes.fromhex(public_key_hex)
            signature = bytes.fromhex(signature_hex)
            message   = node_id.encode("utf-8")
            sig_ok    = _Dilithium3.verify(pub_key, message, signature)
        except Exception:
            sig_ok = False

    if not sig_ok and not plg_valido:
        return {"ok": False, "erro": "Assinatura inválida e endereço PLG ausente.", "code": 403}

    # Rede autenticada: assinatura válida OU endereço PLG verificado (TESTNET)
    autenticado = "DILITHIUM3" if sig_ok else "PLG_ADDRESS"

    # Endereço canónico: usa plg_address da metadata (já validado acima).
    # Fallback para derivação via chave pública se assinatura Dilithium3 for válida.
    if plg_valido:
        node_address = meta_address
    elif sig_ok and public_key_hex:
        node_address = "PLG" + blake3.blake3(bytes.fromhex(public_key_hex)).hexdigest()[:40].upper()
    else:
        return {"ok": False, "erro": "Não foi possível determinar endereço do nó.", "code": 400}

    agora = time.time()
    entry = {
        "node_id"     : node_id,
        "node_address": node_address,
        "public_key"  : public_key_hex,
        "ip"          : ip,
        "ts"          : agora,
        "autenticado" : autenticado,
        "metadata"    : meta,
    }
    plegma_db.salvar_estado(f"heartbeat_{node_id}", entry)

    nos = plegma_db.carregar_estado("nos_heartbeat_list", [])
    if node_id not in nos:
        nos.append(node_id)
        plegma_db.salvar_estado("nos_heartbeat_list", nos)

    # Regista presença na tabela nos_rede — torna o nó visível no admin/console
    node_type = str(meta.get("node_type", "VALIDATOR")).upper()
    plegma_db.upsert_no_ativo(node_address, node_id, node_type)

    node_map = get_node_map()
    return {
        "ok"               : True,
        "ts"               : agora,
        "node_address"     : node_address,
        "autenticado"      : autenticado,
        "fase"             : get_fase_atual(),
        "nos_ativos"       : node_map["nos_ativos"],
        "connectivity_hash": node_map["connectivity_hash"],
    }


def get_node_map() -> dict:
    agora   = time.time()
    nos_ids = plegma_db.carregar_estado("nos_heartbeat_list", [])
    ativos  = []

    for nid in nos_ids:
        entry = plegma_db.carregar_estado(f"heartbeat_{nid}", None)
        if entry and (agora - entry.get("ts", 0)) <= HEARTBEAT_TTL:
            ativos.append({
                "node_id"     : nid,
                "node_address": entry.get("node_address", ""),
                "ip"          : entry.get("ip", ""),
                "ts"          : entry.get("ts"),
                "latencia"    : round(agora - entry["ts"], 1),
                "node_type"   : entry.get("metadata", {}).get("node_type", "UNKNOWN"),
            })

    conn_hash = _connectivity_hash([a["node_id"] for a in ativos])

    zk_proof = None
    if _ZK_OK and _zk_engine:
        try:
            proof_bytes = _zk_engine.generate_recursive_proof(conn_hash)
            zk_proof    = proof_bytes.decode("utf-8") if isinstance(proof_bytes, bytes) else proof_bytes
        except Exception:
            zk_proof = None

    return {
        "nos_ativos"       : len(ativos),
        "nos"              : ativos,
        "connectivity_hash": conn_hash,
        "zk_proof"         : zk_proof,
        "zk_engine"        : "DagSealEngine-V4.1" if _ZK_OK else "unavailable",
        "ts"               : agora,
        "fase"             : get_fase_atual(),
    }


def _connectivity_hash(node_ids: list) -> str:
    bucket = int(time.time()) // HASH_BUCKET_SECS
    raw    = "|".join(sorted(node_ids)) + f"|b={bucket}"
    return "NET_" + blake3.blake3(raw.encode()).hexdigest()[:32]


# =============================================================================
# ATIVAÇÃO — FASE_ZERO → GENESIS_ATIVO
# =============================================================================

def ativar_genesis(admin_override: bool = False) -> dict:
    with _fase_lock:
        fase_atual = get_fase_atual()
        if fase_atual not in {FASE_ZERO, TESTNET}:
            return {
                "ok"  : False,
                "fase": fase_atual,
                "msg" : f"Rede já está em fase {fase_atual}. Nenhuma alteração.",
            }

        agora  = time.time()
        ts_str = datetime.fromtimestamp(agora).strftime('%d/%m/%Y %H:%M')

        plegma_db.salvar_estado("rede_fase",           GENESIS_ATIVO)
        plegma_db.salvar_estado("genesis_launch_date", agora)
        plegma_db.salvar_estado("rede_ativa",          True)
        plegma_db.salvar_estado("genesis_ativo_ts",    agora)

        src = "ADMIN_OVERRIDE" if admin_override else "WATCHDOG_AUTOMATICO"
        _log.info(f"[FASE] ══════════════════════════════════════════════════")
        _log.info(f"[FASE]  GENESIS ATIVO — {ts_str} ({src})")
        _log.info(f"[FASE]  Transações desbloqueadas. R=G/N iniciado.")
        _log.info(f"[FASE]  Lock-up 30 dias ativo. Genesis Reserve aberta.")
        _log.info(f"[FASE] ══════════════════════════════════════════════════")

        return {
            "ok"  : True,
            "fase": GENESIS_ATIVO,
            "ts"  : agora,
            "msg" : "GENESIS_ATIVO — transações desbloqueadas, R=G/N e Genesis Reserve ativos.",
            "src" : src,
        }


# =============================================================================
# WATCHDOG — ativação automática no timestamp
# =============================================================================

def iniciar_watchdog():
    global _watchdog_iniciado
    if _watchdog_iniciado:
        return
    _watchdog_iniciado = True

    if time.time() >= GENESIS_LAUNCH_TS and get_fase_atual() in {FASE_ZERO, TESTNET}:
        ativar_genesis()
        return

    t = threading.Thread(target=_watchdog_loop, daemon=True, name="GenesisWatchdog")
    t.start()


def _watchdog_loop():
    restantes = GENESIS_LAUNCH_TS - time.time()
    _log.info(f"[FASE V4.0] Watchdog ativo → {GENESIS_LAUNCH_BRTC} "
          f"(faltam {restantes/3600:.1f}h | ts={GENESIS_LAUNCH_TS})")

    while True:
        if time.time() >= GENESIS_LAUNCH_TS:
            if get_fase_atual() in {FASE_ZERO, TESTNET}:
                ativar_genesis()
            break
        time.sleep(15)