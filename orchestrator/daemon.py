#!/usr/bin/env python3
"""
PLEGMA DAEMON — Orquestrador Autónomo 24/7
Gerencia todos os agentes especializados sem intervenção humana.

Agentes activos:
  server_monitor      — 3 min          — saúde dos 4 servidores + auto-restart
  social_manager      — 15 min         — moderação da rede social
  governance_watch    — 30 min         — governança, propostas, voting
  analyst             — 05h+17h Madrid — relatório período noturno (17h→05h) e diurno (05h→17h)
  network_sync        — 2 horas        — replicação entre servidores
  security_scan       — 6 horas        — scan de vulnerabilidades (sentinela)
  consensus_review    — 12 horas       — revisão tri-IA de mudanças pendentes
  code_audit          — 24h (03:00)    — auditoria de código
  briefing            — 05:00+17:00    — relatório textual das últimas horas → relatorios/
  auto_update         — diário 06:00   — pesquisa repos públicos · implementa só com consenso
  stability_guardian  — diário 02:00   — score de saúde + propostas de melhoria de repos auditados

Uso:
  python daemon.py            ← inicia daemon (bloqueante)
  python daemon.py --status   ← mostra estado dos jobs
  python daemon.py --run <agente>  ← executa agente manualmente
"""

import sys
import signal
import logging
import argparse
import time
from pathlib import Path
from datetime import datetime, timezone

