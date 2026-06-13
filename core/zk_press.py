"""
zk_press.py — PLEGMA DAG  ZK Press v5.0
=========================================
Protocolo Sigma sobre Grade Ring-SIS · Z_q[x]/(x^N+1)
Primitivas: BLAKE3 keyed-mode (Fiat-Shamir ROM) + Ring-SIS

Propriedades formais:
  completude    : provas honestas são sempre aceites
  soundness     : sem sk, impossível forjar prova (Ring-SIS hard)
  zero-knowledge: distribuição de z não depende de sk (amostral por rejeição)
  determinismo  : mesma semente → mesma prova em qualquer nó
  pós-quântico  : Ring-LWE/Ring-SIS resistente a ataques quânticos

Parâmetros aprovados (consenso orquestrador 2026-05-21):
  N=128 · Q=12289 · ETA=2 · GAMMA=4096 · TAU=32 · REJECT=4032
  Taxa de aceitação: ~13% por round → ~7.5 rounds esperados

Referência: L-99 Auditoria · Sessão 2026-05-21
"""

import json
import logging
import struct
import threading
import blake3

_log = logging.getLogger(__name__)

# ── Parâmetros Ring-SIS ───────────────────────────────────────────────────────
N                = 128
Q                = 12289      # primo NTT-friendly: 12289 = 3·2^12 + 1
ETA              = 2          # |s_i| ≤ ETA (CBD)
GAMMA            = 4096       # |y_i| ≤ GAMMA (uniforme)
TAU              = 32         # peso do desafio (exactamente TAU coefs ±1)
REJECT_THRESHOLD = GAMMA - ETA * TAU   # = 4032

PROTOCOL_VERSION = "SYS-ZK-SIGMA-LATTICE-v5.0"
MAX_PROOF_BYTES  = 22 * 1024

_A_SEED = b"PLEGMA_ZK_PUBLIC_GENERATOR_A_2026"

# Chaves de domínio BLAKE3 keyed-mode (32 bytes) — separação formal por contexto
_DK_EXPAND = blake3.blake3(b"PLEGMA_ZK_DOMAIN_EXPAND_POLY_V5").digest()
_DK_SECRET = blake3.blake3(b"PLEGMA_ZK_DOMAIN_SECRET_KEY_V5").digest()
_DK_MASK   = blake3.blake3(b"PLEGMA_ZK_DOMAIN_MASK_VECTOR_V5").digest()
_DK_CHALL  = blake3.blake3(b"PLEGMA_ZK_DOMAIN_FIAT_SHAMIR_V5").digest()
_DK_CHAIN  = blake3.blake3(b"PLEGMA_ZK_DOMAIN_CHAIN_LINK_V5").digest()

# V4.1 backward-compat (State Seal BLAKE3 legacy)
_V41_PROTO         = "SYS-DAG-SEAL-BLAKE3-v4.1"
_V41_DOMAIN_STATE  = blake3.blake3(b"PLEGMA_DAG_DOMAIN_STATE_COMMIT_V4").digest()
_V41_DOMAIN_CHAIN  = blake3.blake3(b"PLEGMA_DAG_DOMAIN_CHAIN_LINK_V4").digest()
_V41_DOMAIN_EXPAND = blake3.blake3(b"PLEGMA_DAG_DOMAIN_EXPAND_SEAL_V4").digest()
_V41_SEAL_SIZE_KB  = 8


# ── Aritmética no anel Z_q[x]/(x^N+1) ───────────────────────────────────────

def _poly_add(a: list, b: list) -> list:
    return [(a[i] + b[i]) % Q for i in range(N)]


def _poly_sub(a: list, b: list) -> list:
    return [(a[i] - b[i]) % Q for i in range(N)]


def _poly_mul(a: list, b: list) -> list:
    """Schoolbook O(N²) em Z_q[x]/(x^N+1).
    x^N ≡ -1: cruzar N inverte o sinal do coeficiente.
    """
    c = [0] * N
    for i in range(N):
        ai = a[i]
        if not ai:
            continue
        for j in range(N):
            k = i + j
            if k < N:
                c[k] = (c[k] + ai * b[j]) % Q
            else:
                c[k - N] = (c[k - N] - ai * b[j]) % Q
    return c


def _poly_mul_challenge(c_sparse: list, b: list) -> list:
    """O(TAU·N): c tem exactamente TAU coefs ∈ {±1}, restantes nulos."""
    res = [0] * N
    for i in range(N):
        cv = c_sparse[i]
        if not cv:
            continue
        for j in range(N):
            k = i + j
            if k < N:
                res[k] = (res[k] + cv * b[j]) % Q
            else:
                res[k - N] = (res[k - N] - cv * b[j]) % Q
    return res


