# Script de Deploy PLEGMA LANDING - Windows PowerShell
$ErrorActionPreference = "Stop"

$SERVER           = "root@80.78.26.52"
$DEST_PATH        = "/var/www/plegmadag.com/html/"
$APK_DIR          = "/var/www/plegmadag.com/html/download"
$SHIELD_FILES_DIR = "/var/www/plegmadag.com/html/dashboard/files"
$KEY              = "$env:USERPROFILE\.ssh\id_ed25519"

# apkVer com fallback para evitar variavel nula caso nao haja build recente
$apkVer = "0.0.0"

try {

Write-Host "--- Iniciando Deploy para PLEGMA DAG ---" -ForegroundColor Cyan

# ── 0. Copia APK recém-buildado para download\ (se existir build novo) ────────
$apkSrc = "$PSScriptRoot\..\plegma_app\build\app\outputs\flutter-apk\app-release.apk"
if (Test-Path $apkSrc) {
    $pubspec = Get-Content "$PSScriptRoot\..\plegma_app\pubspec.yaml" |
               Where-Object { $_ -match "^version:" }
    $apkVer  = if ($pubspec -match "version:\s*([\d.]+)") { $matches[1] } else { "0.0.0" }
    $apkDest = "$PSScriptRoot\download\plegma-v$apkVer.apk"
    if (-not (Test-Path $apkDest)) {
        Copy-Item $apkSrc $apkDest
        Write-Host "  APK v$apkVer copiado para download\" -ForegroundColor Green
    } else {
        Write-Host "  APK v$apkVer ja existe em download\, sem copia necessaria" -ForegroundColor DarkGray
    }
}

# ── 0b. Limpeza LOCAL: mantém só os 2 APKs mais recentes em download\ ─────────
$localApks = @(Get-ChildItem "$PSScriptRoot\download\*.apk" -ErrorAction SilentlyContinue |
               Sort-Object LastWriteTime -Descending)
if ($localApks.Count -gt 2) {
    $localApks | Select-Object -Skip 2 | ForEach-Object {
        Write-Host "  Removendo local antigo: $($_.Name)" -ForegroundColor DarkGray
        Remove-Item $_.FullName -Force
    }
    $localApks = @(Get-ChildItem "$PSScriptRoot\download\*.apk" -ErrorAction SilentlyContinue |
                   Sort-Object LastWriteTime -Descending)
}

# ── 0e. Minerador EXE: gerencia ZIPs em download\ (mesmas regras do APK) ──────
Write-Host "[0e] Verificando Minerador EXE builds..." -ForegroundColor Yellow
$localMiners = @(Get-ChildItem "$PSScriptRoot\download\plegma-minerador-*.zip" -ErrorAction SilentlyContinue |
                 Sort-Object LastWriteTime -Descending)
if ($localMiners.Count -eq 0) {
    Write-Host "  Nenhum minerador ZIP em download\ (buildar com PyInstaller primeiro)" -ForegroundColor DarkGray
} else {
    Write-Host "  $($localMiners.Count) minerador(es) ZIP encontrado(s)" -ForegroundColor DarkGray
    # Mantém apenas os 2 mais recentes localmente
    if ($localMiners.Count -gt 2) {
        $localMiners | Select-Object -Skip 2 | ForEach-Object {
            Write-Host "  Removendo minerador local antigo: $($_.Name)" -ForegroundColor DarkGray
            Remove-Item $_.FullName -Force
        }
        $localMiners = @(Get-ChildItem "$PSScriptRoot\download\plegma-minerador-*.zip" -ErrorAction SilentlyContinue |
                         Sort-Object LastWriteTime -Descending)
    }
}

# ── 0c. Shield Pack: copia builds de PLEGMA_SHIELD_PACK\ para dashboard\files\ ─
Write-Host "[0c] Verificando Shield Pack builds..." -ForegroundColor Yellow

$shieldPackDir  = "$PSScriptRoot\..\PLEGMA_SHIELD_PACK"
$shieldLocalDir = "$PSScriptRoot\dashboard\files"

if (-not (Test-Path $shieldLocalDir)) {
    New-Item -ItemType Directory -Path $shieldLocalDir | Out-Null
}

# Extensões separadas para evitar duplo wildcard (*.zip e *.tar.gz)
foreach ($pattern in @("plegma-shield-pack-*.zip", "plegma-shield-pack-*.tar.gz")) {
    $found = @(Get-ChildItem "$shieldPackDir\$pattern" -ErrorAction SilentlyContinue |
               Sort-Object LastWriteTime -Descending | Select-Object -First 1)
    foreach ($f in $found) {
        $dest = "$shieldLocalDir\$($f.Name)"
        if (-not (Test-Path $dest)) {
            Copy-Item $f.FullName $dest
            Write-Host "  Shield Pack copiado: $($f.Name)" -ForegroundColor Green
        } else {
            Write-Host "  Shield Pack ja existe: $($f.Name)" -ForegroundColor DarkGray
        }
    }
}

# Limpeza local: mantém só os 2 mais recentes de cada tipo
foreach ($pattern in @("plegma-shield-pack-*.zip", "plegma-shield-pack-*.tar.gz")) {
    $localShields = @(Get-ChildItem "$shieldLocalDir\$pattern" -ErrorAction SilentlyContinue |
                      Sort-Object LastWriteTime -Descending)
    if ($localShields.Count -gt 2) {
        $localShields | Select-Object -Skip 2 | ForEach-Object {
            Write-Host "  Removendo Shield Pack local antigo: $($_.Name)" -ForegroundColor DarkGray
            Remove-Item $_.FullName -Force
        }
    }
}

# ── 0d. Atualiza links APK nos HTMLs com a versao atual ───────────────────────
Write-Host "[0d] Atualizando links de download nos HTMLs para v$apkVer..." -ForegroundColor Yellow

$htmlFiles  = @("$PSScriptRoot\index.html", "$PSScriptRoot\ajuda\index.html")
$apkPattern = '(?i)(plegma-v[\d.]+\.apk)'
$apkNew     = "PLEGMA-v$apkVer.apk"

foreach ($f in $htmlFiles) {
    if (Test-Path $f) {
        $content = Get-Content $f -Raw
        $updated = $content -replace $apkPattern, $apkNew
        if ($content -ne $updated) {
            Set-Content $f $updated -NoNewline
            Write-Host "  Atualizado: $(Split-Path $f -Leaf)" -ForegroundColor Green
        } else {
            Write-Host "  Ja atualizado: $(Split-Path $f -Leaf)" -ForegroundColor DarkGray
        }
    }
}

# ── 1. Envia arquivos da landing — exclui download\ e dashboard\files\ ───────��
# (download = APKs grandes; dashboard\files = Shield Pack ZIPs — enviados separadamente)
Write-Host "[1/5] Enviando arquivos da landing..." -ForegroundColor Yellow

$itens = Get-ChildItem "$PSScriptRoot" -Exclude "download","*.ps1" |
         Where-Object { $_.Name -ne "dashboard" } |
         ForEach-Object { $_.Name }

# Envia dashboard sem a subpasta files\
$itens += "dashboard"
foreach ($item in $itens) {
    if ($item -eq "dashboard") {
        # Envia dashboard excluindo files\ (Shield Packs enviados separadamente)
        $dashItens = Get-ChildItem "$PSScriptRoot\dashboard" -Exclude "files" |
                     ForEach-Object { $_.Name }
        foreach ($di in $dashItens) {
            scp -i $KEY -r "$PSScriptRoot\dashboard\$di" "${SERVER}:${DEST_PATH}dashboard/"
        }
        # Garante que o diretório dashboard/files existe no servidor
        ssh -i $KEY $SERVER "mkdir -p ${DEST_PATH}dashboard/files" 2>$null
    } else {
        scp -i $KEY -r "$PSScriptRoot\$item" "${SERVER}:${DEST_PATH}"
    }
}
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERRO: upload dos arquivos da landing falhou." -ForegroundColor Red
    exit 1
}

