"""JARVIS setup checker.

Run this any time something does not work:

    python doctor.py

It checks every dependency, every external program, and your config, then
prints exactly what is missing and the command to fix it. Uses only the
Python standard library, so it works even when nothing else is installed.
"""

import importlib.util
import os
import shutil
import subprocess
import sys

# (import name, pip name, what it is for, required?)
PACKAGES = [
    # core
    ("yaml",                  "pyyaml",                "reading your config file",        True),
    ("loguru",                "loguru",                "writing logs",                    True),
    ("numpy",                 "numpy",                 "audio maths",                     True),
    ("scipy",                 "scipy",                 "audio filtering",                 True),
    ("requests",              "requests",              "talking to web APIs",             True),
    ("psutil",                "psutil",                "reading system stats",            True),
    ("dateutil",              "python-dateutil",       "understanding dates you say",     True),
    # hearing
    ("faster_whisper",        "faster-whisper",        "turning your speech into text",   True),
    ("openwakeword",          "openwakeword",          "hearing 'hey jarvis'",            True),
    ("pyaudio",               "pyaudio",               "using your microphone",           True),
    ("sounddevice",           "sounddevice",           "playing and recording audio",     True),
    ("soundfile",             "soundfile",             "reading audio files",             True),
    ("silero_vad",            "silero-vad",            "detecting when you stop talking", True),
    # speaking
    ("edge_tts",              "edge-tts",              "the default JARVIS voice",        True),
    ("pedalboard",            "pedalboard",            "voice audio effects",             True),
    # brain
    ("ollama",                "ollama",                "running local AI models",         True),
    ("openai",                "openai",                "OpenRouter / OpenAI APIs",        True),
    ("sentence_transformers", "sentence-transformers", "long-term memory",                True),
    ("lancedb",               "lancedb",               "the memory database",             True),
    # screen / window control
    ("PyQt6",                 "PyQt6",                 "the floating orb window",         True),
    ("pyautogui",             "pyautogui",             "clicking and typing for you",      True),
    ("pywinauto",             "pywinauto",             "controlling Windows apps",        True),
    ("win32api",              "pywin32",               "Windows settings control",        True),
    ("pygetwindow",           "pygetwindow",           "knowing which window is open",    True),
    ("pyperclip",             "pyperclip",             "copy and paste",                  True),
    ("winsdk",                "winsdk",                "Windows notifications",           True),
    ("GPUtil",                "GPUtil",                "graphics card monitoring",        True),
    # reading the screen
    ("pytesseract",           "pytesseract",           "reading text on your screen",     True),
    ("PIL",                   "pillow",                "screenshots and images",          True),
    # web
    ("crawl4ai",              "crawl4ai",              "deep web research",               True),
    ("duckduckgo_search",     "duckduckgo-search",     "web search",                      True),
    ("bs4",                   "beautifulsoup4",        "reading web pages",               True),
    ("feedparser",            "feedparser",            "news headlines",                  True),
    ("yt_dlp",                "yt-dlp",                "playing YouTube",                 True),
    # documents
    ("pptx",                  "python-pptx",           "making presentations",            True),
    ("docx",                  "python-docx",           "making Word documents",           True),
    ("pypdf",                 "pypdf",                 "reading PDFs",                    True),
    ("matplotlib",            "matplotlib",            "charts and graphs",               True),
    ("networkx",              "networkx",              "diagrams in presentations",       True),
    # camera
    ("cv2",                   "opencv-python",         "your camera",                     True),
    ("mediapipe",             "mediapipe",             "hand gestures and face tracking", True),
    # data / finance
    ("pandas",                "pandas",                "data analysis",                   True),
    ("yfinance",              "yfinance",              "stock market data",               True),
    # services
    ("spotipy",               "spotipy",               "Spotify control",                 True),
    ("keyring",               "keyring",               "storing passwords safely",        True),
    ("sarvamai",              "sarvamai",              "Sarvam Indian-language voice",    True),
    # optional extras
    ("PyPDF2",                "PyPDF2",                "splitting/merging PDFs",          False),
    ("rembg",                 "rembg",                 "removing image backgrounds",      False),
    ("nmap",                  "python-nmap",           "network port scanning",           False),
    ("torch",                 "torch",                 "local speech models (~2.5 GB)",   False),
    # growwapi is intentionally optional: it needs protobuf>=5.29 while
    # mediapipe (gestures) needs protobuf<5, so they cannot coexist.
    ("growwapi",              "growwapi",              "Groww market data (yfinance is used instead)", False),
]

