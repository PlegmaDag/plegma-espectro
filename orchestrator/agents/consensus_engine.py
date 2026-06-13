#!/usr/bin/env python3
"""
PLEGMA DAEMON — Consensus Engine
Tri-IA: Anthropic (Claude) + Google (Gemini) + xAI (Grok)
Decisões críticas requerem 2/3 de consenso antes de serem executadas.
Usado para: deploys, mudanças de código, acções irreversíveis.
"""

import sys
import json
import time
import hashlib
import requests
from pathlib import Path
from dataclasses import dataclass

sys.path.insert(0, str(Path(__file__).parent.parent))
from daemon_config import ANTHROPIC_KEY, GEMINI_KEY, GROQ_KEY
from . import BaseAgent, AgentResult
import event_log

_TIMEOUT = 30


@dataclass
class AIVote:
    model:   str
    vote:    str    # "APPROVE" | "REJECT" | "ABSTAIN"
    reason:  str
    confidence: float


def _extract_json(raw: str) -> dict:
    """Extrai JSON de respostas com ou sem code-fences markdown."""
    import re
    cleaned = re.sub(r'^```(?:json)?\s*', '', raw.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r'```\s*$', '', cleaned, flags=re.MULTILINE).strip()
    for candidate in (cleaned, raw):
        try:
            return json.loads(candidate)
        except Exception:
            pass
        match = re.search(r'\{[^{}]*"vote"\s*:[^{}]*\}', candidate, re.DOTALL)
        if not match:
            match = re.search(r'\{.*\}', candidate, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
    return {}


def _vote_claude(prompt: str) -> AIVote:
    if not ANTHROPIC_KEY:
        return AIVote("claude", "ABSTAIN", "API key não configurada", 0.0)
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            system=(
                "És um árbitro autónomo do projecto PLEGMA DAG. "
                "Regra: APPROVE se o estado descrito é aceitável/saudável, "
                "REJECT se há problemas críticos que exigem acção imediata, "
                "ABSTAIN apenas se a informação for completamente ininteligível. "
                "Responde SEMPRE em JSON válido: "
                "{\"vote\":\"APPROVE\"|\"REJECT\"|\"ABSTAIN\","
                "\"reason\":\"string concisa\",\"confidence\":0.0-1.0}. "
                "Critérios de aprovação: servidores activos, sem CRITICAL no sentinela, "
                "criptografia pós-quântica mantida."
            ),
            messages=[{"role": "user", "content": prompt}]
        )
        raw = msg.content[0].text.strip()
        data = _extract_json(raw)
        return AIVote(
            model="claude",
            vote=data.get("vote", "ABSTAIN"),
            reason=data.get("reason", raw[:200]),
            confidence=float(data.get("confidence", 0.5))
        )
    except Exception as e:
        return AIVote("claude", "ABSTAIN", str(e)[:100], 0.0)


def _vote_gemini(prompt: str) -> AIVote:
    if not GEMINI_KEY:
        return AIVote("gemini", "ABSTAIN", "API key não configurada", 0.0)
    try:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
        )
        system = (
            "És um árbitro autónomo do projecto PLEGMA DAG. "
            "APPROVE se estado é saudável, REJECT se há problemas críticos. "
            "Responde APENAS em JSON: {\"vote\":\"APPROVE\"|\"REJECT\"|\"ABSTAIN\","
            "\"reason\":\"string\",\"confidence\":0.0-1.0}"
        )
        body = {
            "contents": [{"parts": [{"text": f"{system}\n\nDECISÃO:\n{prompt}"}]}],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 512,
                                 "responseMimeType": "application/json"}
        }
        r    = requests.post(url, json=body, timeout=_TIMEOUT)
        resp = r.json()

        if "error" in resp:
            return AIVote("gemini", "ABSTAIN", f"API error: {resp['error'].get('message','?')[:80]}", 0.0)

        candidates = resp.get("candidates", [])
        if not candidates:
            return AIVote("gemini", "ABSTAIN", f"Sem candidatos: {str(resp)[:100]}", 0.0)

        raw = candidates[0]["content"]["parts"][0]["text"].strip()

        # Extracção robusta: 3 tentativas por ordem de fiabilidade
        data = {}
        # 1) Parse directo — responseMimeType=application/json deve devolver JSON puro
        try:
            data = json.loads(raw)
        except Exception:
            pass
        # 2) Remove markdown fences e tenta de novo
        if not data:
            import re
            cleaned = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
            cleaned = re.sub(r'```\s*$', '', cleaned, flags=re.MULTILINE).strip()
            try:
                data = json.loads(cleaned)
            except Exception:
                pass
        # 3) Extrai o objeto JSON que contém "vote" (mais específico que .*)
        if not data:
            import re
            match = re.search(r'\{[^{}]*"vote"\s*:[^{}]*\}', raw, re.DOTALL)
            if not match:
                match = re.search(r'\{.*\}', raw, re.DOTALL)
            try:
                data = json.loads(match.group()) if match else {}
            except Exception:
                data = {}

        # 4) Fallback: extrai vote/reason/confidence directamente do texto
        #    Trata JSON truncado (ex: {"vote": "APPROVE sem fechar)
        if not data:
            import re
            vote_m = re.search(r'"vote"\s*:\s*"(APPROVE|REJECT|ABSTAIN)', raw, re.IGNORECASE)
            reason_m = re.search(r'"reason"\s*:\s*"([^"]{0,200})', raw)
            conf_m = re.search(r'"confidence"\s*:\s*([0-9.]+)', raw)
            if vote_m:
                data = {
                    "vote": vote_m.group(1).upper(),
                    "reason": reason_m.group(1) if reason_m else raw[:100],
                    "confidence": float(conf_m.group(1)) if conf_m else 0.5,
                }

        return AIVote(
            model="gemini-2.5-flash",
            vote=data.get("vote", "ABSTAIN"),
            reason=data.get("reason", raw[:200]),
            confidence=float(data.get("confidence", 0.5))
        )
    except Exception as e:
        return AIVote("gemini", "ABSTAIN", str(e)[:100], 0.0)