# ── 2. APKs: só sobe o que ainda nao existe no servidor ───────────────────────
Write-Host "[2/5] Verificando APKs no servidor..." -ForegroundColor Yellow
foreach ($apk in $localApks) {
    $nome   = $apk.Name
    $existe = (ssh -i $KEY $SERVER "test -f ${APK_DIR}/$nome && echo yes || echo no").Trim()
    if ($existe -eq "yes") {
        Write-Host "  $nome ja esta no servidor, pulando" -ForegroundColor DarkGray
    } else {
        Write-Host "  Subindo $nome ($([math]::Round($apk.Length/1MB, 1)) MB)..." -ForegroundColor Yellow
        scp -i $KEY $apk.FullName "${SERVER}:${APK_DIR}/$nome"
        if ($LASTEXITCODE -ne 0) {
            Write-Host "  ERRO ao subir $nome" -ForegroundColor Red
        } else {
            Write-Host "  $nome enviado com sucesso" -ForegroundColor Green
        }
    }
}

# ── 2b. Minerador ZIP: só sobe o que ainda nao existe no servidor ─────────────
Write-Host "[2b/5] Verificando Minerador EXE no servidor..." -ForegroundColor Yellow
foreach ($miner in $localMiners) {
    $nome   = $miner.Name
    $existe = (ssh -i $KEY $SERVER "test -f ${APK_DIR}/$nome && echo yes || echo no").Trim()
    if ($existe -eq "yes") {
        Write-Host "  $nome ja esta no servidor, pulando" -ForegroundColor DarkGray
    } else {
        Write-Host "  Subindo $nome ($([math]::Round($miner.Length/1MB, 1)) MB)..." -ForegroundColor Yellow
        scp -i $KEY $miner.FullName "${SERVER}:${APK_DIR}/$nome"
        if ($LASTEXITCODE -ne 0) {
            Write-Host "  ERRO ao subir $nome" -ForegroundColor Red
        } else {
            Write-Host "  $nome enviado com sucesso" -ForegroundColor Green
        }
    }
}

