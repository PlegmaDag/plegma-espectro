# PLEGMA DAG

**Post-Quantum Distributed Ledger Protocol**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Protocol: DAG](https://img.shields.io/badge/Protocol-DAG-green.svg)]()
[![Crypto: Post-Quantum](https://img.shields.io/badge/Crypto-Post--Quantum-purple.svg)]()
[![Mainnet: LIVE](https://img.shields.io/badge/Mainnet-LIVE-brightgreen.svg)](https://plegmadag.com)

---

## What is PLEGMA DAG?

PLEGMA DAG is a post-quantum distributed ledger protocol built on a **Directed Acyclic Graph (DAG)** consensus architecture. Unlike blockchain systems, PLEGMA uses a DAG structure where multiple transactions can be confirmed in parallel, enabling higher throughput without sacrificing security.

**Key properties:**
- All cryptography is **post-quantum** — resistant to attacks from quantum computers
- All operations are **deterministic** — identical inputs always produce identical outputs
- The $PLG token supply is **fixed at 21,000,000,000** — no inflation, ever
- All code is **open source and auditable** — anyone can verify the protocol

---

## Cryptographic Stack

| Purpose | Algorithm | Standard |
|---------|-----------|----------|
| Digital Signatures | Crystals-Dilithium3 (ML-DSA-65) | NIST FIPS 204 |
| Hashing | BLAKE3 | BLAKE3 spec |
| State Seals | BLAKE3 keyed-mode (DagSealEngine v4.1) | Internal |
| Consensus | DAG (Directed Acyclic Graph) | Internal |

**No classical cryptography is used.** ECDSA, RSA, secp256k1 and all pre-quantum schemes are explicitly forbidden by the protocol.

---

## Repository Structure

```
plegma-espectro/
├── landing/          # Web frontend (17 pages — HTML/CSS/JS)
├── core/             # Protocol core (Python — DAG, mining, wallet, API)
│   ├── core_dag.py           # DAG consensus engine
│   ├── core_api.py           # REST API (FastAPI, port 8080)
│   ├── miner_engine.py       # Mining logic
│   ├── wallet.py             # Wallet operations
│   ├── wallet_server.py      # Wallet API (port 8083)
│   ├── lattice_shield.py     # Post-quantum cryptography layer
│   ├── zk_press.py           # State Integrity Seal (DagSealEngine)
│   ├── plegma_db.py          # Database access layer (SQLite)
│   ├── genesis.py            # Genesis block + tokenomics
│   ├── gossip.py             # P2P gossip protocol
│   └── ...
├── orchestrator/     # Local agent orchestrator
│   ├── orchestrator.py       # CLI: python orchestrator.py "task"
│   ├── router.py             # Complexity routing (SIMPLE/MEDIUM/COMPLEX)
│   └── agents/               # 22 specialized agents
├── app/              # Mobile wallet (Flutter/Dart)
│   ├── lib/                  # App source code
│   └── android/              # Android build config
├── security/         # Public security audits
│   ├── L99_AUDITORIA_COMPLETA_20260521.md
│   └── RELATORIO_SEGURANCA_2026-03-29.md
└── scripts/          # Utility scripts
```

---

## How to Run a Node

Anyone can run a PLEGMA node. This is what makes the network decentralized.

### Requirements

- Python 3.11+
- pip
- A server with a public IP (or local for testing)

### Setup

```bash
git clone https://github.com/PlegmaDag/plegma-espectro.git
cd plegma-espectro/core

# Install dependencies
pip install fastapi uvicorn blake3 pynacl

# Configure environment
cp ../.env.example .env
# Edit .env with your node settings

# Initialize database
python plegma_db.py --init

# Start the node
uvicorn core_api:app --host 0.0.0.0 --port 8080
```

### Environment Variables

Copy `.env.example` to `.env` and configure:

```env
# Your node identity
NODE_ID=your_node_id

# Cluster peers (other nodes to connect to)
NODE_URL_EUR=http://213.199.42.88:8080
NODE_URL_USA=http://209.126.7.120:8080
NODE_URL_MUM=http://217.217.251.206:8080
NODE_URL_SIN=http://82.197.70.189:8080
```

---

## How to Audit the Protocol

Anyone can verify that PLEGMA DAG does what it claims:

1. **Read the cryptography** — `core/lattice_shield.py` implements Dilithium3 signatures. `core/zk_press.py` implements the State Integrity Seal.

2. **Verify the supply cap** — `core/genesis.py` defines `TOTAL_SUPPLY = 21_000_000_000`. The SQLite trigger in `core/plegma_db.py` enforces immutability of founding records.

3. **Check the consensus** — `core/core_dag.py` implements the DAG consensus. Every vertex must be validated by the lattice shield before acceptance.

4. **Read the security audits** — `security/` contains public audit reports from independent reviews.

5. **Run your own node** — Connect to the mainnet and verify state yourself. The API exposes `/api/dag/status`, `/api/cluster/status` and full transaction history.

---

## Token Economics

| Property | Value |
|----------|-------|
| Token | $PLG |
| Total Supply | 21,000,000,000 (fixed) |
| Inflation | None — ever |
| Genesis Reserve (PLG-G) | 10,500,000 (fixed) |
| Foundation | No treasury wallet — direct P2P only |
| Governance | 1 person · 1 vote · threshold-activated |

---

## Mainnet

The PLEGMA DAG mainnet has been **live since May 9, 2026**.

- Website: [plegmadag.com](https://plegmadag.com)
- Explorer: [plegmadag.com/dashboard](https://plegmadag.com/dashboard)
- Timestamp Service: [timestamp.plegmadag.com](https://timestamp.plegmadag.com)
- Translator Service: [translator.plegmadag.com](https://translator.plegmadag.com)

Regional nodes:
- EU: `213.199.42.88:8080`
- USA: `209.126.7.120:8080`
- MUM: `217.217.251.206:8080`
- SIN: `82.197.70.189:8080`

---

## Contributing

1. Fork this repository
2. Create a branch: `git checkout -b fix/your-fix`
3. Make your changes
4. Open a Pull Request with a clear description

All contributions are reviewed before merging. The protocol maintainer approves all changes to the official codebase. Only the maintainer deploys to production nodes.

**Reporting vulnerabilities:** Open a GitHub Issue marked `[SECURITY]`. Do not publish exploit details publicly until a fix is deployed.

---

## Security

See [`security/`](security/) for public audit reports.

The sentinela scanner (`security/sentinela_agent.py`) runs continuously on all nodes and reports to the security dashboard.

---

## License

MIT — see [LICENSE](LICENSE).

This means you can use, copy, modify, distribute and run PLEGMA DAG for any purpose. Attribution is appreciated but not required.
