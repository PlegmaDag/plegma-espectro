# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| mainnet (current) | Yes |

## Reporting a Vulnerability

**Do not open a public GitHub Issue for security vulnerabilities.**

If you discover a security vulnerability in PLEGMA DAG, report it privately:

1. Open a GitHub Issue titled `[SECURITY] Brief description`
2. Mark it as **confidential** using GitHub's private vulnerability reporting
3. Include: affected component, reproduction steps, potential impact

We will acknowledge receipt within 48 hours and provide a fix timeline.

**Please do not publish exploit details publicly until a fix has been deployed to all nodes.**

## Scope

| Component | In scope |
|-----------|----------|
| `core/` — DAG consensus, mining, wallet, API | Yes |
| `core/lattice_shield.py` — post-quantum cryptography | Yes |
| `core/zk_press.py` — State Integrity Seal | Yes |
| `landing/` — web frontend | Yes |
| `app/` — Flutter mobile wallet | Yes |
| Social engineering attacks | No |
| Attacks requiring physical access to nodes | No |

## Public Audits

See [`security/`](security/) for completed public security audits.

## Bug Bounty

There is no formal bug bounty programme at this time. Significant findings will be credited publicly (with your permission) in the security audit reports.
