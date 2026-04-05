"""
zk_press.py — PLEGMA ZK Engine v3.1
=====================================
Protocolo: Groth16 SNARK sobre BN128
Circuito:  PLEGMA_BINDING (circom 2.0 / snarkjs)

Prova que: "o emissor conhece w, r tais que
              snap_h = w*(w+r)      (snapshot binding)
              b      = w*state_h    (DAG vertex binding)
           onde state_h = H(dag_state_hash)"

Backends (em ordem de prioridade):
  1. snarkjs/BN128  — zk/generate_proof.js + verify_proof.js via subprocess
                      Requer: npm install  +  setup_zk.sh  no diretório zk/
                      Velocidade: ~1–2 s gerar / ~50 ms verificar
  2. Python/BN128   — Groth16 puro Python (CRS transparente BLAKE3)
                      Sem dependências extras além de py_ecc e blake3
                      Velocidade: ~400 ms gerar / ~19 s verificar

Tamanho da prova: ~700–1100 bytes  (<< limite 22.528 bytes do Estatuto §2.2)

Dependências:
  pip install py_ecc blake3
  (snarkjs) npm install  +  bash zk/setup_zk.sh
"""

import json
import os
import subprocess
import tempfile
import blake3

# ── Caminhos do backend snarkjs ───────────────────────────────────────────────
_ZK_DIR  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "zk")
_WASM    = os.path.join(_ZK_DIR, "plegma_binding_js", "plegma_binding.wasm")
_ZKEY    = os.path.join(_ZK_DIR, "plegma_binding_final.zkey")
_VKEY    = os.path.join(_ZK_DIR, "verification_key.json")
_GEN_JS  = os.path.join(_ZK_DIR, "generate_proof.js")
_VER_JS  = os.path.join(_ZK_DIR, "verify_proof.js")

PROTOCOL_SNARKJS = "ALV-ZKDAG-GROTH16-SNARKJS-v3.1"
PROTOCOL_PYTHON  = "ALV-ZKDAG-GROTH16-PYTHON-v3.1"
PROTOCOL         = PROTOCOL_SNARKJS          # protocolo preferido
MAX_PROOF_BYTES  = 22 * 1024                 # §2.2


# ═══════════════════════════════════════════════════════════════════════════════
# Utilitários comuns
# ═══════════════════════════════════════════════════════════════════════════════

def _h2s(*parts: bytes) -> int:
    """BLAKE3( partes... ) → escalar em Zq (campo BN128)."""
    from py_ecc.bn128 import curve_order as _Q
    return int.from_bytes(blake3.blake3(b"".join(parts)).digest(), "big") % _Q


# ═══════════════════════════════════════════════════════════════════════════════
# Backend snarkjs (Node.js / circom / snarkjs)
# ═══════════════════════════════════════════════════════════════════════════════

def _snarkjs_ready() -> bool:
    """True se os artefatos do setup_zk.sh existem."""
    return all(os.path.exists(p) for p in [_WASM, _ZKEY, _VKEY, _GEN_JS, _VER_JS])


def _snarkjs_prove(witness: dict) -> dict:
    """
    Chama generate_proof.js via subprocess (arquivos temp — sem bug de pipe Windows).

    witness = { "w": str, "r": str, "state_h": str, "snap_h": str, "b": str }
              (strings decimais — campo BN128)

    Retorna { "proof": {...snarkjs format...}, "publicSignals": [...] }
    """
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as fi:
        json.dump(witness, fi)
        inp_path = fi.name
    out_path = inp_path.replace(".json", "_out.json")
    try:
        proc = subprocess.run(
            ["node", _GEN_JS, inp_path, out_path],
            capture_output=True, timeout=120,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"snarkjs prove falhou: {proc.stderr.decode(errors='replace')[:500]}"
            )
        with open(out_path, "r") as f:
            return json.load(f)   # { "proof": {...}, "publicSignals": [...] }
    finally:
        for p in (inp_path, out_path):
            try: os.unlink(p)
            except OSError: pass


def _snarkjs_verify(proof: dict, public_signals: list) -> bool:
    """
    Chama verify_proof.js via subprocess (arquivos temp).

    public_signals = lista de strings decimais [state_h, snap_h, b]
    """
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as fi:
        json.dump({"proof": proof, "publicSignals": public_signals}, fi)
        inp_path = fi.name
    out_path = inp_path.replace(".json", "_out.json")
    try:
        proc = subprocess.run(
            ["node", _VER_JS, inp_path, out_path],
            capture_output=True, timeout=30,
        )
        if proc.returncode != 0:
            return False
        with open(out_path, "r") as f:
            return bool(json.load(f).get("valid", False))
    except Exception:
        return False
    finally:
        for p in (inp_path, out_path):
            try: os.unlink(p)
            except OSError: pass


