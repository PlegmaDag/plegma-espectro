import time
import json
import threading
from datetime import datetime
try:
    from web3 import Web3
    _WEB3_DISPONIVEL = True
except ImportError:
    _WEB3_DISPONIVEL = False
    Web3 = None  # módulo não instalado neste nó
import plegma_db
import genesis_contract

import logging
_log = logging.getLogger(__name__)

# =============================================================================
# MONITOR DE PAGAMENTOS — Detecta USDC na Polygon e emite PLG-G
# PLEGMA DAG V4.0 (PÓS-QUÂNTICO)
#
# Usa RPC publico da Polygon — sem conta, sem API key.
# Os hashes externos processados aqui (Keccak256) pertencem exclusivamente
# à rede Polygon. O núcleo Plegma mantém a Hegemonia BLAKE3 internamente.
#
# Fluxo:
#   1. Comprador registra intencao em POST /api/genesis/registrar
#   2. Comprador envia USDC para CARTEIRA_RECEBIMENTO (Polygon)
#   3. Este monitor detecta a transferencia a cada INTERVALO_SEGUNDOS
#   4. Chama genesis_contract.confirmar_compra() -> emite PLG-G na PLEGMA
# =============================================================================

POLYGON_RPCS = [
    "https://polygon.drpc.org",
    "https://polygon-bor-rpc.publicnode.com",
    "https://rpc-mainnet.matic.quiknode.pro",
    "https://1rpc.io/matic",
]
USDC_CONTRACT_ADDR  = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"  # USDC nativo Polygon
USDC_DECIMALS       = 6
INTERVALO_SEGUNDOS  = 60
TOLERANCIA_USD      = 0.02   # Diferenca maxima aceita por arredondamento
CHUNK_BLOCOS        = 200    # max blocos por chamada get_logs (scan secundario)
BLOCOS_RECENTES     = 400    # janela de scan secundario (pagamentos sem tx_hash)

# ERC-20 Transfer topic
_TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

# ABI minima — evento Transfer + funções balanceOf e transfer (ERC-20)
USDC_ABI = json.loads('[{"anonymous":false,"inputs":[{"indexed":true,"name":"from","type":"address"},{"indexed":true,"name":"to","type":"address"},{"indexed":false,"name":"value","type":"uint256"}],"name":"Transfer","type":"event"},{"inputs":[{"name":"account","type":"address"}],"name":"balanceOf","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[{"name":"to","type":"address"},{"name":"value","type":"uint256"}],"name":"transfer","outputs":[{"name":"","type":"bool"}],"stateMutability":"nonpayable","type":"function"}]')

_ativo = False


def configurar(carteira: str):
    """Registra a carteira de recebimento no banco."""
    plegma_db.salvar_estado("carteira_recebimento", carteira.lower())
    _log.info(f"[MONITOR V5.0] Carteira configurada: {carteira}")


def _get_carteira() -> str:
    return plegma_db.carregar_estado("carteira_recebimento", "")


def _confirmar(tx_hash: str, plg_address: str, usdt_amount: float, ref_id: str):
    """Chama genesis_contract e loga resultado."""
    resultado = genesis_contract.confirmar_compra(
        tx_hash_externo = tx_hash,
        plg_address     = plg_address,
        usdt_recebido   = usdt_amount,
        ref_id          = ref_id
    )
    if resultado.get("status") == "CONFIRMADO":
        _log.info(f"[MONITOR V5.0] PLG-G emitido: {resultado['plgg_emitido']:.2f} -> {plg_address[:16]}...")
    else:
        _log.info(f"[MONITOR V5.0] Falha confirmar_compra: {resultado.get('erro')}")


def _verificar_pendentes_direto(w3):
    """Mecanismo PRIMARIO: verifica cada AGUARDANDO com tx_hash via eth_getTransactionReceipt.
    Nao depende de block scanning — funciona sempre que o RPC responda."""
    pendentes = plegma_db.listar_pending_aguardando()
    for p in pendentes:
        tx_hash = (p.get("tx_hash") or "").strip()
        if len(tx_hash) < 10:
            continue
        if plegma_db.tx_externo_ja_processado(tx_hash):
            continue
        try:
            receipt = w3.eth.get_transaction_receipt(tx_hash)
        except Exception as e:
            _log.info(f"[MONITOR V5.0] receipt erro ({tx_hash[:20]}...): {e}")
            continue
        if receipt is None:
            continue  # pendente na mempool — aguardar
        if receipt.status != 1:
            _log.info(f"[MONITOR V5.0] tx {tx_hash[:20]}... falhou on-chain (status={receipt.status}) — ignorando.")
            continue
        _log.info(f"[MONITOR V5.0] tx confirmada on-chain: {tx_hash[:20]}... | ref={p['ref_id']}")
        _confirmar(tx_hash, p["plg_address"], p["usdt_amount"], p["ref_id"])


