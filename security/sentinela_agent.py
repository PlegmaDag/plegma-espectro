#!/usr/bin/env python3
"""
PLEGMA DAG — Agente Sentinela de Segurança
Análise estática de vulnerabilidades: backend Python · frontend HTML/JS · app Dart
100% local · sem rede · sem dependências externas obrigatórias

Uso:
  python sentinela_agent.py              — varredura completa
  python sentinela_agent.py --backend    — só Python
  python sentinela_agent.py --frontend   — só HTML/JS
  python sentinela_agent.py --flutter    — só Dart
  python sentinela_agent.py --no-color   — sem cores ANSI
  python sentinela_agent.py --json       — output JSON (para CI/scripts)
"""

import os
import re
import sys
import json
import sqlite3
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from typing import List, Tuple

# ─── Hash determinístico (BLAKE3 se disponível, SHA3-256 como fallback) ───────
try:
    import blake3 as _b3
    def _hash(data: str) -> str:
        return _b3.blake3(data.encode()).hexdigest()[:16]
except ImportError:
    def _hash(data: str) -> str:
        return hashlib.sha3_256(data.encode()).hexdigest()[:16]

# ─── Paths ────────────────────────────────────────────────────────────────────
ROOT         = Path(__file__).parent.parent
BACKEND_DIR  = ROOT / "PLEGMA_CORE"
FRONTEND_DIR = ROOT / "PLEGMA_LANDING"
FLUTTER_DIR  = ROOT / "plegma_app" / "lib"
DB_PATH      = Path(__file__).parent / "sentinela_memory.db"

SKIP_DIRS = {"venv", "__pycache__", ".git", "build", "$backup", "node_modules"}
# Ficheiros compilados/minificados excluídos do scan (falsos positivos garantidos)
SKIP_FILES = {"canvaskit.js", "main.dart.js", "flutter_bootstrap.js", "flutter_service_worker.js"}

SEV_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}

# ─── Finding ──────────────────────────────────────────────────────────────────
@dataclass
class Finding:
    severity:    str
    category:    str
    file:        str
    line:        int
    snippet:     str
    description: str
    fix:         str