# ═══════════════════════════════════════════════════════════════════════════════
# Backend Python/Groth16 (fallback sem Node.js)
# ═══════════════════════════════════════════════════════════════════════════════

def _python_backend_prove(z: list, state_key: bytes) -> dict:
    """Groth16 puro Python — retorna {"A": hex, "B": hex, "C": hex}."""
    return _groth16_prove_py(z, state_key)


def _python_backend_verify(proof: dict, z_pub: list) -> bool:
    """Groth16 puro Python — verifica {"A": hex, "B": hex, "C": hex}."""
    return _groth16_verify_py(proof, z_pub)


# ─── Patch FQ12.__pow__ iterativo (fix Python 3.14 RecursionError) ────────────
def _fq12_pow_iter(self, other):
    exp = int(other)
    if exp == 0:
        try:
            return self.__class__.one()
        except AttributeError:
            c    = [0] * len(getattr(self, "coeffs", [0] * 12))
            c[0] = 1
            return self.__class__(c)
    result = None
    base   = self
    while exp > 0:
        if exp & 1:
            result = base if result is None else result * base
        base = base * base
        exp >>= 1
    return result

for _mp in ("py_ecc.bn128", "py_ecc.fields.bn128_field_elements", "py_ecc.fields.field_elements"):
    try:
        import importlib as _il
        _m = _il.import_module(_mp)
        if hasattr(_m, "FQ12"):
            _m.FQ12.__pow__ = _fq12_pow_iter
    except Exception:
        pass
# ─────────────────────────────────────────────────────────────────────────────

from py_ecc.bn128 import (
    G1, G2, add, multiply, pairing,
    curve_order as _Q, FQ, FQ2,
    b as _B1, b2 as _B2, is_on_curve,
)

# ── Aritmética Zq ─────────────────────────────────────────────────────────────

def _finv(a: int) -> int:
    return pow(int(a) % _Q, _Q - 2, _Q)

def _padd(a, b):
    n = max(len(a), len(b))
    return [((a[i] if i < len(a) else 0)+(b[i] if i < len(b) else 0)) % _Q for i in range(n)]

def _psub(a, b):
    n = max(len(a), len(b))
    return [((a[i] if i < len(a) else 0)-(b[i] if i < len(b) else 0)) % _Q for i in range(n)]

def _pmul(a, b):
    if not a or not b:
        return [0]
    r = [0] * (len(a)+len(b)-1)
    for i, ai in enumerate(a):
        for j, bj in enumerate(b):
            r[i+j] = (r[i+j]+ai*bj) % _Q
    return r

def _pscale(a, s: int):
    s %= _Q
    return [c*s % _Q for c in a]

def _pdiv(f, g):
    f, g = list(f), list(g)
    while len(f) > 1 and f[-1] == 0: f.pop()
    while len(g) > 1 and g[-1] == 0: g.pop()
    if len(f) < len(g): return [0]
    inv_lg = _finv(g[-1]); q = []
    while len(f) >= len(g):
        qc = f[-1]*inv_lg % _Q; q.append(qc); dd = len(f)-len(g)
        for i in range(len(g)): f[dd+i] = (f[dd+i]-qc*g[i]) % _Q
        f.pop()
        while len(f) > 1 and f[-1] == 0: f.pop()
    q.reverse(); return q if q else [0]

def _peval(poly, x):
    x %= _Q; res = 0; xp = 1
    for c in poly: res = (res+c*xp) % _Q; xp = xp*x % _Q
    return res

def _lagrange(pts, evals):
    n = len(pts); res = [0]
    for i in range(n):
        if evals[i] == 0: continue
        num = [1]; den = 1
        for j in range(n):
            if j == i: continue
            num = _pmul(num, [(-pts[j]) % _Q, 1])
            den = den*(pts[i]-pts[j]) % _Q
        res = _padd(res, _pscale(num, evals[i]*_finv(den) % _Q))
    return res

# ── Serialização EC ───────────────────────────────────────────────────────────

