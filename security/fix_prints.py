#!/usr/bin/env python3
"""
Converte print() → logging em ficheiros de servidor/library.
Ficheiros UI/CLI são excluídos (adicionados à skip list do sentinela).
"""
import re
import sys
from pathlib import Path

ROOT         = Path(__file__).parent.parent
BACKEND_DIR  = ROOT / "PLEGMA_CORE"
FLUTTER_DIR  = ROOT / "plegma_app" / "lib"

# Ficheiros UI/CLI — output intencional, não converter
UI_PATTERNS = {
    "wallet_dashboard.py", "wallet_app.py", "app_navegacao.py",
    "app_boot.py", "sentinela.py",
}
UI_SUFFIXES = ("_gui.py", "_dashboard.py", "_app.py", "_navegacao.py", "_boot.py")

def is_ui_file(path: Path) -> bool:
    if path.name in UI_PATTERNS:
        return True
    if any(path.name.endswith(s) for s in UI_SUFFIXES):
        return True
    if path.name.startswith("teste_"):
        return True
    return False

IMPORT_LOGGING = "import logging\n"
LOGGER_LINE    = '_log = logging.getLogger(__name__)\n'

def add_logging_header(lines: list[str]) -> list[str]:
    """Insere import logging + _log logo após os imports existentes."""
    if any("import logging" in l for l in lines):
        if not any("_log = logging.getLogger" in l for l in lines):
            insert_at = 0
            for i, l in enumerate(lines):
                if l.startswith("import ") or l.startswith("from "):
                    insert_at = i + 1
            lines.insert(insert_at, "\n")
            lines.insert(insert_at + 1, LOGGER_LINE)
        return lines

    # Encontrar último import consecutivo no topo
    insert_at = 0
    in_docstring = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('"""') or stripped.startswith("'''"):
            in_docstring = not in_docstring
        if in_docstring:
            continue
        if stripped.startswith("import ") or stripped.startswith("from "):
            insert_at = i + 1

    if insert_at == 0:
        insert_at = 1

    lines.insert(insert_at, "\n")
    lines.insert(insert_at + 1, IMPORT_LOGGING)
    lines.insert(insert_at + 2, LOGGER_LINE)
    return lines

RE_EMPTY_PRINT  = re.compile(r'^(\s*)print\s*\(\s*\)\s*$')
RE_PRINT_CALL   = re.compile(r'(\bprint)\s*\(')

def fix_line(line: str) -> str:
    if RE_EMPTY_PRINT.match(line):
        indent = RE_EMPTY_PRINT.match(line).group(1)
        return f'{indent}_log.info("")\n'
    return RE_PRINT_CALL.sub(r'_log.info(', line)

def fix_python_file(path: Path) -> int:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines(keepends=True)

    has_print = any(RE_PRINT_CALL.search(l) or RE_EMPTY_PRINT.match(l) for l in lines)
    if not has_print:
        return 0

    new_lines = [fix_line(l) for l in lines]
    new_lines = add_logging_header(new_lines)

    path.write_text("".join(new_lines), encoding="utf-8")
    count = sum(1 for ol, nl in zip(lines, new_lines) if ol != nl)
    return count

RE_DART_PRINT = re.compile(r'\bprint\s*\(')

def fix_dart_file(path: Path) -> int:
    text = path.read_text(encoding="utf-8", errors="replace")
    new_text = RE_DART_PRINT.sub("debugPrint(", text)
    if new_text == text:
        return 0
    path.write_text(new_text, encoding="utf-8")
    return len(RE_DART_PRINT.findall(text))

def main():
    total_py = 0
    total_dart = 0
    skipped = []

    print("── Python backend ──────────────────────────────")
    for f in sorted(BACKEND_DIR.rglob("*.py")):
        if f.name.startswith("test_") or is_ui_file(f):
            skipped.append(f.name)
            continue
        n = fix_python_file(f)
        if n:
            rel = f.relative_to(ROOT)
            print(f"  ✓ {rel}  ({n} linhas)")
            total_py += n

    print(f"\n── Flutter ─────────────────────────────────────")
    for f in sorted(FLUTTER_DIR.rglob("*.dart")):
        n = fix_dart_file(f)
        if n:
            rel = f.relative_to(ROOT)
            print(f"  ✓ {rel}  ({n} prints)")
            total_dart += n

    print(f"\n── Excluídos (UI/CLI/test) ──────────────────────")
    for s in skipped:
        print(f"  · {s}")

    print(f"\n✔ Total corrigido: {total_py} py + {total_dart} dart")

if __name__ == "__main__":
    main()
