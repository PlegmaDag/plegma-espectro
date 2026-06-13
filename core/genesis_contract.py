import time
import logging
import threading
from datetime import datetime, timedelta
import plegma_db
from tx_verifier import verificar_tx

_log = logging.getLogger(__name__)

# ── Blindagem de Oráculo Determinístico (Hard Fail) ─────────
try:
    import blake3 as _blake3
except ImportError:
    raise RuntimeError("[FALHA FATAL] Módulo blake3 ausente no Genesis Contract.")

def _b3_hash(data: bytes) -> str:
    return _blake3.blake3(data).hexdigest()

def _get_aerarium_swap():
    import aerarium_swap
    return aerarium_swap

_genesis_lock = threading.Lock()

# =============================================================================
# BURN ADDRESS — Endereço de Queima Verificável
# Derivação: BLAKE3("PLEGMA_BURN_ADDRESS_GENESIS_2026_FAIRLAUNCH_NOPRIVKEY")[:40].upper()
# Nenhuma chave privada Dilithium3 existe para este endereço.
# Qualquer pessoa pode verificar: python -c "import blake3; _log.info('PLG'+blake3.blake3(b'PLEGMA_BURN_ADDRESS_GENESIS_2026_FAIRLAUNCH_NOPRIVKEY').hexdigest()[:40].upper())"
# =============================================================================
BURN_ADDRESS = "PLG0237FEEC84108E37FF522A253AD1D469097A5A2B"
BURN_INPUT   = "PLEGMA_BURN_ADDRESS_GENESIS_2026_FAIRLAUNCH_NOPRIVKEY"

# =============================================================================
# GENESIS CONTRACT — Reserva Genesis PLG-G (Nativo PLEGMA V4.0)
# =============================================================================

PLGG_SUPPLY_TOTAL  = 10_500_000.0
PLGG_PRECO_USD     = 0.10
GENESIS_DIAS       = 62   # duração da fase de venda (09/05/2026 → 10/07/2026)
GENESIS_LOCKUP_DIAS = 30  # lock-up do PLG-G após compra (imutável)

GENESIS_LIQUIDEZ_SHARE  = 0.90  
GENESIS_AERARIUM_SHARE  = 0.10  

AVISO_GOVERNANCA = (
    "\n============================================================\n"
    "  ATENÇÃO: PLG-G é um TOKEN DE GOVERNANÇA da rede PLEGMA.\n"
    "  Sua posse (mín. 1.000 PLG-G) garante:\n"
    "    - Direito de voto nas decisões da rede\n"
    "    - Boost de mineração (até 2x)\n"
    "    - Status de Sócio Genesis (único e intransferível)\n"
    "\n"
    "  Ao vender, você abre mão desses direitos.\n"
    "  A venda é permitida APENAS P2P entre carteiras.\n"
    "  NUNCA via pool de liquidez.\n"
    "============================================================\n"
)

def registrar_intencao(plg_address: str, usdt_amount: float, evm_address: str = "") -> dict:
    """Registra intenção de compra Genesis.
    evm_address (opcional): endereço EVM da carteira que fará o pagamento USDC. Quando informado,
    permite cruzamento on-chain 100% determinístico entre tx_hash Polygon e ref_id PLEGMA (L1).
    """
    if usdt_amount <= 0:
        return {"erro": "Valor invalido."}
    if usdt_amount < 1.0:
        return {"erro": "Aporte minimo e $1 USDC (10 PLG-G)."}

    plgg_amount = round(usdt_amount / PLGG_PRECO_USD, 4)

    with _genesis_lock:
        vendido = plegma_db.carregar_estado("plgg_vendido", 0.0)
        disponivel = PLGG_SUPPLY_TOTAL - vendido
        if plgg_amount > disponivel:
            plgg_amount = disponivel
            usdt_amount = round(plgg_amount * PLGG_PRECO_USD, 2)

        if plgg_amount <= 0:
            return {"erro": "Reserva Genesis esgotada."}

        # ref_id determinístico: BLAKE3 sobre estado da rede + identidade do comprador
        # (sem timestamp como seed — usa contador atômico do oráculo BLAKE3 em plegma_db)
        seq    = int(plegma_db.carregar_estado("genesis_intencao_seq", 0)) + 1
        plegma_db.salvar_estado("genesis_intencao_seq", seq)
        seed   = f"{plg_address}|{usdt_amount}|{evm_address.lower()}|{seq}".encode()
        ref_id = "REF-" + _b3_hash(seed)[:12].upper()

        entry = {
            "ref_id"      : ref_id,
            "plg_address" : plg_address,
            "usdt_amount" : usdt_amount,
            "plgg_amount" : plgg_amount,
            "created_at"  : time.time(),
            "status"      : "AGUARDANDO",
            "evm_address" : evm_address.lower(),
            "tx_hash"     : "",
            "anchor_id"   : "",
        }
        plegma_db.salvar_pending_purchase(entry)

    _log.info(f"[GENESIS] Intenção registrada: {ref_id} | {plgg_amount:.2f} PLG-G | {plg_address[:16]}... | EVM: {evm_address[:10] if evm_address else '—'}")
    return {
        "ref_id"          : ref_id,
        "plg_address"     : plg_address,
        "plgg_amount"     : plgg_amount,
        "usdt_a_pagar"    : usdt_amount,
        "evm_address"     : evm_address.lower(),
        "instrucao"       : "Envie exatamente o valor acima em USDC para a carteira de recebimento.",
        "aviso_lockup"    : f"PLG-G ficara bloqueado por {GENESIS_LOCKUP_DIAS} dias."
    }


