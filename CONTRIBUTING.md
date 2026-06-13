# Contributing to PLEGMA DAG

Thank you for your interest in contributing. PLEGMA DAG is an open protocol — contributions are reviewed and merged by the protocol maintainer.

## Before You Start

1. Check [open Issues](../../issues) — the problem may already be tracked
2. For new features, open an Issue first to discuss before writing code
3. For bug fixes, you can open a Pull Request directly

## Development Setup

```bash
git clone https://github.com/PlegmaDag/plegma-espectro.git
cd plegma-espectro/core
pip install fastapi uvicorn blake3 pynacl
cp ../.env.example .env
# Edit .env with your local config
```

## Protocol Rules (Non-negotiable)

All contributions **must** comply with these rules — PRs that violate them will be rejected:

| Rule | Requirement |
|------|-------------|
| Deterministic | All operations must produce identical output for identical input |
| Post-quantum | Only BLAKE3 + Crystals-Dilithium3 (ML-DSA-65) — no ECDSA, RSA, secp256k1 |
| No redundancy | Do not create functions, endpoints, or tables that already exist |
| No dead code | Remove old code when replacing it |
| No hardcoded secrets | Use environment variables — never commit credentials |
| Supply cap | 21,000,000,000 $PLG — immutable, never modify |

## Pull Request Process

1. Fork the repository
2. Create a branch: `git checkout -b fix/description` or `feat/description`
3. Make your changes — one logical change per PR
4. Write or update tests if applicable
5. Open a Pull Request with:
   - What the change does
   - Why it is needed
   - How to test it

## Code Style

- Python: follow PEP 8, max line length 100
- Dart/Flutter: follow `analysis_options.yaml`
- Comments: only when the WHY is non-obvious — no narrative comments
- No `print()` or `console.log()` debug statements in production code

## What Gets Accepted

- Bug fixes with clear reproduction steps
- Security improvements (see [SECURITY.md](SECURITY.md) for vulnerabilities)
- Performance improvements with measurable evidence
- Documentation improvements

## What Gets Rejected

- Features that break the deterministic or post-quantum requirements
- Code that introduces classical cryptography (ECDSA, RSA, etc.)
- Changes to supply cap, consensus rules, or immutable protocol parameters
- PRs without a clear description of what and why

## Review Process

All PRs are reviewed by the protocol maintainer. Merged code does not automatically deploy to production nodes — deployment is controlled separately.
