# Sessão 29/04/2026 — Bloco 3

## Tópicos discutidos
- Falha de autenticação QR ("desafio expirado ou inexistente") — causa raiz e correcção
- Diagnóstico de serviço auth parado sem reinício automático (systemd mal configurado)
- Criação de sequência de restart em 3 fases com watchdog systemd
- Análise de consenso DAG para tolerância a partições e merge determinístico
- Deploy rolling zero-downtime via cluster DNS Njalla
- Integração do rolling deploy no ritual fechar-sessao
- Comportamento de abort em erro crítico durante deploy
- Uptime da rede vs uptime do processo/nó

## Decisões técnicas tomadas
- **Nonces persistidos no SQLite**: nonces de autenticação eram apenas em memória → restart do auth_server limpava todos os desafios activos. Solução: `salvar_nonce_auth()` + fallback `obter_nonce_auth()` ao arrancar o processo.
- **`StartLimitIntervalSec` na secção `[Unit]`**: estava na secção `[Service]` (ignorado pelo systemd). Movido para `[Unit]` — agora o serviço reinicia sempre sem limite.
- **Watchdog externo via timer systemd**: `plegma-watchdog.timer` corre a cada 60s como camada de segurança independente do systemd.
- **DAG tips como `set` com `threading.Lock()`**: lista mutável não era thread-safe sob carga concorrente. Substituída por set + lock.
- **Merge determinístico por (timestamp, tx_hash)**: após isolamento de nó, os vértices em falta são ordenados de forma determinística antes do insert — a mesma DAG reconstrói-se igual em qualquer nó.
- **`iniciar_loop_reconexao(dag, 300)`**: thread de background ressincroniza com todos os peers a cada 5 min — cobre reconexão após isolamento.
- **Rolling deploy cluster + DNS Njalla**: deploy nó a nó (BR→MAL→SIN→EU), remove do DNS antes de reiniciar, re-adiciona após health check. Rede nunca offline.
- **Abort com TTL sempre restaurado**: bloco `try/finally` garante que o Fase 3 (restaurar TTL=300s) corre mesmo em abort — antes o `throw` saía sem restaurar.
- **`network_start_ts` separado de `motor_start_ts`**: o uptime da rede usa `FASE_ZERO_START_TS` (constante de 9 Abr 2026), não o timestamp do processo. Admin panel actualizado para mostrar os dois.

## Problemas resolvidos
- Auth QR: "desafio expirado ou inexistente" após restart do serviço → nonces agora persistidos no SQLite
- Serviço auth não reiniciava automaticamente → `StartLimitIntervalSec=0` movido para secção `[Unit]`
- `restart_service.sh` SSH: `2>&1 | Out-Null` escondia erros críticos → saída capturada + `$LASTEXITCODE` verificado
- Rolling deploy abortava sem restaurar TTL DNS → bloco `try/finally` em `deploy_rolling.ps1`
- Uptime do admin panel resetava a cada restart → separado em `network_start_ts` (fixo) e `motor_start_ts` (por nó)

## Arquivos criados/modificados
- `D:\PROJETO_Plegma_DAG\PLEGMA_CORE\plegma_db.py` — funções nonce: `salvar_nonce_auth`, `obter_nonce_auth`, `marcar_nonce_verificado`, `remover_nonce_auth`, `limpar_nonces_expirados`
- `D:\PROJETO_Plegma_DAG\PLEGMA_CORE\auth_server.py` — NonceStore com fallback ao DB após restart
- `D:\PROJETO_Plegma_DAG\PLEGMA_CORE\core_dag.py` — tips como set + threading.Lock + trim determinístico
- `D:\PROJETO_Plegma_DAG\PLEGMA_CORE\gossip.py` — merge determinístico, `_aceitar_vertice` recursivo, `iniciar_loop_reconexao`
- `D:\PROJETO_Plegma_DAG\PLEGMA_CORE\core_api.py` — `iniciar_loop_reconexao` no startup; `network_start_ts` nos endpoints /api/status e /api/cluster/status
- `D:\PROJETO_Plegma_DAG\PLEGMA_CORE\restart_service.sh` — NOVO: restart 3 fases (systemctl / pkill+start / port-flush+fork)
- `D:\PROJETO_Plegma_DAG\PLEGMA_CORE\plegma_watchdog.sh` — NOVO: watchdog 5 serviços, log /tmp/watchdog.log
- `D:\PROJETO_Plegma_DAG\PLEGMA_LANDING\admin\index.html` — uptime da rede vs uptime do nó separados
- `D:\PROJETO_Plegma_DAG\deploy_rolling.ps1` — NOVO: rolling deploy zero-downtime + abort com relatório
- `D:\PROJETO_Plegma_DAG\njalla_token.local` — NOVO (não versionado)
- `D:\PROJETO_Plegma_DAG\deploy.ps1` — SystemD StartLimitIntervalSec fix + watchdog setup
- `C:\Users\Alves\.claude\skills\fechar-sessao\SKILL.md` — Etapa 7 rolling deploy adicionada

## Estado atual
- Versão do app: sem mudanças Flutter esta sessão
- Build pendente: não
- Servidor: aguarda deploy rolling para aplicar todas as correcções

## Próximos passos
- Executar `.\deploy_rolling.ps1` para aplicar todas as correcções desta sessão aos 4 nós
- Verificar session affinity bug: sessão criada no EU retorna 401 se próximo request vai para BR (SQLite por nó)
- Shannon pentest: executar apenas dias antes da produção (~$50, pós-TESTNET 09/05/2026)
- Testar autenticação QR após deploy para confirmar fix dos nonces
