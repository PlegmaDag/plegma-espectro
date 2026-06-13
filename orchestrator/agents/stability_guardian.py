#!/usr/bin/env python3
"""
PLEGMA DAEMON — Stability Guardian Agent
Guardião da Estabilidade e Melhoria Contínua do Protocolo PLEGMA DAG.

Responsabilidades:
  1. SCORE DE SAÚDE — consolida eventos recentes dos agentes de auditoria
     num score 0-100 que reflecte o estado real do sistema
  2. VIGILÂNCIA DE REPOS AUDITADOS — monitoriza commits/releases de um conjunto
     curado de repositórios de confiança (não faz descoberta aleatória —
     essa é função do auto_update_agent)
  3. PROPOSTAS DE MELHORIA — para cada mudança relevante detectada, gera uma
     proposta concreta (ficheiro:função → o que melhorar e porquê)
  4. CONSENSO TRI-IA — toda proposta passa por 2/3 antes de ser registada
     como aprovada; NUNCA modifica código directamente
  5. RELATÓRIO — salva em relatorios/stability_YYYYMMDD_HHMM.txt (max 30)

Diferença clara face ao auto_update_agent:
  auto_update_agent  → descobre repositórios novos → relatório de novidades
  stability_guardian → monitoriza repos conhecidos → propõe melhorias específicas

LEIS RESPEITADAS (verificadas em cada proposta antes do consenso):
  LEI 1: só aprova código determinístico e pós-quântico (Dilithium3/BLAKE3/ZK)
  LEI 2: nunca duplica — verifica existência antes de propor
  LEI 3: nunca reescreve o que funciona — melhora, não substitui
  LEI 6: sem credenciais, sem dead code, sem print(), sem SELECT *

Schedule: diário às 02:00 UTC (antes do code_audit às 03:00)
"""

import sys
import re
import time
import json
import requests
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
from daemon_config import ORCHESTRATOR, CORE, GITHUB_TOKEN, ANTHROPIC_KEY
import event_log
from . import BaseAgent, AgentResult

_TIMEOUT    = 20
_RELATORIOS = ORCHESTRATOR / "relatorios"
_RELATORIOS.mkdir(exist_ok=True)
_STATE_FILE = ORCHESTRATOR / "stability_state.json"   # último SHA por repo
_KEEP_MAX   = 30

# ── Repositórios curados e auditados ────────────────────────────────────────
# Critérios de inclusão: >500 stars · auditado publicamente · directamente
# relevante para o stack PLEGMA (BLAKE3, Dilithium, ZK, DAG, FastAPI)
# Não inclui repos descobertos aleatoriamente — esses vão para auto_update.
_REPOS_AUDITADOS = [
    {
        "repo":      "BLAKE3-team/BLAKE3",
        "dominio":   "Hash",
        "relevancia": "Implementação canónica BLAKE3 — hash central do protocolo PLEGMA",
        "ficheiros_plegma": ["PLEGMA_CORE/plegma_db.py", "PLEGMA_CORE/core_api.py"],
    },
    {
        "repo":      "pq-crystals/dilithium",
        "dominio":   "Assinatura PQ",
        "relevancia": "ML-DSA Dilithium3 (NIST FIPS 204) — assinatura pós-quântica do protocolo",
        "ficheiros_plegma": ["PLEGMA_CORE/auth_server.py", "PLEGMA_CORE/wallet_server.py"],
    },
    {
        "repo":      "pq-crystals/kyber",
        "dominio":   "KEM PQ",
        "relevancia": "ML-KEM — troca de chaves pós-quântica para canais seguros entre nós",
        "ficheiros_plegma": ["PLEGMA_CORE/core_api.py"],
    },
    {
        "repo":      "iden3/snarkjs",
        "dominio":   "ZK-SNARK",
        "relevancia": "ZK-SNARKs — relevante para geração/verificação de provas 22KB",
        "ficheiros_plegma": ["PLEGMA_CORE/core_api.py"],
    },
    {
        "repo":      "tiangolo/fastapi",
        "dominio":   "API Framework",
        "relevancia": "FastAPI — base do core_api.py; novas versões podem trazer hardening",
        "ficheiros_plegma": ["PLEGMA_CORE/core_api.py"],
    },
    {
        "repo":      "encode/uvicorn",
        "dominio":   "ASGI Server",
        "relevancia": "Uvicorn — servidor ASGI do PLEGMA CORE; patches de segurança críticos",
        "ficheiros_plegma": ["PLEGMA_CORE/core_api.py"],
    },
    {
        "repo":      "nicowillis/dag-consensus",
        "dominio":   "DAG Consensus",
        "relevancia": "Algoritmos de consenso DAG acíclico — base do protocolo de consenso",
        "ficheiros_plegma": ["PLEGMA_CORE/plegma_db.py"],
    },
    {
        "repo":      "oasisprotocol/curve25519-voi",
        "dominio":   "Criptografia",
        "relevancia": "Implementações constant-time — padrão para resistência a side-channel",
        "ficheiros_plegma": ["PLEGMA_CORE/auth_server.py"],
    },
]