# ─────────────────────────────────────────────────────────────────────────────
#  REGRAS PYTHON BACKEND
# ─────────────────────────────────────────────────────────────────────────────
#  Tupla: (severity, category, regex_pattern, description, fix)
#  O regex é aplicado linha a linha. Linhas de comentário puro são saltadas.
# ─────────────────────────────────────────────────────────────────────────────
PY_RULES: List[Tuple] = [

    # ── Lei 1 — Criptografia proibida ─────────────────────────────────────────
    ("CRITICAL", "CRYPTO_FORBIDDEN",
     r"(?:import\s+(?:ecdsa|py_ecc|fastecdsa|ellipticcurve)|from\s+(?:ecdsa|py_ecc|fastecdsa|ellipticcurve)\s+import|secp256k1\s*[.(]|ecdsa\.\w+\s*\()",
     "Algoritmo de curva elíptica pré-quântico detectado — proibido pela Lei 1",
     "Substituir por Crystals-Dilithium3 (NIST FIPS 204) ou BLAKE3"),

    ("CRITICAL", "RSA_DSA_FORBIDDEN",
     r"\b(Crypto\.PublicKey\.(RSA|DSA)|from\s+Crypto\..*import.*RSA|rsa\.generate|RSA\.generate)\b",
     "RSA/DSA detectado — algoritmos pré-quânticos proibidos pela Lei 1",
     "Substituir por Dilithium3"),

    ("CRITICAL", "RANDOM_INSECURE",
     r"(?<!\w)(random\.random\(\)|random\.randint\(|random\.choice\(|random\.shuffle\(|random\.sample\()",
     "random() sem seed BLAKE3 — não-determinístico, viola Lei 1",
     "Derivar de BLAKE3(input + counter + state) em vez de random()"),

    ("CRITICAL", "UUID_RANDOM",
     r"\buuid\.uuid4\(\)",
     "UUID v4 aleatório proibido — viola Lei 1",
     "Substituir por BLAKE3(inputs determinísticos)[:32]"),

    ("CRITICAL", "SECRETS_MODULE",
     r"^(import secrets|from secrets import)",
     "import secrets — deve ser substituído por BLAKE3 determinístico",
     "Usar blake3.blake3(seed + salt + counter).hexdigest()"),

    # ── SQL Injection ─────────────────────────────────────────────────────────
    ("CRITICAL", "SQL_INJECTION_FSTRING",
     r'(?:execute|executemany)\s*\(\s*f["\'].*(?:SELECT|INSERT|UPDATE|DELETE|WHERE)',
     "SQL com f-string — vetor de injeção SQL direto",
     "Usar parâmetros posicionais: cursor.execute('SELECT ... WHERE x=?', (valor,))"),

    ("CRITICAL", "SQL_INJECTION_FORMAT",
     r'(?:execute|executemany)\s*\(\s*["\'].*%[sd].*["\'].*%',
     "SQL com formatação % — vetor de injeção SQL",
     "Usar parâmetros posicionais: cursor.execute('... WHERE x=?', (valor,))"),

    ("CRITICAL", "SQL_INJECTION_CONCAT",
     r'(?:execute|executemany)\s*\(\s*["\'].*["\'\s]\+\s*\w',
     "SQL com concatenação de string — vetor de injeção SQL",
     "Usar parâmetros posicionais"),

    # ── Credenciais hardcoded ─────────────────────────────────────────────────
    ("HIGH", "HARDCODED_SECRET",
     r'(?:password|passwd|secret|api_key|admin_key|master_key|private_key|token)\s*=\s*["\'][^"\']{8,}["\']',
     "Credencial hardcoded no código fonte",
     "Usar variável de ambiente (os.environ.get) ou ficheiro de config excluído do repositório"),

    ("HIGH", "HARDCODED_IP_BACKEND",
     r'["\']https?://(?!(?:127\.0\.0\.1|0\.0\.0\.0|213\.199\.42\.88|187\.127\.19\.209|187\.127\.108\.201|82\.197\.70\.189)(?::\d+)?["\'])\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(?::\d+)?["\']',
     "IP hardcoded no código backend",
     "Usar constante configurável via variável de ambiente"),

    # ── CORS e Headers ────────────────────────────────────────────────────────
    ("HIGH", "CORS_WILDCARD",
     r'["\']Access-Control-Allow-Origin["\'].*["\']\*["\']|allow_origins\s*=\s*\[.*["\']\*["\']',
     "CORS wildcard (*) — todos os origins autorizados, incluindo maliciosos",
     "Restringir a origins conhecidos: ['https://plegmadag.com']"),

    # ── Qualidade / Lei 6 ─────────────────────────────────────────────────────
    ("HIGH", "SELECT_STAR",
     r"\bSELECT\s+\*\s+FROM\b",
     "SELECT * proibido pela Lei 6 em queries — retorna colunas desnecessárias",
     "Especificar colunas explicitamente: SELECT col1, col2 FROM ..."),

    ("MEDIUM", "DEBUG_PRINT",
     r"^\s{0,8}print\s*\(",
     "print() em código de produção — viola Lei 6",
     "Substituir por logging.getLogger(__name__).debug/info"),

    ("MEDIUM", "MISSING_AUTH_DECORATOR",
     r'@app\.(?:post|put|delete|patch)\s*\(["\'][^"\']*(?:admin|ativar|reset|config|delete)[^"\']*["\']',
     "Endpoint sensível — verificar se tem validação de admin_key/sessão",
     "Confirmar que o handler valida credenciais antes de executar",
     r'admin_key|_check_auth_lockout|admin_password_hash|_check_admin'),

    ("MEDIUM", "EVAL_PYTHON",
     r"\beval\s*\(",
     "eval() Python — execução de código arbitrário",
     "Remover eval(). Usar ast.literal_eval() se necessário para dados"),

    ("MEDIUM", "SHELL_INJECTION",
     r"(?:os\.system|subprocess\.call|subprocess\.run)\s*\([^)]*\+[^)]*\)",
     "Possível injeção de shell via concatenação em subprocess/os.system",
     "Usar lista de argumentos em subprocess.run(['cmd', arg]) sem shell=True"),

    ("LOW", "TODO_FIXME",
     r"#\s*(?:TODO|FIXME|HACK|XXX)\b",
     "TODO/FIXME pendente — rever antes de produção",
     "Resolver ou documentar decisão consciente"),

    ("LOW", "PASS_IN_EXCEPT",
     r"except\s+\w*.*:\s*\n\s*pass",
     "Exceção silenciada com pass — pode ocultar falhas de segurança",
     "Registar pelo menos: logging.error(e) ou re-raise"),
]

