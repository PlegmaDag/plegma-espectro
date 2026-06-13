#!/usr/bin/env python3
"""
PLEGMA DAEMON — Configuração Central
Todos os agentes lêem daqui. Sem hardcode fora deste ficheiro.
"""

import os
from pathlib import Path

ROOT = Path("D:/PROJETO_Plegma_DAG")
CORE = ROOT / "PLEGMA_CORE"
LANDING = ROOT / "PLEGMA_LANDING"
ORCHESTRATOR = ROOT / "PLEGMA_ORCHESTRATOR"

# ── Servidores ──────────────────────────────────────────────────────────────
NODES = {
    "eur": {"ip": "213.199.42.88",   "label": "EUR", "primary": True,  "domain": "plegmadag.com"},
    "usa": {"ip": "209.126.7.120",   "label": "USA", "primary": False, "domain": "usa.plegmadag.com"},
    "mum": {"ip": "217.217.251.206", "label": "MUM", "primary": False, "domain": "mum.plegmadag.com"},
    "sin": {"ip": "82.197.70.189",   "label": "SIN", "primary": False, "domain": "sin.plegmadag.com"},
}
API_PRIMARY = "https://plegmadag.com"
SSH_KEY     = r"C:\Users\Alves\.ssh\id_ed25519"
SSH_USER    = "root"
REMOTE_CORE = "/root/PLEGMA_CORE"

# Serviços monitorados por ordem de prioridade
SERVICES = ["plegma-core", "plegma-auth", "plegma-wallet", "plegma-miner", "plegma-cartorio"]

# Portas de saúde por serviço
SERVICE_PORTS = {
    "plegma-core":     8080,
    "plegma-auth":     8082,
    "plegma-wallet":   8083,
    "plegma-cartorio": 8010,
}

# ── Cartório Digital ──────────────────────────────────────────────────────────
CARTORIO_PORT      = 8010
CARTORIO_SERVICE   = "plegma-cartorio"
CARTORIO_REMOTE    = "/root/PLEGMA_CARTORIO"
CARTORIO_DOMAIN    = "timestamp.plegmadag.com"
CARTORIO_LOCAL     = Path(r"C:\Users\Alves\OneDrive\002 HOLDING\04 PROJETOS\CARTORIO DIGITAL\app")

# ── Autenticação ─────────────────────────────────────────────────────────────
def _read_local(name: str) -> str:
    p = ROOT / name
    return p.read_text(encoding="utf-8").strip() if p.exists() else ""

ADMIN_KEY = _read_local("admin_key.local")

# ── APIs de IA ───────────────────────────────────────────────────────────────
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
GEMINI_KEY    = os.environ.get("GEMINI_API_KEY", "")
GROQ_KEY      = os.environ.get("GROQ_API_KEY", "")
GITHUB_TOKEN  = os.environ.get("GITHUB_TOKEN", "")

# ── Schedules (segundos) ─────────────────────────────────────────────────────
SCHEDULE = {
    "server_monitor":    180,       # 3 minutos
    "social_manager":    900,       # 15 minutos
    "governance_watch":  1800,      # 30 minutos
    # analyst: cron às 03h UTC (05h Madrid) e 15h UTC (17h Madrid) — ver daemon.py
    "network_sync":      7200,      # 2 horas
    "security_scan":     21600,     # 6 horas
    "code_audit":        86400,     # 24 horas (3h da manhã)
    "consensus_review":  43200,     # 12 horas
    "seed_guardian":     3600,      # 1 hora — garante 3 cópias por seed
    # briefing: cron 05:00 e 17:00 UTC — não usa interval, ver daemon.py
    # auto_update: cron diário às 06:00 UTC — pesquisa repos públicos
}

# ── Limites de spam social ───────────────────────────────────────────────────
SPAM = {
    "min_body_len":      10,    # posts com menos chars são spam
    "max_posts_per_hour": 8,    # limite por autor por hora
    "max_duplicate_ratio": 0.8, # similaridade para considerar duplicado
}

# ── Logs ─────────────────────────────────────────────────────────────────────
LOG_DIR   = ORCHESTRATOR / "logs"
LOG_DIR.mkdir(exist_ok=True)
DAEMON_LOG = LOG_DIR / "daemon.log"