_GH_API     = "https://api.github.com"
_GH_HEADERS = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
if GITHUB_TOKEN:
    _GH_HEADERS["Authorization"] = f"Bearer {GITHUB_TOKEN}"

# ── Leis que cada proposta deve satisfazer ───────────────────────────────────
_LEIS_CHECK = """
LEIS DO PROTOCOLO PLEGMA DAG — verificar antes de aprovar qualquer proposta:

LEI 1 — DETERMINISMO E PÓS-QUÂNTICO:
  PROIBIDO: Math.random(), UUID v4, ECDSA, RSA, DSA, secp256k1, MD5, SHA1
  OBRIGATÓRIO: BLAKE3, Dilithium3 (ML-DSA-65), ZK-SNARK ≤22KB, nonces derivados de estado

LEI 2 — SEM REDUNDÂNCIA:
  Nunca propor criar função/endpoint/tabela que já exista no codebase

LEI 3 — SEM RETRABALHO:
  Apenas melhorar o que existe, nunca reescrever código que já funciona

LEI 6 — QUALIDADE:
  Sem print() de debug, sem SELECT *, sem credenciais hardcoded, sem dead code
"""


# ── Persistência de estado ───────────────────────────────────────────────────

def _carregar_estado() -> dict:
    if _STATE_FILE.exists():
        try:
            return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"last_sha": {}, "ultimo_score": None, "propostas_aprovadas": 0}


def _salvar_estado(estado: dict):
    _STATE_FILE.write_text(json.dumps(estado, indent=2, ensure_ascii=False), encoding="utf-8")


# ── Score de saúde do sistema ────────────────────────────────────────────────

