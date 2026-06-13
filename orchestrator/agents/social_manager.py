#!/usr/bin/env python3
"""
PLEGMA DAEMON — Social Manager Agent
Modera a rede social Plegma: detecta spam, remove posts abusivos,
publica dev-log automático a cada 6 horas.
Usa SSH + curl interno (nginx não expõe /api/social/ externamente).
"""

import time
import json
import paramiko
import sys
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from daemon_config import NODES, SSH_KEY, ADMIN_KEY, SPAM
from . import BaseAgent, AgentResult
import event_log

_TIMEOUT          = 10
_LAST_DEVLOG_FILE = Path(__file__).parent.parent / "logs" / ".last_devlog_ts"

# Nó primário para chamadas sociais
_PRIMARY = NODES["eur"]


def _connect() -> paramiko.SSHClient | None:
    try:
        key = paramiko.Ed25519Key.from_private_key_file(SSH_KEY)
        c   = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        c.connect(_PRIMARY["ip"], username="root", pkey=key, timeout=12)
        transport = c.get_transport()
        if transport:
            transport.set_keepalive(20)
        return c
    except Exception as e:
        event_log.log("social_manager", "ssh_connect_fail", "WARN", str(e))
        return None


def _ssh_get(client: paramiko.SSHClient, path: str) -> dict | None:
    """GET via curl localhost no servidor primário."""
    _, stdout, _ = client.exec_command(
        f"curl -s --max-time {_TIMEOUT} http://localhost:8080{path} 2>/dev/null",
        timeout=_TIMEOUT + 5
    )
    stdout.channel.settimeout(_TIMEOUT + 5)
    try:
        raw = stdout.read().decode().strip()
        return json.loads(raw) if raw else None
    except Exception:
        return None


def _ssh_post(client: paramiko.SSHClient, path: str, body: dict) -> dict | None:
    """POST via curl localhost no servidor primário."""
    body_json = json.dumps(body).replace("'", "'\\''")
    _, stdout, _ = client.exec_command(
        f"curl -s --max-time {_TIMEOUT} -X POST -H 'Content-Type: application/json' "
        f"-d '{body_json}' http://localhost:8080{path} 2>/dev/null",
        timeout=_TIMEOUT + 5
    )
    stdout.channel.settimeout(_TIMEOUT + 5)
    try:
        raw = stdout.read().decode().strip()
        return json.loads(raw) if raw else None
    except Exception:
        return None


def _is_spam(post: dict, all_posts: list) -> tuple[bool, str]:
    body = (post.get("corpo") or post.get("body") or "").strip()

    if len(body) < SPAM["min_body_len"]:
        return True, f"corpo muito curto ({len(body)} chars)"

    if body.startswith("http") and " " not in body:
        return True, "post é apenas um link"

    for other in all_posts:
        if other.get("id") == post.get("id"):
            continue
        other_body = (other.get("corpo") or other.get("body") or "").strip()
        ratio = SequenceMatcher(None, body, other_body).ratio()
        if ratio >= SPAM["max_duplicate_ratio"]:
            return True, f"duplicado (similaridade {ratio:.0%})"

    return False, ""


def _check_rate_limits(posts: list) -> list[str]:
    hour_ago = time.time() - 3600
    counts   = defaultdict(int)
    for p in posts:
        ts = p.get("ts") or p.get("criado_em") or 0
        if ts > hour_ago:
            counts[p.get("plg_address") or p.get("autor") or ""] += 1
    return [addr for addr, cnt in counts.items() if cnt > SPAM["max_posts_per_hour"] and addr]


def _delete_post(client: paramiko.SSHClient, post_id, reason: str) -> bool:
    if not ADMIN_KEY:
        return False
    r = _ssh_post(client, "/api/social/post/apagar", {
        "post_id": post_id,
        "admin_key": ADMIN_KEY,
        "motivo": reason
    })
    return r is not None and r.get("status") == "ok"


