# AUDITORIA L-99 — PLEGMA DAG
## Documento de Auditoria Pública · Nível de Confidencialidade: PÚBLICO

**Data:** 2026-05-21 (actualizado 2026-05-21)  
**Versão do Protocolo:** PLEGMA DAG v4.1 · Mainnet activa desde 09/05/2026  
**Metodologia:** 5 auditores independentes, perspectivas distintas, leitura directa do código-fonte  
**Âmbito:** Protocolo completo — supply, mining, consenso, contratos, governança, criptografia, legal  
**Estado:** APROVADO CONDICIONAL — CT-1 ✅ RESOLVIDO · pendente CT-2 e CT-3  

---

## SUMÁRIO EXECUTIVO

O protocolo PLEGMA DAG foi submetido a uma auditoria de nível L-99, conduzida por cinco auditores independentes representando as cinco perspectivas mais exigentes da industria criptográfica: integridade do supply e descentralização (perspectiva Satoshi Nakamoto), contratos inteligentes e escalabilidade (perspectiva Vitalik Buterin), trust minimization e incentivos económicos (perspectiva Nick Szabo), consenso BFT e provas formais (perspectiva Silvio Micali), e criptografia aplicada pós-quântica (perspectiva Dan Boneh).

### Veredicto Agregado

| Auditor | Área | Rating |
|---------|------|--------|
| Auditor 1 — Supply & Mining | Integridade monetária, descentralização | APROVADO COM RESSALVAS GRAVES |
| Auditor 2 — Contratos & Escalabilidade | Smart contracts, governança, ZK, AMM | APROVADO COM RESSALVAS SIGNIFICATIVAS |
| Auditor 3 — Trust & Incentivos | Custódia, protocolo formal, incentivos, legal | APROVADO COM RESSALVAS GRAVES |
| Auditor 4 — BFT & Consenso Formal | Byzantine fault tolerance, gossip, ZK soundness | REPROVADO (protocolo BFT formal) |
| Auditor 5 — Criptografia Aplicada | Dilithium3, BLAKE3, ZK-SNARK, pós-quântico | APROVADO COM RESSALVAS |

**Rating Final:** **APROVADO CONDICIONAL** — A base criptográfica é sólida e pioneira. O protocolo tem falhas estruturais documentadas e rastreáveis. Nenhuma crítica é irrecuperável. A resolução dos 3 críticos transversais e dos 2 críticos de módulo é pré-requisito para lançamento público.

### Pontuação por Categoria (0–10)

| Categoria | Pontuação |
|-----------|-----------|
| Criptografia das primitivas (Dilithium3, BLAKE3) | 9/10 |
| Fair launch e integridade do supply | 7/10 |
| Consenso distribuído / BFT | 3/10 |
| Sistema ZK (zk_press.py) | 1/10 (como ZK) · 6/10 (como integrity seal) |
| Trust minimization | 4/10 |
| Incentivos económicos | 6/10 |
| Estrutura legal | 5/10 |
| Determinismo e qualidade de código | 8/10 |
| **Média geral** | **5.4/10** |

---

## CRÍTICOS TRANSVERSAIS (identificados por ≥2 auditores)

### ✅ CT-1 — RESOLVIDO — `zk_press.py` convertido para `DagSealEngine` (2026-05-21)
**Identificado por:** Auditor 2, Auditor 4, Auditor 5  
**Severidade original:** CRÍTICA · **Estado:** ✅ RESOLVIDO em 2026-05-21

**Resolução aplicada (opção B de Dan Boneh):**

O módulo `PLEGMA_CORE/zk_press.py` foi completamente reescrito. A classe `ZkPressEngine` foi substituída por `DagSealEngine` — um motor de **State Integrity Seal** honesto que usa BLAKE3 keyed-mode com separação formal de domínio (Dan Boneh R1 + R3).