def _score_sistema() -> dict:
    """
    Consolida eventos recentes dos agentes de auditoria num score 0-100.
    Usa event_log.recent() — API pública, não acede internals do módulo.
    """
    try:
        # Últimas 24h — recent() devolve os N mais recentes, filtramos por ts
        ts_limite = time.time() - 86400
        rows = [r for r in event_log.recent(limit=500) if r.get("ts", 0) >= ts_limite]

        penalidades = 0
        detalhes    = []

        falhas_criticas = [
            r for r in rows
            if r.get("status") == "FAIL" and r.get("action") not in ("job_error",)
        ]
        falhas_server = [
            r for r in rows
            if r.get("agent") == "server_monitor" and r.get("status") == "FAIL"
        ]
        criticos_seg = [
            r for r in rows
            if r.get("action") in ("critical", "security_critical")
            and "CRITICAL" in (r.get("summary") or "")
        ]
        # Penalizar também falhas do social_manager com menos peso
        falhas_social = [
            r for r in rows
            if r.get("agent") == "social_manager" and r.get("status") == "FAIL"
        ]

        penalidades += min(len(falhas_criticas) * 2, 30)
        penalidades += min(len(falhas_server)   * 5, 20)
        penalidades += min(len(criticos_seg)    * 10, 40)
        penalidades += min(len(falhas_social),        5)   # -1 por falha social, máx -5

        score = max(0, 100 - penalidades)

        # Contagem de sucessos como confirmação
        sucessos = [r for r in rows if r.get("status") in ("OK", "APPROVE", "SUCCESS")]

        if falhas_server:
            detalhes.append(f"  ⚠ {len(falhas_server)} falha(s) de servidor nas últimas 24h (−{min(len(falhas_server)*5,20)} pts)")
        if criticos_seg:
            detalhes.append(f"  ✕ {len(criticos_seg)} alerta(s) crítico(s) de segurança (−{min(len(criticos_seg)*10,40)} pts)")
        if falhas_criticas and not falhas_server:
            detalhes.append(f"  ⚑ {len(falhas_criticas)} falha(s) de agentes nas últimas 24h (−{min(len(falhas_criticas)*2,30)} pts)")
        if falhas_social:
            detalhes.append(f"  · {len(falhas_social)} falha(s) de API social (API externa inacessível)")
        if not falhas_server and not criticos_seg:
            detalhes.append(f"  ✓ Servidores e segurança sem falhas críticas nas últimas 24h")
        detalhes.append(f"  ✓ {len(sucessos)} operações bem-sucedidas nas últimas 24h")

        nivel = "CRÍTICO" if score < 40 else "DEGRADADO" if score < 70 else "BOM" if score < 90 else "EXCELENTE"
        return {"score": score, "nivel": nivel, "detalhes": detalhes, "falhas": len(falhas_criticas)}
    except Exception as e:
        return {"score": 0, "nivel": "ERRO", "detalhes": [f"  Erro ao calcular score: {e}"], "falhas": -1}


# ── Vigilância de repos auditados ────────────────────────────────────────────

def _get_commits_recentes(repo: str, desde_sha: Optional[str]) -> list:
    """Retorna commits novos desde o último SHA registado (máx 5)."""
    try:
        url    = f"{_GH_API}/repos/{repo}/commits"
        params = {"per_page": 5}
        r = requests.get(url, headers=_GH_HEADERS, params=params, timeout=_TIMEOUT)
        if r.status_code != 200:
            return []
        commits = r.json()
        if not isinstance(commits, list):
            return []
        # Filtrar apenas commits mais novos que o último SHA visto
        novos = []
        for c in commits:
            sha = c.get("sha", "")
            if sha == desde_sha:
                break
            msg   = c.get("commit", {}).get("message", "").split("\n")[0][:120]
            autor = c.get("commit", {}).get("author", {}).get("name", "?")
            data  = c.get("commit", {}).get("author", {}).get("date", "")[:10]
            novos.append({"sha": sha, "msg": msg, "autor": autor, "data": data})
        return novos
    except Exception:
        return []


def _get_releases_recentes(repo: str) -> list:
    """Retorna o último release publicado."""
    try:
        url = f"{_GH_API}/repos/{repo}/releases/latest"
        r   = requests.get(url, headers=_GH_HEADERS, timeout=_TIMEOUT)
        if r.status_code != 200:
            return []
        rel = r.json()
        return [{
            "tag":  rel.get("tag_name", "?"),
            "nome": rel.get("name", "?")[:80],
            "data": (rel.get("published_at") or "")[:10],
            "url":  rel.get("html_url", ""),
            "body": (rel.get("body") or "")[:400],
        }]
    except Exception:
        return []


# ── Análise de relevância com Claude ─────────────────────────────────────────

