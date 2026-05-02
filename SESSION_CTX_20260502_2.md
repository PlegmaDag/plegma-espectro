# Sessão 2026-05-02 — Bloco 2

## Tópicos discutidos
- Actualização dos webhooks Discord no `.env` (canais #build-logs e #alertas)
- Diagnóstico e correcção de múltiplos bugs no pipeline `deploy.ps1`
- Correcção do link de download do APK (case-sensitivity Linux)

## Decisões técnicas tomadas
- **BOM PowerShell 5.1**: `$OutputEncoding = New-Object System.Text.UTF8Encoding $false` não é suficiente no PS 5.1 Desktop. Solução definitiva: adicionar `:` (no-op bash) como primeira linha de cada here-string enviada por pipe a SSH — BOM corrompe a linha 1 mas `:` é inofensivo.
- **Health check sandbox**: `curl -w "%{http_code}"` retornava `200\r` (CR invisível via pipe PS→SSH) causando falha na comparação bash `[ "$CODE" = "200" ]`. Corrigido com `tr -dc '0-9'` antes da comparação.
- **Variável `$host` reservada**: `Wait-HealthCheck` usava `$host` como parâmetro, colide com variável automática read-only do PS 5.1. Renomeado para `$remoteHost`.
- **Fluxo deploy**: sandbox aprovado → produção automática (sem confirmação manual). Cada nó de produção validado individualmente: 10s + `systemctl is-active` + HTTP 200 antes de avançar.
- **Terminal não fecha**: `exit 1/0` substituídos por `throw "DEPLOY_ABORT/DONE"` dentro do bloco `try` para garantir que `finally` (com `Read-Host`) executa sempre.
- **APK case**: padronizado para minúsculas `plegma-v` em `deploy.ps1`, `index.html` e `ajuda/index.html`. Linux é case-sensitive — `PLEGMA-v1.14.2.apk` resulta em 404.

## Problemas resolvidos
- Deploy parava no sandbox com `❌ SANDBOX: falhou` apesar de HTTP 200 — causa: `$CODE` com CR oculto
- Deploy não avançava para produção — causa: `Read-Host` de confirmação bloqueava pipeline
- `plegma-core: inactive` nos nós de produção — causa: BOM a corromper `cat > /etc/systemd/...` (primeira linha do here-string)
- `$host` variável read-only no PS 5.1 abortava health check de produção
- Link APK retornava 404 — `PLEGMA-v1.14.2.apk` no HTML vs `plegma-v1.14.2.apk` no servidor Linux

## Arquivos criados/modificados
- `D:\PROJETO_Plegma_DAG\plegma-espectro\.env` — webhooks Discord actualizados
- `D:\PROJETO_Plegma_DAG\deploy.ps1` — 10+ fixes (BOM, health check, $host, auto-proceed, exit→throw, APK case)
- `D:\PROJETO_Plegma_DAG\PLEGMA_LANDING\index.html` — link APK minúsculas
- `D:\PROJETO_Plegma_DAG\PLEGMA_LANDING\ajuda\index.html` — link APK minúsculas + versão corrigida para v1.14.2

## Estado actual
- Versão do app: v1.14.2 (sem mudanças Flutter nesta sessão)
- Build pendente: não
- Deploy: funcional — sandbox → 4 nós produção (EUR/BR/MAL/SIN) com validação por nó
- APK download: corrigido (link e ficheiro em minúsculas)
- Webhooks Discord: actualizados para novos canais

## Próximos passos
- Verificar HTTPS/SSL em `api.plegmadag.com` (certificado pendente)
- Testar fluxo completo de criação de perfil social (login → `/social/criar-perfil/` → feed)
- Activação do Genesis em 09/05/2026 18:00 CEST: `POST /api/rede/ativar`
