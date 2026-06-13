import time
import blake3
import plegma_db

# =============================================================================
# SENTINELA CORE — V4.0 (HEGEMONIA BLAKE3)
# =============================================================================

MASTER_THRESHOLD    =  6_001.0
SENTINELA_THRESHOLD =  3_001.0
APOIADOR_MIN        =  1_000.0
GENESIS_MINING_MIN  =     10.0  # Genesis: 1 miner a partir de $1 / 10 PLG-G

BOOST_MASTER    = 2.0
BOOST_SENTINELA = 1.5
BOOST_APOIADOR  = 1.0

def check_priority(plg_address: str) -> dict:
    saldo = plegma_db.carregar_saldo_plgg(plg_address)

    # Participantes < 1.000 PLG-G não possuem título ou direitos políticos
    if saldo >= MASTER_THRESHOLD:
        categoria, boost = "MASTER", BOOST_MASTER
    elif saldo >= SENTINELA_THRESHOLD:
        categoria, boost = "SENTINELA", BOOST_SENTINELA
    elif saldo >= APOIADOR_MIN:
        categoria, boost = "APOIADOR", BOOST_APOIADOR
    else:
        categoria, boost = "PARTICIPANTE", 1.0

    if saldo <= 0:
        peso_voto = 1.0
    elif saldo >= APOIADOR_MIN:
        peso_voto = max(1.01, min(5.0, round(1.01 + (saldo - 1_000.0) * (3.99 / 9_000.0), 4)))
    else:
        peso_voto = 1.0

    if saldo >= APOIADOR_MIN:
        max_mineradores = int(saldo // 1_000)
    elif saldo >= GENESIS_MINING_MIN:
        max_mineradores = 1
    else:
        max_mineradores = 0

    return {
        "plg_address"     : plg_address,
        "saldo_plgg"      : saldo,
        "genesis_balance" : plegma_db.carregar_saldo_plgg_genesis(plg_address),
        "categoria"       : categoria,
        "boost"           : boost,
        "peso_voto"       : peso_voto,
        "max_mineradores" : max_mineradores
    }

class Vigia:
    def __init__(self):
        self.banned_jurisdictions = ["KP", "IR", "SY"]
        self.MAX_MOBILE_NODES_PER_IP = 6
        self.active_mobile_connections: dict = plegma_db.carregar_estado("vigia_connections", {})
        self.phr_blacklist = ["terrorismo", "abuso_infantil", "darknet_market", "hitman_service"]

    def verificar_borda(self, ip_address, country_code, hardware_id, node_type, payload):
        if country_code in self.banned_jurisdictions:
            return False, f"VIGIA: Jurisdição bloqueada ({country_code})"

        hard_hash = blake3.blake3(hardware_id.encode('utf-8')).hexdigest()
        if node_type == "MOBILE":
            if ip_address not in self.active_mobile_connections:
                self.active_mobile_connections[ip_address] = []
            if hard_hash not in self.active_mobile_connections[ip_address]:
                if len(self.active_mobile_connections[ip_address]) >= self.MAX_MOBILE_NODES_PER_IP:
                    return False, f"VIGIA: Smurfing. Limite de {self.MAX_MOBILE_NODES_PER_IP} nós por IP atingido."
                self.active_mobile_connections[ip_address].append(hard_hash)
                plegma_db.salvar_estado("vigia_connections", self.active_mobile_connections)

        if payload:
            for word in self.phr_blacklist:
                if word in payload.lower():
                    return False, f"VIGIA [PHR]: Conteúdo ilícito detectado ('{word}')"
        return True, "Vigia: Borda Segura"

class Crivo:
    def interceptar_mempool(self, tx_payload: str, amount: float):
        if amount < 0 or amount > 21_000_000_000:
            return False, "CRIVO: Ataque de Overflow/Underflow matemático detectado."
        if "recursive_call" in tx_payload or "reentrancy_exploit" in tx_payload:
            return False, "CRIVO: Ataque de Reentrância detetado no payload do contrato."
        return True, "Crivo: Mempool Limpo e Seguro"

class Escudo:
    def __init__(self):
        self.reputation_system: dict = plegma_db.carregar_bans()
        if self.reputation_system:
            print(f"  [ESCUDO] {len(self.reputation_system)} ban(s) carregado(s) da base de dados.")

    def registrar_no(self, uidg: str, stake_inicial: float):
        if uidg not in self.reputation_system:
            self.reputation_system[uidg] = {"score": 100, "staked": stake_inicial}
        elif self.reputation_system[uidg]["score"] == -1:
            return

    def protocolo_slashing(self, uidg: str, motivo: str):
        if uidg in self.reputation_system:
            confiscado = self.reputation_system[uidg]["staked"]
            self.reputation_system[uidg]["staked"] = 0
            self.reputation_system[uidg]["score"]  = -1 
            plegma_db.salvar_ban(uidg, confiscado, motivo)
            print(f"  [!!!] ESCUDO ATIVADO: PROTOCOLO DE SLASHING [!!!]")
            print(f"  [X] Nó Infrator : {uidg}")
            print(f"  [X] Motivo      : {motivo}")
            print(f"  [X] Punição     : {confiscado:,.2f} $PLG retidos foram QUEIMADOS/CONFISCADOS.")
            print(f"  [X] Status UIDG : Banido do Consenso da DAG. [GRAVADO EM DISCO]\n")
            return True
        return False

    def is_banido(self, uidg: str) -> bool:
        if self.reputation_system.get(uidg, {}).get("score") == -1:
            return True
        return plegma_db.is_banido(uidg)

class SentinelaCore:
    def __init__(self):
        self.vigia = Vigia()
        self.crivo = Crivo()
        self.escudo = Escudo()

    def processar_transacao(self, uidg, ip, pais, hw_id, tipo_no, payload, valor, is_double_spend=False):
        print(f"[*] Sentinela a intercetar transação do Nó {uidg}...")
        time.sleep(0.3)

        if self.escudo.is_banido(uidg):
            print(f"  [ESCUDO] Nó {uidg[:16]}... PERMANENTEMENTE BANIDO. Transação descartada.")
            return False

        self.escudo.registrar_no(uidg, stake_inicial=500.0)
        
        ok_vigia, msg_vigia = self.vigia.verificar_borda(ip, pais, hw_id, tipo_no, payload)
        if not ok_vigia:
            print(f"  {msg_vigia}")
            return False

        ok_crivo, msg_crivo = self.crivo.interceptar_mempool(payload, valor)
        if not ok_crivo:
            print(f"  {msg_crivo}")
            self.escudo.protocolo_slashing(uidg, msg_crivo)
            return False

        if is_double_spend:
            self.escudo.protocolo_slashing(uidg, "Tentativa comprovada de Gasto Duplo (Double Spend)")
            return False

        print("  [+] SENTINELA: Transação Limpa. Aprovada para a DAG.\n")
        return True

if __name__ == "__main__":
    print("==================================================")
    print(" [!] NÚCLEO SENTINELA MASTER INICIALIZADO (V4.0)  ")
    print("==================================================")
    
    sentinela = SentinelaCore()
    print("--- TESTE 1: Transação Normal ---")
    sentinela.processar_transacao("UIDG_ALFA", "10.0.0.1", "PT", "HW_1", "MOBILE", "Tx de 50 PLG", 50.0)
    print("--- TESTE 2: Ataque de Overflow (Hack) ---")
    sentinela.processar_transacao("UIDG_BETA", "10.0.0.2", "BR", "HW_2", "MOBILE", "Hacker Tx", 999999999999.0)
    print("--- TESTE 3: Tentativa de Gasto Duplo (Slashing) ---")
    sentinela.processar_transacao("UIDG_GAMA", "10.0.0.3", "US", "HW_3", "MINERADOR", "Tx Normal", 100.0, is_double_spend=True)
    print("==================================================")