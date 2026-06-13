# PLEGMA DAG — RELATÓRIO DE AUDITORIA DE SEGURANÇA
**Data:** 2026-03-29
**Build:** BUILD 009
**Testes executados:** 90
**Score de segurança:** 72% (65 aprovados / 25 reprovados)

---

## SUMÁRIO EXECUTIVO

A bateria de 90 testes automatizados cobriu 7 blocos críticos:
- Sentinela (Vigia / Crivo / Escudo)
- Auth Server (NonceStore, Rate Limiter, Dilithium3)
- Core VM (endpoints REST, validação de inputs)
- Wallet Server
- Genesis Contract
- App Flutter (Dart)
- Testes de resistência (edge cases, fuzzing, race conditions)

**Resultado geral: o núcleo de segurança está sólido, mas há vulnerabilidades críticas abertas nas camadas de transação e autenticação mobile.**

---

## RESULTADOS POR SEVERIDADE

| Severidade | Aprovados | Reprovados |
|---|---|---|
| CRITICAL | 15 | 8 |
| HIGH | 19 | 8 |
| MEDIUM | 8 | 8 |
| INFO | 23 | 1 |

---

## VULNERABILIDADES CRÍTICAS (8)

### CVE-PLEGMA-001 — `/api/mine` sem verificação Dilithium3
- **Arquivo:** `core_vm.py:582-598`
- **Impacto:** Qualquer ator pode submeter um vértice ao DAG com `signature: "fake"`. A assinatura é recebida mas nunca verificada criptograficamente.
- **Ataque:** `POST /api/mine {"sender":"PLG...","receiver":"PLG...","amount":1000,"signature":"x","public_key":"y"}` → aceito.
- **Fix:** Integrar `LatticeShield.verify_transaction()` antes de aceitar o vértice.
- **Prioridade:** BLOQUEIA abertura pública da rede.

### CVE-PLEGMA-002 — `/api/peer/vertex` insere dados no DAG sem validação
- **Arquivo:** `core_vm.py:601-613`
- **Impacto:** Qualquer peer pode poluir o DAG com transações fabricadas, corrompendo o estado da rede.
- **Ataque:** `POST /api/peer/vertex {"tx_hash":"fake_hash","parents":[],"amount":999999}` → inserido no DAG e banco.
- **Fix:** Verificar hash do vértice + assinatura Dilithium3 antes de aceitar.
- **Prioridade:** CRÍTICO — corrupção de dados do protocolo.

### CVE-PLEGMA-003 — Token de sessão em `core_vm.py` previsível
- **Arquivo:** `core_vm.py:685`
- **Impacto:** Token gerado como `PLG_TOKEN_{address}_{timestamp}` — 100% determinístico. Qualquer um que conheça o endereço e o timestamp pode forjar o token.
- **Fix:** Substituir por `secrets.token_hex(32)` e armazenar no `NonceStore` do `auth_server.py`.
- **Prioridade:** CRÍTICO — bypass total de autenticação.

### CVE-PLEGMA-004 — Escudo: bans não persistem após restart
- **Arquivo:** `sentinela.py:133-155`
- **Impacto:** `Escudo.reputation_system` é um dict em memória. Ao reiniciar o servidor, todos os nós banidos (score=-1) voltam com score=100 e stake inicial de 500 PLG.
- **Fix:** Persistir `reputation_system` no `plegma_db` e carregar no `__init__`.
- **Prioridade:** CRÍTICO — anula o sistema de slashing.

### CVE-PLEGMA-005 — `/wallet/transferir` sem autenticação
- **Arquivo:** `wallet_server.py:180-185`
- **Impacto:** Endpoint aceita transferências sem verificar se o requisitante é dono da carteira. Qualquer IP pode transferir PLG da wallet ativa.
- **Fix:** Exigir token de sessão válido e verificar correspondência com o endereço remetente.
- **Prioridade:** CRÍTICO — risco financeiro direto.

### CVE-PLEGMA-006 — Genesis `transferir_plgg` sem verificação de propriedade
- **Arquivo:** `genesis_contract.py`
- **Impacto:** Transferência de PLG-G (token de governança) sem verificar se o remetente controla a chave privada correspondente ao endereço.
- **Fix:** Exigir assinatura Dilithium3 do remetente para autorizar a transferência.
- **Prioridade:** CRÍTICO — roubo de tokens de governança.

### CVE-PLEGMA-007 — CryptoService Flutter usa SHA-256 (não Dilithium3)
- **Arquivo:** `PLEGMA_APP/lib/services/crypto_service.dart:22-43`
- **Impacto:** Chaves geradas com SHA-256 simulado, não Dilithium3. Assinaturas são `SHA-256(nonce:privKey)`. Sem segurança post-quântica real. A verificação no `auth_server.py` com Dilithium3 real irá **rejeitar toda autenticação** do app atual.
- **Fix:** Integrar via `dart:ffi` a lib C do Dilithium3 compilada para ARM64.
- **Prioridade:** CRÍTICO — bloqueia autenticação real do app em produção.

