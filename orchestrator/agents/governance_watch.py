#!/usr/bin/env python3
"""
PLEGMA DAEMON — Governance Watch Agent
Monitora estado de governança, propostas Labs, threshold de activação.
Alerta quando limites são atingidos.
"""

import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from daemon_config import API_PRIMARY
from . import BaseAgent, AgentResult
import event_log

_TIMEOUT = 10

GOVERNANCE_THRESHOLD = 0.66   # 66% para activação de proposta
MATURITY_DAYS        = 30     # dias mínimos para maturidade


def _get(path: str) -> dict | None:
    try:
        r = requests.get(f"{API_PRIMARY}{path}", timeout=_TIMEOUT)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


class GovernanceWatchAgent(BaseAgent):
    name = "governance_watch"

    def _execute(self, task: str, context: dict) -> AgentResult:
        details = []
        alerts  = 0

        # 1. Estado geral de governança
        gov = _get("/api/genesis/governance")
        if gov:
            activa      = gov.get("governance_active", False)
            threshold   = gov.get("threshold_pct", 0)
            total_socios = gov.get("total_socios", 0)
            details.append(f"Governança: {'ACTIVA' if activa else 'INACTIVA'}")
            details.append(f"  Threshold atingido: {threshold:.1f}% de {total_socios} sócios")
            if not activa and threshold >= GOVERNANCE_THRESHOLD * 100:
                alerts += 1
                details.append(f"  ⚠ ALERTA: threshold {threshold:.0f}% ≥ {GOVERNANCE_THRESHOLD*100:.0f}% — governança pronta para activar")
                event_log.log(self.name, "governance_threshold", "WARN",
                              f"Threshold {threshold:.1f}% atingido mas governança inactiva",
                              {"threshold": threshold, "total_socios": total_socios})
        else:
            details.append("  ✕ API governança inacessível")

        # 2. Maturidade de rede
        maturity = _get("/api/governance/maturity")
        if maturity:
            days     = maturity.get("days_active", 0)
            mature   = maturity.get("is_mature", False)
            details.append(f"Maturidade: {days} dias {'(MATURA ✓)' if mature else f'(faltam {max(0,MATURITY_DAYS-days)} dias)'}")
            if days >= MATURITY_DAYS and not mature:
                alerts += 1
                event_log.log(self.name, "maturity_check", "WARN",
                              f"Rede com {days} dias mas flag is_mature=False")

        # 3. Propostas Labs
        propostas_data = _get("/api/labs/propostas")
        if propostas_data:
            propostas = propostas_data if isinstance(propostas_data, list) \
                        else propostas_data.get("propostas", [])
            abertas   = [p for p in propostas if p.get("status") == "aberta"]
            details.append(f"Propostas Labs: {len(propostas)} total · {len(abertas)} abertas")

            for p in abertas:
                votos_sim = p.get("votos_sim", 0)
                votos_nao = p.get("votos_nao", 0)
                total_v   = votos_sim + votos_nao
                ratio     = votos_sim / total_v if total_v > 0 else 0
                pct       = ratio * 100
                details.append(f"  · #{p.get('id')} {p.get('titulo','?')[:40]} — {pct:.0f}% aprovação ({total_v} votos)")

                if ratio >= GOVERNANCE_THRESHOLD and total_v >= 5:
                    alerts += 1
                    details.append(f"    ⚠ PROPOSTA APROVÁVEL — {pct:.0f}% ≥ {GOVERNANCE_THRESHOLD*100:.0f}%")
                    event_log.log(self.name, "proposal_threshold", "WARN",
                                  f"Proposta #{p.get('id')} com {pct:.0f}% aprovação",
                                  {"proposta_id": p.get("id"), "pct": pct})
        else:
            details.append("  ✕ API propostas inacessível")

        # 4. Status supply
        gen = _get("/api/genesis/status")
        if gen:
            supply   = gen.get("supply_circulante", 0)
            max_sup  = 21_000_000_000
            pct_emitido = (supply / max_sup) * 100
            details.append(f"Supply: {supply:,.0f} $PLG ({pct_emitido:.3f}% de 21B)")

        event_log.log(self.name, "governance_cycle", "OK" if alerts == 0 else "WARN",
                      f"Ciclo de governança: {alerts} alertas", {"alerts": alerts})

        status = "SUCCESS" if alerts == 0 else "PARTIAL"
        return AgentResult(
            agent=self.name, status=status,
            summary=f"Governança verificada · {alerts} alertas activos",
            details=details,
            data={"alerts": alerts}
        )