# ─────────────────────────────────────────────────────────────────────────────
#  REGRAS HTML / JAVASCRIPT FRONTEND
# ─────────────────────────────────────────────────────────────────────────────
JS_RULES: List[Tuple] = [

    ("CRITICAL", "XSS_EVAL",
     r"\beval\s*\(",
     "eval() detectado — execução de JS arbitrário, XSS direto",
     "Remover eval(). Usar JSON.parse() ou lógica explícita"),

    ("HIGH", "XSS_INNERHTML_UNSANITIZED",
     r"\.innerHTML\s*[+]?=(?!\s*$)(?!\s*`\s*$)(?!.*DOMPurify)(?!.*_esc\()(?!.*\besc\()(?!.*escapeHtml\()(?!.*textContent)(?!.*badgeCategoria\()(?!.*\.map\s*\()(?!.*=>\s*`<(?:tr|div|span|small|strong|br|h[1-6]|p|svg|button|table|th|td|li|ul|ol|img)\b)(?!\s*['\"`]<(?:tr|div|span|small|strong|br|h[1-6]|p|svg|button|table|th|td|li|ul|ol|img|section|header|footer|form|input|label)\b)(?!\s*['\"]['\"])(?!\s*null\b)(?!\s*`\s*[;)]?)(?!\s*''\s*[;,)]?)(?!\s*\"\"\s*[;,)]?)(?!\s*orig\b)(?!\s*isBuy\b)(?!\s*desc\b)(?!\s*\w+\.innerHTML\b)(?!\s*\w[\w.]*\s*(?:>=?|<=?|!==?|===?)\s*\w[\w.]*\s*;?\s*$)(?!\s*\w[\w.]*\s*;?\s*$)",
     "innerHTML sem sanitização — verificar se dados externos estão escapados com _esc()",
     "Usar _esc() em todos os valores de string vindos de API/utilizador; textContent para texto simples"),

    ("CRITICAL", "XSS_DOCUMENT_WRITE",
     r"\bdocument\.write\s*\(",
     "document.write() — vetor XSS clássico, bloqueia parser",
     "Substituir por createElement + appendChild"),

    ("HIGH", "SENSITIVE_IN_JS",
     r'(?:admin_key|master_key|private_key|secret|api_key)\s*[=:]\s*["\'][^"\']{6,}["\']',
     "Credencial hardcoded em JavaScript — visível a qualquer utilizador",
     "Mover para backend. Nunca expor credenciais em JS do lado do cliente"),

    ("CRITICAL", "HASH_HARDCODED_AUTH",
     r'(?:_ADMIN_HASH|_MASTER_HASH|_AUTH_HASH)\s*=\s*["\'][a-f0-9]{32,}["\']',
     "Hash de password hardcoded no client-side — brute-force offline possível",
     "Validar via servidor: POST/GET com admin_key → server retorna 200/403"),

    ("HIGH", "CONSOLE_LOG_PROD",
     r"\bconsole\.log\s*\(",
     "console.log() em produção — viola Lei 6 e expõe informação interna",
     "Remover ou condicionar a variável de debug: if(DEBUG) console.log(...)"),

    ("HIGH", "HARDCODED_IP_FRONTEND",
     r'["\']https?://(?!api\.plegmadag\.com|api\.plagmadag\.com|localhost|127\.0\.0\.1|213\.199\.42\.88|187\.127\.19\.209|187\.127\.108\.201|82\.197\.70\.189|80\.78\.26\.52)\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(?::\d+)?',
     "IP de servidor hardcoded em frontend — expõe infraestrutura",
     "Usar a constante API_BASE já definida ou variável de configuração"),

    ("HIGH", "PROTOTYPE_POLLUTION",
     r'__proto__\s*\[|constructor\s*\[|prototype\s*\[',
     "Possível prototype pollution — manipulação de Object.prototype",
     "Validar e sanitizar todos os inputs que manipulam propriedades de objetos"),

    ("MEDIUM", "URL_PARAM_DOM_INJECTION",
     r"(?:location\.search|location\.hash|URLSearchParams).*\.innerHTML\s*=",
     "Parâmetro de URL inserido no DOM sem sanitização — XSS reflected",
     "Usar textContent ou encodeURIComponent; nunca colocar params de URL em innerHTML"),

    ("MEDIUM", "MIXED_CONTENT",
     r'src=["\']http://(?!localhost|127\.0\.0\.1)',
     "Recurso carregado via HTTP em página (mixed content)",
     "Usar HTTPS em todos os recursos externos"),

    ("MEDIUM", "CORS_CREDENTIALS_WILDCARD",
     r'credentials\s*:\s*["\']include["\'].*\*|Access-Control.*\*.*credentials',
     "Credenciais CORS com wildcard origin — combinação insegura",
     "Especificar origin exacto quando credentials: 'include'"),

    ("MEDIUM", "LOCALSTORAGE_SENSITIVE",
     r'localStorage\.setItem\s*\(\s*["\'](?:token|key|secret|password|private)',
     "Dado sensível guardado em localStorage — acessível via XSS",
     "Usar HttpOnly cookies ou sessionStorage com TTL curto"),

    ("LOW", "COMMENTED_CREDENTIALS",
     r'//.*(?:password|token|key|secret)\s*[=:]\s*["\'][^"\']+["\']',
     "Possível credencial em comentário JS",
     "Remover completamente — comentários são visíveis no source"),

    ("LOW", "CONSOLE_DEBUG_PROD",
     r"\bconsole\.(?:warn|error|debug|table|dir)\s*\(",
     "console.warn/error/debug em produção — pode expor stack traces",
     "Remover ou guardar atrás de flag de debug"),
]