### CVE-PLEGMA-008 — `assinarNonce` Flutter usa SHA-256 (não Dilithium3)
- **Arquivo:** `PLEGMA_APP/lib/services/crypto_service.dart:48-52`
- **Impacto:** Assinatura do nonce de autenticação é apenas `SHA-256(nonce:privKey)`. Não é uma assinatura Dilithium3 válida.
- **Fix:** `Dilithium3.sign(privateKey, nonce.encode())` via FFI.
- **Prioridade:** CRÍTICO — mesmo que CVE-007.

---

## VULNERABILIDADES ALTAS (8)

### VUL-HIGH-001 — Crivo: case-sensitive em detecção de reentrância
- **Arquivo:** `sentinela.py:128-129`
- **Impacto:** `"Recursive_Call"` ou `"REENTRANCY_EXPLOIT"` (com maiúsculas) passam pelo Crivo sem bloqueio.
- **Fix:** `tx_payload.lower()` antes das verificações de substring.

### VUL-HIGH-002 — Endpoints sociais sem autenticação
- **Arquivo:** `core_vm.py:694-732`
- **Impacto:** `/api/social/post`, `/api/social/votar`, `/api/labs/proposta`, `/api/labs/votar` aceitam qualquer address sem verificar propriedade. Manipulação de votos e posts em nome de outros usuários.
- **Fix:** Exigir token de sessão válido correspondente ao author/voter.

### VUL-HIGH-003 — `/api/miner/pause` e `/resume` sem autenticação
- **Arquivo:** `core_vm.py:643-661`
- **Impacto:** Qualquer IP pode pausar ou retomar a mineração de qualquer endereço.
- **Fix:** Exigir token de sessão e verificar que o endereço corresponde ao solicitante.

### VUL-HIGH-004 — Senha hardcoded no Canal Privado
- **Arquivo:** `core_vm.py:75`
- **Código:** `_NOTAS_SENHA_HASH = hashlib.sha256(b"plegma2026").hexdigest()`
- **Impacto:** Qualquer pessoa com acesso ao código-fonte pode ler o canal privado.
- **Fix:** `os.getenv("PLEGMA_NOTAS_SENHA")` com fallback de erro, como feito para `PLEGMA_ADMIN_KEY`.

### VUL-HIGH-005 — B2 Pattern com salt estático no Flutter
- **Arquivo:** `PLEGMA_APP/lib/services/auth_service.dart:101-103`
- **Código:** `salt = 'plegma_b2_salt_$pattern'` hardcoded
- **Impacto:** Rainbow table ou brute-force offline possível pois o salt é previsível.
- **Fix:** Gerar salt aleatório no primeiro setup e armazenar no `FlutterSecureStorage`.

### VUL-HIGH-006 — Crivo: `amount` como string bypassa verificação numérica
- **Arquivo:** `sentinela.py:124`
- **Impacto:** Se `amount` chegar como string (ex: `"999999999999"`), a comparação Python `"999999999999" < 0` é `False` e `"999999999999" > 21_000_000_000` lança `TypeError` — o que pode crashar o servidor.
- **Fix:** Adicionar `if not isinstance(amount, (int, float)): return False, "Tipo inválido"`

### VUL-HIGH-007 — Crivo: `amount=NaN` bypassa verificação
- **Arquivo:** `sentinela.py:124`
- **Impacto:** `float('nan') < 0 == False` e `float('nan') > 21B == False` → NaN passa pelo Crivo sem bloqueio.
- **Fix:** `if math.isnan(amount) or math.isinf(amount): return False, "Valor inválido"`

### VUL-HIGH-008 — API URL hardcoded no app Flutter
- **Arquivo:** `PLEGMA_APP/lib/services/api_service.dart`
- **Impacto:** IP `80.78.26.52` hardcoded. Migração de servidor exige rebuild e republicação do APK.
- **Fix:** `--dart-define=API_BASE_URL=https://api.plegmadag.com` ou remote config.

---

## VULNERABILIDADES MÉDIAS (8)

| ID | Arquivo | Descrição | Fix |
|---|---|---|---|
| MED-001 | `sentinela.py` | PHR blacklist não detecta l33tspeak (`t3rr0r1sm0`) | Regex normalizado + expansão da blacklist |
| MED-002 | `core_vm.py` | Rate limit de fundação sem `threading.Lock()` (race condition) | Usar `threading.Lock()` como `_rate_limit_challenge_lock` |
| MED-003 | `core_vm.py` | `_challenges` acumula em memória (memory leak — sem cleanup thread) | Thread daemon de limpeza a cada 60s |
| MED-004 | `core_vm.py` | `X-Forwarded-For` confiado sem validação → bypass de rate limit | Confiar apenas em `X-Real-IP` definido pelo nginx |
| MED-005 | `core_vm.py` | CORS wildcard `*` em todos os endpoints (incluindo mutadores) | Restringir a `plegmadag.com` e `app.plegmadag.com` |
| MED-006 | `wallet_server.py` | Wallet de demonstração ativa em produção | Substituir por wallet real do usuário autenticado |
| MED-007 | `auth_service.dart` | Dispositivo sem biometria retorna `true` automaticamente | Exigir pelo menos PIN do sistema; rejeitar sem proteção |
| MED-008 | `sentinela.py` | Escudo registra stake fixo de 500 PLG (não reflete stake real) | Consultar stake real do nó no banco antes de registrar |