Alterações aplicadas:
- Protocolo renomeado: `SYS-ZKDAG-LATTICE-FS-v4.0` → `SYS-DAG-SEAL-BLAKE3-v4.1`
- Classe principal: `ZkPressEngine` → `DagSealEngine` (com alias `ZkPressEngine = DagSealEngine` para retrocompatibilidade)
- Função interna `_generate_lattice_polynomials` (simulação de lattice) → `_expand_seal_body` (expansão BLAKE3 honesta)
- Função `_fiat_shamir_challenge` → `_domain_commit` (BLAKE3 keyed-mode com chaves de domínio de 32 bytes)
- Toda a terminologia ZK/SNARK/Ring-LWE/Fiat-Shamir removida do código, docstrings e documentação pública
- Consumidores actualizados: `core_dag.py`, `network_phase.py`, `shield_server.py`, ficheiros de teste
- Documentação pública actualizada: `geo/protocol.txt`, `geo/faq.txt`, `geo/roadmap.txt`, `llms.txt`, `index.html`, `fundacao/index.html` e 18+ páginas HTML
- Self-test: geração [OK] · verificação [OK] · anti-adulteração [OK] · encadeamento [OK]
- Orquestrador tri-IA pós-implementação: CRITICAL:0 · HIGH:0 · APROVADO

---

### CT-2 — Ausência de protocolo BFT formal entre os 4 nós âncora
**Identificado por:** Auditor 1, Auditor 2, Auditor 4  
**Severidade:** CRÍTICA — comprometer 2 nós viola Safety formal

Com `n=4` nós âncora, o teorema BFT (Castro-Liskov, PBFT) garante tolerância a `f=1` nó Byzantine. Com `f=2` nós comprometidos, o consenso é formalmente violável. O código `core_consenso.py` não implementa qualquer protocolo de consenso distribuído entre EUR/BR/MAL/SIN — é um gestor de recursos de hardware local. Não existe: votação entre os 4 nós, quórum de confirmação, detecção de equivocação Byzantine, mecanismo de lock/commit distribuído.

Cada nó âncora mantém o seu próprio SQLite de estado com `validator_pool`, `prover_pool` e `network_state` isolados. Uma partição de rede entre os 4 nós cria estados divergentes sem mecanismo de reconciliação determinístico. O gossip broadcast propaga vértices individualmente mas não implementa agregação de votos para finality.

**Impacto:** Safety (nenhum nó aceita transacções conflituosas) não está formalmente garantida. Um adversário com controlo de 2 nós pode propagar vértices conflituosos para partições diferentes e o protocolo não tem mecanismo de detecção ou resolução.

**Resolução:** Implementar quórum 3/4 para operações que modificam supply. Cada nó âncora assina o hash de cada vértice aceite com a sua chave Dilithium3; um vértice só é finalizado com ≥3 assinaturas de nós âncora distintos. As assinaturas agregadas no campo `endorsements` do vértice tornam a finality auditável externamente.

---

### CT-3 — Centralização real disfarçada de descentralização
**Identificado por:** Auditor 2, Auditor 3  
**Severidade:** ALTA — contradição fundamental com as garantias declaradas

O protocolo declara-se descentralizado mas a análise do código revela sete pontos de confiança centralizada: carteira de recebimento USDC sob controlo unilateral do operador, emissão de PLG-G via monitor Python centralizado, SQLite local modificável pelo operador com acesso ao filesystem, chave admin com controlo sobre aprovação de fundação, configuração de governança, e taxa do pool.

A ausência de governança on-chain funcional significa que todas as decisões de protocolo são tomadas pelo detentor da chave de sessão admin. Enquanto a PlegmaVM e a governança on-chain não existirem, o protocolo é funcionalmente um servidor Python com auditoria de base de dados.

**Resolução:** Publicar roadmap técnico verificável com milestones para: (a) PlegmaVM com especificação formal de execução e rollback; (b) governança on-chain com votação por peso implementada no código; (c) substituição da carteira de recebimento USDC por multi-sig Gnosis Safe 3-of-5 ou smart contract Polygon.

---

## RELATÓRIO AUDITOR 1 — SUPPLY, MINING, DESCENTRALIZAÇÃO
### Perspectiva: Integridade Monetária e Trustlessness

#### 1.1 Supply Integrity

O supply máximo de 21B PLG está declarado de forma hardcoded em `aerarium.py:48` (`MAX_SUPPLY = 21_000_000_000.0`) e o mecanismo de débito em `mine_tokens()` garante que nenhum pool emite além do disponível com clamp explícito. Não existe função de `mint()` por admin identificada no código auditado — ponto forte.

**Vetor de inflação silenciosa identificado:** O método `_distribuir_taxa_rede_locked()` em `aerarium.py:206-208` adiciona taxas de rede de volta aos pools de emissão (`validator_pool += fee_validator`). As taxas são cobradas sobre PLG em circulação e reinjectadas nos pools de emissão, criando um caminho que pode elevar a emissão total acima de 21B ao longo de suficientes ciclos. Requer análise matemática formal para confirmar ou refutar que o invariante `Σ(emissão) ≤ 21B` se mantém sob todos os caminhos de execução.