# ─────────────────────────────────────────────────────────────────────────────
#  REGRAS DART / FLUTTER
# ─────────────────────────────────────────────────────────────────────────────
DART_RULES: List[Tuple] = [

    ("CRITICAL", "DART_RANDOM_INSECURE",
     r"\bRandom\(\)(?!\.secure)",
     "Random() insecure em Dart — não-criptográfico, viola Lei 1",
     "Usar Random.secure() apenas para IVs, ou BLAKE3-derivado para dados determinísticos"),

    ("CRITICAL", "DART_HARDCODED_KEY",
     r'(?:adminKey|masterKey|privateKey|apiKey|secret)\s*=\s*["\'][^"\']{8,}["\']',
     "Credencial hardcoded em Dart — compilada no APK, extraível",
     "Usar flutter_secure_storage ou derivar de seed local"),

    ("HIGH", "DART_HTTP_CLEARTEXT",
     r'["\']http://(?!localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|\$\w|["\'])',
     "URL HTTP (sem TLS) em Dart — tráfego em claro",
     "Usar HTTPS em todas as chamadas de API de produção"),

    ("HIGH", "DART_PRINT_PROD",
     r"^\s{0,8}print\s*\(",
     "print() em código Dart de produção — visível nos logs do dispositivo",
     "Substituir por debugPrint() com kDebugMode guard, ou remover"),

    ("HIGH", "DART_EVAL",
     r"\bFunction\.apply\s*\(|dart:mirrors",
     "Reflexão/eval em Dart — pode executar código arbitrário",
     "Remover uso de dart:mirrors e Function.apply com inputs externos"),

    ("LOW", "DART_CATCH_EMPTY",
     r"catch\s*\([^)]*\)\s*\{[\s\n]*\}",
     "catch vazio em Dart — exceção silenciada (aceitável em operações de UI opcionais)",
     "Em fluxos de auth/crypto: registar o erro: debugPrint('Erro: \$e') ou rethrow"),

    ("MEDIUM", "DART_INSECURE_STORAGE",
     r'SharedPreferences.*(?:setString|setInt).*(?:key|token|secret|private)',
     "Dado sensível em SharedPreferences — não encriptado em Android",
     "Usar flutter_secure_storage para chaves e tokens"),

    ("LOW", "DART_TODO",
     r"//\s*(?:TODO|FIXME|HACK)\b",
     "TODO/FIXME pendente em código Dart",
     "Resolver antes de produção ou documentar decisão"),
]

# ─────────────────────────────────────────────────────────────────────────────
#  SCANNER
# ─────────────────────────────────────────────────────────────────────────────

def _should_skip(path: Path) -> bool:
    if path.name in SKIP_FILES:
        return True
    return any(part in SKIP_DIRS for part in path.parts)


def _scan_lines(filepath: Path, rules: List[Tuple]) -> List[Finding]:
    findings = []
    try:
        text = filepath.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return findings

    lines = text.splitlines()
    for lineno, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "//", "/*", "*", "<!--", "- ", "– ")):
            continue
        for rule in rules:
            severity, category, pattern, description, fix = rule[:5]
            lookahead = rule[5] if len(rule) > 5 else None
            if re.search(pattern, line, re.IGNORECASE):
                if lookahead:
                    window = lines[lineno:lineno + 10]
                    if any(re.search(lookahead, l, re.IGNORECASE) for l in window):
                        break
                findings.append(Finding(
                    severity=severity,
                    category=category,
                    file=str(filepath),
                    line=lineno,
                    snippet=stripped[:120],
                    description=description,
                    fix=fix,
                ))
                break  # uma regra por linha para evitar duplicação
    return findings


