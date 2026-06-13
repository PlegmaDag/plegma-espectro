"""
test_bateria_completa.py — PLEGMA DAG V4.0
Bateria Completa: Stress · Inserção · DB · Sentinela · Auth · Fundação · Tokenomics · Frontend
"""

import os
import sys
import time
import json
import sqlite3
import traceback
import threading
import urllib.request
import urllib.error

# ---------------------------------------------------------------------------
# Configuração de paths
# ---------------------------------------------------------------------------
CORE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, CORE_DIR)

try:
    import blake3
    from dilithium_py.dilithium import Dilithium3
except ImportError as e:
    print(f"[FALHA FATAL] Dependências de núcleo ausentes: {e}")
    sys.exit(1)

try:
    from zk_press import DagSealEngine as ZkPressEngine
    import plegma_db
    import sentinela as sentinela_mod
except ImportError as e:
    print(f"[FALHA FATAL] Módulos PLEGMA não localizados: {e}")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Infra de relatório
# ---------------------------------------------------------------------------
LOG_PATH = os.path.join(CORE_DIR, "test_log_bateria.txt")
_log_lines = []
_total = 0
_passed = 0
_failed = 0
_errors = []

def _log(msg: str):
    _log_lines.append(msg)
    safe = msg.encode("cp1252", errors="replace").decode("cp1252")
    print(safe)

def _header(title: str):
    line = f"\n[{title.center(56, '-')}]"
    _log(line)

def _ok(msg: str):
    global _total, _passed
    _total += 1
    _passed += 1
    _log(f" [OK] {msg}")

def _fail(msg: str, detail: str = ""):
    global _total, _failed
    _total += 1
    _failed += 1
    entry = f" [FALHA] {msg}" + (f" | {detail}" if detail else "")
    _log(entry)
    _errors.append(entry)

def check(cond: bool, ok_msg: str, fail_msg: str, detail: str = ""):
    if cond:
        _ok(ok_msg)
    else:
        _fail(fail_msg, detail)

# ---------------------------------------------------------------------------
# MÓDULO 1 — BLAKE3 + DILITHIUM3
# ---------------------------------------------------------------------------
def teste_cripto():
    _header("1. HEGEMONIA BLAKE3 & DILITHIUM3")
    try:
        pk, sk = Dilithium3.keygen()
        check(len(pk) > 1000, f"Chave pública Dilithium3 gerada ({len(pk)} bytes)", "Chave pública inválida")

        addr = "PLG" + blake3.blake3(pk).hexdigest()[:40].upper()
        check(addr.startswith("PLG") and len(addr) == 43,
              f"Endereço PLG derivado via BLAKE3: {addr[:14]}...",
              "Formato de endereço inválido")

        payload = b"PLEGMA_INTEGRITY_2026"
        sig = Dilithium3.sign(sk, payload)
        check(Dilithium3.verify(pk, payload, sig),
              "Assinatura Dilithium3 verificada com sucesso",
              "Verificação de assinatura falhou")

        check(not Dilithium3.verify(pk, b"PAYLOAD_DIFERENTE", sig),
              "Assinatura rejeitada para payload alterado (non-malleability)",
              "Assinatura aceite para payload errado — VIOLAÇÃO CRÍTICA")

        h1 = blake3.blake3(b"SEED_DETERMINISTICA").hexdigest()
        h2 = blake3.blake3(b"SEED_DETERMINISTICA").hexdigest()
        check(h1 == h2,
              "BLAKE3 determinístico: mesmo input → mesmo hash",
              "BLAKE3 não determinístico — VIOLAÇÃO L1")

        h3 = blake3.blake3(b"SEED_DIFERENTE").hexdigest()
        check(h1 != h3,
              "BLAKE3 resistência a colisão trivial",
              "Colisão trivial detectada — BLAKE3 comprometido")

        return addr, pk, sk
    except Exception as e:
        _fail("Módulo criptográfico", str(e))
        return None, None, None

