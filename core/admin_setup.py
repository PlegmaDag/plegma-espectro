#!/usr/bin/env python3
"""Utilitário para definir a senha de acesso ao Console Mestre.
Uso: python3 admin_setup.py
     echo "minhasenha" | python3 admin_setup.py --stdin
"""
import argparse
import getpass
import json
import os
import sqlite3
import sys

try:
    import blake3 as _blake3
except ImportError:
    sys.exit("[ERRO] Módulo blake3 não instalado. Execute: pip install blake3")

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plegma_data.db")


def _b3_hash(data: bytes) -> str:
    return _blake3.blake3(data).hexdigest()


def _get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _garantir_tabela():
    with _get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS network_state (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)


def definir_senha(senha: str):
    if len(senha) < 8:
        sys.exit("[ERRO] Senha deve ter pelo menos 8 caracteres.")
    h = _b3_hash(senha.encode("utf-8"))
    _garantir_tabela()
    with _get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO network_state (key, value) VALUES (?, ?)",
            ("admin_password_hash", json.dumps(h))
        )
    print(f"[OK] Hash BLAKE3 definido: {h[:16]}…")
    return h


def verificar_senha(senha: str) -> bool:
    _garantir_tabela()
    with _get_connection() as conn:
        row = conn.execute(
            "SELECT value FROM network_state WHERE key='admin_password_hash'"
        ).fetchone()
    if not row:
        print("[ERRO] admin_password_hash não encontrado no DB.")
        return False
    stored = json.loads(row["value"])
    computed = _b3_hash(senha.encode("utf-8"))
    match = stored == computed
    print(f"[{'OK' if match else 'FALHA'}] stored={stored[:16]}… computed={computed[:16]}… match={match}")
    return match


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Setup senha admin PLEGMA DAG")
    parser.add_argument("--stdin", action="store_true", help="Ler senha de stdin")
    parser.add_argument("--verify", action="store_true", help="Verificar senha (não altera DB)")
    args = parser.parse_args()

    print(f"DB: {DB_PATH}")

    if args.stdin:
        senha = sys.stdin.read().strip()
    else:
        senha = getpass.getpass("Nova senha admin: ")
        if not args.verify:
            conf = getpass.getpass("Confirmar senha: ")
            if senha != conf:
                sys.exit("[ERRO] Senhas não coincidem.")

    if args.verify:
        ok = verificar_senha(senha)
        sys.exit(0 if ok else 1)
    else:
        definir_senha(senha)
        print("[VERIFICAÇÃO] Testando hash armazenado…")
        verificar_senha(senha)
