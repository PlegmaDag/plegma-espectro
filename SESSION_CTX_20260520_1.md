# Sessão 20 Mai 2026 — Bloco 1

## Consenso Orquestrador — 20/05/2026
- CRITICAL: 0 · HIGH: 0 · MEDIUM: 0 · LOW: 21
- Validação: 0 críticos · 0 avisos · 5 fluxo-DAG (false positives confirmados)
- Segurança: CRITICAL=0 HIGH=0 MEDIUM=0 LOW=21 (DART_CATCH_EMPTY intencional em Flutter)
- Qualidade: 0 observações em 28 ficheiros
- DAG_AUDITOR: CRÍTICO=0 ALTO=0 MÉDIO=3 (aceitas=0 em relay nodes — cosmético)

## Tópicos discutidos
- plegmadag.com/app retornava 404 (link na landing apontava para pasta inexistente)
- Auditoria completa frontend-backend: Console, Dashboard, Admin
- Mapeamento de todas as chamadas fetch() para endpoints do backend
- Identificação e correcção de fluxos desconectados

## Decisões técnicas tomadas
- Criada `PLEGMA_LANDING/app/index.html` em vez de build Flutter web (mais simples, imediato)
- PLG transfers do web dashboard informam utilizador que precisam do app mobile (sem Dilithium3 no browser)
- `_adminKey` uniformizado: sempre token de sessão emitido por `/api/admin/auth/password`, nunca password raw
- `POST /api/genesis/burn` adicionado ao core_api.py com `_check_admin` obrigatório
- `carregarInscricoes()` guardado com `if (!_adminKey) return;` para evitar chamadas 403 desnecessárias

## Problemas resolvidos
- plegmadag.com/app 404 → página criada com download Android + iOS em breve
- `desvincularProver()` stub → POST real a `/wallet/desvincular_prover`
- `executarEnvio()` sem Authorization → header adicionado + mensagem clara ao utilizador
- `adminLogin()` no Dashboard e Console usavam password raw como admin_key → corrigido para usar token
- `carregarDownloads()` no Dashboard usava sessionStorage key antiga → passa a usar token correcto
- `confirmarBurn()` chamava POST /api/genesis/burn que não existia → endpoint adicionado

## Arquivos criados/modificados
- D:\PROJETO_Plegma_DAG\PLEGMA_LANDING\app\index.html — CRIADO (página app)
- D:\PROJETO_Plegma_DAG\PLEGMA_LANDING\dashboard\index.html — desvincularProver, executarEnvio, adminLogin, carregarDownloads
- D:\PROJETO_Plegma_DAG\PLEGMA_LANDING\console\index.html — adminLogin, carregarInscricoes guard, session restore
- D:\PROJETO_Plegma_DAG\PLEGMA_CORE\core_api.py — POST /api/genesis/burn adicionado
- D:\PROJETO_Plegma_DAG\PLEGMA_LANDING\blog\index.html — novo artigo 20/05
- D:\PROJETO_Plegma_DAG\PLEGMA_LANDING\social\index.html — novo post mesh social
- D:\PROJETO_Plegma_DAG\PROJECT_MEMORY\11_known_issues_roadmap.md — secção 20/05 adicionada

## Estado atual
- Versão APK: 1.16.2+37 (sem mudanças Flutter)
- Build pendente: não
- Servidor: 4/4 nós ACTIVE — core_api.py (com POST /api/genesis/burn) deployado
- EUR: txs=12, aceitas=2, tips=2, score=8/8
- BR/MAL/SIN: score=7/8 (aceitas=0 em relay — cosmético)
- SECURITY: CRITICAL=0 HIGH=0 MEDIUM=0 LOW=21
- CODER: 0 observações em 28 ficheiros

## Próximos passos
1. BR/MAL/SIN score=7/8 → aceitas=0 em relay nodes (cosmético, baixa prioridade)
2. Validation agent DAG-FLOW flags (5x) — false positives a limpar no agente de validação
3. `activate_governance` e `liquidity_injection` não têm `_check_admin` (endpoints admin sem auth)
4. iOS app store submission (na página /app/ está marcado como "em breve")
5. PLG web transfer: considerar endpoint session-only ou remover UI de transfer PLG do web dashboard