**PLG-G de 10.5M:** Supply hardcoded em `genesis_contract.py:38` e protegido por mutex. Ponto forte. Risco identificado: `plegma_db.salvar_saldo_plgg()` actualiza saldo directamente sem verificar supply total — se chamada externamente sem passar por `confirmar_compra()`, pode criar PLG-G acima do supply.

**Burn de PLG-G não vendido:** O burn address `PLG0237FEEC84108E37FF522A253AD1D469097A5A2B` é derivado de BLAKE3 sobre string pública e é elegante e auditável. A queima persiste em SQLite local — não é irreversível a nível de protocolo (operador com acesso directo ao SQLite pode reverter). Para supply genuinamente imutável, o burn deve ser ancorado numa cadeia pública imutável.

#### 1.2 Mining & Proof of Work

**Trustlessness:** Não completo. O endpoint `/api/mine` reside nos 4 nós âncora controlados por um único operador. A validação da prova é feita pelo servidor, não pelos peers. Um operador pode censurar mineradores específicos sem mecanismo de recurso protocolar.

**Double-reward:** A tabela `mine_validated_txs` com `INSERT OR IGNORE` garante idempotência num único nó. Risco: cada nó âncora corre o seu próprio SQLite — se o gossip falhar antes de sincronizar `mine_validated_txs`, o mesmo `ref_tx_hash` pode ser processado em dois nós distintos gerando double-reward.

**Sybil resistance:** Insuficiente. O `node_id` é derivado da keypair Dilithium3 gerada a cada instância sem `node_id` fixo. Qualquer utilizador pode contornar o rate limit de 24h por restart simples. O aviso existe no código como comentário, não como imposição criptográfica.

**CRÍTICO OPERACIONAL — Synthetic blocks:** O APK v1.16.4 emite transacções com `sender==receiver`. O motor DAG em `core_dag.py` não rejeita estas transacções em `add_transaction()`. O único bloqueio actual é operacional (serviços `plegma-miner.service` parados). **Resolução imediata:** adicionar `if sender == receiver: return None` antes da linha 165 de `core_dag.py`.

#### 1.3 Descentralização Real

Com 4 nós fixos, o protocolo não é descentralizado pela definição Bitcoin. Os mineradores mobile são clientes thin que submetem provas via HTTP — não correm full nodes, não verificam estado global, não podem rejeitar blocos inválidos independentemente. Se um nó âncora cair permanentemente, o supply tracking nesse nó diverge irrecuperavelmente dos restantes sem checkpoint de estado assinado criptograficamente entre nós.

#### 1.4 Double-Spend Prevention

O modelo de saldo por agregação relacional (não UTXO) com queries não-atómicas cria risco TOCTOU entre verificação de saldo e inserção da transacção. Dois nós que recebem transacções conflituosas simultaneamente não têm mecanismo protocolar de desempate.

#### TOP 3 RISCOS

1. **Synthetic blocks sem rejeição protocolar** — PLG pode ser emitido por transacções sem valor económico real. Uma linha de código resolve.
2. **Ausência de consenso atómico entre nós** — Double-reward e double-spend possíveis durante partição.
3. **Sybil resistance insuficiente no rate limit** — Bypass trivial por restart.

#### TOP 3 PONTOS FORTES

1. **Criptografia pós-quântica genuína e coerente** — Dilithium3, BLAKE3, ZK, sem excepções encontradas.
2. **Fair launch real e verificável** — Zero alocação para fundadores, supply inteiramente nos pools públicos.
3. **Determinismo absoluto na selecção de parents** — BLAKE3 como CSPRNG ancorado ao estado, sem `random()` ou timestamps como fonte primária.

---

## RELATÓRIO AUDITOR 2 — CONTRATOS, GOVERNANÇA, ESCALABILIDADE
### Perspectiva: Correctness de Contratos e Sistemas Distribuídos

#### 2.1 Smart Contract Design

Os módulos `genesis_contract.py` e `aerarium.py` são Python executados num servidor centralizado, não bytecode compilado e verificável por terceiros. Faltam as três propriedades fundamentais de smart contracts: atomicidade (escritas sequenciais fora de transação SQLite envolvente), imutabilidade (código substituível a qualquer momento), verificabilidade por terceiros (sem ABI pública, sem explorador de contratos).

