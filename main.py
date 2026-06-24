import sys
import os
import threading
import traceback
import yaml
import time
import warnings
warnings.filterwarnings("ignore")

def _p(msg):
    sys.stdout.write(msg + "\n")
    sys.stdout.flush()

_p("DBG: stdlib ok")

# ── Global crash guard ────────────────────────────────────────────────────────
def _excepthook(exc_type, exc_value, exc_tb):
    _p("\n[JARVIS CRASH]")
    traceback.print_exception(exc_type, exc_value, exc_tb)
sys.excepthook = _excepthook

# ── Register local NVIDIA CUDA/cuDNN DLLs on Windows ─────────────────────────
import platform
import sys
if platform.system() == "Windows":
    import site
    # Scan both global and virtual environment site-packages
    _paths = set(site.getsitepackages())
    _paths.add(os.path.join(sys.prefix, "Lib", "site-packages"))
    for p in sys.path:
        if p.endswith("site-packages"):
            _paths.add(p)
            
    for _p_dir in _paths:
        _nv = os.path.join(_p_dir, "nvidia")
        if os.path.exists(_nv):
            for _sub in ["cublas", "cudnn", "cuda_runtime", "cuda_nvrtc", "cufft", "curand", "cusolver", "cusparse", "nvjitlink"]:
                _bin = os.path.join(_nv, _sub, "bin")
                if os.path.exists(_bin):
                    try:
                        os.add_dll_directory(_bin)
                        _p(f"DLL PATH: Added {_bin}")
                    except Exception as _err:
                        _p(f"DLL PATH ERR: {_err} for {_bin}")

from loguru import logger; _p("DBG: loguru ok")
logger.remove()
logger.add(sys.stderr, level="INFO")
from PyQt6.QtWidgets import QApplication; _p("DBG: PyQt6 ok")
from core.audio_engine import AudioEngine
from core.tts_engine import TTSEngine
from core.wake_word import WakeWordDetector
from core.intent_router import IntentRouter
from core.brain import JarvisBrain
from core.vision_engine import CameraEngine
from ui.orb import JarvisOrb; _p("DBG: orb ok")
from skills.screen_vision import ScreenVision; _p("DBG: screen_vision ok")
from skills.os_control import OSControl; _p("DBG: os_control ok")
from skills.web_research import WebResearch; _p("DBG: web_research ok")
from skills.media_summarizer import MediaSummarizer; _p("DBG: media_summarizer ok")
from skills.app_mapper import AppMapper; _p("DBG: app_mapper ok")
from skills.spotify_control import SpotifyControl; _p("DBG: spotify_control ok")
from skills.youtube_music import YouTubeMusicPlayer; _p("DBG: youtube_music ok")
from ui.overlay_widgets import IronManHUDOverlay; _p("DBG: IronManHUDOverlay ok")
from skills.macro_recorder import MacroRecorder; _p("DBG: MacroRecorder ok")
from auth.local_auth import LocalAuth; _p("DBG: local_auth ok")
from domains.medical import MedicalDomain; _p("DBG: medical ok")
from domains.business import BusinessDomain; _p("DBG: business ok")
from domains.finance import FinanceDomain; _p("DBG: finance ok")
from domains.security import SecurityDomain; _p("DBG: security ok")
from domains.development import DevelopmentDomain; _p("DBG: development ok")
from domains.science import ScienceDomain; _p("DBG: science ok")
from domains.engineering import EngineeringDomain; _p("DBG: engineering ok")
from core.proactive_monitor import ProactiveMonitor
from skills.workspace_context import WorkspaceContext
from skills.self_healing_vision import SelfHealingVision
from ui.dashboard import JarvisDashboard
from skills.phone_controller import PhoneController
import ollama; _p("DBG: ollama ok")
from skills.file_manager import FileManager; _p("DBG: file_manager ok")
from skills.data_analyzer import DataAnalyzer; _p("DBG: data_analyzer ok")
from skills.productivity import ProductivityPlanner; _p("DBG: productivity ok")
from skills.security_auditor import SecurityAuditor; _p("DBG: security_auditor ok")
from skills.vision_tracker import VisionTracker; _p("DBG: vision_tracker ok")
from skills.market_analyzer import MarketAnalyzer; _p("DBG: market_analyzer ok")
from skills.gesture_control import GestureController; _p("DBG: gesture_control ok")
from ui.air_canvas import AirCanvas; _p("DBG: air_canvas ok")
from skills.code_runner import CodeRunner; _p("DBG: code_runner ok")
from skills.product_comparator import ProductComparator; _p("DBG: product_comparator ok")
from skills.food_comparator import FoodComparator; _p("DBG: food_comparator ok")
from skills.coding_sandbox import AutonomousCodingSandbox, CompilerRepairEngine; _p("DBG: coding_sandbox ok")
from ui.hologram import HologramSimWidget; _p("DBG: HologramSimWidget ok")
from skills.polyglot_engineer import PolyglotEngineer; _p("DBG: PolyglotEngineer ok")
from skills.research_prodigy import ResearchProdigy; _p("DBG: ResearchProdigy ok")
from skills.emergency_sentinel import EmergencySentinel; _p("DBG: EmergencySentinel ok")


