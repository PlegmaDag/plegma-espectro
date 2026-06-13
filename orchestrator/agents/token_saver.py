#!/usr/bin/env python3
"""
PLEGMA ORCHESTRATOR — Token Saver Agent
Mantém SESSION_START.md mínimo e gera checkpoints pré-compact.
"""

import os
import re
from datetime import datetime
from pathlib import Path
from . import BaseAgent, AgentResult

PROJECT_ROOT  = Path("D:/PROJETO_Plegma_DAG")
MEMORY_DIR    = PROJECT_ROOT / "PROJECT_MEMORY"
SESSION_START = MEMORY_DIR / "SESSION_START.md"
DOMAINS_DIR   = MEMORY_DIR / "domains"


class TokenSaverAgent(BaseAgent):
    name = "token_saver"

    def _execute(self, task: str, context: dict) -> AgentResult:
        task_lower = task.lower()

        if any(k in task_lower for k in ["checkpoint", "compact", "compactar"]):
            return self._create_checkpoint(context)
        if any(k in task_lower for k in ["session_start", "session start", "atualizar sessão"]):
            return self._update_session_start(context)
        if any(k in task_lower for k in ["stats", "tamanho", "token"]):
            return self._report_memory_stats()

        return self._report_memory_stats()

    # ------------------------------------------------------------------
    # Checkpoint pré-compact
    # ------------------------------------------------------------------
    def _create_checkpoint(self, context: dict) -> AgentResult:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = MEMORY_DIR / f"CHECKPOINT_{ts}.md"

        tarefa      = context.get("tarefa",   "—")
        decisoes    = context.get("decisoes", [])
        ficheiros   = context.get("ficheiros", [])
        proximos    = context.get("proximos", [])

        linhas_dec  = "\n".join(f"- {d}" for d in decisoes[:5]) or "- (sem registo)"
        linhas_fich = "\n".join(f"- {f}" for f in ficheiros[:10]) or "- (sem registo)"
        linhas_prox = "\n".join(f"- {p}" for p in proximos[:3]) or "- (sem registo)"

        conteudo = f"""\
# Checkpoint {datetime.now().strftime('%d/%m/%Y %H:%M')}

## Tarefa em curso
{tarefa}

## Decisões tomadas
{linhas_dec}

## Ficheiros modificados
{linhas_fich}

## Próximos passos
{linhas_prox}
"""
        path.write_text(conteudo, encoding="utf-8")
        return AgentResult(
            agent=self.name,
            status="SUCCESS",
            summary=f"Checkpoint guardado: {path.name}",
            details=[f"Caminho: {path}"],
            data={"checkpoint_path": str(path)},
        )

    # ------------------------------------------------------------------
    # Actualiza SESSION_START.md — apenas secção ESTADO GLOBAL
    # ------------------------------------------------------------------
    def _update_session_start(self, context: dict) -> AgentResult:
        if not SESSION_START.exists():
            return AgentResult(
                agent=self.name,
                status="FAILURE",
                summary="SESSION_START.md não encontrado",
            )

        texto = SESSION_START.read_text(encoding="utf-8")

        data_hoje    = datetime.now().strftime("%d %b %Y").upper()
        sentinela    = context.get("sentinela", None)
        apk_versao   = context.get("apk", None)
        resumo_sess  = context.get("resumo", "Sessão em curso")

        # Substitui data na linha do ESTADO GLOBAL
        texto = re.sub(r"(## ESTADO GLOBAL \()([^)]+)(\))", f"\\g<1>{data_hoje}\\g<3>", texto)

        if sentinela:
            texto = re.sub(
                r"(- Sentinela:.*)",
                f"- Sentinela: {sentinela}",
                texto,
            )
        if apk_versao:
            texto = re.sub(
                r"(- APK:.*)",
                f"- APK: {apk_versao}",
                texto,
            )

        # Atualiza última linha de sessão
        texto = re.sub(
            r"(- Sessão [\d/]+ .*)",
            f"- Sessão {datetime.now().strftime('%d/%m')} {resumo_sess[:80]}",
            texto,
        )

        SESSION_START.write_text(texto, encoding="utf-8")
        return AgentResult(
            agent=self.name,
            status="SUCCESS",
            summary="SESSION_START.md actualizado",
            details=[f"Data: {data_hoje}", f"Resumo: {resumo_sess[:60]}"],
        )

    # ------------------------------------------------------------------
    # Relatório de tamanho dos ficheiros de memória
    # ------------------------------------------------------------------
    def _report_memory_stats(self) -> AgentResult:
        stats = []
        total_bytes = 0

        ficheiros_chave = [
            SESSION_START,
            MEMORY_DIR / "00_INDEX.md",
            MEMORY_DIR / "11_known_issues_roadmap.md",
            MEMORY_DIR / "12_database_schema.md",
        ]

        for f in ficheiros_chave:
            if f.exists():
                sz = f.stat().st_size
                total_bytes += sz
                linhas = f.read_text(encoding="utf-8").count("\n")
                stats.append(f"{f.name}: {sz//1024}KB · {linhas} linhas")

        if DOMAINS_DIR.exists():
            for d in sorted(DOMAINS_DIR.glob("*.md")):
                sz = d.stat().st_size
                total_bytes += sz
                stats.append(f"  {d.name}: {sz//1024}KB")

        alerta = []
        if (MEMORY_DIR / "11_known_issues_roadmap.md").stat().st_size > 40_000:
            alerta.append("⚠ 11_known_issues_roadmap.md > 40KB — evitar carregar no arranque")

        return AgentResult(
            agent=self.name,
            status="SUCCESS",
            summary=f"Memória total: {total_bytes//1024}KB em {len(stats)} ficheiros",
            details=stats + alerta,
            data={"total_kb": total_bytes // 1024},
        )