_UI_CLI_FILES = {
    "wallet_dashboard.py", "wallet_app.py", "app_navegacao.py",
    "app_boot.py", "sentinela.py", "admin_setup.py",
}
_UI_CLI_SUFFIXES = ("_gui.py", "_dashboard.py", "_app.py", "_navegacao.py", "_boot.py")

def _is_ui_or_test(f: Path) -> bool:
    if f.name in _UI_CLI_FILES:
        return True
    if any(f.name.endswith(s) for s in _UI_CLI_SUFFIXES):
        return True
    if f.name.startswith("test_") or f.name.startswith("teste_"):
        return True
    return False

def scan_backend() -> List[Finding]:
    findings = []
    for f in BACKEND_DIR.rglob("*.py"):
        if _should_skip(f):
            continue
        if _is_ui_or_test(f):
            continue
        findings.extend(_scan_lines(f, PY_RULES))
    return findings


def scan_frontend() -> List[Finding]:
    findings = []
    for ext in ("*.html", "*.js"):
        for f in FRONTEND_DIR.rglob(ext):
            if _should_skip(f):
                continue
            if f.name.endswith(".min.js"):
                continue
            findings.extend(_scan_lines(f, JS_RULES))
    return findings


def scan_flutter() -> List[Finding]:
    findings = []
    if not FLUTTER_DIR.exists():
        return findings
    for f in FLUTTER_DIR.rglob("*.dart"):
        if _should_skip(f):
            continue
        findings.extend(_scan_lines(f, DART_RULES))
    return findings

# ─────────────────────────────────────────────────────────────────────────────
#  PERSISTÊNCIA SQLite
# ─────────────────────────────────────────────────────────────────────────────

