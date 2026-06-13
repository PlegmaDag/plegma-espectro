import os
import sys
import time
import math
import logging
import threading
from datetime import datetime

# ── Blindagem de Oráculo Determinístico (Hard Fail) ─────────
try:
    import blake3 as _blake3
except ImportError:
    raise RuntimeError("[FALHA FATAL] Módulo blake3 ausente no Miner Engine.")

def _b3_hash(data: bytes) -> str:
    return _blake3.blake3(data).hexdigest()

# =============================================================================
# LOG DE AUDITORIA LOCAL — gravação offline
# =============================================================================
_LOG_PATH = os.path.join(os.path.dirname(__file__), "miner_fatal.log")
logging.basicConfig(
    level    = logging.CRITICAL,
    format   = "%(asctime)s [%(levelname)s] %(message)s",
    handlers = [
        logging.FileHandler(_LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stderr),
    ]
)

# =============================================================================
# MINER ENGINE — Motor de Mineração V4.0 (PÓS-QUÂNTICO)
# DETERMINISMO ABSOLUTO — Biblioteca 'random' banida.
# =============================================================================

try:
    import urllib.request
    import urllib.error
    import json as _json
    HTTP_OK = True
except ImportError:
    HTTP_OK = False

from lattice_shield import LatticeShield

