# Points Claude Code at the KVA gateway, for THIS terminal only.
# Use it only when your Claude Pro limit is reached: the KVA budget is shared with the product.
#
# Run from any folder, with the leading dot, so the variables stay in this terminal:
#     . .\scripts\use-kva.ps1
# Then start `claude` in this same terminal (the VS Code side panel does not see these variables)
# and check with /status.
# Back to Claude Pro: close this terminal.
# If PowerShell says "running scripts is disabled", run this once:
#     Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

$envFile = Join-Path (Split-Path $PSScriptRoot -Parent) '.env'
if (-not (Test-Path $envFile)) { Write-Error ".env not found at $envFile"; return }

$line = Get-Content $envFile | Where-Object { $_ -match '^\s*AI_GATEWAY_API_KEY\s*=' } | Select-Object -First 1
$key = if ($line) { ($line -split '=', 2)[1].Trim().Trim('"').Trim("'") } else { '' }
if (-not $key) { Write-Error 'AI_GATEWAY_API_KEY is missing or empty in .env'; return }

$env:ANTHROPIC_BASE_URL   = 'https://ai-gateway.vercel.sh/claude-code'
$env:ANTHROPIC_AUTH_TOKEN = $key
# ANTHROPIC_API_KEY must stay empty: a real Anthropic key here would override the gateway.
Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue
Remove-Variable key, line

Write-Host 'Claude Code -> KVA gateway (this terminal only). Start "claude" and check /status.'