def _processar_evento_desconhecido(tx_hash: str, usdc_recebido: float):
    """Mecanismo SECUNDARIO: pagamento detectado via event scan sem tx_hash pre-registado."""
    if plegma_db.tx_externo_ja_processado(tx_hash):
        return
    pendentes = plegma_db.listar_pending_aguardando()
    for p in pendentes:
        if (p.get("tx_hash") or "").strip():
            continue  # tem tx_hash — o mecanismo primario trata
        if abs(p["usdt_amount"] - usdc_recebido) <= TOLERANCIA_USD:
            _log.info(f"[MONITOR V5.0] Pagamento por valor matchado: {usdc_recebido:.2f} USDC | tx: {tx_hash[:20]}...")
            _confirmar(tx_hash, p["plg_address"], usdc_recebido, p["ref_id"])
            return
    _log.info(f"[MONITOR V5.0] Pagamento sem registro: {usdc_recebido:.2f} USDC | tx: {tx_hash[:20]}... — guardando.")
    plegma_db.salvar_estado(f"sem_registro_{tx_hash[:16]}", {"tx_hash": tx_hash, "usdc": usdc_recebido})


def _reconnect_w3():
    """Tenta conectar a um RPC Polygon funcional e retorna Web3 ou None."""
    for rpc in POLYGON_RPCS:
        try:
            _w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 15}))
            _ = _w3.eth.block_number
            _log.info(f"[MONITOR V5.0] RPC conectado: {rpc}")
            return _w3
        except Exception as e:
            _log.info(f"[MONITOR V5.0] RPC falhou ({rpc}): {e}")
    return None


def _loop_monitor():
    """Loop principal em background.
    Ciclo 1 — verificacao directa por receipt (primario, nunca falha por range).
    Ciclo 2 — scan de blocos recentes para pagamentos sem tx_hash pre-registado."""
    global _ativo
    _ativo = True

    carteira = _get_carteira()
    if not carteira:
        _log.info("[MONITOR V5.0] Carteira nao configurada. Encerrando.")
        _ativo = False
        return

    w3 = _reconnect_w3()
    if not w3:
        _log.info("[MONITOR V5.0] Todos os RPCs falharam. Encerrando.")
        _ativo = False
        return

    contrato = w3.eth.contract(
        address=Web3.to_checksum_address(USDC_CONTRACT_ADDR),
        abi=USDC_ABI
    )

    ultimo_bloco = w3.eth.block_number
    plegma_db.salvar_estado("monitor_ultimo_bloco", ultimo_bloco)
    _log.info(f"[MONITOR V5.0] Ativo | Carteira: {carteira} | Bloco: {ultimo_bloco}")

    while _ativo:
        try:
            # --- PRIMARIO: verificacao directa de todos os AGUARDANDO com tx_hash ---
            _verificar_pendentes_direto(w3)

            # --- SECUNDARIO: scan de blocos recentes para pagamentos sem tx_hash ---
            # Usa w3.eth.get_logs() directamente (web3 v6 — sem from_block keyword)
            try:
                bloco_atual = w3.eth.block_number
                if bloco_atual > ultimo_bloco:
                    from_scan    = max(bloco_atual - BLOCOS_RECENTES, ultimo_bloco + 1)
                    chunk_inicio = from_scan
                    TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
                    carteira_topic = "0x000000000000000000000000" + Web3.to_checksum_address(carteira)[2:]
                    while chunk_inicio <= bloco_atual and _ativo:
                        chunk_fim = min(chunk_inicio + CHUNK_BLOCOS - 1, bloco_atual)
                        try:
                            logs = w3.eth.get_logs({
                                "fromBlock": chunk_inicio,
                                "toBlock":   chunk_fim,
                                "address":   Web3.to_checksum_address(USDC_CONTRACT_ADDR),
                                "topics":    [TRANSFER_TOPIC, None, carteira_topic]
                            })
                            for lg in logs:
                                txh  = lg["transactionHash"].hex()
                                data = lg["data"]
                                raw  = int(data.hex() if isinstance(data, bytes) else data, 16)
                                usdc = raw / (10 ** USDC_DECIMALS)
                                if usdc >= 0.05:
                                    _processar_evento_desconhecido(txh, usdc)
                        except Exception:
                            pass
                        chunk_inicio = chunk_fim + 1
                    ultimo_bloco = bloco_atual
                    plegma_db.salvar_estado("monitor_ultimo_bloco", ultimo_bloco)
            except Exception as e:
                _log.info(f"[MONITOR V5.0] Scan secundario erro: {e}")

        except Exception as e:
            _log.info(f"[MONITOR V5.0] Erro no loop: {e} — reconectando RPC")
            w3 = _reconnect_w3()
            if w3:
                contrato = w3.eth.contract(
                    address=Web3.to_checksum_address(USDC_CONTRACT_ADDR), abi=USDC_ABI
                )

        # --- Verificação automática do Dia 30 ---
        _verificar_dia_30()

        time.sleep(INTERVALO_SEGUNDOS)


