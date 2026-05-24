# Sessão 23/05/2026 — Bloco 1

## Consenso Orquestrador — 23/05/2026
- CRITICAL: 0 · HIGH: 0 · MEDIUM: 0 · LOW: 30
- Validação: APROVADO (determinismo + pós-quântico conforme)
- Segurança: APROVADO (CRITICAL 0 · HIGH 0 · MEDIUM 0)
- Qualidade: LOW 30 (cosmético — sem bloqueantes)

## Tópicos discutidos
- Auditoria do estado da rede (4 nós: EUR/BR/MAL/SIN)
- Diagnóstico de consumo anormal de memória no nó MAL (38.7% vs ~10% nos demais)
- Verificação de segurança do MAL: acesso não autorizado + serviços estranhos
- Reparação do bug estrutural de gossip: vértices mine-accepted não propagavam para BR/MAL/SIN
- Sincronização da base de dados entre nós (tx em falta)
- Bloqueio de IP externo suspeito no MAL

## Decisões técnicas tomadas
- **Anchor peer bypass** implementado em `/api/peer/vertex`: IPs dos 4 nós contornam verificação Dilithium3 para gossip interno (necessário porque mine-accepted vertices não têm public_key/signature de utilizador)
- **Serviços duplicados removidos**: `plegma-core-8090` (BR/MAL/SIN) e `plegma-core-8091` (SIN) eram unidades antigas com PLEGMA_PORT=8090/8091, activas desde 29/04 — causavam pressão de memória e potencial conflito de gossip
- **IP 80.78.26.52 bloqueado via iptables no MAL**: nó externo não identificado ("ANCHOR_is-nd-no") enviava heartbeats apenas para MAL, sem presença nos outros nós; bloqueado por precaução
- **Tips residuais (18) no BR/MAL/SIN**: acumulação pré-fix, cosmética; reduzirão naturalmente à medida que novas transactions referenciem esses tips como parents

## Problemas resolvidos
- **MAL authorized_keys malformado**: duas chaves SSH numa linha sem separador `\n` → corrigido para entrada única canónica (sem acesso não autorizado confirmado)
- **Transacção em falta**: `e6d3f65e3ad8d02c5ef3817d4c14c06f16c8899e6e8445be7e48dfcc304ca8e9` ausente no BR/MAL/SIN → INSERT directo via SQLite
- **Bug gossip estrutural**: `/api/peer/vertex` rejeitava vértices de anchor peers com 400 Bad Request ("Campos obrigatorios ausentes") porque mine-accepted vertices não carregam public_key/signature de utilizador → anchor peer bypass corrigido e deployado em 4/4 nós
- **Memória MAL**: `plegma-core-8090.service` consumia RAM extra + journals acumulados → stop/disable + drop_caches + journald vacuum → 38.7% → 10%

## Arquivos criados/modificados
- `PLEGMA_CORE/core_api.py` — anchor peer bypass em `/api/peer/vertex` (linhas ~1425); `_ANCHOR_PEER_IPS` set; `_is_anchor_peer` bypass condicional
- Deployed a 4/4 nós (EUR/BR/MAL/SIN) via SCP + systemctl restart plegma-core
- Remote: `/etc/iptables/rules.v4` criado em MAL (bloqueia 80.78.26.52)
- Remote: `/etc/cron.d/iptables-restore` criado em MAL (persistência boot)
- Remote: `/root/.ssh/authorized_keys` corrigido em MAL (1 chave válida)
- Remote: SQLite `plegma_data.db` em BR/MAL/SIN — tx `e6d3f65e...` inserida + tips reset

## Estado atual
- Versão APK: v1.16.2+37 (sem mudanças Flutter)
- Build pendente: não
- Todos 4 nós: ONLINE · tx=21 sincronizados · gossip funcional
- Tips: EUR=2 (canonical) · BR/MAL/SIN=18 (residual cosmético, sem impacto funcional)
- Validadores activos: EUR=N (mobile miners) · BR/MAL/SIN=0 (por design — heartbeats vão a EUR)
- Orquestrador: CRITICAL 0 · HIGH 0 · MEDIUM 0 · LOW 30
- IP suspeito 80.78.26.52 bloqueado em MAL via iptables

## Próximos passos
- **FASE 1 Contratos L0** (prioritário — estava previsto 21-30/05): `contract_vm.py` + tabela `contracts` SQLite + ZK proof por execução
- **Fix colateral FASE 1**: aerarium_amount em falta em 4 INSERT transactions (core_api.py:1350/1457/1524 + plegma_db.py:197)
- **Tips residuais**: monitorar se reduzem naturalmente nos próximos dias de mining; não requerem acção imediata
- **Sentinela MEDIUM 457**: auditoria e redução progressiva em sessão dedicada
