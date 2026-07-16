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
$env:JARVIS_EMAIL_USER   = 'darshitp091@gmail.com'
$env:JARVIS_EMAIL_PASS   = 'lnvv tgnr cnia urnu'
$env:JARVIS_SMTP_SERVER  = 'smtp.gmail.com'
$env:JARVIS_SMTP_PORT    = '587'
$env:JARVIS_IMAP_SERVER  = 'imap.gmail.com'

Write-Host ""
Write-Host "  JARVIS environment activated." -ForegroundColor Cyan
Write-Host "  Python: $(python --version)" -ForegroundColor Green
Write-Host "  Run 'python main.py' to start JARVIS." -ForegroundColor Green
Write-Host ""
