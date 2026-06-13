#!/bin/bash
# restart_service.sh — Sequência de reinício em 3 fases
# Uso : ./restart_service.sh [nome-do-serviço]
# Omitir argumento reinicia TODOS os serviços PLEGMA.

set -euo pipefail

# ── Mapa serviço → script Python → porta ────────────────────────────────────
declare -A SCRIPT_MAP=(
    [plegma-core]="/root/PLEGMA_CORE/core_vm.py"
    [plegma-auth]="/root/PLEGMA_CORE/auth_server.py"
    [plegma-wallet]="/root/PLEGMA_CORE/wallet_server.py"
    [plegma-shield]="/root/PLEGMA_CORE/shield_server.py"
    [plegma-miner]="/root/PLEGMA_CORE/miner_daemon.py"
)
declare -A PORT_MAP=(
    [plegma-core]=8080
    [plegma-auth]=8082
    [plegma-wallet]=8083
    [plegma-shield]=8085
    [plegma-miner]=8084
)
ALL_SERVICES=("plegma-core" "plegma-auth" "plegma-wallet" "plegma-shield" "plegma-miner")

MAX_TENTATIVAS=3
LOG_DIR="/tmp"

# ── Utilitários ──────────────────────────────────────────────────────────────
log() {
    local svc="$1"; shift
    echo "[$(date '+%H:%M:%S')] [$svc] $*" | tee -a "${LOG_DIR}/restart_${svc}.log"
}

esta_ativo() {
    systemctl is-active "$1" >/dev/null 2>&1
}

aguardar_ativo() {
    local svc="$1" espera="${2:-4}"
    sleep "$espera"
    esta_ativo "$svc"
}

# ── FASE 1 — systemctl restart (método nativo systemd) ──────────────────────
# O daemon gere o ciclo completo: envia SIGTERM, aguarda, inicia novo processo.
# Mais limpo — preserva dependências e triggers de systemd.
fase1() {
    local svc="$1"
    log "$svc" "FASE 1 — systemctl restart (modo nativo)"
    for i in 1 2 3; do
        log "$svc" "  Tentativa $i/$MAX_TENTATIVAS..."
        systemctl restart "$svc" 2>/dev/null || true
        if aguardar_ativo "$svc" 4; then
            log "$svc" "  ✓ FASE 1 OK (tentativa $i)"
            return 0
        fi
        log "$svc" "  ✗ Tentativa $i falhou"
        sleep 5
    done
    return 1
}

# ── FASE 2 — SIGKILL directo + start limpo (método de força bruta) ───────────
# Contorna processos zombie ou bloqueados que o SIGTERM não mata.
# Mata o processo Python directamente pelo path do script, depois deixa
# o systemd iniciar uma instância nova.
fase2() {
    local svc="$1"
    local script="${SCRIPT_MAP[$svc]:-}"
    log "$svc" "FASE 2 — pkill -9 + systemctl start (força bruta)"
    for i in 1 2 3; do
        log "$svc" "  Tentativa $i/$MAX_TENTATIVAS..."
        systemctl stop "$svc" 2>/dev/null || true
        sleep 2
        [ -n "$script" ] && pkill -9 -f "$script" 2>/dev/null || true
        sleep 2
        systemctl start "$svc" 2>/dev/null || true
        if aguardar_ativo "$svc" 5; then
            log "$svc" "  ✓ FASE 2 OK (tentativa $i)"
            return 0
        fi
        log "$svc" "  ✗ Tentativa $i falhou"
        sleep 8
    done
    return 1
}

# ── FASE 3 — reset-failed + flush de porta + fork de emergência ─────────────
# Nuclear: limpa o estado de falha do systemd, liberta a porta TCP se ocupada,
# e se o systemd ainda falhar lança o processo Python directamente como
# processo independente (bypassa o systemd como último recurso).
fase3() {
    local svc="$1"
    local script="${SCRIPT_MAP[$svc]:-}"
    local porta="${PORT_MAP[$svc]:-}"
    log "$svc" "FASE 3 — reset-failed + flush porta + fork emergência"
    for i in 1 2 3; do
        log "$svc" "  Tentativa $i/$MAX_TENTATIVAS..."

        # Limpar estado de falha acumulado no systemd
        systemctl stop "$svc" 2>/dev/null || true
        systemctl reset-failed "$svc" 2>/dev/null || true
        sleep 2

        # Matar qualquer processo residual pelo script
        [ -n "$script" ] && pkill -9 -f "$script" 2>/dev/null || true

        # Libertar porta TCP se ainda ocupada por outro processo
        if [ -n "$porta" ] && command -v fuser >/dev/null 2>&1; then
            fuser -k "${porta}/tcp" 2>/dev/null || true
            sleep 1
        fi

        # Tentativa via systemd com estado limpo
        systemctl start "$svc" 2>/dev/null || true
        if aguardar_ativo "$svc" 6; then
            log "$svc" "  ✓ FASE 3 OK via systemd (tentativa $i)"
            return 0
        fi

        # Último recurso: fork directo como processo independente
        if [ -n "$script" ] && [ -f "$script" ]; then
            log "$svc" "  systemd falhou → fork directo: python3 $script"
            nohup /usr/bin/python3 -X utf8 "$script" \
                >> "${LOG_DIR}/${svc}_emergency.log" 2>&1 &
            sleep 5
            # Verificar se o processo está efectivamente a correr
            if pgrep -f "$script" >/dev/null 2>&1; then
                log "$svc" "  ✓ FASE 3 OK via fork directo (tentativa $i)"
                # Re-registar no systemd (best-effort)
                systemctl start "$svc" 2>/dev/null || true
                return 0
            fi
        fi

        log "$svc" "  ✗ Tentativa $i falhou"
        sleep 10
    done
    return 1
}

# ── Função principal para um único serviço ───────────────────────────────────
reiniciar() {
    local svc="$1"
    local log_file="${LOG_DIR}/restart_${svc}.log"

    echo "" >> "$log_file"
    log "$svc" "════ INÍCIO SEQUÊNCIA DE REINÍCIO ════"

    if fase1 "$svc"; then
        log "$svc" "════ CONCLUÍDO (FASE 1) ════"
        return 0
    fi
    log "$svc" "FASE 1 esgotada (3/3 tentativas) → FASE 2"

    if fase2 "$svc"; then
        log "$svc" "════ CONCLUÍDO (FASE 2) ════"
        return 0
    fi
    log "$svc" "FASE 2 esgotada (3/3 tentativas) → FASE 3"

    if fase3 "$svc"; then
        log "$svc" "════ CONCLUÍDO (FASE 3) ════"
        return 0
    fi

    log "$svc" "════ TODAS AS FASES FALHARAM — SERVIÇO OFFLINE ════"
    return 1
}

# ── Entry point ──────────────────────────────────────────────────────────────
if [ $# -eq 0 ]; then
    # Sem argumento: reinicia todos os serviços PLEGMA
    FALHAS=0
    for s in "${ALL_SERVICES[@]}"; do
        reiniciar "$s" || FALHAS=$((FALHAS + 1))
    done
    exit $FALHAS
else
    reiniciar "$1"
fi