# (command, human name, what breaks without it, required?)
BINARIES = [
    ("ffmpeg",  "FFmpeg",    "JARVIS cannot speak at all",              True),
    ("ollama",  "Ollama",    "JARVIS cannot think or hold conversation", True),
    ("node",    "Node.js",   "presentation export via Marp",            False),
    ("adb",     "ADB",       "Android phone control",                   False),
    ("nmap",    "Nmap",      "network scanning",                        False),
]

BAR = "=" * 68


def head(title):
    print("\n" + BAR)
    print(title)
    print(BAR)


def check_python():
    head("1. Python version")
    v = sys.version_info
    print(f"   You have Python {v.major}.{v.minor}.{v.micro}")
    if v < (3, 10):
        print("   [X] TOO OLD. JARVIS needs Python 3.10 or newer.")
        return ["Install Python 3.11 from https://www.python.org/downloads/\n"
                "       During install, TICK the box 'Add Python to PATH'."]
    if v >= (3, 13):
        print("   [!] Python 3.13+ is not supported yet.")
        print("       mediapipe and torch have no 3.13 wheels, so install fails")
        print("       with confusing C++ compiler errors.")
        return ["Install Python 3.12 instead: https://www.python.org/downloads/"]
    print("   [OK] Version is fine.")
    return []


def check_venv():
    head("2. Virtual environment")
    active = sys.prefix != sys.base_prefix
    if active:
        print(f"   [OK] Active: {sys.prefix}")
        return []
    print("   [!] You are NOT inside the virtual environment.")
    print("       Packages may install to the wrong place.")
    return ["Activate it first, then run this again:\n"
            "       .\\jarvis_env\\Scripts\\Activate.ps1"]


def check_packages():
    head("3. Python packages")
    missing_req, missing_opt = [], []
    for mod, pkg, why, required in PACKAGES:
        try:
            ok = importlib.util.find_spec(mod) is not None
        except Exception:
            ok = False
        if not ok:
            (missing_req if required else missing_opt).append((pkg, why))

    total = len(PACKAGES)
    print(f"   Checked {total} packages.")

    if not missing_req:
        print("   [OK] Every required package is installed.")
    else:
        print(f"   [X] {len(missing_req)} REQUIRED package(s) missing:")
        for pkg, why in missing_req:
            print(f"        - {pkg:24s} (needed for {why})")

    if missing_opt:
        print(f"   [i] {len(missing_opt)} optional package(s) not installed:")
        for pkg, why in missing_opt:
            print(f"        - {pkg:24s} ({why} will not work)")

    fixes = []
    if missing_req:
        fixes.append("Install the missing packages:\n"
                     "       pip install -r requirements.txt\n"
                     "\n"
                     "       If that fails on pyaudio, install Microsoft C++ Build Tools:\n"
                     "       https://visualstudio.microsoft.com/visual-cpp-build-tools/\n"
                     "       Tick 'Desktop development with C++', then retry.")
    return fixes