def ancorar_tx_polygon(ref_id: str, tx_hash: str, evm_address: str) -> dict:
    """Vincula determinísticamente uma intenção (ref_id) a um tx_hash Polygon antes da confirmação on-chain.

    Âncora BLAKE3 (L1 + L3): impossível forjar vínculo sem conhecer ref_id + tx_hash + evm_address.
    Retorna {ok, anchor_id, status} ou {erro}. NÃO emite PLG-G — apenas registra a âncora.
    O monitor confirma quando vê a tx on-chain.
    """
    if not ref_id or not tx_hash or not evm_address:
        return {"erro": "ref_id, tx_hash e evm_address são obrigatórios."}

    pending = plegma_db.buscar_pending_purchase(ref_id)
    if not pending:
        return {"erro": "Intenção não encontrada.", "ref_id": ref_id}
    if pending["status"] != "AGUARDANDO":
        return {"erro": f"Intenção em estado {pending['status']} — não ancorável."}

    tx_lower  = tx_hash.lower().replace("0x", "")
    evm_lower = evm_address.lower().replace("0x", "")

    # Âncora determinística — mesmo input → mesmo output sempre (L1)
    anchor_seed = (b"PLEGMA_TX_ANCHOR_V1|"
                   + ref_id.encode() + b"|"
                   + tx_lower.encode() + b"|"
                   + pending["plg_address"].encode() + b"|"
                   + evm_lower.encode())
    anchor_id = "ANC-" + _b3_hash(anchor_seed)[:32].upper()

    ok = plegma_db.ancorar_pending_purchase(
        ref_id      = ref_id,
        tx_hash     = "0x" + tx_lower,
        evm_address = "0x" + evm_lower,
        anchor_id   = anchor_id,
    )
    if not ok:
        return {"erro": "Conflito ao ancorar — possivelmente já ancorada."}

    _log.info(f"[GENESIS] Âncora Web3: {anchor_id[:20]} | {ref_id} | tx: {tx_lower[:16]}... | EVM: {evm_lower[:10]}...")
    return {
        "ok"        : True,
        "anchor_id" : anchor_id,
        "ref_id"    : ref_id,
        "tx_hash"   : "0x" + tx_lower,
        "status"    : "AWAITING_ONCHAIN_CONFIRMATION",
        "lockup_dias": GENESIS_LOCKUP_DIAS,
    }

