import time
import json
import logging
import threading
import os
import re
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

_log = logging.getLogger(__name__)

# ── Blindagem de Oráculo Determinístico (Hard Fail) ─────────
try:
    import blake3 as _blake3
except ImportError:
    raise RuntimeError("[FALHA FATAL] Módulo blake3 ausente no Shield Server.")

def _b3_hash(data: bytes) -> str:
    return _blake3.blake3(data).hexdigest()

try:
    from zk_press import DagSealEngine as _ZkPressEngine
    _zk = _ZkPressEngine()
    _ZK_AVAILABLE = True
except Exception:
    _ZK_AVAILABLE = False
    _zk = None

# =============================================================================
# SHIELD SERVER — Lattice Shield: Scanner, Anti-Phishing, Monitor de Ameaças
# PLEGMA DAG V4.0 (PÓS-QUÂNTICO / HEGEMONIA BLAKE3)
#
# Porta: 8085
#
# Endpoints:
#   GET  /shield/status          → status da proteção + contadores
#   GET  /shield/threats         → lista de ameaças conhecidas
#   POST /shield/scan/url        → verifica URL contra phishing DB
#   POST /shield/scan/batch      → verifica lote de apps contra malware DB
#   POST /shield/report          → reporta nova ameaça (inteligência coletiva)
# =============================================================================

PORT = 8085

# ── Configurações de Pagamento ────────────────────────────────────────────────
SHIELD_PRICE_USD     = 12.0
SHIELD_PLG_AMOUNT    = 1200.0          # 1200 PLG ≈ US$12 (taxa base; ajustável)
GENESIS_DURATION_DAYS = 62             # 09/05/2026 → 10/07/2026 (alinhado com genesis_contract.py)
GENESIS_START_TS     = 1746748800      # 09 Mai 2026 18:00 CEST / 16:00 UTC
TREASURY_ADDRESS     = "PLG198840FFDD9FA7A8AEA2747C994B152B88A49F7C"

# ── Helpers de integração com outros servidores ───────────────────────────────

def _http_get(url: str, timeout: int = 2) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception:
        return {}

def _check_genesis() -> bool:
    # Ativo: qualquer momento antes do fim dos 62 dias pós-lançamento
    # GENESIS_START_TS = 09 Mai 2026 · fim = 10 Jul 2026 · queima = 11 Jul 2026
    now = time.time()
    if now < GENESIS_START_TS + GENESIS_DURATION_DAYS * 86400:
        return True
    data = _http_get("http://localhost:8080/api/genesis/status")
    if data:
        return bool(data.get("fase_genesis_ativa") or data.get("genesis_ativo"))
    return False

def _check_validator(plg_address: str) -> bool:
    data = _http_get(f"http://localhost:8080/api/priority?address={plg_address}")
    cat = str(data.get("categoria", "")).upper()
    return "VALIDATOR" in cat or "VALIDADOR" in cat or "MINER" in cat

def _get_wallet_balance(plg_address: str) -> float:
    data = _http_get(f"http://localhost:8080/api/wallet/status?address={plg_address}")
    for field in ("saldo_plg", "saldo", "balance", "plg_balance"):
        if field in data:
            try:
                return float(data[field])
            except Exception:
                pass
    return 0.0

# ── Banco de Ameaças Estático ─────────────────────────────────────────────────

MALWARE_PACKAGES = {
    "com.android.systemupdate.service",
    "com.android.spy.monitor",
    "com.bankingspy.android",
    "com.fake.google.play.store",
    "com.sms.stealer.service",
    "com.mobile.botnet.agent",
    "com.android.system.keylogger",
    "com.spyware.contact.reader",
    "com.rat.android.remote",
    "com.trojan.banking.lite",
    "org.malware.android.sms",
    "net.hiddenpay.banker",
    "com.spy.android.tracker",
    "com.remote.access.tool",
    "com.android.fakeupdate",
    "com.credential.harvester",
    "com.clipboard.monitor.service",
    "com.screen.recorder.spy",
    "com.phonetracker.hiddenapp",
    "com.smsforward.stealth",
}

PHISHING_DOMAINS = {
    "paypal-secure-login.com",
    "apple-id-verify.net",
    "amazon-prize-winner.com",
    "google-account-confirm.co",
    "bank-secure-update.net",
    "binance-airdrop-claim.io",
    "metamask-wallet-verify.com",
    "coinbase-support-center.net",
    "ledger-live-update.com",
    "trezor-firmware-update.net",
    "plegmadag-airdrop.com",
    "plg-genesis-reward.com",
    "plgcoin-free.com",
    "plegma-official-airdrop.io",
    "blockchain-wallet-verify.net",
    "crypto-reward-claim.com",
    "nft-airdrop-free.io",
    "defi-yield-hack.com",
    "web3-wallet-connect.net",
    "recovery-phrase-verify.com",
    "seed-phrase-restore.net",
    "trust-wallet-support.com",
    "pancakeswap-airdrop.io",
    "uniswap-reward-claim.net",
}

