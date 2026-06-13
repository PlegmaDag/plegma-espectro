"""
AERARIUM SWAP — Pool de Liquidez PLG/USDC V4.0 (PÓS-QUÂNTICO / HEGEMONIA BLAKE3)
================================================================================
Pool Polygon : 0xD8422d6936bE77179DC33C7C2ffceEF4c34FB183
Rede         : Polygon (MATIC)
USDC         : 0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359  (USDC nativo)

Fluxo COMPRAR (USDC → PLG):
  1. POST /pool/comprar  → ref_id + endereço da pool + PLG estimado
  2. Usuário envia USDC para POOL_ADDRESS na Polygon
  3. Monitor detecta Transfer → credita PLG ao plg_address (sem lock-up)

Fluxo VENDER (PLG → USDC):
  1. POST /pool/vender   → cria ordem PENDENTE_MANUAL
  2. Admin processa manualmente (Fase 2: chave em .env para automação)
"""

import logging
import threading
import time
import json

import plegma_db

_log = logging.getLogger(__name__)

# ── Blindagem de Oráculo Determinístico (Hard Fail) ─────────
try:
    import blake3 as _blake3
except ImportError:
    raise RuntimeError("[FALHA FATAL] Módulo blake3 ausente no Aerarium Swap.")

def _b3_hash(data: bytes) -> str:
    return _blake3.blake3(data).hexdigest()

try:
    from web3 import Web3
    _W3_DISPONIVEL = True
except ImportError:
    _W3_DISPONIVEL = False

# =============================================================================
# CONSTANTES
# =============================================================================
POOL_ADDRESS        = "0xD8422d6936bE77179DC33C7C2ffceEF4c34FB183"
POLYGON_RPC         = "https://1rpc.io/matic"
USDC_CONTRACT_ADDR  = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"
USDC_DECIMALS       = 6
INTERVALO_MONITOR_S = 60      
TOLERANCIA_USDC     = 0.05    
DUST_MINIMO         = 0.10    

POOL_PLG_ADDRESS = "PLG_POOL_AERARIUM_0x4AB8FCF05a"

USDC_ABI = json.loads(
    '[{"anonymous":false,"inputs":[{"indexed":true,"name":"from","type":"address"},'
    '{"indexed":true,"name":"to","type":"address"},{"indexed":false,"name":"value",'
    '"type":"uint256"}],"name":"Transfer","type":"event"},'
    '{"inputs":[{"name":"account","type":"address"}],"name":"balanceOf",'
    '"outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"}]'
)

_monitor_ativo = False
_lock          = threading.Lock()


# =============================================================================
# COTAÇÃO
# =============================================================================
def get_cotacao() -> dict:
    taxa          = plegma_db.carregar_estado("pool_taxa_plg_por_usdc", None)
    plg_reserva   = plegma_db.carregar_estado("pool_plg_reserva",       0.0)
    usdc_saldo    = plegma_db.carregar_estado("pool_usdc_saldo",         0.0)
    preco_inicial = plegma_db.carregar_estado("preco_inicial_plg",       None)

    return {
        "pool_address"  : POOL_ADDRESS,
        "taxa"          : taxa,
        "preco_inicial" : preco_inicial,   
        "plg_reserva"   : plg_reserva,
        "usdc_saldo"    : round(usdc_saldo, 6),
        "disponivel"    : taxa is not None and plg_reserva > 0,
        "rede"          : "Polygon",
        "usdc_contrato" : USDC_CONTRACT_ADDR,
    }