def _analisar_relevancia(repo_info: dict, commits: list, releases: list) -> Optional[dict]:
    """
    Usa Claude (Anthropic) para determinar se as mudanças recentes no repo
    têm implicações concretas para o código PLEGMA.
    Devolve proposta estruturada ou None se não relevante.
    """
    if not ANTHROPIC_KEY:
        return None
    if not commits and not releases:
        return None

    mudancas_txt = ""
    if commits:
        mudancas_txt += "COMMITS RECENTES:\n"
        for c in commits[:3]:
            mudancas_txt += f"  [{c['data']}] {c['msg']}\n"
    if releases:
        mudancas_txt += "\nULTIMO RELEASE:\n"
        for rel in releases:
            mudancas_txt += f"  {rel['tag']} ({rel['data']}): {rel['nome']}\n"
            if rel.get("body"):
                mudancas_txt += f"  Notas: {rel['body'][:300]}\n"

    ficheiros_plegma = "\n".join(f"  - {f}" for f in repo_info.get("ficheiros_plegma", []))

    prompt = f"""Analisa as mudanças recentes no repositório {repo_info['repo']} e determina
se são relevantes para o projecto PLEGMA DAG.

CONTEXTO DO PROJECTO:
{_LEIS_CHECK}

FICHEIROS PLEGMA POTENCIALMENTE AFECTADOS:
{ficheiros_plegma}

DOMÍNIO DO REPO: {repo_info['dominio']}
RELEVÂNCIA ESPERADA: {repo_info['relevancia']}

MUDANÇAS RECENTES:
{mudancas_txt}

TAREFA: Analisa se estas mudanças contêm melhorias aplicáveis ao PLEGMA DAG
que respeitem todas as Leis do Protocolo.

Se SIM, responde EXACTAMENTE neste formato JSON (sem markdown):
{{
  "relevante": true,
  "tipo": "SEGURANÇA|PERFORMANCE|ESTABILIDADE|CONFORMIDADE",
  "ficheiro_alvo": "PLEGMA_CORE/nome_ficheiro.py",
  "funcao_alvo": "nome_da_funcao_ou_modulo",
  "descricao": "Descrição clara do que melhorar (máx 200 chars)",
  "justificativa": "Por que esta melhoria é importante para PLEGMA (máx 200 chars)",
  "risco": "BAIXO|MÉDIO|ALTO",
  "lei_violada": null
}}

Se NÃO for relevante ou violar alguma Lei, responde:
{{"relevante": false, "motivo": "razão breve"}}

Responde APENAS com o JSON, sem texto adicional."""

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = (msg.content[0].text or "").strip()

        # Extrai JSON
        match = re.search(r'\{[^{}]*"relevante"[^{}]*\}', raw, re.DOTALL)
        if not match:
            # Tenta parse directo
            data = json.loads(raw)
        else:
            data = json.loads(match.group())

        if not data.get("relevante"):
            return None
        return data
    except Exception:
        return None


# ── Agente principal ──────────────────────────────────────────────────────────

