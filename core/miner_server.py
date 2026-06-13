import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

# =============================================================================
# MINER SERVER — API HTTP do Minerador V1.0
# Porta: 8084
#
# Rotas:
#   GET /miner/status  — stats completos do minerador
#   GET /miner/pause   — pausa a mineração
#   GET /miner/resume  — retoma a mineração
# =============================================================================


_CORS_ORIGINS = {"https://plegmadag.com", "https://plagmadag.com"}

class MinerAPIHandler(BaseHTTPRequestHandler):

    engine = None  # Injetado externamente

    def _cors(self):
        origin = self.headers.get("Origin", "")
        self.send_header("Access-Control-Allow-Origin",
                         origin if origin in _CORS_ORIGINS else "https://plegmadag.com")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")

    def _json(self, status: int, data: dict):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/miner/status":
            if self.engine:
                stats = self.engine.get_stats()
                stats["uptime_fmt"] = self.engine.formatar_uptime()
                stats["pausado"]    = self.engine._pausado
                self._json(200, stats)
            else:
                self._json(503, {"erro": "Engine não inicializado."})

        elif path == "/miner/pause":
            if self.engine and self.engine._rodando:
                self.engine.pausar()
            self._json(200, {"ok": True, "status": "PAUSADO"})

        elif path == "/miner/resume":
            if self.engine and self.engine._pausado:
                self.engine.retomar()
            self._json(200, {"ok": True, "status": "MINERANDO"})

        else:
            self._json(404, {"erro": "Rota não encontrada."})

    def log_message(self, format, *args):
        return


def iniciar_servidor(engine, porta: int = 8084):
    """Inicia o servidor HTTP do minerador em thread separada."""
    MinerAPIHandler.engine = engine

    server = HTTPServer(("", porta), MinerAPIHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server
