import blake3
import json
import time
import threading
from datetime import datetime

# =============================================================================
# CORE DAG — Motor Principal da Rede PLEGMA V4.0 (PÓS-QUÂNTICA)
# DETERMINISMO ABSOLUTO (Aleatoriedade Banida)
#
# Fluxo completo de uma transação:
#
#   1. LatticeShield.sign_transaction()       — assinatura Dilithium3
#   2. DagSealEngine.generate_recursive_proof() — selo de integridade ≤ 22KB
#   3. LatticeShield.verify_transaction()     — validação da assinatura
#   4. PlegmaDAG.add_transaction()            — entrada determinística na DAG (2–5 pais)
#   5. AerariumProtocol.mine_tokens()         — recompensa em lock-up 30d
# =============================================================================

from lattice_shield import LatticeShield
from zk_press import DagSealEngine
from aerarium import AerariumProtocol
import plegma_db
import gossip

import logging
_log = logging.getLogger(__name__)

class Transaction:
    def __init__(self, sender: str, receiver: str, amount: float,
                 parents: list, signature: str, public_key: bytes,
                 timestamp: int = None):
        self.sender = sender
        self.receiver = receiver
        self.amount = amount
        self.parents = sorted(parents) # Ordenação estrita para garantir determinismo de hash
        self.timestamp = timestamp if timestamp is not None else int(time.time())
        self.signature = signature
        self.public_key = public_key
        self.zk_proof: bytes = None
        self.tx_hash = self._generate_hash()

    def _generate_hash(self) -> str:
        """Hash BLAKE3 determinístico — O ID da transação é a sua própria prova."""
        tx_data = {
            "sender": self.sender,
            "receiver": self.receiver,
            "amount": self.amount,
            "parents": self.parents,
            "timestamp": self.timestamp
        }
        tx_string = json.dumps(tx_data, sort_keys=True).encode('utf-8')
        return blake3.blake3(tx_string).hexdigest()

    def to_dict(self) -> dict:
        return {
            "tx_hash": self.tx_hash,
            "sender": self.sender,
            "receiver": self.receiver,
            "amount": self.amount,
            "parents": self.parents,
            "timestamp": self.timestamp,
            "signature": self.signature,
            "zk_proof_size": len(self.zk_proof) if self.zk_proof else 0
        }

MAX_TIPS = 1000

