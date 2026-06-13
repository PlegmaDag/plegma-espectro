import math
import threading
from datetime import datetime, timedelta
import plegma_db
from sentinela import check_priority

import logging
_log = logging.getLogger(__name__)

# Lock global para proteger operações de pool contra race conditions (TOCTOU)
_mine_lock = threading.Lock()

# =============================================================================
# AERARIUM PROTOCOL — Motor de Tokenomics V1.0
#
# Estatuto §3 — Tokenomics:
#   Supply máximo: 21.000.000.000 $PLG
#   Fair Launch: zero alocação para fundadores
#   Lock-up: 30 dias obrigatórios
#   Emissão: R = G / N com decaimento exponencial ~5% ao ano
#
# Estatuto §13 — Divisão de Incentivos (Pools de Mineração):
#   Validator Pool (60%): celulares, tablets, notebooks, PCs básicos
#   Prover Pool    (40%): PC Gamer, GPU, ASIC, Servidores
#
# Estatuto §6 — Distribuição das Taxas de Rede:
#   Padrão:                 10% Aerarium / 40% Provers / 50% Validadores
#   Após teto de $1.000:     0% Aerarium / 40% Provers / 60% Validadores (transbordo)
#
# =============================================================================

TIPO_VALIDATOR = "VALIDATOR"
TIPO_PROVER    = "PROVER"

# Pools de Mineração (inicialização do tesouro)
VALIDATOR_SHARE = 0.60
PROVER_SHARE    = 0.40

# Distribuição das Taxas de Rede (Estatuto §6)
AERARIUM_FEE_SHARE  = 0.10     # 10% → Aerarium (padrão, até o teto)
PROVER_FEE_SHARE    = 0.40     # 40% → Provers (sempre)
VALIDATOR_FEE_SHARE = 0.50     # 50% → Validadores (padrão) / 60% após teto
AERARIUM_FEE_CEILING = 1000.0  # Teto do Aerarium em taxas de rede ($1.000)


