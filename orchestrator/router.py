#!/usr/bin/env python3
"""
PLEGMA ORCHESTRATOR — Router
Analisa complexidade da tarefa e despacha para o agente correto.
Simples → local (<1ms) · Médio → 1 agente · Complexo → swarm
"""

import re
import time
from dataclasses import dataclass
from typing import Optional
from neural_memory import NeuralMemory

SIMPLE  = "SIMPLE"
MEDIUM  = "MEDIUM"
COMPLEX = "COMPLEX"

# Palavras-chave por nível de complexidade
_KW_SIMPLE  = {
    "status", "versao", "versão", "version", "ping", "ajuda", "help",
    "listar", "list", "stats", "info", "mostrar", "show"
}
_KW_COMPLEX = {
    "tudo", "all", "completo", "full", "todos", "swarm", "coordenar",
    "refactor", "refatorar", "migrar", "migrate", "completa", "global",
    "todos os servidores", "all servers"
}

# Mapa de palavras-chave → agente
_KW_AGENT = {
    "security":    {"segurança", "security", "audit", "auditoria", "vulnerabilidade",
                    "xss", "sql", "injection", "critico", "crítico", "scan"},
    "deploy":      {"deploy", "deployer", "servidor", "server", "ssh", "restart",
                    "reiniciar", "publicar", "publish", "eur", "usa", "mum", "sin"},
    "flutter_tester": {"flutter", "emulador", "emulator", "apk", "android", "iphone",
                       "ios", "mobile", "app", "instalar", "smoke"},
    "test_runner": {"test", "teste", "bateria", "testar", "run", "executar", "testes"},
    "validation":  {"validar", "validate", "dilithium", "blake3", "crypto", "hash",
                    "criptografia", "pós-quântico", "determinístico"},
    "coder":       {"código", "code", "fix", "corrigir", "bug", "função", "function",
                    "classe", "class", "módulo", "module", "editar", "edit", "criar"},
}


@dataclass
class RouteDecision:
    complexity: str
    agent:      str
    reason:     str
    confidence: float  # 0.0–1.0


class Router:
    def __init__(self, memory: NeuralMemory):
        self.memory = memory

    def analyze(self, task: str) -> RouteDecision:
        tokens = set(re.findall(r'\w+', task.lower()))
        task_key = task[:48].lower().strip()

        # 1. Consultar memória — se padrão conhecido com ≥3 execuções, confiar
        recalled = self.memory.recall(f"route:{task_key}")
        if recalled and recalled[0].count >= 3:
            p = recalled[0]
            parts = p.task_type.split(":", 1)
            complexity = parts[0] if parts[0] in (SIMPLE, MEDIUM, COMPLEX) else MEDIUM
            return RouteDecision(
                complexity=complexity,
                agent=p.agent_used,
                reason=f"Padrão memorizado ({p.count}x · último: {p.outcome})",
                confidence=min(0.95, 0.50 + p.count * 0.05)
            )

        # 2. Heurística: complexidade por palavras-chave
        if tokens & _KW_SIMPLE:
            return RouteDecision(SIMPLE, "local", "Tarefa de consulta simples", 0.85)
        if tokens & _KW_COMPLEX:
            return RouteDecision(COMPLEX, "coordinator",
                                 "Tarefa multi-agente — coordenador necessário", 0.80)

        # 3. Detetar agente por domínio
        agent = self._detect_agent(tokens)
        return RouteDecision(MEDIUM, agent,
                             f"Domínio detectado → {agent}", 0.80)

    def _detect_agent(self, tokens: set) -> str:
        scores = {agent: len(tokens & kws) for agent, kws in _KW_AGENT.items()}
        best = max(scores, key=lambda a: scores[a])
        return best if scores[best] > 0 else "coder"

    def dispatch(self, task: str) -> dict:
        decision = self.analyze(task)
        t0 = time.time()
        result = {
            "task":       task,
            "complexity": decision.complexity,
            "agent":      decision.agent,
            "reason":     decision.reason,
            "confidence": decision.confidence,
        }
        elapsed = int((time.time() - t0) * 1000)
        self.memory.store(
            task_type=f"{decision.complexity}:{decision.agent}",
            context=task,
            agent_used=decision.agent,
            outcome="DISPATCHED",
            duration_ms=elapsed
        )
        return result