**Race condition crítica:** O `_genesis_lock` (`threading.Lock`) não protege contra múltiplos processos uvicorn workers. Dois pedidos com o mesmo `tx_hash` chegando simultaneamente a workers diferentes passam na verificação `tx_externo_ja_processado` antes de qualquer escrita.

**Âncora contornável:** `confirmar_compra` pode ser chamada com apenas `tx_hash_externo` e `plg_address`, sem verificar a âncora (`ref_id` é opcional). A lógica de `confirmar_compra` recalcula `plgg_amount` sem verificar correspondência com a intenção original.

#### 2.2 Governança e Incentivos

A governança on-chain não existe funcionalmente. Todas as decisões actuais são tomadas via chave admin centralizada. A activação de governança após 30 dias (sem threshold de participação) pode resultar em governança activada com 1% de holders dominando todas as decisões iniciais.

**Contradição de governança:** LEI 5 do CLAUDE.md declara "1 pessoa · 1 voto · ativada por threshold". Os termos de uso descrevem peso proporcional ao PLG-G. Esta contradição cria incerteza jurídica e pode ser usada por reguladores para argumentar que o PLG-G é um security.

#### 2.3 Escalabilidade do DAG

4 nós fixos: configuração de testnet, não de mainnet. TPS real estimado: 100-500 TPS (SQLite não é adequado para alta concorrência). Com 4 nós, qualquer 2 que coludiam atingem 50% — abaixo do threshold BFT mínimo.

#### 2.4 Sistema ZK (ver CT-1)

Ver Crítico Transversal CT-1. Síntese: o sistema não implementa Ring-LWE real, não tem soundness formal, e qualquer participante pode gerar uma "prova válida" sem qualquer segredo.

#### TOP 3 RISCOS

1. **ZK-SNARK é simulação** — Ver CT-1.
2. **Ausência de atomicidade nas operações críticas** — `confirmar_compra` faz 6+ escritas sem transação SQLite. Race condition entre workers.
3. **Centralização real disfarçada** — Ver CT-3.

#### TOP 3 PONTOS FORTES

1. **Dilithium3 real no mobile** — ML-DSA-65 genuíno via FFI C, diferenciador real no ecossistema.
2. **Determinismo rigoroso e sem aleatoriedade não ancorada** — Banimento completo de PRNGs não-determinísticos aplicado consistentemente.
3. **Mecanismo de vesting e DNA Genesis** — Lockup FIFO com timestamp de vértice, sistema de perda de DNA alinha incentivos com longevidade do protocolo.

---

## RELATÓRIO AUDITOR 3 — TRUST MINIMIZATION, LEGAL, INCENTIVOS
### Perspectiva: Protocolos Formais e Criptografia Económica

#### 3.1 Inventário de Pontos de Confiança Centralizada

**CRÍTICO — Carteira de recebimento USDC:** Todos os USDC da Genesis Reserve convergem numa única carteira controlada pelo detentor da chave privada. Adicionalmente, `executar_distribuicao_usdc()` em `monitor_pagamentos.py` referencia `POLYGON_RPC` (singular) que não está definido no módulo — apenas `POLYGON_RPCS` (plural) existe. Este bug provoca `NameError` em runtime e torna a distribuição dos fundos impossível de executar via código. Os fundos podem ficar bloqueados indefinidamente.

**CRÍTICO — Emissão off-chain:** A emissão de PLG-G não é governada por smart contract na Polygon — é governada por código Python num servidor controlado pelo operador. Não existe mecanismo de reclamação trustless se a emissão falhar.

**ELEVADO — `interno=True` em `transferir_plgg`:** O parâmetro `interno=True` permite que chamadas internas ao servidor ignorem verificação de assinatura Dilithium3. Qualquer processo que corra no mesmo servidor e chame esta função pode transferir PLG-G de qualquer carteira sem autorização criptográfica.

#### 3.2 Design Formal do Protocolo

As constantes de protocolo (`PLGG_SUPPLY_TOTAL`, `PLGG_PRECO_USD`, `GENESIS_DIAS`, etc.) são hardcoded em Python e podem ser alteradas em qualquer deploy de nova versão. Não existe mecanismo on-chain que impeça a alteração das regras entre versões. O trigger SQLite `trg_fundacao_imutavel` é protecção superficial — ineficaz contra acesso directo ao ficheiro `.db` ou dump/reimportação sem triggers.

#### 3.3 Sustentabilidade dos Incentivos

