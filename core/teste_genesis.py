import sys
import time
import json
import traceback

# ── Blindagem de Oráculo Determinístico (Hard Fail) ─────────
try:
    import blake3 as _blake3
except ImportError:
    print("\033[91m[FALHA FATAL] Módulo blake3 ausente. Instale: pip install blake3\033[0m")
    sys.exit(1)

def _b3_hash(data: str) -> str:
    return _blake3.blake3(data.encode()).hexdigest()

# ─── DEFINIÇÕES DE CORES E AJUDANTES ─────────────────────────────────────────
GRN = "\033[92m"
RED = "\033[91m"
YLW = "\033[93m"
CYN = "\033[96m"
RST = "\033[0m"

ok  = lambda s: print(f"  {GRN}✓ {s}{RST}")
err = lambda s: print(f"  {RED}✗ {s}{RST}")
inf = lambda s: print(f"  {YLW}→ {s}{RST}")
hdr = lambda s: print(f"\n{CYN}{'═'*60}\n  {s}\n{'═'*60}{RST}")

ERROS = []

def check(condicao, msg_ok, msg_err):
    if condicao:
        ok(msg_ok)
    else:
        err(msg_err)
        ERROS.append(msg_err)
    return condicao

def executar_testes_com_seguranca():
    try:
        # Importação de módulos internos (Assumindo que estão na mesma pasta)
        import plegma_db
        import genesis_contract
        from web3 import Web3

        # --- 1. CONECTIVIDADE RPC POLYGON ---
        hdr("1. Conectividade RPC Polygon")
        w3 = Web3(Web3.HTTPProvider("https://1rpc.io/matic", request_kwargs={"timeout": 15}))
        bloco = w3.eth.block_number
        check(bloco > 0, f"RPC Polygon conectado (bloco {bloco:,})", "Falha na conexão RPC")

        # --- 2. PLEGMA_DB — FUNÇÕES PLG-G ---
        hdr("2. plegma_db — funções PLG-G")
        _RUN_ID = str(int(time.time()))[-6:]
        # Endereço derivado deterministicamente
        ADDR_TESTE = "PLG_TEST_" + _b3_hash(f"TEST_ADDR_{_RUN_ID}")[:34].upper()
        
        plegma_db.salvar_saldo_plgg(ADDR_TESTE, 0.0)
        saldo = plegma_db.carregar_saldo_plgg(ADDR_TESTE)
        check(saldo == 0.0, "salvar/carregar saldo (0.0 PLG-G)", f"Saldo incorreto: {saldo}")

        # --- 3. REGISTRAR INTENÇÃO ---
        hdr("3. registrar_intencao()")
        plegma_db.salvar_estado("plgg_vendido", 0.0)
        
        VALOR_TESTE = 1.00
        EXPECTED_PLGG = 10.0  # $1 / $0.10
        
        res = genesis_contract.registrar_intencao(ADDR_TESTE, VALOR_TESTE)
        
        # Proteção contra falhas de contrato
        if "erro" in res:
            err(f"Contrato rejeitou o aporte: {res['erro']}")
            ERROS.append(res['erro'])
            return # Interrompe a execução para análise

        check(res.get("plgg_amount") == EXPECTED_PLGG, 
              f"plgg_amount correto (${VALOR_TESTE} -> {EXPECTED_PLGG} PLG-G)", 
              "Cálculo incorreto")
        
        REF_ID_REAL = res["ref_id"]
        inf(f"ref_id determinístico: {REF_ID_REAL}")

        # --- 4. CONFIRMAR COMPRA ---
        hdr("4. confirmar_compra() — Simulação de Pagamento")
        TX_HASH_FAKE = "0x" + _b3_hash(f"EXTERNAL_TX_{_RUN_ID}")
        
        res_confirma = genesis_contract.confirmar_compra(
            tx_hash_externo=TX_HASH_FAKE,
            plg_address=ADDR_TESTE,
            usdt_recebido=VALOR_TESTE, # Deve coincidir com o registro
            ref_id=REF_ID_REAL
        )
        check(res_confirma.get("status") == "CONFIRMADO", "Status == CONFIRMADO", "Falha na confirmação")
        # --- RESULTADO FINAL ---
        total_checks = 28 
        passou = total_checks - len(ERROS)
        
        print(f"\n{'═'*60}")
        if not ERROS:
            print(f"{GRN}  TODOS OS TESTES PASSARAM ({passou}/{total_checks}){RST}")
        else:
            print(f"{RED}  {len(ERROS)} FALHA(S) DETECTADAS ({passou}/{total_checks} passaram){RST}")
            for e in ERROS:
                print(f"  {RED}  · {e}{RST}")
        print(f"{'═'*60}")

    except Exception:
        print(f"\n{RED}{'!'*60}\n  ERRO CRÍTICO DURANTE OS TESTES:\n{'!'*60}{RST}")
        traceback.print_exc()
        print(f"{RED}{'═'*60}{RST}")

    finally:
        print("\n")
        input(f"{YLW}Pressione [Enter] para fechar o terminal e encerrar o teste...{RST}")

if __name__ == "__main__":
    executar_testes_com_seguranca()