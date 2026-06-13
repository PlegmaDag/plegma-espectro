import json
import logging
import threading
import time
import urllib.request
import urllib.error
import os
import base64
import plegma_db

_log = logging.getLogger(__name__)

# =============================================================================
# GOSSIP PROTOCOL — PLEGMA DAG V4.0 (PÓS-QUÂNTICO / DETERMINÍSTICO)
# Segurança: Nível 3 (NIST) — Imunidade Quântica Obrigatória.
# Hashing:   Hegemonia BLAKE3
# Diretriz:  Hard Fail ativo. Rebaixamento de segurança proibido.
# =============================================================================

try:
    from dilithium_py.dilithium import Dilithium3 as _D3
except ImportError:
    raise RuntimeError("[FALHA FATAL] dilithium-py ausente no Gossip. Rede operando fora da matriz segura.")

try:
    import blake3 as _blake3
except ImportError:
    raise RuntimeError("[FALHA FATAL] Módulo blake3 ausente. O protocolo P2P exige oráculo BLAKE3.")

def _ghash(data: bytes) -> str:
    return _blake3.blake3(data).hexdigest()

MAX_PROOF_BYTES = 22 * 1024  # §2.2 Limite rígido Zk-Press

def _verificar_vertice(tx_dict: dict) -> bool:
    """
    Verifica integridade Pós-Quântica de vértice recebido antes da inserção na DAG.
    O nó deve barrar propagações maliciosas ou fora do Estatuto de Compressão.
    """
    try:
        pub_hex = tx_dict.get("public_key", "")
        sig_b64 = tx_dict.get("signature", "")
        sender  = tx_dict.get("sender", "")
        zk_size = tx_dict.get("zk_proof_size", 0)

        # Vértices GENESIS são criados pelo sistema — sem chave pública de utilizador.
        # Verificamos apenas o sender canonical e o zk_proof_size.
        if tx_dict.get("node_type") == "GENESIS":
            if not sender.startswith("GENESIS"):
                _log.info("[SYS_GOSSIP] Vértice GENESIS rejeitado: sender não-canonical.")
                return False
            if zk_size <= 0 or zk_size > MAX_PROOF_BYTES:
                _log.info(f"[SYS_GOSSIP] Vértice GENESIS rejeitado: ZK Proof ({zk_size}b) inválido.")
                return False
            return True

        if not pub_hex or not sig_b64 or not sender:
            _log.info(f"[SYS_GOSSIP] Vértice rejeitado: Estrutura incompleta.")
            return False

        if zk_size <= 0 or zk_size > MAX_PROOF_BYTES:
            _log.info(f"[SYS_GOSSIP] Vértice rejeitado: ZK Proof ({zk_size} bytes) viola Estatuto de Compressão (Máx {MAX_PROOF_BYTES}).")
            return False

        pub_bytes = bytes.fromhex(pub_hex)

        # Matriz de Verificação: Endereço PLG = PLG + HASH(pubkey)[:40].upper()
        expected = "PLG" + _ghash(pub_bytes)[:40].upper()
        if expected != sender:
            _log.info(f"[SYS_GOSSIP] Vértice rejeitado: Endereço diverge da chave de grade.")
            return False

        # Reconstrução determinística do payload assinado
        dados = json.dumps({
            "sender"   : tx_dict["sender"],
            "receiver" : tx_dict["receiver"],
            "amount"   : tx_dict["amount"],
            "parents"  : sorted(tx_dict["parents"]),
            "timestamp": tx_dict["timestamp"]
        }, sort_keys=True)
        
        hash_assinado = _ghash(dados.encode())
        sig_bytes = base64.b64decode(sig_b64)
        
        # Validação Dilithium3 Rigorosa
        valido = _D3.verify(pub_bytes, hash_assinado.encode("utf-8"), sig_bytes)
        if not valido:
            _log.info(f"[SYS_GOSSIP] Vértice rejeitado: Assinatura Lattice (Dilithium3) inválida ({sender[:12]}...).")
        return valido

    except Exception as e:
        _log.info(f"[SYS_GOSSIP] Erro crítico na validação de vértice: {e}")
        return False

PEERS_FILE = os.path.join(os.path.dirname(__file__), "peers.json")

def carregar_peers() -> list:
    try:
        with open(PEERS_FILE, encoding='utf-8') as f:
            return json.load(f).get("peers", [])
    except Exception:
        return []

# =============================================================================
# BROADCAST — Propagação P2P em Background
# =============================================================================

def broadcast_vertice(tx_dict: dict):
    peers = carregar_peers()
    if not peers: return
    payload = json.dumps(tx_dict).encode('utf-8')
    for peer in peers:
        threading.Thread(target=_enviar_para_peer, args=(peer, payload), daemon=True).start()