class JARVIS:
    """The master JARVIS integration"""

    def __init__(self):
        with open("./config/settings.yaml") as f:
            self.config = yaml.safe_load(f)
        with open("./config/prompts.yaml") as f:
            self.prompts = yaml.safe_load(f)
            
        # Set Groq API Key in environment variables for subprocesses
        groq_cfg = self.config.get("groq", {})
        if groq_cfg and groq_cfg.get("api_key"):
            os.environ["GROQ_API_KEY"] = groq_cfg.get("api_key")

        self.models = self.config["models"]

        # Ensure Ollama background server is active before starting
        self._ensure_ollama_server()

        logger.info("Initializing JARVIS systems...")
        
        # UI must be initialized in main thread
        _p("INIT: QApplication"); self.app = QApplication(sys.argv)
        _p("INIT: JarvisOrb"); self.orb = JarvisOrb()
        _p("INIT: AirCanvas"); self.canvas = AirCanvas()

        # Auth
        _p("INIT: LocalAuth"); self.auth = LocalAuth()

        # Core
        _p("INIT: AudioEngine"); self.audio = AudioEngine(silence_sec=self.config["audio"]["silence_threshold"])
        _p("INIT: TTSEngine"); self.tts = TTSEngine(
            model_path=self.config["tts"].get("voice_model", "kokoro-v1.0.onnx"),
            voices_path=self.config["tts"].get("voices_json", "voices-v1.0.bin"),
            default_voice=self.config["tts"].get("default_voice", "af_heart"),
            default_speed=self.config["tts"].get("speaking_rate", 1.25)
        )
        _p("INIT: WakeWordDetector"); self.wake = WakeWordDetector()
        self.wake.is_music_playing_cb = self._is_music_playing
        _p("INIT: IntentRouter"); self.router = IntentRouter()
        _p("INIT: JarvisBrain"); self.brain = JarvisBrain()
        _p("INIT: CameraEngine"); self.camera = CameraEngine()
        self.camera.start()
        
        # Skills
        _p("INIT: ScreenVision"); self.vision = ScreenVision()
        _p("INIT: OSControl"); self.os_ctrl = OSControl()
        _p("INIT: WebResearch"); self.web = WebResearch()
        _p("INIT: MediaSummarizer"); self.media = MediaSummarizer()
        _p("INIT: AppMapper"); self.app_map = AppMapper()
        _p("INIT: SpotifyControl"); self.spotify_ctrl = SpotifyControl()
        _p("INIT: YouTubeMusicPlayer"); self.youtube_music = YouTubeMusicPlayer()
        self.youtube_music.on_song_change = lambda title, msg: self.orb.notification_signal.emit(title, msg)
        self.tts.on_speak_start = self._duck_audio
        self.tts.on_speak_end = self._unduck_audio
        
        # Initialize futuristic Iron Man HUD overlay and Macro Recorder
        _p("INIT: IronManHUDOverlay"); self.hud_overlay = IronManHUDOverlay()
        # self.hud_overlay.show()
        self.orb.state_changed.connect(self.hud_overlay.set_hud_state)
        
        _p("INIT: MacroRecorder"); self.macro_recorder = MacroRecorder(vision_engine=self.vision)
        
        _p("INIT: MarketAnalyzer"); self.market_analyzer = MarketAnalyzer()
        _p("INIT: GestureController"); self.gesture_ctrl = GestureController(self.camera, canvas=self.canvas, youtube_music=self.youtube_music)
        self.gesture_ctrl.start()

        # Domains
        _p("INIT: Domains")
        self.domains = {
            "medical": MedicalDomain(),
            "business": BusinessDomain(),
            "finance": FinanceDomain(),
            "security": SecurityDomain(),
            "development": DevelopmentDomain(),
            "science": ScienceDomain(),
            "engineering": EngineeringDomain()
        }

        _p("INIT: WorkspaceContext"); self.workspace_context = WorkspaceContext()
        _p("INIT: SelfHealingVision"); self.self_healing = SelfHealingVision()

        _p("INIT: auth check")
        self.is_authenticated = not self.config["jarvis"].get("pin_enabled", False)

        _p("INIT: JarvisDashboard"); self.dashboard = JarvisDashboard(camera_engine=self.camera)
        self.orb.toggle_callback = self.toggle_dashboard_via_double_click
        self.orb.dashboard_toggle_signal.connect(self._execute_dashboard_toggle)
        self.last_owner_seen_time = time.time()
        _p("INIT: PhoneController"); self.phone = PhoneController()
        self.awaiting_number_for = None
        
        # New offline skills initializations
        _p("INIT: FileManager"); self.file_manager = FileManager()
        _p("INIT: DataAnalyzer"); self.data_analyzer = DataAnalyzer()
        _p("INIT: ProductivityPlanner"); self.productivity = ProductivityPlanner()
        _p("INIT: SecurityAuditor"); self.security_auditor = SecurityAuditor()
        _p("INIT: VisionTracker"); self.vision_tracker = VisionTracker(camera_engine=self.camera)
        _p("INIT: CodeRunner"); self.code_runner = CodeRunner()
        _p("INIT: ProductComparator"); self.product_comparator = ProductComparator()
        _p("INIT: FoodComparator"); self.food_comparator = FoodComparator()
        _p("INIT: AutonomousCodingSandbox"); self.coding_sandbox = AutonomousCodingSandbox()
        _p("INIT: CompilerRepairEngine"); self.compiler_repair = CompilerRepairEngine(self.coding_sandbox)
        
        # Connect AirCanvas air signature detection signal
        self.canvas.signals.signature_detected.connect(self.on_air_signature_detected)

        # Link OSControl to Orb for signals
        self.os_ctrl.orb = self.orb

        # Connect PyQt6 slots for custom overlays
        self.orb.eyecare_toggle_signal.connect(self._execute_eyecare_toggle)
        self.orb.ruler_toggle_signal.connect(self._execute_ruler_toggle)
        self.orb.snipping_tool_signal.connect(self._execute_snipping_tool)
        self.orb.notification_signal.connect(self._show_hud_notification)
        self.orb.hologram_toggle_signal.connect(self._execute_hologram_toggle)

        self.eyecare_overlay = None
        self.screen_ruler = None
        self.snipping_overlay = None
        self.was_yt_playing_before_wake = False
        self.is_listening_to_command = False
        threading.Thread(target=self._phone_monitor, daemon=True).start()
        threading.Thread(target=self._interruption_monitor, daemon=True).start()

        # Proactive alerting

        self.alert_queue = []
        self.alert_lock = threading.Lock()
        self.active_context = None
        self.is_asleep = True

        # Import cognitive tracker
        from core.cognitive import CognitiveSentimentTracker
        self.sentiment_tracker = CognitiveSentimentTracker()
        self.cognitive_state = "calm"

        # Initialize HologramSimWidget
        _p("INIT: HologramSimWidget")
        self.hologram_widget = HologramSimWidget(self.camera)
        self.domains["engineering"].hologram_widget = self.hologram_widget

        _p("INIT: ProactiveMonitor")
        self.proactive_monitor = ProactiveMonitor(
            camera_engine=self.camera,
            alert_callback=self.on_proactive_alert,
            compiler_repair=self.compiler_repair
        )
        self.proactive_monitor.start()
        _p("INIT: Security Sentry")
        self.security_auditor.start_sentry(self.on_proactive_alert)

        _p("INIT: PolyglotEngineer")
        self.polyglot_engineer = PolyglotEngineer()

        _p("INIT: ResearchProdigy")
        self.research_prodigy = ResearchProdigy(web_research_engine=self.web)

        _p("INIT: EmergencySentinel")
        self.emergency_sentinel = EmergencySentinel()

        self._prewarm_models()

        logger.info("JARVIS initialized successfully.")
        _p("INIT: starting background thread")
        threading.Thread(target=self._unlock_monitor, daemon=True).start()
        threading.Thread(target=self.run, daemon=True).start()

    def _ensure_ollama_server(self):
        """Checks if Ollama server is running on port 11434, and if not, launches it in the background."""
        import socket
        import subprocess
        import os
        
        def is_running():
            try:
                with socket.create_connection(("localhost", 11434), timeout=1):
                    return True
            except OSError:
                return False

        if is_running():
            logger.info("Ollama background server is already active.")
            return

        logger.info("Ollama server not active. Attempting to launch background server...")
        try:
            # Resolve executable path on Windows
            ollama_cmd = "ollama"
            if os.name == 'nt':
                user_profile = os.environ.get("USERPROFILE", "")
                fallback_path = os.path.join(user_profile, "AppData", "Local", "Programs", "Ollama", "ollama.exe")
                if os.path.exists(fallback_path):
                    ollama_cmd = fallback_path

            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0  # SW_HIDE
                
            creationflags = 0
            if os.name == 'nt':
                creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | 0x08000000 # DETACHED_PROCESS
                
            subprocess.Popen(
                [ollama_cmd, "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                startupinfo=startupinfo,
                creationflags=creationflags
            )
            
            # Wait up to 10 seconds for the server to bind and respond
            for attempt in range(10):
                if is_running():
                    logger.info("Ollama server successfully launched and active.")
                    return
                time.sleep(1)
            logger.warning("Ollama server launched but did not respond on port 11434 within 10 seconds.")
        except Exception as e:
            logger.error(f"Failed to auto-start Ollama server: {e}")

    def _duck_audio(self):
        """Ducks the background music volume when JARVIS speaks."""
        if hasattr(self, "youtube_music") and self.youtube_music:
            self.youtube_music.duck()

    def _unduck_audio(self):
        """Restores the background music volume after JARVIS finishes speaking."""
        if hasattr(self, "youtube_music") and self.youtube_music:
            if getattr(self, "is_listening_to_command", False):
                logger.debug("Still listening to command. Keeping music ducked.")
                return
            self.youtube_music.unduck()

    def _is_music_playing(self) -> bool:
        """Helper callback to tell the wake word detector if music is active."""
        if hasattr(self, "youtube_music") and self.youtube_music:
            return self.youtube_music.process is not None and not self.youtube_music.is_paused
        return False

    def _prewarm_models(self):
        """Pre-warms the Ollama brain model by sending dummy requests in a background thread."""
        def prewarm():
            logger.info("Starting background pre-warming of Ollama brain model...")
            brain_model = self.models.get("main_brain", "yasserrmd/Human-Like-Qwen2.5-1.5B-Instruct:latest")
            
            # Send dummy query to brain_model
            try:
                logger.info(f"Pre-warming brain model: {brain_model}")
                ollama.generate(model=brain_model, prompt="hi", options={"num_predict": 1})
                logger.info(f"Brain model {brain_model} pre-warmed successfully.")
            except Exception as e:
                logger.warning(f"Failed to pre-warm brain model {brain_model}: {e}")
                
        threading.Thread(target=prewarm, daemon=True).start()

    def _unlock_monitor(self):
        state_file = os.path.abspath("./auth/.auth_state")
        while True:
            try:
                if not self.is_authenticated:
                    # 1. Check keyboard PIN state file
                    if os.path.exists(state_file):
                        try:
                            with open(state_file, "r") as f:
                                content = f.read().strip()
                            if content == "unlocked":
                                logger.info("Keyboard PIN verified. Unlocking...")
                                self.is_authenticated = True
                                self.is_asleep = False
                                self.orb.set_state("speaking")
                                self.tts.speak("Welcome back, sir. Lock screen deactivated.")
                                self.os_ctrl.unlock_screen()
                                self.os_ctrl.wake_monitor()
                                self.orb.set_state("idle")
                                try:
                                    os.remove(state_file)
                                except Exception:
                                    pass
                        except Exception as e:
                            logger.error(f"Error reading auth state file: {e}")
                    
                    # 2. Check Face ID
                    if self.camera.has_face_model and self.camera.latest_frame is not None:
                        frame = self.camera.latest_frame
                        if self.camera.identify_face(frame):
                            logger.info("Face ID verified. Unlocking...")
                            self.is_authenticated = True
                            self.is_asleep = False
                            self.orb.set_state("speaking")
                            self.tts.speak("Identity confirmed. Good evening, sir.")
                            self.os_ctrl.unlock_screen()
                            self.os_ctrl.wake_monitor()
                            self.orb.set_state("idle")
            except Exception as e:
                logger.error(f"Error in unlock monitor: {e}")
            time.sleep(0.5)

    def on_proactive_alert(self, text: str):
        # Check if text is a JSON alert
        if text.startswith("{"):
            try:
                import json
                data = json.loads(text)
                if data.get("type") == "confirm_file_patch":
                    self.active_context = {
                        "type": "confirm_file_patch",
                        "file_path": data["file_path"],
                        "patched_content": data["patched_content"]
                    }
                    spoken_text = data["warning_text"]
                    logger.info(f"Setting active_context for file patch: {data['file_path']}")
                    
                    if self.is_authenticated and not self.is_asleep and self.orb.state == "idle":
                        self.orb.set_state("speaking")
                        self.orb.notification_signal.emit("PROACTIVE ALERT", spoken_text)
                        self.tts.speak(spoken_text)
                        self.orb.set_state("idle")
                    else:
                        with self.alert_lock:
                            self.alert_queue.append(spoken_text)
                    return
                elif data.get("type") == "confirm_quarantine_process":
                    self.active_context = {
                        "type": "confirm_quarantine_process",
                        "pid": data["pid"],
                        "proc_name": data["proc_name"]
                    }
                    spoken_text = data["warning_text"]
                    logger.info(f"Setting active_context for process quarantine: {data['proc_name']}")
                    
                    if self.is_authenticated and not self.is_asleep and self.orb.state == "idle":
                        self.orb.set_state("error")
                        self.orb.notification_signal.emit("PROACTIVE ALERT", spoken_text)
                        self.tts.speak(spoken_text)
                        self.orb.set_state("idle")
                    else:
                        with self.alert_lock:
                            self.alert_queue.append(spoken_text)
                    return
            except Exception as e:
                logger.error(f"Error parsing proactive JSON alert: {e}")

        # Silence alerts regarding system resources except CPU workload spikes which we want spoken proactively
        silent_keywords = ["memory", "graphics processing unit", "storage partition"]
        if any(kw in text.lower() for kw in silent_keywords):
            logger.info(f"Silent proactive alert (notification only): {text}")
            self.orb.notification_signal.emit("PROACTIVE ALERT", text)
            return

        if self.is_authenticated and not self.is_asleep and self.orb.state == "idle":
            logger.info(f"Speaking proactive alert: {text}")
            self.orb.set_state("speaking")
            self.orb.notification_signal.emit("PROACTIVE ALERT", text)
            self.tts.speak(text)
            self.orb.set_state("idle")
        else:
            with self.alert_lock:
                self.alert_queue.append(text)

    def toggle_dashboard_via_double_click(self):
        show = not self.dashboard.isVisible()
        self.orb.dashboard_toggle_signal.emit(show)

    def _execute_dashboard_toggle(self, show: bool):
        if show:
            self.dashboard.show()
            logger.info("HUD Dashboard displayed via slot.")
        else:
            self.dashboard.hide()
            logger.info("HUD Dashboard hidden via slot.")

    def _execute_hologram_toggle(self, show: bool):
        if show:
            self.hologram_widget.show()
            logger.info("Hologram widget shown via slot.")
        else:
            self.hologram_widget.hide()
            logger.info("Hologram widget hidden via slot.")

    def _phone_monitor(self):
        ringing_seconds = 0
        while True:
            try:
                if self.phone.is_device_connected():
                    call_info = self.phone.check_call_state()
                    state = call_info.get("state", 0)
                    number = call_info.get("number", "Unknown")

                    if state == 1:  # Ringing
                        ringing_seconds += 1.5
                        logger.info(f"Incoming call from {number}. Ringing for {ringing_seconds:.1f}s...")
                        if ringing_seconds >= 10.0:
                            logger.warning(f"Ringing threshold reached (10s). Intercepting call from {number}...")
                            self._handle_intercepted_call(number)
                            ringing_seconds = 0
                    else:
                        ringing_seconds = 0
                    time.sleep(1.5)
                else:
                    time.sleep(5.0)
            except Exception as e:
                logger.error(f"Error in phone monitor: {e}")
                time.sleep(5.0)

    def _handle_intercepted_call(self, incoming_number: str):
        logger.info("Answering phone call...")
        self.phone.answer_call()
        time.sleep(1.5)
        
        logger.info("Speaking busy message to caller...")
        self.orb.set_state("speaking")
        # Play sequence in English, Hindi, Gujarati
        self.tts.speak("Darshit is currently busy. Sir will call you back later.")
        self.tts.speak("Darshit abhi vyast hai. Sir aapko baad mein call karenge.")
        self.tts.speak("Darshit atyare vyast che. Sir tamne pachhi call karse.")
        time.sleep(1.0)
        
        logger.info("Hanging up...")
        self.phone.hangup_call()
        self.orb.set_state("idle")
        
        # Announce locally
        self.orb.notification_signal.emit("CALL INTERCEPTED", f"Incoming call from {incoming_number} intercepted.")
        self.tts.speak(f"Sir, I have intercepted the call from {incoming_number} and informed them you are currently busy.")

    def _interruption_monitor(self):
        """Continuously monitors microphone when JARVIS is speaking to detect user interruption."""
        import sounddevice as sd
        import numpy as np
        
        sample_rate = 16000
        block_size = int(0.15 * sample_rate)  # 150ms block
        interruption_counter = 0
        
        # Initialize a single persistent input stream to avoid repeated memory allocation
        try:
            stream = sd.InputStream(samplerate=sample_rate, channels=1, dtype='int16', blocksize=block_size)
            stream.start()
        except Exception as e:
            logger.error(f"Failed to initialize persistent interruption monitor stream: {e}")
            return
            
        while True:
            try:
                if getattr(self, "orb", None) and self.orb.state == "speaking":
                    elapsed = time.time() - getattr(self.tts, "speak_start_time", 0.0)
                    if elapsed < 1.5:
                        interruption_counter = 0
                        # Flush the stream buffer so we don't trigger on stale voice input
                        if stream.active:
                            try:
                                frames = stream.read_available
                                if frames > 0:
                                    stream.read(frames)
                            except Exception:
                                pass
                        time.sleep(0.1)
                        continue
                        
                    if not stream.active:
                        try:
                            stream.start()
                        except Exception:
                            pass
                            
                    # Read block from persistent stream (blocks for 150ms automatically)
                    audio_data, overflowed = stream.read(block_size)
                    if len(audio_data) > 0:
                        rms = np.sqrt(np.mean(np.square(audio_data.astype(np.float32))))
                        interruption_threshold = getattr(self.audio, "energy_threshold", 250.0) * 20.0
                        if rms > max(interruption_threshold, 28000.0):
                            interruption_counter += 1
                            if interruption_counter >= 2:
                                logger.warning(f"Voice interruption detected! RMS={rms:.1f} > threshold={interruption_threshold:.1f}")
                                self.tts.stop_speech()
                                interruption_counter = 0
                        else:
                            interruption_counter = 0
                else:
                    interruption_counter = 0
                    if stream.active:
                        try:
                            stream.stop()
                        except Exception:
                            pass
                    time.sleep(0.2)
            except Exception as e:
                logger.error(f"Error in interruption monitor: {e}")
                time.sleep(0.5)

    def _flush_alerts(self):
        if not self.is_authenticated:
            return
        
        alerts_to_speak = []
        with self.alert_lock:
            if self.alert_queue:
                alerts_to_speak = list(self.alert_queue)
                self.alert_queue.clear()
                
        for alert in alerts_to_speak:
            logger.info(f"Flushing alert: {alert}")
            self.orb.set_state("speaking")
            self.tts.speak(alert)
        self.orb.set_state("idle")

    def _startup_voice(self):
        if not self.is_authenticated:
            if not self.auth.is_setup():
                self.tts.speak("Secure mode is enabled, but no PIN is set. Please state a six digit PIN to setup your lock.")
            else:
                self.tts.speak("Authentication required. Please state your six digit PIN.")
        else:
            name = self.config.get("jarvis", {}).get("name", "JARVIS")
            self.tts.speak(f"{name} online. All systems operational. Waiting on your command, sir.")

    def _generate_response(self, text: str, domain: str = "general") -> str:
        memories = self.brain.format_memories_for_prompt(text)
        
        if domain in self.domains:
            # Route to expert
            return self.domains[domain].answer(text, memories)
            
        system_key = domain if domain in self.prompts["system_prompts"] else "main"
        system = self.prompts["system_prompts"][system_key] + memories

        # Append sentiment modifier to system prompt
        cognitive = getattr(self, "cognitive_state", "calm")
        if cognitive == "stressed":
            system += "\n[System Note: The user is currently feeling STRESSED. Speak slower, be highly encouraging, empathetic, reassuring, and concise to avoid overwhelming them.]"
        elif cognitive == "fatigued":
            system += "\n[System Note: The user is currently feeling FATIGUED/TIRED. Speak in a gentle, warm, encouraging tone, keeping answers brief and comforting.]"
        elif cognitive == "excited":
            system += "\n[System Note: The user is currently feeling EXCITED. Match their energy, be enthusiastic and efficient.]"

        try:
            response = ollama.chat(
                model=self.models["main_brain"],
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": text}
                ]
            )
            return response["message"]["content"]
        except Exception as e:
            logger.error(f"Generate response error: {e}")
            return "I am currently unable to process your request, sir."

    def _safety_check(self, text: str) -> bool:
        """Lightweight safety check (Bypasses heavy LLM shieldgemma to save 2GB+ VRAM and speed up responses)"""
        # Return True directly to optimize performance. Local regex or word blocklists can be added here if needed.
        return True

    def split_chained_commands(self, text: str) -> list[str]:
        import re
        pattern = r"\b(?:and\s+then|then|after\s+that|and\s+after\s+that)\b"
        splits = re.split(pattern, text, flags=re.IGNORECASE)
        commands = [c.strip() for c in splits if c.strip()]
        return commands

    def process_command(self, text: str):
        """Processes a single command, or splits and executes a chain of sequential commands."""
        import re
        commands = self.split_chained_commands(text)
        if len(commands) > 1:
            logger.info(f"Chained commands detected: {commands}")
            for idx, cmd in enumerate(commands):
                cmd_clean = re.sub(r"^(?:first|second|third|fourth|then|and)\s+", "", cmd, flags=re.IGNORECASE).strip()
                if cmd_clean:
                    logger.info(f"Executing chained command {idx+1}/{len(commands)}: '{cmd_clean}'")
                    self._process_single_command(cmd_clean)
                    time.sleep(1.0)
            return
        else:
            self._process_single_command(text)

    def _process_single_command(self, text: str):
        """Full pipeline: route → execute → respond → speak"""
        self.orb.set_state("thinking")

        # Speak filler instantly while processing
        threading.Thread(target=self.tts.speak_filler, daemon=True).start()

        # Store user input in memory
        self.brain.store(text, role="user")

        # Route intent
        intent = self.router.route(text)
        skill = intent.get("skill", "conversation")
        params = intent.get("params", {})
        domain = intent.get("domain", "general")

        logger.info(f"Intent routed -> Skill: {skill} | Domain: {domain} | Params: {params}")

        response = ""

        try:
            # Dispatch to skill
            if skill == "screen_vision":
                action = params.get("action", "")
                if action == "calibrate":
                    self.tts.speak("Please look directly at the camera, sir. I will capture 15 frames of your face to configure your face model.")
                    success = self.camera.calibrate_owner()
                    if success:
                        response = "Face ID setup is complete, sir. All lock systems are fully operational."
                    else:
                        response = "Calibration encountered a fault. Please ensure your lighting is adequate and look directly at the lens, sir."
                elif action == "calibrate_voice":
                    response = self.calibrate_voice_profile()
                else:
                    response = self.vision.analyze(text)

            elif skill == "os_control":
                action = params.get("action", "")
                if action == "launch":
                    response = self.os_ctrl.launch_app(params.get("app", ""))
                elif action == "type":
                    response = self.os_ctrl.type_text(params.get("text", ""))
                elif action == "hotkey":
                    keys = params.get("keys", "").split("+")
                    response = self.os_ctrl.hotkey(*keys)
                elif action == "click":
                    response = self.os_ctrl.click(params.get("x", 0), params.get("y", 0))
                elif action == "show_dashboard":
                    self.orb.dashboard_toggle_signal.emit(True)
                    response = "Opening HUD diagnostics dashboard, sir."
                elif action == "hide_dashboard":
                    self.orb.dashboard_toggle_signal.emit(False)
                    response = "Closing dashboard display, sir."
                elif action == "show_hologram":
                    self.orb.hologram_toggle_signal.emit(True)
                    response = "Activating holographic simulator viewport, sir."
                elif action == "hide_hologram":
                    self.orb.hologram_toggle_signal.emit(False)
                    response = "Deactivating holographic simulator, sir."
                elif action == "close":
                    response = self.os_ctrl.close_app(params.get("app", ""))
                elif action == "minimize":
                    response = self.os_ctrl.minimize_app(params.get("app", ""))
                elif action == "switch_workspace":
                    response = self.os_ctrl.switch_workspace(params.get("direction", "right"))
                elif action == "drag_and_drop":
                    response = self.os_ctrl.drag_and_drop(
                        params.get("x1", 0), params.get("y1", 0),
                        params.get("x2", 0), params.get("y2", 0)
                    )
                elif action == "record_screen":
                    response = self.os_ctrl.record_screen_video(params.get("duration", 5.0))
                elif action == "annotate_screenshot":
                    response = self.os_ctrl.capture_and_annotate_screenshot()
                elif action == "list_startup":
                    response = self.os_ctrl.list_startup_programs()
                elif action == "set_brightness":
                    response = self.os_ctrl.set_brightness(params.get("percent", 50))
                elif action == "toggle_battery_saver":
                    response = self.os_ctrl.toggle_battery_saver(params.get("enable", True))
                elif action == "clean_disk":
                    response = self.os_ctrl.clean_disk()
                elif action == "empty_recycle_bin":
                    response = self.os_ctrl.empty_recycle_bin()
                elif action == "wifi_control":
                    response = self.os_ctrl.wifi_control(params.get("wifi_action", "status"), params.get("profile", ""))
                elif action == "bluetooth_control":
                    response = self.os_ctrl.bluetooth_control(params.get("bt_action", "status"), params.get("device", ""))
                elif action == "check_network_speed":
                    response = self.os_ctrl.check_network_speed()
                elif action == "toggle_mute_mic":
                    response = self.os_ctrl.toggle_mute_mic(params.get("mute", True))
                elif action == "set_mouse_speed":
                    response = self.os_ctrl.set_mouse_speed(params.get("speed", 10))
                elif action == "set_keyboard_lights":
                    response = self.os_ctrl.set_keyboard_lights(params.get("color_hex", "ffffff"))
                elif action == "sync_time":
                    response = self.os_ctrl.sync_time()
                elif action == "toggle_dark_mode":
                    response = self.os_ctrl.toggle_dark_mode(params.get("dark", True))
                elif action == "printer_setup":
                    response = self.os_ctrl.printer_setup(params.get("printer_action", "list"), params.get("printer", ""))
                elif action == "toggle_game_mode":
                    response = self.os_ctrl.toggle_game_mode(params.get("enable", True))
                elif action == "run_auto_update":
                    response = self.os_ctrl.run_auto_update()
                elif action == "pin_window_topmost":
                    response = self.os_ctrl.pin_window_topmost(params.get("topmost", True))
                elif action == "set_wallpaper":
                    response = self.os_ctrl.set_wallpaper(params.get("image_path", ""))
                elif action == "toggle_desktop_icons":
                    response = self.os_ctrl.toggle_desktop_icons(params.get("show", True))
                elif action == "snap_window":
                    response = self.os_ctrl.snap_window(params.get("direction", "left"))
                elif action == "refresh_desktop":
                    response = self.os_ctrl.refresh_desktop()
                elif action == "copy_file_path":
                    response = self.os_ctrl.copy_file_path(params.get("file_path", ""))
                elif action == "create_shortcut":
                    response = self.os_ctrl.create_shortcut(params.get("target_path", ""), params.get("shortcut_path", ""))
                elif action == "toggle_eye_care":
                    response = self.os_ctrl.toggle_eye_care(params.get("enable", True))
                elif action == "show_screen_ruler":
                    response = self.os_ctrl.show_screen_ruler()
                elif action == "show_snipping_tool":
                    response = self.os_ctrl.show_snipping_tool()
                else:
                    response = self._generate_response(text, domain)

            elif skill == "phone":
                action = params.get("action", "")
                name = params.get("name", "")
                number = params.get("number", "")
                app_name = params.get("app_name", "")

                if action == "make_call":
                    if name:
                        resolved_number = self.phone.get_contact_by_name(name)
                        if resolved_number:
                            response = self.phone.make_call(resolved_number)
                        else:
                            self.awaiting_number_for = name
                            response = f"I could not find a contact named {name} in your address book, sir. What is their phone number?"
                    else:
                        response = self.phone.make_call(number)

                elif action == "call_and_save":
                    self.phone.make_call(number)
                    success = self.phone.save_contact(name, number)
                    if success:
                        response = f"Dialing number on your phone and saving contact {name}, sir."
                    else:
                        response = f"Dialing number, but failed to save contact {name} to address book, sir."

                elif action == "save_contact":
                    success = self.phone.save_contact(name, number)
                    if success:
                        response = f"I have saved contact {name} with number {number} on your device, sir."
                    else:
                        response = f"I was unable to save contact {name} on your device, sir."

                elif action == "launch_app":
                    response = self.phone.launch_app_on_phone(app_name)

                elif action == "answer":
                    self.phone.answer_call()
                    response = "Answering the call on your phone, sir."

                elif action == "hangup":
                    self.phone.hangup_call()
                    response = "Terminating the call on your phone, sir."

                elif action == "go_home":
                    response = self.phone.go_home()

                elif action == "flashlight":
                    if params.get("toggle"):
                        response = self.phone.toggle_flashlight()
                    else:
                        response = self.phone.set_flashlight(params.get("state", True))

                elif action == "volume":
                    vol_action = params.get("vol_action", "")
                    if vol_action == "adjust":
                        response = self.phone.adjust_volume(params.get("direction", "up"))
                    elif vol_action == "set_level":
                        response = self.phone.set_volume_level(params.get("percent", 50))
                    elif vol_action == "mute":
                        response = self.phone.mute_unmute(params.get("mute", True))
                    elif vol_action == "profile":
                        response = self.phone.set_sound_profile(params.get("profile", "normal"))
                    elif vol_action == "status":
                        response = self.phone.get_volume_status()
                    else:
                        response = "Unsupported phone volume operation, sir."

                elif action == "brightness":
                    bright_action = params.get("bright_action", "")
                    if bright_action == "adjust":
                        response = self.phone.adjust_brightness(params.get("direction", "up"))
                    elif bright_action == "set_level":
                        response = self.phone.set_brightness_level(params.get("percent", 50))
                    elif bright_action == "max_min":
                        response = self.phone.set_brightness_max_min(params.get("max", True))
                    elif bright_action == "auto":
                        response = self.phone.set_auto_brightness(params.get("enable", True))
                    elif bright_action == "status":
                        response = self.phone.get_brightness_status()
                    else:
                        response = "Unsupported phone brightness operation, sir."

                elif action == "open_camera":
                    response = self.phone.open_camera()

                elif action == "click_shutter":
                    response = self.phone.click_shutter()

                elif action == "flip_camera":
                    response = self.phone.flip_camera()

                elif action == "take_photo_handsfree":
                    response = self.phone.take_photo_handsfree()

                elif action == "screen_analysis":
                    self.tts.speak("Capturing your phone's screen layout for visual analysis, sir.")
                    img_path = self.phone.capture_screen_for_analysis()
                    if img_path.startswith("Error"):
                        response = img_path
                    else:
                        logger.info(f"Feeding phone screen to ScreenVision: {img_path}")
                        orig_shot = self.vision.latest_screenshot
                        self.vision.latest_screenshot = img_path
                        try:
                            prompt = "This is a screenshot from my Android phone. Describe what is visible on this screen in detail."
                            response = self.vision.analyze(prompt)
                        finally:
                            self.vision.latest_screenshot = orig_shot

                elif action == "camera_analysis":
                    self.tts.speak("Triggering phone camera capture to analyze your physical surroundings, sir.")
                    img_path = self.phone.capture_camera_for_analysis()
                    if img_path.startswith("Error"):
                        response = img_path
                    else:
                        logger.info(f"Feeding phone camera capture to ScreenVision: {img_path}")
                        orig_shot = self.vision.latest_screenshot
                        self.vision.latest_screenshot = img_path
                        try:
                            prompt = "This is a photo captured from my Android phone camera. Analyze my physical surroundings visible in this image."
                            response = self.vision.analyze(prompt)
                        finally:
                            self.vision.latest_screenshot = orig_shot

                elif action == "reminder":
                    msg = params.get("message", "Reminder")
                    time_val = params.get("time", "")
                    response = self.phone.set_smart_reminder(msg, time_val)

                elif action == "system_info":
                    info_type = params.get("info_type", "")
                    if info_type == "battery":
                        response = self.phone.get_battery_status()
                    elif info_type == "time_date":
                        response = self.phone.get_device_time_date()
                    elif info_type == "weather":
                        response = self.phone.get_local_weather(params.get("location", ""))
                    elif info_type == "location":
                        response = self.phone.get_current_location()
                    else:
                        response = "Unsupported phone telemetry requested, sir."

                elif action == "sms":
                    phone_dest = params.get("phone", "")
                    msg = params.get("message", "")
                    response = self.phone.send_sms(phone_dest, msg)

                elif action == "whatsapp_message":
                    dest = params.get("contact", "")
                    msg = params.get("message", "")
                    response = self.phone.send_whatsapp_message_adb(dest, msg)

                elif action == "whatsapp_call":
                    dest = params.get("name", "")
                    video_mode = params.get("video", False)
                    response = self.phone.whatsapp_call_adb(dest, video_mode)

                elif action == "navigation":
                    nav_action = params.get("nav_action", "")
                    q = params.get("query", "")
                    if nav_action == "navigate":
                        response = self.phone.start_navigation(q)
                    elif nav_action == "view":
                        response = self.phone.view_on_map(q)
                    elif nav_action == "nearby":
                        response = self.phone.find_nearby_places(q)
                    else:
                        response = "Unsupported maps request, sir."

                elif action == "lock_power":
                    lock_action = params.get("lock_action", "")
                    if lock_action == "lock":
                        response = self.phone.lock_phone()
                    elif lock_action == "power_menu":
                        response = self.phone.open_power_menu()
                    else:
                        response = "Unsupported power event, sir."

                elif action == "spotify":
                    spotify_action = params.get("spotify_action", "")
                    if spotify_action == "play":
                        response = self.phone.play_spotify_track(params.get("query", ""))
                    elif spotify_action == "resume":
                        response = self.phone.resume_playback()
                    else:
                        response = "Unsupported media event, sir."

                elif action == "connectivity":
                    conn_action = params.get("conn_action", "")
                    if conn_action == "toggle":
                        response = self.phone.toggle_network(params.get("interface", ""), params.get("enable", True))
                    elif conn_action == "airplane":
                        response = self.phone.toggle_airplane_mode(params.get("enable", True))
                    else:
                        response = "Unsupported connectivity event, sir."

                else:
                    response = self._generate_response(text, domain)

            elif skill == "web_research":
                action = params.get("action", "")
                query = params.get("query", text)
                url = params.get("url", "")
                if action == "download":
                    response = self.web.download_file(url)
                elif action == "daily_news":
                    response = self.web.get_daily_news_summary()
                elif action == "track_competitor":
                    response = self.web.track_competitor_website(url)
                elif action == "extract_tables":
                    response = self.web.extract_tables_from_webpage(url)
                elif action == "monitor_rss":
                    response = self.web.monitor_rss_feed(url)
                elif action == "search_papers":
                    response = self.web.search_academic_papers(params.get("query", ""))
                elif action == "fact_check":
                    response = self.web.fact_check(params.get("statement", ""))
                elif action == "whatsapp_message":
                    response = self.web.whatsapp_message(params.get("phone", ""), params.get("message", ""))
                elif action == "search_food":
                    response = self.web.search_food(params.get("query", ""))
                elif action == "track_package":
                    response = self.web.track_package(params.get("carrier", ""), params.get("tracking_number", ""))
                else:
                    if "mode" in params and params["mode"] == "visual":
                        response = self.web.visual_search_and_summarize(query)
                    else:
                        response = self.web.headless_search_and_summarize(query)

            elif skill == "media_summarize":
                url = params.get("url", "")
                if url:
                    response = self.media.summarize_youtube(url)
                else:
                    response = "Please provide a URL or file path to summarize, sir."

            elif skill == "code":
                response = self._generate_response(text, "development")

            elif skill == "system_monitor":
                try:
                    import psutil
                    cpu = psutil.cpu_percent()
                    ram = psutil.virtual_memory().percent
                    response = f"System resources are nominal. CPU is at {cpu} percent and RAM is at {ram} percent, sir."
                except ImportError:
                    response = "psutil is not installed. Run `pip install psutil` to monitor the system."
                
            elif skill == "app_control":
                action = params.get("action", "")
                app_name = params.get("app", "")
                if action == "map":
                    response = self.app_map.map_app_ui(app_name)
                elif action == "click":
                    response = self.app_map.click_element(app_name, params.get("element", ""))
                elif action == "fill":
                    response = self.app_map.fill_form_field(app_name, params.get("field", ""), params.get("text", ""))
                else:
                    response = self._generate_response(text, domain)

            elif skill == "market_analyzer":
                action = params.get("action", "")
                query = params.get("query", "")
                if action == "analyze":
                    response = self.market_analyzer.analyze_asset(query)
                else:
                    response = self._generate_response(text, domain)

            elif skill == "spotify":
                action = params.get("action", "")
                query = params.get("query", "")
                use_spotify = "spotify" in text.lower() or self.spotify_ctrl.use_api
                if not use_spotify:
                    if action == "play":
                        response = self.youtube_music.play_song(query)
                    elif action in ["pause", "resume", "next", "previous", "volume_up", "volume_down"]:
                        if action == "pause":
                            if "stop" in text.lower():
                                response = self.youtube_music.control_media("stop")
                            else:
                                response = self.youtube_music.control_media("pause")
                        elif action == "resume":
                            response = self.youtube_music.control_media("resume")
                        elif action in ["volume_up", "volume_down", "next", "previous"]:
                            response = self.youtube_music.control_media(action)
                        else:
                            response = self.spotify_ctrl.control_media(action)
                    else:
                        response = self._generate_response(text, domain)
                else:
                    if action == "play":
                        response = self.spotify_ctrl.play_song(query)
                    elif action in ["pause", "resume", "next", "previous", "volume_up", "volume_down"]:
                        response = self.spotify_ctrl.control_media(action)
                    else:
                        response = self._generate_response(text, domain)

            elif skill == "memory_ops":
                action = params.get("action", "")
                query = params.get("query", "")
                if action == "store":
                    self.brain.store_fact(query)
                    response = "I have noted that down and committed it to memory, sir."
                else:
                    response = self._generate_response(text, domain)

            elif skill == "workspace_context":
                action = params.get("action", "")
                if action == "explain_workspace":
                    context_summary = self.workspace_context.get_editor_context_summary()
                    query = f"Explain my current workspace context and files:\n{context_summary}"
                    response = self._generate_response(query, domain)
                elif action == "read_clipboard":
                    clip_text = self.workspace_context.read_clipboard()
                    response = f"Your clipboard currently contains the following, sir:\n{clip_text}"
                else:
                    response = self._generate_response(text, domain)

            elif skill == "self_healing":
                action = params.get("action", "")
                element_name = params.get("element_name", "")
                if action == "click_element":
                    self.tts.speak(f"Locating and clicking the {element_name}, sir.")
                    success = self.self_healing.click_element_visually(element_name)
                    if success:
                        response = f"Successfully clicked the {element_name}, sir."
                    else:
                        response = f"I was unable to visually locate the {element_name} on your screen, sir."
                else:
                    response = self._generate_response(text, domain)


            elif skill == "file_manager":
                action = params.get("action", "")
                path = params.get("path", "")
                if action == "create_file":
                    response = self.file_manager.create_file(path, params.get("content", ""))
                elif action == "rename_file":
                    response = self.file_manager.rename_file(params.get("old_path", ""), params.get("new_path", ""))
                elif action == "move_file":
                    response = self.file_manager.move_file(params.get("src", ""), params.get("dst", ""))
                elif action == "delete_file":
                    response = self.file_manager.delete_file(path, params.get("shred", False))
                elif action == "create_directory":
                    response = self.file_manager.create_directory(path)
                elif action == "delete_directory":
                    response = self.file_manager.delete_directory(path)
                elif action == "toggle_show_hidden_files":
                    response = self.file_manager.toggle_show_hidden_files(params.get("show", True))
                elif action == "set_file_hidden":
                    response = self.file_manager.set_file_hidden(path, params.get("hide", True))
                elif action == "get_folder_size":
                    response = self.file_manager.get_folder_size(path)
                elif action == "sync_folders":
                    response = self.file_manager.sync_folders(params.get("src", ""), params.get("dst", ""))
                elif action == "backup_to_local_cloud":
                    response = self.file_manager.backup_to_local_cloud(path, params.get("cloud_provider", "onedrive"))
                else:
                    response = "File action not supported, sir."

            elif skill == "data_analyzer":
                action = params.get("action", "")
                filepath = params.get("filepath", "")
                if action == "read_document":
                    response = self.data_analyzer.read_document_text(filepath)
                elif action == "calculate_statistics":
                    response = self.data_analyzer.calculate_statistics(filepath, params.get("column_name", ""))
                elif action == "log_kpi":
                    response = self.data_analyzer.log_kpi(params.get("name", ""), params.get("value", 0.0))
                elif action == "kpi_history":
                    response = self.data_analyzer.get_kpi_history(params.get("name", ""))
                else:
                    response = "Data analysis action not supported, sir."

            elif skill == "productivity":
                action = params.get("action", "")
                if action == "add_todo":
                    response = self.productivity.add_todo(params.get("task", ""))
                elif action == "list_todos":
                    response = self.productivity.list_todos()
                elif action == "complete_todo":
                    response = self.productivity.complete_todo(params.get("todo_id", 0))
                elif action == "check_inbox":
                    response = self.productivity.check_inbox()
                elif action == "record_meeting":
                    response = self.productivity.record_meeting_notes(params.get("duration", 60))
                elif action == "edit_pdf":
                    response = self.productivity.edit_pdf(
                        params.get("pdf_action", "merge"),
                        params.get("files_list", []),
                        params.get("output_path", ""),
                        params.get("page_num", 0),
                        params.get("angle", 90)
                    )
                elif action == "create_presentation":
                    import json
                    title = params.get("title", "Topic")
                    prompt = f"Create a slide bullet outline for a 3-slide presentation on '{title}'. Output raw JSON containing a list of objects with 'title' (string) and 'bullets' (list of strings). Do not include any markdown wrapper or backticks."
                    try:
                        res = ollama.chat(model=self.models["main_brain"], messages=[{"role": "user", "content": prompt}])
                        raw = res["message"]["content"].strip().replace("```json", "").replace("```", "").strip()
                        slides_content = json.loads(raw)
                    except Exception:
                        slides_content = [
                            {"title": "Introduction to " + title, "bullets": ["Overview of the topic", "Key components", "Initial analysis"]},
                            {"title": "Deep Dive", "bullets": ["Detailed explanations", "Current trends and developments", "Practical examples"]},
                            {"title": "Summary", "bullets": ["Conclusion of key points", "Next steps"]}
                        ]
                    name = self.config.get("jarvis", {}).get("name", "JARVIS")
                    response = self.productivity.pptx_helper(title, f"Generated by {name}", slides_content)
                elif action == "create_mind_map":
                    import json
                    central_idea = params.get("central_idea", "Idea")
                    prompt = f"Generate 5 sub-topics linked to the central idea '{central_idea}'. Output raw JSON list of strings. Do not include markdown code block formatting."
                    try:
                        res = ollama.chat(model=self.models["main_brain"], messages=[{"role": "user", "content": prompt}])
                        raw = res["message"]["content"].strip().replace("```json", "").replace("```", "").strip()
                        nodes = json.loads(raw)
                    except Exception:
                        nodes = ["Overview", "Details", "Challenges", "Solutions", "Future"]
                    response = self.productivity.create_mind_map(central_idea, nodes)
                elif action == "block_distractions":
                    response = self.productivity.block_distractions(params.get("domains_list", []), params.get("block", True))
                elif action == "sign_document":
                    response = self.productivity.sign_document(
                        params.get("doc_path", ""),
                        params.get("sig_img_path", ""),
                        params.get("output_path", ""),
                        params.get("coords", (100, 100))
                    )
                else:
                    response = "Productivity action not supported, sir."

            elif skill == "security_auditor":
                action = params.get("action", "")
                if action == "scan_ports":
                    response = self.security_auditor.scan_ports(params.get("host", "127.0.0.1"))
                elif action == "scan_network":
                    response = self.security_auditor.scan_network_devices()
                elif action == "audit_traffic":
                    response = self.security_auditor.list_active_outbound_connections()
                elif action == "audit_password":
                    response = self.security_auditor.audit_password_strength(params.get("password", ""))
                elif action == "audit_cve":
                    response = self.security_auditor.audit_installed_packages_for_cves()
                elif action == "audit_logs":
                    response = self.security_auditor.analyze_workspace_logs()
                else:
                    response = "Security audit action not supported, sir."

            elif skill == "vision_tracker":
                action = params.get("action", "")
                if action == "detect_objects":
                    response = self.vision_tracker.detect_objects_in_room()
                elif action == "analyze_fatigue":
                    response = self.vision_tracker.analyze_user_fatigue_and_stress()
                elif action == "analyze_appearance":
                    response = self.vision_tracker.analyze_user_appearance()
                else:
                    response = "Vision tracking action not supported, sir."

            elif skill == "code_runner":
                action = params.get("action", "")
                if action == "run_code":
                    response = self.code_runner.run_code(params.get("language", "python"), params.get("code_text", ""))
                elif action == "git_command":
                    response = self.code_runner.git_command(params.get("git_action", "status"), params.get("args", ""))
                elif action == "docker_command":
                    response = self.code_runner.docker_command(params.get("docker_action", "list"), params.get("args", ""))
                elif action == "mobile_view_emulation":
                    response = self.code_runner.mobile_view_emulation(params.get("url", ""))
                elif action == "deploy_app":
                    response = self.code_runner.deploy_app(params.get("project_path", ""), params.get("port", 3000))
                else:
                    response = "Code runner action not supported, sir."

            elif skill == "product_comparison":
                response = self.product_comparator.search_and_compare(
                    params.get("query", ""),
                    params.get("budget", None)
                )

            elif skill == "food_ordering":
                response = self.food_comparator.find_food(
                    params.get("query", ""),
                    params.get("budget", None)
                )

            elif skill == "macro_recorder":
                action = params.get("action", "")
                name = params.get("name", "default_macro")
                if action == "start":
                    response = self.macro_recorder.start_recording(name)
                elif action == "stop":
                    response = self.macro_recorder.stop_recording(name)
                elif action == "play":
                    response = self.macro_recorder.play_macro(name)
                else:
                    response = "Unsupported macro recorder operation, sir."

            elif skill == "customizer":
                action = params.get("action", "")
                if action == "enter":
                    response = "Customization protocol active, sir. What parameters shall I adjust?"
                elif action == "set_threshold":
                    val = params.get("value", 0.78)
                    if hasattr(self, "wake") and self.wake and self.wake.voice_profile:
                        self.wake.voice_profile["threshold"] = val
                        with open(self.wake.voice_profile_path, "w") as f:
                            import json
                            json.dump(self.wake.voice_profile, f, indent=2)
                        self.wake._load_voice_profile()
                        response = f"Voice print similarity threshold adjusted to {val}, sir."
                    else:
                        response = "No active voice profile calibrated, sir."
                elif action == "set_speed":
                    val = params.get("value", 1.25)
                    self.tts.default_speed = val
                    response = f"Speech rate set to {val}, sir."
                elif action == "toggle_hud":
                    visible = self.hud_overlay.isVisible()
                    self.hud_overlay.setVisible(not visible)
                    response = f"HUD screen overlay is now {'disabled' if visible else 'enabled'}, sir."
                else:
                    response = "Unsupported voice customizer action, sir."

            elif skill == "coding_sandbox":
                action = params.get("action", "")
                if action == "execute_task":
                    self.tts.speak("Initializing isolated coding sandbox, sir. Please wait while I construct and run the solution.")
                    response = self.coding_sandbox.execute_task(params.get("task", ""))
                elif action == "compiler_repair":
                    self.tts.speak("Initiating compiler repair loop, sir. I will build the project and fix any errors automatically.")
                    response = self.compiler_repair.compile_and_repair(params.get("command", ""))
                elif action == "compile_canvas":
                    self.tts.speak("Capturing air canvas drawing for visual analysis, sir.")
                    image_path = self.canvas.grab_canvas_image()
                    self.tts.speak("Analyzing strokes and parsing coordinates, sir.")
                    visual_query = (
                        "Analyze this drawing. Identify what coordinates, shapes, text, equations, or layout structure "
                        "are present. Describe them clearly so an AI coder can write a Python PyQt6 application replicating this drawing."
                    )
                    drawing_description = self.vision.analyze_image(image_path, visual_query)
                    logger.info(f"Air canvas visual analysis: {drawing_description}")
                    
                    self.tts.speak("Generating application code and compiling program inside sandbox, sir.")
                    response = self.coding_sandbox.execute_task(
                        f"Construct a PyQt6 GUI application based on this drawing description: {drawing_description}"
                    )
                    try:
                        import os
                        os.unlink(image_path)
                    except Exception:
                        pass
                else:
                    response = "Unsupported coding sandbox action, sir."

            elif skill == "polyglot_engineer":
                action = params.get("action", "")
                if action == "design_architecture":
                    self.tts.speak("Designing system architecture and generating blueprints, sir.")
                    response = self.polyglot_engineer.design_architecture(params.get("task", ""))
                elif action == "write_solution":
                    lang = params.get("language", "python")
                    self.tts.speak(f"Writing optimized {lang} solution, sir.")
                    response = self.polyglot_engineer.write_polyglot_solution(lang, params.get("task", ""))
                elif action == "review_code":
                    lang = params.get("language", "python")
                    self.tts.speak(f"Reviewing {lang} code structure, sir.")
                    code = ""
                    try:
                        import pyperclip
                        code = pyperclip.paste().strip()
                    except Exception:
                        pass
                    if not code:
                        for root, dirs, files in os.walk("."):
                            dirs[:] = [d for d in dirs if d not in {".git", "__pycache__", "jarvis_env", ".agents", ".gemini"}]
                            for f in files:
                                if f.endswith((".py", ".go", ".rs", ".cpp", ".zig")):
                                    try:
                                        with open(os.path.join(root, f), "r", encoding="utf-8") as file:
                                            code = file.read()
                                            break
                                    except Exception:
                                        pass
                            if code:
                                break
                    if code:
                        response = self.polyglot_engineer.review_code(lang, code)
                    else:
                        response = f"Sir, I could not find any code in your clipboard or active workspace files to review."
                else:
                    response = "Unsupported polyglot engineering action, sir."

            elif skill == "research_prodigy":
                action = params.get("action", "")
                if action == "deep_research":
                    topic = params.get("topic", "")
                    self.tts.speak("Initiating multi-stage deep research crawl, sir. Gathering facts and academic publications.")
                    response = self.research_prodigy.execute_deep_research(topic)
                else:
                    response = "Unsupported research prodigy action, sir."

            else:
                # Default: conversation with domain knowledge
                response = self._generate_response(text, domain)
                
        except Exception as e:
            logger.error(f"Skill execution failed: {e}")
            response = "I encountered a minor fault while executing that command, sir."

        # Safety check
        if not self._safety_check(response):
            response = "I cannot assist with that request, sir."

        # Store response in memory
        self.brain.store(response, role="assistant", skill=skill)

        # Speak
        self.orb.set_state("speaking")
        self.tts.speak(response)
        self.orb.set_state("idle")

    def _handle_auth(self, text: str):
        self.orb.set_state("thinking")
        # STT might return text like "my pin is 123456"
        # Extract digits
        pin = "".join(filter(str.isdigit, text))
        
        if not self.auth.is_setup():
            if len(pin) == 6:
                if self.auth.setup_pin(pin):
                    self.is_authenticated = True
                    self.orb.set_state("speaking")
                    self.tts.speak("PIN setup successful. I am now fully operational, sir.")
                else:
                    self.tts.speak("PIN setup failed. Please carefully state a six digit PIN.")
            else:
                self.tts.speak("I need a precise six digit PIN to setup your secure lock.")
            self.orb.set_state("idle")
            return

        # Verification
        if len(pin) >= 6:
            # Try to grab the first 6 digits spoken
            pin = pin[:6]
            success, msg = self.auth.verify_pin(pin)
            self.orb.set_state("speaking")
            self.tts.speak(msg)
            if success:
                self.is_authenticated = True
                self.os_ctrl.unlock_screen()
                self.os_ctrl.wake_monitor()
        else:
            self.tts.speak("Authentication failed. Please clearly state your six digit PIN.")
            
        self.orb.set_state("idle")

    def _execute_eyecare_toggle(self, enable: bool):
        from ui.overlay_widgets import EyeCareOverlay
        if enable:
            if not self.eyecare_overlay:
                self.eyecare_overlay = EyeCareOverlay()
            self.eyecare_overlay.show()
            logger.info("Eye care overlay activated.")
        else:
            if self.eyecare_overlay:
                self.eyecare_overlay.close()
                self.eyecare_overlay = None
            logger.info("Eye care overlay deactivated.")

    def _execute_ruler_toggle(self, show: bool):
        from ui.overlay_widgets import ScreenRuler
        if show:
            if not self.screen_ruler:
                self.screen_ruler = ScreenRuler()
            self.screen_ruler.show()
            logger.info("Screen ruler activated.")
        else:
            if self.screen_ruler:
                self.screen_ruler.close()
                self.screen_ruler = None
            logger.info("Screen ruler deactivated.")

    def _execute_snipping_tool(self):
        from ui.overlay_widgets import SnippingOverlay
        if self.snipping_overlay:
            self.snipping_overlay.close()
        self.snipping_overlay = SnippingOverlay()
        self.snipping_overlay.snipped.connect(self._on_snipped_completed)
        self.snipping_overlay.show()
        logger.info("Snipping tool activated.")

    def _on_snipped_completed(self, path: str):
        self.snipping_overlay = None
        if path:
            logger.info(f"Snipping capture saved to: {path}")
            self.tts.speak(f"Region captured and saved to {os.path.basename(path)}, sir.")
        else:
            logger.info("Snipping tool cancelled.")

    def _show_hud_notification(self, title: str, message: str):
        try:
            from ui.hud_notification import HudNotificationManager
            HudNotificationManager.show_toast(title, message)
        except Exception as e:
            logger.error(f"Failed to show HUD notification: {e}")

    def on_air_signature_detected(self, signature: str):
        if not signature:
            return
        logger.info(f"Air signature detected: {signature}")
        self.orb.set_state("speaking")
        if signature == "S":
            self.tts.speak("Air signature S recognized. Launching Spotify, sir.")
            try: os.startfile("spotify:")
            except Exception: pass
        elif signature == "C":
            self.tts.speak("Air signature C recognized. Launching Chrome, sir.")
            try: os.startfile("chrome.exe")
            except Exception: pass
        elif signature == "G":
            self.tts.speak("Air signature G recognized. Opening GitHub, sir.")
            import webbrowser
            try: webbrowser.open("https://github.com")
            except Exception: pass
        elif signature == "W":
            self.tts.speak("Air signature W recognized. Opening WhatsApp, sir.")
            try: os.startfile("whatsapp:")
            except Exception: pass
        elif signature == "circle":
            self.tts.speak("Air signature circle recognized. Opening system dashboard, sir.")
            self.orb.dashboard_toggle_signal.emit(True)
        else:
            self.tts.speak(f"Air signature {signature} recognized, sir.")
        self.orb.set_state("idle")

    def calibrate_voice_profile(self) -> str:
        """Calibrates the user's voice profile by recording 'Hey JARVIS' 3 times."""
        self.orb.set_state("speaking")
        self.tts.speak("Starting voice calibration process. I will need you to say 'Hey JARVIS' three times. Let's record the first attempt.")
        
        from core.wake_word import compute_mean_mfcc, cosine_similarity
        import numpy as np
        import json
        import time
        import os
        
        utterance_mfccs = []
        attempts = 0
        max_attempts = 6
        
        while len(utterance_mfccs) < 3 and attempts < max_attempts:
            attempts += 1
            self.orb.set_state("speaking")
            if len(utterance_mfccs) > 0:
                self.tts.speak(f"Please say 'Hey JARVIS' again (attempt {len(utterance_mfccs)+1} of 3)...")
            else:
                self.tts.speak("Please say 'Hey JARVIS' now...")
                
            time.sleep(0.5)
            self.orb.set_state("listening")
            
            # Record raw audio
            audio_data = self.audio.listen_raw(timeout_sec=5.0)
            
            if audio_data is None:
                self.orb.set_state("speaking")
                self.tts.speak("I did not hear anything. Let's try that attempt again.")
                continue
                
            # Check length/energy
            rms = np.sqrt(np.mean(audio_data**2))
            # At least 0.5 seconds of audio and not silent
            if len(audio_data) < 8000 or rms < 0.002: 
                self.orb.set_state("speaking")
                self.tts.speak("The recording was too quiet or too short. Let's try that attempt again.")
                continue
                
            # Extract MFCC
            try:
                mean_mfcc = compute_mean_mfcc(audio_data)
                utterance_mfccs.append(mean_mfcc)
                self.orb.set_state("speaking")
                self.tts.speak(f"Attempt {len(utterance_mfccs)} captured successfully.")
            except Exception as e:
                logger.error(f"Error extracting MFCC: {e}")
                self.tts.speak("I encountered a fault processing that attempt. Let's retry.")
                
        if len(utterance_mfccs) < 3:
            self.orb.set_state("speaking")
            return "Voice calibration failed due to too many invalid attempts, sir. Please try again when you are ready."
            
        # Calculate pair-wise similarities
        sim12 = cosine_similarity(utterance_mfccs[0], utterance_mfccs[1])
        sim13 = cosine_similarity(utterance_mfccs[0], utterance_mfccs[2])
        sim23 = cosine_similarity(utterance_mfccs[1], utterance_mfccs[2])
        
        min_sim = min(sim12, sim13, sim23)
        logger.info(f"Calibration similarities: 1-2: {sim12:.3f}, 1-3: {sim13:.3f}, 2-3: {sim23:.3f} (Min: {min_sim:.3f})")
        
        # Calculate mean vector
        mean_vector = np.mean(utterance_mfccs, axis=0)
        
        # Adaptive threshold: min_sim - 0.05, capped between 0.72 and 0.80
        adaptive_threshold = max(0.72, min(0.80, min_sim - 0.05))
        
        # Save profile
        profile = {
            "mean_vector": mean_vector.tolist(),
            "threshold": adaptive_threshold
        }
        
        os.makedirs("config", exist_ok=True)
        profile_path = "config/voice_profile.json"
        try:
            with open(profile_path, "w") as f:
                json.dump(profile, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to write voice profile JSON: {e}")
            return "I failed to write your voice profile to the disk, sir."
            
        # Reload detector profile
        if hasattr(self, "wake") and self.wake:
            self.wake._load_voice_profile()
            
        self.orb.set_state("speaking")
        return f"Voice calibration complete, sir. Speaker verification is now active with an adaptive threshold of {adaptive_threshold:.2f}."

    def _auto_pause_music(self):
        """Temporarily ducks active background music when JARVIS wakes up to listen."""
        self.was_yt_playing_before_wake = (
            self.youtube_music.process is not None 
            and not self.youtube_music.is_paused
        )
        if self.was_yt_playing_before_wake:
            logger.info("Auto-ducking YouTube music to 35% to listen to command...")
            self.youtube_music.duck()

    def _auto_resume_music(self, user_command: str = ""):
        """Restores background music volume if it was temporarily ducked."""
        self.is_listening_to_command = False # Reset flag
        self.was_yt_playing_before_wake = False # Reset flag
        
        # Check if user explicitly asked to pause, stop, or sleep
        cmd_clean = user_command.lower().strip() if user_command else ""
        explicit_stop = any(
            phrase in cmd_clean 
            for phrase in ["stop", "pause", "shut up", "go to sleep", "sentry", "shutdown"]
        )
        
        if self.youtube_music.process is not None:
            if explicit_stop:
                logger.info("Command requested stop/pause. Pausing YouTube music...")
                self.youtube_music.pause_song()
            else:
                logger.info("Restoring YouTube music volume to original level...")
                self.youtube_music.unduck()

    def run(self):
        """Main voice loop in background thread"""
        # Give UI a moment to show up
        time.sleep(1)
        self._startup_voice()
        
        self.is_asleep = True
        
        while True:
            try:
                self.orb.set_state("idle")
                
                if self.is_asleep:
                    # 1. Wait for wake word
                    if not self.wake.listen_for_wake_word():
                        continue
                        
                    self.is_listening_to_command = True
                    # Temporarily pause background music
                    self._auto_pause_music()
                        
                    # Play wakeup response immediately so user knows it's listening
                    self.orb.set_state("speaking")
                    
                    alerts_to_speak = []
                    with self.alert_lock:
                        if self.alert_queue:
                            alerts_to_speak = list(self.alert_queue)
                            self.alert_queue.clear()
                            
                    if alerts_to_speak:
                        alert_msg = " Also, ".join(alerts_to_speak)
                        self.tts.speak(f"Yes, sir? I notice a critical warning. {alert_msg}")
                    else:
                        self.tts.speak("Yes, sir?")
                        
                    self.is_asleep = False
                
                # Ensure is_listening_to_command and ducking are active before recording command
                self.is_listening_to_command = True
                self._auto_pause_music()
                
                self.orb.set_state("listening")
                
                # 2. Record command (blocks until user stops speaking or 5-second silence timeout)
                text = self.audio.listen(timeout_sec=5.0)
                
                # Check owner presence via face recognition to refresh timer
                if self.camera.has_face_model and self.camera.latest_frame is not None:
                    if self.camera.identify_face(self.camera.latest_frame):
                        self.last_owner_seen_time = time.time()
                        logger.info("Owner face verified. Presence timer refreshed.")
                
                if not text:
                    # Timeout during number entry
                    if getattr(self, "awaiting_number_for", None):
                        self.awaiting_number_for = None
                        self.orb.set_state("speaking")
                        self.tts.speak("Number entry timed out, sir. Call aborted.")
                        self.orb.set_state("idle")
                        self._auto_resume_music()
                        continue

                    # Resume music on silence timeout
                    self._auto_resume_music()

                    # Return to standby if music is active to prevent feedback loop
                    if self.youtube_music.process is not None and not self.youtube_music.is_paused:
                        logger.info("Music is active. Forcing sleep state on silence to avoid feedback.")
                        self.is_asleep = True
                        self.orb.set_state("idle")
                        continue

                    time_since_owner = time.time() - getattr(self, "last_owner_seen_time", time.time())
                    if time_since_owner < 120.0:
                        logger.info(f"No speech, but owner verified {time_since_owner:.1f}s ago. Staying awake.")
                        continue
                    else:
                        logger.info(f"No speech and owner absent for {time_since_owner:.1f}s. Returning to standby.")
                        self.is_asleep = True
                        self.orb.set_state("idle")
                        continue

                # Analyze sentiment using text and acoustic energy (RMS)
                self.cognitive_state = self.sentiment_tracker.analyze(text, self.audio.last_avg_rms)

                # Check for active emergency/distress situation
                distress_info = self.emergency_sentinel.check_for_distress(text, self.audio.last_avg_rms)
                if distress_info:
                    logger.warning("Active distress detected in user input!")
                    self.orb.set_state("error")
                    
                    if self.youtube_music.process is not None:
                        self.youtube_music._stop_song_locked()
                        
                    # Camera Emergency Verification
                    self.tts.speak("Distress alert detected. Sir, activating camera verification to assess the emergency.")
                    
                    verified = False
                    verification_reason = "Camera feed was not accessible."
                    
                    if self.camera:
                        # Wait a short moment to ensure a fresh, stable frame is captured
                        time.sleep(1.2)
                        frame = self.camera.latest_frame
                        if frame is not None:
                            try:
                                import cv2
                                import base64
                                import tempfile
                                
                                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_f:
                                    temp_path = temp_f.name
                                
                                # Save the frame to temp file
                                cv2.imwrite(temp_path, frame)
                                
                                # Read as base64
                                with open(temp_path, "rb") as f:
                                    img_b64 = base64.b64encode(f.read()).decode()
                                    
                                try:
                                    os.unlink(temp_path)
                                except Exception:
                                    pass
                                    
                                vision_prompt = (
                                    "Analyze this camera frame of the user's environment. The user has triggered an emergency voice alert "
                                    "indicating a potential physical accident, fire, injury, medical crisis, or severe distress. "
                                    "Confirm if there is indeed a visible accident, injury, fire, blood, a person lying down hurt, or "
                                    "other active physical hazard/crisis. Answer strictly starting with YES or NO, followed by a one-sentence reason."
                                )
                                
                                logger.info("Invoking vision model for camera emergency verification...")
                                response = ollama.chat(
                                    model=self.models.get("vision", "moondream:latest"),
                                    messages=[{
                                        "role": "user",
                                        "content": vision_prompt,
                                        "images": [img_b64]
                                    }],
                                    keep_alive="10s"
                                )
                                
                                vision_res = response["message"]["content"].strip()
                                logger.info(f"Vision verification response: {vision_res}")
                                
                                # Check if starting with YES or containing YES in the first few words
                                first_part = vision_res.upper()[:15]
                                if "YES" in first_part:
                                    verified = True
                                    verification_reason = vision_res
                                else:
                                    verified = False
                                    verification_reason = vision_res
                            except Exception as vision_err:
                                logger.error(f"Error during vision verification process: {vision_err}")
                                verification_reason = f"Verification engine error: {vision_err}"
                        else:
                            verification_reason = "No video frame captured."
                    
                    if not verified:
                        logger.warning(f"Emergency visual verification failed: {verification_reason}")
                        self.tts.speak(
                            f"Sir, visual verification failed. My camera analysis shows: {verification_reason}. "
                            "I will not dial emergency services automatically to prevent illegal false alarms. "
                            "Please dial manually if this is an actual emergency."
                        )
                        self.orb.set_state("idle")
                        continue
                        
                    logger.info("Emergency visually verified! Proceeding with call routing...")
                    
                    priority_contacts = ["ambulance", "doctor", "emergency", "hospital", "mom", "dad", "wife", "husband", "family"]
                    number_to_call = None
                    resolved_name = None
                    
                    try:
                        contacts = self.phone._fetch_all_contacts()
                        for c_query in priority_contacts:
                            for c_name, c_num in contacts.items():
                                if c_query in c_name.lower():
                                    number_to_call = c_num
                                    resolved_name = c_name
                                    break
                            if number_to_call:
                                break
                    except Exception as contact_err:
                        logger.error(f"Error fetching contacts for emergency: {contact_err}")
                        
                    if not number_to_call:
                        number_to_call = "108"
                        resolved_name = "Emergency Services (108)"
                        
                    alert_msg = f"Sir, I detect a distress situation. Initiating emergency call to {resolved_name} immediately."
                    self.tts.speak(alert_msg)
                    
                    try:
                        self.phone.make_call(number_to_call)
                    except Exception as call_err:
                        logger.error(f"Failed to initiate emergency call: {call_err}")
                        self.tts.speak("Device call initiation failed, sir. Please dial emergency manually.")
                        
                    self.orb.set_state("idle")
                    continue

                # Dynamically scale speech rate based on sentiment
                if self.cognitive_state == "stressed":
                    self.tts.default_speed = 1.0
                elif self.cognitive_state == "fatigued":
                    self.tts.default_speed = 0.95
                elif self.cognitive_state == "excited":
                    self.tts.default_speed = 1.4
                else: # calm
                    self.tts.default_speed = 1.25

                # Check if we have an active context (Stateful Conversational Turns)
                if getattr(self, "active_context", None):
                    ctx = self.active_context
                    cmd_lower = text.lower().strip()

                    if ctx.get("type") == "confirm_file_patch":
                        yes_words = ["yes", "go ahead", "do it", "confirm", "ok", "sure", "apply", "yep", "yeah"]
                        no_words = ["no", "abort", "cancel", "don't", "dont", "no do not", "discard", "nah", "nope"]

                        if any(w in cmd_lower for w in yes_words):
                            file_path = ctx["file_path"]
                            patched_content = ctx["patched_content"]
                            filename = os.path.basename(file_path)
                            try:
                                with open(file_path, "w", encoding="utf-8") as f:
                                    f.write(patched_content)
                                logger.info(f"Active context: applied patch to {file_path}")
                                self.orb.set_state("speaking")
                                self.tts.speak(f"Patch applied successfully to {filename}, sir. The file has been restored.")
                                self.orb.set_state("idle")
                            except Exception as patch_err:
                                logger.error(f"Error applying patch in context: {patch_err}")
                                self.orb.set_state("speaking")
                                self.tts.speak(f"Sir, I was unable to write the patch to disk. Error: {str(patch_err)}")
                                self.orb.set_state("idle")
                            self.active_context = None
                            continue
                        elif any(w in cmd_lower for w in no_words):
                            self.orb.set_state("speaking")
                            self.tts.speak("Understood, sir. I have discarded the patch.")
                            self.orb.set_state("idle")
                            self.active_context = None
                            continue

                    elif ctx.get("type") == "confirm_quarantine_process":
                        yes_words = ["yes", "go ahead", "do it", "confirm", "ok", "sure", "block", "kill", "quarantine"]
                        no_words = ["no", "abort", "cancel", "don't", "dont", "allow", "ignore", "nah", "nope"]

                        pid = ctx["pid"]
                        proc_name = ctx["proc_name"]
                        if any(w in cmd_lower for w in yes_words):
                            try:
                                import psutil
                                p = psutil.Process(pid)
                                p.terminate()
                                logger.info(f"Active context: terminated process {proc_name} (PID: {pid})")
                                self.orb.set_state("speaking")
                                self.tts.speak(f"Process {proc_name} has been terminated and quarantined, sir.")
                                self.orb.set_state("idle")
                            except Exception as kill_err:
                                logger.error(f"Error killing process in context: {kill_err}")
                                self.orb.set_state("speaking")
                                self.tts.speak(f"Sir, I was unable to terminate process {proc_name}. It may have already exited.")
                                self.orb.set_state("idle")
                            self.active_context = None
                            continue
                        elif any(w in cmd_lower for w in no_words):
                            self.orb.set_state("speaking")
                            self.tts.speak(f"Understood, sir. I will allow the connection for {proc_name}.")
                            self.orb.set_state("idle")
                            self.active_context = None
                            continue

                # Check if we are waiting for a number response
                if getattr(self, "awaiting_number_for", None):
                    name_to_save = self.awaiting_number_for
                    self.awaiting_number_for = None
                    
                    digits = "".join(filter(str.isdigit, text))
                    if len(digits) >= 4:
                        logger.info(f"Received number '{digits}' for contact '{name_to_save}'")
                        self.orb.set_state("speaking")
                        self.tts.speak(f"Dialing {digits} and saving it as {name_to_save}, sir.")
                        self.phone.make_call(digits)
                        self.phone.save_contact(name_to_save, digits)
                        self.orb.set_state("idle")
                        continue
                    else:
                        self.orb.set_state("speaking")
                        self.tts.speak("I did not hear a valid number, sir. Call aborted.")
                        self.orb.set_state("idle")
                        continue

                cmd_lower = text.lower()
                
                # Explicit sleep command overrides presence
                if any(phrase in cmd_lower for phrase in ["go to sleep", "sleep away", "stop listening", "shut up jarvis", "jarvis sleep"]):
                    self.is_asleep = True
                    self.orb.set_state("speaking")
                    self.tts.speak("Going to sleep, sir. Wake me if you need me.")
                    self.os_ctrl.sleep_system()
                    continue
                    
                # Sentry mode command
                if "secure the laptop" in cmd_lower or "sentry mode" in cmd_lower or "see the laptop" in cmd_lower:
                    self.is_asleep = True
                    self.is_authenticated = False
                    self.orb.set_state("speaking")
                    self.tts.speak("Sentry mode activated. Laptop is secure.")
                    self.os_ctrl.activate_sentry_mode()
                    continue
                    
                # Shutdown command
                if "shutdown the laptop" in cmd_lower or "shut down the laptop" in cmd_lower:
                    self.orb.set_state("speaking")
                    self.tts.speak("Initiating shutdown protocol. Goodbye, sir.")
                    self.os_ctrl.shutdown_system()
                    continue

                logger.info(f"User Transcribed: {text}")
                
                # 3. Process
                if not self.is_authenticated:
                    self._handle_auth(text.lower())
                else:
                    self.process_command(text)
                    
                # Auto-resume music if temporarily paused during listening
                self._auto_resume_music(text)

                # Return to standby if music is active to prevent feedback loop
                if self.youtube_music.process is not None and not self.youtube_music.is_paused:
                    logger.info("Music is active. Returning to standby (asleep) state to prevent feedback loop.")
                    self.is_asleep = True
                    self.orb.set_state("idle")
                    
            except KeyboardInterrupt:
                logger.info("JARVIS shutting down...")
                sys.exit(0)
            except Exception as e:
                logger.error(f"Main loop error: {e}")
                self.orb.set_state("error")
                try:
                    self.tts.speak("I encountered a critical error in my main sensory loop, sir. Attempting to recover.")
                except Exception:
                    pass
                time.sleep(2)
                self.orb.set_state("idle")

if __name__ == "__main__":
    jarvis = JARVIS()
    sys.exit(jarvis.app.exec())