def _g1enc(pt) -> str:
    x, y = pt
    return int(x).to_bytes(32,"big").hex()+int(y).to_bytes(32,"big").hex()

def _g1dec(s: str):
    raw = bytes.fromhex(s)
    if len(raw) != 64: raise ValueError("G1: 64 bytes")
    pt = (FQ(int.from_bytes(raw[:32],"big")), FQ(int.from_bytes(raw[32:],"big")))
    if not is_on_curve(pt, _B1): raise ValueError("G1 fora da curva")
    return pt

def _g2enc(pt) -> str:
    x, y = pt; xc = x.coeffs; yc = y.coeffs
    return (int(xc[0]).to_bytes(32,"big").hex()+int(xc[1]).to_bytes(32,"big").hex()+
            int(yc[0]).to_bytes(32,"big").hex()+int(yc[1]).to_bytes(32,"big").hex())

def _g2dec(s: str):
    raw = bytes.fromhex(s)
    if len(raw) != 128: raise ValueError("G2: 128 bytes")
    pt = (FQ2([int.from_bytes(raw[0:32],"big"), int.from_bytes(raw[32:64],"big")]),
          FQ2([int.from_bytes(raw[64:96],"big"), int.from_bytes(raw[96:128],"big")]))
    if not is_on_curve(pt, _B2): raise ValueError("G2 fora da curva")
    return pt

# ── R1CS PLEGMA_BINDING ───────────────────────────────────────────────────────
# z = [1, state_h, snap_h, b,  w,  r,  w_sq, wr]

_M=4; _NVAR=8; _NPUB=4
_A_R1CS=[[0,0,0,0,1,0,0,0],[0,0,0,0,1,0,0,0],[0,0,0,0,0,0,1,1],[0,0,0,0,1,0,0,0]]
_B_R1CS=[[0,0,0,0,1,0,0,0],[0,0,0,0,0,1,0,0],[1,0,0,0,0,0,0,0],[0,1,0,0,0,0,0,0]]
_C_R1CS=[[0,0,0,0,0,0,1,0],[0,0,0,0,0,0,0,1],[0,0,1,0,0,0,0,0],[0,0,0,1,0,0,0,0]]

_EVAL=[1,2,3,4]
_T_POLY=[1]
for _rp in _EVAL: _T_POLY=_pmul(_T_POLY,[(-_rp)%_Q,1])

_QAP_U=[_lagrange(_EVAL,[_A_R1CS[i][j] for i in range(_M)]) for j in range(_NVAR)]
_QAP_V=[_lagrange(_EVAL,[_B_R1CS[i][j] for i in range(_M)]) for j in range(_NVAR)]
_QAP_W=[_lagrange(_EVAL,[_C_R1CS[i][j] for i in range(_M)]) for j in range(_NVAR)]

# ── CRS transparente ─────────────────────────────────────────────────────────
_CRS_SEED = b"PLEGMA_GROTH16_BN128_CRS_2026_ZKDAG_FAIRLAUNCH"
def _cs(lbl): return int.from_bytes(blake3.blake3(_CRS_SEED+lbl.encode()).digest(),"big") % _Q
_TAU=_cs("tau"); _ALPHA=_cs("alpha"); _BETA=_cs("beta"); _GAMMA=_cs("gamma"); _DELTA=_cs("delta")

_U_TAU=[_peval(_QAP_U[j],_TAU) for j in range(_NVAR)]
_V_TAU=[_peval(_QAP_V[j],_TAU) for j in range(_NVAR)]
_W_TAU=[_peval(_QAP_W[j],_TAU) for j in range(_NVAR)]
_T_TAU=_peval(_T_POLY,_TAU)


