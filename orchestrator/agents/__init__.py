#!/usr/bin/env python3
"""
PLEGMA ORCHESTRATOR — Agentes
Base class e exports.
"""

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class AgentResult:
    agent:      str
    status:     str          # SUCCESS · FAILURE · PARTIAL
    summary:    str
    details:    List[str] = field(default_factory=list)
    data:       Dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0


class BaseAgent:
    name: str = "base"

    def run(self, task: str, context: dict = None) -> AgentResult:
        t0 = time.time()
        result = self._execute(task, context or {})
        result.duration_ms = int((time.time() - t0) * 1000)
        return result

    def _execute(self, task: str, context: dict) -> AgentResult:
        raise NotImplementedError
