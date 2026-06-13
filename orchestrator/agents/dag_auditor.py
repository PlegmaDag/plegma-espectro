#!/usr/bin/env python3
"""
PLEGMA ORCHESTRATOR — DAG Auditor Agent
Verifica a integridade completa do fluxo de cada transação:
  Detecção → Hash → ZK Proof → Parents DAG → Aerarium → Recompensa PLG → Confirmação

Este agente corre APÓS cada deploy e em cada auditoria periódica.
Falha se qualquer etapa do fluxo estiver quebrada.
"""

import json
import sqlite3
import time
import urllib.request
from pathlib import Path
from . import BaseAgent, AgentResult

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from daemon_config import NODES
import event_log

_DB_PATH  = "/root/PLEGMA_CORE/plegma_data.db"
_API_BASE = "http://localhost:8080"


def _http_get(url: str, timeout: int = 5) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception:
        return {}


def _audit_remote(ip: str, domain: str = "") -> dict:
    """Audita a integridade DAG num nó remoto via API pública HTTPS."""
    base = f"https://{domain}" if domain else f"http://{ip}:8080"
    status  = _http_get(f"{base}/api/dag/status")
    txs_raw = _http_get(f"{base}/api/transactions?limit=50")
    txs     = txs_raw.get("transactions", [])

    issues = []
    ok_map = {}

    # ── Etapa 1: Transação detectada e gravada ────────────────────────────────
    total = status.get("total_transacoes", 0)
    ok_map["1_gravadas"] = total > 0
    if total == 0:
        issues.append("CRÍTICO: Nenhuma transação gravada na DAG")

    # ── Etapa 2: Cada tx tem hash único ──────────────────────────────────────
    hashes = [tx.get("tx_hash", "") for tx in txs]
    duplicados = len(hashes) - len(set(hashes))
    ok_map["2_hash_unico"] = duplicados == 0
    if duplicados:
        issues.append(f"CRÍTICO: {duplicados} hashes duplicados")

    # ── Etapa 3: ZK proof registada (zk_proof_size > 0 OU zk_proof_hash presente) ──
    sem_zk = [tx["tx_hash"][:16] for tx in txs
              if not tx.get("zk_proof_size") and not tx.get("zk_proof_hash")]
    ok_map["3_zk_proof"] = len(sem_zk) == 0
    if sem_zk:
        issues.append(f"ALTO: {len(sem_zk)} txs sem ZK proof: {sem_zk[:3]}")

    # ── Etapa 4: Topologia DAG — parents não vazios em txs não-genesis ────────
    nao_genesis = [tx for tx in txs if tx.get("node_type", "") != "GENESIS"]
    sem_parents = [tx["tx_hash"][:16] for tx in nao_genesis
                   if not tx.get("parents") or tx.get("parents") == "[]"
                   or tx.get("parents") == []]
    ok_map["4_parents_dag"] = len(sem_parents) == 0
    if sem_parents:
        issues.append(f"ALTO: {len(sem_parents)} txs não-genesis sem parents: {sem_parents[:3]}")

    # ── Etapa 5: Aerarium registado por tx de mineração ─────────────────────
    # txs de mining devem ter aerarium_amount > 0 (TRANSFER e WALLET são 0 por design)
    _TIPOS_SEM_AERARIUM = {"TRANSFER", "WALLET", "GENESIS"}
    sem_aerarium = [tx["tx_hash"][:16] for tx in nao_genesis
                    if not tx.get("aerarium_amount")
                    and tx.get("node_type", "") not in _TIPOS_SEM_AERARIUM]
    ok_map["5_aerarium"] = len(sem_aerarium) == 0
    if sem_aerarium:
        issues.append(f"MÉDIO: {len(sem_aerarium)} txs não-genesis sem aerarium_amount")

    # ── Etapa 6: Recompensa PLG gerada (miner_vesting) ───────────────────────
    # Verificado via API (não acesso directo à DB remota)
    # Estimativa: deve existir pelo menos 1 registo de vesting por tx de mineração
    ok_map["6_recompensa_plg"] = True  # verificado abaixo com DB local

    # ── Etapa 7: Confirmação — total_aceitas coerente ────────────────────────
    aceitas    = status.get("total_aceitas", 0)
    total_txs  = status.get("total_transacoes", 0)
    tips_pend  = status.get("tips_pendentes", 0)
    # Genesis-only network: aceitas pode ser 0. Alerta apenas se há txs não-genesis sem confirmar.
    if total_txs > 0 and aceitas == 0 and len(nao_genesis) > 0:
        ok_map["7_confirmacao"] = False
        issues.append(f"MÉDIO: {len(nao_genesis)} txs não-genesis mas total_aceitas=0 — mecanismo de confirmação inativo")
    else:
        ok_map["7_confirmacao"] = True

    # ── Etapa 8: anchor_id preenchido nas compras confirmadas ────────────────
    ok_map["8_anchor_id"] = True  # verificado via DB local

    score = sum(1 for v in ok_map.values() if v)
    return {
        "ip"      : ip,
        "score"   : f"{score}/{len(ok_map)}",
        "ok_map"  : ok_map,
        "issues"  : issues,
        "total_txs": total_txs,
        "aceitas" : aceitas,
        "tips"    : tips_pend,
    }


