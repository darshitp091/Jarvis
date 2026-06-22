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
if platform.system() == "Windows":
    import site
    for _p_dir in site.getsitepackages():
        _nv = os.path.join(_p_dir, "nvidia")
        if os.path.exists(_nv):
            for _sub in ["cublas", "cudnn", "cuda_runtime", "cuda_nvrtc"]:
                _bin = os.path.join(_nv, _sub, "bin")
                if os.path.exists(_bin):
                    try:
                        os.add_dll_directory(_bin)
                        _p(f"DLL PATH: Added {_bin}")
                    except Exception as _err:
                        _p(f"DLL PATH ERR: {_err} for {_bin}")

from loguru import logger; _p("DBG: loguru ok")
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
from auth.local_auth import LocalAuth; _p("DBG: local_auth ok")
from domains.medical import MedicalDomain; _p("DBG: medical ok")
from domains.business import BusinessDomain; _p("DBG: business ok")
from domains.finance import FinanceDomain; _p("DBG: finance ok")
from domains.security import SecurityDomain; _p("DBG: security ok")
from domains.development import DevelopmentDomain; _p("DBG: development ok")
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

class JARVIS:
    """The master JARVIS integration"""

    def __init__(self):
        with open("./config/settings.yaml") as f:
            self.config = yaml.safe_load(f)
        with open("./config/prompts.yaml") as f:
            self.prompts = yaml.safe_load(f)

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
            voices_path=self.config["tts"].get("voices_json", "voices-v1.0.bin")
        )
        _p("INIT: WakeWordDetector"); self.wake = WakeWordDetector()
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
        _p("INIT: MarketAnalyzer"); self.market_analyzer = MarketAnalyzer()
        _p("INIT: GestureController"); self.gesture_ctrl = GestureController(self.camera, canvas=self.canvas)
        self.gesture_ctrl.start()

        # Domains
        _p("INIT: Domains")
        self.domains = {
            "medical": MedicalDomain(),
            "business": BusinessDomain(),
            "finance": FinanceDomain(),
            "security": SecurityDomain(),
            "development": DevelopmentDomain()
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

        # Link OSControl to Orb for signals
        self.os_ctrl.orb = self.orb

        # Connect PyQt6 slots for custom overlays
        self.orb.eyecare_toggle_signal.connect(self._execute_eyecare_toggle)
        self.orb.ruler_toggle_signal.connect(self._execute_ruler_toggle)
        self.orb.snipping_tool_signal.connect(self._execute_snipping_tool)

        self.eyecare_overlay = None
        self.screen_ruler = None
        self.snipping_overlay = None
        threading.Thread(target=self._phone_monitor, daemon=True).start()
        threading.Thread(target=self._interruption_monitor, daemon=True).start()

        # Proactive alerting

        self.alert_queue = []
        self.alert_lock = threading.Lock()
        _p("INIT: ProactiveMonitor")
        self.proactive_monitor = ProactiveMonitor(camera_engine=self.camera, alert_callback=self.on_proactive_alert)
        self.proactive_monitor.start()

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
        if self.is_authenticated and self.orb.state == "idle":
            logger.info(f"Speaking proactive alert: {text}")
            self.orb.set_state("speaking")
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
        self.tts.speak(f"Sir, I have intercepted the call from {incoming_number} and informed them you are currently busy.")

    def _interruption_monitor(self):
        """Continuously monitors microphone when JARVIS is speaking to detect user interruption."""
        import sounddevice as sd
        import numpy as np
        
        sample_rate = 16000
        block_size = int(0.15 * sample_rate)  # 150ms block
        
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
                        if rms > max(interruption_threshold, 25000.0):
                            logger.warning(f"Voice interruption detected! RMS={rms:.1f} > threshold={interruption_threshold:.1f}")
                            self.tts.stop_speech()
                else:
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
            self.tts.speak("JARVIS online. All systems operational. Waiting on your command, sir.")

    def _generate_response(self, text: str, domain: str = "general") -> str:
        memories = self.brain.format_memories_for_prompt(text)
        
        if domain in self.domains:
            # Route to expert
            return self.domains[domain].answer(text, memories)
            
        system_key = domain if domain in self.prompts["system_prompts"] else "main"
        system = self.prompts["system_prompts"][system_key] + memories

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

    def process_command(self, text: str):
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
                        elif action in ["volume_up", "volume_down"]:
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
                    response = self.productivity.pptx_helper(title, "Generated by JARVIS", slides_content)
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
                    self._flush_alerts()
                    # 1. Wait for wake word
                    if not self.wake.listen_for_wake_word():
                        continue
                        
                    # Play wakeup response immediately so user knows it's listening
                    self.orb.set_state("speaking")
                    self.tts.speak("Yes, sir?")
                    self.is_asleep = False
                
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
                if any(phrase in cmd_lower for phrase in ["go to sleep", "sleep away", "stop listening", "shut up jarvis"]):
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