def confirmar_compra(tx_hash_externo: str, plg_address: str,
                     usdt_recebido: float, ref_id: str = None) -> dict:
    
    if plegma_db.tx_externo_ja_processado(tx_hash_externo):
        return {"erro": "Pagamento ja processado.", "tx_hash": tx_hash_externo}

    launch_date = plegma_db.carregar_estado("genesis_launch_date", None)
    if launch_date:
        dias_decorridos = (time.time() - launch_date) / 86400
        if dias_decorridos > GENESIS_DIAS:
            return {"erro": "Fase Genesis encerrada. Queima em andamento."}

    plgg_amount = round(usdt_recebido / PLGG_PRECO_USD, 4)

    with _genesis_lock:
        vendido = plegma_db.carregar_estado("plgg_vendido", 0.0)
        disponivel = PLGG_SUPPLY_TOTAL - vendido
        if plgg_amount > disponivel:
            plgg_amount = disponivel

        if plgg_amount <= 0:
            return {"erro": "Reserva Genesis esgotada."}

        agora        = time.time()
        release_date = agora + (GENESIS_LOCKUP_DIAS * 86400)

        dna = _b3_hash(plg_address.encode())

        vesting_entry = {
            "plg_address"    : plg_address,
            "amount"         : plgg_amount,
            "usdt_pago"      : usdt_recebido,
            "tx_hash_externo": tx_hash_externo,
            "purchase_date"  : agora,
            "release_date"   : release_date,
            "status"         : "LOCKED"
        }
        plegma_db.salvar_plgg_vesting(vesting_entry)

        saldo_atual = plegma_db.carregar_saldo_plgg(plg_address)
        plegma_db.salvar_saldo_plgg(plg_address, saldo_atual + plgg_amount)

        genesis_atual = plegma_db.carregar_saldo_plgg_genesis(plg_address)
        novo_genesis = genesis_atual + plgg_amount
        plegma_db.salvar_saldo_plgg_genesis(plg_address, novo_genesis)

        # Selo Gênese condicionado à barreira de 1000 PLG-G ($100)
        if novo_genesis >= 1000.0:
            plegma_db.marcar_socio_genesis(plg_address)

        plegma_db.salvar_estado("plgg_vendido",    vendido + plgg_amount)
        total_usdt = plegma_db.carregar_estado("plgg_usdt_arrecadado", 0.0)
        plegma_db.salvar_estado("plgg_usdt_arrecadado", total_usdt + usdt_recebido)

        if ref_id:
            plegma_db.atualizar_status_pending(ref_id, "CONFIRMADO")

    # ── Transação DAG (histórico + hash PLEGMA visível) ────────────────────
    tx_seed     = f"GENESIS:{plg_address}:{plgg_amount}:{tx_hash_externo}:{agora}".encode()
    dag_tx_hash = "PLG" + _b3_hash(tx_seed)[:40].upper()
    tips        = plegma_db.carregar_tips()
    plegma_db.salvar_transacao({
        "tx_hash"       : dag_tx_hash,
        "sender"        : "GENESIS_CONTRACT",
        "receiver"      : plg_address,
        "amount"        : plgg_amount,
        "parents"       : tips[:2] if tips else [],
        "timestamp"     : int(agora),
        "signature"     : _b3_hash(f"GENESIS_SIG:{dag_tx_hash}".encode()),
        "zk_proof_size" : 22000,
        "node_type"     : "GENESIS",
    })

    liberacao_str = datetime.fromtimestamp(release_date).strftime('%d/%m/%Y %H:%M')
    _log.info(f"[GENESIS] PLG-G emitido: {plgg_amount:.2f} -> {plg_address[:16]}... | DNA: {dna[:16]}... | tx: {dag_tx_hash} | Liberação: {liberacao_str}")

    return {
        "status"         : "CONFIRMADO",
        "plg_address"    : plg_address,
        "plgg_emitido"   : plgg_amount,
        "usdt_recebido"  : usdt_recebido,
        "tx_hash_externo": tx_hash_externo,
        "dag_tx_hash"    : dag_tx_hash,
        "lockup_ate"     : liberacao_str,
        "dna"            : dna,
        "aviso_dna"      : "PLG-G Genesis vinculado ao DNA desta carteira.",
        "aviso"          : AVISO_GOVERNANCA
    }

def get_saldo_liberado(plg_address: str) -> dict:
    agora    = time.time()
    vestings = plegma_db.carregar_vesting_por_usuario(plg_address)
    locked   = 0.0
    liberado = 0.0

    for v in vestings:
        if v["status"] == "LOCKED":
            if agora >= v["release_date"]:
                plegma_db.atualizar_status_plgg_vesting(v["tx_hash_externo"], "LIBERADO")
                liberado += v["amount"]
            else:
                locked += v["amount"]
        elif v["status"] == "LIBERADO":
            liberado += v["amount"]

    return {
        "plg_address"    : plg_address,
        "saldo_total"    : plegma_db.carregar_saldo_plgg(plg_address),
        "saldo_liberado" : liberado,
        "saldo_bloqueado": locked,
        "proximo_unlock" : _proximo_unlock(vestings, agora)
    }