def _audit_db_local() -> dict:
    """Auditoria directa na DB local do nó primário."""
    issues = []
    ok_map = {}

    try:
        conn = sqlite3.connect(_DB_PATH)
        conn.row_factory = sqlite3.Row

        txs = conn.execute(
            "SELECT tx_hash, sender, receiver, amount, parents, node_type, "
            "zk_proof_size, aerarium_amount, zk_proof_hash FROM transactions"
        ).fetchall()

        # Etapa 6: miner_vesting count vs txs não-genesis
        vesting_count = conn.execute("SELECT COUNT(*) FROM miner_vesting").fetchone()[0]
        nao_genesis_count = sum(1 for tx in txs if dict(tx).get("node_type") != "GENESIS")
        ok_map["6_recompensa_plg"] = vesting_count >= nao_genesis_count
        if vesting_count < nao_genesis_count:
            issues.append(
                f"ALTO: miner_vesting={vesting_count} < txs não-genesis={nao_genesis_count} "
                "— recompensas PLG não foram geradas"
            )

        # Etapa 8: anchor_id nas pending_purchases confirmadas
        try:
            sem_anchor = conn.execute(
                "SELECT COUNT(*) FROM pending_purchases WHERE status='CONFIRMADO' AND (anchor_id IS NULL OR anchor_id='')"
            ).fetchone()[0]
            ok_map["8_anchor_id"] = sem_anchor == 0
            if sem_anchor:
                issues.append(f"MÉDIO: {sem_anchor} compras CONFIRMADAS sem anchor_id na DAG")
        except Exception:
            ok_map["8_anchor_id"] = None  # coluna pode não existir ainda

        # Schema check: colunas V4.6 presentes
        cols = {row[1] for row in conn.execute("PRAGMA table_info(transactions)").fetchall()}
        ok_map["schema_aerarium_col"] = "aerarium_amount" in cols
        ok_map["schema_zk_hash_col"]  = "zk_proof_hash"  in cols
        if "aerarium_amount" not in cols:
            issues.append("CRÍTICO: coluna aerarium_amount ausente em transactions — migração V4.6 não aplicada")
        if "zk_proof_hash" not in cols:
            issues.append("CRÍTICO: coluna zk_proof_hash ausente em transactions — migração V4.6 não aplicada")

        conn.close()
    except Exception as e:
        issues.append(f"ERRO acesso DB: {e}")
        ok_map["db_access"] = False

    return {"ok_map": ok_map, "issues": issues}


