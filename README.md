# 🎙️ JARVIS: Stark-Level Local Voice & Gesture Assistant

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Local AI: Ollama](https://img.shields.io/badge/Local%20AI-Ollama-red.svg)](https://ollama.com/)
[![TTS: Kokoro ONNX](https://img.shields.io/badge/TTS-Kokoro%20ONNX-green.svg)](https://github.com/hexgrad/kokoro)

JARVIS is a **100% local, privacy-first, Stark-level desktop and mobile assistant**. It operates entirely offline (requiring no paid cloud API keys) using a local LLM/VLM stack, local neural voice synthesis, local speech recognition, and spatial computer vision (hand-gestures & eye-gaze tracking). 

JARVIS is capable of executing complex Windows operations, conducting deep web research, running local data analytics, scanning host network security, and controlling physical Android devices via a custom local USB ADB bridge.

---

## 🚀 The Journey of JARVIS

JARVIS grew from a simple voice-controlled CLI script into a fully integrated spatial-perception OS controller. 

*   **Phase 1: Basic Speech & Router Foundation:** Built standard voice recognition and text-to-speech loops. Implemented semantic routing regexes to map commands (like volume or brightness changes) to local scripts.
*   **Phase 2: Spatial Perception & Gesture Control:** Integrated MediaPipe hand tracking to convert the user's hand into a mouse cursor. Added custom features like **Air Writing** (drawing neon trails on screen) and fist-activated window closures (with self-closure guards to prevent JARVIS from terminating itself).
*   **Phase 3: Stark-Level Desktop Utilities:** Added custom transparent PyQt6 overlays for system tools including an eye-care amber night-light overlay, a pixel-accurate screen ruler, and a click-and-drag snipping tool. Added real-time screen recording (OpenCV) and watermarked screenshotting.
*   **Phase 4: Productivity & Analytics Engines:** Added support for local databases (Todo, KPIs, Contacts) using SQLite, Excel/CSV ingestion, Matplotlib plotting, SMTP/IMAP email dispatcher, and automated Mutual NDA/document generators.
*   **Phase 5: Mobile Control via ADB:** Built a phone integration interface that executes ADB commands over USB. It handles 45 different phone interactions (dialing, messaging, maps navigation, system settings) completely offline, securing user privacy.

---

## 🛠️ Key Capabilities & Features

### 1. 🗣️ Voice, Speech, & Audio
*   **Multilingual STT:** Transcribes **English, Hindi, and Gujarati** commands using a local `Faster-Whisper` model.
*   **Neural Speech Synthesis:** Speaks in a natural, witty British accent utilizing a local **Kokoro ONNX** engine.
*   **Acoustic Interruption:** Automatically stops speaking mid-sentence if you interrupt by talking over it (uses a persistent microphone feedback analyzer thread).
*   **Hinglish / Hindi Song Routing:** Routes phonetic phrases (e.g. *"gane bajado"*) directly to play regional hits on Spotify.
*   **Whisper Mode:** Speech volume scales down to 25% and speed drops to 0.8x for quiet/private interactions.

### 2. 🖐️ High-Fidelity Hand Gesture Control
Activate spatial control using your webcam feed (runs smoothly at ~30 FPS):
*   **Cursor Tracking:** Tracks your index finger with Exponential Moving Average (EMA) smoothing to eliminate hand jitters.
*   **Left Click & Drag:** Pinch Index + Thumb. Holds drag states for text highlighting or window dragging.
*   **Right Click / Double Click:** Pinch Middle + Thumb (Right Click) or Pinky + Thumb (Double Click).
*   **Scrolling:** Extend Index + Middle + Ring fingers and move vertically.
*   **Air Writing Canvas:** Extend Index + Pinky ("Rock-On") to draw neon-green trails on screen.
*   **Window Management:** Holds the window under the cursor (Index + Middle extended) to move it. Close active windows by forming a Closed Fist (held for 1.5s).

### 3. 👁️ Eye-Gaze & Fatigue Monitoring
*   **Proactive Alerts:** Measures eyebrow furrowing and eye-gaze centering via a local camera mesh. If you appear confused or furrow your brow for over 30 seconds, JARVIS prompts: *"Sir, you look a bit puzzled. Would you like me to analyze your active window or screen code?"*
*   **Sentry Mode:** Lock screen automatically if unauthorized face peekers are detected behind you, or if owner presence is lost.

### 4. 📊 Data Ingestion & Analytics
*   **File Parsers:** Directly reads and summarizes Excel (`.xlsx`), CSV, Word (`.docx`), and PDF files from disk.
*   **Local Plotting:** Generates and exports custom trend charts and scatter plots to `config/chart.png` using Matplotlib.
*   **Telemetry KPI Logs:** Tracks custom numerical performance data inside a local SQLite database (`kpis.db`).

### 5. 🌐 Offline Web Research
*   **Fact Checker:** Crawls search results locally, cross-examines sources, and validates facts using the local LLM.
*   **Competitor Diff Tracker:** Monitors changes on specified websites by downloading, stripping, and diffing layouts.
*   **RSS & arXiv Parser:** Aggregates RSS feeds and queries academic papers via the arXiv API.

### 6. 📱 Android ADB Mobile Integration
Control your phone from your PC using an offline USB ADB interface:
*   **Hardware Control:** Toggle flashlight, adjust volume/brightness streams, switch sound profiles (silent/vibrate/normal), and query battery/telemetry stats.
*   **Multimodal VLM Screen/Camera Analysis:** Captures the phone screen or camera shutter, pulls the image, and describes it via the local Moondream model.
*   **Communications:** Resolve contacts fuzzily, compose SMS drafts, and send WhatsApp messages or launch WhatsApp VoIP/Video calls.
*   **Navigation & Maps:** Query nearby stores, display coordinate pins, and launch turn-by-turn navigation intents.

### 7. 🏛️ Polyglot Software Architect & High-Level Engineer
*   **System Blueprints:** Designs production-grade software architectures, database schemas, and OOP class relationships complete with embedded, clean Mermaid.js diagrams.
*   **Optimal Code Generation:** Writes optimal, production-grade solutions and snippets in Rust, Go, C++, Zig, Python, and JavaScript/TypeScript.
*   **DSA & Quality Audits:** Scans code from files or system clipboard to check for memory leaks, concurrency bugs, algorithmic (Big O) complexity, and design pattern violations.

### 8. ⚙️ Mechanics CAD Simulator & 3D Hologram Viewport
*   **3D Geometry Blueprinting:** Mathematically designs coordinates and connections for physical mechanical assemblies:
    *   *Gear Assembly:* Axles, inner hub rims, and 12-teeth gears.
    *   *Double-Wishbone Suspension:* Upper/lower A-arms, shock coilovers, wheel spindles, and rim outlines.
    *   *Rocket Engine Nozzle:* Concentric combustor, throat narrowing, and expansion bell exit rings.
*   **Real-Time Parallax Hologram:** Projects designed meshes to the draggable, floating glassmorphic 3D Hologram viewport. Coordinates skew dynamically in 3D perspective based on face-tracking (webcam) bounding boxes or mouse movement.

### 9. 🔬 Deep Autonomous Research Explorer
*   **Multi-Stage Deep Crawls:** Dynamically generates search queries for general web search and academic literature (arXiv/Semantic Scholar style).
*   **Academic Paper Synthesis:** Crawls and compiles gathered data into publication-grade scientific reports containing Abstract, State of the Art, Mathematical Modeling (with LaTeX math equations), Hypotheses, and APA references.

### 10. 🚨 Emergency Sentinel & Smart Contact Sentry
*   **Semantic & Acoustic Distress Triggers:** Listens for vocal panic RMS spikes (>330.0) or emergency keywords (*accident*, *injured*, *bleeding*, *heart attack*, *unconscious*).
*   **Webcam Visual Verification:** Automatically duck-pauses music, captures a camera frame, and asks the vision model (`moondream:latest`) to verify if there is an actual visible physical hazard, injury, fall, or fire to eliminate false alarms and prevent illegal false dialing.
*   **Fuzzy Priority Contact Dialing:** Once verified, searches Android contacts (Ambulance, Doctor, Mom, Dad, Wife, Family) and dials via ADB bridge (falling back to standard service `108` if no contact is matched).

### 11. 🔄 Voice & Sensor Loop Enhancements
*   **Repetitive Hallucination Filtering:** Added Counter-based word-frequency filter in `core/audio_engine.py` to discard looped Whisper hallucinations (like repeated phrases "play music, play music") when background noise or music is loud.
*   **Punctuation-Free Intent Routing:** Strips punctuation from voice transcriptions before matching regex rules, ensuring reliable app launching and routing.
*   **Sleep-Aware Alert Queuing:** Proactive warnings (port intrusions, network quarantine, ast file watcher auto-patches) are queued silently when JARVIS is asleep and announced immediately upon wake-word trigger, allowing active input.
*   **PyQt Thread-Safety Abstraction:** Signals are connected to slots across different threads for `set_state` on `JarvisOrb`, `on_song_change` on `YouTubeMusicPlayer`, and `show`/`hide`/`set_hologram_object` on `HologramSimWidget` to prevent GUI event dispatcher destruction and device context handle crashes.

---

## 🤖 Local AI Model Stack

JARVIS coordinates multiple specialized models running locally:

| Model Role | Model / Repository | Interface | Purpose |
| :--- | :--- | :---: | :--- |
| **Main Brain** | `yasserrmd/Human-Like-Qwen2.5-1.5B-Instruct` | Ollama | Conversation, reasoning, and personality. |
| **Vision (VLM)** | `moondream:latest` | Ollama | Visual screen descriptions and webcam analysis. |
| **Code Specialist** | `codegemma:2b` | Ollama | Coding assistant, bug checks, and environment setup. |
| **Medical Domain** | `medgemma:latest` | Ollama | Offline medical explanations, symptoms, and fitness queries. |
| **Filler Dialog** | `gemma2:2b` | Ollama | Speaks instant placeholder dialogue while major thinking runs. |
| **Safety Classifier** | `shieldgemma:2b` | Ollama | Input safety checks (can be bypassed in settings to save VRAM). |
| **Embeddings** | `nomic-embed-text:latest` | Ollama | Semantic similarity checks for memory indexes. |
| **Speech-to-Text** | `Faster-Whisper` (base) | Direct Python | Fast speech-to-text with auto-language detection. |
| **Text-to-Speech** | `Kokoro-82M` (Kokoro ONNX) | Direct Python | Speech synthesis in a high-quality British voice. |
| **Sensory Tracking** | `MediaPipe` / `OpenCV` | Direct Python | Hand landmarks, Face Mesh, and face detection. |

### ⚙️ Hardware Optimization & Specialized Models

#### ⚠️ The Problem: VRAM Overload & CPU Spikes
By default, the `config/settings.yaml` file maps all text domains (`code`, `medical`, `safety`, `filler`, `main_brain`) to a single lightweight model: `yasserrmd/Human-Like-Qwen2.5-1.5B-Instruct:latest`. 

If your PC has standard hardware (e.g., lower VRAM or only CPU), running separate specialized models (like `codegemma`, `medgemma`, and `shieldgemma` at the same time) will force Ollama to continuously load and unload models in memory as you chat. This causes:
* **Severe lag (10–30 seconds)** every time JARVIS routes queries to a new domain.
* **100% CPU usage spikes** when models spill over from GPU VRAM to system RAM.

#### 💡 The Solution: Unified vs. Specialized Model Setup

Depending on your computer's specifications, you can choose how to configure `config/settings.yaml`:

* **Option A: Unified Configuration (Recommended for Budget/Average PCs)**
  Keep the default configuration where all text-based keys point to the same model (`yasserrmd/Human-Like-Qwen2.5-1.5B-Instruct`). Since only one model is loaded, it stays cached ("warm") in VRAM. JARVIS will respond instantly and use minimal system resources.
  
* **Option B: Specialized Configuration (For High-End PCs with 12GB+ GPU VRAM)**
  If your PC has a powerful GPU and CPU that can handle multiple models simultaneously, you can unlock specialized expertise. Update your `config/settings.yaml` under the `models` section:
  ```yaml
  models:
    main_brain: yasserrmd/Human-Like-Qwen2.5-1.5B-Instruct:latest
    vision: moondream:latest
    code: codegemma:2b          # <-- Change to specialized coding model
    medical: medgemma:latest     # <-- Change to specialized medical model
    safety: shieldgemma:2b       # <-- Change to specialized safety model
    filler: gemma2:2b            # <-- Change to specialized filler model
    embeddings: nomic-embed-text:latest
  ```
  *Make sure to pull any new models you configure:*
  ```bash
  ollama pull codegemma:2b
  ollama pull medgemma:latest
  ollama pull shieldgemma:2b
  ollama pull gemma2:2b
  ```

---

## ⚙️ Installation & Setup

### Prerequisites
*   Windows 10/11
*   Python 3.10 or 3.11 (Python 3.12 is not recommended due to MediaPipe constraints)
*   [Ollama](https://ollama.com/) (installed and running in background)
*   [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) (Add to system PATH for screen vision)
*   A working webcam and microphone

### Step 1: Clone the Repository
```bash
git clone https://github.com/darshitp091/YourCV.git
cd YourCV
```

### Step 2: Set Up Virtual Environment & Dependencies
```powershell
# Create virtual environment
python -m venv jarvis_env

# Activate virtual environment
.\jarvis_env\Scripts\Activate.ps1

# Install requirements
pip install -r requirements.txt
```

### Step 3: Install & Start Ollama Models
Ensure Ollama is running, then pull the necessary models:
```bash
ollama pull yasserrmd/Human-Like-Qwen2.5-1.5B-Instruct:latest
ollama pull moondream:latest
ollama pull codegemma:2b
ollama pull medgemma:latest
ollama pull nomic-embed-text:latest
ollama pull gemma2:2b
```

### Step 4: Download Kokoro TTS Weights
To run high-quality neural voice synthesis locally:
1. Download the ONNX model file `kokoro-v1.0.onnx` and the voices binary file `voices-v1.0.bin` (e.g. from the [hexgrad/kokoro-onnx](https://github.com/hexgrad/kokoro-onnx) releases).
2. Place both files in the root folder of the project.
```
YourCV/
├── kokoro-v1.0.onnx
├── voices-v1.0.bin
├── main.py
...
```

### Step 5: Android USB ADB Setup (Optional)
If you wish to utilize phone integration features:
1. Enable **Developer Options** and turn on **USB Debugging** on your Android device.
2. (Optional) Turn on **USB Debugging (Security settings)** if you wish to allow simulate touches and screen locks via ADB.
3. Connect the phone to your PC via USB and select "Always allow from this computer" when prompted.
4. Ensure `adb` is installed on your PC and added to your system PATH.

---

## ⚡ How to Run
Once configuration is complete, execute the main orchestrator:
```powershell
python main.py
```
*   Double-click the **Floating Orb UI** to open the HUD System Dashboard.
*   Say *"Hey JARVIS"* to trigger voice commands.
*   Hold up your hand to the webcam to engage mouse gesture tracking. Pinch fingers to click, scroll, and drag. Form a closed fist to close active application windows.

---

## 📄 License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
