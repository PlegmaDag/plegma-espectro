# PLEGMA-ESPECTRO - Setup Script (Windows PowerShell)
# Protocolo Privacy Total
#
# INSTRUCOES:
# 1. Coloque este arquivo e a pasta setup-files/ na raiz do seu projeto
# 2. Abra PowerShell como Administrador
# 3. Execute:
#    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#    .\setup.ps1

$GITHUB_USER = "Plegma-dag"
$REPO_NAME   = "plegma-espectro"
$REPO_DESC   = "Espectro interface - public frontend and protocol specs for the Plegma network"

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  PLEGMA-ESPECTRO - Privacy Total Setup" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "[1/6] Verificando gh CLI..." -ForegroundColor Yellow
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    Write-Host "  Instalando gh CLI via winget..." -ForegroundColor Red
    winget install --id GitHub.cli -e --accept-source-agreements --accept-package-agreements
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
    if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
        Write-Host "  ERRO: Instale manualmente: https://cli.github.com" -ForegroundColor Red
        exit 1
    }
}
Write-Host "  OK" -ForegroundColor Green

Write-Host "[2/6] Verificando autenticacao GitHub..." -ForegroundColor Yellow
gh auth status 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Abrindo browser para login..." -ForegroundColor Yellow
    gh auth login
}
Write-Host "  OK" -ForegroundColor Green

Write-Host "[3/6] Criando repositorio $GITHUB_USER/$REPO_NAME..." -ForegroundColor Yellow
gh repo create $REPO_NAME --public --description $REPO_DESC --clone
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ERRO: Repositorio pode ja existir." -ForegroundColor Red
    exit 1
}
Write-Host "  OK: Repositorio criado e clonado" -ForegroundColor Green
Set-Location $REPO_NAME

Write-Host "[4/6] Copiando arquivos de configuracao..." -ForegroundColor Yellow
Copy-Item "..\setup-files\.gitignore" ".gitignore"
New-Item -ItemType Directory -Force -Path "scripts" | Out-Null
Copy-Item "..\setup-files\scripts\notify_discord.ps1" "scripts\notify_discord.ps1"
Copy-Item "..\setup-files\.env.example" ".env.example"
Write-Host "  OK" -ForegroundColor Green

Write-Host "[5/6] Configurando git hook post-commit..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path ".git\hooks" | Out-Null
"#!/bin/sh`npowershell -ExecutionPolicy Bypass -File scripts/notify_discord.ps1" | Set-Content ".git\hooks\post-commit" -Encoding ASCII
Write-Host "  OK" -ForegroundColor Green

Write-Host "[6/6] Scan de seguranca pre-push..." -ForegroundColor Yellow
$patterns = "dilithium|seed_phrase|private_key|SYS_SYNC|-----BEGIN"
$found = $false
Get-ChildItem -Recurse -Include "*.py","*.js","*.ts","*.dart" -ErrorAction SilentlyContinue |
    Select-String -Pattern $patterns -ErrorAction SilentlyContinue |
    ForEach-Object { Write-Host "  ALERTA: $_" -ForegroundColor Red; $script:found = $true }
if ($found) {
    Write-Host "  PARADO: Corrija os alertas." -ForegroundColor Red; exit 1
}
Write-Host "  OK: Nenhuma credencial detectada" -ForegroundColor Green

Write-Host ""
git status --short
Write-Host ""
$confirm = Read-Host "Confirma o push? (s/N)"
if ($confirm -notmatch "^[Ss]$") { Write-Host "Push cancelado."; exit 0 }

git add .gitignore scripts/ .env.example
git commit -m "chore: initial commit - Privacy Total protocol setup"
git push -u origin main

Write-Host ""
Write-Host "==================================================" -ForegroundColor Green
Write-Host "  Setup concluido!" -ForegroundColor Green
Write-Host "  Repo: https://github.com/$GITHUB_USER/$REPO_NAME" -ForegroundColor Green
Write-Host "  Proximo: crie .env com DISCORD_WEBHOOK_URL" -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Green
