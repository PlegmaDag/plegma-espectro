# Sessão 15/04/2026 — Bloco 1

## Tópicos discutidos
- Diagnóstico e correção do executável do minerador Windows (não abria)
- Implementação de instância única no minerador (single-instance mutex)
- Correção de 4 bugs CSS/HTML na página Finanças
- Revisão de conteúdo da página Finanças (estatutos, cards, descrições)
- Remoção de ideia obsoleta no LABS
- Adição de nova ideia COFRE QUÂNTICO no LABS

## Decisões técnicas tomadas
- **Minerador exe — crash silencioso:** Com `console=False` no PyInstaller, `sys.stdout` e `sys.stderr` são `None`. O exe crashava em 2 pontos: (1) `sys.stdout.buffer` no `__main__` → `AttributeError`; (2) `logging.StreamHandler(sys.stderr)` → crash na primeira emissão. Solução: guards `if sys.stdout is not None` e `if sys.stderr is not None`. `_LOG_PATH` migrado para `os.path.dirname(sys.executable)` quando `sys.frozen=True`.
- **Single-instance via Windows Named Mutex:** `ctypes.windll.kernel32.CreateMutexW(None, False, "Global\\PLEGMA_Minerador_V4_Instance")` + `GetLastError() == 183` (ERROR_ALREADY_EXISTS). Bloqueia antes de criar qualquer janela Tkinter. Mostra messagebox de erro e `sys.exit(0)`.
- **Finanças — Justice Cap:** Removido conceito de "10% máximo por Prover". Substituído por descrição correta: trabalho equitativo fracionado por latência geográfica (prioridade regional: Brasil→Brasil, Espanha→Espanha, fallback global).
- **LABS — COFRE QUÂNTICO:** Nova ideia registada. Mecanismo: fragmentação de documentos → distribuição pelos mineradores → compactação ZK-SNARK 22KB. Acesso triplo: hash + carteira PLG + senha. Preço a ser decidido por votação.

## Problemas resolvidos
- Exe do minerador não abria (crash silencioso por `sys.stdout=None` com `console=False`)
- Múltiplas instâncias do minerador podiam ser abertas em simultâneo
- `--purple` CSS não definido → seals "Lattice-Based" e "1 Person · 1 Vote" sem cor
- `.footer-legal` sem CSS → links do rodapé sem estilo
- `@media (max-width: 600px)` duplicado na página Finanças
- Nav + testnet ticker sobrepostos (ambos em `top: 0`)
- Título secção errado `§3 · §13` → `§13`
- Descrição Justice Cap incorreta (dizia "10% máximo" — conceito não existe no protocolo)

## Arquivos criados/modificados
- `D:\PROJETO_Plegma_DAG\PLEGMA_CORE\miner\miner_engine.py` — guard sys.stderr + _LOG_PATH frozen
- `D:\PROJETO_Plegma_DAG\PLEGMA_CORE\miner\minerador_gui.py` — guard sys.stdout + single-instance mutex
- `D:\PROJETO_Plegma_DAG\PLEGMA_CORE\miner\dist\PLEGMA-Minerador-v2.0.exe` — rebuild (33.1 MB)
- `D:\PROJETO_Plegma_DAG\PLEGMA_CORE\miner\dist\plegma-minerador-v2.0-windows.zip` — rebuild
- `D:\PROJETO_Plegma_DAG\PLEGMA_LANDING\download\plegma-minerador-v2.0-windows.zip` — atualizado
- `D:\PROJETO_Plegma_DAG\PLEGMA_LANDING\financas\index.html` — 7 fixes CSS+conteúdo
- `D:\PROJETO_Plegma_DAG\PLEGMA_LANDING\labs\index.html` — ideia mobile dashboard removida + COFRE QUÂNTICO adicionado

## Estado atual
- Versão do app Flutter: v1.10.0+23 (sem mudanças esta sessão)
- Build APK pendente: NÃO
- Minerador Windows: v2.0 rebuild 15/04/2026 — single-instance + crash fix
- Servidor: TESTNET ativo até 09/05/2026 18:00 CEST

## Próximos passos
1. **Ícone do minerador exe** — criar SVG do símbolo "Plegma minerador" (snowflake lattice) via PIL e rebuildar exe com novo .ico (bloqueado: utilizador interrompeu render, confirmar abordagem)
2. **Instalar APK v1.10.0** no celular e testar validador 24h (bateria + Doze mode)
3. **Testar QR login** no dashboard (FIX-F ML-DSA-65 em prod)
4. **Console Admin E4/E5/E6** — validar abas TESTNET, SERVIÇOS, FUNDAÇÃO