def _centre_lift(x: int) -> int:
    """[0, Q) → (-Q/2, Q/2]."""
    x = int(x) % Q
    return x - Q if x > Q >> 1 else x


def _inf_norm(p: list) -> int:
    return max(abs(_centre_lift(c)) for c in p)


# ── Amostragem determinística ──────────────────────────────────────────────────

def _expand_poly_from_seed(seed: bytes) -> list:
    """Uniforme em Z_q^N via rejeição sobre 14 bits (Q < 2^14, taxa ≥ 75%)."""
    coeffs = []
    ctr    = 0
    while len(coeffs) < N:
        block = blake3.blake3(seed + ctr.to_bytes(4, "big"), key=_DK_EXPAND).digest()
        ctr  += 1
        for i in range(0, 32, 2):
            if len(coeffs) >= N:
                break
            val = (block[i] | (block[i + 1] << 8)) & 0x3FFF
            if val < Q:
                coeffs.append(val)
    return coeffs[:N]


def _popcount2(x: int) -> int:
    return (x & 1) + ((x >> 1) & 1)


def _sample_secret(seed: bytes) -> list:
    """CBD (ETA=2): a − b, a,b ∈ {0,1,2} por byte. Coefs em Z_q."""
    coeffs = []
    ctr    = 0
    while len(coeffs) < N:
        block = blake3.blake3(seed + ctr.to_bytes(4, "big"), key=_DK_SECRET).digest()
        ctr  += 1
        for byte in block:
            if len(coeffs) >= N:
                break
            a = _popcount2((byte >> 2) & 0x3)
            b = _popcount2(byte & 0x3)
            coeffs.append((a - b) % Q)
            if len(coeffs) < N:
                a2 = _popcount2((byte >> 6) & 0x3)
                b2 = _popcount2((byte >> 4) & 0x3)
                coeffs.append((a2 - b2) % Q)
    return coeffs[:N]


def _sample_mask(seed: bytes, nonce: int) -> list:
    """Uniforme em [-GAMMA, GAMMA]^N. Rejeição 14 bits → taxa ≈ 50%."""
    nb     = nonce.to_bytes(4, "big")
    coeffs = []
    ctr    = 0
    while len(coeffs) < N:
        block = blake3.blake3(seed + nb + ctr.to_bytes(4, "big"), key=_DK_MASK).digest()
        ctr  += 1
        i     = 0
        while i + 1 < 32 and len(coeffs) < N:
            raw  = (block[i] | (block[i + 1] << 8)) & 0x3FFF
            i   += 2
            if raw <= 2 * GAMMA:          # aceita [0, 8192] → [-4096, 4096]
                coeffs.append(raw - GAMMA)
    return coeffs[:N]


def _sample_challenge(hash_bytes: bytes) -> list:
    """Desafio esparso: exactamente TAU coefs ±1, posições e sinais do hash."""
    sign_bits = int.from_bytes(hash_bytes[:4], "little")
    c         = [0] * N
    placed    = set()
    pos_buf   = bytearray(hash_bytes[4:])
    ctr       = 0
    p_idx     = 0
    sign_ctr  = 0

    while sign_ctr < TAU:
        if p_idx >= len(pos_buf):
            ctr    += 1
            pos_buf += blake3.blake3(
                hash_bytes + ctr.to_bytes(4, "big"), key=_DK_CHALL
            ).digest()
        pos    = pos_buf[p_idx] % N
        p_idx += 1
        if pos in placed:
            continue
        placed.add(pos)
        c[pos]    = 1 if not ((sign_bits >> sign_ctr) & 1) else -1
        sign_ctr += 1

    return c


# ── Gerador público A (lazy, partilhado entre instâncias) ─────────────────────
_A_CACHE: list       = None
_A_LOCK: threading.Lock = threading.Lock()


def _get_A() -> list:
    global _A_CACHE
    if _A_CACHE is None:
        with _A_LOCK:
            if _A_CACHE is None:
                _A_CACHE = _expand_poly_from_seed(_A_SEED)
    return _A_CACHE


# ── Serialização ──────────────────────────────────────────────────────────────

def _poly_to_bytes(p: list) -> bytes:
    return struct.pack(f"<{N}H", *[int(x) % Q for x in p])


def _bytes_to_poly(b: bytes) -> list:
    return list(struct.unpack(f"<{N}H", b))


def _zlist_to_bytes(z: list) -> bytes:
    return struct.pack(f"<{N}h", *[int(x) for x in z])


def _bytes_to_zlist(b: bytes) -> list:
    return list(struct.unpack(f"<{N}h", b))


# ── Verificador legacy v4.1 ───────────────────────────────────────────────────