def _groth16_prove_py(z, state_key: bytes):
    A_tau=sum(z[j]*_U_TAU[j] for j in range(_NVAR))%_Q
    B_tau=sum(z[j]*_V_TAU[j] for j in range(_NVAR))%_Q
    Ap=[0]; Bp=[0]; Cp=[0]
    for j in range(_NVAR):
        if z[j]==0: continue
        Ap=_padd(Ap,_pscale(_QAP_U[j],z[j])); Bp=_padd(Bp,_pscale(_QAP_V[j],z[j])); Cp=_padd(Cp,_pscale(_QAP_W[j],z[j]))
    h_tau=_peval(_pdiv(_psub(_pmul(Ap,Bp),Cp),_T_POLY),_TAU)
    rho  =int.from_bytes(blake3.blake3(state_key+b"PLEGMA_RHO_SALT").digest(),"big")%_Q
    sigma=int.from_bytes(blake3.blake3(state_key+b"PLEGMA_SIGMA_SALT").digest(),"big")%_Q
    inv_d=_finv(_DELTA)
    piA_s=(_ALPHA+A_tau+rho*_DELTA)%_Q
    pi_A=multiply(G1,piA_s); pi_B=multiply(G2,(_BETA+B_tau+sigma*_DELTA)%_Q)
    priv=sum(z[j]*(_BETA*_U_TAU[j]+_ALPHA*_V_TAU[j]+_W_TAU[j])%_Q for j in range(_NPUB,_NVAR))%_Q
    pi_C=multiply(G1,(priv*inv_d+h_tau*_T_TAU%_Q*inv_d+sigma*piA_s+rho*(_BETA+B_tau))%_Q)
    return {"A":_g1enc(pi_A),"B":_g2enc(pi_B),"C":_g1enc(pi_C)}


def _groth16_verify_py(proof,z_pub):
    pi_A=_g1dec(proof["A"]); pi_B=_g2dec(proof["B"]); pi_C=_g1dec(proof["C"])
    vk_s=sum(z_pub[j]*(_BETA*_U_TAU[j]+_ALPHA*_V_TAU[j]+_W_TAU[j])%_Q for j in range(_NPUB))%_Q
    vk_x=multiply(G1,vk_s*_finv(_GAMMA)%_Q)
    return (pairing(pi_B,pi_A) ==
            pairing(multiply(G2,_BETA),multiply(G1,_ALPHA)) *
            pairing(multiply(G2,_GAMMA),vk_x) *
            pairing(multiply(G2,_DELTA),pi_C))


# ═══════════════════════════════════════════════════════════════════════════════
# ZkPressEngine — API pública
# ═══════════════════════════════════════════════════════════════════════════════

class ZkPressEngine:
    """
    Motor ZK-SNARK Groth16/BN128 para o PLEGMA DAG.

    Usa snarkjs (circom) se os artefatos do setup_zk.sh estiverem presentes
    em PLEGMA_CORE/zk/.  Caso contrário, cai no Groth16 puro Python.

    API idêntica à v2.0 (compatível com chamadas existentes em core_vm.py / gossip.py).
    """

    MAX_PROOF_SIZE_BYTES = MAX_PROOF_BYTES

    def generate_recursive_proof(
        self,
        dag_state_hash: str,
        previous_proof: bytes = b"",
    ) -> bytes:
        """
        Gera prova ZK Groth16 para um vértice DAG.

        Witness:
          w       = H(state_hash ‖ prev_hash)
          r       = random
          state_h = H(state_hash)
          snap_h  = w*(w+r) mod q
          b       = w*state_h mod q
        """
        prev_hash = (blake3.blake3(previous_proof).digest()
                     if previous_proof else bytes(32))

        w       = _h2s(dag_state_hash.encode(), prev_hash)
        r_seed  = dag_state_hash.encode() + b"PLEGMA_ZKDAG_SALT"
        r_wit   = int.from_bytes(blake3.blake3(r_seed).digest(), "big") % _Q
        state_h = _h2s(dag_state_hash.encode())
        snap_h  = w * (w + r_wit) % _Q
        b_val   = w * state_h % _Q

        if _snarkjs_ready():
            # ── Backend snarkjs ──────────────────────────────────────────
            witness = {
                "w"      : str(w),
                "r"      : str(r_wit),
                "state_h": str(state_h),
                "snap_h" : str(snap_h),
                "b"      : str(b_val),
            }
            out   = _snarkjs_prove(witness)
            proof = out["proof"]                  # formato snarkjs nativo
            # publicSignals: [state_h, snap_h, b]  (ordem circom)

            payload = {
                "protocol": PROTOCOL_SNARKJS,
                "curve"   : "BN128-Groth16-circom",
                "proof"   : proof,
                "pub"     : {
                    "state_h": hex(state_h),
                    "snap_h" : hex(snap_h),
                    "b"      : hex(b_val),
                },
                "state"   : dag_state_hash,
                "prev"    : prev_hash.hex(),
            }
        else:
            # ── Backend Python (fallback) ────────────────────────────────
            z      = [1, state_h, snap_h, b_val,
                      w, r_wit, w*w % _Q, w*r_wit % _Q]
            proof  = _groth16_prove_py(z, dag_state_hash.encode())

            payload = {
                "protocol": PROTOCOL_PYTHON,
                "curve"   : "BN128-Groth16-python",
                "A"       : proof["A"],
                "B"       : proof["B"],
                "C"       : proof["C"],
                "pub"     : {
                    "state_h": hex(state_h),
                    "snap_h" : hex(snap_h),
                    "b"      : hex(b_val),
                },
                "state"   : dag_state_hash,
                "prev"    : prev_hash.hex(),
            }

        proof_bytes = json.dumps(payload, separators=(",", ":")).encode()

        if len(proof_bytes) > MAX_PROOF_BYTES:
            raise MemoryError(
                f"Prova excedeu {MAX_PROOF_BYTES} bytes: {len(proof_bytes)} bytes"
            )
        return proof_bytes

    def verify_proof(self, proof_bytes: bytes, current_state_hash: str) -> bool:
        """
        Verifica prova ZK — detects backend from 'protocol' field.
        """
        try:
            p        = json.loads(proof_bytes.decode())
            protocol = p.get("protocol", "")

            if p.get("state") != current_state_hash:
                return False

            pub     = p["pub"]
            state_h = int(pub["state_h"], 16)
            snap_h  = int(pub["snap_h"],  16)
            b_val   = int(pub["b"],       16)

            if state_h != _h2s(current_state_hash.encode()):
                return False

            if protocol == PROTOCOL_SNARKJS:
                # ── snarkjs path ─────────────────────────────────────────
                if not _snarkjs_ready():
                    return False   # chaves não disponíveis neste nó
                public_signals = [str(state_h), str(snap_h), str(b_val)]
                return _snarkjs_verify(p["proof"], public_signals)

            elif protocol == PROTOCOL_PYTHON:
                # ── Python fallback path ──────────────────────────────────
                proof_ec = {"A": p["A"], "B": p["B"], "C": p["C"]}
                return _groth16_verify_py(proof_ec, [1, state_h, snap_h, b_val])

            else:
                return False

        except Exception:
            return False