# ── 3. Shield Pack: só sobe o que ainda nao existe no servidor ────────────────
Write-Host "[3/5] Verificando Shield Pack no servidor..." -ForegroundColor Yellow
ssh -i $KEY $SERVER "mkdir -p ${SHIELD_FILES_DIR}" 2>$null

$allShieldLocal = @(Get-ChildItem "$shieldLocalDir\plegma-shield-pack-*" -ErrorAction SilentlyContinue |
                    Sort-Object LastWriteTime -Descending)
if ($allShieldLocal.Count -eq 0) {
    Write-Host "  Nenhum Shield Pack local (buildar com build_windows.ps1 primeiro)" -ForegroundColor DarkGray
} else {
    foreach ($sf in $allShieldLocal) {
        $nome   = $sf.Name
        $existe = (ssh -i $KEY $SERVER "test -f ${SHIELD_FILES_DIR}/$nome && echo yes || echo no").Trim()
        if ($existe -eq "yes") {
            Write-Host "  $nome ja esta no servidor, pulando" -ForegroundColor DarkGray
        } else {
            Write-Host "  Subindo $nome ($([math]::Round($sf.Length/1MB, 1)) MB)..." -ForegroundColor Yellow
            scp -i $KEY $sf.FullName "${SERVER}:${SHIELD_FILES_DIR}/$nome"
            if ($LASTEXITCODE -ne 0) {
                Write-Host "  ERRO ao subir $nome" -ForegroundColor Red
            } else {
                Write-Host "  $nome enviado com sucesso" -ForegroundColor Green
            }
        }
    }
}

# ── 4. Envia nginx config atualizado ──────────────────────────────────────────
Write-Host "[4/5] Enviando configuracao nginx..." -ForegroundColor Yellow
scp -i $KEY "$PSScriptRoot\..\\_nginx_api.conf" "${SERVER}:/etc/nginx/sites-available/api.plegmadag.com"