# Setup de path
sys.path.insert(0, str(Path(__file__).parent))

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED
import event_log
from daemon_config import SCHEDULE, DAEMON_LOG

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(str(DAEMON_LOG), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger("plegma.daemon")

# ── Registry de agentes (lazy-load) ─────────────────────────────────────────
_AGENTS = {}

def _agent(name: str):
    if name not in _AGENTS:
        if name == "server_monitor":
            from agents.server_monitor   import ServerMonitorAgent;   _AGENTS[name] = ServerMonitorAgent()
        elif name == "social_manager":
            from agents.social_manager   import SocialManagerAgent;   _AGENTS[name] = SocialManagerAgent()
        elif name == "governance_watch":
            from agents.governance_watch import GovernanceWatchAgent; _AGENTS[name] = GovernanceWatchAgent()
        elif name == "analyst":
            from agents.analyst          import AnalystAgent;         _AGENTS[name] = AnalystAgent()
        elif name == "network_sync":
            from agents.network_sync     import NetworkSyncAgent;     _AGENTS[name] = NetworkSyncAgent()
        elif name == "security":
            from agents.security         import SecurityAgent;        _AGENTS[name] = SecurityAgent()
        elif name == "consensus_engine":
            from agents.consensus_engine import ConsensusEngineAgent; _AGENTS[name] = ConsensusEngineAgent()
        elif name == "seed_guardian":
            from agents.seed_guardian    import SeedGuardianAgent;    _AGENTS[name] = SeedGuardianAgent()
        elif name == "validation":
            from agents.validation       import ValidationAgent;      _AGENTS[name] = ValidationAgent()
        elif name == "briefing":
            from agents.briefing_agent   import BriefingAgent;        _AGENTS[name] = BriefingAgent()
        elif name == "auto_update":
            from agents.auto_update_agent import AutoUpdateAgent;     _AGENTS[name] = AutoUpdateAgent()
        elif name == "stability_guardian":
            from agents.stability_guardian import StabilityGuardianAgent; _AGENTS[name] = StabilityGuardianAgent()
        elif name == "cartorio_monitor":
            from agents.cartorio_monitor import CartorioMonitorAgent; _AGENTS[name] = CartorioMonitorAgent()
        elif name == "cartorio_deploy":
            from agents.cartorio_deploy_agent import CartorioDeployAgent; _AGENTS[name] = CartorioDeployAgent()
    return _AGENTS.get(name)


# ── Jobs agendados ───────────────────────────────────────────────────────────
def _run(agent_name: str, task: str = "", context: dict = None):
    """Wrapper seguro para execução de agentes — nunca deixa crashar o scheduler."""
    try:
        ag = _agent(agent_name)
        if not ag:
            log.error(f"Agente '{agent_name}' não encontrado")
            return
        result = ag.run(task or agent_name, context or {})
        sym = {"SUCCESS": "✓", "PARTIAL": "⚑", "FAILURE": "✕"}.get(result.status, "?")
        log.info(f"{sym} [{agent_name}] {result.summary} ({result.duration_ms}ms)")
        if result.status != "SUCCESS" and result.details:
            for d in result.details:
                log.error(f"  DETALHE: {d}")
    except Exception as e:
        log.error(f"✕ [{agent_name}] EXCEPÇÃO: {e}", exc_info=True)
        event_log.log(agent_name, "exception", "FAIL", str(e)[:200])


def job_server_monitor():
    _run("server_monitor", "verificar saúde dos servidores")

def job_social_manager():
    _run("social_manager", "moderar rede social e publicar dev-log se necessário")

def job_governance_watch():
    _run("governance_watch", "verificar estado de governança e propostas")

def job_analyst_manha():
    """05h Madrid (03h UTC) — Relatório Período Noturno 17h→05h."""
    _run("analyst", "periodo=noturno", {"periodo": "noturno", "label": "17h→05h (período noturno)"})

def job_analyst_tarde():
    """17h Madrid (15h UTC) — Relatório Período Diurno 05h→17h."""
    _run("analyst", "periodo=diurno", {"periodo": "diurno", "label": "05h→17h (período diurno)"})

def job_network_sync():
    _run("network_sync", "verificar sincronização entre servidores")

def job_security_scan():
    _run("security", "auditoria de segurança completa")

def job_code_audit():
    _run("validation", "auditoria de qualidade de código")

def job_seed_guardian():
    _run("seed_guardian", "verificar e replicar seed backups para 3 cópias")

def job_briefing():
    _run("briefing", "gerar briefing das últimas 12h")

def job_auto_update():
    _run("auto_update", "pesquisar novidades em repositórios públicos")

def job_stability_guardian():
    _run("stability_guardian", "avaliar saúde do sistema e propor melhorias de repos auditados")

def job_cartorio_monitor():
    _run("cartorio_monitor", "verificar saúde do Cartório Digital nos 4 nós")

def job_consensus_review():
    """Revisão periódica tri-IA do estado geral do projecto."""
    from agents.consensus_engine import reach_consensus
    import requests

    try:
        status = requests.get("https://plegmadag.com/api/status", timeout=8).json()
        nos    = status.get("peers", 0)
    except Exception:
        nos = 0

    ev = event_log.stats()
    prompt = (
        f"Estado actual da rede PLEGMA DAG:\n"
        f"- Nós activos: {nos}\n"
        f"- Eventos no audit log: {ev.get('total', 0)}\n"
        f"- Agentes por frequência: {ev.get('by_agent', {})}\n\n"
        f"Há alguma acção crítica que o daemon deveria executar automaticamente "
        f"para melhorar a saúde da rede? Responde APPROVE se está tudo bem, "
        f"REJECT se há problemas críticos que exigem atenção imediata."
    )
    result = reach_consensus(prompt)
    log.info(f"⬡ [consensus] Revisão periódica: {'APROVADO' if result['approved'] else 'ATENÇÃO NECESSÁRIA'} "
             f"({result['approvals']}/3)")


# ── APScheduler setup ────────────────────────────────────────────────────────
def _build_scheduler() -> BackgroundScheduler:
    sched = BackgroundScheduler(timezone="UTC", job_defaults={
        "coalesce":     True,   # executa uma vez se atrasado
        "max_instances": 1,     # nunca mais de 1 instância por job
        "misfire_grace_time": 300,
    })

    # Intervalo fixo para todos os jobs de monitoramento
    sched.add_job(job_server_monitor,   "interval", seconds=SCHEDULE["server_monitor"],   id="server_monitor",   next_run_time=datetime.now(timezone.utc))
    sched.add_job(job_social_manager,   "interval", seconds=SCHEDULE["social_manager"],   id="social_manager")
    sched.add_job(job_governance_watch, "interval", seconds=SCHEDULE["governance_watch"], id="governance_watch")
    # Analyst — 05h Madrid (03h UTC) e 17h Madrid (15h UTC)
    sched.add_job(job_analyst_manha,    "cron", hour=3,  minute=0, id="analyst_manha")
    sched.add_job(job_analyst_tarde,    "cron", hour=15, minute=0, id="analyst_tarde")
    sched.add_job(job_network_sync,     "interval", seconds=SCHEDULE["network_sync"],     id="network_sync")
    sched.add_job(job_security_scan,    "interval", seconds=SCHEDULE["security_scan"],    id="security_scan")
    sched.add_job(job_seed_guardian,    "interval", seconds=SCHEDULE["seed_guardian"],    id="seed_guardian")
    sched.add_job(job_consensus_review, "interval", seconds=SCHEDULE["consensus_review"], id="consensus_review")

    # Auditoria de código — diariamente às 3h UTC
    sched.add_job(job_code_audit,   "cron", hour=3,  minute=0, id="code_audit")

    # Briefing — 05:00 e 17:00 UTC
    sched.add_job(job_briefing,     "cron", hour=5,  minute=0, id="briefing_manha")
    sched.add_job(job_briefing,     "cron", hour=17, minute=0, id="briefing_tarde")

    # Auto-update — diariamente às 06:00 UTC
    sched.add_job(job_auto_update,        "cron", hour=6,  minute=0, id="auto_update")

    # Stability Guardian — diariamente às 02:00 UTC (antes do code_audit)
    sched.add_job(job_stability_guardian, "cron", hour=2,  minute=0, id="stability_guardian")

    # Cartório Digital — a cada 5 minutos (serviço de produção activo)
    sched.add_job(job_cartorio_monitor, "interval", seconds=300, id="cartorio_monitor",
                  next_run_time=datetime.now(timezone.utc))

    return sched


def _on_job_event(event):
    if event.exception:
        log.error(f"Job '{event.job_id}' falhou: {event.exception}")
        event_log.log(event.job_id, "job_error", "FAIL", str(event.exception)[:200])


# ── CLI ──────────────────────────────────────────────────────────────────────
def _print_status(sched: BackgroundScheduler):
    print("\n⬡ PLEGMA DAEMON — Jobs Agendados")
    print(f"  {'ID':<20} {'Próxima execução':<25} {'Intervalo'}")
    print("  " + "─" * 65)
    for job in sched.get_jobs():
        next_run = str(job.next_run_time)[:19] if job.next_run_time else "N/A"
        trigger  = str(job.trigger)[:25]
        print(f"  {job.id:<20} {next_run:<25} {trigger}")

    ev = event_log.stats()
    print(f"\n  Audit log: {ev.get('total', 0)} eventos · último: {ev.get('last_ts', 0):.0f}")
    print()


def main():
    parser = argparse.ArgumentParser(description="PLEGMA Daemon — Orquestrador 24/7")
    parser.add_argument("--status", action="store_true", help="Mostrar estado dos jobs")
    parser.add_argument("--run",    default=None,        help="Executar agente manualmente")
    args = parser.parse_args()

    if args.run:
        log.info(f"Execução manual: {args.run}")
        _run(args.run)
        return

    # ── Boot ─────────────────────────────────────────────────────────────────
    log.info("=" * 60)
    log.info("  ⬡ PLEGMA DAEMON v2.0 — ORQUESTRADOR AUTÓNOMO 24/7")
    log.info("=" * 60)
    log.info(f"  Agentes activos: {len(SCHEDULE) + 3}")  # +3: briefing + auto_update + stability_guardian (cron)
    log.info(f"  Audit log:       {Path('daemon_events.db').absolute()}")
    log.info(f"  Logs:            {DAEMON_LOG}")
    log.info("=" * 60)

    event_log.log("daemon", "boot", "OK", "PLEGMA Daemon iniciado")

    sched = _build_scheduler()
    sched.add_listener(_on_job_event, EVENT_JOB_ERROR | EVENT_JOB_EXECUTED)
    sched.start()

    if args.status:
        _print_status(sched)
        sched.shutdown()
        return

    # ── Loop principal — aguarda sinal de paragem ────────────────────────────
    def _shutdown(sig, frame):
        log.info("\n⬡ Sinal recebido — encerrando daemon...")
        event_log.log("daemon", "shutdown", "OK", f"Sinal {sig} recebido")
        sched.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    log.info("⬡ Daemon activo. Ctrl+C para encerrar.")
    _print_status(sched)

    try:
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        sched.shutdown()
        log.info("⬡ Daemon encerrado.")


if __name__ == "__main__":
    main()