# =============================================================================
# REGISTRAR COMPRA (USDC → PLG)
# =============================================================================
def registrar_compra(plg_address: str, usdc_amount: float) -> dict:
    if not plg_address or not plg_address.startswith("PLG"):
        return {"ok": False, "erro": "Endereço PLG inválido."}

    taxa        = plegma_db.carregar_estado("pool_taxa_plg_por_usdc", None)
    plg_reserva = plegma_db.carregar_estado("pool_plg_reserva",       0.0)

    if taxa is None:
        return {"ok": False, "erro": "Pool não inicializada. Taxa não configurada pelo administrador."}
    if usdc_amount < 1.0:
        return {"ok": False, "erro": "Valor mínimo: 1.00 USDC."}

    plg_estimado = round(usdc_amount * taxa, 4)

    if plg_estimado > plg_reserva:
        return {
            "ok"  : False,
            "erro": f"PLG insuficiente na pool. Disponível: {plg_reserva:,.0f} PLG "
                    f"(máx. {plg_reserva / taxa:.2f} USDC neste momento)."
        }

    ts = time.time()
    # Determinismo absoluto V4.0 - uuid banido
    ref_id = "REF_" + _b3_hash(f"COMPRA:{plg_address}:{usdc_amount}:{ts}".encode())[:12].upper()
    
    order  = {
        "ref_id"         : ref_id,
        "tipo"           : "COMPRAR",
        "plg_address"    : plg_address,
        "polygon_address": "",
        "plg_amount"     : plg_estimado,
        "usdc_amount"    : round(usdc_amount, 6),
        "taxa"           : taxa,
        "created_at"     : ts,
        "status"         : "AGUARDANDO",
        "tx_hash_polygon": "",
    }
    plegma_db.salvar_swap_order(order)
    _log.info(f"[SWAP V4.0] Compra registrada: {ref_id[:8]}… | "
          f"{usdc_amount:.2f} USDC → {plg_estimado:,.4f} PLG → {plg_address[:20]}…")

    return {
        "ok"          : True,
        "ref_id"      : ref_id,
        "pool_address": POOL_ADDRESS,
        "plg_estimado": plg_estimado,
        "usdc_amount" : round(usdc_amount, 6),
        "taxa"        : taxa,
        "instrucao"   : (f"Envie exatamente {usdc_amount:.2f} USDC para {POOL_ADDRESS} "
                         f"na rede Polygon. Seu PLG será creditado automaticamente."),
        "expira_em_s" : 3600,
    }


# =============================================================================
# REGISTRAR VENDA (PLG → USDC)
# =============================================================================
def registrar_venda(plg_address: str, plg_amount: float, polygon_address: str) -> dict:
    if not plg_address or not plg_address.startswith("PLG"):
        return {"ok": False, "erro": "Endereço PLG inválido."}
    if not polygon_address or not polygon_address.startswith("0x") or len(polygon_address) != 42:
        return {"ok": False, "erro": "Endereço Polygon inválido."}

    taxa       = plegma_db.carregar_estado("pool_taxa_plg_por_usdc", None)
    usdc_saldo = plegma_db.carregar_estado("pool_usdc_saldo",         0.0)

    if taxa is None:
        return {"ok": False, "erro": "Pool não inicializada."}
    if plg_amount < 100:
        return {"ok": False, "erro": "Quantidade mínima para venda: 100 PLG."}

    usdc_estimado = round(plg_amount / taxa, 6)

    if usdc_estimado > usdc_saldo:
        return {
            "ok"  : False,
            "erro": f"USDC insuficiente na pool. Disponível: ${usdc_saldo:.2f} "
                    f"(máx. {usdc_saldo * taxa:,.0f} PLG neste momento)."
        }

    ts = time.time()
    # Determinismo absoluto V4.0
    ref_id = "REF_" + _b3_hash(f"VENDA:{plg_address}:{polygon_address}:{plg_amount}:{ts}".encode())[:12].upper()
    
    order  = {
        "ref_id"         : ref_id,
        "tipo"           : "VENDER",
        "plg_address"    : plg_address,
        "polygon_address": polygon_address,
        "plg_amount"     : round(plg_amount, 4),
        "usdc_amount"    : usdc_estimado,
        "taxa"           : taxa,
        "created_at"     : ts,
        "status"         : "PENDENTE_MANUAL",
        "tx_hash_polygon": "",
    }
    plegma_db.salvar_swap_order(order)
    _log.info(f"[SWAP V4.0] Venda registrada: {ref_id[:8]}… | "
          f"{plg_amount:,.0f} PLG → ${usdc_estimado:.2f} USDC → {polygon_address[:12]}…")

    return {
        "ok"           : True,
        "ref_id"       : ref_id,
        "usdc_estimado": usdc_estimado,
        "plg_amount"   : round(plg_amount, 4),
        "taxa"         : taxa,
        "status"       : "PENDENTE_MANUAL",
        "aviso"        : ("Venda registrada com sucesso. O USDC será enviado em até 24h."),
    }