# ── 5. Permissoes + nginx + limpeza remota ─────────────────────────────────────
Write-Host "[5/5] Permissoes, nginx e limpeza remota..." -ForegroundColor Yellow

$remoteScript = @'
chown -R www-data:www-data __DEST__
chmod -R 755 __DEST__

# Limpeza APKs antigos no servidor (mantém 2)
APK_COUNT=$(ls -t __APK_DIR__/PLEGMA-v*.apk __APK_DIR__/plegma-v*.apk 2>/dev/null | wc -l)
if [ "$APK_COUNT" -gt 2 ]; then
    ls -t __APK_DIR__/PLEGMA-v*.apk __APK_DIR__/plegma-v*.apk 2>/dev/null | tail -n +3 | xargs rm -f
    echo "APKs antigos removidos"
else
    echo "APKs no servidor: $APK_COUNT (sem limpeza necessaria)"
fi

# Limpeza Minerador ZIPs antigos no servidor (mantém 2)
MINER_COUNT=$(ls -t __APK_DIR__/plegma-minerador-*.zip 2>/dev/null | wc -l)
if [ "$MINER_COUNT" -gt 2 ]; then
    ls -t __APK_DIR__/plegma-minerador-*.zip 2>/dev/null | tail -n +3 | xargs rm -f
    echo "Minerador ZIPs antigos removidos"
else
    echo "Minerador ZIPs no servidor: $MINER_COUNT (sem limpeza necessaria)"
fi
chmod 644 __APK_DIR__/plegma-minerador-*.zip 2>/dev/null || true

# Limpeza Shield Pack antigos no servidor (mantém 2 por tipo)
if [ -d __SHIELD_FILES_DIR__ ]; then
    for PATTERN in "plegma-shield-pack-*.zip" "plegma-shield-pack-*.tar.gz"; do
        SC=$(ls -t __SHIELD_FILES_DIR__/$PATTERN 2>/dev/null | wc -l)
        if [ "$SC" -gt 2 ]; then
            ls -t __SHIELD_FILES_DIR__/$PATTERN 2>/dev/null | tail -n +3 | xargs rm -f
            echo "Shield Pack antigos removidos: $PATTERN"
        fi
    done
    chmod 644 __SHIELD_FILES_DIR__/plegma-shield-pack-* 2>/dev/null || true
fi

nginx -t && systemctl restart nginx
'@
$remoteScript = $remoteScript.Replace("__DEST__", $DEST_PATH).Replace("__APK_DIR__", $APK_DIR).Replace("__SHIELD_FILES_DIR__", $SHIELD_FILES_DIR).Replace("`r`n", "`n").Replace("`r", "`n")
$remoteScript | ssh -i $KEY $SERVER "bash"

Write-Host ""
Write-Host "--- Deploy Concluido com Sucesso! ---" -ForegroundColor Green
Write-Host "Acesse: https://plegmadag.com" -ForegroundColor Cyan
Write-Host ""

Write-Host "APKs no servidor:" -ForegroundColor Yellow
ssh -i $KEY $SERVER "ls -lh ${APK_DIR}/*.apk 2>/dev/null || echo '  (nenhum)'"

Write-Host "Minerador EXE no servidor:" -ForegroundColor Yellow
ssh -i $KEY $SERVER "ls -lh ${APK_DIR}/plegma-minerador-*.zip 2>/dev/null || echo '  (nenhum)'"

Write-Host "Shield Pack no servidor:" -ForegroundColor Yellow
ssh -i $KEY $SERVER "ls -lh ${SHIELD_FILES_DIR}/plegma-shield-pack-* 2>/dev/null || echo '  (nenhum - buildar com build_windows.ps1 primeiro)'"

Write-Host ""

} catch {
    Write-Host ""
    Write-Host "ERRO: $_" -ForegroundColor Red
    Write-Host $_.ScriptStackTrace -ForegroundColor DarkRed
}

Read-Host "Pressione Enter para fechar"