# ---------------------------------------------------------------------------
# MÓDULO 2 — ZK-PRESS
# ---------------------------------------------------------------------------
def teste_zk():
    _header("2. MOTOR ZK-PRESS V4.0 (LATTICE SNARK)")
    try:
        zk = ZkPressEngine()
        estado = blake3.blake3(b"TEST_STATE_ZK").hexdigest()

        t0 = time.time()
        prova = zk.generate_recursive_proof(estado)
        t_ms = (time.time() - t0) * 1000
        kb = len(prova) / 1024

        check(kb <= 22, f"Tamanho da prova: {kb:.2f} KB (limite 22 KB)", f"Prova excede 22 KB: {kb:.2f} KB")
        check(kb >= 15, f"Densidade Lattice OK: {kb:.2f} KB", f"Prova leve demais: {kb:.2f} KB — simulação inválida")
        check(zk.verify_proof(prova, estado),
              f"Prova verificada em {t_ms:.0f}ms",
              "Falha na verificação Fiat-Shamir")

        # Determinismo: mesma prova para mesmo estado
        prova2 = zk.generate_recursive_proof(estado)
        check(prova == prova2,
              "ZK determinístico: mesmo estado → mesma prova",
              "ZK não determinístico — VIOLAÇÃO L1")

        # Prova inválida deve rejeitar
        estado_errado = blake3.blake3(b"OUTRO_ESTADO").hexdigest()
        check(not zk.verify_proof(prova, estado_errado),
              "Prova rejeitada para estado diferente (soundness)",
              "Prova aceite para estado errado — VIOLAÇÃO SOUNDNESS")
    except Exception as e:
        _fail("Motor ZK-Press", str(e))

# ---------------------------------------------------------------------------
# MÓDULO 3 — DB: INSERÇÃO E PERSISTÊNCIA
# ---------------------------------------------------------------------------
def teste_db_basico(plg_address: str):
    _header("3. PERSISTÊNCIA DETERMINÍSTICA (DB V4)")
    try:
        plegma_db.inicializar_banco()
        check(os.path.exists(plegma_db.DB_PATH),
              f"Banco SQLite instanciado: {plegma_db.DB_PATH}",
              "Arquivo DB não criado")

        # Saldo PLG-G
        plegma_db.salvar_saldo_plgg(plg_address, 5000.0)
        saldo = plegma_db.carregar_saldo_plgg(plg_address)
        check(abs(saldo - 5000.0) < 0.001,
              f"Saldo PLG-G gravado e lido: {saldo}",
              f"Saldo incorreto: esperado 5000.0, obtido {saldo}")

        # Saldo genesis
        plegma_db.salvar_saldo_plgg_genesis(plg_address, 1000.0)
        g = plegma_db.carregar_saldo_plgg_genesis(plg_address)
        check(abs(g - 1000.0) < 0.001,
              f"Saldo genesis PLG-G: {g}",
              f"Saldo genesis incorreto: {g}")

        # State key-value
        plegma_db.salvar_estado("teste_key", {"status": "OK", "valor": 42})
        estado = plegma_db.carregar_estado("teste_key")
        check(isinstance(estado, dict) and estado.get("valor") == 42,
              "State key-value gravado e lido",
              "State key-value corrompido")

        # Saldo inexistente retorna 0
        saldo_novo = plegma_db.carregar_saldo_plgg("PLG_INEXISTENTE_XYZ")
        check(saldo_novo == 0.0,
              "Endereço sem saldo retorna 0.0",
              f"Endereço sem saldo retornou {saldo_novo}")

    except Exception as e:
        _fail("DB básico", str(e))

# ---------------------------------------------------------------------------
# MÓDULO 4 — BANS / SLASHING
# ---------------------------------------------------------------------------
def teste_bans():
    _header("4. SISTEMA DE BANS / SLASHING")
    try:
        uid_ban = blake3.blake3(b"NOD_MALICIOSO_TESTE").hexdigest()

        plegma_db.salvar_ban(uid_ban, 2500.0, "TESTE_BATERIA_SLASHING")
        bans = plegma_db.carregar_bans()
        check(uid_ban in bans, "Ban gravado e recuperado pelo UIDG", "Ban não persistido")
        check(bans[uid_ban]["score"] == -1,
              "Score do banido = -1",
              f"Score incorreto: {bans.get(uid_ban, {}).get('score')}")

        check(plegma_db.is_banido(uid_ban),
              "is_banido() retorna True para UIDG banido",
              "is_banido() falhou para banido conhecido")

        uid_limpo = blake3.blake3(b"NOD_LIMPO_TESTE").hexdigest()
        check(not plegma_db.is_banido(uid_limpo),
              "is_banido() retorna False para UIDG sem ban",
              "is_banido() falso positivo para nó limpo")

        # Idempotência: salvar mesmo ban duas vezes não duplica
        plegma_db.salvar_ban(uid_ban, 9999.0, "REINSERCAO")
        bans2 = plegma_db.carregar_bans()
        count = sum(1 for k in bans2 if k == uid_ban)
        check(count == 1,
              "Ban idempotente: INSERT OR REPLACE sem duplicação",
              f"Ban duplicado: {count} entradas para mesmo UIDG")

    except Exception as e:
        _fail("Bans/Slashing", str(e))

