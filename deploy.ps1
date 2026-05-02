# deploy.ps1 — PLEGMA DAG Deploy Unificado v2.0
# =============================================================================
# FLUXO OBRIGATÓRIO (quando há Python):
#   FASE S — Sandbox (80.78.26.52) → health check 100% → confirmação → PRODUÇÃO
#
# Uso:
#   .\deploy.ps1                     # deploy completo: sandbox → produção
#   .\deploy.ps1 -SandboxOnly        # só sandbox (sem produção)
#   .\deploy.ps1 -SkipCore           # só landing (sandbox ignorado automaticamente)
#   .\deploy.ps1 -SkipSandbox        # ⚠ produção directa EMERGÊNCIA
#   .\deploy.ps1 -Force              # sem verificação MD5
#   .\deploy.ps1 -Node EUR           # produção num nó específico
#   .\deploy.ps1 -Rolling            # rolling zero-downtime via Njalla DNS
#
# Nós de produção: EUR 213.199.42.88 | BR 187.127.19.209 | MAL 187.127.108.201 | SIN 82.197.70.189
# Sandbox:         80.78.26.52:22  (plagmadag.com)
# EU-MINER:        80.78.26.52:2222 (standby, deploy com -Node EU-MINER)
# =============================================================================

param(
    [switch]$SkipCore,      # pula envio de Python (sandbox ignorado)
    [switch]$SkipLanding,   # pula landing pages
    [switch]$SkipRestart,   # pula restart dos serviços
    [switch]$SkipSandbox,   # bypass sandbox — APENAS EM EMERGÊNCIA
    [switch]$Force,         # envia sem verificação MD5
    [switch]$SandboxOnly,   # executa só a fase sandbox
    [switch]$Rolling,       # rolling zero-downtime via Njalla DNS
    [switch]$NoConfirm,     # pula confirmação entre sandbox e produção (uso por scripts)
    [string]$Node = ""      # EUR|BR|MAL|SIN|EU-MINER (default: todos)
)

$ErrorActionPreference = "Continue"
$LOG = "$PSScriptRoot\deploy.log"
try { Start-Transcript -Path $LOG -Append -Force | Out-Null } catch {}

# =============================================================================
# CONFIGURAÇÃO GLOBAL
# =============================================================================
# UTF-8 sem BOM — evita ﻿BOM nos pipes para bash via SSH (PS 5.1)
$OutputEncoding = New-Object System.Text.UTF8Encoding $false
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false

$KEY       = "$env:USERPROFILE\.ssh\id_ed25519"
$adminKeyFile = "$PSScriptRoot\admin_key.local"
$ADMIN_KEY = if ($env:PLEGMA_ADMIN_KEY) {
    $env:PLEGMA_ADMIN_KEY
} elseif (Test-Path $adminKeyFile) {
    (Get-Content $adminKeyFile -Raw).Trim()
} else {
    throw "ADMIN_KEY nao encontrada. Defina PLEGMA_ADMIN_KEY ou crie admin_key.local"
}
$SSH_OPTS  = @("-o","ConnectTimeout=15","-o","ServerAliveInterval=10","-o","ServerAliveCountMax=3","-o","StrictHostKeyChecking=no","-o","BatchMode=yes")

# Paths locais
$CORE_LOCAL      = "$PSScriptRoot\PLEGMA_CORE"
$LANDING_DIR     = "$PSScriptRoot\PLEGMA_LANDING"
$SHIELD_PACK_DIR = "$PSScriptRoot\PLEGMA_SHIELD_PACK"

# Paths remotos (produção)
$CORE_REMOTE        = "/root/PLEGMA_CORE"
$WEB_ROOT           = "/var/www/plegmadag.com/html"
$APK_DIR            = "$WEB_ROOT/download"
$SHIELD_FILES_DIR   = "$WEB_ROOT/dashboard/files"

# Sandbox
$SBX_HOST    = "80.78.26.52"
$SBX_PORT    = "22"
$SBX_SRV     = "root@${SBX_HOST}"
$SBX_DOMAIN  = "plagmadag.com"
$SBX_WEBROOT = "/var/www/${SBX_DOMAIN}/html"

# Cluster de produção
$ALL_NODES = @(
    @{ Name="EUR";      Host="213.199.42.88";   Port=22;   Region="EU";     Standby=$false; RecordId="2340241" },
    @{ Name="BR";       Host="187.127.19.209";  Port=22;   Region="BR";     Standby=$false; RecordId="2521435" },
    @{ Name="MAL";      Host="187.127.108.201"; Port=22;   Region="MAL";    Standby=$false; RecordId="2479675" },
    @{ Name="SIN";      Host="82.197.70.189";   Port=22;   Region="SIN";    Standby=$false; RecordId="2479679" },
    @{ Name="EU-MINER"; Host="80.78.26.52";     Port=2222; Region="EU-OLD"; Standby=$true;  RecordId="" }
)

# Filtrar nós alvo
if ($Node -ne "") {
    $NODES = $ALL_NODES | Where-Object { $_.Name -eq $Node.ToUpper() }
    if ($NODES.Count -eq 0) {
        Write-Host "Nó '$Node' não reconhecido. Usar EUR, BR, MAL, SIN ou EU-MINER." -ForegroundColor Red
        exit 1
    }
} else {
    $NODES = $ALL_NODES | Where-Object { -not $_.Standby }
}

$EU_NODE   = $NODES | Where-Object { $_.Name -eq "EUR" }
$EU_SERVER = "root@213.199.42.88"
$EU_PORT   = "22"

# Lista de ficheiros Python CORE
$PY_FILES = @(
    "aerarium.py", "aerarium_swap.py", "app_boot.py", "app_navegacao.py",
    "auth_server.py", "core_api.py", "core_consenso.py", "core_dag.py",
    "core_vm.py", "espectro_web.py", "genesis.py", "genesis_contract.py",
    "gossip.py", "hardware_detector.py", "labs_db.py", "lattice_shield.py",
    "miner_daemon.py", "miner_engine.py", "miner_server.py",
    "monitor_pagamentos.py", "network_phase.py", "pacto_dos_5.py",
    "peers.json", "plegma_db.py", "sentinela.py", "shield_server.py",
    "social_db.py", "tx_verifier.py", "wallet.py", "wallet_server.py",
    "zk_press.py", "restart_service.sh", "plegma_watchdog.sh"
)