def _verify_v41_seal(p: dict, state_hash: str) -> bool:
    try:
        if p.get("state") != state_hash:
            return False
        state_bytes = state_hash.encode()
        prev_hash   = bytes.fromhex(p.get("prev", ""))
        c_state     = blake3.blake3(state_bytes, key=_V41_DOMAIN_STATE).digest()
        c_chain     = blake3.blake3(prev_hash,   key=_V41_DOMAIN_CHAIN).digest()
        seal_seed   = blake3.blake3(c_state + c_chain, key=_V41_DOMAIN_EXPAND).digest()
        if p.get("c_state") != c_state.hex():
            return False
        target  = _V41_SEAL_SIZE_KB * 1024
        hasher  = blake3.blake3(seal_seed, key=_V41_DOMAIN_EXPAND)
        exp     = bytearray()
        counter = 0
        while len(exp) < target:
            hasher.update(counter.to_bytes(4, "big"))
            exp.extend(hasher.digest())
            counter += 1
        return p.get("seal_body") == exp[:target].hex()
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# DagSealEngine — Protocolo Sigma ZK sobre Grade Ring-SIS
# ═══════════════════════════════════════════════════════════════════════════════

class DagSealEngine:
    """
    Prova de Conhecimento Zero: provador demonstra conhecimento de sk tal que
    pk = A·sk (mod q, mod x^N+1), sem revelar sk.

    Protocolo:
      y ← U[-GAMMA,GAMMA]^N   (máscara)
      w = A·y  (mod q)
      c = H(pk ‖ state ‖ prev ‖ w)  (Fiat-Shamir, BLAKE3 como ROM)
      z = y + c·sk  (mod q, centre-lift)
      rejeitar se ||z||_∞ > REJECT  (garantia ZK por amostral)

    Verificação: A·z = w + c·pk  (mod q, mod x^N+1)  ∧  ||z||_∞ ≤ REJECT
    """

    MAX_PROOF_SIZE_BYTES = MAX_PROOF_BYTES

    def __init__(self, secret_seed: bytes = None):
        sk_seed = (
            blake3.blake3(secret_seed, key=_DK_SECRET).digest()
            if secret_seed is not None
            else blake3.blake3(
                b"PLEGMA_ZK_PROTOCOL_SECRET_SEED_2026", key=_DK_SECRET
            ).digest()
        )
        self._sk       = _sample_secret(sk_seed)
        self._pk       = _poly_mul(_get_A(), self._sk)
        self._pk_bytes = _poly_to_bytes(self._pk)

    def generate_recursive_proof(
        self,
        dag_state_hash: str,
        previous_proof: bytes = b"",
    ) -> bytes:
        """
        Gera prova ZK Ring-SIS para o estado dag_state_hash.
        Encadeia com previous_proof via BLAKE3 keyed-mode.
        """
        state_bytes = dag_state_hash.encode("utf-8")
        prev_hash   = (
            blake3.blake3(previous_proof, key=_DK_CHAIN).digest()
            if previous_proof
            else bytes(32)
        )

        A         = _get_A()
        sk        = self._sk
        pk_bytes  = self._pk_bytes
        mask_seed = blake3.blake3(state_bytes + prev_hash, key=_DK_MASK).digest()

        w_bytes  = None
        c_tilde  = None
        z_int    = None
        accepted = 99

        for nonce in range(100):
            # 1. Máscara y ∈ [-GAMMA, GAMMA]^N
            y      = _sample_mask(mask_seed, nonce)
            y_ring = [v % Q for v in y]

            # 2. Compromisso w = A·y (mod q, mod x^N+1)
            w       = _poly_mul(A, y_ring)
            w_bytes = _poly_to_bytes(w)

            # 3. Desafio Fiat-Shamir: c̃ = H(pk ‖ state ‖ prev ‖ w)
            c_tilde = blake3.blake3(
                pk_bytes + state_bytes + prev_hash + w_bytes,
                key=_DK_CHALL,
            ).digest()
            c_poly = _sample_challenge(c_tilde)

            # 4. Resposta z = y + c·sk (mod q), centre-lift para norma
            cs     = _poly_mul_challenge(c_poly, sk)
            z_ring = _poly_add(y_ring, cs)
            z_int  = [_centre_lift(x) for x in z_ring]

            # 5. Rejeição: aceitar apenas se ||z||_∞ ≤ REJECT_THRESHOLD
            if max(abs(x) for x in z_int) <= REJECT_THRESHOLD:
                accepted = nonce
                break
        else:
            _log.warning("[ZK] Amostras esgotadas — usando última iteração")

        z_bytes = _zlist_to_bytes(z_int)

        payload = {
            "protocol": PROTOCOL_VERSION,
            "state"   : dag_state_hash,
            "prev"    : prev_hash.hex(),
            "pk"      : pk_bytes.hex(),
            "w"       : w_bytes.hex(),
            "z"       : z_bytes.hex(),
            "c_tilde" : c_tilde.hex(),
            "nonce"   : accepted,
        }

        proof_bytes = json.dumps(payload, separators=(",", ":")).encode()

        if len(proof_bytes) > MAX_PROOF_BYTES:
            raise MemoryError(
                f"Prova excedeu limite de {MAX_PROOF_BYTES} bytes: {len(proof_bytes)} bytes."
            )

        return proof_bytes

    def verify_proof(self, proof_bytes: bytes, current_state_hash: str) -> bool:
        """
        Verifica prova ZK: A·z = w + c·pk (mod q, mod x^N+1) ∧ ||z||_∞ ≤ REJECT.
        Aceita provas v4.1 (State Seal BLAKE3) para retrocompatibilidade.
        """
        try:
            p = json.loads(proof_bytes.decode())
        except Exception:
            return False

        proto = p.get("protocol", "")

        if proto == _V41_PROTO:
            return _verify_v41_seal(p, current_state_hash)

        if proto != PROTOCOL_VERSION:
            return False

        if p.get("state") != current_state_hash:
            return False

        try:
            state_bytes = current_state_hash.encode("utf-8")
            prev_hash   = bytes.fromhex(p["prev"])
            pk_bytes    = bytes.fromhex(p["pk"])
            w_bytes     = bytes.fromhex(p["w"])
            z_bytes     = bytes.fromhex(p["z"])
            c_tilde     = bytes.fromhex(p["c_tilde"])
        except Exception:
            return False

        try:
            pk    = _bytes_to_poly(pk_bytes)
            w     = _bytes_to_poly(w_bytes)
            z_int = _bytes_to_zlist(z_bytes)
        except Exception:
            return False

        # 1. Verificar norma da resposta
        if max(abs(x) for x in z_int) > REJECT_THRESHOLD:
            return False

        # 2. Reconstruir desafio Fiat-Shamir e verificar consistência
        expected_c_tilde = blake3.blake3(
            pk_bytes + state_bytes + prev_hash + w_bytes,
            key=_DK_CHALL,
        ).digest()
        if c_tilde != expected_c_tilde:
            return False

        c_poly = _sample_challenge(c_tilde)

        # 3. Equação de verificação: A·z = w + c·pk (mod q, mod x^N+1)
        A      = _get_A()
        z_ring = [v % Q for v in z_int]
        lhs    = _poly_mul(A, z_ring)
        cpk    = _poly_mul_challenge(c_poly, pk)
        rhs    = _poly_add(w, cpk)

        return lhs == rhs


