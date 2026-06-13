import json
import logging
import time
import threading
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

_log = logging.getLogger(__name__)

from lattice_shield import LatticeShield
from aerarium import AerariumProtocol, TIPO_VALIDATOR, TIPO_PROVER
from wallet import PlegmaWallet
from tx_verifier import verificar_sessao_header, verificar_tx
import plegma_db
import aerarium_swap

# ── Blindagem de Oráculo Determinístico (Hard Fail) ─────────
try:
    import blake3 as _blake3
except ImportError:
    raise RuntimeError("[FALHA FATAL] Módulo blake3 ausente no Wallet Server.")

def _b3_hash(data: bytes) -> str:
    return _blake3.blake3(data).hexdigest()

# =============================================================================
# WALLET SERVER — API HTTP para o Dashboard V4.0 (PÓS-QUÂNTICO)
# Porta: 8083
#
# Rotas:
#   GET  /wallet/status          — saldos, pools, vesting resumido
#   GET  /wallet/vesting         — contratos de vesting detalhados
#   GET  /wallet/extrato         — histórico de transações
#   GET  /wallet/provers         — Provers vinculados
#   GET  /wallet/stats           — estatísticas completas
#   POST /wallet/transferir      — envia $PLG para outro endereço
#   POST /wallet/vincular_prover — vincula um novo Prover
# =============================================================================

# =============================================================================
# INSTÂNCIA GLOBAL DA WALLET (em memória — sem dados de demonstração)
# =============================================================================
def _criar_wallet_vazia() -> PlegmaWallet:
    shield   = LatticeShield()
    shield.generate_wallet()
    aerarium = AerariumProtocol(launch_date=datetime.now())
    return PlegmaWallet(shield, aerarium)

_wallet: PlegmaWallet = _criar_wallet_vazia()
_lock = threading.Lock()
_ofertas_p2p = {}
import blake3 as _blake3

# Endereço de custódia determinístico para reserva de PLG-G em ofertas P2P.
# Derivado de BLAKE3("PLEGMA_PLGG_P2P_ESCROW_ADDRESS_2026") — sem chave privada.
PLGG_ESCROW_ADDR = "PLG" + _blake3.blake3(b"PLEGMA_PLGG_P2P_ESCROW_ADDRESS_2026").hexdigest()[:40].upper()


# =============================================================================
# HANDLER HTTP
# =============================================================================
_CORS_ORIGINS = {"https://plegmadag.com", "https://plagmadag.com"}