# =============================================================================
# FUNÇÕES AUXILIARES
# =============================================================================

function Test-TcpPort($target, $port, $timeout = 8000) {
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        $ar  = $tcp.BeginConnect($target, $port, $null, $null)
        $ok  = $ar.AsyncWaitHandle.WaitOne($timeout)
        try { $tcp.Close() } catch {}
        return $ok
    } catch { return $false }
}

function Get-RemoteHashes($srv, $port, $files, $remoteDir) {
    $fileList   = $files -join ' '
    $hashScript = "for f in $fileList; do h=`$(md5sum $remoteDir/`$f 2>/dev/null | awk '{print `$1}'); echo `"`$f:`${h:-0}`"; done"
    $result = @{}
    (ssh @SSH_OPTS -i $KEY -p $port $srv $hashScript) | ForEach-Object {
        if ($_ -match '^([^:]+):([a-f0-9]{32}|0)$') { $result[$matches[1]] = $matches[2] }
    }
    return $result
}

function Send-Files($srv, $port, $files, $localDir, $remoteDir, $force = $false) {
    $remoteHashes = if (-not $force) {
        Get-RemoteHashes $srv $port $files $remoteDir
    } else { @{} }

    $enviados = 0; $pulados = 0; $erros = 0
    foreach ($f in $files) {
        $localFile = "$localDir\$f"
        if (-not (Test-Path $localFile)) { continue }

        $send = $force
        if (-not $force) {
            $localHash  = (Get-FileHash $localFile -Algorithm MD5).Hash.ToLower()
            $remoteHash = if ($remoteHashes.ContainsKey($f)) { $remoteHashes[$f] } else { "0" }
            $send = ($localHash -ne $remoteHash)
        }

        if ($send) {
            scp @SSH_OPTS -i $KEY -P $port $localFile "${srv}:${remoteDir}/$f"
            if ($LASTEXITCODE -eq 0) { Write-Host "  -> $f" -ForegroundColor Green; $enviados++ }
            else { Write-Host "  ERRO: $f" -ForegroundColor Red; $erros++ }
        } else { $pulados++ }
    }
    return @{ Enviados=$enviados; Pulados=$pulados; Erros=$erros }
}

function Wait-HealthCheck($remoteHost, $port, $sshPort, $maxSeconds = 90) {
    $srv      = "root@${remoteHost}"
    $deadline = (Get-Date).AddSeconds($maxSeconds)
    Write-Host "  [HEALTH] Aguardando $remoteHost responder..." -ForegroundColor Cyan
    while ((Get-Date) -lt $deadline) {
        try {
            $code = (ssh @SSH_OPTS -i $KEY -p $sshPort $srv `
                "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:${port}/api/status --max-time 4 2>/dev/null || echo 000").Trim() -replace '[^0-9]',''
            if ($code -eq "200") {
                Write-Host "  [HEALTH] $remoteHost OK (HTTP 200)" -ForegroundColor Green
                return $true
            }
        } catch {}
        Start-Sleep 5
    }
    Write-Host "  [HEALTH] $remoteHost nao respondeu em ${maxSeconds}s" -ForegroundColor Red
    return $false
}

# Njalla DNS (modo Rolling)
function Invoke-Njalla($method, $params) {
    $body = @{ method=$method; params=$params; jsonrpc="2.0"; id=1 } | ConvertTo-Json -Depth 5
    $resp = Invoke-RestMethod -Uri "https://njal.la/api/1/" -Method POST `
        -Headers @{ Authorization="Njalla $NJALLA_TOKEN"; "Content-Type"="application/json" } `
        -Body $body
    if ($resp.PSObject.Properties['error'] -and $resp.error) {
        throw "Njalla API erro: $($resp.error.message)"
    }
    return $resp.result
}

# =============================================================================
# HEADER
# =============================================================================
$needsSandbox = (-not $SkipCore) -and (-not $SkipSandbox) -and (-not $SandboxOnly -or $SandboxOnly)

Write-Host ""
Write-Host "╔══════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║      PLEGMA DAG — Deploy Unificado v2.0      ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════╝" -ForegroundColor Cyan

if ($SkipSandbox -and -not $SkipCore) {
    Write-Host ""
    Write-Host "  ⚠  MODO EMERGÊNCIA — sandbox ignorado" -ForegroundColor Red
    Write-Host "  ⚠  Produção directa sem validação prévia" -ForegroundColor Red
}
if ($Force)       { Write-Host "  ⚡ FORCE — sem verificação MD5" -ForegroundColor Yellow }
if ($Rolling)     { Write-Host "  ⟳  ROLLING — zero-downtime via Njalla DNS" -ForegroundColor Cyan }
if ($SandboxOnly) { Write-Host "  🔲 SANDBOX ONLY — sem deploy de produção" -ForegroundColor Magenta }

$nodeNames = ($NODES | ForEach-Object { $_.Name }) -join " + "
if (-not $SandboxOnly) {
    Write-Host "  Nós produção: $nodeNames" -ForegroundColor Cyan
}
Write-Host ""