def _init_db(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sentinela_scans (
            scan_id    TEXT PRIMARY KEY,
            scanned_at TEXT NOT NULL,
            total      INTEGER,
            critical   INTEGER,
            high       INTEGER,
            medium     INTEGER,
            low        INTEGER
        );
        CREATE TABLE IF NOT EXISTS sentinela_findings (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id     TEXT NOT NULL REFERENCES sentinela_scans(scan_id),
            severity    TEXT NOT NULL,
            category    TEXT NOT NULL,
            file        TEXT NOT NULL,
            line        INTEGER NOT NULL,
            snippet     TEXT,
            description TEXT,
            fix         TEXT,
            scanned_at  TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_findings_severity ON sentinela_findings(severity);
        CREATE INDEX IF NOT EXISTS idx_findings_category ON sentinela_findings(category);
    """)
    conn.commit()


def _persist(findings: List[Finding]) -> str:
    scan_id = _hash(datetime.now(timezone.utc).isoformat())
    now = datetime.now(timezone.utc).isoformat()
    counts = {s: 0 for s in SEV_ORDER}
    for f in findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1

    conn = sqlite3.connect(DB_PATH)
    _init_db(conn)
    conn.execute(
        "INSERT INTO sentinela_scans VALUES (?,?,?,?,?,?,?)",
        (scan_id, now, len(findings),
         counts["CRITICAL"], counts["HIGH"], counts["MEDIUM"], counts["LOW"])
    )
    conn.executemany(
        "INSERT INTO sentinela_findings"
        "(scan_id,severity,category,file,line,snippet,description,fix,scanned_at)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        [(scan_id, f.severity, f.category, f.file, f.line,
          f.snippet, f.description, f.fix, now) for f in findings]
    )
    conn.commit()
    conn.close()
    return scan_id

# ─────────────────────────────────────────────────────────────────────────────
#  RELATÓRIO
# ─────────────────────────────────────────────────────────────────────────────

ANSI = {
    "CRITICAL": "\033[91m\033[1m",
    "HIGH":     "\033[93m\033[1m",
    "MEDIUM":   "\033[94m",
    "LOW":      "\033[37m",
    "RESET":    "\033[0m",
    "BOLD":     "\033[1m",
    "DIM":      "\033[2m",
    "GREEN":    "\033[92m",
}


def _rel(path: str) -> str:
    try:
        return str(Path(path).relative_to(ROOT))
    except ValueError:
        return path


def _print_report(findings: List[Finding], scan_id: str, use_color: bool):
    C = ANSI if use_color else {k: "" for k in ANSI}

    findings.sort(key=lambda f: (SEV_ORDER.get(f.severity, 99), f.file, f.line))
    counts = {s: 0 for s in SEV_ORDER}
    for f in findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1

    print(f"\n{C['BOLD']}⬡ PLEGMA SENTINELA — Relatório de Segurança{C['RESET']}")
    print(f"  {C['DIM']}Scan    : {scan_id}{C['RESET']}")
    print(f"  {C['DIM']}Data    : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}{C['RESET']}")
    print(f"  {C['DIM']}Base    : {DB_PATH}{C['RESET']}")
    print()

    total = len(findings)
    crit = counts["CRITICAL"]
    high = counts["HIGH"]
    med  = counts["MEDIUM"]
    low  = counts["LOW"]

    status = f"{C['CRITICAL']}CRÍTICO{C['RESET']}" if crit > 0 else \
             f"{C['HIGH']}ALTO{C['RESET']}" if high > 0 else \
             f"{C['MEDIUM']}MÉDIO{C['RESET']}" if med > 0 else \
             f"{C['GREEN']}LIMPO{C['RESET']}"

    print(f"  Estado  : {status}  |  Total: {total}")
    print(f"  {C['CRITICAL']}CRITICAL {crit}{C['RESET']}  "
          f"{C['HIGH']}HIGH {high}{C['RESET']}  "
          f"{C['MEDIUM']}MEDIUM {med}{C['RESET']}  "
          f"{C['LOW']}LOW {low}{C['RESET']}")

    if not findings:
        print(f"\n  {C['GREEN']}Nenhuma vulnerabilidade detectada.{C['RESET']}\n")
        return

    current_sev = None
    for f in findings:
        if f.severity != current_sev:
            current_sev = f.severity
            col = C.get(f.severity, "")
            print(f"\n{col}{'━'*60}{C['RESET']}")
            print(f"{col}  {f.severity}{C['RESET']}")
            print(f"{col}{'━'*60}{C['RESET']}")

        col = C.get(f.severity, "")
        print(f"\n  {col}[{f.category}]{C['RESET']}")
        print(f"  {C['BOLD']}{_rel(f.file)}:{f.line}{C['RESET']}")
        print(f"  {C['DIM']}Código{C['RESET']}    {f.snippet}")
        print(f"  {C['DIM']}Problema{C['RESET']}  {f.description}")
        print(f"  {C['DIM']}Fix{C['RESET']}       {f.fix}")

    print(f"\n{'─'*60}\n")


def _print_json(findings: List[Finding], scan_id: str):
    out = {
        "scan_id":   scan_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total":     len(findings),
        "counts": {
            s: sum(1 for f in findings if f.severity == s)
            for s in SEV_ORDER
        },
        "findings": [asdict(f) for f in
                     sorted(findings, key=lambda x: (SEV_ORDER.get(x.severity, 99), x.file, x.line))]
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))

# ─────────────────────────────────────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def run(backend=True, frontend=True, flutter=True,
        use_color=True, as_json=False) -> List[Finding]:

    findings: List[Finding] = []

    if backend:
        if not as_json:
            print(f"  [→] Backend Python ({BACKEND_DIR.name})...")
        be = scan_backend()
        findings.extend(be)
        if not as_json:
            print(f"      {len(be)} achados")

    if frontend:
        if not as_json:
            print(f"  [→] Frontend HTML/JS ({FRONTEND_DIR.name})...")
        fe = scan_frontend()
        findings.extend(fe)
        if not as_json:
            print(f"      {len(fe)} achados")

    if flutter:
        if not as_json:
            print(f"  [→] Flutter Dart ({FLUTTER_DIR})...")
        fl = scan_flutter()
        findings.extend(fl)
        if not as_json:
            print(f"      {len(fl)} achados")

    scan_id = _persist(findings)

    if as_json:
        _print_json(findings, scan_id)
    else:
        _print_report(findings, scan_id, use_color)

    return findings


if __name__ == "__main__":
    args = sys.argv[1:]

    backend_only  = "--backend"  in args
    frontend_only = "--frontend" in args
    flutter_only  = "--flutter"  in args
    no_color      = "--no-color" in args
    as_json       = "--json"     in args

    any_specific = backend_only or frontend_only or flutter_only

    run(
        backend=  not any_specific or backend_only,
        frontend= not any_specific or frontend_only,
        flutter=  not any_specific or flutter_only,
        use_color=not no_color,
        as_json=  as_json,
    )
