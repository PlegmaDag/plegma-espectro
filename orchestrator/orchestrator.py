#!/usr/bin/env python3
"""
PLEGMA ORCHESTRATOR — CLI Principal
Orquestrador local de agentes para construção, verificação e manutenção
do projecto PLEGMA DAG. 100% local · sem rede · determinístico.

Uso:
  python orchestrator.py "auditar segurança do backend"
  python orchestrator.py "deploy para br e sin"
  python orchestrator.py "correr testes"
  python orchestrator.py --stats
  python orchestrator.py --pipeline pre_deploy "deploy completo"
"""

import sys
import json
import time
import argparse
from pathlib import Path

# Adicionar diretório pai ao path para imports relativos dos agentes
sys.path.insert(0, str(Path(__file__).parent))

from neural_memory  import NeuralMemory
from router         import Router, SIMPLE, MEDIUM, COMPLEX
from domain_loader  import load_for_task, list_domains

# Mapa de agentes instanciados a pedido (lazy)
_AGENT_REGISTRY = {}

def _get_agent(name: str):
    if name not in _AGENT_REGISTRY:
        if name == "security":
            from agents.security    import SecurityAgent;    _AGENT_REGISTRY[name] = SecurityAgent()
        elif name == "deploy":
            from agents.deploy      import DeployAgent;      _AGENT_REGISTRY[name] = DeployAgent()
        elif name == "test_runner":
            from agents.test_runner   import TestRunnerAgent;   _AGENT_REGISTRY[name] = TestRunnerAgent()
        elif name == "flutter_tester":
            from agents.flutter_tester import FlutterTesterAgent; _AGENT_REGISTRY[name] = FlutterTesterAgent()
        elif name == "validation":
            from agents.validation  import ValidationAgent;  _AGENT_REGISTRY[name] = ValidationAgent()
        elif name == "coder":
            from agents.coder       import CoderAgent;       _AGENT_REGISTRY[name] = CoderAgent()
        elif name == "coordinator":
            from agents.coordinator     import CoordinatorAgent;     _AGENT_REGISTRY[name] = CoordinatorAgent()
        elif name == "server_monitor":
            from agents.server_monitor  import ServerMonitorAgent;   _AGENT_REGISTRY[name] = ServerMonitorAgent()
        elif name == "social_manager":
            from agents.social_manager  import SocialManagerAgent;   _AGENT_REGISTRY[name] = SocialManagerAgent()
        elif name == "governance_watch":
            from agents.governance_watch import GovernanceWatchAgent; _AGENT_REGISTRY[name] = GovernanceWatchAgent()
        elif name == "analyst":
            from agents.analyst         import AnalystAgent;          _AGENT_REGISTRY[name] = AnalystAgent()
        elif name == "network_sync":
            from agents.network_sync    import NetworkSyncAgent;      _AGENT_REGISTRY[name] = NetworkSyncAgent()
        elif name == "consensus_engine":
            from agents.consensus_engine import ConsensusEngineAgent; _AGENT_REGISTRY[name] = ConsensusEngineAgent()
        elif name == "seed_guardian":
            from agents.seed_guardian    import SeedGuardianAgent;    _AGENT_REGISTRY[name] = SeedGuardianAgent()
    return _AGENT_REGISTRY.get(name)


# ─── Respostas locais (SIMPLE) ─────────────────────────────────────────────
_LOCAL_RESPONSES = {
    "status":   lambda: "Orchestrator activo · 6 agentes disponíveis",
    "versao":   lambda: "PLEGMA Orchestrator v1.0.0",
    "versão":   lambda: "PLEGMA Orchestrator v1.0.0",
    "version":  lambda: "PLEGMA Orchestrator v1.0.0",
    "ajuda":    lambda: __doc__,
    "help":     lambda: __doc__,
    "agentes":  lambda: "\n".join([
        "  · validation       (auditoria de código)",
        "  · security         (scan de vulnerabilidades)",
        "  · coder            (qualidade de código)",
        "  · deploy           (deploy para EUR/BR/MAL/SIN)",
        "  · test_runner      (testes automáticos)",
        "  · coordinator      (pipelines)",
        "  · server_monitor   (saúde dos 4 servidores)",
        "  · social_manager   (moderação da rede social)",
        "  · governance_watch (governança e propostas)",
        "  · analyst          (métricas e relatórios)",
        "  · network_sync     (replicação entre nós)",
        "  · consensus_engine (decisões tri-IA Claude+Gemini+Grok)",
    ]),
}