O decaimento exponencial das recompensas de mineração é correcto como mecanismo anti-inflacionário. O problema de incentivo emerge da divisão por N: com mais nós, cada nó recebe menos, criando dilema do prisioneiro para participantes marginais. O Aerarium com teto de $1.000 USDC não financia sequer uma auditoria de segurança — o protocolo depende de capital dos fundadores para operações continuadas, criando dependência estrutural oposta à descentralização declarada.

#### 3.4 Análise Legal

**Classificação PLG-G:** A classificação como token de governança é plausível mas não garantida. O recebimento de USDC (stablecoin regulamentada) pode atrair atenção de reguladores MSB/VASP. Ausência de empresa controladora não elimina responsabilidade — transfere-a para indivíduos que controlam activos.

**Contradição governança:** Ver CT-3 e secção 2.2. Contradição entre "1 pessoa 1 voto" (LEI 5) e "peso proporcional ao PLG-G" (termos de uso) não está resolvida no código auditado. Se a governança é proporcional, o PLG-G é funcionalmente um security sob o teste de Howey.

#### TOP 3 RISCOS

1. **Single point of failure na custódia dos fundos Genesis** — Carteira centralizada + bug `NameError: POLYGON_RPC` = fundos potencialmente bloqueados.
2. **Ausência de smart contract na camada de settlement** — Emissão de PLG-G dependente inteiramente da disponibilidade e honestidade do operador.
3. **Contradição entre governança declarada e mecanismo implementado** — Risco regulatório e de protocolo.

#### TOP 3 PONTOS FORTES

1. **Stack criptográfico pós-quântico genuíno** — Dilithium3 e BLAKE3 são escolhas técnicas correctas e pioneiras.
2. **Fair launch estrutural** — Zero alocação para fundadores, uma das estruturas mais limpas identificadas.
3. **Determinismo como lei do protocolo** — Disciplina consistente e correctamente aplicada.

---

## RELATÓRIO AUDITOR 4 — BFT, CONSENSO FORMAL, ZK SOUNDNESS
### Perspectiva: Byzantine Agreement e Provas Verificáveis

#### 4.1 Byzantine Fault Tolerance

Com `n=4` nós, o teorema BFT é irrefutável: `n ≥ 3f+1` → `f ≤ 1`. O sistema tolera no máximo 1 nó Byzantine em simultâneo. Com 2 nós comprometidos, o consenso é formalmente violável.

`core_consenso.py` não implementa qualquer protocolo BFT — é um gestor de hardware local. Não existe votação entre nós, quórum, detecção de equivocação Byzantine, ou mecanismo de lock/commit distribuído. O gossip é broadcast one-to-all sem confirmação de quórum. Não existe mecanismo de detecção de nós Byzantine — o `monitorar_prover()` apenas monitora hashrate e temperatura.

#### 4.2 Propriedades Formais

**Safety:** Não formalmente garantida. `add_transaction()` não verifica saldo disponível nem transacção conflituosa em flight nos outros nós. A verificação é puramente local.

**Liveness:** Parcialmente garantida em condições normais; falha sob partição. Não existe noção de quórum no protocolo.

**Finality determinística:** Não nas condições actuais. A finality assenta em pressupostos não formalizados. Não existe checkpoint distribuído com assinatura de quórum.

**Ordering:** Partial ordering apenas. A tentativa de impor total ordering via timestamp no merge é frágil — timestamps gerados por `int(time.time())` localmente sem sincronização NTP verificada são não-Byzantine-safe.

#### 4.3 Mecanismo de Gossip

**Eclipse attacks:** A lista de peers é estática (`peers.json`) — não existe descoberta dinâmica. Substituição do `peers.json` ou intercepção das conexões HTTP pode isolar um nó completamente.

**Amplificação:** `broadcast_vertice()` dispara uma thread por peer sem rate limiting. Sem deduplicação por hash antes do envio, o mesmo vértice pode ser reenviado múltiplas vezes. Um atacante com chave Dilithium válida pode gerar O(n_peers × n_vértices) threads em cada nó.

**Ponto forte:** A verificação de assinatura Dilithium3 em `_verificar_vertice()` antes de aceitar vértices é robusta e correcta — impede flooding de vértices inválidos.

#### 4.4 ZK Soundness (ver CT-1)

**Soundness = 0%.** Qualquer participante com `dag_state_hash` pode gerar uma "prova" que passa `verify_proof` sem qualquer segredo. O sistema funciona como MAC baseado em hash, não como prova ZK.

#### TOP 3 RISCOS