def _verificar_dia_30():
    """
    Chamado a cada ciclo do monitor.
    No Dia 30+: ativa governança e injeta liquidez automaticamente.
    Pool e Aerarium são a mesma carteira — sem movimentação on-chain necessária.
    """
    launch_ts = plegma_db.carregar_estado("genesis_launch_date", None)
    if not launch_ts:
        return

    dias = (time.time() - launch_ts) / 86400
    if dias < 30:
        return

    # Ativa governança se ainda não ativou
    if not plegma_db.carregar_estado("governance_active", False):
        r = genesis_contract.activate_governance()
        _log.info(f"[MONITOR V4.0] Dia 30+ detectado → {r.get('status')}: {r.get('mensagem','')}")

    # Injeta liquidez na pool se ainda não injetou
    if not plegma_db.carregar_estado("liquidity_injected", False):
        r = genesis_contract.liquidity_injection()
        _log.info(f"[MONITOR V4.0] liquidity_injection → {r.get('status')}: {r.get('mensagem','')}")


def iniciar():
    """Inicia o monitor em thread background. Silencioso se web3 nao disponivel."""
    global _ativo
    if not _WEB3_DISPONIVEL:
        _log.info("[MONITOR V4.0] web3 nao instalado — monitor de pagamentos desativado neste no.")
        return
    carteira = _get_carteira()
    if not carteira:
        _log.info("[MONITOR V4.0] Carteira nao configurada. Use POST /api/genesis/configurar primeiro.")
        return
    if _ativo:
        _log.info("[MONITOR V4.0] Ja esta rodando.")
        return
    t = threading.Thread(target=_loop_monitor, daemon=True)
    t.start()


def parar():
    global _ativo
    _ativo = False
    _log.info("[MONITOR V4.0] Parando...")


# =============================================================================
# DISTRIBUIÇÃO GENESIS — envia USDC real na Polygon após Dia 30
# =============================================================================