def _proximo_unlock(vestings: list, agora: float):
    proximos = [v["release_date"] for v in vestings
                if v["status"] == "LOCKED" and v["release_date"] > agora]
    if not proximos:
        return None
    return datetime.fromtimestamp(min(proximos)).strftime('%d/%m/%Y %H:%M')

def transferir_plgg(from_addr: str, to_addr: str,
                    amount: float, confirmado: bool = False,
                    preco_unitario: float = None,
                    signature: str = None,
                    public_key: str = None,
                    interno: bool = False) -> dict:
    """interno=True ignora verificação de assinatura (chamadas autenticadas por sessão)."""

    if not interno:
        if not confirmado:
            return {
                "status"         : "AGUARDANDO_CONFIRMACAO",
                "aviso_governanca": AVISO_GOVERNANCA,
                "instrucao"      : "Reenvie com confirmado=true, signature e public_key para prosseguir."
            }

        if not signature or not public_key:
            return {"erro": "Campos obrigatórios para transferência: signature e public_key."}

        tx_mensagem = f"{from_addr}:PLGG:{to_addr}:{amount}"
        ok_sig, motivo = verificar_tx(
            sender        = from_addr,
            public_key_hex= public_key,
            signature     = signature,
            mensagem      = tx_mensagem
        )
        if not ok_sig:
            _log.info(f"[GENESIS][BLOQUEADO] transferir_plgg rejeitado — {motivo} — {from_addr[:16]}...")
            return {"erro": f"Assinatura inválida: {motivo}"}

    saldo_info = get_saldo_liberado(from_addr)
    disponivel = max(0.0, saldo_info["saldo_total"] - saldo_info["saldo_bloqueado"])
    if disponivel < amount:
        return {
            "erro"            : "Saldo liberado insuficiente.",
            "saldo_liberado"  : disponivel,
            "saldo_bloqueado" : saldo_info["saldo_bloqueado"],
            "proximo_unlock"  : saldo_info["proximo_unlock"]
        }

    saldo_from = plegma_db.carregar_saldo_plgg(from_addr)
    plegma_db.salvar_saldo_plgg(from_addr, saldo_from - amount)

    genesis_from = plegma_db.carregar_saldo_plgg_genesis(from_addr)
    if genesis_from > 0:
        genesis_debitado = min(amount, genesis_from)
        plegma_db.salvar_saldo_plgg_genesis(from_addr, genesis_from - genesis_debitado)
        if genesis_debitado > 0:
            _log.info(f"[GENESIS] DNA perdido: {genesis_debitado:.4f} PLG-G saíram de {from_addr[:16]}...")

    novo_genesis_from = plegma_db.carregar_saldo_plgg_genesis(from_addr)
    if novo_genesis_from <= 0 and plegma_db.is_socio_genesis(from_addr):
        plegma_db.marcar_status_genesis_perdido(from_addr)
        _log.info(f"[GENESIS] Título Sócio Genesis PERDIDO: {from_addr[:16]}...")

    saldo_to = plegma_db.carregar_saldo_plgg(to_addr)
    plegma_db.salvar_saldo_plgg(to_addr, saldo_to + amount)

    if preco_unitario is not None and preco_unitario > 0:
        _registrar_preco_venda(from_addr, preco_unitario, amount)

    agora       = time.time()
    tx_seed     = f"PLGG_TX:{from_addr}:{to_addr}:{amount}:{agora}".encode()
    dag_tx_hash = "PLG" + _b3_hash(tx_seed)[:40].upper()
    tips        = plegma_db.carregar_tips()
    plegma_db.salvar_transacao({
        "tx_hash"       : dag_tx_hash,
        "sender"        : from_addr,
        "receiver"      : to_addr,
        "amount"        : amount,
        "parents"       : tips[:2] if tips else [],
        "timestamp"     : int(agora),
        "signature"     : _b3_hash(f"PLGG_SIG:{dag_tx_hash}".encode()),
        "zk_proof_size" : 22000,
        "node_type"     : "PLGG_TRANSFER",
    })

    _log.info(f"[GENESIS] Transferencia PLG-G: {amount:.4f} | {from_addr[:12]}... -> {to_addr[:12]}... | tx: {dag_tx_hash}")
    return {
        "status"   : "TRANSFERIDO",
        "de"       : from_addr,
        "para"     : to_addr,
        "amount"   : amount,
        "tx_hash"  : dag_tx_hash,
        "aviso"    : "PLG-G transferido. Lembre: venda apenas P2P, nunca via pool de liquidez."
    }