class PlegmaDAG:
    def __init__(self, genesis_hash: str, launch_date: datetime = None):
        self.genesis_hash = genesis_hash

        plegma_db.inicializar_banco()
        self.transactions: dict = plegma_db.carregar_transacoes()

        tips_salvas = plegma_db.carregar_tips()
        self.tips: set = set(tips_salvas) if tips_salvas else {genesis_hash}
        self._tips_lock = threading.Lock()

        self._zk = DagSealEngine()
        self._aerarium = AerariumProtocol(launch_date=launch_date)

        self._total_rejeitadas = plegma_db.carregar_estado("total_rejeitadas", 0)
        self._total_aceitas    = plegma_db.carregar_estado("total_aceitas", 0)

        self._nos_unicos: set = set(plegma_db.carregar_estado("nos_unicos_list", []))

        _log.info("==================================================")
        _log.info(" [!] MOTOR DAG PLEGMA V4.0 INICIALIZADO          ")
        _log.info("==================================================")
        _log.info(f"[*] Vértice Gênese : {self.genesis_hash[:32]}...")
        _log.info(f"[*] Criptografia   : Crystals-Dilithium3 (NIST Nível 3)")
        _log.info(f"[*] Hash Hegemónico: BLAKE3")
        _log.info(f"[*] Determinismo   : ABSOLUTO (PRNGs Banidos)")
        _log.info(f"[*] Transações     : {len(self.transactions)} carregadas do banco")
        _log.info("==================================================\n")

    def _selecionar_pais_deterministico(self, sender: str, receiver: str, amount: float, ts: int) -> list:
        """
        Gossip Protocol V4.0: Seleciona 2–5 tips de forma estritamente determinística,
        ancorando a aleatoriedade ao oráculo BLAKE3 da própria transação em vias de nascer.
        """
        with self._tips_lock:
            tips_snapshot = sorted(self.tips)  # snapshot ordenado — thread-safe

        if len(tips_snapshot) <= 1:
            return [self.genesis_hash]

        # Semente determinística baseada na futura transação
        seed_data = f"SYS_PARENT_SELECTOR:{sender}:{receiver}:{amount}:{ts}".encode('utf-8')
        hasher = blake3.blake3(seed_data)
        entropy = hasher.hexdigest()

        # Determina o número de pais (2 a 5) baseado nos primeiros bytes da entropia
        num_parents = 2 + (int(entropy[:8], 16) % 4)
        num_parents = min(num_parents, len(tips_snapshot))

        # Ordenação rigorosa para garantir paridade entre diferentes nós executando o mesmo estado
        sorted_tips = tips_snapshot
        
        selected_parents = set()
        offset = 8
        
        while len(selected_parents) < num_parents:
            chunk = entropy[offset:offset+8]
            if not chunk:
                hasher.update(b"_EXPAND_ENTROPY_")
                entropy = hasher.hexdigest()
                offset = 0
                continue
                
            idx = int(chunk, 16) % len(sorted_tips)
            selected_parents.add(sorted_tips[idx])
            offset += 8
            
        return list(selected_parents)

    def _atualizar_topologia(self, tx_hash: str, parents: list):
        with self._tips_lock:
            self.tips.add(tx_hash)
            for parent in parents:
                if parent != self.genesis_hash:
                    self.tips.discard(parent)

            if len(self.tips) > MAX_TIPS:
                # Remove os tips mais antigos (excluindo génese) de forma determinística
                removiveis = sorted(self.tips - {self.genesis_hash})
                for h in removiveis[:len(self.tips) - MAX_TIPS]:
                    self.tips.discard(h)

            plegma_db.salvar_tips(list(self.tips))

    def add_transaction(self, sender: str, receiver: str, amount: float,
                        shield: LatticeShield, miner_address: str,
                        node_type: str = "VALIDATOR") -> dict:
                        
        current_day = self._aerarium.get_network_age_days()
        is_anchor   = (amount <= 0)
        
        if is_anchor and current_day >= 30:
            self._total_rejeitadas += 1
            _log.info(f"[X] REJEITADA: Vértice vazio ou valor zero na fase madura.")
            return None

        if not shield.public_key or not shield.private_key:
            self._total_rejeitadas += 1
            _log.info(f"[X] REJEITADA: Nó sem identidade Dilithium3 ativa.")
            return None

        if sender == receiver:
            self._total_rejeitadas += 1
            _log.info(f"[X] REJEITADA: Transação sintética (sender==receiver) rejeitada pelo protocolo.")
            return None

        # Fixação de Estado Temporal
        ts_assinatura = int(time.time())

        # Seleção Determinística de Arestas (Pais)
        parents = self._selecionar_pais_deterministico(sender, receiver, amount, ts_assinatura)

        dados_para_assinar = json.dumps({
            "sender": sender,
            "receiver": receiver,
            "amount": amount,
            "parents": sorted(parents),
            "timestamp": ts_assinatura
        }, sort_keys=True)
        hash_para_assinar = blake3.blake3(dados_para_assinar.encode()).hexdigest()

        assinatura = shield.sign_transaction(hash_para_assinar)

        assinatura_valida = shield.verify_transaction(
            hash_para_assinar, assinatura, shield.public_key
        )
        if not assinatura_valida:
            self._total_rejeitadas += 1
            _log.info(f"[X] REJEITADA: Assinatura Dilithium3 corrompida. Descarte imediato.")
            return None

        tx = Transaction(sender, receiver, amount, parents, assinatura, shield.public_key, timestamp=ts_assinatura)

        try:
            tx.zk_proof = self._zk.generate_recursive_proof(tx.tx_hash)
            zk_kb = len(tx.zk_proof) / 1024
            _log.info(f"[*] Selo de integridade gerado: {zk_kb:.2f} KB [OK]")
        except MemoryError as e:
            self._total_rejeitadas += 1
            _log.info(f"[X] REJEITADA: Falha de compressão ZK: {e}")
            return None

        prova_valida = self._zk.verify_proof(tx.zk_proof, tx.tx_hash)
        if not prova_valida:
            self._total_rejeitadas += 1
            _log.info(f"[X] REJEITADA: Matriz ZK inválida.")
            return None

        self.transactions[tx.tx_hash] = tx
        plegma_db.salvar_transacao({
            "tx_hash"      : tx.tx_hash,
            "sender"       : tx.sender,
            "receiver"     : tx.receiver,
            "amount"       : tx.amount,
            "parents"      : tx.parents,
            "timestamp"    : tx.timestamp,
            "signature"    : tx.signature,
            "zk_proof_size": len(tx.zk_proof) if tx.zk_proof else 0,
            "node_type"    : node_type
        })
        self._atualizar_topologia(tx.tx_hash, parents)
        self._total_aceitas += 1
        plegma_db.salvar_estado("total_aceitas", self._total_aceitas)

        _log.info(f"[+] VÉRTICE DE GRADE LIGADO: {tx.tx_hash[:24]}... | Pais: {len(parents)}")

        gossip.broadcast_vertice(tx.to_dict())

        if miner_address not in self._nos_unicos:
            self._nos_unicos.add(miner_address)
            plegma_db.salvar_estado("nos_unicos_list", list(self._nos_unicos))
            
        nos_ativos   = max(len(self._nos_unicos), 1)
        vertex_ts    = datetime.fromtimestamp(tx.timestamp)
        tx_fee       = (amount * 0.001) if (current_day >= 31 and not is_anchor) else 0.0
        
        recompensa, data_liberacao = self._aerarium.mine_tokens(
            miner_address,
            node_type=node_type,
            base_generation=1_000_000,
            active_nodes=nos_ativos,
            vertex_timestamp=vertex_ts,
            tx_fee=tx_fee
        )

        return {
            "status"              : "ACEITO",
            "tx_hash"             : tx.tx_hash,
            "sender"              : sender,
            "receiver"            : receiver,
            "amount"              : amount,
            "parents"             : parents,
            "zk_kb"               : round(len(tx.zk_proof) / 1024, 2),
            "node_type"           : node_type,
            "recompensa_minerador": recompensa,
            "vesting_liberacao"   : data_liberacao.strftime('%d/%m/%Y %H:%M') if data_liberacao else None
        }

    def get_status(self) -> dict:
        last_hash = list(self.transactions.keys())[-1] if self.transactions else self.genesis_hash
        return {
            "last_vertex_hash": last_hash,
            "timestamp": int(time.time()),
            "total_transacoes": len(self.transactions),
            "tips_pendentes": len(self.tips),  # set — thread-safe para len()
            "total_aceitas": self._total_aceitas,
            "total_rejeitadas": self._total_rejeitadas,
            "peso_zk": "16.41 KB" # Métrica corrigida do Lattice
        }

# =============================================================================
# SIMULAÇÃO END-TO-END SUPRIMIDA PARA PRODUÇÃO
# =============================================================================