# ═══════════════════════════════════════════════════════════════════════════════
# Self-test
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import time

    print("=" * 62)
    print(" PLEGMA ZK Engine v3.1  |  Groth16 / BN128               ")
    print(" Circuito: PLEGMA_BINDING (circom 2.0 + snarkjs)         ")
    print("=" * 62)

    snarkjs_ok = _snarkjs_ready()
    print(f"\n Backend ativo : {'snarkjs (circom/Node.js)' if snarkjs_ok else 'Python puro (fallback)'}")
    if not snarkjs_ok:
        print(" AVISO: Para usar o backend snarkjs, execute:")
        print("   cd zk && npm install && bash setup_zk.sh")

    zk     = ZkPressEngine()
    estado = "a1b2c3d4e5f60718293a4b5c6d7e8f90" * 2

    print("\n[*] Gerando prova Groth16...")
    t0    = time.time()
    prova = zk.generate_recursive_proof(estado)
    t_gen = (time.time() - t0) * 1000
    print(f"    Gerada em  : {t_gen:.0f} ms")
    print(f"    Tamanho    : {len(prova)} bytes ({len(prova)/1024:.2f} KB)")
    print(f"    Limite 22K : {'[OK]' if len(prova) <= MAX_PROOF_BYTES else '[FAIL]'}")

    print("\n[*] Verificando prova...")
    t0    = time.time()
    ok    = zk.verify_proof(prova, estado)
    t_ver = (time.time() - t0) * 1000
    print(f"    Verificada : {t_ver:.0f} ms")
    print(f"    Resultado  : {'[OK] VALIDA' if ok else '[FAIL] INVALIDA'}")

    ok_neg = zk.verify_proof(prova, "hash_adulterado")
    print(f"    Adulteracao: {'[OK] REJEITADA' if not ok_neg else '[FAIL] FALHA!'}")

    print("\n[*] Encadeamento recursivo...")
    e2     = blake3.blake3(prova).hexdigest()
    prova2 = zk.generate_recursive_proof(e2, previous_proof=prova)
    ok2    = zk.verify_proof(prova2, e2)
    print(f"    Encadeada  : {'[OK] VALIDA' if ok2 else '[FAIL] INVALIDA'}")

    parsed = json.loads(prova)
    print(f"\n    Protocol   : {parsed['protocol']}")
    print(f"    Curve      : {parsed['curve']}")
    print("=" * 62)