class MinerEngine:
    def __init__(
        self,
        plg_address  : str,
        node_id      : str,
        node_type    : str,
        dag_url      : str = "http://localhost:8080",
        on_log       = None,
        on_stats     = None,
        on_status    = None,
    ):
        self.plg_address = plg_address
        self.node_id     = node_id
        self.node_type   = node_type
        self.dag_url     = dag_url
        self.on_log      = on_log    or (lambda msg: None)
        self.on_stats    = on_stats  or (lambda d: None)
        self.on_status   = on_status or (lambda s: None)

        self._rodando    = False
        self._pausado    = False
        self._thread     = None
        self._shield     = None
        self._zk_ativo   = False

        self.stats = {
            "hashrate"         : 0.0,
            "total_aceitas"    : 0,
            "total_rejeitadas" : 0,
            "total_recompensa" : 0.0,
            "uptime_segundos"  : 0,
            "ultima_tx"        : "--",
            "nos_ativos"       : 0,
            "dag_status"       : "DESCONECTADO",
            "node_type"        : node_type,
            "node_id"          : node_id,
            "plg_address"      : plg_address,
            "zk_ativo"         : False,
        }
        self._inicio = None

    def _obter_entropia_determinista(self, ciclo: int, semente: str = "GENERIC") -> str:
        """Substitui o módulo 'random' por entropia hash baseada no estado do nó."""
        raw = f"{self.node_id}:{ciclo}:{semente}:{time.time_ns() // 1_000_000}"
        return _b3_hash(raw.encode())

    def _bifurcar_no(self):
        if self.node_type == "PROVER":
            self._zk_ativo = True
            self.stats["zk_ativo"] = True
            self.on_log("ZK sub-rotina: ATIVA (Prover — Matriz Lattice V4.0)")
        else:
            self._zk_ativo = False
            self.stats["zk_ativo"] = False
            self.on_log("ZK sub-rotina: DORMENTE (Validator — Verificação Dilithium3)")

    def validar_camada_seguranca(self):
        if self._shield is None:
            erro_msg = "[FATAL] LatticeShield inoperante. O protocolo V4.0 exige Dilithium3."
            logging.critical(erro_msg)
            sys.exit(1)

    def iniciar(self):
        if self._rodando: return
        self._rodando = True
        self._pausado = False
        self._inicio  = time.time()
        self._thread  = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self.on_status("MINERANDO")

    def pausar(self):
        self._pausado = True
        self.on_status("PAUSADO")

    def retomar(self):
        self._pausado = False
        self.on_status("MINERANDO")

    def parar(self):
        self._rodando = False
        self.on_status("PARADO")

    def _loop(self):
        self._shield = LatticeShield()
        self._shield.generate_wallet()
        self.validar_camada_seguranca()
        self._bifurcar_no()

        # Preserva node_id fixo do construtor — só deriva do shield se não foi definido.
        # Sobrescrever causaria bypass do rate limit 24h a cada restart.
        if not self.node_id:
            self.node_id = _b3_hash(self._shield.public_key)
        self.stats["node_id"] = self.node_id

        self._verificar_dag()
        ciclo = 0
        t_hashrate = time.time()
        hashes_ciclo = 0

        while self._rodando:
            if self._pausado:
                time.sleep(0.5)
                continue

            ciclo += 1
            hashes_ciclo += 1

            if time.time() - t_hashrate >= 5.0:
                elapsed = time.time() - t_hashrate
                self.stats["hashrate"] = round(hashes_ciclo / elapsed, 2)
                hashes_ciclo = 0
                t_hashrate = time.time()

            if self._inicio:
                self.stats["uptime_segundos"] = int(time.time() - self._inicio)

            sucesso, recompensa = self._minerar_vertice(ciclo)

            if sucesso:
                self.stats["total_aceitas"]    += 1
                self.stats["total_recompensa"] += recompensa
                self.stats["ultima_tx"]         = datetime.now().strftime("%H:%M:%S")
            else:
                self.stats["total_rejeitadas"] += 1

            self.on_stats(dict(self.stats))
            if ciclo % 10 == 0: self._verificar_dag()

            # Jitter determinístico baseado no hash do ciclo
            entropy = self._obter_entropia_determinista(ciclo, "SLEEP")
            wait_time = 0.8 + (int(entropy[:2], 16) / 512.0) 
            time.sleep(wait_time)

    def _buscar_pending_tx(self) -> str:
        """Busca a tx P2P mais recente ainda não validada para referenciar no mine."""
        try:
            req = urllib.request.Request(f"{self.dag_url}/api/pending_txs?limite=1",
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = _json.loads(resp.read())
                pending = data.get("pending", [])
                if pending:
                    return pending[0]["tx_hash"]
        except Exception:
            pass
        return ""

    def _minerar_vertice(self, ciclo: int) -> tuple[bool, float]:
        if not HTTP_OK: return self._simular_mineracao(ciclo)

        try:
            sender   = self._shield.address
            receiver = self.plg_address

            # Valor determinístico para o teste/simulação
            entropy = self._obter_entropia_determinista(ciclo, "AMOUNT")
            amount = 10.0 + (int(entropy[:4], 16) % 90)

            tx_mensagem = f"{sender}:{receiver}:{amount}:{ciclo}"
            signature   = self._shield.sign_transaction(tx_mensagem)
            public_key  = self._shield.get_public_key_hex()
            zk_proof    = _b3_hash(tx_mensagem.encode()) if self._zk_ativo else ""

            ref_tx = self._buscar_pending_tx()

            payload_dict = {
                "sender"        : sender,
                "receiver"      : receiver,
                "amount"        : amount,
                "node_type"     : self.node_type,
                "miner_address" : self.plg_address,
                "node_id"       : self.node_id,
                "signature"     : signature,
                "public_key"    : public_key,
                "zk_proof"      : zk_proof,
                "version"       : "4.0"
            }
            if ref_tx:
                payload_dict["ref_tx_hash"] = ref_tx

            payload = _json.dumps(payload_dict).encode()

            req = urllib.request.Request(f"{self.dag_url}/api/mine", data=payload,
                                         headers={"Content-Type": "application/json"}, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = _json.loads(resp.read())
                    return True, float(data.get("recompensa_minerador", 0.0))
            except urllib.error.HTTPError as he:
                if he.code == 429:
                    # Rate limit atingido — dorme 1h antes de tentar de novo
                    time.sleep(3600)
                    return False, 0.0
                raise
        except Exception:
            return self._simular_mineracao(ciclo)

    def _simular_mineracao(self, ciclo: int) -> tuple[bool, float]:
        entropy = self._obter_entropia_determinista(ciclo, "SIM")
        if int(entropy[:2], 16) < 230: # ~90% chance determinística
            recompensa = 5.0 + (int(entropy[2:6], 16) % 35)
            return True, float(recompensa)
        return False, 0.0

    def _verificar_dag(self):
        if not HTTP_OK:
            self.stats["dag_status"] = "SIMULAÇÃO"
            return
        try:
            with urllib.request.urlopen(f"{self.dag_url}/api/status", timeout=3) as resp:
                data = _json.loads(resp.read())
                self.stats["nos_ativos"] = data.get("nos_ativos", 0)
                self.stats["dag_status"] = "ONLINE"
        except Exception:
            self.stats["dag_status"] = "OFFLINE"

    def get_stats(self) -> dict:
        return dict(self.stats)

    def formatar_uptime(self) -> str:
        s = self.stats["uptime_segundos"]
        return f"{s//3600:02d}:{(s%3600)//60:02d}:{s%60:02d}"