class WalletHandler(BaseHTTPRequestHandler):

    def _cors(self):
        origin = self.headers.get("Origin", "")
        self.send_header("Access-Control-Allow-Origin",
                         origin if origin in _CORS_ORIGINS else "https://plegmadag.com")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def _json(self, status: int, data: dict):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            return {}

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path   = parsed.path
        params = parse_qs(parsed.query)

        with _lock:
            if path == "/wallet/status":
                stats  = _wallet.get_stats_dashboard()
                pools  = _wallet.aerarium.get_pools_status()
                vesting= _wallet.get_vesting_pendente()

                self._json(200, {
                    "plg_address"      : stats["plg_address"],
                    "disponivel"       : round(stats["saldo_disponivel"], 4),
                    "vesting_locked"   : round(stats["saldo_vesting"], 4),
                    "total_estimado"   : round(stats["total_estimado"], 4),
                    "minerado_total"   : round(stats["minerado_total"], 4),
                    "enviado_total"    : round(stats["enviado_total"], 4),
                    "recebido_total"   : round(stats["recebido_total"], 4),
                    "vesting_validator": round(stats["vesting_validator"], 4),
                    "vesting_prover"   : round(stats["vesting_prover"], 4),
                    "provers_vinculados": stats["provers_vinculados"],
                    "proxima_liberacao": stats["proxima_liberacao"],
                    "validator_pool_rede": round(pools["validator_pool"], 2),
                    "prover_pool_rede"   : round(pools["prover_pool"], 2),
                    "total_emitido"      : round(pools["total_emitido"], 4),
                    "proximos_vestings"  : vesting[:3]
                })

            elif path == "/wallet/vesting":
                todos   = [v.to_dict() for v in _wallet.vestings]
                locked  = [v for v in todos if v["status"] == "BLOQUEADO"]
                liberado= [v for v in todos if v["status"] == "LIBERADO"]
                self._json(200, {
                    "locked"  : locked,
                    "liberado": liberado,
                    "total_locked"  : round(sum(v["amount"] for v in locked), 4),
                    "total_liberado": round(sum(v["amount"] for v in liberado), 4)
                })

            elif path == "/wallet/extrato":
                filtro = params.get("filtro", [None])[0]
                limite = int(params.get("limite", [20])[0])
                self._json(200, {
                    "extrato": _wallet.get_extrato(limite=limite, filtro=filtro),
                    "total"  : len(_wallet.historico)
                })

            elif path == "/wallet/provers":
                address = params.get("address", [None])[0] or ""
                provers = []
                import time as _time
                ttl_cutoff = _time.time() - 900
                if address:
                    with plegma_db.get_connection() as _conn:
                        rows = _conn.execute(
                            "SELECT node_id, node_type, categoria, score, amount, created_at "
                            "FROM miner_vesting WHERE plg_address = ? AND pool = 'PROVER_POOL' "
                            "ORDER BY created_at DESC",
                            (address,)
                        ).fetchall()
                    _ANCHOR_TYPES = {'VALIDATOR', 'ANCHOR'}
                    for row in rows:
                        nt = row[1] or ""
                        cat = row[2] or nt or "DESKTOP"
                        provers.append({
                            "node_id"    : row[0] or "",
                            "categoria"  : "SERVER" if nt in _ANCHOR_TYPES else cat,
                            "tipo"       : "ANCORA" if nt in _ANCHOR_TYPES else "PROVER",
                            "score"      : int(row[3] or 0),
                            "ganhos_total": float(row[4] or 0),
                            "ativo"      : True,
                            "ultimo_ping": "",
                        })
                    # Inclui mineradores ativos via heartbeat (nos_rede) ainda não em miner_vesting
                    # Inclui VALIDATOR e ANCHOR (nós âncora da rede) além de PROVER/DESKTOP/MINER
                    ids_existentes = {p["node_id"] for p in provers}
                    with plegma_db.get_connection() as _cn:
                        nos_rows = _cn.execute(
                            "SELECT node_id, node_type, last_seen FROM nos_rede "
                            "WHERE plg_address = ? "
                            "AND node_type IN ('PROVER','DESKTOP','MINER','VALIDATOR','ANCHOR') "
                            "AND last_seen > ?",
                            (address, ttl_cutoff)
                        ).fetchall()
                    _ANCHOR_TYPES = {'VALIDATOR', 'ANCHOR'}
                    for nr in nos_rows:
                        if nr[0] not in ids_existentes:
                            nt = nr[1] or "DESKTOP"
                            provers.append({
                                "node_id"    : nr[0] or "",
                                "categoria"  : "SERVER" if nt in _ANCHOR_TYPES else nt,
                                "tipo"       : "ANCORA" if nt in _ANCHOR_TYPES else "PROVER",
                                "score"      : 0,
                                "ganhos_total": 0.0,
                                "ativo"      : True,
                                "ultimo_ping": "",
                            })
                count_val = 0
                if address:
                    with plegma_db.get_connection() as _c2:
                        row_val = _c2.execute(
                            "SELECT COUNT(*) FROM nos_rede "
                            "WHERE plg_address = ? AND node_type IN ('VALIDATOR','PROVER') "
                            "AND last_seen > ?",
                            (address, ttl_cutoff)
                        ).fetchone()
                    count_val = int(row_val[0]) if row_val else 0
                self._json(200, {
                    "provers"          : provers,
                    "total_ganhos"     : round(sum(p["ganhos_total"] for p in provers), 4),
                    "count_provers"    : len(provers),
                    "count_validadores": count_val,
                })

            elif path == "/wallet/stats":
                self._json(200, _wallet.get_stats_dashboard())

            elif path == "/pool/cotacao":
                self._json(200, aerarium_swap.get_cotacao())

            elif path == "/pool/status":
                self._json(200, aerarium_swap.get_pool_status())

            elif path == "/wallet/oferta_plgg/pendente":
                address = params.get("address", [None])[0] or ""
                oferta = None
                if address:
                    oferta = next((v for v in _ofertas_p2p.values()
                                   if v["comprador"] == address and v["status"] == "PENDENTE"), None)
                    if not oferta:
                        with plegma_db.get_connection() as _conn:
                            row = _conn.execute(
                                "SELECT oferta_id, vendedor, comprador, amount_plgg, preco_unitario, status, created_at "
                                "FROM plgg_ofertas WHERE comprador = ? AND status = 'PENDENTE' "
                                "ORDER BY created_at DESC LIMIT 1",
                                (address,)
                            ).fetchone()
                        if row:
                            oferta = dict(row)
                if oferta:
                    self._json(200, oferta)
                else:
                    self._json(404, {"erro": "Nenhuma oferta pendente."})

            else:
                self._json(404, {"erro": "Rota não encontrada."})

    def do_POST(self):
        parsed = urlparse(self.path)
        path   = parsed.path
        body   = self._body()

        with _lock:
            if path == "/wallet/transferir":
                ok_sess, sess_info = verificar_sessao_header(self.headers)
                if not ok_sess:
                    self._json(401, {"erro": f"Não autorizado: {sess_info}"})
                    return

                plg_address = sess_info

                dest      = body.get("destinatario", "")
                amount_raw= body.get("amount", 0)
                signature = body.get("signature", "")
                public_key= body.get("public_key", "")

                if not dest or not signature or not public_key:
                    self._json(400, {"erro": "Campos obrigatórios: destinatario, amount, signature, public_key"})
                    return

                import math as _math
                try:
                    amount = float(amount_raw)
                    if _math.isnan(amount) or _math.isinf(amount) or amount <= 0:
                        raise ValueError
                except (ValueError, TypeError):
                    self._json(400, {"erro": "Campo 'amount' inválido."})
                    return

                tx_mensagem = f"{plg_address}:{dest}:{amount}"
                ok_sig, motivo = verificar_tx(
                    sender        = plg_address,
                    public_key_hex= public_key,
                    signature     = signature,
                    mensagem      = tx_mensagem
                )
                if not ok_sig:
                    _log.info(f"[WALLET][BLOQUEADO] Transferência inválida de {plg_address[:16]}... — {motivo}")
                    self._json(401, {"erro": f"Assinatura inválida: {motivo}"})
                    return

                result = _wallet.transferir(dest, amount)
                status = 200 if result["ok"] else 400
                self._json(status, result)

            elif path == "/wallet/vincular_prover":
                node_id     = body.get("node_id", "").strip()
                categoria   = body.get("categoria", "DESKTOP").strip()
                score       = int(body.get("score", 0))
                plg_address = body.get("plg_address", "").strip()
                if not node_id:
                    self._json(400, {"erro": "node_id obrigatório."})
                    return
                if not plg_address:
                    self._json(400, {"erro": "plg_address obrigatório."})
                    return
                plegma_db.salvar_vesting(plg_address, {
                    "amount"      : 0,
                    "release_date": "",
                    "status"      : "ATIVO",
                    "node_type"   : "PROVER",
                    "pool"        : "PROVER_POOL",
                    "node_id"     : node_id,
                    "categoria"   : categoria,
                    "score"       : score,
                })
                self._json(200, {"ok": True, "node_id": node_id})

            elif path == "/wallet/desvincular_prover":
                node_id     = body.get("node_id", "").strip()
                plg_address = body.get("plg_address", "").strip()
                if not node_id:
                    self._json(400, {"erro": "node_id obrigatório."})
                    return
                if not plg_address:
                    self._json(400, {"erro": "plg_address obrigatório."})
                    return
                with plegma_db.get_connection() as _conn:
                    _conn.execute(
                        "DELETE FROM miner_vesting WHERE node_id = ? AND plg_address = ?",
                        (node_id, plg_address)
                    )
                self._json(200, {"ok": True, "node_id": node_id})

            elif path == "/wallet/oferta_plgg":
                ok_sess, sess_info = verificar_sessao_header(self.headers)
                if not ok_sess:
                    self._json(401, {"erro": f"Não autorizado: {sess_info}"})
                    return
                vendedor = sess_info
                comprador = body.get("comprador", "").strip()
                import math as _math
                try:
                    amount = float(body.get("amount_plgg", 0))
                    preco = float(body.get("preco_unitario", 0))
                    if _math.isnan(amount) or _math.isinf(amount) or amount <= 0:
                        raise ValueError
                    if _math.isnan(preco) or _math.isinf(preco) or preco <= 0:
                        raise ValueError
                except (ValueError, TypeError):
                    self._json(400, {"erro": "Valores numéricos inválidos."})
                    return
                if not comprador or comprador == vendedor:
                    self._json(400, {"erro": "Comprador inválido."})
                    return
                import genesis_contract as _gc
                reserva = _gc.transferir_plgg(vendedor, PLGG_ESCROW_ADDR, amount, interno=True)
                if reserva.get("status") != "TRANSFERIDO":
                    self._json(400, reserva)
                    return
                oferta_id = "OFT_" + _blake3.blake3(
                    f"OFERTA:{vendedor}:{comprador}:{amount}:{preco}:{int(time.time())}".encode()
                ).hexdigest()[:16].upper()
                oferta = {
                    "oferta_id": oferta_id,
                    "vendedor": vendedor,
                    "comprador": comprador,
                    "amount_plgg": amount,
                    "preco_unitario": preco,
                    "status": "PENDENTE",
                    "created_at": time.time(),
                }
                plegma_db.salvar_plgg_oferta(oferta)
                _ofertas_p2p[oferta_id] = oferta
                self._json(200, {"ok": True, "oferta_id": oferta_id})

            elif path == "/wallet/transferir_plgg":
                ok_sess, sess_info = verificar_sessao_header(self.headers)
                if not ok_sess:
                    self._json(401, {"erro": f"Não autorizado: {sess_info}"})
                    return

                from_addr  = sess_info
                dest       = body.get("destinatario", "").strip()
                amount_raw = body.get("amount", 0)

                import math as _math
                try:
                    amount = float(amount_raw)
                    if _math.isnan(amount) or _math.isinf(amount) or amount <= 0:
                        raise ValueError
                except (ValueError, TypeError):
                    self._json(400, {"erro": "Campo 'amount' inválido."})
                    return

                if not dest:
                    self._json(400, {"erro": "Destinatário obrigatório."})
                    return

                if dest == from_addr:
                    self._json(400, {"erro": "Não pode enviar para si mesmo."})
                    return

                import genesis_contract as _gc
                result = _gc.transferir_plgg(from_addr, dest, amount, confirmado=True, interno=True)

                if result.get("status") == "TRANSFERIDO":
                    self._json(200, {"ok": True, "tx_id": result.get("tx_hash", ""),
                                     "de": from_addr, "para": dest, "amount": amount})
                else:
                    self._json(400, result)

            elif path == "/wallet/oferta_plgg/responder":
                ok_sess, sess_info = verificar_sessao_header(self.headers)
                if not ok_sess:
                    self._json(401, {"erro": f"Não autorizado: {sess_info}"})
                    return
                comprador_sess = sess_info
                oferta_id = body.get("oferta_id", "")
                aceitar = bool(body.get("aceitar", False))
                oferta = _ofertas_p2p.get(oferta_id) or plegma_db.carregar_plgg_oferta(oferta_id)
                if not oferta or oferta["comprador"] != comprador_sess:
                    self._json(404, {"erro": "Oferta não encontrada."})
                    return
                if oferta["status"] != "PENDENTE":
                    self._json(400, {"erro": f"Oferta já {oferta['status']}."})
                    return
                import genesis_contract as _gc
                if aceitar:
                    resultado = _gc.transferir_plgg(
                        PLGG_ESCROW_ADDR, comprador_sess, oferta["amount_plgg"],
                        interno=True, preco_unitario=oferta["preco_unitario"]
                    )
                    novo_status = "ACEITA"
                else:
                    resultado = _gc.transferir_plgg(
                        PLGG_ESCROW_ADDR, oferta["vendedor"], oferta["amount_plgg"],
                        interno=True
                    )
                    novo_status = "REJEITADA"
                if resultado.get("status") != "TRANSFERIDO":
                    self._json(500, {"erro": "Falha ao executar transferência.", "detalhe": resultado})
                    return
                plegma_db.atualizar_status_plgg_oferta(oferta_id, novo_status)
                if oferta_id in _ofertas_p2p:
                    _ofertas_p2p[oferta_id]["status"] = novo_status
                self._json(200, {"ok": True, "status": novo_status, "tx_hash": resultado.get("tx_hash", "")})

            elif path == "/pool/comprar":
                ok_sess, sess_info = verificar_sessao_header(self.headers)
                if not ok_sess:
                    self._json(401, {"erro": f"Não autorizado: {sess_info}"})
                    return

                plg_address  = sess_info
                usdc_raw     = body.get("usdc_amount", 0)

                import math as _math
                try:
                    usdc_amount = float(usdc_raw)
                    if _math.isnan(usdc_amount) or _math.isinf(usdc_amount) or usdc_amount <= 0:
                        raise ValueError
                except (ValueError, TypeError):
                    self._json(400, {"erro": "Campo 'usdc_amount' inválido."})
                    return

                resultado = aerarium_swap.registrar_compra(plg_address, usdc_amount)
                status    = 200 if resultado.get("ok") else 400
                self._json(status, resultado)

            elif path == "/pool/vender":
                ok_sess, sess_info = verificar_sessao_header(self.headers)
                if not ok_sess:
                    self._json(401, {"erro": f"Não autorizado: {sess_info}"})
                    return

                plg_address     = sess_info
                polygon_address = body.get("polygon_address", "").strip()
                plg_raw         = body.get("plg_amount", 0)

                import math as _math
                try:
                    plg_amount = float(plg_raw)
                    if _math.isnan(plg_amount) or _math.isinf(plg_amount) or plg_amount <= 0:
                        raise ValueError
                except (ValueError, TypeError):
                    self._json(400, {"erro": "Campo 'plg_amount' inválido."})
                    return

                resultado = aerarium_swap.registrar_venda(plg_address, plg_amount, polygon_address)
                status    = 200 if resultado.get("ok") else 400
                self._json(status, resultado)

            elif path == "/pool/configurar":
                host = self.headers.get("Host", "")
                if not (host.startswith("localhost") or host.startswith("127.0.0.1")):
                    self._json(403, {"erro": "Acesso restrito ao servidor local."})
                    return

                admin_token = body.get("admin_token", "")
                token_salvo = plegma_db.carregar_estado("admin_token_hash", "")
                if not token_salvo or _b3_hash(admin_token.encode()) != token_salvo:
                    self._json(403, {"erro": "Token admin inválido (BLAKE3 mismatch)."})
                    return

                try:
                    taxa = float(body.get("taxa", 0))
                except (ValueError, TypeError):
                    self._json(400, {"erro": "taxa deve ser numérica."})
                    return

                resultado = aerarium_swap.configurar_pool(taxa)
                status    = 200 if resultado.get("ok") else 400
                self._json(status, resultado)

            elif path == "/pool/confirmar_venda":
                host = self.headers.get("Host", "")
                if not (host.startswith("localhost") or host.startswith("127.0.0.1")):
                    self._json(403, {"erro": "Acesso restrito ao servidor local."})
                    return

                admin_token = body.get("admin_token", "")
                token_salvo = plegma_db.carregar_estado("admin_token_hash", "")
                if not token_salvo or _b3_hash(admin_token.encode()) != token_salvo:
                    self._json(403, {"erro": "Token admin inválido (BLAKE3 mismatch)."})
                    return

                ref_id      = body.get("ref_id", "")
                tx_hash_pol = body.get("tx_hash_polygon", "")
                if not ref_id or not tx_hash_pol:
                    self._json(400, {"erro": "ref_id e tx_hash_polygon obrigatórios."})
                    return

                resultado = aerarium_swap.confirmar_venda_admin(ref_id, tx_hash_pol)
                status    = 200 if resultado.get("ok") else 400
                self._json(status, resultado)

            else:
                self._json(404, {"erro": "Rota POST não encontrada."})

    def log_message(self, format, *args):
        return


