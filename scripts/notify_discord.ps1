# notify_discord.ps1 - Notificacao de commit para Discord
# Plegma-Espectro | Protocolo Privacy Total
# Chamado automaticamente pelo git post-commit hook
# NUNCA hardcode a URL do webhook neste arquivo

if (Test-Path ".env") {
    Get-Content ".env" | ForEach-Object {
        if ($_ -match "^\s*([^#][^=]+)=(.+)$") {
            [System.Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), "Process")
        }
    }
}

$webhookUrl = $env:DISCORD_WEBHOOK_URL
if (-not $webhookUrl) {
    Write-Host "[notify_discord] DISCORD_WEBHOOK_URL nao definida - pulando"
    exit 0
}

$repo      = git remote get-url origin 2>$null
$branch    = git rev-parse --abbrev-ref HEAD 2>$null
$commitMsg = git log -1 --pretty=%s 2>$null
$commitSha = git log -1 --pretty=%h 2>$null
$timestamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
$color     = if ($branch -eq "main") { 3066993 } else { 3447003 }

$payload = @{
    embeds = @(@{
        title       = "Commit - $branch"
        description = "$commitSha $commitMsg"
        color       = $color
        fields      = @(
            @{ name = "Branch";    value = "$branch";    inline = $true },
            @{ name = "Repo";      value = "$repo";      inline = $true },
            @{ name = "Timestamp"; value = "$timestamp"; inline = $false }
        )
        footer = @{ text = "Plegma-Espectro | Privacy Total" }
    })
} | ConvertTo-Json -Depth 10

try {
    Invoke-RestMethod -Uri $webhookUrl -Method Post -ContentType "application/json" -Body $payload | Out-Null
    Write-Host "[notify_discord] OK: Notificacao enviada"
} catch {
    Write-Host "[notify_discord] ERRO: $_"
}