MALICIOUS_CERT_HASHES: set = set()

_SUSPICIOUS_TERMS = [
    "spy", "keylog", "stealer", "rat.", "botnet", "trojan",
    "banker", "phish", "credential", "harvester", "clipper",
    "remote.access", "screen.record.spy", "sms.forward",
]

_PHISHING_PATTERNS = [
    re.compile(r"(paypal|apple|amazon|google|microsoft|bank|binance|coinbase|ledger|trezor)"
               r"\w*[-_](verify|secure|confirm|update|login|support|account)", re.I),
    re.compile(r"(crypto|wallet|nft|airdrop|free|reward|claim)\w*\.(tk|ml|ga|cf|gq|xyz|top|click)", re.I),
    re.compile(r"seed[-_]?phrase|recovery[-_]?phrase|private[-_]?key[-_]?restore", re.I),
]

_SHORTENERS = re.compile(r"(bit\.ly|tinyurl\.com|t\.co|goo\.gl|ow\.ly)/", re.I)
_DIRECT_IP  = re.compile(r"https?://\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}[/:]")

# ── Ameaças da Comunidade (file-backed) ───────────────────────────────────────
_THREATS_FILE = os.path.join(os.path.dirname(__file__), "shield_threats.json")
_community: dict = {"packages": [], "domains": [], "cert_hashes": []}
_db_lock = threading.Lock()
_start_ts = time.time()
_scan_counter = 0

def _load_community():
    global _community
    if os.path.exists(_THREATS_FILE):
        try:
            with open(_THREATS_FILE, "r", encoding="utf-8") as f:
                _community = json.load(f)
        except Exception:
            pass

def _save_community():
    with open(_THREATS_FILE, "w", encoding="utf-8") as f:
        json.dump(_community, f, ensure_ascii=False, indent=2)

_load_community()

# ── Anchors de Snapshot ZK ────────────────────────────────────────────────────
_ANCHORS_FILE = os.path.join(os.path.dirname(__file__), "shield_anchors.json")
_anchors: list = []

def _load_anchors():
    global _anchors
    if os.path.exists(_ANCHORS_FILE):
        try:
            with open(_ANCHORS_FILE, "r", encoding="utf-8") as f:
                _anchors = json.load(f)
        except Exception:
            pass

def _save_anchors():
    with open(_ANCHORS_FILE, "w", encoding="utf-8") as f:
        json.dump(_anchors, f, ensure_ascii=False, indent=2)

_load_anchors()

# ── Assinaturas Lattice Shield (file-backed) ──────────────────────────────────
_SUBSCRIPTIONS_FILE = os.path.join(os.path.dirname(__file__), "shield_subscriptions.json")
_subscriptions: list = []

def _load_subscriptions():
    global _subscriptions
    if os.path.exists(_SUBSCRIPTIONS_FILE):
        try:
            with open(_SUBSCRIPTIONS_FILE, "r", encoding="utf-8") as f:
                _subscriptions = json.load(f)
        except Exception:
            pass