class AerariumProtocol:
    def __init__(self, launch_date=None):
        self.MAX_SUPPLY  = 21_000_000_000.0
        self.launch_date = launch_date or datetime.now()

        # Anti-Dump
        self.WHALE_DUMP_THRESHOLD = 500_000.0
        self.WHALE_DELAY_HOURS    = 24

        # Carrega pools do banco ou inicializa valores padrão
        self.validator_pool  = plegma_db.carregar_estado("validator_pool",  self.MAX_SUPPLY * VALIDATOR_SHARE)
        self.prover_pool     = plegma_db.carregar_estado("prover_pool",     self.MAX_SUPPLY * PROVER_SHARE)

        # Pool do Aerarium (taxas de rede — Estatuto §6)
        self.aerarium_pool = plegma_db.carregar_estado("aerarium_pool", 0.0)

        # Vesting carregado do banco
        self.vesting_contracts = plegma_db.carregar_vesting()

    def get_network_age_days(self) -> int:
        return (datetime.now() - self.launch_date).days

    def get_pools_status(self) -> dict:
        emitido = self.MAX_SUPPLY - self.validator_pool - self.prover_pool
        aerarium_acumulado = plegma_db.carregar_estado("aerarium_fees_accumulated", 0.0)
        return {
            "validator_pool"           : self.validator_pool,
            "prover_pool"              : self.prover_pool,
            "aerarium_pool"            : self.aerarium_pool,
            "aerarium_fees_accumulated": aerarium_acumulado,
            "aerarium_teto_atingido"   : aerarium_acumulado >= AERARIUM_FEE_CEILING,
            "total_emitido"            : emitido,
        }

    def calculate_reward(
        self,
        base_generation: float,
        active_nodes   : int,
        current_day    : int
    ) -> float:
        """
        R = G(t) / N   [recompensa por nó ativo]
        G(t) = G_inicial × e^(-λ × t)   [decaimento ~5% ao ano]
        N    = nós ativos do mesmo tipo de pool

        Taxas de rede são distribuídas separadamente por _distribuir_taxa_rede_locked()
        conforme Estatuto §6 (10% Aerarium / 40% Provers / 50% Validadores).
        """
        if active_nodes <= 0:
            return 0.0
        decay_rate = 0.000137
        g_atual    = base_generation * math.exp(-decay_rate * current_day)
        return g_atual / active_nodes

    def mine_tokens(
        self,
        plg_address      : str,           # Endereço PLG do celular dono (sempre)
        node_type        : str,           # VALIDATOR ou PROVER
        base_generation  : float,
        active_nodes     : int,
        vertex_timestamp : datetime = None,  # FIFO: quando o vértice foi minerado
        tx_fee           : float = 0.0       # Taxa da transação (R = G/N + fee pós Dia 31)
    ):
        """
        Minera tokens do pool correto conforme o tipo do nó.

        Importante: plg_address é SEMPRE o celular dono.
        PCs (Provers e Validators técnicos) não têm carteira própria —
        suas recompensas vão direto para o PLG do celular vinculado.
        """
        current_day = self.get_network_age_days()

        if node_type not in (TIPO_VALIDATOR, TIPO_PROVER):
            _log.info(f"[!] Tipo de nó inválido: {node_type}")
            return 0.0, None

        reward = self.calculate_reward(base_generation, active_nodes, current_day)

        # Boost por categoria PLG-G (Estatuto §4) — fora do lock (apenas leitura)
        priority = check_priority(plg_address)
        boost = priority["boost"]
        if boost > 1.0:
            reward *= boost
            _log.info(f"[*] Boost {priority['categoria']} (x{boost}): {priority['saldo_plgg']:.0f} PLG-G -> recompensa ajustada")

        with _mine_lock:
            # Recarrega pools do DB para garantir estado atual (evita TOCTOU)
            self.validator_pool = plegma_db.carregar_estado("validator_pool", self.validator_pool)
            self.prover_pool    = plegma_db.carregar_estado("prover_pool",    self.prover_pool)
            self.aerarium_pool  = plegma_db.carregar_estado("aerarium_pool",  self.aerarium_pool)

            # Distribui taxa de rede conforme Estatuto §6 (dentro do lock — pools já recarregados)
            if current_day >= 31 and tx_fee > 0:
                self._distribuir_taxa_rede_locked(tx_fee)

            # Debita do pool correto (read-check-write atômico)
            if node_type == TIPO_VALIDATOR:
                if self.validator_pool < reward:
                    reward = self.validator_pool
                self.validator_pool -= reward
                pool_label = "Validator Pool (60%)"
            else:
                if self.prover_pool < reward:
                    reward = self.prover_pool
                self.prover_pool -= reward
                pool_label = "Prover Pool (40%)"

            # Lock-up FIFO 30 dias — liberação ancorada ao timestamp do vértice minerado
            anchor       = vertex_timestamp if vertex_timestamp else datetime.now()
            release_date = anchor + timedelta(days=30)

            entry = {
                "amount"      : reward,
                "release_date": release_date.timestamp(),
                "status"      : "LOCKED",
                "node_type"   : node_type,
                "pool"        : pool_label
            }

            if plg_address not in self.vesting_contracts:
                self.vesting_contracts[plg_address] = []
            self.vesting_contracts[plg_address].append(entry)

            # Persiste vesting e saldos dos pools (dentro do lock)
            plegma_db.salvar_vesting(plg_address, entry)
            plegma_db.salvar_estado("validator_pool", self.validator_pool)
            plegma_db.salvar_estado("prover_pool",    self.prover_pool)
            plegma_db.salvar_estado("aerarium_pool",  self.aerarium_pool)

        return reward, release_date

    def _distribuir_taxa_rede_locked(self, tx_fee: float) -> dict:
        """
        Distribui a taxa de rede conforme Estatuto §6.
        DEVE ser chamado dentro do _mine_lock (pools já recarregados do DB).

        Padrão (Aerarium < teto):
            10% → Aerarium | 40% → Provers | 50% → Validadores
        Após teto de $1.000 do Aerarium (transbordo):
             0% → Aerarium | 40% → Provers | 60% → Validadores
        """
        aerarium_acumulado = plegma_db.carregar_estado("aerarium_fees_accumulated", 0.0)

        if aerarium_acumulado >= AERARIUM_FEE_CEILING:
            # Transbordo: 0% Aerarium, 40% Provers, 60% Validadores
            fee_aerarium  = 0.0
            fee_prover    = tx_fee * PROVER_FEE_SHARE
            fee_validator = tx_fee * (VALIDATOR_FEE_SHARE + AERARIUM_FEE_SHARE)  # 60%
        else:
            # Padrão: 10% Aerarium, 40% Provers, 50% Validadores
            fee_aerarium  = tx_fee * AERARIUM_FEE_SHARE
            fee_prover    = tx_fee * PROVER_FEE_SHARE
            fee_validator = tx_fee * VALIDATOR_FEE_SHARE

            # Teto parcial: excedente do Aerarium vai para Validadores
            restante = AERARIUM_FEE_CEILING - aerarium_acumulado
            if fee_aerarium > restante:
                overflow      = fee_aerarium - restante
                fee_aerarium  = restante
                fee_validator += overflow

        # Aplica nos pools (já recarregados dentro do lock)
        self.validator_pool += fee_validator
        self.prover_pool    += fee_prover
        self.aerarium_pool  += fee_aerarium

        # Persiste acumulador do Aerarium (pools serão persistidos ao final do mine_tokens)
        novo_acumulado = aerarium_acumulado + fee_aerarium
        plegma_db.salvar_estado("aerarium_fees_accumulated", novo_acumulado)

        if fee_aerarium > 0:
            _log.info(f"[*] TAXA §6: Aerarium +{fee_aerarium:.4f} | Provers +{fee_prover:.4f} | Validators +{fee_validator:.4f} $PLG")
        else:
            _log.info(f"[*] TAXA §6 (teto atingido): Provers +{fee_prover:.4f} | Validators +{fee_validator:.4f} $PLG")

        return {
            "fee_total"          : tx_fee,
            "fee_aerarium"       : fee_aerarium,
            "fee_prover"         : fee_prover,
            "fee_validator"      : fee_validator,
            "aerarium_acumulado" : novo_acumulado,
            "teto_atingido"      : novo_acumulado >= AERARIUM_FEE_CEILING
        }

    def process_whale_transaction(self, sender: str, amount: float):
        if amount >= self.WHALE_DUMP_THRESHOLD:
            rph = amount / self.WHALE_DELAY_HOURS
            _log.info(f"[!] ALERTA BALEIA: {amount:,.2f} $PLG — diluindo em {self.WHALE_DELAY_HOURS}h.")
            return True, rph
        _log.info(f"[+] Transação de {amount:,.2f} $PLG aprovada.")
        return False, amount