def _local_response(task: str) -> str | None:
    key = task.strip().lower().split()[0] if task.strip() else ""
    fn = _LOCAL_RESPONSES.get(key)
    return fn() if fn else None


# ─── Consensus Gate ────────────────────────────────────────────────────────
# Agentes de leitura/monitorização dispensam consenso (baixo risco)
_READ_ONLY_AGENTS = {"server_monitor", "analyst", "network_sync", "governance_watch", "seed_guardian"}

_LEIS_RESUMO = """
LEIS IMUTÁVEIS DO PROTOCOLO PLEGMA DAG:
LEI 1 — DETERMINISMO ABSOLUTO: todo código deve ser 100% determinístico. Proibido Math.random/UUID v4/timestamps como aleatoriedade.
LEI 2 — SEM REDUNDÂNCIA: nunca criar função/endpoint/tabela/ficheiro que já exista.
LEI 3 — PÓS-QUÂNTICO: stack obrigatório: BLAKE3 (hash), Crystals-Dilithium3 (assinatura), ZK-SNARK. Proibido ECDSA/RSA/Ed25519.
LEI 4 — SEM ATALHOS: código completo e correcto na primeira vez. Sem TODO/placeholder/debug em produção.
LEI 5 — ARQUITETURA IMUTÁVEL: supply PLG=21B fixo, supply PLG-G=10.5M fixo, hash_inscricao imutável após INSERT.
LEI 7 — SIGILO ABSOLUTO: proibido expor IPs, chaves, identidade do criador, nomes de ferramentas IA.
"""


def _consensus_local(task: str, agent_name: str, json_out: bool) -> bool:
    """Consenso local via agentes internos (validation + security + coder).
    Usado quando tri-IA não está disponível.
    Bloqueia apenas se validation ou security retornarem FAILURE com CRITICAL."""
    from agents.validation import ValidationAgent
    from agents.security   import SecurityAgent
    from agents.coder      import CoderAgent

    results = {}
    for cls, name in [(ValidationAgent, "validation"), (SecurityAgent, "security"), (CoderAgent, "coder")]:
        try:
            r = cls().run(task, {})
            results[name] = r
        except Exception:
            results[name] = None

    critical_block = False
    if not json_out:
        print(_color("\n⬡ CONSENSO LOCAL (validation + security + coder):", "36"))
    for name, r in results.items():
        if r is None:
            if not json_out: print(f"  ⚠ {name:<12} — indisponível")
            continue
        sym = "✓" if r.status != "FAILURE" else "✕"
        if not json_out: print(f"  {sym} {name:<12} — {r.summary[:80]}")
        # Bloqueia apenas se validation ou security tiverem FAILURE com CRITICAL
        if r.status == "FAILURE" and name in ("validation", "security"):
            data = r.data or {}
            if data.get("totais", {}).get("CRITICAL", 0) > 0 or \
               data.get("criticos", 0) > 0:
                critical_block = True

    approved = not critical_block
    sym = "✓" if approved else "✕"
    label = "APROVADO" if approved else "BLOQUEADO (CRITICAL encontrado)"
    if not json_out:
        print(_color(f"  ↳ {sym} {label}", "32" if approved else "31"))
    return approved


