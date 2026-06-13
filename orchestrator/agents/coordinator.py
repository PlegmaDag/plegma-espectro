#!/usr/bin/env python3
"""
PLEGMA ORCHESTRATOR — Coordinator Agent
Orquestra múltiplos agentes em sequência para tarefas complexas.
Swarm local: validation → security → coder → test_runner → deploy
"""

from typing import List, Dict
from . import BaseAgent, AgentResult
from .validation      import ValidationAgent
from .security        import SecurityAgent
from .coder           import CoderAgent
from .test_runner     import TestRunnerAgent
from .flutter_tester  import FlutterTesterAgent
from .deploy          import DeployAgent
from .token_saver     import TokenSaverAgent
from .dag_auditor     import DagAuditorAgent

# Pipelines pré-definidos
PIPELINES: Dict[str, List[str]] = {
    "pre_deploy":     ["validation", "security", "test_runner", "flutter_tester", "deploy", "dag_auditor"],
    "backend_deploy": ["validation", "security", "test_runner", "deploy", "dag_auditor"],
    "full_audit":     ["validation", "security", "coder", "dag_auditor"],
    "dag_audit":      ["dag_auditor"],
    "ci_check":       ["validation", "test_runner", "flutter_tester"],
    "deploy_only":    ["deploy"],
    "full":           ["validation", "security", "coder", "test_runner", "flutter_tester", "deploy", "dag_auditor"],
    "token_save":     ["token_saver"],
}

_AGENT_MAP = {
    "validation":     ValidationAgent,
    "security":       SecurityAgent,
    "coder":          CoderAgent,
    "test_runner":    TestRunnerAgent,
    "flutter_tester": FlutterTesterAgent,
    "deploy":         DeployAgent,
    "token_saver":    TokenSaverAgent,
    "dag_auditor":    DagAuditorAgent,
}


class CoordinatorAgent(BaseAgent):
    name = "coordinator"

    def _execute(self, task: str, context: dict) -> AgentResult:
        task_lower = task.lower()

        # Selecionar pipeline
        pipeline_name = context.get("pipeline", self._detect_pipeline(task_lower))
        pipeline = PIPELINES.get(pipeline_name, PIPELINES["full_audit"])

        results: List[AgentResult] = []
        details = [f"Pipeline: {pipeline_name} → {' → '.join(pipeline)}"]
        aborted = False

        for agent_name in pipeline:
            cls = _AGENT_MAP.get(agent_name)
            if not cls:
                details.append(f"  ⚠ Agente '{agent_name}' não encontrado — skipped")
                continue

            agent = cls()
            details.append(f"\n[{agent_name.upper()}]")
            result = agent.run(task, context)
            results.append(result)

            details.append(f"  Status:  {result.status}")
            details.append(f"  Resumo: {result.summary}")
            details.extend([f"    {d}" for d in result.details[:5]])

            # Parar se FAILURE em agentes críticos (sem deploy com falhas)
            if result.status == "FAILURE" and agent_name in ("validation", "security", "flutter_tester"):
                details.append(f"  ⛔ Pipeline interrompido — {agent_name} falhou")
                aborted = True
                break

        # Resultado global
        failures = sum(1 for r in results if r.status == "FAILURE")
        status = "FAILURE"  if aborted or failures == len(results) else \
                 "PARTIAL"  if failures > 0 else \
                 "SUCCESS"

        return AgentResult(
            agent=self.name, status=status,
            summary=f"Pipeline '{pipeline_name}': {len(results)} agentes · {failures} falhas",
            details=details,
            data={
                "pipeline":    pipeline_name,
                "agentes":     pipeline,
                "executados":  len(results),
                "falhas":      failures,
                "abortado":    aborted,
            }
        )

    def _detect_pipeline(self, task: str) -> str:
        if any(w in task for w in ("deploy", "publicar", "servidor")):
            return "pre_deploy"
        if any(w in task for w in ("auditoria", "audit", "full audit", "completo")):
            return "full_audit"
        if any(w in task for w in ("ci", "check", "validar tudo")):
            return "ci_check"
        if any(w in task for w in ("token", "compact", "compactar", "checkpoint", "memoria")):
            return "token_save"
        return "full_audit"
