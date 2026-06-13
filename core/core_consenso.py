import time

import logging
_log = logging.getLogger(__name__)

# =============================================================================
# CORE CONSENSO — Motor de Hierarquia e Classificação de Nós V4.0
# (HEGEMONIA BLAKE3 / PÓS-QUÂNTICO — hashlib expurgado)
#
# Estatuto §4 — Divisão de Infraestrutura:
#   Validators (60% incentivos): celular, tablet, notebook, PC básico
#   Provers    (40% incentivos): PC Gamer, GPU dedicada, ASIC, Servidor
#
# Estatuto §13 — Divisão de Incentivos:
#   Validators: garantem descentralização, validam provas ZK (~22KB)
#   Provers   : calculam BLAKE3 e geram as provas ZK
#
# Estatuto §14 — Justiça Computacional:
#   A potência de hardware NÃO confere prioridade.
#   O trabalho é fragmentado equitativamente entre os Provers disponíveis.
#   Teto de participação por Prover: máximo 10% do trabalho total da rede.
#
# Fluxo de entrada na rede:
#   1. Usuário baixa o app → gera chave Dilithium3 → endereço PLG (celular)
#   2. Celular ativa o Validator móvel (com direito de voto)
#   3. Via dashboard, usuário baixa o minerador no PC
#   4. Minerador detecta o hardware → classifica como Validator ou Prover
#   5. PC reporta ao celular → vínculo celular→PC estabelecido
#   6. Recompensas do PC vão para o endereço PLG do celular dono
# =============================================================================

# ===== THRESHOLDS DE CLASSIFICAÇÃO DE HARDWARE =====
VALIDATOR_MAX_SCORE = 999    # Abaixo disso → Validator (notebook, PC básico)
PROVER_MIN_SCORE    = 1000   # Acima disso → Prover (PC Gamer, GPU, ASIC, Servidor)

PROVER_WORK_CAP_PCT = 0.10
MAX_PROVERS_PER_VALIDATOR = None

def classificar_hardware(
    device_type: str,
    cpu_cores: int,
    ram_gb: float,
    has_dedicated_gpu: bool,
    gpu_vram_gb: float = 0.0,
    is_asic: bool = False
) -> dict:
    
    if device_type in ("SMARTPHONE", "TABLET"):
        return {
            "tipo"      : "VALIDATOR",
            "score"     : 0,
            "categoria" : "MOBILE",
            "descricao" : "Nó Validador Móvel — Coração da descentralização"
        }

    if is_asic or device_type == "SERVER":
        score = 9999 if is_asic else (cpu_cores * 100 + ram_gb * 10)
        return {
            "tipo"      : "PROVER",
            "score"     : int(score),
            "categoria" : "ASIC" if is_asic else "SERVER",
            "descricao" : "Prover de Alta Performance — Geração de Provas ZK"
        }

    score = 0
    score += cpu_cores * 50           
    score += ram_gb * 5               
    if has_dedicated_gpu:
        score += 500                  
        score += gpu_vram_gb * 100    

    if device_type == "NOTEBOOK":
        score *= 0.7  

    score = int(score)

    if score < PROVER_MIN_SCORE:
        return {
            "tipo"      : "VALIDATOR",
            "score"     : score,
            "categoria" : "NOTEBOOK" if device_type == "NOTEBOOK" else "DESKTOP_BASIC",
            "descricao" : "Nó Validador Técnico — Valida provas ZK na rede"
        }
    else:
        return {
            "tipo"      : "PROVER",
            "score"     : score,
            "categoria" : "GPU" if has_dedicated_gpu else "DESKTOP_HIGH",
            "descricao" : "Prover — Gera provas ZK e calcula hashes BLAKE3"
        }

class No:
    def __init__(self, node_id: str, plg_address: str, classificacao: dict):
        self.node_id        = node_id
        self.plg_address    = plg_address   
        self.tipo           = classificacao["tipo"]       
        self.categoria      = classificacao["categoria"]  
        self.score          = classificacao["score"]
        self.descricao      = classificacao["descricao"]

        self.direito_voto   = (classificacao["categoria"] == "MOBILE")

        self.ativo          = True
        self.em_quarentena  = False
        self.capacidade     = 1.0   

        self.trabalho_total = 0     
        self.trabalho_ciclo = 0     

