#!/usr/bin/env python3
"""
PLEGMA ORCHESTRATOR — Limpeza de _ARQUIVADOS/
Remove ficheiros em quarentena dos 4 nós após confirmação de ausência de alertas.
Execução única: python limpar_arquivados.py
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from daemon_config import NODES, SSH_KEY, SSH_USER

_OPTS = ["-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=10", "-i", SSH_KEY]
_DIR  = "/root/PLEGMA_CORE/_ARQUIVADOS"


def _ssh(ip: str, cmd: str) -> str:
    r = subprocess.run(
        ["ssh"] + _OPTS + [f"{SSH_USER}@{ip}", cmd],
        capture_output=True, text=True, timeout=20
    )
    return (r.stdout + r.stderr).strip()


def main():
    print("⬡ PLEGMA — Limpeza _ARQUIVADOS/ (quarentena encerrada em 12/05/2026)\n")
    total_ok = 0
    for nid, node in NODES.items():
        ip    = node["ip"]
        label = node.get("label", nid)
        print(f"[{label}] {ip}")

        conteudo = _ssh(ip, f"ls {_DIR}/ 2>/dev/null || echo NAOEXISTE")
        if conteudo == "NAOEXISTE":
            print(f"  ✓ _ARQUIVADOS/ já não existe")
            total_ok += 1
            continue

        print(f"  Ficheiros: {conteudo.replace(chr(10), ', ')}")
        out = _ssh(ip, f"rm -rf {_DIR} && echo OK || echo ERRO")
        if "OK" in out:
            print(f"  ✓ _ARQUIVADOS/ eliminado")
            total_ok += 1
        else:
            print(f"  ✕ ERRO: {out}")

    print(f"\n⬡ Resultado: {total_ok}/{len(NODES)} nós limpos")


if __name__ == "__main__":
    main()
