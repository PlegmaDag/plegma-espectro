"""
test_plegma_integrity.py — PLEGMA DAG V4.0
Auditoria de Conformidade e Integração de Núcleo
"""

import os
import sys
import time
import traceback

# Verificação de Dependências Rígidas
try:
    import blake3
    from dilithium_py.dilithium import Dilithium3
except ImportError as e:
    print(f"[FALHA FATAL] Dependências de núcleo ausentes: {e}")
    sys.exit(1)

# Importação dos Módulos Refatorados
try:
    from zk_press import DagSealEngine as ZkPressEngine
    import plegma_db
except ImportError as e:
    print(f"[FALHA FATAL] Módulos PLEGMA não localizados: {e}")
    sys.exit(1)

def print_header(title):
    print(f"\n[{title.center(46, '-')}]")

def assert_condition(condition, success_msg, fail_msg):
    if condition:
        print(f" [✓] {success_msg}")
    else:
        print(f" [X] FALHA CRÍTICA: {fail_msg}")
        raise RuntimeError(fail_msg)

def run_diagnostics():
    print("==================================================")
    print(" INICIANDO DIAGNÓSTICO DE INTEGRIDADE PLEGMA DAG  ")
    print("==================================================")

    # ---------------------------------------------------------
    print_header("1. HEGEMONIA BLAKE3 & DILITHIUM3")
    # ---------------------------------------------------------
    try:
        # Geração de Chaves
        pk, sk = Dilithium3.keygen()
        assert_condition(len(pk) > 1000, "Chave Pública LATTICE gerada (Dilithium3)", "Chave incorreta")
        
        # Derivação de Endereço Determinístico
        addr_hash = blake3.blake3(pk).hexdigest()[:40].upper()
        plg_address = f"PLG{addr_hash}"
        assert_condition(plg_address.startswith("PLG") and len(plg_address) == 43, 
                         f"Endereço derivado via BLAKE3: {plg_address[:12]}...", "Formato de endereço inválido")

        # Assinatura e Verificação
        payload = b"SYS_INTEGRITY_CHECK_2026"
        signature = Dilithium3.sign(sk, payload)
        is_valid = Dilithium3.verify(pk, payload, signature)
        assert_condition(is_valid, "Assinatura Pós-Quântica verificada com sucesso", "Falha na verificação da assinatura")
    except Exception as e:
        assert_condition(False, "", f"Erro no motor criptográfico: {e}")

    # ---------------------------------------------------------
    print_header("2. MOTOR ZK-PRESS V4.0 (LATTICE SNARK)")
    # ---------------------------------------------------------
    try:
        zk = ZkPressEngine()
        estado_teste = blake3.blake3(b"TEST_STATE").hexdigest()
        
        t0 = time.time()
        prova = zk.generate_recursive_proof(estado_teste)
        t_gen = (time.time() - t0) * 1000
        tamanho_kb = len(prova) / 1024

        assert_condition(tamanho_kb <= 22, 
                         f"Compressão Zk-Press OK: {tamanho_kb:.2f} KB (Limite: 22KB)", "Estatuto de compressão excedido (>22KB)")
        assert_condition(tamanho_kb >= 15, 
                         f"Densidade de Matriz Lattice OK: {tamanho_kb:.2f} KB", "Prova leve demais. Falha na simulação Lattice")
        
        is_proof_valid = zk.verify_proof(prova, estado_teste)
        assert_condition(is_proof_valid, 
                         f"Prova determinística verificada em {t_gen:.0f}ms", "Falha na reconstrução de Fiat-Shamir")
    except Exception as e:
        assert_condition(False, "", f"Erro no motor ZK: {e}")

    # ---------------------------------------------------------
    print_header("3. PERSISTÊNCIA DETERMINÍSTICA (DB V4)")
    # ---------------------------------------------------------
    try:
        # Inicializa o DB
        plegma_db.inicializar_banco()
        assert_condition(os.path.exists(plegma_db.DB_PATH), "Banco SQLite V4 instanciado", "Arquivo DB não criado")

        # Teste de Escudo / Checksum BLAKE3
        uid_teste = blake3.blake3(b"MALICIOUS_NODE").hexdigest()
        plegma_db.salvar_ban(uid_teste, 1000.0, "TESTE_INTEGRIDADE")
        
        bans = plegma_db.carregar_bans()
        assert_condition(uid_teste in bans, "Checksum BLAKE3 de Slashing persistido e validado", "Falha de integridade no DB")
        
        # Teste de Sessão
        token_teste = blake3.blake3(b"TEST_TOKEN").hexdigest()
        plegma_db.salvar_sessao(plg_address, token_teste, 300)
        sess_valida = plegma_db.validar_sessao(plg_address, token_teste)
        assert_condition(sess_valida, "Estado de sessão gravado e lido", "Falha na recuperação de sessão")
        
    except Exception as e:
        assert_condition(False, "", f"Erro na camada de dados: {e}")

    print("==================================================")
    print(" [✓] TODOS OS SISTEMAS OPERACIONAIS E ÍNTEGROS    ")
    print("==================================================")

if __name__ == "__main__":
    try:
        run_diagnostics()
        input("\nPressione ENTER para encerrar o diagnóstico...")
    except Exception:
        print("\n[!] DIAGNÓSTICO INTERROMPIDO DEVIDO A FALHA ESTRUTURAL.")
        traceback.print_exc()
        input("\nPressione ENTER para fechar o terminal...")
        sys.exit(1)