def _enviar_para_peer(peer_url: str, payload: bytes):
    try:
        req = urllib.request.Request(
            f"{peer_url}/api/peer/vertex",
            data=payload,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=5):
            pass
        _log.info(f"[SYS_GOSSIP] Vértice de grade propagado para {peer_url}")
    except Exception as e:
        _log.info(f"[SYS_GOSSIP] Peer inatingível {peer_url}: {e}")

# =============================================================================
# SYNC — Sincronização Topológica Determinística
#
# Ordem de merge após isolamento: timestamp ascendente.
# Garante que a DAG reconstrói o mesmo grafo em qualquer nó dado o mesmo
# conjunto de vértices — independentemente da ordem de chegada.
# =============================================================================

def sincronizar_com_peers(dag):
    peers = carregar_peers()
    if not peers:
        return
    threading.Thread(target=_sync_loop, args=(dag, peers), daemon=True).start()

def iniciar_loop_reconexao(dag, intervalo: int = 300):
    """Re-sincroniza com todos os peers a cada `intervalo` segundos.
    Cobre o caso de isolamento de continente: quando o nó volta à rede,
    a próxima iteração do loop detecta os vértices em falta e faz merge."""
    def _loop():
        while True:
            time.sleep(intervalo)
            peers = carregar_peers()
            for peer in peers:
                try:
                    _sincronizar_peer(peer, dag)
                except Exception:
                    pass
    threading.Thread(target=_loop, daemon=True).start()

def _sync_loop(dag, peers: list):
    for peer in peers:
        try:
            _sincronizar_peer(peer, dag)
        except Exception as e:
            _log.info(f"[SYS_GOSSIP] Erro no sync com {peer}: {e}")

def _buscar_vertice_remoto(peer_url: str, tx_hash: str) -> dict | None:
    try:
        req = urllib.request.Request(f"{peer_url}/api/peer/vertex/{tx_hash}", method='GET')
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except Exception:
        return None

def _aceitar_vertice(tx_dict: dict, dag, peer_url: str, visitados: set, profundidade: int = 0):
    """Insere um vértice na DAG garantindo que todos os seus pais existem primeiro.
    Resolução recursiva de pais — máximo 64 níveis de profundidade."""
    tx_hash = tx_dict.get("tx_hash", "")
    if not tx_hash or tx_hash in dag.transactions or tx_hash in visitados:
        return
    if profundidade > 64:
        _log.info(f"[SYS_GOSSIP] Profundidade máxima atingida em {tx_hash[:16]}... — abortando ramo.")
        return
    visitados.add(tx_hash)

    # Garantir que todos os pais existem antes de inserir este vértice
    for parent_hash in tx_dict.get("parents", []):
        if parent_hash == dag.genesis_hash or parent_hash in dag.transactions:
            continue
        parent_dict = _buscar_vertice_remoto(peer_url, parent_hash)
        if parent_dict:
            _aceitar_vertice(parent_dict, dag, peer_url, visitados, profundidade + 1)

    # Verificação pós-quântica antes da inserção
    if not _verificar_vertice(tx_dict):
        _log.info(f"[SYS_GOSSIP] Interceptação: Vértice {tx_hash[:16]}... REJEITADO.")
        return

    plegma_db.salvar_transacao(tx_dict)
    dag.transactions[tx_hash] = tx_dict
    dag._atualizar_topologia(tx_hash, tx_dict.get("parents", []))
    _log.info(f"[SYS_GOSSIP] Vértice integrado: {tx_hash[:24]}... (profundidade={profundidade})")

def _sincronizar_peer(peer_url: str, dag):
    try:
        req = urllib.request.Request(f"{peer_url}/api/peer/hashes", method='GET')
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())

        peer_hashes = set(data.get("hashes", []))
        meus_hashes = set(dag.transactions.keys())
        faltando    = peer_hashes - meus_hashes

        if not faltando:
            _log.info(f"[SYS_GOSSIP] {peer_url} — Topologia sincronizada.")
            return

        _log.info(f"[SYS_GOSSIP] {peer_url} — {len(faltando)} vértices em falta. A buscar...")

        # Fase 1: buscar todos os vértices em falta para obter timestamps
        vertices_pendentes: dict[str, dict] = {}
        for tx_hash in faltando:
            tx_dict = _buscar_vertice_remoto(peer_url, tx_hash)
            if tx_dict:
                vertices_pendentes[tx_hash] = tx_dict

        # Fase 2: ordenar por timestamp ascendente — merge determinístico
        # Garante que o mesmo conjunto de vértices produz a mesma DAG em qualquer nó.
        ordenados = sorted(vertices_pendentes.values(), key=lambda v: (v.get("timestamp", 0), v.get("tx_hash", "")))

        visitados: set = set()
        for tx_dict in ordenados:
            _aceitar_vertice(tx_dict, dag, peer_url, visitados)

        _log.info(f"[SYS_GOSSIP] {peer_url} — Merge concluído: {len(visitados)} vértices integrados.")

    except Exception as e:
        _log.info(f"[SYS_GOSSIP] Falha de handshake com {peer_url}: {e}")