1. **ZK Engine é uma simulação sem soundness** — Ver CT-1. Invalida toda a arquitectura de segurança que depende das provas para validação de transacções.
2. **Ausência de protocolo BFT formal** — Ver CT-2. Safety formal não está provada nem implementada.
3. **Gossip sem rate limiting e peers estáticos** — DDoS por actor com chave Dilithium válida e eclipse attacks por comprometimento de infraestrutura.

#### TOP 3 PONTOS FORTES

1. **Assinatura Dilithium3 real e correctamente integrada** — Binding criptográfico correcto, verificação de tamanho de chave como sanity check, Hard Fail na inicialização.
2. **Determinismo rigoroso e consistente** — Banimento completo de PRNGs, ordenação estrita de parents antes do hash, merge determinístico pós-partição.
3. **Verificação defensiva em múltiplas camadas** — Verificação de vértices em gossip e motor DAG independentemente; rejeição de provas > 22KB.

#### Recomendação de Implementação BFT Mínima

Com 4 nós fixos, implementar threshold de confirmação 3/4 para todos os vértices (não apenas contratos). Cada nó âncora assina o hash do vértice aceite com a sua chave Dilithium3. Vértice finalizado com ≥3 assinaturas. Assinaturas agregadas (3 × ~3.3KB Dilithium) = ~10KB, dentro do limite de 22KB revisado. Isto fornece Safety com f=1 e é auditável por qualquer observador externo.

---

## RELATÓRIO AUDITOR 5 — CRIPTOGRAFIA APLICADA PÓS-QUÂNTICA
### Perspectiva: Rigor Académico em Criptografia e Segurança

#### 5.1 Crystals-Dilithium3 / ML-DSA-65

**Conformidade FIPS 204:** A biblioteca usa `ML_DSA_65` como prioridade, com fallback para `Dilithium3` Round 3. **Inconsistência crítica:** `lattice_shield.py` e `tx_verifier.py` tentam primeiro `Dilithium3` Round 3; `auth_server.py` tenta primeiro `ML_DSA_65`. Em ambiente heterogéneo (diferentes versões da biblioteca entre nós), o motor activo pode diferir entre assinador e verificador. ML-DSA-65 produz assinaturas de 3309 bytes; Dilithium3 Round 3 produz 2420 bytes. O verificador com motor errado rejeitará todas as assinaturas legítimas.

**Auth challenge-response:** O protocolo é correcto. Nonces consumidos atomicamente (`verify_and_consume`), TTL de 600s adequado, anti-replay implementado. Token de sessão derivado criptograficamente da própria assinatura Dilithium3 — não forjável. Aprovado.

**Side-channel:** `dilithium-py` é Python puro, sem bindings C constant-time. Em contexto de servidor partilhado, adversário com acesso à mesma VM pode executar timing attacks via análise de cache. Mitigação: usar PQClean com side-channel protections, ou hardware de auth isolado.

#### 5.2 BLAKE3 como Primitiva Universal

O uso simultâneo como PRF, KDF e Fiat-Shamir Oracle é seguro com contextos de domínio distintos. A separação de domínio existe mas é informal — prefixos em `update()` em vez de keyed hash mode (`blake3.blake3(key=domain_key_32bytes, data=payload)`). Funcionalmente equivalente mas menos elegante e com risco teórico de colisão de domínio com input crafted.

**Derivação de endereços `BLAKE3(pubkey)[:40]`:** 160 bits, birthday bound 2^80 — adequado e seguro. Equivalente à segurança do HASH160 do Bitcoin.

**Burn address `BLAKE3(string_fixa)[:40]`:** Criptograficamente correcto. Provável sem chave privada, verificável publicamente. Aprovado.

**Anchor ID:** Correcto com ressalva menor — separadores `|` entre campos não são length-prefixed. Se um campo contiver `|`, existe ambiguidade de parsing. Correcção: usar length-prefix por campo.

#### 5.3 ZK-SNARK Próprio (ver CT-1)

**Veredicto técnico rigoroso:** O `zk_press.py` não implementa ZK-SNARK. É um KDF de expansão BLAKE3. O próprio comentário da função `_generate_lattice_polynomials` usa a palavra "Simula". A verificação é determinística total — qualquer entidade com `dag_state_hash` reproduz a prova exactamente. Soundness = 0%. A terminologia "Ring-LWE", "Fiat-Shamir", "SNARK", "lattice polynomial matrix" é incorrecta para o que o código implementa.

