#!/usr/bin/env python3
"""
PLEGMA DAEMON — Auto-Update Agent
Pesquisa repositórios públicos com boa avaliação por novidades relevantes ao projecto.
Categorias: criptografia pós-quântica · DAG · ZK proofs · Flutter · lattice.
Apenas implementa se o consenso Tri-IA (2/3) aprovar.
Salva relatórios em relatorios/auto_update_*.txt
"""

import sys
import time
import json
import requests
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))
from daemon_config import ORCHESTRATOR, GITHUB_TOKEN
from . import BaseAgent, AgentResult
import event_log

_TIMEOUT    = 15
_RELATORIOS = ORCHESTRATOR / "relatorios"
_RELATORIOS.mkdir(exist_ok=True)
_STARS_MIN  = 50     # estrelas mínimas para considerar relevante
_DAYS_MAX   = 90     # actualizado nos últimos 90 dias
_KEEP_MAX   = 30     # ficheiros de relatório a manter

# Pesquisas temáticas: (query_github, categoria_label)
# Queries curtas — GitHub Search penaliza queries com muitos termos sem matches exactos
_QUERIES = [
    ("dilithium post-quantum",          "Criptografia PQ — Dilithium/ML-DSA"),
    ("blake3 hash",                     "Hash — BLAKE3"),
    ("dag consensus blockchain",        "Consenso DAG"),
    ("zk-snark zero-knowledge",         "ZK Proofs"),
    ("flutter cryptography secure",     "Flutter Security"),
    ("lattice cryptography kyber",      "Lattice Crypto"),
    ("post-quantum protocol network",   "Protocolo PQ"),
]

_GH_SEARCH  = "https://api.github.com/search/repositories"
_GH_HEADERS = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
if GITHUB_TOKEN:
    _GH_HEADERS["Authorization"] = f"Bearer {GITHUB_TOKEN}"


