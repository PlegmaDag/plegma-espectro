"""
=============================================================================
  TX VERIFIER — Interceptador Centralizado Pós-Quântico
  PLEGMA DAG V4.0 (NÍVEL 3 NIST)
=============================================================================
  Diretriz de Segurança (Hard Fail):
    - Hegemonia BLAKE3 (hashlib banido).
    - Assinaturas estritas Lattice (Dilithium3 / ML-DSA-65).
    - Rebaixamento criptográfico terminantemente proibido.
=============================================================================
"""

import base64
import logging
import plegma_db

_log = logging.getLogger(__name__)

# ── 1. Blindagem de Motor Pós-Quântico (Hard Fail) ────────────
try:
    from dilithium_py.dilithium import Dilithium3
    _ENGINE = Dilithium3
except ImportError:
    try:
        from dilithium_py.ml_dsa import ML_DSA_65
        _ENGINE = ML_DSA_65
    except ImportError:
        raise RuntimeError(
            "[FALHA FATAL] dilithium-py não encontrado. "
            "O nó recusa a inicialização fora da matriz segura Pós-Quântica."
        )

# ── 2. Blindagem de Oráculo Determinístico (Hard Fail) ─────────
try:
    import blake3 as _b3
except ImportError:
    raise RuntimeError(
        "[FALHA FATAL] Módulo blake3 ausente. "
        "A verificação de assinaturas exige determinismo via oráculo BLAKE3."
    )

def _hash(data: bytes) -> str:
    return _b3.blake3(data).hexdigest()

def _derivar_endereco(public_key: bytes) -> str:
    """Deriva o endereço PLG determinístico: PLG + BLAKE3(pk)[:40]"""
    return "PLG" + _hash(public_key)[:40].upper()

# ═══════════════════════════════════════════════════════════════════════════════
# AUDITORIA E VERIFICAÇÃO DE GRADE
# ═══════════════════════════════════════════════════════════════════════════════

def verificar_tx(sender: str, public_key_hex: str, signature: str,
                 mensagem: str) -> tuple[bool, str]:
    """
    Auditoria criptográfica de transação (Dilithium3 + BLAKE3).
    """
    try:
        public_key = bytes.fromhex(public_key_hex)
    except (ValueError, TypeError):
        return False, "Rejeição: Formato de chave pública corrompido."

    if len(public_key) != 1952:
        return False, f"Rejeição: Matriz de chave inválida ({len(public_key)} bytes). Requer 1952 bytes."

    endereco_esperado = _derivar_endereco(public_key)
    if endereco_esperado != sender:
        _log.info(f"[SYS_VERIFIER] Falha de Binding: Esperado {endereco_esperado[:16]}... Recebido {sender[:16]}...")
        return False, "Rejeição: Divergência de integridade entre chave pública e endereço emissor."

    try:
        try:
            sig_bytes = base64.b64decode(signature)
        except Exception:
            sig_bytes = bytes.fromhex(signature)

        msg_bytes = mensagem.encode("utf-8")
        valido    = _ENGINE.verify(public_key, msg_bytes, sig_bytes)
        
        if not valido:
            return False, "Rejeição: Assinatura Pós-Quântica (Dilithium3) inválida."
        return True, "OK"

    except Exception as e:
        _log.info(f"[SYS_VERIFIER] Colisão na decodificação de assinatura: {type(e).__name__}")
        return False, "Rejeição: Erro estrutural ao auditar assinatura."

def verificar_sessao_header(headers, required_address: str = None) -> tuple[bool, str]:
    """
    Valida o canal de estado (Token BLAKE3) via header HTTP.
    """
    auth = headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return False, "Rejeição: Canal de autorização ausente ou mal formado."

    parts = auth[7:].split(":", 1)
    if len(parts) != 2:
        return False, "Rejeição: Estrutura de token corrompida. Padrão: Bearer <address>:<token>"

    plg_address, token = parts
    if required_address and plg_address != required_address:
        return False, "Rejeição: Conflito de identidade no canal de sessão."

    if not plegma_db.validar_sessao(plg_address, token):
        return False, "Rejeição: Sessão expirada ou não reconhecida."

    return True, plg_address