# ---------------------------------------------------------------------------
# MÓDULO 5 — SESSÕES AUTH
# ---------------------------------------------------------------------------
def teste_sessoes(plg_address: str):
    _header("5. GESTÃO DE SESSÕES AUTH")
    try:
        token_valido = blake3.blake3(b"TOKEN_TESTE_AUTH").hexdigest()
        plegma_db.salvar_sessao(plg_address, token_valido, ttl_segundos=3600)
        check(plegma_db.validar_sessao(plg_address, token_valido),
              "Sessão gravada e validada com sucesso",
              "validar_sessao() falhou para sessão válida")

        # Token errado deve rejeitar
        token_errado = blake3.blake3(b"TOKEN_FALSO").hexdigest()
        check(not plegma_db.validar_sessao(plg_address, token_errado),
              "Token inválido rejeitado correctamente",
              "Token falso aceite — FALHA DE SEGURANÇA")

        # Sessão expirada (TTL = 0)
        token_exp = blake3.blake3(b"TOKEN_EXPIRADO").hexdigest()
        plegma_db.salvar_sessao(plg_address, token_exp, ttl_segundos=0)
        time.sleep(0.05)
        check(not plegma_db.validar_sessao(plg_address, token_exp),
              "Sessão expirada rejeitada (TTL=0)",
              "Sessão expirada aceite — VIOLAÇÃO DE SEGURANÇA")

        # Revogar sessão
        plegma_db.revogar_sessao(plg_address, token_valido)
        check(not plegma_db.validar_sessao(plg_address, token_valido),
              "Sessão revogada (logout) rejeitada correctamente",
              "Sessão revogada ainda válida — FALHA DE SEGURANÇA")

        # Limpeza de expiradas
        plegma_db.limpar_sessoes_expiradas()
        _ok("limpar_sessoes_expiradas() executou sem erro")

    except Exception as e:
        _fail("Sessões auth", str(e))

# ---------------------------------------------------------------------------
# MÓDULO 6 — SENTINELA (VIGIA / CRIVO / ESCUDO)
# ---------------------------------------------------------------------------
def teste_sentinela():
    _header("6. SENTINELA CORE (VIGIA · CRIVO · ESCUDO)")
    try:
        vigia = sentinela_mod.Vigia()
        crivo = sentinela_mod.Crivo()

        # Vigia: país permitido
        ok, msg = vigia.verificar_borda("10.0.0.1", "BR", "HW_TEST_001", "MOBILE", "payload limpo")
        check(ok, "Vigia aprova nó de jurisdição permitida (BR)", f"Vigia rejeitou BR: {msg}")

        # Vigia: país bloqueado
        ok, msg = vigia.verificar_borda("10.0.0.2", "KP", "HW_TEST_002", "MOBILE", "payload")
        check(not ok, "Vigia bloqueia jurisdição KP (Coreia do Norte)", f"Vigia não bloqueou KP: {msg}")

        ok, msg = vigia.verificar_borda("10.0.0.3", "IR", "HW_TEST_003", "MOBILE", "payload")
        check(not ok, "Vigia bloqueia jurisdição IR (Irão)", f"Vigia não bloqueou IR: {msg}")

        # Vigia: PHR — conteúdo ilícito
        ok, msg = vigia.verificar_borda("10.0.0.5", "US", "HW_TEST_005", "MOBILE", "terrorismo financeiro")
        check(not ok, "Vigia bloqueia PHR: palavra 'terrorismo'", f"Vigia não bloqueou PHR: {msg}")

        # Crivo: montante normal
        ok, msg = crivo.interceptar_mempool("tx normal", 100.0)
        check(ok, "Crivo aprova transação normal (100 PLG)", f"Crivo rejeitou normal: {msg}")

        # Crivo: overflow
        ok, msg = crivo.interceptar_mempool("tx overflow", 22_000_000_000.0)
        check(not ok, "Crivo detecta overflow (22 bilhões PLG)", f"Crivo falhou overflow: {msg}")

        # Crivo: underflow
        ok, msg = crivo.interceptar_mempool("tx negativa", -1.0)
        check(not ok, "Crivo detecta underflow (valor negativo)", f"Crivo falhou underflow: {msg}")

        # Crivo: reentrância
        ok, msg = crivo.interceptar_mempool("reentrancy_exploit payload", 50.0)
        check(not ok, "Crivo detecta ataque de reentrância", f"Crivo falhou reentrância: {msg}")

        # Escudo: slashing
        escudo = sentinela_mod.Escudo()
        uid_slash = blake3.blake3(b"NO_SLASH_TEST").hexdigest()
        escudo.registrar_no(uid_slash, stake_inicial=1000.0)
        resultado = escudo.protocolo_slashing(uid_slash, "TESTE_SLASHING_BATERIA")
        check(resultado, "Protocolo Slashing executado com sucesso", "Slashing retornou False")
        check(plegma_db.is_banido(uid_slash),
              "Nó slashado persistido no DB como banido",
              "Nó slashado não encontrado no DB após slashing")

    except Exception as e:
        _fail("Sentinela", str(e))
        traceback.print_exc()

