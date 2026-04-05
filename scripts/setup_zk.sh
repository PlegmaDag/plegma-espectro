#!/usr/bin/env bash
# =============================================================================
# setup_zk.sh — PLEGMA ZK Setup (one-time, roda no servidor Linux)
# =============================================================================
# Pré-requisitos:
#   1. circom 2.x     →  cargo install circom
#      (ou via npm: npm install -g @iden3/circom)
#   2. node >= 18      →  apt install nodejs  /  nvm install 20
#   3. npm             →  apt install npm
#
# Execute UMA vez no servidor. Gera:
#   plegma_binding.r1cs
#   plegma_binding_js/plegma_binding.wasm
#   plegma_binding_final.zkey
#   verification_key.json
# =============================================================================

set -euo pipefail
ZK_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ZK_DIR"

echo "=== PLEGMA ZK Setup ==="
echo ""

# ── 1. npm install ───────────────────────────────────────────────────────────
echo "[1/6] Instalando dependências npm (snarkjs)..."
npm install
SNARKJS="node node_modules/.bin/snarkjs"

# ── 2. Compilar circuito com circom ──────────────────────────────────────────
echo "[2/6] Compilando plegma_binding.circom..."
circom plegma_binding.circom --r1cs --wasm --sym --output .
echo "      R1CS: plegma_binding.r1cs"
echo "      WASM: plegma_binding_js/plegma_binding.wasm"

# ── 3. Powers-of-Tau (Hermez perpétuo, fase 1 pública) ──────────────────────
echo "[3/6] Obtendo ptau (Hermez perpetual powers-of-tau, 2^12)..."
PTAU="pot12_final.ptau"
if [ ! -f "$PTAU" ]; then
    # Fonte oficial: cerimônia Hermez/Iden3 (~30 MB)
    curl -L \
      "https://hermez.s3-eu-west-1.amazonaws.com/powersOfTau28_hez_final_12.ptau" \
      -o "$PTAU"
    echo "      Download concluído."
else
    echo "      Arquivo existente reutilizado: $PTAU"
fi

# ── 3b. Hash Guard — Determinismo absoluto do PTau ───────────────────────────
PTAU_EXPECTED_B3="7054a415d444ee19b64fcfaa94dbb4f398a97570813720ea3ca62e24eea0efa1"
PTAU_ACTUAL_B3=$(python3 -c "import blake3; print(blake3.blake3(open('${PTAU}','rb').read()).hexdigest())")

if [ "$PTAU_EXPECTED_B3" != "$PTAU_ACTUAL_B3" ]; then
    echo "ERRO FATAL: Quebra de Determinismo. O arquivo .ptau não corresponde ao registro Gênesis."
    echo "  Esperado : $PTAU_EXPECTED_B3"
    echo "  Obtido   : $PTAU_ACTUAL_B3"
    exit 1
fi
echo "      Determinismo do PTau validado. Continuando setup..."

# ── 4. Groth16 setup fase 2 ──────────────────────────────────────────────────
echo "[4/6] Groth16 setup fase 2 (zkey inicial)..."
$SNARKJS groth16 setup plegma_binding.r1cs "$PTAU" plegma_binding_0000.zkey

# ── 5. Contribuição PLEGMA DAG ───────────────────────────────────────────────
echo "[5/6] Adicionando contribuição PLEGMA_DAG_2026..."
# Em produção: use uma fonte de entropia real e guarde o hash da contribuição.
echo "PLEGMA_DAG_2026_ZKDAG_FAIRLAUNCH_ENTROPY" | \
    $SNARKJS zkey contribute \
        plegma_binding_0000.zkey plegma_binding_final.zkey \
        --name="PLEGMA_DAG_2026" -v

# ── 6. Exportar verification key ─────────────────────────────────────────────
echo "[6/6] Exportando verification_key.json..."
$SNARKJS zkey export verificationkey plegma_binding_final.zkey verification_key.json

# ── Resumo ───────────────────────────────────────────────────────────────────
echo ""
echo "=== Setup concluído ==="
echo "  Circuito : plegma_binding.r1cs"
echo "  Prover   : plegma_binding_js/plegma_binding.wasm"
echo "  Zkey     : plegma_binding_final.zkey"
echo "  Vkey     : verification_key.json"
echo ""
echo "ATENÇÃO: Para mainnet, repita a fase 2 com cerimônia MPC multi-party."
echo "  Ref: https://zkproof.org/2021/06/30/setup-ceremonies/"
