import logging
import platform
import time

_log = logging.getLogger(__name__)

# ── Blindagem de Oráculo Determinístico (Hard Fail) ─────────
try:
    import blake3 as _blake3
except ImportError:
    raise RuntimeError("[FALHA FATAL] Módulo blake3 ausente no Hardware Detector.")

def _b3_hash(data: bytes) -> str:
    return _blake3.blake3(data).hexdigest()

# =============================================================================
# HARDWARE DETECTOR — Detecção Real de Hardware V4.0 (PÓS-QUÂNTICO)
# Usa psutil para leitura real de CPU/RAM/GPU
# Fallback gracioso se psutil não estiver disponível
# Hegemonia BLAKE3 para geração de Identidade de Máquina
# =============================================================================

try:
    import psutil
    PSUTIL_OK = True
except ImportError:
    PSUTIL_OK = False

try:
    import subprocess
    SUBPROCESS_OK = True
except ImportError:
    SUBPROCESS_OK = False


def detectar_hardware() -> dict:
    """
    Detecta o hardware real do sistema.
    Retorna dict com todas as informações necessárias para classificação.
    """
    info = {
        "os"               : platform.system(),
        "os_version"       : platform.version()[:60],
        "machine"          : platform.machine(),
        "cpu_model"        : platform.processor() or "Desconhecido",
        "cpu_cores_fisicos": 1,
        "cpu_cores_logicos": 1,
        "cpu_freq_mhz"     : 0,
        "ram_total_gb"     : 4.0,
        "ram_disponivel_gb": 2.0,
        "has_gpu"          : False,
        "gpu_nome"         : "Não detectada",
        "gpu_vram_gb"      : 0.0,
        "device_type"      : "DESKTOP",
        "temperatura_c"    : 0.0,
    }

    # ── CPU e RAM via psutil ─────────────────────────────────────────────────
    if PSUTIL_OK:
        try:
            info["cpu_cores_fisicos"] = psutil.cpu_count(logical=False) or 1
            info["cpu_cores_logicos"] = psutil.cpu_count(logical=True)  or 1
            freq = psutil.cpu_freq()
            if freq:
                info["cpu_freq_mhz"] = int(freq.max or freq.current or 0)
            mem = psutil.virtual_memory()
            info["ram_total_gb"]     = round(mem.total / (1024**3), 1)
            info["ram_disponivel_gb"]= round(mem.available / (1024**3), 1)
        except Exception:
            pass

        try:
            temps = psutil.sensors_temperatures()
            if temps:
                for key in ('coretemp', 'cpu_thermal', 'k10temp'):
                    if key in temps and temps[key]:
                        info["temperatura_c"] = temps[key][0].current
                        break
        except Exception:
            pass

    # ── Detecção de GPU ──────────────────────────────────────────────────────
    if SUBPROCESS_OK:
        try:
            out = subprocess.check_output(
                ["nvidia-smi",
                 "--query-gpu=name,memory.total",
                 "--format=csv,noheader,nounits"],
                stderr=subprocess.DEVNULL, timeout=5
            ).decode().strip()
            if out:
                parts = out.split(",")
                info["gpu_nome"]    = parts[0].strip()
                info["gpu_vram_gb"] = round(int(parts[1].strip()) / 1024, 1)
                info["has_gpu"]     = True
        except Exception:
            pass

        if not info["has_gpu"] and platform.system() == "Windows":
            try:
                out = subprocess.check_output(
                    ["wmic", "path", "win32_VideoController",
                     "get", "name,AdapterRAM", "/format:csv"],
                    stderr=subprocess.DEVNULL, timeout=5
                ).decode()
                for line in out.strip().splitlines():
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) >= 3 and parts[2] and parts[2] != "Name":
                        ram_bytes = int(parts[1]) if parts[1].isdigit() else 0
                        vram_gb   = round(ram_bytes / (1024**3), 1)
                        if vram_gb >= 1.0:
                            info["gpu_nome"]    = parts[2]
                            info["gpu_vram_gb"] = vram_gb
                            info["has_gpu"]     = True
                            break
            except Exception:
                pass

    # ── Tipo de dispositivo ──────────────────────────────────────────────────
    if PSUTIL_OK:
        try:
            bat = psutil.sensors_battery()
            if bat is not None:
                info["device_type"] = "NOTEBOOK"
        except Exception:
            pass

    return info


def calcular_score(hw: dict) -> int:
    """
    Calcula o score de performance seguindo a lógica do core_consenso.
    """
    score = 0
    score += hw["cpu_cores_fisicos"] * 50
    score += hw["ram_total_gb"] * 5

    if hw["has_gpu"]:
        score += 500
        score += hw["gpu_vram_gb"] * 100

    if hw["device_type"] == "NOTEBOOK":
        score = int(score * 0.7)

    return int(score)


def gerar_node_id(hw: dict) -> str:
    """
    Gera um node_id determinístico baseado no hardware, selado com BLAKE3.
    """
    fingerprint = (
        f"{hw['cpu_model']}"
        f"{hw['cpu_cores_fisicos']}"
        f"{hw['ram_total_gb']}"
        f"{hw['gpu_nome']}"
        f"{platform.node()}"
    )
    h = _b3_hash(fingerprint.encode())[:16].upper()
    return f"NODE_{h}"


def classificar(hw: dict) -> dict:
    """
    Classifica o hardware como VALIDATOR ou PROVER.
    Retorna dict completo com tipo, score, categoria, descrição.
    """
    score = calcular_score(hw)

    if hw["device_type"] == "NOTEBOOK":
        categoria = "NOTEBOOK"
    elif hw["has_gpu"] and hw["gpu_vram_gb"] >= 4.0:
        categoria = "GPU"
    elif score >= 1000:
        categoria = "DESKTOP_HIGH"
    else:
        categoria = "DESKTOP_BASIC"

    if score < 1000:
        tipo     = "VALIDATOR"
        descricao= "Nó Validador Técnico — Valida provas ZK na rede"
    else:
        tipo     = "PROVER"
        descricao= "Prover — Gera provas ZK e calcula hashes BLAKE3"

    return {
        "tipo"      : tipo,
        "score"     : score,
        "categoria" : categoria,
        "descricao" : descricao,
        "node_id"   : gerar_node_id(hw)
    }


if __name__ == "__main__":
    hw    = detectar_hardware()
    clase = classificar(hw)
    _log.info(f"CPU     : {hw['cpu_model']}")
    _log.info(f"Núcleos : {hw['cpu_cores_fisicos']} físicos / {hw['cpu_cores_logicos']} lógicos")
    _log.info(f"RAM     : {hw['ram_total_gb']} GB")
    _log.info(f"GPU     : {hw['gpu_nome']} ({hw['gpu_vram_gb']} GB VRAM)")
    _log.info(f"Tipo    : {hw['device_type']}")
    _log.info(f"Score   : {clase['score']}")
    _log.info(f"Classe  : {clase['tipo']} ({clase['categoria']})")
    _log.info(f"Node ID : {clase['node_id']}")