try {

# =============================================================================
# FASE 0 — Preparação local (APK, minerador, shield pack)
# =============================================================================
if (-not $SandboxOnly) {
    Write-Host "[0] Preparação local..." -ForegroundColor Yellow

    # APK
    $apkSrc = "$PSScriptRoot\plegma_app\build\app\outputs\flutter-apk\app-release.apk"
    $apkVer = "0.0.0"
    if (Test-Path $apkSrc) {
        $pubspec = Get-Content "$PSScriptRoot\plegma_app\pubspec.yaml" |
                   Where-Object { $_ -match "^version:" }
        $apkVer  = if ($pubspec -match "version:\s*([\d.]+)") { $matches[1] } else { "0.0.0" }
        $apkDest = "$LANDING_DIR\download\plegma-v$apkVer.apk"
        if (-not (Test-Path $apkDest)) {
            Copy-Item $apkSrc $apkDest
            Write-Host "  APK v$apkVer copiado para LANDING\download\" -ForegroundColor Green
        } else {
            Write-Host "  APK v$apkVer já existe em LANDING\download\" -ForegroundColor DarkGray
        }
    }

    # Reter apenas 2 APKs mais recentes
    $localApks = @(Get-ChildItem "$LANDING_DIR\download\*.apk" -ErrorAction SilentlyContinue |
                   Sort-Object LastWriteTime -Descending)
    if ($localApks.Count -gt 2) {
        $localApks | Select-Object -Skip 2 | ForEach-Object { Remove-Item $_.FullName -Force }
        $localApks = @(Get-ChildItem "$LANDING_DIR\download\*.apk" -ErrorAction SilentlyContinue |
                       Sort-Object LastWriteTime -Descending)
    }

    # Reter apenas 2 mineradores mais recentes
    $localMiners = @(Get-ChildItem "$LANDING_DIR\download\plegma-minerador-*.zip" -ErrorAction SilentlyContinue |
                     Sort-Object LastWriteTime -Descending)
    if ($localMiners.Count -gt 2) {
        $localMiners | Select-Object -Skip 2 | ForEach-Object { Remove-Item $_.FullName -Force }
        $localMiners = @(Get-ChildItem "$LANDING_DIR\download\plegma-minerador-*.zip" -ErrorAction SilentlyContinue |
                         Sort-Object LastWriteTime -Descending)
    }

    # Shield Pack → pasta local dashboard/files
    $shieldLocalDir = "$LANDING_DIR\dashboard\files"
    if (-not (Test-Path $shieldLocalDir)) { New-Item -ItemType Directory -Path $shieldLocalDir | Out-Null }
    foreach ($pat in @("plegma-shield-pack-*.zip","plegma-shield-pack-*.tar.gz")) {
        $found = @(Get-ChildItem "$SHIELD_PACK_DIR\$pat" -ErrorAction SilentlyContinue |
                   Sort-Object LastWriteTime -Descending | Select-Object -First 1)
        foreach ($f in $found) {
            $dest = "$shieldLocalDir\$($f.Name)"
            if (-not (Test-Path $dest)) { Copy-Item $f.FullName $dest }
        }
    }
    foreach ($pat in @("plegma-shield-pack-*.zip","plegma-shield-pack-*.tar.gz")) {
        $ls = @(Get-ChildItem "$shieldLocalDir\$pat" -ErrorAction SilentlyContinue |
                Sort-Object LastWriteTime -Descending)
        if ($ls.Count -gt 2) { $ls | Select-Object -Skip 2 | ForEach-Object { Remove-Item $_.FullName -Force } }
    }

    # Derivar versão APK mais recente e actualizar HTML
    if ($localApks.Count -gt 0) {
        $newestApk = $localApks[0].Name
        if ($newestApk -match '(?i)plegma-v([\d.]+)\.apk') { $apkVer = $matches[1] }
    }
    $apkNew     = "plegma-v$apkVer.apk"
    $apkPattern = '(?i)(plegma-v[\d.]+\.apk)'
    foreach ($f in @("$LANDING_DIR\index.html","$LANDING_DIR\ajuda\index.html")) {
        if (Test-Path $f) {
            $c = Get-Content $f -Raw
            $u = $c -replace $apkPattern, $apkNew
            if ($c -ne $u) { Set-Content $f $u -NoNewline }
        }
    }

    Write-Host "  Preparação local concluída" -ForegroundColor Green
}

# =============================================================================
# FASE S — SANDBOX (obrigatório se Python está incluído e -SkipSandbox não usado)
# =============================================================================
$sandboxPassed = $false

if (-not $SkipCore -and -not $SkipSandbox) {
    Write-Host ""
    Write-Host "╔══════════════════════════════════════════════╗" -ForegroundColor Magenta
    Write-Host "║   FASE SANDBOX — ${SBX_HOST} (${SBX_DOMAIN})   ║" -ForegroundColor Magenta
    Write-Host "╚══════════════════════════════════════════════╝" -ForegroundColor Magenta
    Write-Host ""

    # Verificar conectividade sandbox
    if (-not (Test-TcpPort $SBX_HOST ([int]$SBX_PORT))) {
        Write-Host "  SANDBOX INACESSÍVEL (${SBX_HOST}:${SBX_PORT}) — deploy abortado." -ForegroundColor Red
        Write-Host "  Use -SkipSandbox apenas em emergência comprovada." -ForegroundColor DarkYellow
        throw "DEPLOY_ABORT"
    }

    # S0 — Estrutura sandbox
    Write-Host "[S0] Preparando estrutura sandbox..." -ForegroundColor Yellow
    $prepSbx = @"
:
mkdir -p ${SBX_WEBROOT}/download
mkdir -p ${SBX_WEBROOT}/dashboard/files
chown -R www-data:www-data /var/www/${SBX_DOMAIN} 2>/dev/null || true
chmod -R 755 /var/www/${SBX_DOMAIN}
mkdir -p ${CORE_REMOTE}
echo PREP_SANDBOX_OK
"@
    $prepSbx = $prepSbx.Replace("`r`n", "`n").Replace("`r", "`n")
    $prepSbx | ssh @SSH_OPTS -i $KEY -p $SBX_PORT $SBX_SRV "bash"

    # S1 — Python CORE para sandbox
    Write-Host "[S1] Enviando Python CORE para sandbox..." -ForegroundColor Yellow
    $r = Send-Files $SBX_SRV $SBX_PORT $PY_FILES $CORE_LOCAL $CORE_REMOTE $Force.IsPresent
    Write-Host "  Sandbox CORE: $($r.Enviados) enviado(s), $($r.Pulados) sem alteração, $($r.Erros) erro(s)" -ForegroundColor Cyan

    # S2 — Nginx sandbox
    Write-Host "[S2] Nginx config sandbox..." -ForegroundColor Yellow
    $nginxSbxLocal  = "$PSScriptRoot\_nginx_sandbox.conf"
    $nginxSbxRemote = "/etc/nginx/sites-available/api.${SBX_DOMAIN}"
    if (Test-Path $nginxSbxLocal) {
        $lTs = [int64](Get-Item $nginxSbxLocal).LastWriteTimeUtc.Subtract([datetime]'1970-01-01').TotalSeconds
        $rTs = [int64](ssh @SSH_OPTS -i $KEY -p $SBX_PORT $SBX_SRV "stat -c %Y '$nginxSbxRemote' 2>/dev/null || echo 0")
        if ($lTs -ne $rTs) {
            scp @SSH_OPTS -p -i $KEY -P $SBX_PORT $nginxSbxLocal "${SBX_SRV}:${nginxSbxRemote}"
            Write-Host "  nginx sandbox atualizado" -ForegroundColor Green
        } else {
            Write-Host "  nginx sandbox já atualizado" -ForegroundColor DarkGray
        }
    }

    # S3 — Landing para sandbox
    if (-not $SkipLanding) {
        Write-Host "[S3] Landing pages para sandbox..." -ForegroundColor Yellow
        $landFiles = @(Get-ChildItem $LANDING_DIR -Recurse -File | Where-Object {
            $_.FullName -notlike "*\download\*"        -and
            $_.FullName -notlike "*\dashboard\files\*" -and
            $_.Extension -ne '.ps1'
        })
        $localLH = @{}
        foreach ($lf in $landFiles) {
            $rel = $lf.FullName.Substring($LANDING_DIR.Length + 1).Replace('\','/')
            $localLH[$rel] = (Get-FileHash $lf.FullName -Algorithm MD5).Hash.ToLower()
        }
        $lhs = "cd $SBX_WEBROOT && find . -type f ! -path './download/*' ! -path './dashboard/files/*' 2>/dev/null | while read f; do h=`$(md5sum `"`$f`" 2>/dev/null | awk '{print `$1}'); echo `"`${f#./}:`$h`"; done"
        $remoteLH = @{}
        (ssh @SSH_OPTS -i $KEY -p $SBX_PORT $SBX_SRV $lhs) | ForEach-Object {
            if ($_ -match '^([^:]+):([a-f0-9]{32})$') { $remoteLH[$matches[1]] = $matches[2] }
        }
        $dirs = @($localLH.Keys | ForEach-Object {
            $parts = $_ -split '/'; if ($parts.Count -gt 1) { "$SBX_WEBROOT/$($parts[0..($parts.Count-2)] -join '/')" } else { $SBX_WEBROOT }
        } | Sort-Object -Unique)
        ssh @SSH_OPTS -i $KEY -p $SBX_PORT $SBX_SRV ("mkdir -p " + ($dirs -join ' ')) 2>$null
        $lE = 0; $lP = 0
        foreach ($rel in ($localLH.Keys | Sort-Object)) {
            $lh = $localLH[$rel]
            $rh = if ($remoteLH.ContainsKey($rel)) { $remoteLH[$rel] } else { "0" }
            if ($lh -ne $rh) {
                scp @SSH_OPTS -i $KEY -P $SBX_PORT "$LANDING_DIR\$($rel.Replace('/','\'))" "${SBX_SRV}:${SBX_WEBROOT}/$rel"
                if ($LASTEXITCODE -eq 0) { $lE++ } else { Write-Host "  ERRO: $rel" -ForegroundColor Red }
            } else { $lP++ }
        }
        Write-Host "  Landing sandbox: $lE enviado(s), $lP sem alteração" -ForegroundColor Cyan
    }

    # S4 — Deps + restart + health check sandbox
    Write-Host "[S4] Deps + restart sandbox..." -ForegroundColor Yellow
    $sbxRestart = @"
:
pip3 install blake3 cryptography 'dilithium-py>=0.4.0' psutil -q 2>/dev/null || pip3 install --break-system-packages blake3 cryptography 'dilithium-py>=0.4.0' psutil -q 2>&1 | tail -2
chmod -R 750 ${CORE_REMOTE}
chown -R www-data:www-data ${SBX_WEBROOT} 2>/dev/null || true
chmod -R 755 ${SBX_WEBROOT}
nginx -t && systemctl restart nginx 2>/dev/null && echo "NGINX_SANDBOX_OK"
systemctl restart plegma-core plegma-auth plegma-wallet plegma-miner plegma-shield 2>/dev/null || true
sleep 4
echo "=== SERVIÇOS SANDBOX ==="
for SVC in plegma-core plegma-auth plegma-wallet plegma-miner plegma-shield; do
    STATUS=`$(systemctl is-active `$SVC 2>/dev/null)
    echo "  `$SVC: `$STATUS"
done
echo "=== PORTAS ==="
ss -tlnp | grep -E ':808[0-5]' || echo "  (nenhuma porta 808x activa)"
echo "=== HEALTH CHECK ==="
sleep 2
CODE=`$(curl -o /dev/null -sf -w "%{http_code}" --max-time 5 "http://127.0.0.1:8080/api/status" 2>/dev/null || echo "000")
CODE=`$(echo "`$CODE" | tr -dc '0-9')
echo "  HTTP: `$CODE"
if [ "`$CODE" = "200" ]; then echo "SANDBOX_HEALTH_OK"; else echo "SANDBOX_HEALTH_FAIL"; fi
"@
    $sbxRestart = $sbxRestart.Replace("`r`n", "`n").Replace("`r", "`n")
    $sbxOutput = $sbxRestart | ssh @SSH_OPTS -i $KEY -p $SBX_PORT $SBX_SRV "bash"
    $sbxOutput | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }

    $healthOk = ($sbxOutput -like "*SANDBOX_HEALTH_OK*") -or ($sbxOutput -match "HTTP:\s*200")

    Write-Host ""
    if ($healthOk) {
        Write-Host "  ✅ SANDBOX: API HTTP 200 — validação bem-sucedida" -ForegroundColor Green
        $sandboxPassed = $true
    } else {
        Write-Host "  ❌ SANDBOX: falhou — abortando deploy" -ForegroundColor Red
        Write-Host ""
        Write-Host "  Consulte os logs sandbox:" -ForegroundColor Yellow
        Write-Host "    ssh root@${SBX_HOST} 'tail -40 /tmp/core_vm.log'" -ForegroundColor White
        throw "DEPLOY_ABORT"
    }

    if ($SandboxOnly) {
        Write-Host ""
        Write-Host "╔══════════════════════════════════════════════╗" -ForegroundColor Magenta
        Write-Host "║  SANDBOX ONLY — deploy de produção ignorado  ║" -ForegroundColor Magenta
        Write-Host "╚══════════════════════════════════════════════╝" -ForegroundColor Magenta
        Write-Host ""
        Write-Host "  http://${SBX_HOST}:8080/api/status" -ForegroundColor Cyan
        Write-Host "  https://${SBX_DOMAIN}" -ForegroundColor Cyan
        Write-Host ""
        throw "DEPLOY_DONE"
    }

    Write-Host "  Sandbox validado — avançando para produção ($nodeNames)" -ForegroundColor Green

} elseif ($SkipSandbox -and -not $SkipCore) {
    Write-Host ""
    Write-Host "  ⚠  -SkipSandbox activo — continuando directamente para produção" -ForegroundColor Red
    Write-Host ""
} else {
    # SkipCore = $true → sem Python, sandbox não necessário
    $sandboxPassed = $true
}

# =============================================================================
# FASE 0b — Preparação servidor EU (web root + nginx symlink)
# =============================================================================
if ($EU_NODE -and -not $SandboxOnly) {
    Write-Host "[0b] Preparação servidor EU ($($EU_NODE.Host))..." -ForegroundColor Yellow

    if (Test-TcpPort $EU_NODE.Host $EU_NODE.Port) {
        $prepEU = @'
:
mkdir -p /var/www/plegmadag.com/html/download
mkdir -p /var/www/plegmadag.com/html/dashboard/files
chown -R www-data:www-data /var/www/plegmadag.com 2>/dev/null || true
chmod -R 755 /var/www/plegmadag.com
NGINX_AVAIL="/etc/nginx/sites-available/api.plegmadag.com"
NGINX_ENABLED="/etc/nginx/sites-enabled/api.plegmadag.com"
if [ -f "$NGINX_AVAIL" ] && [ ! -L "$NGINX_ENABLED" ]; then
    ln -sf "$NGINX_AVAIL" "$NGINX_ENABLED"
    echo "NGINX_SYMLINK_CRIADO"
elif [ -L "$NGINX_ENABLED" ]; then
    echo "NGINX_SYMLINK_JA_EXISTE"
else
    echo "NGINX_AVAIL_AUSENTE"
fi
nginx -t 2>&1 | tail -2
echo PREP_EU_OK
'@
        $prepEU = $prepEU.Replace("`r`n", "`n").Replace("`r", "`n")
        $prepEU | ssh @SSH_OPTS -i $KEY -p $EU_PORT $EU_SERVER "bash"
    } else {
        Write-Host "  [EU] INACESSÍVEL (TCP timeout) — FASE 0b ignorada" -ForegroundColor Red
    }
}

# =============================================================================
# FASE 1 — Python CORE (todos os nós de produção)
# =============================================================================
if (-not $SkipCore) {
    Write-Host ""
    Write-Host "[1] Python CORE → produção..." -ForegroundColor Yellow

    foreach ($n in $NODES) {
        $srv = "root@$($n.Host)"
        $p   = $n.Port.ToString()

        Write-Host "[CORE → $($n.Name)] $($n.Host)" -ForegroundColor Yellow

        if (-not (Test-TcpPort $n.Host $n.Port)) {
            Write-Host "  [$($n.Name)] INACESSÍVEL (TCP timeout) — ignorando nó" -ForegroundColor Red
            continue
        }

        ssh @SSH_OPTS -i $KEY -p $p $srv "mkdir -p $CORE_REMOTE"

        $r = Send-Files $srv $p $PY_FILES $CORE_LOCAL $CORE_REMOTE $Force.IsPresent
        Write-Host "  $($n.Name): $($r.Enviados) enviado(s), $($r.Pulados) sem alteração, $($r.Erros) erro(s)" -ForegroundColor Cyan
    }
}

# =============================================================================
# FASE 2 — Nginx config (apenas EU)
# =============================================================================
if ($EU_NODE) {
    Write-Host ""
    Write-Host "[2] Nginx config (EU)..." -ForegroundColor Yellow
    $nginxLocal  = "$PSScriptRoot\_nginx_api.conf"
    $nginxRemote = "/etc/nginx/sites-available/api.plegmadag.com"
    if (Test-Path $nginxLocal) {
        $lTs = [int64](Get-Item $nginxLocal).LastWriteTimeUtc.Subtract([datetime]'1970-01-01').TotalSeconds
        $rTs = [int64](ssh @SSH_OPTS -i $KEY -p $EU_PORT $EU_SERVER "stat -c %Y '$nginxRemote' 2>/dev/null || echo 0")
        if ($lTs -ne $rTs) {
            scp @SSH_OPTS -p -i $KEY -P $EU_PORT $nginxLocal "${EU_SERVER}:${nginxRemote}"
            Write-Host "  nginx config atualizado" -ForegroundColor Green
        } else {
            Write-Host "  nginx config já atualizado" -ForegroundColor DarkGray
        }
    }
}

# =============================================================================
# FASE 3 — Landing pages (apenas EU)
# =============================================================================
if (-not $SkipLanding -and $EU_NODE) {
    Write-Host ""
    Write-Host "[3] Landing pages (EU)..." -ForegroundColor Yellow

    $landFiles = @(Get-ChildItem $LANDING_DIR -Recurse -File | Where-Object {
        $_.FullName -notlike "*\download\*"        -and
        $_.FullName -notlike "*\dashboard\files\*" -and
        $_.Extension -ne '.ps1'
    })

    $localLH = @{}
    foreach ($lf in $landFiles) {
        $rel = $lf.FullName.Substring($LANDING_DIR.Length + 1).Replace('\','/')
        $localLH[$rel] = (Get-FileHash $lf.FullName -Algorithm MD5).Hash.ToLower()
    }

    $lhs = "cd $WEB_ROOT && find . -type f ! -path './download/*' ! -path './dashboard/files/*' 2>/dev/null | while read f; do h=`$(md5sum `"`$f`" 2>/dev/null | awk '{print `$1}'); echo `"`${f#./}:`$h`"; done"
    $remoteLH = @{}
    (ssh @SSH_OPTS -i $KEY -p $EU_PORT $EU_SERVER $lhs) | ForEach-Object {
        if ($_ -match '^([^:]+):([a-f0-9]{32})$') { $remoteLH[$matches[1]] = $matches[2] }
    }

    $dirs = @($localLH.Keys | ForEach-Object {
        $parts = $_ -split '/'
        if ($parts.Count -gt 1) { "$WEB_ROOT/$($parts[0..($parts.Count-2)] -join '/')" } else { $WEB_ROOT }
    } | Sort-Object -Unique)
    $dirs += "${WEB_ROOT}/dashboard/files"
    ssh @SSH_OPTS -i $KEY -p $EU_PORT $EU_SERVER ("mkdir -p " + ($dirs -join ' ')) 2>$null

    $lE = 0; $lP = 0
    foreach ($rel in ($localLH.Keys | Sort-Object)) {
        $lh = $localLH[$rel]
        $rh = if ($remoteLH.ContainsKey($rel)) { $remoteLH[$rel] } else { "0" }
        if ($lh -ne $rh) {
            scp @SSH_OPTS -i $KEY -P $EU_PORT "$LANDING_DIR\$($rel.Replace('/','\'))" "${EU_SERVER}:${WEB_ROOT}/$rel"
            if ($LASTEXITCODE -eq 0) { Write-Host "  -> $rel" -ForegroundColor Green; $lE++ }
            else { Write-Host "  ERRO: $rel" -ForegroundColor Red }
        } else { $lP++ }
    }
    Write-Host "  Landing: $lE enviado(s), $lP sem alteração" -ForegroundColor Cyan
}

# =============================================================================
# FASE 4 — APKs + Minerador (apenas EU)
# =============================================================================
if ($EU_NODE) {
    Write-Host ""
    Write-Host "[4] APKs + Minerador (EU)..." -ForegroundColor Yellow
    foreach ($apk in $localApks) {
        $nome   = $apk.Name
        $existe = (ssh @SSH_OPTS -i $KEY -p $EU_PORT $EU_SERVER "test -f ${APK_DIR}/$nome && echo yes || echo no").Trim()
        if ($existe -ne "yes") {
            scp @SSH_OPTS -i $KEY -P $EU_PORT $apk.FullName "${EU_SERVER}:${APK_DIR}/$nome"
            if ($LASTEXITCODE -eq 0) { Write-Host "  $nome enviado" -ForegroundColor Green }
        } else { Write-Host "  $nome já existe" -ForegroundColor DarkGray }
    }
    foreach ($miner in $localMiners) {
        $nome   = $miner.Name
        $lHash  = (Get-FileHash $miner.FullName -Algorithm MD5).Hash.ToLower()
        $rHash  = (ssh @SSH_OPTS -i $KEY -p $EU_PORT $EU_SERVER "md5sum ${APK_DIR}/$nome 2>/dev/null | awk '{print `$1}'").Trim()
        if ($lHash -ne $rHash) {
            scp @SSH_OPTS -i $KEY -P $EU_PORT $miner.FullName "${EU_SERVER}:${APK_DIR}/$nome"
            if ($LASTEXITCODE -eq 0) { Write-Host "  $nome enviado" -ForegroundColor Green }
        } else { Write-Host "  $nome sem alteração" -ForegroundColor DarkGray }
    }
}

# =============================================================================
# FASE 5 — Shield Pack (apenas EU)
# =============================================================================
if ($EU_NODE) {
    Write-Host ""
    Write-Host "[5] Shield Pack (EU)..." -ForegroundColor Yellow
    ssh @SSH_OPTS -i $KEY -p $EU_PORT $EU_SERVER "mkdir -p ${SHIELD_FILES_DIR}" 2>$null
    $allShield = @(Get-ChildItem "$LANDING_DIR\dashboard\files\plegma-shield-pack-*" -ErrorAction SilentlyContinue |
                   Sort-Object LastWriteTime -Descending)
    foreach ($sf in $allShield) {
        $nome   = $sf.Name
        $existe = (ssh @SSH_OPTS -i $KEY -p $EU_PORT $EU_SERVER "test -f ${SHIELD_FILES_DIR}/$nome && echo yes || echo no").Trim()
        if ($existe -ne "yes") {
            scp @SSH_OPTS -i $KEY -P $EU_PORT $sf.FullName "${EU_SERVER}:${SHIELD_FILES_DIR}/$nome"
            if ($LASTEXITCODE -eq 0) { Write-Host "  $nome enviado" -ForegroundColor Green }
        } else { Write-Host "  $nome já existe" -ForegroundColor DarkGray }
    }
}

# =============================================================================
# FASE 6 — Permissões + deps + systemd + restart (todos os nós)
# =============================================================================
Write-Host ""
Write-Host "[6] Permissões, deps, systemd e restart..." -ForegroundColor Yellow

foreach ($n in $NODES) {
    $srv = "root@$($n.Host)"
    $p   = $n.Port.ToString()
    Write-Host "  [$($n.Name)] $($n.Host)..." -ForegroundColor Yellow

    if (-not (Test-TcpPort $n.Host $n.Port)) {
        Write-Host "  [$($n.Name)] INACESSÍVEL (TCP timeout) — ignorando nó" -ForegroundColor Red
        continue
    }

    # Dependências Python
    if (-not $SkipCore) {
        ssh @SSH_OPTS -i $KEY -p $p $srv "pip3 install blake3 cryptography 'dilithium-py>=0.4.0' psutil -q 2>/dev/null || pip3 install --break-system-packages blake3 cryptography 'dilithium-py>=0.4.0' psutil -q 2>&1 | tail -2"
    }

    # Permissões CORE
    ssh @SSH_OPTS -i $KEY -p $p $srv "chmod -R 750 $CORE_REMOTE"

    # Permissões web + nginx + limpeza APKs (apenas EU)
    if ($n.Name -eq "EUR") {
        $euScript = @"
:
chown -R www-data:www-data $WEB_ROOT
chmod -R 755 $WEB_ROOT
APK_COUNT=`$(ls -t ${APK_DIR}/PLEGMA-v*.apk ${APK_DIR}/plegma-v*.apk 2>/dev/null | wc -l)
if [ "`$APK_COUNT" -gt 2 ]; then
    ls -t ${APK_DIR}/PLEGMA-v*.apk ${APK_DIR}/plegma-v*.apk 2>/dev/null | tail -n +3 | xargs rm -f
fi
MINER_COUNT=`$(ls -t ${APK_DIR}/plegma-minerador-*.zip 2>/dev/null | wc -l)
if [ "`$MINER_COUNT" -gt 2 ]; then
    ls -t ${APK_DIR}/plegma-minerador-*.zip 2>/dev/null | tail -n +3 | xargs rm -f
fi
nginx -t && systemctl restart nginx && echo "NGINX_EU_OK"
"@
        $euScript = $euScript.Replace("`r`n", "`n").Replace("`r", "`n")
        $euScript | ssh @SSH_OPTS -i $KEY -p $p $srv "bash"
    }

    # Instalar/actualizar systemd services
    if (-not $SkipCore) {
        $systemdScript = @'
:
cat > /etc/systemd/system/plegma-core.service << 'SVCEOF'
[Unit]
Description=PLEGMA DAG Core API
After=network.target
Wants=network.target
StartLimitIntervalSec=0
StartLimitBurst=0

[Service]
Type=simple
WorkingDirectory=/root/PLEGMA_CORE
ExecStart=/usr/bin/python3 -X utf8 /root/PLEGMA_CORE/core_api.py
Restart=always
RestartSec=3
StandardOutput=append:/tmp/core_vm.log
StandardError=append:/tmp/core_vm.log
Environment=PYTHONUNBUFFERED=1
Environment=PLEGMA_PORT=8080

[Install]
WantedBy=multi-user.target
SVCEOF

cat > /etc/systemd/system/plegma-auth.service << 'SVCEOF'
[Unit]
Description=PLEGMA DAG Auth Server
After=network.target plegma-core.service
Wants=network.target
StartLimitIntervalSec=0
StartLimitBurst=0

[Service]
Type=simple
WorkingDirectory=/root/PLEGMA_CORE
ExecStart=/usr/bin/python3 -X utf8 /root/PLEGMA_CORE/auth_server.py
Restart=always
RestartSec=3
StandardOutput=append:/tmp/auth_server.log
StandardError=append:/tmp/auth_server.log
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
SVCEOF

cat > /etc/systemd/system/plegma-wallet.service << 'SVCEOF'
[Unit]
Description=PLEGMA DAG Wallet Server
After=network.target plegma-core.service
Wants=network.target
StartLimitIntervalSec=0
StartLimitBurst=0

[Service]
Type=simple
WorkingDirectory=/root/PLEGMA_CORE
ExecStart=/usr/bin/python3 -X utf8 /root/PLEGMA_CORE/wallet_server.py
Restart=always
RestartSec=3
StandardOutput=append:/tmp/wallet_server.log
StandardError=append:/tmp/wallet_server.log
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
SVCEOF

cat > /etc/systemd/system/plegma-shield.service << 'SVCEOF'
[Unit]
Description=PLEGMA DAG Shield Server
After=network.target plegma-core.service
Wants=network.target
StartLimitIntervalSec=0
StartLimitBurst=0

[Service]
Type=simple
WorkingDirectory=/root/PLEGMA_CORE
ExecStart=/usr/bin/python3 -X utf8 /root/PLEGMA_CORE/shield_server.py
Restart=always
RestartSec=3
StandardOutput=append:/tmp/shield_server.log
StandardError=append:/tmp/shield_server.log
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
SVCEOF

cat > /etc/systemd/system/plegma-miner.service << 'SVCEOF'
[Unit]
Description=PLEGMA DAG Miner Daemon
After=network.target plegma-core.service
Wants=network.target
StartLimitIntervalSec=0
StartLimitBurst=0

[Service]
Type=simple
WorkingDirectory=/root/PLEGMA_CORE
ExecStart=/usr/bin/python3 -X utf8 /root/PLEGMA_CORE/miner_daemon.py
Restart=always
RestartSec=3
StandardOutput=append:/tmp/miner_daemon.log
StandardError=append:/tmp/miner_daemon.log
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
SVCEOF

cat > /etc/systemd/system/plegma-sandbox.service << 'SVCEOF'
[Unit]
Description=PLEGMA DAG Core VM — Sandbox
After=network.target

[Service]
Type=simple
WorkingDirectory=/root/PLEGMA_SANDBOX
ExecStart=/usr/bin/python3 -X utf8 /root/PLEGMA_SANDBOX/core_vm.py
Restart=no
StandardOutput=append:/tmp/sandbox_vm.log
StandardError=append:/tmp/sandbox_vm.log
Environment=PYTHONUNBUFFERED=1
Environment=PLEGMA_PORT=8090

[Install]
WantedBy=multi-user.target
SVCEOF

chmod +x /root/PLEGMA_CORE/restart_service.sh /root/PLEGMA_CORE/plegma_watchdog.sh 2>/dev/null || true

cat > /etc/systemd/system/plegma-watchdog.service << 'SVCEOF'
[Unit]
Description=PLEGMA DAG Watchdog
After=network.target

[Service]
Type=oneshot
ExecStart=/bin/bash /root/PLEGMA_CORE/plegma_watchdog.sh
StandardOutput=append:/tmp/watchdog.log
StandardError=append:/tmp/watchdog.log
SVCEOF

cat > /etc/systemd/system/plegma-watchdog.timer << 'SVCEOF'
[Unit]
Description=PLEGMA DAG Watchdog Timer
Requires=plegma-watchdog.service

[Timer]
OnBootSec=60
OnUnitActiveSec=60
AccuracySec=5

[Install]
WantedBy=timers.target
SVCEOF

systemctl daemon-reload
systemctl enable plegma-core plegma-auth plegma-wallet plegma-shield plegma-miner plegma-watchdog.timer 2>/dev/null
systemctl start plegma-watchdog.timer 2>/dev/null || true
echo SYSTEMD_OK
'@
        $systemdScript = $systemdScript.Replace("`r`n", "`n").Replace("`r", "`n")
        $systemdScript | ssh @SSH_OPTS -i $KEY -p $p $srv "bash" | Out-Null
    }

    # Rolling: aguardar outros nós antes de reiniciar este
    if (-not $SkipRestart) {
        $otherNodes = $NODES | Where-Object { $_.Name -ne $n.Name }
        $clusterOk  = $false
        foreach ($other in $otherNodes) {
            if (Test-TcpPort $other.Host 443 4000) { $clusterOk = $true; break }
        }
        if (-not $clusterOk -and $NODES.Count -gt 1) {
            Write-Host "  [$($n.Name)] AVISO: nenhum outro nó acessível — reiniciando mesmo assim" -ForegroundColor DarkYellow
        }

        ssh @SSH_OPTS -i $KEY -p $p $srv "systemctl restart plegma-core plegma-auth plegma-wallet plegma-shield plegma-miner 2>/dev/null || true" | Out-Null

        # Aguardar 10s e validar: serviço active + HTTP 200
        Write-Host "  [$($n.Name)] Aguardando 10s..." -ForegroundColor DarkGray
        Start-Sleep -Seconds 10
        $svcStatus = (ssh @SSH_OPTS -i $KEY -p $p $srv "systemctl is-active plegma-core 2>/dev/null").Trim()
        if ($svcStatus -ne "active") {
            Write-Host "  [$($n.Name)] FALHOU — plegma-core não está active (estado: $svcStatus)" -ForegroundColor Red
            Write-Host "  [$($n.Name)] Deploy abortado. Verificar: ssh root@$($n.Host) 'journalctl -u plegma-core -n 50'" -ForegroundColor Yellow
            throw "DEPLOY_ABORT"
        }
        $nodeHealthOk = Wait-HealthCheck $n.Host 8080 $n.Port 30
        if (-not $nodeHealthOk) {
            Write-Host "  [$($n.Name)] FALHOU health check HTTP 200 — deploy abortado" -ForegroundColor Red
            Write-Host "  [$($n.Name)] Verificar: ssh root@$($n.Host) 'tail -30 /tmp/core_vm.log'" -ForegroundColor Yellow
            throw "DEPLOY_ABORT"
        }

        # Garantir admin_key na DB
        $adminPy = "import plegma_db`nk=plegma_db.carregar_estado('admin_key',None)`nk or plegma_db.salvar_estado('admin_key','$ADMIN_KEY')`nprint('admin_key: ' + ('ja definida' if k else 'definida agora'))"
        $adminPy | ssh @SSH_OPTS -i $KEY -p $p $srv "cd /root/PLEGMA_CORE && python3"
    }

    Write-Host "  [$($n.Name)] OK" -ForegroundColor Green
}

# =============================================================================
# FASE R — Rolling DNS (opcional, apenas com -Rolling)
# =============================================================================
if ($Rolling -and -not $SkipCore) {
    Write-Host ""
    Write-Host "[R] Rolling deploy via Njalla DNS..." -ForegroundColor Cyan

    $NJALLA_TOKEN = $env:NJALLA_TOKEN
    if (-not $NJALLA_TOKEN) {
        $tokenFile = "$PSScriptRoot\njalla_token.local"
        if (Test-Path $tokenFile) { $NJALLA_TOKEN = (Get-Content $tokenFile -Raw).Trim() }
    }
    if (-not $NJALLA_TOKEN) {
        Write-Host "  AVISO: NJALLA_TOKEN não encontrado — modo rolling ignorado" -ForegroundColor Yellow
        Write-Host "  Defina `$env:NJALLA_TOKEN ou crie njalla_token.local" -ForegroundColor DarkGray
    } else {
        $TTL_PROD = 300; $TTL_ROLL = 60
        $DOMAIN   = "plegmadag.com"
        $rollingNodes = $NODES | Where-Object { $_.RecordId -ne "" }

        Write-Host "  [DNS] Baixando TTL → ${TTL_ROLL}s..." -ForegroundColor DarkCyan
        foreach ($n in $rollingNodes) {
            try { Invoke-Njalla "edit-record" @{ domain=$DOMAIN; id=$n.RecordId; ttl=$TTL_ROLL } | Out-Null
                  Write-Host "  [DNS] $($n.Name) TTL → ${TTL_ROLL}s" -ForegroundColor DarkCyan }
            catch { Write-Host "  [DNS] AVISO: $($n.Name) — $_" -ForegroundColor Yellow }
        }
        Write-Host "  [DNS] Aguardando 60s para TTL drenar..." -ForegroundColor DarkGray
        Start-Sleep 60

        Write-Host "  [DNS] Restaurando TTL → ${TTL_PROD}s..." -ForegroundColor DarkCyan
        foreach ($n in $rollingNodes) {
            try { Invoke-Njalla "edit-record" @{ domain=$DOMAIN; id=$n.RecordId; ttl=$TTL_PROD } | Out-Null
                  Write-Host "  [DNS] $($n.Name) TTL → ${TTL_PROD}s" -ForegroundColor Green }
            catch { Write-Host "  [DNS] AVISO: $($n.Name) — $_" -ForegroundColor Yellow }
        }
    }
}

# =============================================================================
# FASE 7 — Status final
# =============================================================================
Write-Host ""
Write-Host "╔══════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║       Deploy Concluído com Sucesso!          ║" -ForegroundColor Green
Write-Host "╚══════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
Write-Host "  Cluster:" -ForegroundColor Cyan
foreach ($n in $NODES) {
    Write-Host "    $($n.Name) ($($n.Region)) → http://$($n.Host):8080/api/status" -ForegroundColor White
}
Write-Host ""
Write-Host "  https://plegmadag.com" -ForegroundColor Cyan
Write-Host "  https://api.plegmadag.com/api/status" -ForegroundColor White
Write-Host ""

} catch {
    if ($_.Exception.Message -notin @("DEPLOY_ABORT","DEPLOY_DONE")) {
        Write-Host ""
        Write-Host "ERRO: $_" -ForegroundColor Red
        Write-Host $_.ScriptStackTrace -ForegroundColor DarkRed
    }
} finally {
    try { Stop-Transcript | Out-Null } catch {}
    Write-Host ""
    Write-Host "Log completo em: $LOG" -ForegroundColor DarkYellow
    Read-Host "Pressione Enter para fechar"
}