**Resistência quântica:** BLAKE3 tem 128 bits de segurança quântica (Grover). A integridade fornecida é pós-quântica. A propriedade de "ZK" ou "prova de conhecimento" não existe.

#### 5.4 Dependências e Fronteiras Quânticas

| Componente | Resistência Quântica | Notas |
|------------|---------------------|-------|
| ML-DSA-65 assinaturas | Pós-quântica NIST L3 | APROVADO |
| BLAKE3 derivação endereços | 128 bits quântico | APROVADO |
| Burn address commitment | Provável sem chave privada | APROVADO |
| Auth challenge-response | Sólido, anti-replay | APROVADO |
| zk_press.py como ZK | Não existe soundness | REPROVADO como ZK |
| zk_press.py como integrity seal | MAC hash funcional | APROVADO uso limitado |
| Fallback Dilithium inconsistente | Risco de inoperabilidade | REPROVADO |
| Bridge EVM (Polygon/secp256k1) | Vulnerável a quântico | Risco documentado — pertence ao Polygon, não ao PLEGMA |

**Dependência EVM:** O `anchor_id` vincula `tx_hash` Polygon ao protocolo PLEGMA. Se adversário quântico quebrar secp256k1 (Polygon), pode criar `tx_hash` falsos aceites como pagamentos legítimos. Este é o único vetor quântico que afecta o PLEGMA através da bridge — deve ser documentado no modelo de ameaça.

#### TOP 3 RISCOS CRIPTOGRÁFICOS

1. **`zk_press.py` não implementa ZK proofs** — Ver CT-1. Soundness = 0%.
2. **Inconsistência de fallback ML-DSA-65 / Dilithium3** — Diferentes módulos usam ordens de importação diferentes. Em ambiente heterogéneo, verificação falha sistematicamente.
3. **`tx_hash` derivado com timestamp** — Em `genesis_contract.py:217-218`, `agora = time.time()` como componente do seed permite colisão teórica em servidor moderno (precisão de microsegundo).

#### TOP 3 PONTOS FORTES

1. **ML-DSA-65 como primitiva de assinatura** — A decisão correcta para protocolo pós-quântico em 2026. Implementação correcta e com Hard Fail na ausência da biblioteca.
2. **Arquitectura de nonce e sessão com consumo atómico** — Implementação sólida do challenge-response, rate limiting por IP e endereço PLG.
3. **Burn address e anchor_id como commitment schemes verificáveis** — Design elegante, correcto, e auditável publicamente.

---

## RECOMENDAÇÕES CONSOLIDADAS POR PRIORIDADE

### PRIORIDADE IMEDIATA (bloqueantes para produção)

| ID | Recomendação | Auditor(es) | Esforço |
|----|--------------|-------------|---------|
| ✅ R1 | RESOLVIDO — `DagSealEngine` (State Integrity Seal BLAKE3 keyed-mode) · terminologia ZK/SNARK removida | 2, 4, 5 | — |
| R2 | Corrigir bug `NameError: POLYGON_RPC` em `monitor_pagamentos.py` → usar `POLYGON_RPCS[0]` com fallback | 3 | Trivial |
| R3 | Adicionar verificação `sender != receiver` em `core_dag.py:add_transaction()` — rejeitar synthetic blocks no protocolo | 1 | Trivial |
| R4 | Uniformizar ordem de importação Dilithium em todos os módulos — definir `CRYPTO_ENGINE` central em `plegma_crypto.py` | 5 | Baixo |
| R5 | Envolver todas as escritas críticas em `genesis_contract.py` e `aerarium.py` em transações SQLite `BEGIN IMMEDIATE` | 2 | Médio |

### PRIORIDADE ALTA (pré-lançamento público)

| ID | Recomendação | Auditor(es) | Esforço |
|----|--------------|-------------|---------|
| R6 | Implementar quórum 3/4 entre nós âncora: cada nó assina vértices aceites com Dilithium3, finality exige ≥3 assinaturas | 1, 2, 4 | Alto |
| R7 | Substituir carteira de recebimento USDC por multi-sig Gnosis Safe 3-of-5 ou smart contract Polygon | 3 | Alto |
| R8 | Remover `interno=True` de `transferir_plgg` ou auditar todos os usos e substituir por autorização explícita auditável | 3 | Médio |
| R9 | Substituir `tx_hash` derivado com timestamp por seed baseado em `tx_hash_externo` (sem timestamp) | 5 | Baixo |
| R10 | Verificar `tx_hash` contra Polygon RPC em `ancorar_tx_polygon` antes de aceitar a âncora | 5 | Médio |

