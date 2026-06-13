#!/usr/bin/env python3
"""
PLEGMA ORCHESTRATOR — Coder Agent
Análise estática de qualidade de código seguindo as Leis do Protocolo.
Detecta: código morto, SELECT *, print() em produção, endpoints sem validação.
"""

import re
from pathlib import Path
from typing import List
from . import BaseAgent, AgentResult

ROOT = Path(__file__).parent.parent.parent

_RULES = [
    # Lei 6 — qualidade
    ("DEAD_CODE",
     r"^\s*#.*\bTODO\b.*$|^\s*#.*\bFIXME\b",
     "TODO/FIXME pendente"),
    ("DEBUG_PRINT",
     r"^\s{0,8}print\s*\(",
     "print() em produção — usar logging"),
    ("SELECT_STAR",
     r"\bSELECT\s+\*\s+FROM\b",
     "SELECT * proibido — especificar colunas"),
    ("ENDPOINT_NO_VALIDATION",
     r'@app\.(?:post|put|delete|patch)\s*\(["\'][^"\']*(?:admin|ativar|reset|config|delete)[^"\']*["\']',
     "Endpoint sensível — confirmar validação de credenciais",
     r'admin_key|_check_auth_lockout|admin_password_hash|_check_admin'),
    ("HARDCODED_CREDENTIAL",
     r'(?:password|secret|api_key|admin_key)\s*=\s*["\'][^"\']{8,}["\']',
     "Credencial hardcoded"),
    # ── Integridade do fluxo DAG (Etapas 1-8) ────────────────────────────────
    ("DAG_NO_AERARIUM",
     r'INSERT\s+(?:OR\s+\w+\s+)?INTO\s+transactions\b(?![\s\S]{0,600}aerarium_amount)',
     "DAG Etapa 5: INSERT transactions sem aerarium_amount"),
    ("DAG_NO_ZK_HASH",
     r'INSERT\s+(?:OR\s+\w+\s+)?INTO\s+transactions\b(?![\s\S]{0,600}zk_proof_hash)',
     "DAG Etapa 3: INSERT transactions sem zk_proof_hash"),
    ("DAG_HARDCODED_PARENTS_EMPTY",
     r'["\']parents["\']\s*:\s*\[\s*\]',
     "DAG Etapa 4: parents=[] hardcoded quebra topologia"),
    ("DAG_MINE_NO_TX_INSERT",
     r'def\s+_write_vesting\b(?![\s\S]{0,800}INSERT\s+(?:OR\s+\w+\s+)?INTO\s+transactions)',
     "DAG Etapa 1: /api/mine não grava na transactions"),
]


def _scan(path: Path) -> List[dict]:
    findings = []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return findings
    lines = text.splitlines()

    # Regras DAG_* usam re.DOTALL sobre o texto completo (INSERT spans múltiplas linhas)
    dag_rules = [r for r in _RULES if r[0].startswith("DAG_")]
    for rule in dag_rules:
        name, pattern, desc = rule[:3]
        for m in re.finditer(pattern, text, re.IGNORECASE | re.DOTALL):
            lineno = text[:m.start()].count("\n") + 1
            snippet = lines[lineno - 1].strip()[:100] if lineno <= len(lines) else ""
            findings.append({"rule": name, "desc": desc,
                             "file": str(path.relative_to(ROOT)),
                             "line": lineno, "snippet": snippet})

    # Restantes regras: scan linha a linha com lookahead opcional
    line_rules = [r for r in _RULES if not r[0].startswith("DAG_")]
    for lineno, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        for rule in line_rules:
            name, pattern, desc = rule[:3]
            lookahead = rule[3] if len(rule) > 3 else None
            if re.search(pattern, line, re.IGNORECASE):
                if lookahead:
                    window = lines[lineno:lineno + 10]
                    if any(re.search(lookahead, l, re.IGNORECASE) for l in window):
                        break
                findings.append({
                    "rule":    name,
                    "desc":    desc,
                    "file":    str(path.relative_to(ROOT)),
                    "line":    lineno,
                    "snippet": stripped[:100],
                })
                break
    return findings


class CoderAgent(BaseAgent):
    name = "coder"

    def _execute(self, task: str, context: dict) -> AgentResult:
        task_lower = task.lower()
        skip = {"venv", "__pycache__", ".git", "build"}

        # Escopo: ficheiro específico ou todos os .py
        target_file = context.get("ficheiro")
        if target_file:
            files = [Path(target_file)]
        else:
            base = ROOT / "PLEGMA_CORE"
            _CLI_TOOLS = {"admin_setup.py", "minerador_gui.py",
                          "wallet_dashboard.py", "wallet_app.py",
                          "app_navegacao.py", "app_boot.py", "sentinela.py"}
            files = [f for f in base.rglob("*.py")
                     if not any(s in f.parts for s in skip)
                     and not f.name.startswith("test_")
                     and not f.name.startswith("teste_")
                     and f.name not in _CLI_TOOLS]

        all_findings = []
        for f in files:
            all_findings.extend(_scan(f))

        # Agrupar por regra
        by_rule: dict = {}
        for fn in all_findings:
            by_rule.setdefault(fn["rule"], []).append(fn)

        details = []
        for rule, items in sorted(by_rule.items(), key=lambda x: -len(x[1])):
            details.append(f"  [{rule}] {len(items)}x")
            for i in items[:2]:
                details.append(f"    {i['file']}:{i['line']}  {i['snippet'][:80]}")

        status = "SUCCESS" if not any(
            r in by_rule for r in ("HARDCODED_CREDENTIAL", "SELECT_STAR")
        ) else "FAILURE"

        return AgentResult(
            agent=self.name, status=status,
            summary=f"Análise: {len(all_findings)} observações em {len(files)} ficheiros",
            details=details,
            data={"total": len(all_findings), "por_regra": {k: len(v) for k, v in by_rule.items()}}
        )
