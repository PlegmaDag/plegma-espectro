import json
import logging

_log = logging.getLogger(__name__)

# ── Blindagem de Oráculo Determinístico (Hard Fail) ─────────
try:
    import blake3
except ImportError:
    raise RuntimeError("[FALHA FATAL] Módulo blake3 ausente no Genesis Vertex.")

class GenesisVertex:
    def __init__(self):
        self.sys_sync_code = "ZKDAG_PLG_GENESIS_2026_FAIRLAUNCH"
        self.message = "GENESIS BLOCK - JUSTICE ABSOLUTE"
        
        # Timestamp determinístico (01 Jan 2026 00:00:00 UTC)
        self.timestamp = 1767225600 
        self.parents = [] 
        
        self.vertex_data = {
            "sync_code": self.sys_sync_code,
            "message": self.message,
            "timestamp": self.timestamp,
            "parents": self.parents
        }
        self.hash = self.generate_hash()

    def generate_hash(self):
        vertex_string = json.dumps(self.vertex_data, sort_keys=True).encode('utf-8')
        return blake3.blake3(vertex_string).hexdigest()

    def display(self):
        _log.info("==================================================")
        _log.info(" [!] INICIALIZANDO REDE PLEGMA (V4.0) [!]         ")
        _log.info("==================================================")
        _log.info(f"[*] SYS_SYNC_CODE : {self.sys_sync_code}")
        _log.info(f"[*] HASH BLAKE3   : {self.hash}")
        _log.info("==================================================")

if __name__ == "__main__":
    genesis = GenesisVertex()
    genesis.display()