def _consensus_gate(task: str, agent_name: str, json_out: bool, local_only: bool = False) -> bool:
    """Executa consenso tri-IA antes de qualquer acção MEDIUM/COMPLEX.
    Fallback automático para consenso local se tri-IA indisponível.
    Retorna True se aprovado, False se bloqueado."""
    if local_only:
        return _consensus_local(task, agent_name, json_out)

    try:
        from agents.consensus_engine import ConsensusEngineAgent
        engine = ConsensusEngineAgent()
        prompt = (
            f"AVALIAÇÃO DE PROPOSTA — PLEGMA DAG\n\n"
            f"Tarefa solicitada: {task}\n"
            f"Agente executor: {agent_name}\n\n"
            f"{_LEIS_RESUMO}\n"
            f"CRITÉRIOS DE AVALIAÇÃO:\n"
            f"1. A tarefa viola alguma das Leis Imutáveis acima?\n"
            f"2. A execução pode causar instabilidade ou derrubar serviços em produção?\n"
            f"3. Para deploys: existe risco de quebrar serviços activos nos 4 servidores?\n\n"
            f"Se qualquer critério for violado, vota REJECT com justificação clara.\n"
            f"Aprova a execução desta proposta?"
        )
        result = engine.run(prompt)
        approved = result.data.get("approved", False)
        votes    = result.data.get("votes", [])

        # Se todos os votos falharam por falta de API key → fallback local
        api_failures = sum(1 for v in votes if "api key" in v.get("reason", "").lower()
                           or "não configurad" in v.get("reason", "").lower()
                           or "not configured" in v.get("reason", "").lower())
        if api_failures == len(votes) and len(votes) > 0:
            if not json_out:
                print(_color("\n⬡ Tri-IA indisponível (sem API keys) — activando consenso local", "33"))
            return _consensus_local(task, agent_name, json_out)

        if not json_out:
            sym = "✓" if approved else "✕"
            print(_color(f"\n⬡ CONSENSO TRI-IA: {sym} {'APROVADO' if approved else 'BLOQUEADO'}", "32" if approved else "31"))
            for vote in votes:
                ai    = vote.get("model", "?")
                v_sym = "✓" if vote.get("vote") == "APPROVE" else "✕"
                print(f"  {v_sym} {ai:<12} — {vote.get('reason', '')[:90]}")
            if not approved:
                print(_color("  ↳ Execução bloqueada — consenso insuficiente", "31"))

        return approved
    except Exception:
        # Erro técnico no motor de consenso → fallback local
        if not json_out:
            print(_color("\n⬡ Motor tri-IA indisponível — activando consenso local", "33"))
        return _consensus_local(task, agent_name, json_out)