def _pesquisar_github(query: str, stars_min: int = _STARS_MIN, days: int = _DAYS_MAX) -> list[dict]:
    data_limite = (datetime.now(tz=timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    q    = f"{query} stars:>={stars_min} pushed:>{data_limite}"
    params = {"q": q, "sort": "stars", "order": "desc", "per_page": 5}
    try:
        r    = requests.get(_GH_SEARCH, params=params, headers=_GH_HEADERS, timeout=_TIMEOUT)
        if r.status_code == 200:
            items = r.json().get("items", [])
            return [{
                "name":        it["full_name"],
                "url":         it["html_url"],
                "stars":       it["stargazers_count"],
                "description": (it.get("description") or "")[:200],
                "updated":     it.get("pushed_at", "")[:10],
                "language":    it.get("language") or "?",
                "topics":      it.get("topics", []),
            } for it in items]
        return []
    except Exception:
        return []


def _ja_reportado(nome_repo: str) -> bool:
    """Evita reportar o mesmo repo duas vezes no mesmo mês."""
    mes_actual = datetime.now(tz=timezone.utc).strftime("%Y%m")
    for f in _RELATORIOS.glob(f"auto_update_{mes_actual}*.txt"):
        try:
            if nome_repo in f.read_text(encoding="utf-8"):
                return True
        except Exception:
            pass
    return False


def pesquisar_novidades() -> list[dict]:
    """Percorre todas as categorias e devolve lista de achados."""
    achados = []
    for query, categoria in _QUERIES:
        repos = _pesquisar_github(query)
        for repo in repos:
            if not _ja_reportado(repo["name"]):
                repo["categoria"] = categoria
                achados.append(repo)
        time.sleep(1.2)   # respeita rate-limit GitHub (10 req/min sem auth)
    return achados


def _formatar_relatorio(achados: list[dict], decisoes: list[dict]) -> str:
    agora  = datetime.now(tz=timezone.utc)
    sep    = "═" * 60
    linhas = [
        sep,
        f"  ⬡ PLEGMA DAG — AUTO-UPDATE REPORT  {agora.strftime('%d/%m/%Y %H:%M UTC')}",
        sep,
        f"  Repositórios analisados : {len(achados)}",
        f"  Decisões de consenso    : {len(decisoes)}",
        "",
    ]

    aprovados  = [d for d in decisoes if d.get("approved")]
    rejeitados = [d for d in decisoes if not d.get("approved")]

    if aprovados:
        linhas.append("INOVAÇÕES APROVADAS PELO CONSENSO TRI-IA")
        for d in aprovados:
            r = d["repo"]
            linhas += [
                f"  ★ {r['name']}  [{r['stars']} ⭐]  {r['categoria']}",
                f"    {r['url']}",
                f"    {r['description']}",
                f"    Linguagem: {r['language']}  |  Actualizado: {r['updated']}",
                f"    Consenso: {d['approvals']}/3 APPROVE  (hash {d['hash']})",
                f"    ACÇÃO SUGERIDA: Avaliar integração/referência no projecto",
                "",
            ]
    else:
        linhas += ["INOVAÇÕES APROVADAS", "  Nenhuma neste ciclo.", ""]

    if rejeitados:
        linhas.append("REPOSITÓRIOS ANALISADOS — NÃO APROVADOS")
        for d in rejeitados:
            r = d["repo"]
            linhas += [
                f"  · {r['name']}  [{r['stars']} ⭐]  {r['categoria']}",
                f"    {r['url']}",
                f"    Consenso: {d['approvals']}/3  motivo: {d.get('motivo', '?')[:120]}",
                "",
            ]

    if not achados:
        linhas += ["  Nenhum repositório novo relevante encontrado neste ciclo.", ""]

    linhas += [sep, f"  Gerado: {agora.strftime('%Y-%m-%d %H:%M UTC')}", sep, ""]
    return "\n".join(linhas)


class AutoUpdateAgent(BaseAgent):
    name = "auto_update"

    def _execute(self, task: str, context: dict) -> AgentResult:
        from agents.consensus_engine import reach_consensus

        details   = []
        decisoes  = []

        details.append("Pesquisando repositórios públicos...")
        achados = pesquisar_novidades()
        details.append(f"  {len(achados)} novos repositórios encontrados")

        for repo in achados[:10]:   # máximo 10 por ciclo para não esgotar quota
            decision_prompt = (
                f"NOVO REPOSITÓRIO PÚBLICO DETECTADO\n\n"
                f"Nome     : {repo['name']}\n"
                f"URL      : {repo['url']}\n"
                f"Estrelas : {repo['stars']}\n"
                f"Categoria: {repo['categoria']}\n"
                f"Descrição: {repo['description']}\n"
                f"Linguagem: {repo['language']}\n"
                f"Tópicos  : {', '.join(repo.get('topics', []))}\n"
                f"Actualiz.: {repo['updated']}\n\n"
                f"PERGUNTA: Este repositório contém inovações relevantes para o projecto "
                f"PLEGMA DAG (criptografia pós-quântica Dilithium3/BLAKE3, DAG consensus, "
                f"ZK proofs, Flutter seguro, lattice)? "
                f"APPROVE se sim e merece ser referenciado/avaliado para integração. "
                f"REJECT se não é relevante ou se pode comprometer a segurança/determinismo do projecto."
            )
            ctx = (
                "PLEGMA DAG — Stack: Dilithium3 (ML-DSA-65), BLAKE3, ZK-SNARK 22KB, "
                "DAG acíclico, Flutter 3.41.5. Supply fixo 21B $PLG. "
                "Regra: nunca introduzir aleatoriedade, curvas elípticas ou RSA."
            )
            resultado = reach_consensus(decision_prompt, context=ctx)
            motivo_rej = ""
            if not resultado["approved"]:
                rejeicoes = [v["reason"] for v in resultado["votes"] if v["vote"] == "REJECT"]
                motivo_rej = rejeicoes[0] if rejeicoes else "não relevante"

            decisoes.append({
                "repo":      repo,
                "approved":  resultado["approved"],
                "approvals": resultado["approvals"],
                "hash":      resultado["hash"],
                "motivo":    motivo_rej,
            })

            status_str = "✅ APROVADO" if resultado["approved"] else "❌ rejeitado"
            details.append(f"  [{status_str}] {repo['name']} ({repo['stars']}⭐) — {repo['categoria']}")

            event_log.log(
                self.name, "repo_avaliado",
                "APPROVE" if resultado["approved"] else "REJECT",
                f"{repo['name']} ({repo['stars']}⭐) — {resultado['approvals']}/3",
                {"repo": repo["name"], "stars": repo["stars"], "hash": resultado["hash"]}
            )

            time.sleep(2)   # pausa entre chamadas de API

        # Gera relatório
        texto    = _formatar_relatorio(achados, decisoes)
        dt_now   = datetime.now(tz=timezone.utc)
        filename = f"auto_update_{dt_now.strftime('%Y%m%d_%H%M')}.txt"
        filepath = _RELATORIOS / filename
        filepath.write_text(texto, encoding="utf-8")

        # Limpeza
        antigos = sorted(_RELATORIOS.glob("auto_update_*.txt"))[:-_KEEP_MAX]
        for f in antigos:
            f.unlink(missing_ok=True)

        aprovados = sum(1 for d in decisoes if d["approved"])
        summary   = (
            f"{len(achados)} repositórios analisados · "
            f"{aprovados} aprovados pelo consenso → {filename}"
        )

        return AgentResult(
            agent=self.name, status="SUCCESS", summary=summary,
            details=details,
            data={"achados": len(achados), "aprovados": aprovados, "file": str(filepath)}
        )