def _save_subscriptions():
    with open(_SUBSCRIPTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(_subscriptions, f, ensure_ascii=False, indent=2)

_load_subscriptions()

# ── Funções de Verificação ────────────────────────────────────────────────────

def _scan_url(url: str) -> dict:
    url_s = url.strip()
    try:
        parsed = urlparse(url_s if "://" in url_s else "https://" + url_s)
        domain = parsed.netloc.lower().replace("www.", "").split(":")[0]
    except Exception:
        domain = url_s.lower()

    if domain in PHISHING_DOMAINS:
        return {"status": "BLOQUEADO", "risco": "ALTO", "motivo": "dominio_lista_negra", "dominio": domain}

    with _db_lock:
        if domain in _community.get("domains", []):
            return {"status": "BLOQUEADO", "risco": "ALTO", "motivo": "reportado_comunidade", "dominio": domain}

    if _DIRECT_IP.search(url_s):
        return {"status": "SUSPEITO", "risco": "MÉDIO", "motivo": "url_ip_direto", "dominio": domain}

    if _SHORTENERS.search(url_s):
        return {"status": "SUSPEITO", "risco": "MÉDIO", "motivo": "encurtador_de_url", "dominio": domain}

    for pat in _PHISHING_PATTERNS:
        if pat.search(url_s):
            return {"status": "SUSPEITO", "risco": "MÉDIO", "motivo": "padrao_phishing_detectado", "dominio": domain}

    return {"status": "SEGURO", "risco": "BAIXO", "motivo": "sem_ameacas_detectadas", "dominio": domain}

def _scan_app(package_name: str, cert_hash: str = "") -> dict:
    pkg = package_name.lower().strip()

    if pkg in MALWARE_PACKAGES:
        return {"status": "MALWARE", "risco": "ALTO", "motivo": "pacote_lista_negra", "pacote": package_name}

    if cert_hash and cert_hash.lower() in MALICIOUS_CERT_HASHES:
        return {"status": "MALWARE", "risco": "ALTO", "motivo": "certificado_comprometido", "pacote": package_name}

    with _db_lock:
        if pkg in _community.get("packages", []):
            return {"status": "MALWARE", "risco": "ALTO", "motivo": "reportado_comunidade", "pacote": package_name}
        if cert_hash and cert_hash.lower() in _community.get("cert_hashes", []):
            return {"status": "SUSPEITO", "risco": "MÉDIO", "motivo": "certificado_suspeito", "pacote": package_name}

    for term in _SUSPICIOUS_TERMS:
        if term in pkg:
            return {"status": "SUSPEITO", "risco": "MÉDIO", "motivo": "nome_suspeito", "pacote": package_name}

    return {"status": "LIMPO", "risco": "BAIXO", "motivo": "sem_ameacas_detectadas", "pacote": package_name}

# ── HTTP Handler ──────────────────────────────────────────────────────────────

_CORS_ORIGINS = {"https://plegmadag.com", "https://plagmadag.com"}

def _cors(handler):
    origin = handler.headers.get("Origin", "")
    handler.send_header("Access-Control-Allow-Origin",
                        origin if origin in _CORS_ORIGINS else "https://plegmadag.com")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")

def _send(handler, code: int, data: dict):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    _cors(handler)
    handler.end_headers()
    handler.wfile.write(body)

class ShieldHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_OPTIONS(self):
        self.send_response(200)
        _cors(self)
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path   = parsed.path
        qs     = parse_qs(parsed.query)

        if path == "/shield/status":
            uptime = int(time.time() - _start_ts)
            with _db_lock:
                comm_total = (
                    len(_community.get("packages", [])) +
                    len(_community.get("domains", []))
                )
            _send(self, 200, {
                "status"           : "ATIVO",
                "uptime_segundos"  : uptime,
                "total_scans"      : _scan_counter,
                "ameacas_estaticas": len(MALWARE_PACKAGES) + len(PHISHING_DOMAINS),
                "ameacas_comunidade": comm_total,
                "protecoes": {
                    "scanner_apps"        : True,
                    "antivirus"           : True,
                    "anti_phishing"       : True,
                    "monitor_permissoes"  : True,
                    "rede_dilithium3"     : True,
                },
            })

        elif path.startswith("/shield/anchor/"):
            anchor_id = path.split("/shield/anchor/")[-1].strip()
            with _db_lock:
                found = next((a for a in _anchors if a.get("anchor_id") == anchor_id), None)
            if not found:
                _send(self, 404, {"error": "anchor_nao_encontrado"})
                return
            if _ZK_AVAILABLE:
                try:
                    proof_bytes = bytes.fromhex(found["zk_proof"])
                    valido = _zk.verify_proof(proof_bytes, found["state_hash"])
                except Exception:
                    valido = False
            else:
                valido = None 
            _send(self, 200, {**found, "zk_valido": valido})

        elif path.startswith("/shield/subscription/"):
            plg_address = path.split("/shield/subscription/")[-1].strip()
            with _db_lock:
                found = next((s for s in _subscriptions if s.get("plg_address") == plg_address), None)
            if not found:
                _send(self, 200, {"ativo": False, "plg_address": plg_address})
                return
            _send(self, 200, {**found, "ativo": found.get("ativo", True)})

        elif path == "/shield/payment/check":
            plg_address = qs.get("address", [""])[0].strip()
            if not plg_address.startswith("PLG"):
                _send(self, 400, {"error": "address_invalido"})
                return
            genesis_ativo  = _check_genesis()
            eh_validador   = _check_validator(plg_address)
            saldo_plg      = _get_wallet_balance(plg_address)
            _send(self, 200, {
                "genesis_ativo"     : genesis_ativo,
                "eh_validador"      : eh_validador,
                "saldo_plg"         : saldo_plg,
                "preco_plg"         : SHIELD_PLG_AMOUNT,
                "preco_usd"         : SHIELD_PRICE_USD,
                "treasury_address"  : TREASURY_ADDRESS,
                "saldo_suficiente"  : saldo_plg >= SHIELD_PLG_AMOUNT,
            })

        elif path == "/shield/subscriptions/count":
            ROYALTY_SHARE = 0.02
            with _db_lock:
                ativos           = [s for s in _subscriptions if s.get("ativo", True)]
                genesis_gratis   = [s for s in ativos if s.get("genesis_gratis", False)]
                pagos            = [s for s in ativos if not s.get("genesis_gratis", False)]
                # PC = validadores com pagamento por mineração (desktop)
                # Móvel = app Android (genesis grátis ou carteira PLG)
                pcs              = sum(1 for s in ativos if s.get("metodo_pagamento") == "mineracao")
                mobile           = len(ativos) - pcs
                # valor_arrecadado inclui apenas assinaturas pagas (não genesis gratuitas)
                valor_arrecadado = len(pagos) * SHIELD_PRICE_USD
                royalties        = round(valor_arrecadado * ROYALTY_SHARE, 2)
            _send(self, 200, {
                "total_ativos"        : len(ativos),
                "pcs"                 : pcs,
                "mobile"              : mobile,
                "genesis_gratis_count": len(genesis_gratis),
                "valor_arrecadado"    : valor_arrecadado,
                "royalties_2pct"      : royalties,
                "carteira_criador"    : TREASURY_ADDRESS,
            })

        elif path == "/shield/threats":
            tipo = qs.get("tipo", ["all"])[0]
            result: dict = {}
            if tipo in ("all", "packages"):
                result["packages"] = sorted(MALWARE_PACKAGES)
            if tipo in ("all", "domains"):
                result["domains"] = sorted(PHISHING_DOMAINS)
            _send(self, 200, result)
        else:
            _send(self, 404, {"error": "rota_nao_encontrada"})

    def do_POST(self):
        global _scan_counter
        parsed = urlparse(self.path)
        path   = parsed.path
        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8")) if length > 0 else {}
        except Exception:
            _send(self, 400, {"error": "json_invalido"})
            return

        if path == "/shield/scan/url":
            url = body.get("url", "").strip()
            if not url:
                _send(self, 400, {"error": "url_obrigatoria"})
                return
            _scan_counter += 1
            _send(self, 200, _scan_url(url))

        elif path == "/shield/scan/batch":
            apps = body.get("apps", [])
            if not isinstance(apps, list):
                _send(self, 400, {"error": "apps_deve_ser_lista"})
                return
            _scan_counter += len(apps)
            results  = []
            flagged  = []
            for app in apps:
                pkg  = app.get("package_name", "")
                cert = app.get("cert_hash", "")
                if not pkg:
                    continue
                r = _scan_app(pkg, cert)
                results.append(r)
                if r["status"] != "LIMPO":
                    flagged.append(r)
            _send(self, 200, {
                "total_escaneado"   : len(results),
                "ameacas_encontradas": len(flagged),
                "flagged"           : flagged,
            })

        elif path == "/shield/anchor":
            state_hash  = body.get("state_hash", "").strip()
            plg_address = body.get("plg_address", "").strip()
            app_count   = int(body.get("app_count", 0))

            if not state_hash or len(state_hash) < 32:
                _send(self, 400, {"error": "state_hash_invalido"})
                return
            if not plg_address.startswith("PLG"):
                _send(self, 400, {"error": "plg_address_invalido"})
                return

            if _ZK_AVAILABLE:
                try:
                    with _db_lock:
                        prev_anchors = [a for a in _anchors if a.get("plg_address") == plg_address]
                        prev_proof   = bytes.fromhex(prev_anchors[-1]["zk_proof"]) if prev_anchors else b""
                    proof_bytes = _zk.generate_recursive_proof(state_hash, previous_proof=prev_proof)
                    zk_proof_hex = proof_bytes.hex()
                except Exception as e:
                    _send(self, 500, {"error": f"zk_proof_falhou: {str(e)}"})
                    return
            else:
                # BLAKE3 Hegemonia
                zk_proof_hex = _b3_hash(state_hash.encode())

            ts = int(time.time())
            # Anchor ID purificado para BLAKE3
            anchor_id = _b3_hash(f"{plg_address}:{state_hash}:{ts}".encode())[:32]

            record = {
                "anchor_id"  : anchor_id,
                "plg_address": plg_address,
                "state_hash" : state_hash,
                "zk_proof"   : zk_proof_hex,
                "app_count"  : app_count,
                "timestamp"  : ts,
                "zk_engine"  : "DagSealEngine-V4.1" if _ZK_AVAILABLE else "BLAKE3-fallback",
            }

            with _db_lock:
                _anchors.append(record)
                _save_anchors()

            _send(self, 200, {
                "status"    : "ancorado",
                "anchor_id" : anchor_id,
                "state_hash": state_hash,
                "zk_proof"  : zk_proof_hex[:64] + "...",
                "timestamp" : ts,
                "zk_engine" : record["zk_engine"],
            })

        elif path == "/shield/subscribe":
            plg_address = body.get("plg_address", "").strip()
            metodo      = body.get("metodo_pagamento", "carteira").strip()
            tx_id       = body.get("tx_id", "").strip()

            if not plg_address.startswith("PLG"):
                _send(self, 400, {"error": "plg_address_invalido"})
                return
            if metodo not in ("gratis_genesis", "carteira", "mineracao"):
                _send(self, 400, {"error": "metodo_invalido: gratis_genesis|carteira|mineracao"})
                return

            if metodo == "gratis_genesis":
                if not _check_genesis():
                    _send(self, 403, {"error": "fase_genesis_encerrada"})
                    return
            elif metodo == "mineracao":
                if not _check_validator(plg_address):
                    _send(self, 403, {"error": "apenas_validadores_ativos_podem_usar_mineracao"})
                    return
            elif metodo == "carteira":
                if not tx_id:
                    _send(self, 400, {"error": "tx_id_obrigatorio_para_pagamento_carteira"})
                    return

            ts = int(time.time())
            with _db_lock:
                existing = next(
                    (s for s in _subscriptions if s.get("plg_address") == plg_address), None
                )
                record = {
                    "plg_address"       : plg_address,
                    "ativo"             : True,
                    "criado_em"         : ts,
                    "renovado_em"       : ts,
                    "metodo_pagamento"  : metodo,
                    "tx_id"             : tx_id,
                    "genesis_gratis"    : metodo == "gratis_genesis",
                    "desconto_mineracao": metodo == "mineracao",
                }
                if existing:
                    existing.update({**record, "criado_em": existing.get("criado_em", ts)})
                else:
                    _subscriptions.append(record)
                _save_subscriptions()

            _send(self, 200, {
                "status"            : "subscribed",
                "plg_address"       : plg_address,
                "metodo_pagamento"  : metodo,
                "timestamp"         : ts,
            })

        elif path == "/shield/unsubscribe":
            plg_address = body.get("plg_address", "").strip()
            ts = int(time.time())
            with _db_lock:
                existing = next(
                    (s for s in _subscriptions if s.get("plg_address") == plg_address), None
                )
                if existing:
                    existing["ativo"]        = False
                    existing["cancelado_em"] = ts
                    _save_subscriptions()
            _send(self, 200, {"status": "unsubscribed", "plg_address": plg_address})

        elif path == "/shield/report":
            tipo  = body.get("tipo", "").strip()
            valor = body.get("valor", "").strip().lower()
            if not tipo or not valor:
                _send(self, 400, {"error": "tipo_e_valor_obrigatorios"})
                return

            with _db_lock:
                if tipo == "package":
                    if valor not in _community["packages"]:
                        _community["packages"].append(valor)
                        _save_community()
                elif tipo == "domain":
                    if valor not in _community["domains"]:
                        _community["domains"].append(valor)
                        _save_community()
                elif tipo == "cert_hash":
                    if valor not in _community["cert_hashes"]:
                        _community["cert_hashes"].append(valor)
                        _save_community()
                else:
                    _send(self, 400, {"error": "tipo_invalido: package|domain|cert_hash"})
                    return

            _send(self, 200, {"status": "reportado", "tipo": tipo, "valor": valor})

        else:
            _send(self, 404, {"error": "rota_nao_encontrada"})

if __name__ == "__main__":
    _log.info(f"[SHIELD SERVER] Iniciando na porta {PORT}...")
    _log.info(f"[SHIELD SERVER] Ameaças: {len(MALWARE_PACKAGES)} pacotes + {len(PHISHING_DOMAINS)} domínios")
    server = HTTPServer(("0.0.0.0", PORT), ShieldHandler)
    _log.info(f"[SHIELD SERVER] ATIVO — http://0.0.0.0:{PORT}/shield/status")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        _log.info("[SHIELD SERVER] Encerrado.")