#!/usr/bin/env python3
"""
PLEGMA ORCHESTRATOR — Validation Agent
Verifica conformidade com as Leis do Protocolo:
  Lei 1 — criptografia pós-quântica (Dilithium3/BLAKE3)
  Lei 1 — determinismo (sem random(), timestamps como seed)
"""

import re
from pathlib import Path
from typing import List, Tuple
from . import BaseAgent, AgentResult

ROOT = Path(__file__).parent.parent.parent

# Padrões proibidos com descrição
_CRITICOS: List[Tuple[str, str]] = [
    (r"(?:import\s+(?:ecdsa|py_ecc|fastecdsa)|secp256k1\s*[.(]|ecdsa\.\w+\s*\()",
     "Curva elíptica pré-quântica"),
    (r"\b(?:Crypto\.PublicKey\.(?:RSA|DSA)|RSA\.generate|rsa\.generate)\b",
     "RSA/DSA proibido"),
    (r"(?<!\w)(?:random\.random|random\.randint|random\.choice|random\.shuffle)\s*\(",
     "random() inseguro sem seed BLAKE3"),
    (r"(?:Math\.random\(\)|crypto\.randomBytes\s*\()(?!.*BLAKE3)",
     "Math.random() / randomBytes sem âncora determinística"),
    (r'(?:uuid\.uuid4\(\)|uuidv4\s*\(\))',
     "UUID v4 aleatório — usar BLAKE3(inputs)"),
]

_WARNINGS: List[Tuple[str, str]] = [
    (r"\btime\.time\(\)\s*as\s+seed\b|\bseed\s*=\s*time\.time\(\)",
     "Timestamp como seed — não determinístico"),
    (r"(?:import\s+hashlib.*\bmd5\b|\bhashlib\.md5\b)",
     "MD5 — usar BLAKE3"),
    (r"(?:import\s+hashlib.*\bsha1\b|\bhashlib\.sha1\b)",
     "SHA-1 — usar BLAKE3 ou SHA3-256"),
]

# ── Regras de integridade do fluxo DAG ──────────────────────────────────────
# Detectam falhas no pipeline: Tx → Hash → ZK → Parents → Aerarium → Recompensa
_DAG_FLOW: List[Tuple[str, str]] = [
    # INSERT em transactions sem aerarium_amount — Etapa 5 do fluxo ausente
    (r'INSERT\s+(?:OR\s+\w+\s+)?INTO\s+transactions\b(?![\s\S]{0,400}aerarium_amount)',
     "DAG-FLOW: INSERT transactions sem aerarium_amount — Etapa 5 (Aerarium) não gravada"),
    # INSERT em transactions sem zk_proof_hash — Etapa 3 incompleta
    (r'INSERT\s+(?:OR\s+\w+\s+)?INTO\s+transactions\b(?![\s\S]{0,400}zk_proof_hash)',
     "DAG-FLOW: INSERT transactions sem zk_proof_hash — Etapa 3 (ZK Proof hash) não gravada"),
    # parents=[] hardcoded em contexto não-genesis — quebra topologia DAG (Etapa 4)
    (r'"parents"\s*:\s*\[\s*\]',
     "DAG-FLOW: parents=[] hardcoded — Etapa 4 (topologia) quebrada em tx não-genesis"),
    # mine endpoint sem inserir na transactions — Etapa 1 incompleta
    (r'@app\.post\s*\(["\']\/api\/mine["\']',
     "DAG-FLOW: /api/mine — confirmar que grava na transactions com todos os campos"),
]


def _scan_file(path: Path, patterns: List[Tuple[str, str]]) -> List[dict]:
    findings = []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return findings
    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "//", "/*", "*", "- ", "– ")):
            continue
        for pattern, desc in patterns:
            if re.search(pattern, line, re.IGNORECASE):
                findings.append({
                    "file": str(path.relative_to(ROOT)),
                    "line": lineno,
                    "desc": desc,
                    "snippet": stripped[:100]
                })
                break
    return findings


class ValidationAgent(BaseAgent):
    name = "validation"

    def _execute(self, task: str, context: dict) -> AgentResult:
        task_lower = task.lower()

        # Determinar escopo
        if "flutter" in task_lower or "dart" in task_lower:
            dirs  = [ROOT / "plegma_app" / "lib"]
            exts  = ["*.dart"]
        elif "frontend" in task_lower or "js" in task_lower:
            dirs  = [ROOT / "PLEGMA_LANDING"]
            exts  = ["*.js", "*.html"]
        else:
            dirs  = [ROOT / "PLEGMA_CORE"]
            exts  = ["*.py"]

        criticos   = []
        avisos     = []
        dag_issues = []
        skip       = {"venv", "__pycache__", ".git", "build", "node_modules"}

        for base_dir in dirs:
            if not base_dir.exists():
                continue
            for ext in exts:
                for f in base_dir.rglob(ext):
                    if any(s in f.parts for s in skip):
                        continue
                    if f.name.endswith(".min.js") or f.name.startswith("test_"):
                        continue
                    criticos.extend(_scan_file(f, _CRITICOS))
                    avisos.extend(_scan_file(f, _WARNINGS))
                    # DAG flow scan apenas em ficheiros core Python
                    if ext == "*.py":
                        dag_issues.extend(_scan_file(f, _DAG_FLOW))

        status = "SUCCESS" if not criticos else "FAILURE"
        details = []
        for c in criticos[:10]:
            details.append(f"  ✕ CRÍTICO [{c['desc']}] {c['file']}:{c['line']}")
        for w in avisos[:5]:
            details.append(f"  ⚠ AVISO [{w['desc']}] {w['file']}:{w['line']}")
        for d in dag_issues[:5]:
            details.append(f"  ⬡ DAG-FLOW [{d['desc']}] {d['file']}:{d['line']}")

        if not criticos and not avisos and not dag_issues:
            details.append("  ✓ Nenhuma violação criptográfica detectada")

        return AgentResult(
            agent=self.name, status=status,
            summary=f"Validação: {len(criticos)} críticos · {len(avisos)} avisos · {len(dag_issues)} fluxo-DAG",
            details=details,
            data={"criticos": len(criticos), "avisos": len(avisos), "dag_flow": len(dag_issues)}
        )
