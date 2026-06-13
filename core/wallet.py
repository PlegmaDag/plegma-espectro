import logging
import time
from datetime import datetime
from lattice_shield import LatticeShield
from aerarium import AerariumProtocol, TIPO_VALIDATOR, TIPO_PROVER

_log = logging.getLogger(__name__)

# ── Blindagem de Oráculo Determinístico (Hard Fail) ─────────
try:
    import blake3 as _blake3
except ImportError:
    raise RuntimeError("[FALHA FATAL] Módulo blake3 ausente em PlegmaWallet.")

def _b3_hash(data: bytes) -> str:
    return _blake3.blake3(data).hexdigest()

# =============================================================================
# PLEGMA WALLET — Motor Central da Carteira V4.0 (PÓS-QUÂNTICA)
#
# Diretrizes:
#   - Hegemonia BLAKE3 para geração de TX_IDs
#   - Transferência rigorosamente assinada com Dilithium3
# =============================================================================

class VestingContract:
    def __init__(self, amount: float, release_ts: float,
                 node_type: str, pool: str, tx_id: str):
        self.amount      = amount
        self.release_ts  = release_ts
        self.node_type   = node_type
        self.pool        = pool
        self.tx_id       = tx_id
        self.status      = "LOCKED"

    @property
    def release_date(self) -> datetime:
        return datetime.fromtimestamp(self.release_ts)

    @property
    def is_released(self) -> bool:
        return time.time() >= self.release_ts

    @property
    def days_remaining(self) -> int:
        remaining = self.release_ts - time.time()
        return max(0, int(remaining / 86400))

    def to_dict(self) -> dict:
        return {
            "amount"        : self.amount,
            "release_date"  : self.release_date.strftime("%d/%m/%Y %H:%M"),
            "days_remaining": self.days_remaining,
            "node_type"     : self.node_type,
            "pool"          : self.pool,
            "tx_id"         : self.tx_id,
            "status"        : "LIBERADO" if self.is_released else "BLOQUEADO"
        }

class TransacaoHistorico:
    def __init__(self, tx_id: str, tipo: str, amount: float,
                 contraparte: str, timestamp: float, status: str = "CONFIRMADA"):
        self.tx_id       = tx_id
        self.tipo        = tipo        
        self.amount      = amount
        self.contraparte = contraparte 
        self.timestamp   = timestamp
        self.status      = status

    @property
    def data(self) -> str:
        return datetime.fromtimestamp(self.timestamp).strftime("%d/%m/%Y %H:%M")

    def to_dict(self) -> dict:
        return {
            "tx_id"      : self.tx_id[:16] + "...",
            "tipo"       : self.tipo,
            "amount"     : self.amount,
            "contraparte": self.contraparte[:14] + "..." if len(self.contraparte) > 14 else self.contraparte,
            "data"       : self.data,
            "status"     : self.status
        }

_CATEGORIAS_VALIDATOR = {"MOBILE", "CELULAR", "ANDROID", "IOS", "SMARTPHONE"}

class ProverVinculado:
    def __init__(self, node_id: str, categoria: str, score: int):
        self.node_id     = node_id
        self.categoria   = categoria   
        self.score       = score
        self.ativo       = True
        self.ganhos_total= 0.0
        self.linked_at   = time.time()
        self.ultimo_ping = time.time()

    @property
    def tipo(self) -> str:
        return "VALIDATOR" if self.categoria.upper() in _CATEGORIAS_VALIDATOR else "PROVER"

    def to_dict(self) -> dict:
        return {
            "node_id"     : self.node_id,
            "categoria"   : self.categoria,
            "tipo"        : self.tipo,
            "score"       : self.score,
            "ativo"       : self.ativo,
            "ganhos_total": self.ganhos_total,
            "linked_at"   : self.linked_at,
            "ultimo_ping" : datetime.fromtimestamp(self.ultimo_ping).strftime("%d/%m/%Y %H:%M")
        }