# =============================================================================
# PROCESSAR PAGAMENTO DETECTADO PELO MONITOR
# =============================================================================
def processar_pagamento_usdc(tx_hash: str, usdc_recebido: float, from_polygon: str):
    if plegma_db.swap_tx_ja_processada(tx_hash):
        return

    ordem = plegma_db.buscar_swap_order_pendente_por_valor(usdc_recebido, TOLERANCIA_USDC)

    if not ordem:
        _log.info(f"[SWAP V4.0][AVISO] USDC sem ordem correspondente: "
              f"{usdc_recebido:.2f} USDC | tx:{tx_hash[:20]}… | de:{from_polygon[:12]}…")
        plegma_db.salvar_estado(
            f"swap_unmatched_{tx_hash[:16]}",
            {"tx_hash": tx_hash, "usdc": usdc_recebido,
             "from": from_polygon, "ts": time.time()}
        )
        return

    with _lock:
        plg_amount  = ordem["plg_amount"]
        plg_address = ordem["plg_address"]

        plg_reserva = plegma_db.carregar_estado("pool_plg_reserva", 0.0)

        if plg_reserva < plg_amount:
            _log.info(f"[SWAP V4.0][ERRO] Reserva PLG insuficiente: "
                  f"{plg_reserva:,.0f} disponível, {plg_amount:,.0f} necessário.")
            plegma_db.atualizar_swap_order_status(ordem["ref_id"], "ERRO_RESERVA", tx_hash)
            return

        plegma_db.salvar_estado("pool_plg_reserva", plg_reserva - plg_amount)

        usdc_atual = plegma_db.carregar_estado("pool_usdc_saldo", 0.0)
        plegma_db.salvar_estado("pool_usdc_saldo", usdc_atual + usdc_recebido)

        _registrar_credito_plg(plg_address, plg_amount, tx_hash)
        plegma_db.atualizar_swap_order_status(ordem["ref_id"], "CONFIRMADO", tx_hash)

        _log.info(f"[SWAP V4.0] ✓ Compra confirmada: {plg_amount:,.4f} PLG "
              f"→ {plg_address[:20]}… | USDC tx: {tx_hash[:20]}…")


def _registrar_credito_plg(plg_address: str, plg_amount: float, tx_hash_ref: str):
    ts    = int(time.time())
    raw   = f"SWAP:{POOL_PLG_ADDRESS}:{plg_address}:{plg_amount}:{ts}:{tx_hash_ref}"
    thash = "SWAP_" + _b3_hash(raw.encode())[:48]

    tx = {
        "tx_hash"      : thash,
        "sender"       : POOL_PLG_ADDRESS,
        "receiver"     : plg_address,
        "amount"       : plg_amount,
        "parents"      : plegma_db.carregar_tips()[:2],
        "timestamp"    : ts,
        "signature"    : f"POOL_SWAP:{tx_hash_ref[:20]}",
        "zk_proof_size": 0,
        "node_type"    : "SWAP",
    }
    plegma_db.salvar_transacao(tx)


# =============================================================================
# STATUS COMPLETO DA POOL
# =============================================================================
def get_pool_status() -> dict:
    ordens = plegma_db.listar_swap_orders(limite=20)
    ordens_pub = [
        {
            "ref_id"     : o["ref_id"][:8] + "…",
            "tipo"       : o["tipo"],
            "plg_amount" : o["plg_amount"],
            "usdc_amount": o["usdc_amount"],
            "status"     : o["status"],
            "created_at" : o["created_at"],
        }
        for o in ordens
    ]
    return {
        **get_cotacao(),
        "ordens_recentes": ordens_pub,
    }


