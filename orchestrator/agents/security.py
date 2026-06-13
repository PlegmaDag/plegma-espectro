#!/usr/bin/env python3
"""
PLEGMA ORCHESTRATOR — Security Agent
Delega ao sentinela_agent.py para análise estática de vulnerabilidades.
"""

import sys
import subprocess
from pathlib import Path
from . import BaseAgent, AgentResult

SENTINELA = Path(__file__).parent.parent.parent / "SECURITY_AUDIT" / "sentinela_agent.py"


class SecurityAgent(BaseAgent):
    name = "security"

    def _execute(self, task: str, context: dict) -> AgentResult:
        task_lower = task.lower()

        # Determinar escopo do scan
        flags = []
        if any(w in task_lower for w in ("backend", "python", "py")):
            flags = ["--backend"]
        elif any(w in task_lower for w in ("frontend", "html", "js")):
            flags = ["--frontend"]
        elif any(w in task_lower for w in ("flutter", "dart", "app")):
            flags = ["--flutter"]

        if not SENTINELA.exists():
            return AgentResult(
                agent=self.name, status="FAILURE",
                summary="sentinela_agent.py não encontrado",
                details=[str(SENTINELA)]
            )

        try:
            cmd = [sys.executable, str(SENTINELA), "--json"] + flags
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=120)

            import json, re
            out = proc.stdout or ""
            match = re.search(r"\{.*\}", out, re.DOTALL)
            if not match:
                return AgentResult(
                    agent=self.name, status="FAILURE",
                    summary="Sentinela não retornou JSON válido",
                    details=[out[:300]]
                )

            data = json.loads(match.group())
            findings = data.get("findings", [])
            by_sev = {}
            for f in findings:
                by_sev[f["severity"]] = by_sev.get(f["severity"], 0) + 1

            crits = by_sev.get("CRITICAL", 0)
            highs = by_sev.get("HIGH", 0)
            status = "SUCCESS" if crits == 0 else "FAILURE"

            details = [
                f"CRITICAL: {crits}",
                f"HIGH:     {highs}",
                f"MEDIUM:   {by_sev.get('MEDIUM', 0)}",
                f"LOW:      {by_sev.get('LOW', 0)}",
                f"Total:    {len(findings)}",
            ]

            # Mostrar os primeiros CRITICALs/HIGHs
            urgent = [f for f in findings if f["severity"] in ("CRITICAL", "HIGH")][:5]
            for u in urgent:
                fn = u["file"].split("\\")[-1] if "\\" in u["file"] else u["file"].split("/")[-1]
                details.append(f"  ⚠ {u['severity']} [{u['category']}] {fn}:{u['line']}")

            return AgentResult(
                agent=self.name, status=status,
                summary=f"Scan concluído — CRITICAL:{crits} HIGH:{highs}",
                details=details,
                data={"totais": by_sev, "total": len(findings)}
            )

        except subprocess.TimeoutExpired:
            return AgentResult(
                agent=self.name, status="FAILURE",
                summary="Timeout — scan excedeu 120s"
            )
        except Exception as e:
            return AgentResult(
                agent=self.name, status="FAILURE",
                summary=f"Erro: {e}"
            )
