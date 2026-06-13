#!/usr/bin/env python3
"""
PLEGMA ORCHESTRATOR — Test Runner Agent
Executa test_bateria_completa.py e interpreta os resultados.
"""

import sys
import re
import subprocess
from pathlib import Path
from . import BaseAgent, AgentResult

TEST_FILE = Path(__file__).parent.parent.parent / "PLEGMA_CORE" / "test_bateria_completa.py"


class TestRunnerAgent(BaseAgent):
    name = "test_runner"

    def _execute(self, task: str, context: dict) -> AgentResult:
        if not TEST_FILE.exists():
            return AgentResult(
                agent=self.name, status="FAILURE",
                summary="test_bateria_completa.py não encontrado",
                details=[str(TEST_FILE)]
            )

        try:
            proc = subprocess.run(
                [sys.executable, str(TEST_FILE)],
                capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                timeout=180,
                cwd=str(TEST_FILE.parent)
            )
            output = (proc.stdout + proc.stderr)

            # Interpretar resultados
            passed  = len(re.findall(r"✓|PASS|OK", output))
            failed  = len(re.findall(r"✕|FAIL|ERROR|ERRO", output))
            lines   = [l for l in output.splitlines() if any(
                        m in l for m in ("✓", "✕", "PASS", "FAIL", "ERROR", "ERRO",
                                         "TOTAL", "Total", "resultado"))]

            status = "SUCCESS" if failed == 0 and proc.returncode == 0 else \
                     "PARTIAL" if passed > 0 else "FAILURE"

            return AgentResult(
                agent=self.name, status=status,
                summary=f"Bateria: {passed} pass · {failed} fail (rc={proc.returncode})",
                details=lines[:30],
                data={"passed": passed, "failed": failed, "returncode": proc.returncode}
            )

        except subprocess.TimeoutExpired:
            return AgentResult(
                agent=self.name, status="FAILURE",
                summary="Timeout — bateria excedeu 180s"
            )
        except Exception as e:
            return AgentResult(
                agent=self.name, status="FAILURE",
                summary=f"Erro: {e}"
            )