def _registrar_preco_venda(vendedor: str, preco: float, amount: float):
    num_vendas = int(plegma_db.carregar_estado("plgg_num_vendas_p2p", 0)) + 1
    plegma_db.salvar_estado("plgg_ultimo_preco_p2p",   preco)
    plegma_db.salvar_estado("plgg_ultima_venda_ts",    time.time())
    plegma_db.salvar_estado("plgg_ultima_venda_vendor", vendedor)
    plegma_db.salvar_estado("plgg_num_vendas_p2p",     num_vendas)

def queimar_plgg_nao_vendido() -> dict:
    if plegma_db.carregar_estado("genesis_plgg_queimado", 0) == 1:
        queimado = plegma_db.carregar_estado("genesis_plgg_burn_amount", 0.0)
        return {"status": "JA_EXECUTADO", "burned_plgg": queimado}

    launch_date = plegma_db.carregar_estado("genesis_launch_date", None)
    if launch_date:
        dias_decorridos = (time.time() - launch_date) / 86400
        if dias_decorridos < GENESIS_DIAS:
            restante = GENESIS_DIAS - dias_decorridos
            return {"status": "PERIODO_ATIVO", "dias_restantes": round(restante, 1)}

    with _genesis_lock:
        vendido   = plegma_db.carregar_estado("plgg_vendido", 0.0)
        nao_vendido = max(0.0, PLGG_SUPPLY_TOTAL - vendido)

        if nao_vendido <= 0:
            plegma_db.salvar_estado("genesis_plgg_queimado",    1)
            plegma_db.salvar_estado("genesis_plgg_burn_amount", 0.0)
            plegma_db.salvar_estado("genesis_plgg_burn_ts",     time.time())
            return {"status": "TUDO_VENDIDO", "burned_plgg": 0.0}

        burn_ts = time.time()
        plegma_db.salvar_estado("genesis_plgg_queimado",      1)
        plegma_db.salvar_estado("genesis_plgg_burn_amount",   nao_vendido)
        plegma_db.salvar_estado("genesis_plgg_burn_ts",       burn_ts)
        plegma_db.salvar_estado("genesis_plgg_burn_address",  BURN_ADDRESS)
        plegma_db.salvar_estado("genesis_plgg_burn_input",    BURN_INPUT)

    _log.info(f"[GENESIS] QUEIMA INSTANTÂNEA: {nao_vendido:,.4f} PLG-G → {BURN_ADDRESS}")
    return {
        "status"      : "QUEIMADO",
        "burned_plgg" : nao_vendido,
        "vendido"     : vendido,
        "supply_total": PLGG_SUPPLY_TOTAL
    }

def get_status_socio_genesis(address: str) -> dict:
    is_genesis      = plegma_db.is_socio_genesis(address)
    perdido         = plegma_db.status_genesis_perdido(address)
    saldo           = plegma_db.carregar_saldo_plgg(address)
    genesis_balance = plegma_db.carregar_saldo_plgg_genesis(address)
    dna             = _b3_hash(address.encode()) if is_genesis else None

    if not is_genesis:
        return {
            "socio_genesis"    : False,
            "status_perdido"   : False,
            "selo_ativo"       : False,
            "saldo_plgg"       : saldo,
            "genesis_balance"  : 0.0,
            "dna"              : None,
            "mensagem"         : "Endereço não atingiu o teto estrutural Gênese (1.000 PLG-G)."
        }

    if perdido:
        return {
            "socio_genesis"    : True,
            "status_perdido"   : True,
            "selo_ativo"       : False,
            "saldo_plgg"       : saldo,
            "genesis_balance"  : genesis_balance,
            "dna"              : dna,
            "mensagem"         : "Título Sócio Genesis perdido permanentemente."
        }

    return {
        "socio_genesis"    : True,
        "status_perdido"   : False,
        "selo_ativo"       : True,
        "saldo_plgg"       : saldo,
        "genesis_balance"  : genesis_balance,
        "dna"              : dna,
        "mensagem"         : "Sócio Genesis ativo. PLG-G com DNA vinculado."
    }