class MotorConsenso:
    def __init__(self):
        self.nos: dict[str, No] = {}
        self.vinculos: dict[str, list] = {}

    def registrar_no(
        self,
        node_id     : str,
        plg_address : str,    
        device_type : str,
        cpu_cores   : int   = 4,
        ram_gb      : float = 8.0,
        has_gpu     : bool  = False,
        gpu_vram_gb : float = 0.0,
        is_asic     : bool  = False
    ) -> No:
        
        classificacao = classificar_hardware(
            device_type, cpu_cores, ram_gb,
            has_gpu, gpu_vram_gb, is_asic
        )

        no = No(node_id, plg_address, classificacao)
        self.nos[node_id] = no

        if classificacao["categoria"] != "MOBILE":
            if plg_address not in self.vinculos:
                self.vinculos[plg_address] = []
            if node_id not in self.vinculos[plg_address]:
                self.vinculos[plg_address].append(node_id)

        _log.info(f"[+] NÓ REGISTRADO: {node_id}")
        _log.info(f"    Tipo      : {no.tipo} ({no.categoria})")
        _log.info(f"    Score     : {no.score}")
        _log.info(f"    Dono PLG  : {plg_address[:12]}...")
        _log.info(f"    Voto      : {'SIM ✓' if no.direito_voto else 'NÃO'}")
        _log.info(f"    {no.descricao}")

        return no

    def distribuir_trabalho(self, total_provas: int) -> dict[str, int]:
        provers_ativos = [
            n for n in self.nos.values()
            if n.tipo == "PROVER" and n.ativo and not n.em_quarentena
        ]

        if not provers_ativos:
            return {}

        n_provers   = len(provers_ativos)
        teto        = int(total_provas * PROVER_WORK_CAP_PCT)
        base        = total_provas // n_provers
        distribuicao= {}

        excedente = 0
        for prover in provers_ativos:
            cota = min(base, teto)
            distribuicao[prover.node_id] = cota
            excedente += base - cota

        if excedente > 0:
            com_margem = [
                n for n in provers_ativos
                if distribuicao[n.node_id] < teto
            ]
            if com_margem:
                extra = excedente // len(com_margem)
                for n in com_margem:
                    espaco = teto - distribuicao[n.node_id]
                    distribuicao[n.node_id] += min(extra, espaco)

        for node_id, qtd in distribuicao.items():
            self.nos[node_id].trabalho_ciclo += qtd
            self.nos[node_id].trabalho_total += qtd

        return distribuicao

    def monitorar_prover(self, node_id: str, hashrate: float, temperatura_c: float):
        if node_id not in self.nos:
            return

        no = self.nos[node_id]

        if no.tipo == "VALIDATOR":
            return  

        falha = hashrate < 50.0 or temperatura_c > 85.0

        if falha and not no.em_quarentena:
            no.em_quarentena = True
            no.capacidade    = 0.6
            _log.info(f"[!] QUARENTENA: Prover {node_id}")
            _log.info(f"    Temp: {temperatura_c}°C | Hash: {hashrate} H/s")
            _log.info(f"    Capacidade reduzida a 60% até estabilizar.")

        elif not falha and no.em_quarentena:
            no.em_quarentena = False
            no.capacidade    = 1.0
            _log.info(f"[+] RECUPERADO: Prover {node_id} — capacidade restaurada.")

    def get_validators(self) -> list[No]:
        return [n for n in self.nos.values() if n.tipo == "VALIDATOR" and n.ativo]

    def get_provers(self) -> list[No]:
        return [n for n in self.nos.values() if n.tipo == "PROVER" and n.ativo]

    def get_nos_do_celular(self, plg_address: str) -> list[No]:
        ids = self.vinculos.get(plg_address, [])
        return [self.nos[i] for i in ids if i in self.nos]

    def get_status(self) -> dict:
        validators = self.get_validators()
        provers    = self.get_provers()
        return {
            "total_nos"        : len(self.nos),
            "validators_ativos": len(validators),
            "provers_ativos"   : len(provers),
            "nos_com_voto"     : len([n for n in validators if n.direito_voto]),
            "vinculos_ativos"  : len(self.vinculos)
        }

if __name__ == "__main__":
    _log.info("==================================================")
    _log.info(" [!] MOTOR DE CONSENSO V4.0 — PLEGMA DAG         ")
    _log.info("==================================================\n")

    consenso = MotorConsenso()

    PLG_DONO = "PLG9DC5642E1B2A67766F97367E062345B0723A7123"

    _log.info("--- REGISTRO: CELULAR DO DONO ---")
    consenso.registrar_no(
        node_id     = "IMEI_DONO_01",
        plg_address = PLG_DONO,
        device_type = "SMARTPHONE"
    )

    _log.info("\n--- REGISTRO: NOTEBOOK DO DONO ---")
    consenso.registrar_no(
        node_id     = "NOTEBOOK_DONO",
        plg_address = PLG_DONO,
        device_type = "NOTEBOOK",
        cpu_cores   = 8,
        ram_gb      = 16.0,
        has_gpu     = False
    )

    _log.info("\n--- REGISTRO: PC GAMER DO DONO ---")
    consenso.registrar_no(
        node_id     = "PC_GAMER_DONO",
        plg_address = PLG_DONO,
        device_type = "DESKTOP",
        cpu_cores   = 16,
        ram_gb      = 32.0,
        has_gpu     = True,
        gpu_vram_gb = 12.0
    )

    PLG_FARM = "PLG1234567890ABCDEF1234567890ABCDEF12345678"
    _log.info("\n--- REGISTRO: ASIC FARM (PLG diferente) ---")
    consenso.registrar_no(
        node_id     = "ASIC_FARM_01",
        plg_address = PLG_FARM,
        device_type = "ASIC",
        is_asic     = True
    )

    _log.info(f"\n--- NÓS VINCULADOS AO CELULAR {PLG_DONO[:12]}... ---")
    nos_dono = consenso.get_nos_do_celular(PLG_DONO)
    for n in nos_dono:
        _log.info(f"  [{n.tipo}] {n.node_id} — {n.categoria}")

    _log.info("\n--- DISTRIBUIÇÃO DE TRABALHO (1000 provas ZK) ---")
    dist = consenso.distribuir_trabalho(1000)
    for node_id, qtd in dist.items():
        no = consenso.nos[node_id]
        pct = qtd / 1000 * 100
        _log.info(f"  {node_id:<20} → {qtd:>4} provas ({pct:.1f}%) — PLG: {no.plg_address[:12]}...")

    _log.info("\n--- MONITORAMENTO TÉRMICO ---")
    consenso.monitorar_prover("PC_GAMER_DONO", hashrate=100.0, temperatura_c=70.0)
    consenso.monitorar_prover("PC_GAMER_DONO", hashrate=80.0,  temperatura_c=91.0)
    consenso.monitorar_prover("PC_GAMER_DONO", hashrate=110.0, temperatura_c=75.0)

    _log.info("\n--- STATUS DA REDE ---")
    status = consenso.get_status()
    for k, v in status.items():
        _log.info(f"  {k:<25}: {v}")

    _log.info("\n==================================================")