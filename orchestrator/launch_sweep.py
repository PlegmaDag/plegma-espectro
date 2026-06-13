"""
PRE-LAUNCH SWEEP — Verifica todos os endpoints e serviços críticos.
Lançamento: 2026-05-09 18:00 Madrid (16:00 UTC)
"""
import paramiko
import json
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from daemon_config import NODES, SSH_KEY

ENDPOINTS = [
    ("http://localhost:8080/api/status",           "core status"),
    ("http://localhost:8080/api/dag/status",        "dag status"),
    ("http://localhost:8080/api/genesis/status",    "genesis status"),
    ("http://localhost:8080/api/social/posts?limit=3", "social posts"),
    ("http://localhost:8082/api/auth/challenge",    "auth challenge"),
    ("http://localhost:8083/wallet/status",         "wallet status"),
]

SERVICES = ["plegma-core", "plegma-auth", "plegma-wallet", "plegma-miner"]

key = paramiko.Ed25519Key.from_private_key_file(SSH_KEY)

issues = []

for node_id, node in NODES.items():
    label = node['label']
    try:
        c = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        c.connect(node['ip'], username='root', pkey=key, timeout=12)
        transport = c.get_transport()
        if transport:
            transport.set_keepalive(20)

        print(f"\n{'='*50}")
        print(f"  {label} ({node['ip']})")
        print(f"{'='*50}")

        # 1. Serviços systemd
        svc_cmd = " ".join([f"systemctl is-active {s}" for s in SERVICES])
        _, stdout, _ = c.exec_command("; ".join([f"echo -n '{s}:'; systemctl is-active {s}" for s in SERVICES]))
        svc_out = stdout.read().decode().strip()
        print(f"\n[Serviços]")
        for line in svc_out.split('\n'):
            ok = 'active' in line and 'inactive' not in line
            sym = "✓" if ok else "✗"
            if not ok:
                issues.append(f"{label}: serviço {line}")
            print(f"  {sym} {line}")

        # 2. Endpoints HTTP
        print(f"\n[Endpoints HTTP]")
        for url, name in ENDPOINTS:
            _, stdout, _ = c.exec_command(
                f"code=$(curl -s -o /dev/null -w '%{{http_code}}' --max-time 5 '{url}' 2>/dev/null); echo $code",
                timeout=10
            )
            code = stdout.read().decode().strip()
            ok = code in ('200', '201')
            sym = "✓" if ok else "✗"
            if not ok:
                # Tentar obter o corpo para diagnóstico
                _, stdout2, _ = c.exec_command(
                    f"curl -s --max-time 5 '{url}' 2>/dev/null | head -c 200",
                    timeout=10
                )
                body = stdout2.read().decode().strip()
                issues.append(f"{label}: {name} HTTP {code} — {body[:100]}")
            print(f"  {sym} {name}: HTTP {code}")

        # 3. Genesis status details
        _, stdout, _ = c.exec_command(
            "curl -s --max-time 5 http://localhost:8080/api/genesis/status 2>/dev/null",
            timeout=10
        )
        gen_raw = stdout.read().decode().strip()
        try:
            gen = json.loads(gen_raw) if gen_raw else {}
            supply = gen.get("supply_total", gen.get("total_supply", 0))
            socios = gen.get("socios", gen.get("total_socios", 0))
            fase   = gen.get("fase", gen.get("phase", "?"))
            print(f"\n[Genesis] supply={supply:,} PLG-G | sócios={socios} | fase={fase}")
        except Exception:
            print(f"\n[Genesis] parse error: {gen_raw[:80]}")

        # 4. Core status details
        _, stdout, _ = c.exec_command(
            "curl -s --max-time 5 http://localhost:8080/api/status 2>/dev/null",
            timeout=10
        )
        core_raw = stdout.read().decode().strip()
        try:
            core = json.loads(core_raw) if core_raw else {}
            txs  = core.get("total_transacoes", 0)
            nos  = core.get("nos_ativos", 0)
            tips = core.get("tips_pendentes", 0)
            print(f"[Core] txs={txs} | nós={nos} | tips={tips}")
        except Exception:
            print(f"[Core] parse error: {core_raw[:80]}")

        # 5. Disk space (servidores não podem ficar sem disco)
        _, stdout, _ = c.exec_command("df -h / | tail -1 | awk '{print $4\" livre de \"$2\" (\"$5\" usado)\"}'")
        disk = stdout.read().decode().strip()
        print(f"[Disco] {disk}")

        # 6. Memória
        _, stdout, _ = c.exec_command("free -m | awk '/^Mem:/{printf \"%dMB livre de %dMB\\n\", $7, $2}'")
        mem = stdout.read().decode().strip()
        print(f"[Memória] {mem}")

        c.close()
    except Exception as e:
        print(f"\n=== {label} === FALHOU: {e}")
        issues.append(f"{label}: SSH falhou — {e}")

print(f"\n{'='*50}")
print(f"  RESUMO PRÉ-LANÇAMENTO")
print(f"{'='*50}")
if not issues:
    print("  TUDO OK — Sistema pronto para lançamento.")
else:
    print(f"  {len(issues)} PROBLEMA(S) DETECTADO(S):")
    for i, issue in enumerate(issues, 1):
        print(f"  {i}. {issue}")
