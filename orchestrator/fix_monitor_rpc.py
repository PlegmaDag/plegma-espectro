"""
Atualiza monitor_pagamentos.py em todos os servidores:
- Múltiplos RPCs Polygon com fallback automático
- Compatibilidade web3 v6 (camelCase) e v7 (snake_case)
- Retry com backoff se RPC falha
"""
import paramiko
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from daemon_config import NODES, SSH_KEY

MONITOR_CODE = '''import time
import json
import threading
import logging
from datetime import datetime

try:
    from web3 import Web3
    _WEB3_DISPONIVEL = True
except ImportError:
    _WEB3_DISPONIVEL = False
    Web3 = None

import plegma_db
import genesis_contract

_log = logging.getLogger(__name__)

# =============================================================================
# MONITOR DE PAGAMENTOS — Detecta USDC na Polygon e emite PLG-G
# =============================================================================

# Múltiplos RPCs públicos Polygon — tenta em ordem até um funcionar
POLYGON_RPCS = [
    "https://rpc.ankr.com/polygon",
    "https://polygon-mainnet.public.blastapi.io",
    "https://gateway.tenderly.co/public/polygon",
    "https://polygon.drpc.org",
    "https://polygon-rpc.com",
    "https://rpc-mainnet.matic.quiknode.pro",
]

USDC_CONTRACT_ADDR = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"  # USDC.e Polygon
USDC_DECIMALS      = 6
INTERVALO_SEGUNDOS = 60
TOLERANCIA_USD     = 0.02

USDC_ABI = json.loads(\'[{"anonymous":false,"inputs":[{"indexed":true,"name":"from","type":"address"},{"indexed":true,"name":"to","type":"address"},{"indexed":false,"name":"value","type":"uint256"}],"name":"Transfer","type":"event"},{"inputs":[{"name":"account","type":"address"}],"name":"balanceOf","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[{"name":"to","type":"address"},{"name":"value","type":"uint256"}],"name":"transfer","outputs":[{"name":"","type":"bool"}],"stateMutability":"nonpayable","type":"function"}]\')

_ativo   = False
_thread  = None

# Detecta versão web3 (v6 usa camelCase, v7 usa snake_case)
def _web3_version() -> int:
    try:
        import web3
        ver = getattr(web3, "__version__", "7.0.0")
        return int(str(ver).split(".")[0])
    except Exception:
        return 7

_W3_MAJOR = _web3_version()


def configurar(carteira: str):
    plegma_db.salvar_estado("carteira_recebimento", carteira.lower())
    _log.info(f"[MONITOR] Carteira configurada: {carteira}")


def _get_carteira() -> str:
    return plegma_db.carregar_estado("carteira_recebimento", "")


def _conectar_rpc() -> object:
    """Tenta cada RPC em ordem até conseguir conexão. Retorna instância w3 ou None."""
    for rpc in POLYGON_RPCS:
        try:
            w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 12}))
            bloco = w3.eth.block_number
            if bloco and bloco > 0:
                _log.info(f"[MONITOR] RPC ok: {rpc} | bloco {bloco}")
                return w3
        except Exception as e:
            _log.info(f"[MONITOR] RPC falhou {rpc}: {type(e).__name__}")
    return None


def _get_logs(contrato, from_block: int, to_block: int, carteira: str) -> list:
    """Busca eventos Transfer compatível com web3 v6 e v7."""
    addr = Web3.to_checksum_address(carteira)
    if _W3_MAJOR >= 7:
        return contrato.events.Transfer.get_logs(
            from_block=from_block,
            to_block=to_block,
            argument_filters={"to": addr}
        )
    else:
        # web3 v6 usa camelCase
        return contrato.events.Transfer.get_logs(
            fromBlock=from_block,
            toBlock=to_block,
            argument_filters={"to": addr}
        )


def _processar_evento(evento):
    tx_hash       = evento["transactionHash"].hex()
    valor_raw     = evento["args"]["value"]
    usdc_recebido = valor_raw / (10 ** USDC_DECIMALS)

    if usdc_recebido < 0.05:
        return
    if plegma_db.tx_externo_ja_processado(tx_hash):
        return

    _log.info(f"[MONITOR] Pagamento: {usdc_recebido:.2f} USDC | tx: {tx_hash[:20]}...")

    pending     = plegma_db.listar_pending_aguardando()
    plg_address = None
    ref_id      = None

    for p in pending:
        if abs(p["usdt_amount"] - usdc_recebido) <= TOLERANCIA_USD:
            plg_address = p["plg_address"]
            ref_id      = p["ref_id"]
            break

    if not plg_address:
        _log.info(f"[MONITOR] Sem registro para {usdc_recebido:.2f} USDC. Guardando.")
        plegma_db.salvar_estado(
            f"sem_registro_{tx_hash[:16]}",
            {"tx_hash": tx_hash, "usdc": usdc_recebido}
        )
        return

    resultado = genesis_contract.confirmar_compra(
        tx_hash_externo=tx_hash,
        plg_address=plg_address,
        usdt_recebido=usdc_recebido,
        ref_id=ref_id
    )

    if resultado.get("status") == "CONFIRMADO":
        _log.info(f"[MONITOR] PLG-G emitido: {resultado[\'plgg_emitido\']:.2f} -> {plg_address[:16]}...")
    else:
        _log.info(f"[MONITOR] Falha: {resultado.get(\'erro\')}")


def _loop_monitor():
    global _ativo
    _ativo = True

    carteira = _get_carteira()
    if not carteira:
        _log.info("[MONITOR] Carteira nao configurada.")
        _ativo = False
        return

    # Tentar conectar ao RPC — retry até 3x com espera
    w3 = None
    for tentativa in range(3):
        w3 = _conectar_rpc()
        if w3:
            break
        _log.info(f"[MONITOR] Todos RPCs falharam (tentativa {tentativa+1}/3). Aguardando 30s...")
        time.sleep(30)

    if not w3:
        _log.info("[MONITOR] Nao foi possivel conectar a nenhum RPC Polygon. Monitor inativo.")
        _ativo = False
        return

    contrato = w3.eth.contract(
        address=Web3.to_checksum_address(USDC_CONTRACT_ADDR),
        abi=USDC_ABI
    )

    ultimo_bloco = plegma_db.carregar_estado("monitor_ultimo_bloco", None)
    if not ultimo_bloco:
        ultimo_bloco = w3.eth.block_number
        plegma_db.salvar_estado("monitor_ultimo_bloco", ultimo_bloco)

    _log.info(f"[MONITOR] Ativo | carteira={carteira[:16]}... | bloco={ultimo_bloco} | web3=v{_W3_MAJOR}")

    falhas_consecutivas = 0
    while _ativo:
        try:
            bloco_atual = w3.eth.block_number

            if bloco_atual > ultimo_bloco:
                eventos = _get_logs(contrato, ultimo_bloco + 1, bloco_atual, carteira)
                for evento in eventos:
                    _processar_evento(evento)
                ultimo_bloco = bloco_atual
                plegma_db.salvar_estado("monitor_ultimo_bloco", ultimo_bloco)
                falhas_consecutivas = 0

        except Exception as e:
            falhas_consecutivas += 1
            _log.info(f"[MONITOR] Erro no loop: {e}")
            if falhas_consecutivas >= 5:
                # Tentar reconectar ao RPC
                _log.info("[MONITOR] Reconectando ao RPC...")
                w3_novo = _conectar_rpc()
                if w3_novo:
                    w3 = w3_novo
                    contrato = w3.eth.contract(
                        address=Web3.to_checksum_address(USDC_CONTRACT_ADDR),
                        abi=USDC_ABI
                    )
                    falhas_consecutivas = 0
                else:
                    time.sleep(60)

        _verificar_dia_30()
        time.sleep(INTERVALO_SEGUNDOS)


def _verificar_dia_30():
    launch_ts = plegma_db.carregar_estado("genesis_launch_date", None)
    if not launch_ts:
        return
    dias = (time.time() - launch_ts) / 86400
    if dias < 30:
        return
    if not plegma_db.carregar_estado("governance_active", False):
        r = genesis_contract.activate_governance()
        _log.info(f"[MONITOR] Dia 30+ → governança: {r.get(\'status\')}")
    if not plegma_db.carregar_estado("liquidity_injected", False):
        r = genesis_contract.liquidity_injection()
        _log.info(f"[MONITOR] liquidity_injection → {r.get(\'status\')}")


def iniciar():
    global _ativo, _thread
    if not _WEB3_DISPONIVEL:
        _log.info("[MONITOR] web3 nao instalado — monitor desativado.")
        return
    carteira = _get_carteira()
    if not carteira:
        _log.info("[MONITOR] Carteira nao configurada.")
        return
    if _ativo and _thread and _thread.is_alive():
        _log.info("[MONITOR] Ja esta rodando.")
        return
    _ativo = False  # reset para forcar reinicio se thread morreu
    _thread = threading.Thread(target=_loop_monitor, name="monitor_pagamentos", daemon=True)
    _thread.start()
    _log.info("[MONITOR] Thread iniciada.")


def parar():
    global _ativo
    _ativo = False
    _log.info("[MONITOR] Parando...")


# =============================================================================
# DISTRIBUIÇÃO GENESIS
# =============================================================================

def executar_distribuicao_usdc(chave_privada: str) -> dict:
    if plegma_db.carregar_estado("distribuicao_genesis_executada", False):
        tx_pool     = plegma_db.carregar_estado("distribuicao_tx_pool",     None)
        tx_aerarium = plegma_db.carregar_estado("distribuicao_tx_aerarium", None)
        ts          = plegma_db.carregar_estado("distribuicao_genesis_ts",  None)
        ts_str      = datetime.fromtimestamp(ts).strftime(\'%d/%m/%Y %H:%M\') if ts else "desconhecido"
        return {"status": "JA_EXECUTADA", "executada_em": ts_str,
                "tx_pool": tx_pool, "tx_aerarium": tx_aerarium}

    if not plegma_db.carregar_estado("governance_active", False):
        return {"status": "ERRO", "mensagem": "Governança nao ativa."}

    destinos = genesis_contract.get_carteiras_destino_polygon()
    if not destinos["prontas"]:
        return {"status": "ERRO", "mensagem": "Carteiras destino nao registradas."}

    addr_pool     = Web3.to_checksum_address(destinos["pool_liquidez"])
    addr_aerarium = Web3.to_checksum_address(destinos["aerarium"])

    w3 = _conectar_rpc()
    if not w3:
        return {"status": "ERRO", "mensagem": "Nao foi possivel conectar ao RPC Polygon."}

    try:
        conta = w3.eth.account.from_key(chave_privada)
    except Exception:
        return {"status": "ERRO", "mensagem": "Chave privada invalida."}

    contrato_usdc = w3.eth.contract(
        address=Web3.to_checksum_address(USDC_CONTRACT_ADDR), abi=USDC_ABI)

    saldo_raw  = contrato_usdc.functions.balanceOf(conta.address).call()
    saldo_usdc = saldo_raw / (10 ** USDC_DECIMALS)

    if saldo_usdc < 0.01:
        return {"status": "AVISO", "mensagem": f"Saldo insuficiente: ${saldo_usdc:.2f}"}

    raw_pool     = int(saldo_raw * genesis_contract.GENESIS_LIQUIDEZ_SHARE)
    raw_aerarium = saldo_raw - raw_pool
    valor_pool     = round(raw_pool     / (10 ** USDC_DECIMALS), 2)
    valor_aerarium = round(raw_aerarium / (10 ** USDC_DECIMALS), 2)

    nonce = w3.eth.get_transaction_count(conta.address)

    def _enviar(to_addr, raw_valor, nonce_tx):
        tx = contrato_usdc.functions.transfer(to_addr, raw_valor).build_transaction({
            "from": conta.address, "nonce": nonce_tx,
            "gas": 80_000, "gasPrice": w3.eth.gas_price, "chainId": 137
        })
        assinada = w3.eth.account.sign_transaction(tx, chave_privada)
        return w3.eth.send_raw_transaction(assinada.raw_transaction).hex()

    try:
        tx_hash_pool = _enviar(addr_pool, raw_pool, nonce)
    except Exception as e:
        return {"status": "ERRO", "mensagem": f"Falha ao enviar para Pool: {e}"}

    try:
        tx_hash_aerarium = _enviar(addr_aerarium, raw_aerarium, nonce + 1)
    except Exception as e:
        plegma_db.salvar_estado("distribuicao_tx_pool",       tx_hash_pool)
        plegma_db.salvar_estado("distribuicao_aerarium_erro", str(e))
        return {"status": "PARCIAL", "tx_pool": tx_hash_pool,
                "mensagem": f"Pool enviado mas falha no Aerarium: {e}"}

    agora = time.time()
    plegma_db.salvar_estado("distribuicao_genesis_executada", True)
    plegma_db.salvar_estado("distribuicao_tx_pool",           tx_hash_pool)
    plegma_db.salvar_estado("distribuicao_tx_aerarium",       tx_hash_aerarium)
    plegma_db.salvar_estado("distribuicao_genesis_ts",        agora)

    ts_str = datetime.fromtimestamp(agora).strftime(\'%d/%m/%Y %H:%M\')
    _log.info(f"[GENESIS] DISTRIBUICAO CONCLUIDA em {ts_str}")

    return {
        "status": "DISTRIBUIDO", "executada_em": ts_str,
        "saldo_total_usdc": saldo_usdc,
        "pool_liquidez":    {"addr": addr_pool,     "valor": valor_pool,     "tx": tx_hash_pool},
        "aerarium":         {"addr": addr_aerarium, "valor": valor_aerarium, "tx": tx_hash_aerarium},
        "mensagem": f"${valor_pool:,.2f} (90%) Pool | ${valor_aerarium:,.2f} (10%) Aerarium"
    }
'''

