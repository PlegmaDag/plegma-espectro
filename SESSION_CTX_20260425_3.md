# Sessão 25 ABR 2026 — Bloco 3

## Tópicos discutidos
- NAV completo ausente na página `/ajuda/`
- Ticker testnet a sobrepor a NAV sticky quando ativo

## Decisões técnicas tomadas
- Substituir NAV mínimo da `/ajuda/` pelo NAV padronizado do site (logo GIF + hamburger + todos os links + botão DASHBOARD)
- Incluir `auth.js` na `<head>` da ajuda (necessário para o botão DASHBOARD funcionar)
- Corrigir o `showTicker()` para ajustar `nav.style.top = '26px'` e `nav-links.style.top = '82px'` quando o ticker testnet fica ativo (evita que o fixed ticker sobreponha a sticky nav ao fazer scroll)
- Adicionar CSS completo do hamburger mobile com animação X (`nav-open`) e dropdown fixo

## Problemas resolvidos
- Página `/ajuda/` não exibia NAV de navegação do site — corrigido com NAV padronizado completo
- Ticker testnet (position: fixed, z-index 99999) cobria a sticky nav ao fazer scroll — corrigido ajustando o `top` da nav via JS quando o ticker ativa
- Link AJUDA marcado como `.active` na nova nav

## Arquivos criados/modificados
- `D:\PROJETO_Plegma_DAG\PLEGMA_LANDING\ajuda\index.html` — NAV completo substituído, auth.js adicionado, CSS hamburger/nav-links atualizado, showTicker() corrigido

## Estado atual
- Versão do app: v1.12.0+25 (sem mudanças Flutter nesta sessão)
- Build pendente: não (sem mudanças Flutter)
- Servidor: plegma-core ativo em EUR/BR/MAL/SIN (deploy pendente desta sessão)

## Próximos passos
- Deploy da landing page `ajuda/index.html` para os servidores (via `deploy.ps1`)
- Verificar se outras páginas com NAV mínimo precisam do mesmo tratamento (ex: `termos/`, `privacidade/`, `cookies/`)
- Testar QR login no dashboard (FIX-F: ML-DSA-65)
- Instalar APK v1.12.0 no celular e testar recovery com seed phrase real