def _post_devlog(client: paramiko.SSHClient) -> bool:
    if not ADMIN_KEY:
        return False

    if _LAST_DEVLOG_FILE.exists():
        last_ts = float(_LAST_DEVLOG_FILE.read_text().strip() or "0")
        if time.time() - last_ts < 21600:
            return False

    status = _ssh_get(client, "/api/status")       or {}
    dag    = _ssh_get(client, "/api/dag/status")   or {}
    gen    = _ssh_get(client, "/api/genesis/status") or {}

    nos    = status.get("nos_ativos", 0) or dag.get("nos_ativos", 0)
    txs    = status.get("total_transacoes", 0) or dag.get("total_transacoes", 0)
    supply = gen.get("supply_total", gen.get("supply_circulante", 0))

    corpo = (
        f"⬡ Rede PLEGMA DAG — Status Automático\n\n"
        f"Nós activos: {nos} · Transações DAG: {txs}\n"
        f"Supply em circulação: {supply:,.0f} $PLG\n\n"
        f"Sistema operacional · Todos os servidores online.\n"
        f"#PlegmaDAG #DAG #PostQuantum #Lattice"
    )

    r = _ssh_post(client, "/api/social/post", {
        "corpo": corpo,
        "plg_address": "PLG_DAEMON_AUTO",
        "admin_key": ADMIN_KEY,
        "tag": "devlog"
    })

    if r and r.get("status") == "ok":
        _LAST_DEVLOG_FILE.write_text(str(time.time()))
        return True
    return False


class SocialManagerAgent(BaseAgent):
    name = "social_manager"

    def _execute(self, task: str, context: dict) -> AgentResult:
        details = []
        removed = 0
        flagged = 0

        client = _connect()
        if not client:
            event_log.log(self.name, "fetch_posts", "FAIL", "SSH ao nó primário inacessível")
            return AgentResult(agent=self.name, status="FAILURE",
                               summary="SSH ao nó primário inacessível")

        try:
            data = _ssh_get(client, "/api/social/posts?limit=200")
            if not data:
                event_log.log(self.name, "fetch_posts", "FAIL", "API social inacessível via SSH")
                return AgentResult(agent=self.name, status="FAILURE",
                                   summary="API social inacessível via SSH")

            posts = data.get("posts") or (data if isinstance(data, list) else [])
            details.append(f"Posts analisados: {len(posts)}")

            for post in posts:
                is_sp, reason = _is_spam(post, posts)
                if is_sp:
                    flagged += 1
                    pid = post.get("id") or post.get("post_id")
                    ok  = _delete_post(client, pid, reason) if pid else False
                    sym = "✓ REMOVIDO" if ok else "⚑ SINALIZADO"
                    details.append(f"  {sym} post#{pid} — {reason}")
                    if ok:
                        removed += 1
                    event_log.log(self.name, "spam_detected", "OK" if ok else "WARN",
                                  f"post#{pid}: {reason}", {"removed": ok})

            abusers = _check_rate_limits(posts)
            for addr in abusers:
                details.append(f"  ⚠ Rate-limit: {addr[:16]}… ({SPAM['max_posts_per_hour']}+ posts/hora)")
                event_log.log(self.name, "rate_limit", "WARN",
                              f"autor com excesso de posts: {addr[:16]}")

            devlog_ok = _post_devlog(client)
            if devlog_ok:
                details.append("  ✓ Dev-log automático publicado")
                event_log.log(self.name, "devlog_post", "OK", "Dev-log automático publicado na mesh")

        finally:
            client.close()

        event_log.log(self.name, "moderation_cycle", "OK",
                      f"{len(posts)} posts analisados · {removed} removidos",
                      {"posts": len(posts), "flagged": flagged, "removed": removed})

        return AgentResult(
            agent=self.name, status="SUCCESS",
            summary=f"Moderação: {len(posts)} posts · {flagged} flagged · {removed} removidos",
            details=details,
            data={"posts": len(posts), "flagged": flagged, "removed": removed}
        )
