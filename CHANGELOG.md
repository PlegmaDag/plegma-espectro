# Changelog

All notable changes to PLEGMA DAG are documented here.

## [1.0.0] — 2026-06-13

### Initial Open Source Release

- Full protocol source code published under MIT license
- `core/` — DAG consensus engine, REST API, mining, wallet, post-quantum cryptography
- `orchestrator/` — Local agent orchestrator with 22 specialized agents
- `app/` — Flutter mobile wallet (Android)
- `landing/` — Web frontend (17 pages)
- `security/` — Public security audit reports

---

## Mainnet History

### 2026-06-04 — Translator Service
- Plegma Translator launched at `translator.plegmadag.com` (port 8020, 4 nodes)

### 2026-05-31 — Timestamp Service
- Plegma Timestamp launched at `timestamp.plegmadag.com` (4 nodes, `plegma-cartorio.service`)
- BLAKE3 WASM implementation for frontend certificate verification

### 2026-05-23 — Network Audit
- Gossip P2P bug fixed — mine-accepted vertices propagate correctly across all nodes
- Duplicate services removed, memory normalized
- External suspicious IP blocked

### 2026-05-21 — L-99 Security Audit
- 5-auditor review completed — CONDITIONALLY APPROVED
- ZK-SNARK replaced by DagSealEngine (State Integrity Seal, BLAKE3 keyed-mode v4.1)
- SEO/GEO/AEO deployment complete

### 2026-05-09 — Mainnet Launch
- PLEGMA DAG mainnet live at 18:00 CEST
- Cluster: EU · USA · MUM · SIN (4 nodes)
- USDC native Polygon: `0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359`

### 2026-04-25 — Orchestrator
- PLEGMA Orchestrator built — 6 specialized agents operational
- Critical vulnerability fixed: admin hash removed from frontend auth

### 2026-04-24 — Security
- SQL injection fixed in `labs_db.py`
- XSS vulnerabilities fixed in console and admin frontends