def get_ultimo_preco_plgg() -> dict:
    preco_p2p  = plegma_db.carregar_estado("plgg_ultimo_preco_p2p",  None)
    venda_ts   = plegma_db.carregar_estado("plgg_ultima_venda_ts",   None)
    num_vendas = int(plegma_db.carregar_estado("plgg_num_vendas_p2p", 0))

    if preco_p2p is not None and num_vendas > 0:
        venda_dt = datetime.fromtimestamp(venda_ts).strftime('%d/%m/%Y %H:%M') if venda_ts else None
        return {
            "preco"            : round(float(preco_p2p), 6),
            "fonte"            : "p2p",
            "ultima_venda_data": venda_dt,
            "num_vendas_p2p"   : num_vendas,
            "nota"             : "Preço definido exclusivamente pelo Sócio vendedor."
        }
    else:
        return {
            "preco"            : PLGG_PRECO_USD,
            "fonte"            : "genesis",
            "ultima_venda_data": None,
            "num_vendas_p2p"   : 0,
            "nota"             : "Preço de emissão Genesis. Mercado P2P ativo pós-lançamento."
        }

def activate_governance() -> dict:
    ja_ativa = plegma_db.carregar_estado("governance_active", False)
    if ja_ativa:
        return {"status": "JA_ATIVA", "governance_active": True}

    launch_ts = plegma_db.carregar_estado("genesis_launch_date", None)
    if not launch_ts:
        return {"status": "ERRO", "governance_active": False}

    dias_decorridos = (time.time() - launch_ts) / 86400
    if dias_decorridos < GENESIS_DIAS:
        return {"status": "AGUARDANDO", "governance_active": False}

    agora = time.time()
    plegma_db.salvar_estado("governance_active",       True)
    plegma_db.salvar_estado("governance_activated_at", agora)
    return {"status": "ATIVADA", "governance_active": True}

def get_governance_status() -> dict:
    return {
        "governance_active"  : plegma_db.carregar_estado("governance_active", False)
    }

def liquidity_injection() -> dict:
    ja_injetado = plegma_db.carregar_estado("liquidity_injected", False)
    if ja_injetado:
        return {"status": "JA_INJETADO"}

    total_usdc = plegma_db.carregar_estado("plgg_usdt_arrecadado", 0.0)
    valor_liquidez = round(total_usdc * GENESIS_LIQUIDEZ_SHARE, 2)
    valor_aerarium = round(total_usdc * GENESIS_AERARIUM_SHARE, 2)

    agora = time.time()
    plegma_db.salvar_estado("liquidity_injected",          True)
    plegma_db.salvar_estado("liquidity_amount",            valor_liquidez)
    plegma_db.salvar_estado("liquidity_timestamp",         agora)
    plegma_db.salvar_estado("aerarium_genesis_amount",     valor_aerarium)

    return {"status": "INJETADO", "liquidity_injected": True}

def get_liquidity_status() -> dict:
    injetado    = plegma_db.carregar_estado("liquidity_injected", False)
    total_usdc  = plegma_db.carregar_estado("plgg_usdt_arrecadado", 0.0)
    aerarium_fila = round(total_usdc * GENESIS_AERARIUM_SHARE, 2)
    aerarium_pool = plegma_db.carregar_estado("aerarium_pool", 0.0)

    proxima_str = None
    try:
        with plegma_db.get_connection() as conn:
            row = conn.execute(
                "SELECT MIN(release_date) FROM plgg_vesting WHERE status='LOCKED'"
            ).fetchone()
        if row and row[0]:
            proxima_str = datetime.fromtimestamp(row[0]).strftime('%d/%m/%Y')
    except Exception:
        pass

    fees_acumuladas = plegma_db.carregar_estado("aerarium_fees_accumulated", 0.0)

    # valor_aerarium = USDC Genesis (10%) + PLG pool acumulado de taxas
    # Mostrado em USDC — aerarium_pool (PLG) separado como campo próprio
    valor_usdc_aerarium = round(aerarium_fila + aerarium_pool, 2)
    return {
        "liquidity_injected"        : injetado,
        "valor_aerarium"            : valor_usdc_aerarium,
        "aerarium_genesis_usdc"     : aerarium_fila,
        "aerarium_pool_plg"         : round(aerarium_pool, 2),
        "aerarium_teto"             : 1000.0,
        "aerarium_transbordo"       : round(max(0.0, valor_usdc_aerarium - 1000.0), 2),
        "usdc_arrecadado_total"     : round(total_usdc, 2),
        "aerarium_fila_usdc"        : aerarium_fila,
        "aerarium_fila_data"        : proxima_str,
        "aerarium_fees_acumuladas"  : round(fees_acumuladas, 6),
    }

