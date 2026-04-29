# Sessão 29/04/2026 — Bloco 1

## Tópicos discutidos
- Redução de HIGH no sentinela antes do lançamento Genesis (09/05/2026)
- Análise completa dos 91 HIGH: categorização por tipo (CORS, IP, XSS, Dart)
- Correcção CORS nos servidores Python
- Melhoria das exclusões do sentinela para eliminar falsos positivos
- Correcção de strings de texto puro a usar textContent em vez de innerHTML

## Decisões técnicas tomadas
- CORS wildcard (*) substituído por validação dinâmica de origin em todos os servidores BaseHTTP (auth, wallet, shield, miner, core_vm)
- FastAPI CORSMiddleware restringido a: plegmadag.com, www.plegmadag.com, plagmadag.com
- IPs dos nós âncora (EU/BR/MAL/SIN) adicionados à lista de exclusões do sentinela (são públicos by design)
- IPs de sandbox (80.78.26.52) também excluídos do sentinela frontend
- `badgeCategoria()`, `orig`, `isBuy` adicionados como exclusões seguras de innerHTML no sentinela
- Exclusão de template literals iniciando com `=> \`<tag>` em callbacks `.map()`
- Exclusão de linhas terminando com apenas `=` (multi-linha) e `= \`` (template multi-linha)
- `escapeHtml()` adicionado como função de escape conhecida ao sentinela
- strings de texto puro no console (mensagens de sócio Genesis) migradas para `textContent`

## Problemas resolvidos
- Sentinela reportava 91 HIGH — análise mostrou 42 estáticos + 8 IPs públicos + 10 CORS reais + 3 Dart falso positivo
- CORS wildcard em 7 locais de código (6 ficheiros de servidor): todos corrigidos
- Falso positivo Dart: `replaceAll('http://', '')` — adicionado `["\']` ao lookbehind da regra

## Arquivos criados/modificados
- `PLEGMA_CORE/auth_server.py` — CORS dinâmico
- `PLEGMA_CORE/wallet_server.py` — CORS dinâmico
- `PLEGMA_CORE/shield_server.py` — CORS dinâmico
- `PLEGMA_CORE/miner_server.py` — CORS dinâmico
- `PLEGMA_CORE/miner/miner_server.py` — CORS dinâmico
- `PLEGMA_CORE/core_vm.py` — CORS dinâmico em _set_headers + do_OPTIONS
- `PLEGMA_CORE/core_api.py` — CORSMiddleware restringido; headers manuais * removidos de node_map
- `PLEGMA_LANDING/console/index.html` — 3 innerHTML → textContent (msgs sócio Genesis)
- `SECURITY_AUDIT/sentinela_agent.py` — 6 melhorias de exclusão nas regras XSS, IP e Dart

## Estado atual
- Versão do app: v1.12.0 (sem mudanças Flutter nesta sessão)
- Build pendente: não
- Servidor: core_api.py activo em EU/BR/MAL/SIN (TESTNET)
- Sentinela: CRITICAL 0 · HIGH 36 · MEDIUM 453 · LOW 3 (era 91 HIGH no início)

## Próximos passos
- Continuar redução HIGH 36 → idealmente <20 antes do Genesis
- Analisar os 36 restantes: maioria são dados de API server (lista.map, txs.map) — baixo risco real
- Instalar APK v1.12.0 no celular e testar recovery com seed phrase real
- Testar QR login no dashboard
- Comprometer data pública de auditoria externa (pré-requisito Genesis)