---

## O QUE ESTÁ FUNCIONANDO BEM ✅

| Componente | Resultado |
|---|---|
| Geofencing (KP, IR, SY) | 100% bloqueado — T02-T04 |
| PHR (terrorismo, darknet_market, uppercase) | Detectado — T05-T06, T08 |
| Anti-Smurfing (limite 6 dispositivos/IP) | Funcionando — T09-T11 |
| Anti-Smurfing: thread-safety sob race condition | Aprovado com 10 threads simultâneas — T90 |
| Crivo: overflow/underflow | Bloqueado — T12-T13 |
| Crivo: reentrância (lowercase) | Bloqueado — T14-T15 |
| Crivo: Infinity bloqueado (> 21B) | OK — T87 |
| Escudo: slashing efetivo | score=-1, staked=0 — T20 |
| Double-spend bloqueado | Slashing imediato — T22 |
| Overflow aciona Slashing | T23 |
| check_priority: fórmulas corretas | MASTER/SENTINELA/APOIADOR — T24-T27 |
| NonceStore: uso único, TTL, thread-safety | T28-T34 |
| RateLimiter: sliding window thread-safe | T35-T38 |
| Auth: endereços PLG inválidos rejeitados | T39 |
| /api/mine: validação de campos obrigatórios | T41 |
| Limite 64KB por request POST | T45 |
| Body JSON deve ser objeto (não array) | T46 |
| Rate limit challenge com threading.Lock() | T51 |
| Admin endpoint com variável de ambiente | T54 |
| Admin: chave vazia não bypassa | T55 |
| Honeypot anti-bot na Fundação | T56 |
| Sem queries SQL raw no core_vm.py | T57 |
| Genesis: lock TOCTOU no supply check | T65 |
| Genesis: mínimo $100 USDC e supply cap | T66, T68 |
| Flutter: Random.secure() para entropia | T71 |
| Flutter: validação de endereço PLG com regex | T72 |
| Flutter: dupla autenticação B1+B2 (código) | T73 |
| Flutter: FlutterSecureStorage com encryption | T74 |
| Flutter: grace period anti-MIUI | T76 |
| Flutter: chave privada em SecureStorage | T80 |
| Crivo: payload 1MB não crasha | T81 |
| Crivo: unicode/emojis não crasha | T82 |
| Vigia: hardware_id vazio não crasha | T83 |
| Vigia: payload None protegido | T84 |
| PHR: null byte não crasha | T89 |

---

## ROADMAP DE CORREÇÕES

### Prioridade P0 — Antes de abertura pública (CRÍTICO)
1. CVE-001: Verificação Dilithium3 em `/api/mine`
2. CVE-002: Validação de vértices em `/api/peer/vertex`
3. CVE-004: Persistência de bans do Escudo no banco
4. CVE-005: Autenticação em `/wallet/transferir`
5. CVE-006: Verificação de propriedade em `transferir_plgg`
6. CVE-003: Token JWT não-previsível em `core_vm.py`
7. VUL-HIGH-004: Senha hardcoded do canal privado

### Prioridade P1 — V1.5 (pós-lançamento, 1-3 meses)
8. VUL-HIGH-001: Crivo case-insensitive
9. VUL-HIGH-002: Auth em endpoints sociais
10. VUL-HIGH-003: Auth em miner/pause e miner/resume
11. VUL-HIGH-006: Type check em amount (string/NaN/Inf)
12. MED-002: threading.Lock() no rate limit fundação
13. MED-003: Cleanup thread de _challenges
14. MED-005: CORS restritivo

### Prioridade P2 — V2.0+ (conforme PMR)
15. CVE-007 + CVE-008: Dilithium3 FFI no Flutter (bloqueia burn da Chave DEUS)
16. VUL-HIGH-005: PBKDF2/Argon2 no B2 pattern
17. MED-007: Auth biométrica obrigatória
18. VUL-HIGH-008: URL configurável via build args

---

## METODOLOGIA

- **Análise estática:** Leitura linha a linha de todos os arquivos Python e Dart
- **Testes unitários:** Instância direta dos módulos Python com mocks do plegma_db
- **Fuzzing básico:** Inputs maliciosos (NaN, Infinity, string, None, null bytes, unicode, 1MB payload)
- **Race conditions:** Threading concorrente em Anti-Smurfing e RateLimiter
- **Análise de padrão:** Grep de vulnerabilidades conhecidas (hardcoded secrets, CORS, SQL injection, type confusion)

---

_Relatório gerado automaticamente em 2026-03-29 por bateria de testes PLEGMA DAG Security Suite v1.0_