# =============================================================================
# CÁLCULO DO PREÇO INICIAL
# =============================================================================
def calcular_e_setar_preco_genesis(usdc_pool: float, plg_disponivel: float) -> dict:
    if usdc_pool <= 0 or plg_disponivel <= 0:
        return {"ok": False, "erro": "usdc_pool e plg_disponivel devem ser > 0."}

    preco_plg = usdc_pool / plg_disponivel      
    taxa      = plg_disponivel / usdc_pool      

    with _lock:
        plegma_db.salvar_estado("pool_taxa_plg_por_usdc",   taxa)
        plegma_db.salvar_estado("pool_plg_reserva",         plg_disponivel)
        plegma_db.salvar_estado("preco_inicial_plg",        preco_plg)
        plegma_db.salvar_estado("preco_inicial_plg_ts",     time.time())
        plegma_db.salvar_estado("preco_inicial_usdc_pool",  usdc_pool)
        plegma_db.salvar_estado("preco_inicial_plg_supply", plg_disponivel)
        plegma_db.salvar_estado("carteira_pool_aerarium",   POOL_ADDRESS)

    _log.info(f"[SWAP V4.0] ══════════════════════════════════════════════")
    _log.info(f"[SWAP V4.0]  PREÇO INICIAL PLG : ${preco_plg:.8f} USDC/PLG")
    _log.info(f"[SWAP V4.0]  TAXA POOL         : 1 USDC = {taxa:,.4f} PLG")
    _log.info(f"[SWAP V4.0]  USDC na pool (L)  : ${usdc_pool:,.2f}")
    _log.info(f"[SWAP V4.0]  PLG emitido (S)   : {plg_disponivel:,.4f} PLG")
    _log.info(f"[SWAP V4.0] ══════════════════════════════════════════════")

    return {
        "ok"               : True,
        "preco_inicial_plg": preco_plg,
        "taxa"             : taxa,
        "usdc_pool"        : usdc_pool,
        "plg_disponivel"   : plg_disponivel,
        "pool_address"     : POOL_ADDRESS,
        "solvencia"        : "100%",
    }


# =============================================================================
# INJEÇÃO DE USDC
# =============================================================================
def injetar_usdc(usdc_amount: float) -> dict:
    if usdc_amount <= 0:
        return {"ok": False, "erro": "Valor USDC inválido."}

    ja_injetado = plegma_db.carregar_estado("pool_usdc_genesis_injetado", False)
    if ja_injetado:
        return {"ok": True, "aviso": "Injeção genesis já executada."}

    with _lock:
        saldo_atual = plegma_db.carregar_estado("pool_usdc_saldo", 0.0)
        plegma_db.salvar_estado("pool_usdc_saldo",             saldo_atual + usdc_amount)
        plegma_db.salvar_estado("pool_usdc_genesis_injetado",  True)
        plegma_db.salvar_estado("pool_usdc_genesis_amount",    usdc_amount)
        plegma_db.salvar_estado("carteira_pool_aerarium",      POOL_ADDRESS)

    _log.info(f"[SWAP V4.0] ✓ Injeção Genesis: +${usdc_amount:,.2f} USDC")
    return {"ok": True, "usdc_injetado": usdc_amount, "pool_address": POOL_ADDRESS}