def registrar_carteiras_destino_polygon(pool_polygon_addr: str, aerarium_polygon_addr: str) -> dict:
    plegma_db.salvar_estado("polygon_addr_pool_liquidez", pool_polygon_addr.lower())
    plegma_db.salvar_estado("polygon_addr_aerarium",      aerarium_polygon_addr.lower())
    return {"status": "REGISTRADO"}

def get_carteiras_destino_polygon() -> dict:
    return {
        "pool_liquidez"  : plegma_db.carregar_estado("polygon_addr_pool_liquidez", None),
        "aerarium"       : plegma_db.carregar_estado("polygon_addr_aerarium", None)
    }

def get_burn_status() -> dict:
    queimado   = plegma_db.carregar_estado("genesis_plgg_queimado", 0)
    burned_qty = plegma_db.carregar_estado("genesis_plgg_burn_amount", 0.0)
    burn_ts    = plegma_db.carregar_estado("genesis_plgg_burn_ts", None)
    vendido    = plegma_db.carregar_estado("plgg_vendido", 0.0)

    return {
        "burn_address":       BURN_ADDRESS,
        "burn_input":         BURN_INPUT,
        "burn_method":        "BLAKE3(input)[:40].upper() prefixed with PLG",
        "burned_plgg":        float(burned_qty),
        "burn_executed":      bool(queimado),
        "burn_timestamp":     burn_ts,
        "burn_timestamp_iso": datetime.fromtimestamp(burn_ts).isoformat() if burn_ts else None,
        "supply_total":       PLGG_SUPPLY_TOTAL,
        "supply_sold":        float(vendido),
        "supply_remaining":   max(0.0, PLGG_SUPPLY_TOTAL - float(vendido)),
        "verification_cmd":   "python -c \"import blake3; _log.info('PLG'+blake3.blake3(b'PLEGMA_BURN_ADDRESS_GENESIS_2026_FAIRLAUNCH_NOPRIVKEY').hexdigest()[:40].upper())\"",
        "verification_url":   "https://plegmadag.com/burn/"
    }

def get_status() -> dict:
    """Status canônico da Reserva Genesis.
    Fonte única lida por dashboard, console, admin e página /genesis/.
    Mantém aliases retro-compat (total_plgg_sold, total_usdt_arrecadado) para
    UIs antigas — todos os novos consumidores devem usar os nomes principais.
    """
    vendido    = plegma_db.carregar_estado("plgg_vendido",          0.0)
    arrecadado = plegma_db.carregar_estado("plgg_usdt_arrecadado",  0.0)
    queimado   = plegma_db.carregar_estado("plgg_queimado",         0.0)
    disponivel = max(PLGG_SUPPLY_TOTAL - vendido, 0.0)
    pct        = (vendido / PLGG_SUPPLY_TOTAL * 100.0) if PLGG_SUPPLY_TOTAL > 0 else 0.0

    # Estado temporal: nao_iniciado / em_andamento / encerrado
    launch_ts = plegma_db.carregar_estado("genesis_launch_date", None)
    if not launch_ts:
        dias_restantes = "Nao iniciado"
        network_day    = 0
        genesis_inicio = None
        genesis_fim    = None
    else:
        fim_ts          = launch_ts + GENESIS_DIAS * 86400
        restante        = (fim_ts - time.time()) / 86400
        dias_restantes  = round(restante, 2) if restante > 0 else 0
        network_day     = max(1, int((time.time() - launch_ts) / 86400) + 1)
        genesis_inicio  = datetime.fromtimestamp(launch_ts).isoformat()
        genesis_fim     = datetime.fromtimestamp(fim_ts).isoformat()

    return {
        # ── Campos canônicos (preferidos) ─────────────────────────────────
        "supply_total"          : PLGG_SUPPLY_TOTAL,
        "vendido"               : vendido,
        "disponivel"            : disponivel,
        "queimado"              : queimado,
        "usdt_arrecadado"       : arrecadado,
        "percentual_vendido"    : pct,
        "dias_restantes"        : dias_restantes,
        "network_day"           : network_day,
        "genesis_inicio"        : genesis_inicio,
        "genesis_fim"           : genesis_fim,
        # ── Aliases retro-compat (UIs antigas) ────────────────────────────
        "total_plgg_sold"       : vendido,
        "total_usdt_arrecadado" : arrecadado,
    }