class PlegmaWallet:
    def __init__(self, shield: LatticeShield, aerarium: AerariumProtocol):
        if not shield.address:
            raise ValueError("LatticeShield sem carteira gerada. Chame generate_wallet() primeiro.")

        self.shield      = shield
        self.aerarium    = aerarium
        self.plg_address = shield.address

        self._recebido_total   = 0.0   
        self._enviado_total    = 0.0   
        self._minerado_total   = 0.0   
        self._vesting_liberado = 0.0   

        self.vestings: list[VestingContract] = []
        self.historico: list[TransacaoHistorico] = []
        self.provers: dict[str, ProverVinculado] = {}

        self._sync_vesting_aerarium()

    def _sync_vesting_aerarium(self):
        contratos = self.aerarium.vesting_contracts.get(self.plg_address, [])
        for c in contratos:
            tx_id = f"AERARIUM_{int(c['release_date'])}"
            vc = VestingContract(
                amount     = c["amount"],
                release_ts = c["release_date"],
                node_type  = c.get("node_type", TIPO_VALIDATOR),
                pool       = c.get("pool", "Validator Pool (60%)"),
                tx_id      = tx_id
            )
            self.vestings.append(vc)
            self._minerado_total += c["amount"]

            self.historico.append(TransacaoHistorico(
                tx_id      = tx_id,
                tipo       = "MINERADO",
                amount     = c["amount"],
                contraparte= "REDE PLEGMA",
                timestamp  = time.time(),
                status     = "EM VESTING"
            ))

    def liberar_vesting(self) -> float:
        total_liberado = 0.0
        for vc in self.vestings:
            if vc.is_released and vc.status == "LOCKED":
                vc.status         = "LIBERADO"
                total_liberado    += vc.amount
                self._vesting_liberado += vc.amount

                self.historico.append(TransacaoHistorico(
                    tx_id      = vc.tx_id + "_LIB",
                    tipo       = "VESTING_LIBERADO",
                    amount     = vc.amount,
                    contraparte= "VESTING",
                    timestamp  = time.time()
                ))

        if total_liberado > 0:
            _log.info(f"[+] VESTING LIBERADO: {total_liberado:.4f} $PLG disponíveis.")
        return total_liberado

    @property
    def saldo_vesting_locked(self) -> float:
        return sum(v.amount for v in self.vestings if v.status == "LOCKED")

    @property
    def saldo_disponivel(self) -> float:
        self.liberar_vesting()  
        return max(0.0,
            self._recebido_total
            + self._vesting_liberado
            - self._enviado_total
        )

    @property
    def saldo_total_estimado(self) -> float:
        return self.saldo_disponivel + self.saldo_vesting_locked

    def get_resumo_saldos(self) -> dict:
        return {
            "plg_address"     : self.plg_address,
            "disponivel"      : self.saldo_disponivel,
            "vesting_locked"  : self.saldo_vesting_locked,
            "total_estimado"  : self.saldo_total_estimado,
            "minerado_total"  : self._minerado_total,
            "enviado_total"   : self._enviado_total,
            "recebido_total"  : self._recebido_total,
        }

    def registrar_recebimento(self, tx_id: str, amount: float, remetente: str):
        self._recebido_total += amount
        self.historico.append(TransacaoHistorico(
            tx_id      = tx_id,
            tipo       = "RECEBIDO",
            amount     = amount,
            contraparte= remetente,
            timestamp  = time.time()
        ))
        _log.info(f"[+] RECEBIDO: {amount:.4f} $PLG de {remetente[:14]}...")

    def transferir(self, destinatario: str, amount: float, dag=None) -> dict:
        if amount <= 0:
            return {"ok": False, "erro": "Valor deve ser maior que zero."}

        if not destinatario.startswith("PLG") or len(destinatario) != 43:
            return {"ok": False, "erro": "Endereço PLG inválido."}

        if destinatario == self.plg_address:
            return {"ok": False, "erro": "Não é possível enviar para si mesmo."}

        if self.saldo_disponivel < amount:
            return {
                "ok"        : False,
                "erro"      : f"Saldo insuficiente. Disponível: {self.saldo_disponivel:.4f} $PLG",
                "disponivel": self.saldo_disponivel
            }

        tx_payload = f"{self.plg_address}:{destinatario}:{amount}:{int(time.time())}"
        try:
            assinatura = self.shield.sign_transaction(tx_payload)
        except Exception as e:
            return {"ok": False, "erro": f"Falha na assinatura: {str(e)}"}

        self._enviado_total += amount

        # Gera tx_id estritamente determinístico via Oráculo BLAKE3
        tx_id = "TX_" + _b3_hash(tx_payload.encode())[:32]

        self.historico.append(TransacaoHistorico(
            tx_id      = tx_id,
            tipo       = "ENVIADO",
            amount     = amount,
            contraparte= destinatario,
            timestamp  = time.time()
        ))

        _log.info(f"[+] ENVIADO: {amount:.4f} $PLG → {destinatario[:14]}...")

        return {
            "ok"         : True,
            "tx_id"      : tx_id,
            "amount"     : amount,
            "destinatario": destinatario,
            "assinatura" : assinatura[:32] + "...",
            "saldo_apos" : self.saldo_disponivel
        }

    def vincular_prover(self, node_id: str, categoria: str, score: int):
        prover = ProverVinculado(node_id, categoria, score)
        self.provers[node_id] = prover
        _log.info(f"[+] PROVER VINCULADO: {node_id} ({categoria} — score {score})")

    def registrar_ganho_prover(self, node_id: str, amount: float):
        if node_id in self.provers:
            self.provers[node_id].ganhos_total += amount
            self.provers[node_id].ultimo_ping   = time.time()

    def get_extrato(self, limite: int = 20, filtro: str = None) -> list:
        txs = self.historico
        if filtro:
            txs = [t for t in txs if t.tipo == filtro]
        return [t.to_dict() for t in sorted(txs, key=lambda x: x.timestamp, reverse=True)[:limite]]

    def get_vesting_pendente(self) -> list:
        locked = [v for v in self.vestings if v.status == "LOCKED"]
        return sorted([v.to_dict() for v in locked], key=lambda x: x["days_remaining"])

    def get_stats_dashboard(self) -> dict:
        v_pool = sum(
            v.amount for v in self.vestings
            if v.node_type == TIPO_VALIDATOR
        )
        p_pool = sum(
            v.amount for v in self.vestings
            if v.node_type == TIPO_PROVER
        )
        provers_ativos = [p for p in self.provers.values() if p.ativo]

        return {
            "plg_address"       : self.plg_address,
            "saldo_disponivel"  : self.saldo_disponivel,
            "saldo_vesting"     : self.saldo_vesting_locked,
            "total_estimado"    : self.saldo_total_estimado,
            "minerado_total"    : self._minerado_total,
            "enviado_total"     : self._enviado_total,
            "recebido_total"    : self._recebido_total,
            "vesting_validator" : v_pool,
            "vesting_prover"    : p_pool,
            "total_txs"         : len(self.historico),
            "provers_vinculados": len(provers_ativos),
            "provers_ganhos"    : sum(p.ganhos_total for p in provers_ativos),
            "proxima_liberacao" : min(
                (v.days_remaining for v in self.vestings if v.status == "LOCKED"),
                default=None
            )
        }