def executar_distribuicao_usdc(chave_privada: str) -> dict:
    """
    Envia os USDC arrecadados na Genesis para Pool de Liquidez e Aerarium.

    Pré-requisitos:
      - governance_active == True  (Dia 30 passou e governança foi ativada)
      - Carteiras destino registradas via genesis_contract.registrar_carteiras_destino_polygon()
      - Idempotente: se já distribuído, retorna estado sem reenviar

    Divisão (Estatuto §5):
      90% → Pool de Liquidez $PLG  (polygon_addr_pool_liquidez)
      10% → Aerarium               (polygon_addr_aerarium)

    Args:
        chave_privada: chave privada Polygon da CARTEIRA_RECEBIMENTO (nunca persiste)
    """
    # Idempotência
    if plegma_db.carregar_estado("distribuicao_genesis_executada", False):
        tx_pool     = plegma_db.carregar_estado("distribuicao_tx_pool",     None)
        tx_aerarium = plegma_db.carregar_estado("distribuicao_tx_aerarium", None)
        ts          = plegma_db.carregar_estado("distribuicao_genesis_ts",  None)
        ts_str      = datetime.fromtimestamp(ts).strftime('%d/%m/%Y %H:%M') if ts else "desconhecido"
        return {
            "status"        : "JA_EXECUTADA",
            "executada_em"  : ts_str,
            "tx_pool"       : tx_pool,
            "tx_aerarium"   : tx_aerarium,
            "mensagem"      : "Distribuição já foi executada anteriormente."
        }

    # Verifica governance_active
    if not plegma_db.carregar_estado("governance_active", False):
        return {
            "status"  : "ERRO",
            "mensagem": "Governança não ativa. Execute activate_governance() antes de distribuir."
        }

    # Verifica carteiras destino
    destinos = genesis_contract.get_carteiras_destino_polygon()
    if not destinos["prontas"]:
        return {
            "status"  : "ERRO",
            "mensagem": "Carteiras destino não registradas. Chame registrar_carteiras_destino_polygon() no Dia Zero."
        }

    addr_pool     = Web3.to_checksum_address(destinos["pool_liquidez"])
    addr_aerarium = Web3.to_checksum_address(destinos["aerarium"])

    # Conecta à Polygon
    try:
        w3 = Web3(Web3.HTTPProvider(POLYGON_RPCS[0], request_kwargs={"timeout": 15}))
        _ = w3.eth.block_number
    except Exception as e:
        return {"status": "ERRO", "mensagem": f"Falha ao conectar ao RPC Polygon: {e}"}

    # Carteira de recebimento (remetente)
    try:
        conta = w3.eth.account.from_key(chave_privada)
    except Exception:
        return {"status": "ERRO", "mensagem": "Chave privada inválida."}

    contrato_usdc = w3.eth.contract(
        address=Web3.to_checksum_address(USDC_CONTRACT_ADDR),
        abi=USDC_ABI
    )

    # Saldo USDC atual da carteira de recebimento
    saldo_raw = contrato_usdc.functions.balanceOf(conta.address).call()
    saldo_usdc = saldo_raw / (10 ** USDC_DECIMALS)

    if saldo_usdc < 0.01:
        return {
            "status"  : "AVISO",
            "mensagem": f"Saldo USDC insuficiente na carteira de recebimento: ${saldo_usdc:.2f}"
        }

    # Calcula valores (arredonda para baixo em raw para não exceder o saldo)
    raw_pool     = int(saldo_raw * genesis_contract.GENESIS_LIQUIDEZ_SHARE)
    raw_aerarium = saldo_raw - raw_pool   # garante que raw_pool + raw_aerarium == saldo_raw

    valor_pool     = round(raw_pool     / (10 ** USDC_DECIMALS), 2)
    valor_aerarium = round(raw_aerarium / (10 ** USDC_DECIMALS), 2)

    nonce = w3.eth.get_transaction_count(conta.address)

    def _enviar(to_addr: str, raw_valor: int, nonce_tx: int) -> str:
        tx = contrato_usdc.functions.transfer(to_addr, raw_valor).build_transaction({
            "from"    : conta.address,
            "nonce"   : nonce_tx,
            "gas"     : 80_000,
            "gasPrice": w3.eth.gas_price,
            "chainId" : 137   # Polygon Mainnet
        })
        assinada = w3.eth.account.sign_transaction(tx, chave_privada)
        return w3.eth.send_raw_transaction(assinada.raw_transaction).hex()

    # Envia 90% → Pool de Liquidez
    try:
        tx_hash_pool = _enviar(addr_pool, raw_pool, nonce)
    except Exception as e:
        return {"status": "ERRO", "mensagem": f"Falha ao enviar para Pool: {e}"}

    # Envia 10% → Aerarium (nonce + 1)
    try:
        tx_hash_aerarium = _enviar(addr_aerarium, raw_aerarium, nonce + 1)
    except Exception as e:
        # Pool já enviado — registra parcial para não perder o tx
        plegma_db.salvar_estado("distribuicao_tx_pool",        tx_hash_pool)
        plegma_db.salvar_estado("distribuicao_aerarium_erro",  str(e))
        return {
            "status"   : "PARCIAL",
            "tx_pool"  : tx_hash_pool,
            "mensagem" : f"Pool enviado mas falha no Aerarium: {e}. Verifique manualmente."
        }

    # Persiste resultado
    agora = time.time()
    plegma_db.salvar_estado("distribuicao_genesis_executada", True)
    plegma_db.salvar_estado("distribuicao_tx_pool",           tx_hash_pool)
    plegma_db.salvar_estado("distribuicao_tx_aerarium",       tx_hash_aerarium)
    plegma_db.salvar_estado("distribuicao_genesis_ts",        agora)
    plegma_db.salvar_estado("distribuicao_valor_pool",        valor_pool)
    plegma_db.salvar_estado("distribuicao_valor_aerarium",    valor_aerarium)

    ts_str = datetime.fromtimestamp(agora).strftime('%d/%m/%Y %H:%M')
    _log.info(f"[GENESIS V4.0] DISTRIBUIÇÃO CONCLUÍDA em {ts_str}")
    _log.info(f"[GENESIS V4.0]   Pool Liquidez : ${valor_pool:,.2f} USDC → {addr_pool} | tx: {tx_hash_pool[:20]}...")
    _log.info(f"[GENESIS V4.0]   Aerarium      : ${valor_aerarium:,.2f} USDC → {addr_aerarium} | tx: {tx_hash_aerarium[:20]}...")

    return {
        "status"          : "DISTRIBUIDO",
        "executada_em"    : ts_str,
        "saldo_total_usdc": saldo_usdc,
        "pool_liquidez"   : {"addr": addr_pool,     "valor": valor_pool,     "tx": tx_hash_pool},
        "aerarium"        : {"addr": addr_aerarium, "valor": valor_aerarium, "tx": tx_hash_aerarium},
        "mensagem"        : f"${valor_pool:,.2f} USDC (90%) → Pool | ${valor_aerarium:,.2f} USDC (10%) → Aerarium"
    }