# =============================================================================
# SIMULAÇÃO
# =============================================================================
if __name__ == "__main__":
    _log.info("==================================================")
    _log.info(" [!] AERARIUM V1.0 — POOLS 60/40 INICIALIZADOS   ")
    _log.info("==================================================")

    eco   = AerariumProtocol()
    pools = eco.get_pools_status()

    _log.info(f"[*] MAX SUPPLY       : {eco.MAX_SUPPLY:>20,.0f} $PLG")
    _log.info(f"[*] VALIDATOR POOL   : {pools['validator_pool']:>20,.0f} $PLG  (60%)")
    _log.info(f"[*] PROVER POOL      : {pools['prover_pool']:>20,.0f} $PLG  (40%)")
    _log.info(f"[*] FAIR LAUNCH      : Zero alocação para fundadores ✓\n")

    PLG = "PLG9DC5642E1B2A67766F97367E062345B0723A7123"
    eco.launch_date = datetime.now() - timedelta(days=35)

    _log.info("[*] --- TESTE 1: CELULAR (Validator Pool 60%) ---")
    r1, d1 = eco.mine_tokens(PLG, TIPO_VALIDATOR, 1_000_000, 50_000)
    if d1:
        _log.info(f"    Recompensa : {r1:.4f} $PLG  |  Vesting: {d1.strftime('%d/%m/%Y')}\n")

    _log.info("[*] --- TESTE 2: PC GAMER vinculado ao mesmo PLG (Prover Pool 40%) ---")
    r2, d2 = eco.mine_tokens(PLG, TIPO_PROVER, 1_000_000, 5_000)
    if d2:
        _log.info(f"    Recompensa : {r2:.4f} $PLG  |  Vesting: {d2.strftime('%d/%m/%Y')}")
        _log.info(f"    Endereço   : mesmo PLG do celular ✓\n")

    pools = eco.get_pools_status()
    _log.info("[*] --- STATUS FINAL ---")
    _log.info(f"    Validator Pool : {pools['validator_pool']:,.4f} $PLG restantes")
    _log.info(f"    Prover Pool    : {pools['prover_pool']:,.4f} $PLG restantes")
    _log.info(f"    Total emitido  : {pools['total_emitido']:,.4f} $PLG")
    _log.info("==================================================")