class StabilityGuardianAgent(BaseAgent):
    name = "stability_guardian"

    def _execute(self, task: str, context: dict) -> AgentResult:
        from agents.consensus_engine import reach_consensus

        agora   = datetime.now(tz=timezone.utc)
        estado  = _carregar_estado()
        details = []
        propostas_ciclo: list[dict] = []

        # ── 1. Score de saúde ────────────────────────────────────────────────
        saude = _score_sistema()
        details.append(f"Score de saúde: {saude['score']}/100 [{saude['nivel']}]")
        details.extend(saude["detalhes"])
        details.append("")

        # ── 2. Vigilância de repos auditados ────────────────────────────────
        details.append(f"Repos auditados monitorizados: {len(_REPOS_AUDITADOS)}")
        repos_com_novidades = 0

        for repo_info in _REPOS_AUDITADOS:
            repo      = repo_info["repo"]
            ultimo_sha = estado["last_sha"].get(repo)

            commits  = _get_commits_recentes(repo, ultimo_sha)
            releases = _get_releases_recentes(repo)

            if not commits and not releases:
                time.sleep(0.5)
                continue

            repos_com_novidades += 1
            details.append(f"  [{repo_info['dominio']}] {repo}: {len(commits)} commit(s) novo(s)")

            # ── 3. Análise de relevância com IA ─────────────────────────────
            proposta = _analisar_relevancia(repo_info, commits, releases)

            # Actualiza SHA mesmo que não haja proposta
            if commits:
                estado["last_sha"][repo] = commits[0]["sha"]

            if proposta is None:
                details.append(f"    → Sem impacto aplicável ao PLEGMA")
                time.sleep(1)
                continue

            details.append(f"    → Proposta detectada: [{proposta['tipo']}] {proposta['descricao'][:80]}")

            # ── 4. Consenso Tri-IA ───────────────────────────────────────────
            prompt_consenso = (
                f"PROPOSTA DE MELHORIA DE CÓDIGO — STABILITY GUARDIAN\n\n"
                f"Repositório fonte: {repo}\n"
                f"Domínio: {repo_info['dominio']}\n"
                f"Tipo: {proposta['tipo']}\n"
                f"Ficheiro alvo: {proposta.get('ficheiro_alvo', '?')}\n"
                f"Função/módulo: {proposta.get('funcao_alvo', '?')}\n"
                f"Descrição: {proposta['descricao']}\n"
                f"Justificativa: {proposta['justificativa']}\n"
                f"Risco estimado: {proposta.get('risco', '?')}\n\n"
                f"VERIFICAÇÃO DE LEIS:\n{_LEIS_CHECK}\n\n"
                f"PERGUNTA: Esta proposta é segura, relevante e compatível com as Leis "
                f"do Protocolo PLEGMA DAG? "
                f"APPROVE se sim. REJECT se viola alguma Lei ou introduz risco inaceitável."
            )
            ctx_consenso = (
                "PLEGMA DAG — Stack: Dilithium3, BLAKE3, ZK-SNARK 22KB, DAG acíclico, Python FastAPI. "
                "Supply fixo 21B $PLG. Regra de ouro: nunca introduzir aleatoriedade, "
                "curvas elípticas clássicas ou RSA."
            )
            resultado = reach_consensus(prompt_consenso, context=ctx_consenso)

            status_proposta = "APROVADA" if resultado["approved"] else "REJEITADA"
            details.append(f"    → Consenso Tri-IA: {status_proposta} ({resultado['approvals']}/3)")

            proposta["repo"]        = repo
            proposta["aprovada"]    = resultado["approved"]
            proposta["approvals"]   = resultado["approvals"]
            proposta["hash"]        = resultado["hash"]
            proposta["commits_ref"] = [c["sha"][:8] for c in commits[:2]]
            propostas_ciclo.append(proposta)

            if resultado["approved"]:
                estado["propostas_aprovadas"] = estado.get("propostas_aprovadas", 0) + 1
                event_log.log(
                    self.name, "proposta_aprovada", "APPROVE",
                    f"{repo} → {proposta.get('ficheiro_alvo','?')} [{proposta['tipo']}]",
                    {"repo": repo, "ficheiro": proposta.get("ficheiro_alvo"), "tipo": proposta["tipo"]}
                )
            else:
                rejeicoes = [v["reason"] for v in resultado["votes"] if v["vote"] == "REJECT"]
                motivo    = rejeicoes[0][:120] if rejeicoes else "não relevante"
                event_log.log(
                    self.name, "proposta_rejeitada", "REJECT",
                    f"{repo} — {motivo[:120]}", {"repo": repo}
                )

            time.sleep(2)  # pausa entre chamadas de API

        # ── 5. Salvar estado e relatório ─────────────────────────────────────
        estado["ultimo_score"] = saude["score"]
        _salvar_estado(estado)

        relatorio = _formatar_relatorio(agora, saude, propostas_ciclo, repos_com_novidades)
        filename  = f"stability_{agora.strftime('%Y%m%d_%H%M')}.txt"
        filepath  = _RELATORIOS / filename
        filepath.write_text(relatorio, encoding="utf-8")

        # Limpar ficheiros antigos
        antigos = sorted(_RELATORIOS.glob("stability_*.txt"))[:-_KEEP_MAX]
        for f in antigos:
            f.unlink(missing_ok=True)

        aprovadas  = sum(1 for p in propostas_ciclo if p["aprovada"])
        rejeitadas = len(propostas_ciclo) - aprovadas

        summary = (
            f"Score {saude['score']}/100 [{saude['nivel']}] · "
            f"{repos_com_novidades} repos com novidades · "
            f"{aprovadas} proposta(s) aprovada(s) · {rejeitadas} rejeitada(s) → {filename}"
        )

        status = "FAILURE" if saude["score"] < 40 else "PARTIAL" if saude["score"] < 70 else "SUCCESS"

        return AgentResult(
            agent=self.name, status=status, summary=summary,
            details=details,
            data={
                "score":      saude["score"],
                "nivel":      saude["nivel"],
                "aprovadas":  aprovadas,
                "rejeitadas": rejeitadas,
                "file":       str(filepath),
            }
        )