VERIFY_SCRIPT = """
import sys
sys.path.insert(0, '/root/PLEGMA_CORE')
import monitor_pagamentos
import importlib
importlib.reload(monitor_pagamentos)

print(f"web3 major: {monitor_pagamentos._W3_MAJOR}")
print(f"_ativo antes: {monitor_pagamentos._ativo}")

# Testar conectividade RPC
w3 = monitor_pagamentos._conectar_rpc()
if w3:
    print(f"RPC ok | bloco: {w3.eth.block_number}")
else:
    print("FALHOU: nenhum RPC disponivel")

# Verificar carteira configurada
carteira = monitor_pagamentos._get_carteira()
print(f"carteira: {carteira[:16] if carteira else 'NAO CONFIGURADA'}...")
"""

import paramiko

REMOTE_PATH = "/root/PLEGMA_CORE/monitor_pagamentos.py"

key = paramiko.Ed25519Key.from_private_key_file(SSH_KEY)

for node_id, node in NODES.items():
    try:
        c = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        c.connect(node['ip'], username='root', pkey=key, timeout=12)
        transport = c.get_transport()
        if transport:
            transport.set_keepalive(20)

        # Backup
        c.exec_command(f"cp {REMOTE_PATH} {REMOTE_PATH}.bak")

        # Upload novo ficheiro
        sftp = c.open_sftp()
        with sftp.open(REMOTE_PATH, 'w') as f:
            f.write(MONITOR_CODE)

        # Verificar
        with sftp.open('/tmp/verify_mon.py', 'w') as f:
            f.write(VERIFY_SCRIPT)
        sftp.close()

        _, stdout, stderr = c.exec_command(
            'cd /root/PLEGMA_CORE && python3 /tmp/verify_mon.py; rm -f /tmp/verify_mon.py',
            timeout=40
        )
        out = stdout.read().decode()
        err = stderr.read().decode()

        print(f"\n=== {node['label']} — upload + verify ===")
        print(out)
        if err.strip() and 'DeprecationWarning' not in err and 'RequestsDependencyWarning' not in err:
            print("ERR:", err[:200])

        c.close()
    except Exception as e:
        print(f"\n=== {node['label']} === ERRO: {e}")

print("\nDone. Reiniciar plegma-core em todos os servidores...")
