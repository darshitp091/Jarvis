# JARVIS one-command installer.
#
#   Right-click this file -> "Run with PowerShell"
#   or in a terminal:  .\install.ps1
#
# Creates the virtual environment, installs every package, downloads the AI
# models, creates your config, then verifies the whole thing. Safe to re-run:
# it skips anything already done.

$ErrorActionPreference = "Continue"

function Say($msg)  { Write-Host ""; Write-Host "==> $msg" -ForegroundColor Cyan }
function Good($msg) { Write-Host "    [OK] $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "    [!] $msg"  -ForegroundColor Yellow }
function Bad($msg)  { Write-Host "    [X] $msg"  -ForegroundColor Red }

Write-Host ""
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "  JARVIS INSTALLER" -ForegroundColor Cyan
Write-Host "  Takes 30-45 min, mostly downloads. Leave it running." -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan

# --- 1. Python ---------------------------------------------------------------
Say "Checking Python"
$py = $null
foreach ($c in @("python", "python3", "py")) {
    try {
        $v = & $c --version 2>&1
        if ($v -match "Python (\d+)\.(\d+)") {
            $maj = [int]$Matches[1]; $min = [int]$Matches[2]
            if ($maj -eq 3 -and $min -ge 10 -and $min -lt 13) { $py = $c; Good "$v"; break }
            if ($maj -eq 3 -and $min -ge 13) { Warn "$v is not supported yet (use 3.12)" }
            if ($maj -eq 3 -and $min -lt 10) { Warn "$v is too old (need 3.10-3.12)" }
        }
    } catch { }
}
if (-not $py) {
    Bad "No suitable Python found."
    Write-Host "    Install Python 3.12 from https://www.python.org/downloads/"
    Write-Host "    IMPORTANT: tick 'Add python.exe to PATH' during install."
    Read-Host "`nPress Enter to exit"
    exit 1
}

# --- 2. Virtual environment --------------------------------------------------
Say "Setting up the virtual environment"
if (Test-Path "jarvis_env\Scripts\python.exe") {
    Good "Already exists, reusing it"
} else {
    & $py -m venv jarvis_env
    if (-not (Test-Path "jarvis_env\Scripts\python.exe")) {
        Bad "Could not create the virtual environment."
        Read-Host "`nPress Enter to exit"
        exit 1
    }
    Good "Created"
}
$vpy = ".\jarvis_env\Scripts\python.exe"

# --- 3. Packages -------------------------------------------------------------
Say "Installing packages (this is the slow part, ~15 min)"
& $vpy -m pip install --upgrade pip --quiet 2>&1 | Out-Null
& $vpy -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Warn "Some packages failed to install."
    Write-Host "    Most often this is pyaudio needing a C++ compiler."
    Write-Host "    Install Microsoft C++ Build Tools, then re-run this script:"
    Write-Host "    https://visualstudio.microsoft.com/visual-cpp-build-tools/"
} else {
    Good "All packages installed"
}

# --- 4. Config ---------------------------------------------------------------
Say "Creating your config file"
if (Test-Path "config\settings.yaml") {
    Good "config\settings.yaml already exists, leaving it alone"
} elseif (Test-Path "config\settings.yaml.example") {
    Copy-Item "config\settings.yaml.example" "config\settings.yaml"
    Good "Created config\settings.yaml from the template"
} else {
    Bad "config\settings.yaml.example is missing - re-download the project"
}

# --- 5. FFmpeg ---------------------------------------------------------------
Say "Checking FFmpeg (needed for JARVIS to speak)"
if (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
    Good "FFmpeg found"
} else {
    Warn "FFmpeg missing - JARVIS will not be able to speak."
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "    Installing it now..."
        winget install --id Gyan.FFmpeg --accept-source-agreements --accept-package-agreements 2>&1 | Out-Null
        Warn "Close and reopen PowerShell afterwards so PATH updates."
    } else {
        Write-Host "    Install manually: https://www.gyan.dev/ffmpeg/builds/"
    }
}

# --- 6. Ollama + models ------------------------------------------------------
Say "Checking Ollama and AI models"
if (Get-Command ollama -ErrorAction SilentlyContinue) {
    Good "Ollama found"
    $have = (ollama list 2>&1 | Out-String)
    foreach ($m in @("qwen2.5-coder:7b", "moondream:latest", "nomic-embed-text:latest")) {
        $base = $m.Split(":")[0]
        if ($have -match [regex]::Escape($base)) {
            Good "$m already downloaded"
        } else {
            Write-Host "    Downloading $m (this takes a few minutes)..."
            ollama pull $m
        }
    }
} else {
    Warn "Ollama not installed - JARVIS cannot think without it."
    Write-Host "    Install from https://ollama.com/download then re-run this script."
}

# --- 7. Verify ---------------------------------------------------------------
Say "Verifying the installation"
& $vpy doctor.py

Write-Host ""
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "  NEXT STEPS" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  If the check above passed, start JARVIS with:"
Write-Host ""
Write-Host "      .\jarvis_env\Scripts\Activate.ps1" -ForegroundColor White
Write-Host "      python main.py" -ForegroundColor White
Write-Host ""
Write-Host "  Then say: 'hey jarvis'"
Write-Host ""
Write-Host "  Anything wrong? Run:  python doctor.py" -ForegroundColor White
Write-Host "  Full guide:           SETUP.md" -ForegroundColor White
Write-Host ""