def _vote_groq(prompt: str) -> AIVote:
    if not GROQ_KEY:
        return AIVote("groq", "ABSTAIN", "API key não configurada", 0.0)
    try:
        url  = "https://api.groq.com/openai/v1/chat/completions"
        body = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": (
                    "És um árbitro de decisões técnicas para o projecto PLEGMA DAG. "
                    "Responde APENAS em JSON: {\"vote\":\"APPROVE\"|\"REJECT\"|\"ABSTAIN\","
                    "\"reason\":\"string\",\"confidence\":0.0-1.0}. "
                    "Critérios: segurança pós-quântica, determinismo, sem redundância."
                )},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 300,
            "temperature": 0.1
        }
        r = requests.post(url, json=body,
                          headers={"Authorization": f"Bearer {GROQ_KEY}"},
                          timeout=_TIMEOUT)
        raw  = r.json()["choices"][0]["message"]["content"].strip()
        data = _extract_json(raw)
        return AIVote(
            model="groq/llama3.3-70b",
            vote=data.get("vote", "ABSTAIN"),
            reason=data.get("reason", raw[:200]),
            confidence=float(data.get("confidence", 0.5))
        )
    except Exception as e:
        return AIVote("groq", "ABSTAIN", str(e)[:100], 0.0)


def reach_consensus(decision_prompt: str, context: str = "") -> dict:
    """
    Submete uma decisão às 3 IAs e calcula consenso 2/3.
    Retorna: {approved: bool, votes: [...], reason: str, hash: str}
    """
    full_prompt = f"{context}\n\nDECISÃO A AVALIAR:\n{decision_prompt}" if context else decision_prompt

    votes = [
        _vote_claude(full_prompt),
        _vote_gemini(full_prompt),
        _vote_groq(full_prompt),
    ]

    approvals = sum(1 for v in votes if v.vote == "APPROVE")
    rejections = sum(1 for v in votes if v.vote == "REJECT")
    approved  = approvals >= 2  # maioria de 3

    decision_hash = hashlib.sha256(
        (decision_prompt + str(time.time())).encode()
    ).hexdigest()[:16]

    result = {
        "approved":    approved,
        "approvals":   approvals,
        "rejections":  rejections,
        "abstentions": 3 - approvals - rejections,
        "votes":       [{"model": v.model, "vote": v.vote, "reason": v.reason,
                         "confidence": v.confidence} for v in votes],
        "hash":        decision_hash,
        "ts":          time.time(),
    }

    status = "APPROVED" if approved else "REJECTED"
    event_log.log("consensus", "decision", status,
                  f"[{decision_hash}] {approvals}/3 APPROVE: {decision_prompt[:100]}",
                  result)

    return result


class ConsensusEngineAgent(BaseAgent):
    name = "consensus_engine"

    def _execute(self, task: str, context: dict) -> AgentResult:
        prompt = context.get("decision_prompt", task)
        ctx    = context.get("context", "")

        result = reach_consensus(prompt, ctx)

        details = [
            f"Hash decisão: {result['hash']}",
            f"Resultado: {'✅ APROVADO' if result['approved'] else '❌ REJEITADO'}",
            f"Votos: {result['approvals']} APPROVE · {result['rejections']} REJECT · {result['abstentions']} ABSTAIN",
        ]
        for v in result["votes"]:
            conf = f"{v['confidence']*100:.0f}%"
            details.append(f"  · {v['model']:8} [{v['vote']:7}] conf={conf} — {v['reason'][:80]}")

        status = "SUCCESS" if result["approved"] else "FAILURE"
        summary = f"Consenso {'APROVADO' if result['approved'] else 'REJEITADO'} ({result['approvals']}/3 IAs)"

        return AgentResult(
            agent=self.name, status=status, summary=summary,
            details=details, data=result
        )
