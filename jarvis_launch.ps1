# jarvis_launch.ps1
# ─────────────────────────────────────────────────────────────────────────────
# Run this script to activate the JARVIS virtual environment AND set all
# required environment variables in one step.
#
# Usage:  . .\jarvis_launch.ps1   (dot-source so env vars persist in your shell)
# ─────────────────────────────────────────────────────────────────────────────

# 1. Activate virtual environment
. "$PSScriptRoot\jarvis_env\Scripts\Activate.ps1"

# 2. Set JARVIS environment variables
$env:JARVIS_EMAIL_USER   = 'YOUR_EMAIL_ID'
$env:JARVIS_EMAIL_PASS   = 'YOUR_EMAIL_APP_SECRET'
$env:JARVIS_SMTP_SERVER  = 'SMTP_SERVER_LINK'
$env:JARVIS_SMTP_PORT    = 'SMTP_SERVER_PORT'
$env:JARVIS_IMAP_SERVER  = 'IMAP_SERVER_LINK'

Write-Host ""
Write-Host "  JARVIS environment activated." -ForegroundColor Cyan
Write-Host "  Python: $(python --version)" -ForegroundColor Green
Write-Host "  Run 'python main.py' to start JARVIS." -ForegroundColor Green
Write-Host ""
