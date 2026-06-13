#!/bin/bash
# plegma_watchdog.sh — Verifica serviços PLEGMA e invoca restart_service.sh
# Chamado pelo plegma-watchdog.timer a cada 60 segundos.

RESTART_SCRIPT="/root/PLEGMA_CORE/restart_service.sh"
LOG="/tmp/watchdog.log"
SERVICES=("plegma-core" "plegma-auth" "plegma-wallet" "plegma-shield" "plegma-miner")

log() { echo "[$(date '+%H:%M:%S')] [watchdog] $*" | tee -a "$LOG"; }

for svc in "${SERVICES[@]}"; do
    if ! systemctl is-active "$svc" >/dev/null 2>&1; then
        log "ALERTA: $svc offline — invocando sequência de reinício"
        bash "$RESTART_SCRIPT" "$svc" >> "$LOG" 2>&1
        status=$?
        if [ $status -eq 0 ]; then
            log "OK: $svc recuperado"
        else
            log "CRITICO: $svc não recuperado após 3 fases"
        fi
    fi
done
