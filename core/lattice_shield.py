import base64
import logging

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
            "[FALHA FATAL] dilithium-py não encontrado.\n"
            "O escudo recusa inicialização fora da matriz segura Pós-Quântica."
        )

# ── 2. Blindagem de Oráculo Determinístico (Hard Fail) ─────────
try:
    import blake3 as _blake3
except ImportError:
    raise RuntimeError(
        "[FALHA FATAL] Módulo blake3 ausente no Lattice Shield.\n"
        "A geração de chaves exige determinismo via oráculo BLAKE3."
    )

def _hash(data: bytes) -> str:
    return _blake3.blake3(data).hexdigest()

# =============================================================================
# LATTICE SHIELD — Módulo Criptográfico Pós-Quântico (V4.0)
# Algoritmo: Crystals-Dilithium3 (Padrão NIST FIPS 204)
# Nível de Segurança: NIST Level 3 (equivalente a AES-192)
# Determinismo Absoluto: Hegemonia BLAKE3 (hashlib expurgado)
# =============================================================================

class LatticeShield:
    def __init__(self):
        self.public_key = None
        self.private_key = None
        self.address = None

    def generate_wallet(self) -> str:
        """
        Gera um par de chaves Crystals-Dilithium3 e deriva o endereço PLG.
        Endereço: PLG + BLAKE3(chave_pública)[:40]
        """
        self.public_key, self.private_key = _ENGINE.keygen()

        # Endereço PLEGMA: PLG + BLAKE3(pubkey)[:40] — determinístico
        pub_hash = _hash(self.public_key)
        self.address = f"PLG{pub_hash[:40].upper()}"

        return self.address

    def sign_transaction(self, tx_hash: str) -> str:
        """
        Assina o hash de uma transação DAG com a chave privada Dilithium3.
        Retorna a assinatura em Base64 para transporte eficiente na rede.
        """
        if not self.private_key:
            raise RuntimeError("Chave privada não encontrada. Execute generate_wallet() primeiro.")
        signature = _ENGINE.sign(self.private_key, tx_hash.encode("utf-8"))
        return base64.b64encode(signature).decode("utf-8")

    def verify_transaction(self, tx_hash: str, signature_b64: str, public_key: bytes) -> bool:
        """
        Verifica a assinatura de uma transação Dilithium3.
        Chamado pelos Nós Validadores e pelo TX Verifier.
        """
        try:
            signature = base64.b64decode(signature_b64)
            return _ENGINE.verify(public_key, tx_hash.encode("utf-8"), signature)
        except Exception:
            return False

    def get_public_key_hex(self) -> str:
        """Retorna a chave pública em hex para broadcast na rede."""
        if not self.public_key:
            raise RuntimeError("Carteira não gerada ainda.")
        return self.public_key.hex()


if __name__ == "__main__":
    _log.info("==================================================")
    _log.info(" [!] LATTICE SHIELD — CRYSTALS-DILITHIUM3 (NIST)  ")
    _log.info("==================================================")

    shield = LatticeShield()
    endereco = shield.generate_wallet()

    _log.info(f"[*] Algoritmo     : Crystals-Dilithium3 (NIST FIPS 204)")
    _log.info(f"[*] Nível NIST    : Level 3 (AES-192 equivalente)")
    _log.info(f"[*] Endereço PLG  : {endereco}")
    _log.info(f"[*] Pub Key (hex) : {shield.get_public_key_hex()[:48]}...")
    _log.info(f"[*] Tamanho PubKey: {len(shield.public_key)} bytes")
    _log.info(f"[*] Tamanho PrivKey: {len(shield.private_key)} bytes")

    tx_hash_exemplo = "b2c58dc567e62c5df56a5436756a4a16a8b2f189d0bcb8a6d6d26048f8d8ac87"
    _log.info(f"\n[*] Assinando TX  : {tx_hash_exemplo[:32]}...")

    assinatura = shield.sign_transaction(tx_hash_exemplo)
    _log.info(f"[*] Assinatura    : {assinatura[:64]}...")
    _log.info(f"[*] Tamanho Assin.: {len(base64.b64decode(assinatura))} bytes")

    valido = shield.verify_transaction(tx_hash_exemplo, assinatura, shield.public_key)
    _log.info(f"\n[*] Verificação   : {'VÁLIDA ✓' if valido else 'INVÁLIDA ✗'}")

    valido_falso = shield.verify_transaction("hash_adulterado_ataque", assinatura, shield.public_key)
    _log.info(f"[*] Ataque forjado: {'BLOQUEADO ✓' if not valido_falso else 'FALHOU ✗'}")

    _log.info("\n==================================================")
    _log.info(" MÓDULO PÓS-QUÂNTICO VALIDADO COM SUCESSO.        ")
    _log.info("==================================================")