# Sessão 18 ABR 2026 — Bloco 1

## Tópicos discutidos
- Migração completa de `core_vm.py` (ThreadingHTTPServer) para `core_api.py` (FastAPI + uvicorn)
- Deploy nos 4 nós de produção (EU/SIN/BR/MAL) — 10 backends totais
- Nginx local-only: upstream de cada nó aponta só para `127.0.0.1` (sem cross-node)
- Nginx micro-cache activo: `/api/status`, `/api/lastBlock`, `/api/dag/status`, `/api/genesis/*`
- GeoDNS: Njalla não suporta — mantido round-robin com 4 IPs (DNS já tinha os 4 IPs)
- Persistência assíncrona SQLite: batch write queue com BLAKE3 ordering e commit ACID
- Benchmark completo do cluster — load test final 0% erros

## Decisões técnicas tomadas
- **FastAPI em vez de gevent**: uvicorn ASGI nativo é mais correto que monkey-patching; gevent removido de todos os nós
- **Upstream local-only**: cada nó serve só os seus backends via loopback — elimina latência cross-node e hot-server no EU
- **Batch write queue 50ms**: SQLite liberta o lock uma vez por janela de 50ms; ordenação por BLAKE3 key garante determinismo entre nós; em falha → rollback + gossip resync
- **202 Accepted em `/api/mine`**: a resposta é emitida após validação criptográfica completa (Dilithium3 + Sentinela + priority) mas antes do I/O SQLite — correto para DAG assíncrono
- **`_update_topology_memory()` em `/api/peer/vertex`**: memória é a fonte de verdade imediata; `_atualizar_topologia()` do motor não é chamada (evita SQLite síncrono dentro do handler)
- **GeoDNS adiado**: round-robin funciona; GeoDNS real requer Cloudflare ou Route53 — decisão: manter Njalla por ora
- **OpenClaw confirmado como módulo antigo** — não existe no codebase actual

## Problemas resolvidos
- EU era o único nó a servir ~70% do tráfego (outros backends inacessíveis por least_conn favorecer loopback do EU) → resolvido com nginx local-only em todos os nós
- SQLite serializava writes, criando bottleneck artificial numa DAG assíncrona → resolvido com batch write queue
- Python 3.12 (EU/SIN): conflito `typing_extensions` no pip → resolvido com `--ignore-installed`
- T13 fundação no sandbox falhava: payload de teste sem campo `site` → corrigido adicionando `"site": "https://example.com"` ao payload

## Arquivos criados/modificados
- `D:\PROJETO_Plegma_DAG\PLEGMA_CORE\core_api.py` — criado (FastAPI, 1171 linhas); deployado em sandbox + 4 nós produção
- `D:\PROJETO_Plegma_DAG\TESTS\sandbox_diario.py` — payload T13 corrigido (`site` field adicionado)
- `/etc/systemd/system/plegma-core*.service` (todos os nós) — ExecStart atualizado para `core_api.py`
- `/etc/nginx/sites-available/api.plegmadag.com` (todos os nós) — upstream `plegma_cluster` → `127.0.0.1` local only

## Estado atual
- Versão do app: sem alterações Flutter nesta sessão
- Build pendente: não
- Servidores: FastAPI + uvicorn activo em todos os 10 backends; nginx local-only + micro-cache em todos os 4 nós
- Sandbox: 16/16 testes PASS
- Cluster load test: 399 req/s status / 302 req/s mine / 371 req/s social — 0% erros

## Próximos passos
1. **Após 09/05/2026**: medir TPS real via `/api/mine` quando TESTNET terminar — validar batch writer em produção
2. **GeoDNS** (opcional): migrar DNS para Cloudflare (anycast gratuito) ou Route53 (~$2/mês) para routing geográfico real
3. **Console Admin E4–E7**: validar abas TESTNET, SERVIÇOS, FUNDAÇÃO; ajustes visuais; deploy final
4. **Instalar APK v1.10.0** no celular e testar validador 24h + QR login
5. **Shield Pack Linux build**: executar `build_linux.sh` em VM Linux
