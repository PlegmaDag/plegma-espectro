# Sessão 2026-05-02 — Bloco 1

## Tópicos discutidos
- Continuação da investigação do problema "app não conecta à rede / não gera carteira / não activa validador"
- Auditoria de segurança completa do projecto (servidores externos, SSH, chaves)
- Build APK v1.14.1 e deploy para landing
- Diagnóstico de skill `/fechar-sessao` não visível no CLI

## Decisões técnicas tomadas
- **Flutter storage mismatch** identificado como causa-raiz do validador não activar:
  - `validator_bg_service.dart` usava `encryptedSharedPreferences: true`
  - `StorageService` usa `encryptedSharedPreferences: false` (Android Keystore)
  - Dois backends diferentes → address sempre null → heartbeat nunca enviado
- **Migração de APK legado**: adicionado `StorageService.migrarStorageLegado()` para migrar dados do backend antigo (true) para o novo (false) em primeiro boot
- **SSH restrito a IP admin**: porta 22 em todos os 5 servidores agora só aceita `91.126.186.40`
- **Admin key** removida de `deploy.ps1` e movida para `admin_key.local`
- **Skills Claude Code**: skills em `~/.claude/skills/` precisam de ficheiro espelho em `~/.claude/commands/` para serem reconhecidas pelo CLI

## Problemas resolvidos
- `validator_bg_service.dart:145` — `encryptedSharedPreferences: true` → `false` ✅
- `StorageService.migrarStorageLegado()` criado — migração automática no boot ✅
- `boot_screen.dart._verificar()` — chama migração antes de `carteiraConfigurada()` ✅
- `peers_servidor.json` com IP desconhecido `100.89.89.28` apagado ✅
- Porta 2222 aberta no MAL sem justificação → fechada ✅
- `$ADMIN_KEY = "13312112"` hardcoded no `deploy.ps1` → movido para `admin_key.local` ✅

## Arquivos criados/modificados
- `D:\PROJETO_Plegma_DAG\plegma_app\lib\services\validator_bg_service.dart` — linha 145 corrigida
- `D:\PROJETO_Plegma_DAG\plegma_app\lib\services\storage_service.dart` — `migrarStorageLegado()` adicionado
- `D:\PROJETO_Plegma_DAG\plegma_app\lib\screens\boot\boot_screen.dart` — chamada de migração no boot
- `D:\PROJETO_Plegma_DAG\deploy.ps1` — `$ADMIN_KEY` substituído por leitura de ficheiro local
- `D:\PROJETO_Plegma_DAG\admin_key.local` — criado (não versionar)
- `D:\PROJETO_Plegma_DAG\PLEGMA_LANDING\download\PLEGMA-v1.14.1.apk` — APK actualizado (76MB)
- `D:\PROJETO_Plegma_DAG\PLEGMA_LANDING\index.html` — link corrigido para PLEGMA-v1.14.1.apk
- `C:\Users\Alves\.claude\commands\fechar-sessao.md` — criado para CLI
- APAGADO: `D:\PROJETO_Plegma_DAG\PLEGMA_CORE\peers_servidor.json`

## Estado atual
- Versão do app: v1.14.1+30
- Build pendente: não (build feito nesta sessão)
- Servidores: EUR activo (todos os serviços UP); BR/MAL/SIN/SBX activos
- UFW SSH: porta 22 restrita a 91.126.186.40 em todos os 5 nós ✅
- APK na landing: PLEGMA-v1.14.1.apk ✅

## Próximos passos
1. **Rebuild APK + testar no device** — confirmar que validator activa e carteira é gerada após fix storage
2. **Webhooks Discord** — rodar manualmente os 2 webhooks em `plegma-espectro/.env` (painel Discord)
3. **Deploy landing + APK para EUR** — `.\deploy.ps1 -SkipCore` para enviar o APK e landing actualizada
4. **E7 Console Master** — confirmado feito pelo utilizador, actualizar roadmap como ✅
5. **Pré-Genesis** — comprometer data de audit externo + nomear parceiro P2P Foundation