# =============================================================================
# MAIN
# =============================================================================
if __name__ == "__main__":
    porta = 8083
    _log.info("==================================================")
    _log.info(" [!] WALLET SERVER — PLEGMA DAG V4.0 (PÓS-QUÂNTICO)")
    _log.info("==================================================")
    _log.info(f" Porta          : {porta}")
    _log.info(f" Carteira       : {_wallet.plg_address[:20]}...")
    _log.info("--------------------------------------------------")
    _log.info(f" GET  /wallet/status")
    _log.info(f" GET  /wallet/vesting")
    _log.info(f" GET  /wallet/extrato")
    _log.info(f" GET  /wallet/provers")
    _log.info(f" GET  /wallet/stats")
    _log.info(f" POST /wallet/transferir")
    _log.info(f" POST /wallet/vincular_prover")
    _log.info("--------------------------------------------------")
    _log.info(f" GET  /pool/cotacao")
    _log.info(f" GET  /pool/status")
    _log.info(f" POST /pool/comprar")
    _log.info(f" POST /pool/vender")
    _log.info(f" POST /pool/configurar        [localhost only]")
    _log.info("==================================================")

    aerarium_swap.iniciar_monitor()

    server = HTTPServer(("", porta), WalletHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        _log.info("\n[!] Wallet Server encerrado.")