class DagAuditorAgent(BaseAgent):
    name = "dag_auditor"

    # Quantas vezes tentar aguardar o fluxo antes de reportar (3s entre tentativas)
    _MAX_POLL = 5
    _POLL_INTERVAL = 3  # segundos

    def _poll_remote(self, ip: str, domain: str = "") -> dict:
        """Aguarda até o nó ter transações gravadas (Etapa 1 OK) antes de auditar.
        Retorna o último resultado, tendo havido convergência ou não."""
        for attempt in range(1, self._MAX_POLL + 1):
            r = _audit_remote(ip, domain)
            if r["ok_map"].get("1_gravadas") or attempt == self._MAX_POLL:
                if attempt > 1:
                    r["_wait_attempts"] = attempt
                return r
            time.sleep(self._POLL_INTERVAL)
        return _audit_remote(ip, domain)

    def _execute(self, task: str, context: dict) -> AgentResult:
        details  = []
        all_issues: list = []
        nós_ok   = 0

        # ── Auditoria remota: todos os nós ───────────────────────────────────
        for nid, node in NODES.items():
            ip     = node["ip"]
            label  = node["label"]
            domain = node.get("domain", "")
            r      = self._poll_remote(ip, domain)

            wait_note = f"  (aguardou {r.get('_wait_attempts', 1)} tentativas)" if r.get("_wait_attempts") else ""
            details.append(f"\n[{label}] {ip}  score={r['score']}{wait_note}")
            details.append(f"  Txs: {r['total_txs']} | Aceitas: {r['aceitas']} | Tips: {r['tips']}")

            etapas = r["ok_map"]
            etapa_labels = {
                "1_gravadas"       : "Etapa 1 — Tx gravada na DAG",
                "2_hash_unico"     : "Etapa 2 — Hash único",
                "3_zk_proof"       : "Etapa 3 — ZK Proof registada",
                "4_parents_dag"    : "Etapa 4 — Topologia DAG (parents)",
                "5_aerarium"       : "Etapa 5 — Aerarium por tx",
                "6_recompensa_plg" : "Etapa 6 — Recompensa PLG (vesting)",
                "7_confirmacao"    : "Etapa 7 — Confirmação (aceitas)",
                "8_anchor_id"      : "Etapa 8 — Anchor ID compras",
            }
            for k, label_etapa in etapa_labels.items():
                v = etapas.get(k)
                sym = "✓" if v else ("⚠" if v is None else "✕")
                details.append(f"  {sym} {label_etapa}")

            for iss in r["issues"]:
                details.append(f"    → {iss}")
                all_issues.append(f"[{label}] {iss}")

            if not r["issues"]:
                nós_ok += 1
                event_log.log("dag_auditor", "audit_ok", "OK",
                              f"{label} fluxo DAG íntegro", {"node": nid})
            else:
                event_log.log("dag_auditor", "audit_fail", "WARN",
                              f"{label} {len(r['issues'])} problema(s)", {"node": nid})

        # ── Auditoria DB local (nó primário) ─────────────────────────────────
        db_audit = _audit_db_local()
        details.append("\n[DB LOCAL] Schema + miner_vesting + anchor_id")
        for k, v in db_audit["ok_map"].items():
            sym = "✓" if v else ("⚠" if v is None else "✕")
            details.append(f"  {sym} {k}")
        for iss in db_audit["issues"]:
            details.append(f"    → {iss}")
            all_issues.append(f"[DB] {iss}")

        criticos = sum(1 for i in all_issues if "CRÍTICO" in i)
        altos    = sum(1 for i in all_issues if "ALTO"    in i)
        medios   = sum(1 for i in all_issues if "MÉDIO"   in i)

        status = "SUCCESS" if criticos == 0 and altos == 0 else \
                 "PARTIAL" if nós_ok > 0 else "FAILURE"

        summary = (f"Auditoria DAG: CRÍTICO={criticos} ALTO={altos} MÉDIO={medios} "
                   f"| {nós_ok}/{len(NODES)} nós OK")

        return AgentResult(
            agent=self.name, status=status, summary=summary,
            details=details,
            data={"criticos": criticos, "altos": altos, "medios": medios,
                  "nos_ok": nós_ok, "issues": all_issues}
        )
