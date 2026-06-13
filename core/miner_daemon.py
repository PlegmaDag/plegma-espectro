"""
miner_daemon.py — Daemon headless do Miner Server
Levanta o HTTP na porta 8084 com um MinerEngine real conectado à DAG local.
Usado no servidor validador para expor /miner/status via nginx.
"""
import time
import threading
from miner_engine import MinerEngine
import miner_server

import logging
_log = logging.getLogger(__name__)

PLG_VALIDADOR = "PLG198840FFDD9FA7A8AEA2747C994B152B88A49F7C"
API_DAG       = "http://127.0.0.1:8080"
PORTA         = 8084

if __name__ == "__main__":
    _log.info(f"[MINER DAEMON] Iniciando MinerEngine para {PLG_VALIDADOR} ...")
    engine = MinerEngine(
        plg_address = PLG_VALIDADOR,
        node_id     = "SERVER_VALIDATOR_001",
        node_type   = "VALIDATOR",
        dag_url     = API_DAG,
    )

    server = miner_server.iniciar_servidor(engine, porta=PORTA)
    _log.info(f"[MINER DAEMON] HTTP ouvindo na porta {PORTA}")

    # Inicia mineração em thread separada
    t = threading.Thread(target=engine.iniciar, daemon=True)
    t.start()
    _log.info("[MINER DAEMON] Engine de mineração iniciado.")

    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        _log.info("[MINER DAEMON] Encerrando.")
        server.shutdown()