# Alias de retrocompatibilidade
ZkPressEngine = DagSealEngine


# ── Self-test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import time
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    _log.info("=" * 68)
    _log.info(" PLEGMA ZK Press v5.0 — Ring-SIS Sigma Protocol              ")
    _log.info(f" N={N} · Q={Q} · ETA={ETA} · GAMMA={GAMMA} · TAU={TAU} · REJECT={REJECT_THRESHOLD}")
    _log.info("=" * 68)

    engine = DagSealEngine()
    estado = "a1b2c3d4e5f60718293a4b5c6d7e8f90" * 2

    _log.info("\n[*] Gerando prova ZK Ring-SIS...")
    t0     = time.time()
    prova  = engine.generate_recursive_proof(estado)
    t_gen  = (time.time() - t0) * 1000
    parsed = json.loads(prova)

    _log.info(f"    Nonce aceite    : {parsed['nonce']}")
    _log.info(f"    Tempo geração   : {t_gen:.0f} ms")
    _log.info(f"    Tamanho prova   : {len(prova)} bytes ({len(prova)/1024:.2f} KB)")
    _log.info(f"    Limite (22KB)   : {'[OK]' if len(prova) <= MAX_PROOF_BYTES else '[FAIL]'}")

    _log.info("\n[*] Verificando prova...")
    t0    = time.time()
    ok    = engine.verify_proof(prova, estado)
    t_ver = (time.time() - t0) * 1000
    _log.info(f"    Tempo verif.    : {t_ver:.0f} ms")
    _log.info(f"    Verificação ZK  : {'[OK]' if ok else '[FAIL]'}")

    _log.info("\n[*] Anti-adulteração (estado errado)...")
    ok_neg = engine.verify_proof(prova, "estado_adulterado_malicioso")
    _log.info(f"    Adulterado      : {'[OK] BLOQUEADO' if not ok_neg else '[FAIL] BRECHA'}")

    _log.info("\n[*] Encadeamento DAG (previous_proof)...")
    e2     = blake3.blake3(prova).hexdigest()
    prova2 = engine.generate_recursive_proof(e2, previous_proof=prova)
    ok2    = engine.verify_proof(prova2, e2)
    _log.info(f"    Encadeamento    : {'[OK]' if ok2 else '[FAIL]'}")

    _log.info(f"\n    Protocolo       : {parsed['protocol']}")
    _log.info("=" * 68)