# ── Formatação do relatório ───────────────────────────────────────────────────

def _formatar_relatorio(agora: datetime, saude: dict, propostas: list, repos_novos: int) -> str:
    sep  = "═" * 60
    sep2 = "─" * 60

    score_bar_filled = int(saude["score"] / 5)
    score_bar = "█" * score_bar_filled + "░" * (20 - score_bar_filled)

    linhas = [
        sep,
        f"  ⬡ PLEGMA DAG — STABILITY GUARDIAN  {agora.strftime('%d/%m/%Y %H:%M UTC')}",
        sep,
        "",
        "SCORE DE SAÚDE DO SISTEMA",
        f"  {saude['score']}/100  [{saude['nivel']}]",
        f"  [{score_bar}]",
        *saude["detalhes"],
        "",
        sep2,
        f"  Repos auditados com novidades: {repos_novos}/{len(_REPOS_AUDITADOS)}",
        f"  Propostas geradas este ciclo : {len(propostas)}",
        sep2,
        "",
    ]

    aprovadas  = [p for p in propostas if p.get("aprovada")]
    rejeitadas = [p for p in propostas if not p.get("aprovada")]

    if aprovadas:
        linhas.append("PROPOSTAS APROVADAS PELO CONSENSO TRI-IA")
        linhas.append("  (Requerem revisão humana antes de implementação)")
        linhas.append("")
        for p in aprovadas:
            linhas += [
                f"  ★ [{p['tipo']}] {p['repo']}",
                f"    Ficheiro alvo : {p.get('ficheiro_alvo', '?')}",
                f"    Função/módulo : {p.get('funcao_alvo', '?')}",
                f"    Descrição     : {p['descricao']}",
                f"    Justificativa : {p['justificativa']}",
                f"    Risco         : {p.get('risco', '?')}",
                f"    Consenso      : {p['approvals']}/3 APPROVE (hash {p['hash']})",
                f"    Commits ref   : {', '.join(p.get('commits_ref', []))}",
                f"    ACÇÃO         : Revisar e implementar manualmente se concordar",
                "",
            ]
    else:
        linhas += ["PROPOSTAS APROVADAS", "  Nenhuma neste ciclo.", ""]

    if rejeitadas:
        linhas.append("PROPOSTAS REJEITADAS PELO CONSENSO")
        for p in rejeitadas:
            linhas += [
                f"  · [{p['tipo']}] {p['repo']} → {p.get('ficheiro_alvo','?')}",
                f"    {p['descricao'][:100]}",
                f"    Consenso: {p['approvals']}/3",
                "",
            ]

    linhas += [
        sep,
        "REPOS AUDITADOS MONITORIZADOS",
        "",
    ]
    for r in _REPOS_AUDITADOS:
        linhas.append(f"  [{r['dominio']:12}] {r['repo']}")
        linhas.append(f"                 {r['relevancia'][:70]}")

    linhas += [
        "",
        sep,
        f"  Gerado: {agora.strftime('%Y-%m-%d %H:%M UTC')}",
        f"  Próxima execução: 02:00 UTC",
        sep, "",
    ]
    return "\n".join(linhas)