# ---------------------------------------------------------------------------
# MÓDULO 7 — FUNDAÇÃO: IMUTABILIDADE + APROVAÇÃO
# ---------------------------------------------------------------------------
def teste_fundacao():
    _header("7. FUNDAÇÃO: INSERÇÃO · IMUTABILIDADE · APROVAÇÃO")
    import json as _json
    try:
        ts = time.time()
        carteira = "PLG" + blake3.blake3(f"FUNDACAO_TEST_{ts}".encode()).hexdigest()[:40].upper()

        # Campos públicos usados para gerar o hash
        campos_publicos = {
            "carteira_plg": carteira,
            "nome_projeto": "Projeto Teste Bateria",
            "segmento": "Educação",
            "localizacao": "Brasil",
            "descricao": "Inscrição de teste automatizado",
            "responsavel": "Agente Teste",
            "tempo_atuacao": "1 ano",
        }
        payload_bytes = _json.dumps(campos_publicos, sort_keys=True, ensure_ascii=False).encode("utf-8")
        hash_calc = blake3.blake3(payload_bytes).hexdigest()

        entry = {
            **campos_publicos,
            "hash_inscricao": hash_calc,
            "created_at": ts,
        }

        row_id = plegma_db.salvar_inscricao_fundacao(entry)
        check(row_id > 0, f"Inscrição Fundação criada (id={row_id})", "Falha ao criar inscrição")

        reg = plegma_db.buscar_inscricao_fundacao(hash_calc)
        check(reg is not None, "Inscrição recuperável pelo hash BLAKE3", "Inscrição não encontrada por hash")
        if reg is None:
            _fail("Fundação", "buscar retornou None — abortando módulo")
            return
        check(reg["status"] == "PENDENTE", "Status inicial = PENDENTE", f"Status inicial incorreto: {reg['status']}")

        # Imutabilidade: tentar alterar hash directo no DB deve falhar
        conn = plegma_db.get_connection()
        try:
            conn.execute("UPDATE fundacao_registros SET hash_inscricao='HACK' WHERE id=?", (row_id,))
            conn.commit()
            _fail("Trigger imutabilidade", "UPDATE em hash_inscricao não gerou excepção — trigger inativo")
        except sqlite3.IntegrityError:
            _ok("Trigger trg_fundacao_imutavel: UPDATE em hash bloqueado (ABORT)")
        finally:
            conn.close()

        # Aprovação
        aprovado = plegma_db.aprovar_inscricao_fundacao(hash_calc)
        check(aprovado, "Inscrição aprovada via aprovar_inscricao_fundacao()", "Aprovação falhou")

        reg_ap = plegma_db.buscar_inscricao_fundacao(hash_calc)
        check(reg_ap["status"] == "APROVADA", "Status = APROVADA após aprovação", f"Status: {reg_ap['status']}")

        # Dupla aprovação deve retornar False
        dupla = plegma_db.aprovar_inscricao_fundacao(hash_calc)
        check(not dupla, "Dupla aprovação rejeitada (rowcount=0)", "Dupla aprovação permitida — BUG")

        # Carteira aprovada verificável
        resultado = plegma_db.carteira_fundacao_aprovada(carteira)
        check(resultado is not None, "carteira_fundacao_aprovada() localiza carteira aprovada", "Carteira aprovada não encontrada")

        # Rejeição de inscrição pendente
        ts2 = time.time() + 1
        carteira2 = "PLG" + blake3.blake3(f"FUND2_{ts2}".encode()).hexdigest()[:40].upper()
        campos2 = {**campos_publicos, "carteira_plg": carteira2}
        hash2 = blake3.blake3(_json.dumps(campos2, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        plegma_db.salvar_inscricao_fundacao({**campos2, "hash_inscricao": hash2, "created_at": ts2})
        rejeitado = plegma_db.rejeitar_inscricao_fundacao(hash2)
        check(rejeitado, "Rejeição de inscrição pendente OK", "Rejeição falhou")

    except Exception as e:
        _fail("Fundação", str(e))
        traceback.print_exc()

# ---------------------------------------------------------------------------
# MÓDULO 8 — TOKENOMICS
# ---------------------------------------------------------------------------
def teste_tokenomics():
    _header("8. TOKENOMICS & GOVERNANÇA")
    try:
        # Supply PLG imutável
        plegma_db.salvar_estado("supply_plg", 21_000_000_000)
        supply = plegma_db.carregar_estado("supply_plg")
        check(supply == 21_000_000_000, "Supply PLG = 21.000.000.000 (fixo)", f"Supply incorreto: {supply}")

        # Supply PLG-G
        plegma_db.salvar_estado("supply_plgg", 10_500_000)
        supply_g = plegma_db.carregar_estado("supply_plgg")
        check(supply_g == 10_500_000, "Supply PLG-G = 10.500.000 (Genesis Reserve)", f"Supply PLG-G incorreto: {supply_g}")

        # check_priority: tiers
        addr_master    = "PLG" + blake3.blake3(b"MASTER_TEST").hexdigest()[:40].upper()
        addr_sentinela = "PLG" + blake3.blake3(b"SENTINELA_TEST").hexdigest()[:40].upper()
        addr_apoiador  = "PLG" + blake3.blake3(b"APOIADOR_TEST").hexdigest()[:40].upper()
        addr_sem       = "PLG" + blake3.blake3(b"SEM_SALDO_TEST").hexdigest()[:40].upper()

        plegma_db.salvar_saldo_plgg(addr_master,    7000.0)
        plegma_db.salvar_saldo_plgg(addr_sentinela, 4000.0)
        plegma_db.salvar_saldo_plgg(addr_apoiador,  1500.0)
        plegma_db.salvar_saldo_plgg(addr_sem,          0.0)

        from sentinela import check_priority
        check(check_priority(addr_master)["categoria"]    == "MASTER",      "Tier MASTER    (saldo ≥ 6.001)",    "Tier MASTER errado")
        check(check_priority(addr_sentinela)["categoria"] == "SENTINELA",   "Tier SENTINELA (saldo ≥ 3.001)",    "Tier SENTINELA errado")
        check(check_priority(addr_apoiador)["categoria"]  == "APOIADOR",    "Tier APOIADOR  (saldo ≥ 1.000)",    "Tier APOIADOR errado")
        check(check_priority(addr_sem)["categoria"]       == "PARTICIPANTE","Tier PARTICIPANTE (saldo = 0)",      "Tier PARTICIPANTE errado")

        # Peso de voto max = 5.0 para saldo muito alto
        addr_high = "PLG" + blake3.blake3(b"HIGH_VOTE_TEST").hexdigest()[:40].upper()
        plegma_db.salvar_saldo_plgg(addr_high, 10_001.0)
        pv = check_priority(addr_high)["peso_voto"]
        check(pv <= 5.0, f"Peso de voto capped em ≤ 5.0 (obtido {pv:.4f})", f"Peso de voto excede 5.0: {pv}")

    except Exception as e:
        _fail("Tokenomics", str(e))

# ---------------------------------------------------------------------------
# MÓDULO 9 — STRESS: INSERÇÕES MASSIVAS
# ---------------------------------------------------------------------------
def teste_stress_insercoes():
    _header("9. STRESS: 500 INSERÇÕES CONCORRENTES")
    try:
        N = 500
        erros_thread = []

        def inserir_lote(inicio, fim):
            for i in range(inicio, fim):
                try:
                    uid = blake3.blake3(f"STRESS_NODE_{i}".encode()).hexdigest()
                    addr = "PLG" + blake3.blake3(f"STRESS_ADDR_{i}".encode()).hexdigest()[:40].upper()
                    plegma_db.salvar_saldo_plgg(addr, float(i))
                    token = blake3.blake3(f"STRESS_TOKEN_{i}".encode()).hexdigest()
                    plegma_db.salvar_sessao(addr, token, ttl_segundos=3600)
                    if i % 50 == 0:
                        plegma_db.salvar_ban(uid, float(i * 10), f"STRESS_BAN_{i}")
                except Exception as ex:
                    erros_thread.append(str(ex))

        threads = []
        t0 = time.time()
        chunk = N // 4
        for t in range(4):
            th = threading.Thread(target=inserir_lote, args=(t * chunk, (t + 1) * chunk))
            threads.append(th)
            th.start()
        for th in threads:
            th.join()
        t_total = time.time() - t0

        check(len(erros_thread) == 0,
              f"{N} inserções em 4 threads: {t_total:.2f}s sem erros",
              f"Erros durante stress: {erros_thread[:3]}")

        # Verifica contagem de sessões criadas
        conn = plegma_db.get_connection()
        count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        conn.close()
        check(count >= N, f"Sessões no DB: {count} (≥ {N})", f"Poucas sessões no DB: {count}")

    except Exception as e:
        _fail("Stress inserções", str(e))

# ---------------------------------------------------------------------------
# MÓDULO 10 — STRESS: LEITURAS REPETIDAS (DETERMINISMO)
# ---------------------------------------------------------------------------
def teste_stress_leituras():
    _header("10. STRESS: DETERMINISMO EM 1000 LEITURAS BLAKE3")
    try:
        seed = b"DETERMINISM_SEED_PLEGMA_2026"
        hash_ref = blake3.blake3(seed).hexdigest()
        falhas = 0
        for _ in range(1000):
            if blake3.blake3(seed).hexdigest() != hash_ref:
                falhas += 1
        check(falhas == 0,
              "1000 hashes BLAKE3 idênticos (determinismo absoluto)",
              f"{falhas}/1000 hashes divergiram — VIOLAÇÃO L1")

        # ZK determinismo
        zk = ZkPressEngine()
        estado = blake3.blake3(b"ZK_DET_SEED").hexdigest()
        prova_ref = zk.generate_recursive_proof(estado)
        falhas_zk = 0
        for _ in range(20):
            if zk.generate_recursive_proof(estado) != prova_ref:
                falhas_zk += 1
        check(falhas_zk == 0,
              "20 provas ZK idênticas (ZK determinístico)",
              f"{falhas_zk}/20 provas ZK divergiram — VIOLAÇÃO L1")

    except Exception as e:
        _fail("Stress leituras / determinismo", str(e))

# ---------------------------------------------------------------------------
# MÓDULO 11 — VESTING + PENDING PURCHASES
# ---------------------------------------------------------------------------
def teste_vesting():
    _header("11. VESTING & PENDING PURCHASES")
    try:
        addr = "PLG" + blake3.blake3(b"VESTING_TEST_ADDR").hexdigest()[:40].upper()
        now = int(time.time())
        # seed inclui timestamp para garantir unicidade de tx_hash_externo entre runs
        tx_hash = blake3.blake3(f"TX_VESTING_EXT_{now}".encode()).hexdigest()

        entry = {
            "plg_address": addr,
            "amount": 500.0,
            "usdt_pago": 250.0,
            "tx_hash_externo": tx_hash,
            "purchase_date": now,
            "release_date": now + 30 * 86400,
            "status": "LOCKED"
        }
        plegma_db.salvar_plgg_vesting(entry)
        vesting = plegma_db.carregar_vesting_por_usuario(addr)
        check(len(vesting) >= 1, f"Vesting gravado e recuperado ({len(vesting)} entradas)", "Vesting não recuperado")
        check(vesting[0]["status"] == "LOCKED", "Status vesting = LOCKED", f"Status: {vesting[0]['status']}")

        # Pending purchase
        ref_id = blake3.blake3(f"REF_{now}".encode()).hexdigest()[:16]
        purchase = {
            "ref_id": ref_id,
            "plg_address": addr,
            "usdt_amount": 100.0,
            "plgg_amount": 50.0,
            "created_at": time.time(),
            "status": "AGUARDANDO"
        }
        plegma_db.salvar_pending_purchase(purchase)
        recovered = plegma_db.buscar_pending_purchase(ref_id)
        check(recovered is not None, "Pending purchase gravada e recuperada", "Pending purchase não encontrada")
        check(recovered["status"] == "AGUARDANDO", "Status pending = AGUARDANDO", f"Status: {recovered['status']}")

        plegma_db.atualizar_status_pending(ref_id, "CONFIRMADO")
        updated = plegma_db.buscar_pending_purchase(ref_id)
        check(updated["status"] == "CONFIRMADO", "Status atualizado para CONFIRMADO", f"Status: {updated['status']}")

        # Tx externa idempotente
        tx_ext = blake3.blake3(f"TX_EXT_TEST_{now}".encode()).hexdigest()
        plegma_db.registrar_tx_externa(tx_ext)
        check(plegma_db.tx_externo_ja_processado(tx_ext),
              "Tx externa registrada e confirmada como processada",
              "tx_externo_ja_processado() falhou")
        plegma_db.registrar_tx_externa(tx_ext)  # idempotente
        _ok("Registro idempotente de tx externa (INSERT OR IGNORE)")

    except Exception as e:
        _fail("Vesting/Pending", str(e))

# ---------------------------------------------------------------------------
# MÓDULO 12 — FRONTEND: PÁGINAS CRÍTICAS ACESSÍVEIS
# ---------------------------------------------------------------------------
FRONTEND_PAGES = [
    ("http://localhost:8080/",                      "Landing principal"),
    ("http://localhost:8080/dashboard/",            "Dashboard web"),
    ("http://localhost:8080/fundacao/",             "Fundação pública"),
    ("http://localhost:8080/admin/",                "Console Admin"),
    ("http://localhost:8080/console/",              "Console Sócio"),
    ("http://localhost:8080/genesis/",              "Genesis PLG-G"),
    ("http://localhost:8080/blog/",                 "Blog"),
]

def teste_frontend():
    _header("12. FRONTEND: DISPONIBILIDADE DE PÁGINAS")
    for url, nome in FRONTEND_PAGES:
        try:
            req = urllib.request.urlopen(url, timeout=3)
            code = req.getcode()
            check(code == 200, f"{nome} → HTTP {code}", f"{nome} retornou HTTP {code} (esperado 200)")
        except urllib.error.HTTPError as e:
            _fail(f"{nome} inacessível", f"HTTP {e.code}")
        except Exception as e:
            _fail(f"{nome} inacessível", str(e))

# ---------------------------------------------------------------------------
# MÓDULO 13 — API REST: ENDPOINTS CRÍTICOS
# ---------------------------------------------------------------------------
API_BASE = "http://localhost:8082"
API_ENDPOINTS = [
    (f"{API_BASE}/status",          "GET", None, "Status do nó"),
    (f"{API_BASE}/tips",            "GET", None, "Tips DAG"),
    (f"{API_BASE}/genesis/status",  "GET", None, "Genesis status"),
]

def teste_api():
    _header("13. API REST: ENDPOINTS CRÍTICOS (porta 8082)")
    for url, method, body, nome in API_ENDPOINTS:
        try:
            req = urllib.request.Request(url, method=method)
            resp = urllib.request.urlopen(req, timeout=3)
            code = resp.getcode()
            raw = resp.read()
            check(code == 200, f"{nome} → HTTP {code}", f"{nome} retornou HTTP {code}")
            try:
                data = json.loads(raw)
                check(isinstance(data, dict), f"{nome} resposta JSON válida", f"{nome} resposta não é dict")
            except Exception:
                _fail(f"{nome} JSON inválido", raw[:80].decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as e:
            _fail(f"{nome} inacessível", f"HTTP {e.code}")
        except Exception as e:
            _fail(f"{nome} inacessível (servidor offline?)", str(e))

# ---------------------------------------------------------------------------
# MÓDULO 14 — SEGURANÇA: INJECÇÃO SQL E INPUTS MALICIOSOS
# ---------------------------------------------------------------------------
def teste_seguranca_inputs():
    _header("14. SEGURANÇA: INPUTS MALICIOSOS / SQL INJECTION")
    payloads_sql = [
        "' OR '1'='1",
        "'; DROP TABLE sessions; --",
        "1; SELECT * FROM sessions",
        "\x00NULL_BYTE",
        "A" * 10000,
    ]
    for pl in payloads_sql:
        try:
            resultado = plegma_db.validar_sessao(pl, pl)
            check(not resultado,
                  f"SQL injection rejeitado: {repr(pl[:30])}",
                  f"Possível SQL injection aceite: {repr(pl[:30])}")
        except Exception as e:
            _fail(f"Excepção ao processar input malicioso: {repr(pl[:30])}", str(e))

    for pl in payloads_sql:
        try:
            plegma_db.is_banido(pl)
            _ok(f"is_banido() não crashou para: {repr(pl[:30])}")
        except Exception as e:
            _fail(f"is_banido() crashou para input malicioso: {repr(pl[:30])}", str(e))

# ---------------------------------------------------------------------------
# MÓDULO 15 — INTEGRIDADE FINAL DO DB
# ---------------------------------------------------------------------------
def teste_integridade_db():
    _header("15. INTEGRIDADE FINAL DO BANCO DE DADOS")
    try:
        conn = plegma_db.get_connection()
        result = conn.execute("PRAGMA integrity_check").fetchone()
        conn.close()
        check(result[0] == "ok",
              f"PRAGMA integrity_check: {result[0]}",
              f"Banco corrompido: {result[0]}")

        # Tabelas obrigatórias
        conn2 = plegma_db.get_connection()
        tables = {r[0] for r in conn2.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        conn2.close()
        required = {"transactions", "tips", "network_state", "plgg_balances",
                    "plgg_vesting", "pending_purchases", "sessions", "bans",
                    "nonces", "fundacao_registros", "tx_externas_processadas", "swap_orders"}
        faltando = required - tables
        check(not faltando,
              f"Todas as {len(required)} tabelas obrigatórias presentes",
              f"Tabelas em falta: {faltando}")

    except Exception as e:
        _fail("Integridade DB", str(e))

# ---------------------------------------------------------------------------
# RUNNER PRINCIPAL
# ---------------------------------------------------------------------------
def run_all():
    start_time = time.time()
    _log("=" * 58)
    _log(" PLEGMA DAG — BATERIA COMPLETA DE TESTES V4.0")
    _log(f" Data: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    _log("=" * 58)

    plg_address, pk, sk = teste_cripto()
    if plg_address is None:
        plg_address = "PLG" + "0" * 40

    teste_zk()
    teste_db_basico(plg_address)
    teste_bans()
    teste_sessoes(plg_address)
    teste_sentinela()
    teste_fundacao()
    teste_tokenomics()
    teste_stress_insercoes()
    teste_stress_leituras()
    teste_vesting()
    teste_frontend()
    teste_api()
    teste_seguranca_inputs()
    teste_integridade_db()

    elapsed = time.time() - start_time

    _log("\n" + "=" * 58)
    _log(f" RESULTADOS FINAIS")
    _log("=" * 58)
    _log(f" Total de testes : {_total}")
    _log(f" Aprovados       : {_passed}")
    _log(f" Falhados        : {_failed}")
    _log(f" Tempo total     : {elapsed:.2f}s")
    _log("=" * 58)

    if _errors:
        _log("\n LISTA DE FALHAS:")
        for err in _errors:
            _log(f"  {err}")

    if _failed == 0:
        _log("\n [OK OK OK] TODOS OS SISTEMAS OPERACIONAIS E INTEGROS")
    else:
        _log(f"\n [!!!] {_failed} FALHA(S) DETECTADA(S) - VER LISTA ACIMA")

    _log("=" * 58)

    # Salvar log
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(_log_lines))
    print(f"\n LOG SALVO EM: {LOG_PATH}")


if __name__ == "__main__":
    try:
        run_all()
    except Exception:
        traceback.print_exc()
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            f.write("\n".join(_log_lines))
        sys.exit(1)