def check_binaries():
    head("4. External programs")
    fixes = []
    hints = {
        "ffmpeg": "winget install Gyan.FFmpeg\n"
                  "       (or download from https://www.gyan.dev/ffmpeg/builds/ and\n"
                  "        add its bin folder to PATH)",
        "ollama": "Download and install from https://ollama.com/download",
        "node":   "winget install OpenJS.NodeJS",
        "adb":    "Install Android Platform Tools:\n"
                  "       https://developer.android.com/studio/releases/platform-tools",
        "nmap":   "Download from https://nmap.org/download.html",
    }
    for cmd, name, breaks, required in BINARIES:
        found = shutil.which(cmd) is not None
        if cmd == "ffmpeg" and not found:
            # ffmpeg is sometimes installed but not on PATH
            found = os.path.exists(r"C:\ffmpeg\bin\ffmpeg.exe")
        if found:
            print(f"   [OK] {name}")
        elif required:
            print(f"   [X]  {name} MISSING -> {breaks}")
            fixes.append(f"Install {name}:\n       {hints[cmd]}")
        else:
            print(f"   [i]  {name} not found ({breaks} will not work)")

    tess = shutil.which("tesseract") or os.path.exists(
        r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    if tess:
        print("   [OK] Tesseract OCR")
    else:
        print("   [i]  Tesseract OCR not found (reading screen text will be poor)")
    return fixes


def _models_from_config():
    """Read models.* from settings.yaml without needing pyyaml."""
    path = os.path.join("config", "settings.yaml")
    if not os.path.exists(path):
        return []
    wanted, in_models = [], False
    try:
        for line in open(path, encoding="utf-8"):
            raw = line.rstrip("\n")
            if raw.startswith("models:"):
                in_models = True
                continue
            if in_models:
                if raw and not raw[0].isspace():
                    break
                if ":" in raw:
                    val = raw.split(":", 1)[1].strip().strip('"').strip("'")
                    if val and val not in wanted:
                        wanted.append(val)
    except Exception:
        return []
    return wanted


def check_models():
    head("5. AI models (Ollama)")
    if shutil.which("ollama") is None:
        print("   [X] Ollama is not installed, so no models can be checked.")
        return []
    try:
        out = subprocess.run(["ollama", "list"], capture_output=True,
                             text=True, timeout=30).stdout
    except Exception as e:
        print(f"   [!] Could not run 'ollama list': {e}")
        print("       Is the Ollama app running?")
        return ["Start the Ollama application, then run this again."]

    installed = [l.split()[0] for l in out.strip().splitlines()[1:] if l.strip()]
    if not installed:
        print("   [X] No models downloaded yet.")
    else:
        print(f"   Installed: {', '.join(installed)}")

    wanted = _models_from_config()
    if not wanted:
        print("   [i] Could not read model names from config/settings.yaml.")
        return []

    missing = []
    for m in wanted:
        base = m.split(":")[0]
        if any(i == m or i.split(":")[0] == base for i in installed):
            print(f"   [OK] {m}")
        else:
            print(f"   [X]  {m} is missing")
            missing.append(m)

    if missing:
        cmds = "\n       ".join(f"ollama pull {m}" for m in missing)
        return [f"Download the missing model(s):\n       {cmds}"]
    return []


def check_config():
    head("6. Config files")
    fixes = []
    real = os.path.join("config", "settings.yaml")
    example = os.path.join("config", "settings.yaml.example")

    if os.path.exists(real):
        print("   [OK] config/settings.yaml exists")
    elif os.path.exists(example):
        print("   [X] config/settings.yaml is MISSING.")
        print("       This is the #1 cause of startup crashes.")
        fixes.append("Create your config from the template:\n"
                     "       copy config\\settings.yaml.example config\\settings.yaml")
    else:
        print("   [X] Both settings.yaml and settings.yaml.example are missing.")
        fixes.append("Re-download the project — config/settings.yaml.example is missing.")

    if os.path.exists(os.path.join("config", "prompts.yaml")):
        print("   [OK] config/prompts.yaml exists")
    else:
        print("   [X] config/prompts.yaml is missing (JARVIS loses its personality)")
        fixes.append("Re-download the project — config/prompts.yaml is missing.")
    return fixes


def main():
    print(BAR)
    print("  JARVIS SETUP CHECKER")
    print("  Finds what is missing and tells you how to fix it.")
    print(BAR)

    fixes = []
    fixes += check_python()
    fixes += check_venv()
    fixes += check_packages()
    fixes += check_binaries()
    fixes += check_models()
    fixes += check_config()

    head("RESULT")
    if not fixes:
        print("   Everything looks good. Start JARVIS with:\n")
        print("       python main.py\n")
        print("   Then say: \"hey jarvis\"")
        return 0

    print(f"   Found {len(fixes)} thing(s) to fix. Do them in order:\n")
    for i, fix in enumerate(fixes, 1):
        print(f"   {i}. {fix}\n")
    print("   Then run this checker again:\n")
    print("       python doctor.py")
    return 1


if __name__ == "__main__":
    sys.exit(main())
