# Sessão 2026-05-09 — Bloco 1

## Tópicos discutidos
- Verificação e activação do monitor de pagamentos Polygon (USDC → PLG-G)
- Diagnóstico de falha de RPC Polygon em todos os 4 servidores
- Compatibilidade web3 v6 (EUR/SIN) vs v7 (BR/MAL) — parâmetros camelCase vs snake_case
- Pre-launch sweep completo às vésperas do lançamento às 18h
- Confirmação de carteira Genesis Pool correcta: `0xd8422d6936be77179dc33c7c2ffceef4c34fb183`

## Decisões técnicas tomadas
- **RPC fallback list**: substituídos `1rpc.io/matic`, `ankr`, `blast` (todos falhados) por: `polygon.drpc.org`, `rpc-mainnet.matic.quiknode.pro`, `polygon-bor-rpc.publicnode.com`, `polygon.api.onfinality.io/public`, `polygon.rpc.subquery.network/public`
- **Compatibilidade web3 v6/v7**: função `_get_logs()` detecta versão major e usa `fromBlock`/`toBlock` (v6) ou `from_block`/`to_block` (v7) conforme necessário
- **Monitor thread nomeada**: `threading.Thread(name="monitor_pagamentos", ...)` para facilitar inspecção via `/proc`
- **Retry com reconexão**: após 5 falhas consecutivas, tenta reconectar ao RPC automaticamente

## Problemas resolvidos
- **RPC `1rpc.io/matic` morto**: SSL error em EUR/SIN, rate limit em BR/MAL — substituído por lista de fallback
- **Ankr passou a exigir API key** (aconteceu durante a sessão): removido da lista primária
- **web3 v6 incompatibilidade**: `get_logs(from_block=..., to_block=...)` lançava `TypeError` silencioso em EUR/SIN com web3 6.15.1 — corrigido com detecção de versão
- **Monitor nunca activado**: bloco inicial não era salvo porque o RPC falhava na primeira conexão — agora com fallback, conecta e salva o bloco de referência

## Arquivos criados/modificados
- `/root/PLEGMA_CORE/monitor_pagamentos.py` — reescrito em todos os 4 servidores (backup `.bak` criado)
- `D:\PROJETO_Plegma_DAG\PLEGMA_ORCHESTRATOR\fix_monitor_rpc.py` — script de deploy do monitor
- `D:\PROJETO_Plegma_DAG\PLEGMA_ORCHESTRATOR\update_rpc_list.py` — script de patch da lista RPC
- `D:\PROJETO_Plegma_DAG\PLEGMA_ORCHESTRATOR\verify_monitor_final.py` — script de verificação
- `D:\PROJETO_Plegma_DAG\PLEGMA_ORCHESTRATOR\launch_sweep.py` — sweep pré-lançamento
- `D:\PROJETO_Plegma_DAG\PLEGMA_ORCHESTRATOR\chk_monitor_live.py` — diagnóstico de threads
- `D:\PROJETO_Plegma_DAG\PLEGMA_ORCHESTRATOR\chk_monitor_proc.py` — inspecção do processo
- `D:\PROJETO_Plegma_DAG\PLEGMA_ORCHESTRATOR\chk_monitor_code.py` — leitura do código remoto
- `D:\PROJETO_Plegma_DAG\PLEGMA_ORCHESTRATOR\chk_rpc_compat.py` — teste de compatibilidade
- `D:\PROJETO_Plegma_DAG\PLEGMA_ORCHESTRATOR\restart_core_all.py` — restart coordenado
- `D:\PROJETO_Plegma_DAG\PLEGMA_ORCHESTRATOR\test_rpcs.py`, `test_rpcs2.py` — testes de RPC
- `D:\PROJETO_Plegma_DAG\PLEGMA_ORCHESTRATOR\chk_monitor_db.py` — verificação via DB

## Estado atual
- Versão do app: sem mudanças Flutter nesta sessão
- Build pendente: não
- Servidor: 4/4 online — core/auth/wallet/miner ACTIVE em EUR, BR, MAL, SIN
- Monitor Polygon: ATIVO — bloco atualizado a cada 60s (diff <32 blocos verificado)
- Carteira monitorada: `0xd8422d6936be77179dc33c7c2ffceef4c34fb183` (Genesis Pool)
- Supply Genesis: 10.500.000 PLG-G disponível
- Lançamento: 2026-05-09 às 18h Madrid (16h UTC)

## Próximos passos
1. **Enviar $1 USDC de teste** para `0xd8422d6936be77179dc33c7c2ffceef4c34fb183` (Polygon Mainnet) e confirmar que o monitor deteta e emite PLG-G
2. **Verificar o registo de compra** — o comprador deve ter criado uma `pending_purchase` via `POST /api/genesis/registrar` antes do envio para que o matching funcione
3. **Monitorar RPC stability** — os RPCs gratuitos podem ter rate limits variáveis; se o monitor falhar repetidamente, considerar um RPC pago ou Alchemy/Infura com chave API
4. **Após lançamento**: activar `genesis_launch_date` no DB para iniciar contagem dos 30 dias até governança
5. **Build APK** se houver actualizações ao app plegma_app antes do lançamento