# ─── CLI ──────────────────────────────────────────────────────────────────
def _color(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if sys.stdout.isatty() else text

def _print_result(result, json_out: bool = False):
    if json_out:
        from dataclasses import asdict
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
        return

    status_color = {"SUCCESS": "32", "FAILURE": "31", "PARTIAL": "33"}.get(result.status, "37")
    print(_color(f"\n⬡ [{result.agent.upper()}] {result.status}", status_color))
    print(f"  {result.summary}")
    if result.details:
        for d in result.details:
            print(f"  {d}")
    if result.duration_ms:
        print(_color(f"\n  {result.duration_ms}ms", "2"))


def main():
    parser = argparse.ArgumentParser(
        description="PLEGMA Orchestrator — agentes locais de manutenção"
    )
    parser.add_argument("task",           nargs="?", default="",  help="Tarefa em linguagem natural")
    parser.add_argument("--stats",        action="store_true",    help="Mostrar estatísticas da memória neural")
    parser.add_argument("--pipeline",     default=None,           help="Forçar pipeline: pre_deploy|full_audit|ci_check|full")
    parser.add_argument("--agent",        default=None,           help="Forçar agente específico")
    parser.add_argument("--json",         action="store_true",    help="Output JSON")
    parser.add_argument("--ficheiro",     default=None,           help="Ficheiro alvo para deploy/coder")
    parser.add_argument("--remote-path",  default=None,           help="Caminho remoto completo (deploy estático)")
    parser.add_argument("--static-only",  action="store_true",    help="Deploy estático (landing/APK) — só EUR, sem restart")
    parser.add_argument("--no-color",        action="store_true", help="Desactivar cores ANSI")
    parser.add_argument("--dominios",        action="store_true", help="Listar domínios disponíveis")
    parser.add_argument("--local-consensus", action="store_true", help="Usar consenso local (validation+security+coder) sem tri-IA externa")
    args = parser.parse_args()

    mem    = NeuralMemory()
    router = Router(mem)

    # ─── Domínios ────────────────────────────────────────────────────────
    if args.dominios:
        print("⬡ PLEGMA — Domínios de Contexto")
        for d in list_domains():
            estado = "✓" if d["exists"] else "✗"
            print(f"  {estado} {d['id']}  {d['file']}  ({d['keywords_count']} keywords)")
        mem.close()
        return

    # ─── Stats ───────────────────────────────────────────────────────────
    if args.stats:
        s = mem.stats()
        print(f"⬡ PLEGMA Orchestrator — Memória Neural")
        print(f"  Padrões: {s['padroes']}")
        print(f"  Execuções: {s['execucoes']}")
        print(f"  Sucessos: {s['sucessos']}")
        mem.close()
        return

    task = args.task
    if not task:
        parser.print_help()
        mem.close()
        return

    # ─── Resposta local (SIMPLE) ─────────────────────────────────────────
    local = _local_response(task)
    if local and not args.agent and not args.pipeline:
        print(local)
        mem.close()
        return

    # ─── Routing ─────────────────────────────────────────────────────────
    context = {}
    if args.ficheiro:    context["ficheiro"]     = args.ficheiro
    if args.pipeline:    context["pipeline"]     = args.pipeline
    if args.remote_path: context["remote_path"]  = args.remote_path
    if args.static_only: context["static_only"]  = True

    if args.agent:
        agent_name = args.agent
        complexity = MEDIUM
    else:
        decision   = router.dispatch(task)
        agent_name = decision["agent"]
        complexity = decision["complexity"]

        if not args.json:
            print(_color(
                f"\n⬡ [{complexity}] → {agent_name}  ({decision['reason']} · conf={decision['confidence']:.0%})",
                "36"
            ))

    # ─── Carregar contexto de domínio (lazy) ────────────────────────────
    domain_context = load_for_task(task)
    if domain_context and not args.json:
        from domain_loader import detect_domains
        detected = detect_domains(task)
        print(_color(f"  ↳ domínios: {', '.join(detected[:2])}", "2"))
    if domain_context:
        context["domain_context"] = domain_context

    # ─── Execução ────────────────────────────────────────────────────────
    if agent_name == "local" or complexity == SIMPLE:
        resp = _local_response(task) or f"Tarefa simples: {task}"
        print(resp)
        mem.close()
        return

    agent = _get_agent(agent_name)
    if not agent:
        print(_color(f"✕ Agente '{agent_name}' não disponível", "31"))
        mem.close()
        return

    # ─── Consenso (tri-IA ou local) ──────────────────────────────────────
    if agent_name not in _READ_ONLY_AGENTS:
        approved = _consensus_gate(task, agent_name, args.json,
                                   local_only=getattr(args, "local_consensus", False))
        if not approved:
            mem.close()
            return

    t0     = time.time()
    result = agent.run(task, context)
    elapsed = int((time.time() - t0) * 1000)

    # Persistir na memória
    mem.store(
        task_type=f"{complexity}:{agent_name}",
        context=task,
        agent_used=agent_name,
        outcome=result.status,
        duration_ms=elapsed
    )

    _print_result(result, json_out=args.json)
    mem.close()


if __name__ == "__main__":
    main()