### PRIORIDADE MÉDIA (curto prazo)

| ID | Recomendação | Auditor(es) | Esforço |
|----|--------------|-------------|---------|
| R11 | Adicionar rate limiting e thread pool com limite máximo em `gossip.broadcast_vertice()` | 4 | Baixo |
| R12 | Substituir `peers.json` estático por peer discovery dinâmico com verificação de assinatura | 4 | Alto |
| R13 | Resolver contradição "1 pessoa 1 voto" vs proporcional ao PLG-G — escolha explícita, consistente em código e documentação | 3 | Médio |
| R14 | Usar BLAKE3 keyed mode (`blake3(key=domain_key, data=payload)`) para separação formal de domínio | 5 | Baixo |
| R15 | Publicar roadmap técnico verificável com milestones para PlegmaVM, governança on-chain, e expansão de nós | 2, 3 | Médio |

---

## APÊNDICE A — RESULTADOS DO ORQUESTRADOR TRI-IA

**Data da auditoria orquestrador:** 2026-05-21  
**Pipeline:** `full_audit` — Validation + Security + Coder agents  

| Agente | Estado | Resultado |
|--------|--------|-----------|
| Validation (L1) | SUCCESS | CRITICAL 0 · 5 DAG-FLOW issues (pre-existentes, documentados FASE 1) |
| Security | SUCCESS | CRITICAL 0 · HIGH 0 · MEDIUM 0 · LOW 30 |
| Coder | SUCCESS | 0 observações em 28 ficheiros |

**DAG Auditor:** EUR score=8/8 · BR/MAL/SIN score=7/8 (aceitas=0 cosmético) · CRÍTICO=0 ALTO=0 MÉDIO=3

---

## APÊNDICE B — FICHEIROS AUDITADOS

| Ficheiro | Auditor(es) |
|---------|-------------|
| `PLEGMA_CORE/core_dag.py` | 1, 4 |
| `PLEGMA_CORE/miner_engine.py` | 1 |
| `PLEGMA_CORE/plegma_db.py` | 1 |
| `PLEGMA_CORE/genesis_contract.py` | 1, 2, 3, 5 |
| `PLEGMA_CORE/aerarium.py` | 1, 2, 3 |
| `PLEGMA_CORE/aerarium_swap.py` | 2 |
| `PLEGMA_CORE/zk_press.py` | 2, 4, 5 |
| `PLEGMA_CORE/lattice_shield.py` | 5 |
| `PLEGMA_CORE/auth_server.py` | 5 |
| `PLEGMA_CORE/tx_verifier.py` | 4, 5 |
| `PLEGMA_CORE/core_api.py` (parcial) | 2, 3 |
| `PLEGMA_CORE/core_consenso.py` | 4 |
| `PLEGMA_CORE/gossip.py` | 4 |
| `PLEGMA_CORE/monitor_pagamentos.py` | 3 |
| `PLEGMA_LANDING/termos/index.html` | 3 |
| `PLEGMA_LANDING/privacidade/index.html` | 3 |
| `PROJECT_MEMORY/domains/D01_core_dag.md` | 1, 4 |
| `PROJECT_MEMORY/domains/D05_genesis_tokenomics.md` | 2 |
| `PROJECT_MEMORY/domains/D06_fundacao.md` | 3 |
| `PROJECT_MEMORY/domains/D09_seguranca.md` | 5 |

---

## APÊNDICE C — METODOLOGIA

Esta auditoria foi conduzida com os seguintes princípios:

1. **Leitura directa do código-fonte** — todas as conclusões baseadas em análise do código real, não de documentação ou declarações do protocolo.
2. **Independência de perspectiva** — 5 auditores com foco em áreas distintas, sem comunicação entre si durante a auditoria.
3. **Distinção entre intenção e implementação** — o que o código *afirma ser* vs. o que o código *demonstravelmente é*.
4. **Não existe crítica irrecuperável** — todas as falhas identificadas têm caminho de resolução técnica definido.
5. **Confidencialidade dos críticos de segurança** — falhas de segurança não corrigidas são referenciadas por categoria genérica, não por detalhe de exploração.

---

*Auditoria L-99 — PLEGMA DAG*  
*Data: 2026-05-21*  
*Classificação: PÚBLICO*  
*Próxima revisão: pós-resolução de R1-R5 (críticos imediatos)*