# =============================================================================
# CONFIRMAR VENDA (admin confirma)
# =============================================================================
def confirmar_venda_admin(ref_id: str, tx_hash_polygon: str) -> dict:
    ordem  = next((o for o in plegma_db.listar_swap_orders(limite=200) if o["ref_id"] == ref_id), None)

    if not ordem:
        return {"ok": False, "erro": "Ordem não encontrada."}
    if ordem["status"] not in ("PENDENTE_MANUAL",):
        return {"ok": False, "erro": f"Ordem {ordem['status']}."}

    with _lock:
        plg_amount  = ordem["plg_amount"]
        usdc_amount = ordem["usdc_amount"]

        reserva_atual = plegma_db.carregar_estado("pool_plg_reserva", 0.0)
        plegma_db.salvar_estado("pool_plg_reserva", reserva_atual + plg_amount)

        usdc_saldo = plegma_db.carregar_estado("pool_usdc_saldo", 0.0)
        plegma_db.salvar_estado("pool_usdc_saldo", max(0.0, usdc_saldo - usdc_amount))

        plegma_db.atualizar_swap_order_status(ref_id, "CONFIRMADO", tx_hash_polygon)

    _log.info(f"[SWAP V4.0] ✓ Venda confirmada: {plg_amount:,.4f} PLG → reserva | "
          f"${usdc_amount:.2f} USDC → tx:{tx_hash_polygon[:16]}…")

    return {
        "ok"            : True,
        "ref_id"        : ref_id,
        "plg_na_reserva": plg_amount,
        "usdc_debitado" : usdc_amount,
    }


def configurar_pool(taxa: float) -> dict:
    if taxa <= 0:
        return {"ok": False, "erro": "Taxa deve ser positiva."}

    plegma_db.salvar_estado("pool_taxa_plg_por_usdc", taxa)
    plegma_db.salvar_estado("carteira_pool_aerarium",  POOL_ADDRESS)

    _log.info(f"[SWAP V4.0] Taxa configurada: 1 USDC = {taxa:,.0f} PLG | Pool: {POOL_ADDRESS}")
    return {
        "ok"          : True,
        "pool_address": POOL_ADDRESS,
        "taxa"        : taxa,
    }


def _loop_monitor():
    global _monitor_ativo

    if not _W3_DISPONIVEL:
        _log.info("[SWAP V4.0][MONITOR] web3 indisponível — monitor desativado.")
        return

    w3           = Web3(Web3.HTTPProvider(POLYGON_RPC))
    usdc         = w3.eth.contract(
        address=Web3.to_checksum_address(USDC_CONTRACT_ADDR), abi=USDC_ABI
    )
    pool_cs      = Web3.to_checksum_address(POOL_ADDRESS)
    ultimo_bloco = w3.eth.block_number - 5

    _log.info(f"[SWAP V4.0][MONITOR] Ativo | Watching {POOL_ADDRESS[:20]}… | Bloco: {ultimo_bloco}")

    while _monitor_ativo:
        try:
            bloco_atual = w3.eth.block_number
            if bloco_atual <= ultimo_bloco:
                time.sleep(INTERVALO_MONITOR_S)
                continue

            eventos = usdc.events.Transfer.get_logs(
                from_block=ultimo_bloco + 1,
                to_block=bloco_atual,
                argument_filters={"to": pool_cs},
            )

            for ev in eventos:
                tx_hash       = ev["transactionHash"].hex()
                usdc_recebido = ev["args"]["value"] / (10 ** USDC_DECIMALS)
                from_addr     = ev["args"]["from"]

                if usdc_recebido < DUST_MINIMO:
                    continue

                processar_pagamento_usdc(tx_hash, usdc_recebido, from_addr)

            ultimo_bloco = bloco_atual

        except Exception as e:
            _log.info(f"[SWAP V4.0][MONITOR][ERRO] {e}")

        time.sleep(INTERVALO_MONITOR_S)


def iniciar_monitor():
    global _monitor_ativo
    if _monitor_ativo:
        return
    _monitor_ativo = True
    t = threading.Thread(target=_loop_monitor, daemon=True, name="AerariumSwapMonitor")
    t.start()


def parar_monitor():
    global _monitor_ativo
    _monitor_ativo = False


if __name__ == "__main__":
    import sys
    plegma_db.inicializar_banco()

    if len(sys.argv) == 2:
        taxa_arg = float(sys.argv[1])
        r = configurar_pool(taxa_arg)
        _log.info(r)
    else:
        _log.info("Pool status:", json.dumps(get_pool_status(), indent=2, ensure_ascii=False))