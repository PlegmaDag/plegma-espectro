#!/usr/bin/env python3
"""
PLEGMA ORCHESTRATOR — Domain Loader
Carrega contexto de domínio ON DEMAND baseado na tarefa.
Princípio: lazy-load — zero contexto irrelevante em memória.
"""

from pathlib import Path

_DOMAINS_DIR = Path(__file__).parent.parent / "PROJECT_MEMORY" / "domains"

# Mapa de palavras-chave → ficheiro de domínio
_DOMAIN_MAP = {
    "D01": {
        "file": "D01_core_dag.md",
        "keywords": {
            "dag", "core", "mine", "mining", "consenso", "gossip",
            "heartbeat", "vertice", "vertex", "peer", "rede", "fase",
            "testnet", "mainnet", "nó", "nos", "âncora", "ancora",
            "core_api", "core_dag", "plegma_db", "network_phase"
        }
    },
    "D02": {
        "file": "D02_auth.md",
        "keywords": {
            "auth", "autenticação", "autenticacao", "qr", "dilithium",
            "sessão", "sessao", "session", "challenge", "verify", "login",
            "chave", "key", "lattice_shield", "auth_server", "token",
            "assinatura", "signature", "ml_dsa", "ml-dsa"
        }
    },
    "D03": {
        "file": "D03_wallet_dashboard.md",
        "keywords": {
            "wallet", "carteira", "saldo", "extrato", "transferir",
            "pool", "swap", "prover", "dashboard", "vesting", "plg",
            "wallet_server", "aerarium_swap", "transferência", "transfer"
        }
    },
    "D04": {
        "file": "D04_admin_console.md",
        "keywords": {
            "admin", "console", "sócio", "socio", "socios", "gauge",
            "gauges", "âncora", "ancora", "download", "aba", "roteiro",
            "painel", "panel", "mestre"
        }
    },
    "D05": {
        "file": "D05_genesis_tokenomics.md",
        "keywords": {
            "genesis", "plg-g", "plgg", "aerarium", "burn", "queima",
            "supply", "tier", "master", "sentinela", "apoiador",
            "liquidity", "liquidez", "tokenomics", "vesting", "boost",
            "governança", "governanca", "governance"
        }
    },
    "D06": {
        "file": "D06_fundacao.md",
        "keywords": {
            "fundação", "fundacao", "inscrição", "inscricao", "aprovar",
            "rejeitar", "instituição", "instituicao", "projecto", "projeto",
            "fundacao_registros", "inscricoes"
        }
    },
    "D07": {
        "file": "D07_social_mesh.md",
        "keywords": {
            "social", "mesh", "post", "feed", "perfil", "profile",
            "avatar", "votar", "comentar", "social_db", "mesh-social"
        }
    },
    "D08": {
        "file": "D08_flutter_app.md",
        "keywords": {
            "flutter", "app", "dart", "apk", "mobile", "screen",
            "provider", "service", "widget", "android", "ios",
            "boot_screen", "wallet_provider", "shield_screen", "seed"
        }
    },
    "D09": {
        "file": "D09_seguranca.md",
        "keywords": {
            "segurança", "seguranca", "security", "sentinela", "scan",
            "xss", "injection", "cve", "audit", "auditoria",
            "vulnerabilidade", "shield", "zk", "lattice", "blake3",
            "zk_press", "lattice_shield", "critico", "crítico"
        }
    },
}


def detect_domains(task: str) -> list[str]:
    """
    Detecta domínios relevantes para uma tarefa.
    Retorna lista de IDs de domínio ordenados por relevância.
    """
    tokens = set(task.lower().replace("-", "_").split())
    scores: dict[str, int] = {}

    for domain_id, cfg in _DOMAIN_MAP.items():
        score = len(tokens & cfg["keywords"])
        if score > 0:
            scores[domain_id] = score

    return sorted(scores, key=lambda d: scores[d], reverse=True)


def load_domain(domain_id: str) -> str:
    """
    Carrega o ficheiro de contexto de um domínio.
    Retorna string vazia se não encontrado.
    """
    cfg = _DOMAIN_MAP.get(domain_id)
    if not cfg:
        return ""

    path = _DOMAINS_DIR / cfg["file"]
    if not path.exists():
        return f"[AVISO] Ficheiro de domínio não encontrado: {path}"

    return path.read_text(encoding="utf-8")


def load_for_task(task: str, max_domains: int = 2) -> str:
    """
    Detecta domínios relevantes e carrega os contextos necessários.
    max_domains=2 evita carregar contexto excessivo em tarefas multi-domínio.
    Retorna contexto pronto para injectar no agente.
    """
    domains = detect_domains(task)[:max_domains]

    if not domains:
        return ""

    parts = []
    for d_id in domains:
        content = load_domain(d_id)
        if content:
            parts.append(content)

    return "\n\n---\n\n".join(parts) if parts else ""


def list_domains() -> list[dict]:
    """Lista todos os domínios disponíveis."""
    result = []
    for d_id, cfg in _DOMAIN_MAP.items():
        path = _DOMAINS_DIR / cfg["file"]
        result.append({
            "id":      d_id,
            "file":    cfg["file"],
            "exists":  path.exists(),
            "keywords_count": len(cfg["keywords"])
        })
    return result
