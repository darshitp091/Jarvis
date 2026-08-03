# JARVIS Setup Guide

**Written for complete beginners.** No programming knowledge needed. Follow the
steps in order and do not skip any. It takes about 45 minutes, most of which is
just waiting for downloads.

If you get stuck, jump to [Common Errors](#common-errors) at the bottom — it
lists every error people actually hit and the exact fix.

> **Golden rule:** whenever anything breaks, run this command and it will tell
> you what is wrong:
> ```
> python doctor.py
> ```

---

## What you need first

| Requirement | Details |
|---|---|
| Windows 10 or 11 | JARVIS controls Windows settings, so it does not run on Mac/Linux |
| ~15 GB free space | The AI models are large |
| Microphone | Any mic, including a laptop's built-in one |
| Internet | Needed for setup. Afterwards most things run offline |
| 8 GB RAM minimum | 16 GB recommended |

---

## Step 1 — Install Python (5 min)

JARVIS is written in Python, so your computer needs it.

1. Go to **https://www.python.org/downloads/release/python-31210/**
2. Scroll down and click **Windows installer (64-bit)**
3. Open the downloaded file
4. **IMPORTANT:** on the first screen, tick the box that says
   **"Add python.exe to PATH"** at the bottom. If you miss this, nothing else
   will work.
5. Click **Install Now** and wait

**Use Python 3.12.** Do not use 3.13 — two required components have no 3.13
version yet and the install will fail with confusing errors.

**Check it worked.** Press `Windows key`, type `powershell`, press Enter, then
type:

```powershell
python --version
```

You should see `Python 3.12.10`. If you see an error, Python is not on your
PATH — reinstall and make sure you tick that box.

---

## Step 2 — Install FFmpeg (3 min)

This handles audio. **Without it JARVIS cannot speak at all.**

In the same PowerShell window:

```powershell
winget install Gyan.FFmpeg
```

Close PowerShell and open a new one, then check:

```powershell
ffmpeg -version
```

If `winget` is not recognised, download from
https://www.gyan.dev/ffmpeg/builds/ (get `ffmpeg-release-essentials.zip`),
unzip to `C:\ffmpeg`, then see
[FFmpeg not found](#ffmpeg-is-not-recognized) below for adding it to PATH.

---

## Step 3 — Install Ollama (5 min)

This runs the AI brain on your own computer, for free.

1. Go to **https://ollama.com/download**
2. Download and install the Windows version
3. After installing, Ollama runs in the background — you will see its icon in
   the system tray (bottom-right of your screen)

**Ollama must be running whenever you use JARVIS.**

---

## Step 4 — Download JARVIS (2 min)

```powershell
cd $HOME\Documents
git clone https://github.com/darshitp091/Jarvis.git
cd Jarvis
```

If `git` is not recognised, install it with `winget install Git.Git`, then
close and reopen PowerShell and try again.

---

## Step 5 — Create the virtual environment (2 min)

This keeps JARVIS's packages separate from the rest of your computer.

```powershell
python -m venv jarvis_env
.\jarvis_env\Scripts\Activate.ps1
```

Your prompt should now start with `(jarvis_env)`. **You need this every time**
you use JARVIS — if you close PowerShell, run the `Activate.ps1` line again.

If you get a red error about "running scripts is disabled", run this once:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

Type `Y` and press Enter, then try activating again.

---

## Step 6 — Install the packages (15 min)

```powershell
pip install -r requirements.txt
```

This downloads about 50 packages. It is slow — leave it alone until it
finishes. Warnings in yellow are normal; only red `ERROR:` lines matter.

**If it fails on `pyaudio`**, see
[pyaudio fails to build](#pyaudio-fails-to-build) below.

---

## Step 7 — Download the AI models (15 min)

```powershell
ollama pull qwen2.5-coder:7b
ollama pull moondream:latest
ollama pull nomic-embed-text:latest
```

That is roughly 6.7 GB total. Run them one at a time and wait for each.

---

## Step 8 — Create your config file (1 min)

**This is the single most common reason JARVIS fails to start.**

```powershell
copy config\settings.yaml.example config\settings.yaml
```

That is all you need to start. The file contains optional API keys for Spotify,
weather and similar — leave them blank and those specific features simply stay
switched off. Everything else works without them.

---

## Step 9 — Check everything (1 min)

```powershell
python doctor.py
```

This checks all 51 packages, external programs, AI models and config, then
tells you exactly what is missing and the command to fix it.

Keep fixing and re-running until you see:

```
Everything looks good. Start JARVIS with:
    python main.py
```

---

## Step 10 — Start JARVIS

```powershell
python main.py
```

A glowing orb appears on screen. Say **"hey jarvis"**, wait for it to turn
blue (that means it is listening), then speak.

Try these first:

- "hey jarvis" → "what time is it"
- "hey jarvis" → "open notepad"
- "hey jarvis" → "what's on my screen"

---

## Common Errors

### ModuleNotFoundError: No module named '...'

The most reported problem. It means a package is missing.

```powershell
.\jarvis_env\Scripts\Activate.ps1
pip install -r requirements.txt
python doctor.py
```

Usually the real cause is a forgotten virtual environment. If your prompt does
not start with `(jarvis_env)`, that is the bug.

### 'python' is not recognized

Python is not on your PATH. Reinstall it and tick
**"Add python.exe to PATH"** on the first screen.

### running scripts is disabled on this system

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

### pyaudio fails to build

pyaudio needs a C++ compiler. Either install
[Microsoft C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)
(tick "Desktop development with C++"), or install a prebuilt version:

```powershell
pip install pipwin
pipwin install pyaudio
```

### FFmpeg is not recognized

Installed but not on PATH. Press `Windows key`, type "environment variables",
open **Edit the system environment variables** → **Environment Variables** →
select **Path** → **Edit** → **New** → add `C:\ffmpeg\bin` → OK.
**Close and reopen PowerShell.**

### JARVIS starts but never speaks

FFmpeg is missing or not on PATH. Run `python doctor.py` to confirm.

### Errors mentioning ollama / connection refused

Ollama is not running. Open the Ollama app from the Start menu and check for
its system-tray icon.

### FileNotFoundError: config/settings.yaml

You skipped Step 8:

```powershell
copy config\settings.yaml.example config\settings.yaml
```

### It cannot hear me

1. Check Windows Settings → System → Sound → Input, and confirm the right
   microphone is selected and the bar moves when you talk
2. Say "hey jarvis" clearly, then **pause** and wait for the orb to turn blue
3. Speak your command only after it turns blue

### Installation fails with C++ compiler errors

You are probably on Python 3.13. Install Python 3.12 instead — several
dependencies have no 3.13 build yet.

---

## Still stuck?

Open an issue at https://github.com/darshitp091/Jarvis/issues and include:

1. The full output of `python doctor.py`
2. The complete error message (copy the red text)
3. Your Windows version and the output of `python --version`

The doctor output alone usually identifies the problem immediately.
