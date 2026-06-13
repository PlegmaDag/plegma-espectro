#!/usr/bin/env python3
"""
PLEGMA ORCHESTRATOR — Flutter Tester Agent
Lança emulador Android, instala APK debug e valida que o app arranca sem crash.
Pipeline: build debug → launch emulator → install → smoke test via logcat → report
"""

import subprocess
import sys
import time
import re
import shutil
from pathlib import Path
from . import BaseAgent, AgentResult

# Windows: flutter e adb são .bat/.cmd — precisam de shell=True ou path completo
_IS_WIN  = sys.platform == "win32"
_FLUTTER = shutil.which("flutter") or "flutter"
_ADB     = shutil.which("adb")     or "adb"

def _run(cmd, **kwargs):
    """subprocess.run com shell=True no Windows para encontrar .bat commands."""
    if _IS_WIN:
        # Converter lista para string no Windows (shell=True requer string)
        if isinstance(cmd, list):
            cmd = " ".join(f'"{c}"' if " " in str(c) else str(c) for c in cmd)
        kwargs.setdefault("shell", True)
    return subprocess.run(cmd, **kwargs)

APP_DIR      = Path(__file__).parent.parent.parent / "plegma_app"
EMULATOR_ID  = "Medium_Phone_API_36.1"
BUILD_TIMEOUT = 600  # segundos máx para build debug (APK ~175s release, mais debug)
BOOT_TIMEOUT  = 120  # segundos máx para o emulador arrancar
SMOKE_WAIT    = 20   # segundos a observar logcat após install


class FlutterTesterAgent(BaseAgent):
    name = "flutter_tester"

    def _execute(self, task: str, context: dict) -> AgentResult:
        details = []

        # ── 1. Build debug APK ───────────────────────────────────────────────
        details.append("1. flutter build apk --debug")
        try:
          build = _run(
              ["flutter", "build", "apk", "--debug"],
              capture_output=True, text=True, cwd=str(APP_DIR),
              encoding="utf-8", errors="replace", timeout=BUILD_TIMEOUT
          )
        except subprocess.TimeoutExpired:
            return AgentResult(
                agent=self.name, status="FAILURE",
                summary=f"Build debug excedeu {BUILD_TIMEOUT}s", details=details
            )
        if build.returncode != 0:
            err = (build.stdout + build.stderr)[-800:]
            return AgentResult(
                agent=self.name, status="FAILURE",
                summary="Build debug falhou", details=[err]
            )
        apk_path = APP_DIR / "build/app/outputs/flutter-apk/app-debug.apk"
        if not apk_path.exists():
            return AgentResult(
                agent=self.name, status="FAILURE",
                summary="APK debug não gerado", details=details
            )
        apk_mb = apk_path.stat().st_size / (1024 * 1024)
        details.append(f"   ✓ APK debug gerado ({apk_mb:.1f} MB)")

        # ── 2. Verificar se emulador já está a correr ─────────────────────────
        details.append("2. Verificar emuladores activos")
        adb_devs = _run(
            ["adb", "devices"], capture_output=True, text=True, timeout=10
        )
        emulator_online = "emulator" in adb_devs.stdout and "device" in adb_devs.stdout

        if not emulator_online:
            details.append("   Emulador offline — a lançar...")
            subprocess.Popen(
                f'flutter emulators --launch {EMULATOR_ID}' if _IS_WIN else
                ["flutter", "emulators", "--launch", EMULATOR_ID],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                shell=_IS_WIN
            )
            # Aguardar boot
            booted = self._wait_for_emulator(BOOT_TIMEOUT)
            if not booted:
                return AgentResult(
                    agent=self.name, status="FAILURE",
                    summary=f"Emulador não arrancou em {BOOT_TIMEOUT}s",
                    details=details
                )
            details.append("   ✓ Emulador pronto")
        else:
            details.append("   ✓ Emulador já activo")

        # ── 3. Instalar APK ──────────────────────────────────────────────────
        details.append("3. adb install -r app-debug.apk")
        install = _run(
            ["adb", "install", "-r", str(apk_path)],
            capture_output=True, text=True, timeout=60
        )
        if install.returncode != 0 or "Success" not in install.stdout:
            return AgentResult(
                agent=self.name, status="FAILURE",
                summary="Instalação falhou",
                details=details + [install.stdout, install.stderr]
            )
        details.append("   ✓ APK instalado")

        # ── 4. Lançar app e monitorizar logcat ───────────────────────────────
        details.append(f"4. Lançar app e observar {SMOKE_WAIT}s de logcat")
        _run(
            ["adb", "shell", "am", "start",
             "-n", "com.plegmadag.app/com.plegmadag.app.MainActivity"],
            capture_output=True, text=True, timeout=15
        )
        time.sleep(2)

        # Capturar logcat dos últimos SMOKE_WAIT segundos
        logcat = _run(
            ["adb", "logcat", "-d", "-t", str(SMOKE_WAIT * 20),
             "--pid=$(adb shell pidof com.plegmadag.app 2>/dev/null || echo 0)"],
            capture_output=True, text=True, timeout=SMOKE_WAIT + 10, shell=False
        )
        log_output = logcat.stdout + logcat.stderr

        # Verificar crashes
        crash_patterns = [
            r"FATAL EXCEPTION",
            r"AndroidRuntime.*FATAL",
            r"Process.*has died",
            r"FlutterActivity.*crash",
        ]
        crashes = [line for line in log_output.splitlines()
                   if any(re.search(p, line) for p in crash_patterns)]

        if crashes:
            return AgentResult(
                agent=self.name, status="FAILURE",
                summary=f"App crashou ({len(crashes)} erros fatais)",
                details=details + crashes[:5]
            )

        details.append("   ✓ App arrancou sem crash fatal")

        # ── 5. Verificar PID activo ──────────────────────────────────────────
        pid = _run(
            ["adb", "shell", "pidof", "com.plegmadag.app"],
            capture_output=True, text=True, timeout=10
        ).stdout.strip()

        if pid and pid.isdigit():
            details.append(f"   ✓ Processo activo (PID {pid})")
            return AgentResult(
                agent=self.name, status="SUCCESS",
                summary=f"Smoke test OK — APK {apk_mb:.1f}MB · PID {pid} activo",
                details=details
            )
        else:
            return AgentResult(
                agent=self.name, status="PARTIAL",
                summary="App instalado mas PID não detectado (pode ter encerrado)",
                details=details
            )

    def _wait_for_emulator(self, timeout: int) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            result = _run(
                ["adb", "shell", "getprop", "sys.boot_completed"],
                capture_output=True, text=True, timeout=10
            )
            if result.stdout.strip() == "1":
                time.sleep(3)
                return True
            time.sleep(5)
        return False
