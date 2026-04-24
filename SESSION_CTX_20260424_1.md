# Sessão 2026-04-24 — Bloco 1

## Tópicos discutidos
- Simulações MiroFish (Runs A-E) para prever reacções do mercado cripto ao Genesis Reserve PLG
- Análise de resultados da única simulação completa (run_091a78c3dcdd, 19 agentes, conf. 0.6)
- Causa raiz do hang nas simulações de 61 agentes (BERT model + OASIS subprocess no Windows)
- Produção de relatório de marketing com base nos dados disponíveis
- Criação da pasta `MARKETING/` com 6 ficheiros de directrizes de lançamento
- Identificação de 3 bloqueadores críticos pré-Genesis não documentados no roadmap

## Decisões técnicas tomadas
- **Parar simulações**: Todas as runs de 61 agentes travam após inicialização BERT (~10 min de chamadas LLM, depois silêncio). Decisão: usar dados da run de 19 agentes + análise de personas.
- **Headline principal confirmado**: "Post-Quantum Bitcoin. Fair Launch. No Compromises." (sinal NIST/Dilithium3 = 0.8 positivo na simulação)
- **Narrativa bloqueada**: Fundação P2P não activar sem 1 organização nomeada (sinal fraco sem prova)
- **Tier 1 de narrativa**: PQC Bitcoin + Fair Launch Absolutista (ambos high-signal, low-skepticism)
- **3 bloqueadores adicionados ao roadmap** como itens 🟡 pré-Genesis obrigatórios

## Problemas resolvidos
- OASIS hang identificado mas não corrigido: pattern consistente — LLM activo 10 min → rate limiter sleep → silêncio. Apenas afecta runs de 61 agentes neste sistema Windows.
- Bash tool EEXIST: contornado com PowerShell para execução de simulações.
- Marketing sem dados completos: compensado com simulação parcial + análise directa de configuração de agentes.

## Arquivos criados/modificados
- `D:\PROJETO_Plegma_DAG\MARKETING\00_INDEX.md` — CRIADO (índice da pasta marketing)
- `D:\PROJETO_Plegma_DAG\MARKETING\01_narrativa_e_tagline.md` — CRIADO (tagline, hierarquia, mensagem por persona)
- `D:\PROJETO_Plegma_DAG\MARKETING\02_thread_twitter_lancamento.md` — CRIADO (12 tweets + avulso + FUD)
- `D:\PROJETO_Plegma_DAG\MARKETING\03_faq_objecoes.md` — CRIADO (5 objecções com resposta curta + longa)
- `D:\PROJETO_Plegma_DAG\MARKETING\04_checklist_pre_genesis.md` — CRIADO (bloqueadores, timing D-14 a D+30, métricas)
- `D:\PROJETO_Plegma_DAG\MARKETING\05_post_reddit_dd.md` — CRIADO (post DD completo EN + template PT)
- `D:\PROJETO_Plegma_DAG\mirofish_research_runs.md` — ACTUALIZADO (Run A: conf. 0.6, NIST 0.8)
- `D:\PROJETO_Plegma_DAG\PROJECT_MEMORY\11_known_issues_roadmap.md` — ACTUALIZADO (3 bloqueadores + entrada "Alterações Recentes")

## Estado actual
- Versão do app: v1.12.0 (sem mudanças Flutter nesta sessão)
- Build pendente: não
- Servidor: status não verificado nesta sessão (sem mudanças de backend)

## Próximos passos
- **CRÍTICO**: Comprometer data pública do audit externo (publicar como post fixado antes de 9 Mai)
- **CRÍTICO**: Nomear 1 parceiro real da Fundação (sem nome, narrativa humanitária não funciona)
- **CRÍTICO**: Documentar o endereço de burn on-chain e publicar como guia técnico
- Publicar comparação técnica PLG vs QRL vs IOTA (D-14 = 25 Abr 2026)
- Executar checklist de conteúdo de `04_checklist_pre_genesis.md` na ordem indicada
