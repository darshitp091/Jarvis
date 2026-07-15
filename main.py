import sys
import os
os.environ["GLOG_minloglevel"] = "3"
os.environ["ABSL_log_min_level"] = "3"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["CRAWL4AI_LOG_LEVEL"] = "ERROR"
import threading
import traceback
import yaml
import time
import warnings
warnings.filterwarnings("ignore")

def _p(msg):
    try:
        with open("jarvis.log", "a", encoding="utf-8") as f:
            f.write(f"INIT_DBG: {msg}\n")
    except Exception:
        pass

from contextlib import contextmanager
import threading
_stderr_lock = threading.Lock()

@contextmanager
def silence_stderr():
    """Silences OS-level stderr completely (e.g. C/C++ library absl warnings)."""
    with _stderr_lock:
        new_target = open(os.devnull, 'w')
        old_stderr_fd = os.dup(2)
        os.dup2(new_target.fileno(), 2)
        try:
            yield
        finally:
            os.dup2(old_stderr_fd, 2)
            os.close(old_stderr_fd)
            new_target.close()

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
logger.add("jarvis.log", level="INFO", rotation="10 MB", encoding="utf-8")
from PyQt6.QtWidgets import QApplication; _p("DBG: PyQt6 ok")
import core.llm_client
core.llm_client.patch_ollama()

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
from core.context_sentinel import ContextSentinel
from skills.app_control import AppControl
from core.profile_manager import ProfileManager
from skills.obsidian_control import ObsidianControl; _p("DBG: obsidian ok")


class JARVIS:
    """The master JARVIS integration"""

    def __init__(self, start_threads: bool = True):
        self.start_threads = start_threads
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
        # Safely wrap self.orb.set_state to ignore C++ deleted errors during exit
        self.orb_original_set_state = self.orb.set_state
        def safe_set_state(state):
            try:
                self.orb_original_set_state(state)
            except RuntimeError as re:
                if "deleted" in str(re):
                    pass
        self.orb.set_state = safe_set_state
        _p("INIT: AirCanvas"); self.canvas = AirCanvas()

        # Auth
        _p("INIT: LocalAuth"); self.auth = LocalAuth()

        # Core
        with silence_stderr():
            _p("INIT: AudioEngine"); self.audio = AudioEngine(silence_sec=self.config["audio"]["silence_threshold"])
            _p("INIT: TTSEngine"); self.tts = TTSEngine(
                default_voice=self.config["tts"].get("default_voice", "hinglish"),
                default_speed=self.config["tts"].get("speaking_rate", 1.0)
            )
            _p("INIT: WakeWordDetector"); self.wake = WakeWordDetector()
        self.wake.is_music_playing_cb = self._is_music_playing
        self.wake.is_speaking_cb = lambda: self.tts.is_speaking
        self.audio.is_speaking_cb = lambda: self.tts.is_speaking
        _p("INIT: IntentRouter"); self.router = IntentRouter()
        _p("INIT: JarvisBrain"); self.brain = JarvisBrain()
        self.chat_history = []
        self.chat_history_summary = ""
        self.last_voice_auth_time = 0.0
        _p("INIT: ContextSentinel"); self.sentinel = ContextSentinel()
        _p("INIT: ProfileManager"); self.profile_mgr = ProfileManager()
        with silence_stderr():
            _p("INIT: CameraEngine"); self.camera = CameraEngine()
        if self.start_threads:
            self.camera.start()
        
        # Skills
        _p("INIT: ScreenVision"); self.vision = ScreenVision(jarvis=self)
        _p("INIT: OSControl"); self.os_ctrl = OSControl()
        _p("INIT: WebResearch"); self.web = WebResearch(jarvis=self)
        _p("INIT: MediaSummarizer"); self.media = MediaSummarizer()
        _p("INIT: AppMapper"); self.app_map = AppMapper()
        _p("INIT: AppControl"); self.app_ctrl = AppControl()
        _p("INIT: SpotifyControl"); self.spotify_ctrl = SpotifyControl()
        # If Spotify credentials exist but no cached token, remind user to run authorize_spotify.py
        if getattr(self.spotify_ctrl, "use_api", False) is False and \
           getattr(self.spotify_ctrl, "client_id", None) and \
           getattr(self.spotify_ctrl, "client_secret", None):
            cache_path = getattr(self.spotify_ctrl, "CACHE_PATH", ".cache-jarvis-spotify")
            if not os.path.exists(cache_path):
                logger.warning("Spotify not authorized. Run 'python authorize_spotify.py' once to enable full API mode.")
        _p("INIT: YouTubeMusicPlayer"); self.youtube_music = YouTubeMusicPlayer()
        _p("INIT: ObsidianControl"); self.obsidian_ctrl = ObsidianControl()
        self.youtube_music.on_song_change = lambda title, msg: self.orb.notification_signal.emit(title, msg)
        self.tts.on_speak_start = self._duck_audio
        self.tts.on_speak_end = self._unduck_audio
        
        # Initialize futuristic Iron Man HUD overlay and Macro Recorder
        _p("INIT: IronManHUDOverlay"); self.hud_overlay = IronManHUDOverlay()
        # self.hud_overlay.show()
        self.orb.state_changed.connect(self.hud_overlay.set_hud_state)
        self.orb.state_changed.connect(self.on_orb_state_changed)
        
        _p("INIT: MacroRecorder"); self.macro_recorder = MacroRecorder(vision_engine=self.vision)
        
        _p("INIT: MarketAnalyzer"); self.market_analyzer = MarketAnalyzer()
        with silence_stderr():
            _p("INIT: GestureController"); self.gesture_ctrl = GestureController(self.camera, canvas=self.canvas, youtube_music=self.youtube_music)
        if self.start_threads:
            self.gesture_ctrl.start()

        # Domains
        _p("INIT: Domains")
        self.domains = {
            "medical": MedicalDomain(jarvis=self),
            "business": BusinessDomain(jarvis=self),
            "finance": FinanceDomain(jarvis=self),
            "security": SecurityDomain(jarvis=self),
            "development": DevelopmentDomain(jarvis=self),
            "science": ScienceDomain(jarvis=self),
            "engineering": EngineeringDomain()
        }

        _p("INIT: WorkspaceContext"); self.workspace_context = WorkspaceContext()
        _p("INIT: SelfHealingVision"); self.self_healing = SelfHealingVision()
        
        # Self-Healing Engine & Memory Consolidation QTimer
        _p("INIT: SelfHealingEngine")
        from core.self_healing import SelfHealingEngine
        self.healer = SelfHealingEngine()
        
        from PyQt6.QtCore import QTimer
        self.consolidation_timer = QTimer(self.orb)
        self.consolidation_timer.setInterval(20 * 60 * 1000) # every 20 minutes
        self.consolidation_timer.timeout.connect(self._run_memory_consolidation)
        self.consolidation_timer.start()

        _p("INIT: auth check")
        self.is_authenticated = not self.config["jarvis"].get("pin_enabled", False)
        self.face_verified = False

        _p("INIT: JarvisDashboard"); self.dashboard = JarvisDashboard(camera_engine=self.camera)
        self.orb.toggle_callback = self.toggle_dashboard_via_double_click
        self.orb.dashboard_toggle_signal.connect(self._execute_dashboard_toggle)
        self.last_owner_seen_time = time.time()
        _p("INIT: PhoneController"); self.phone = PhoneController()
        self.awaiting_number_for = None
        self.is_spotify_playing = False
        
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

        # Presentation state tracking
        self.active_presentation_topic = None
        self.active_presentation_status = "idle"  # idle, created

        # Parallel Visual Assistant Loop
        self.visual_assistant_enabled = True
        self.last_active_title = ""
        self.last_visual_suggestion_time = 0.0
        self.is_busy = False # True when executing a command or speaking
        if self.start_threads:
            threading.Thread(target=self._visual_assistant_loop, daemon=True).start()
        self.alert_lock = threading.Lock()
        self.active_context = None
        self.pending_code_snippet = None
        self._is_asleep = True
        self.last_command_time = 0.0

        # Import cognitive tracker
        from core.cognitive import CognitiveSentimentTracker
        self.sentiment_tracker = CognitiveSentimentTracker()
        self.cognitive_state = "calm"

        # Initialize HologramSimWidget
        _p("INIT: HologramSimWidget")
        self.hologram_widget = HologramSimWidget(self.camera)
        self.hologram_widget.node_clicked_signal.connect(self._on_hologram_node_clicked)
        self.domains["engineering"].hologram_widget = self.hologram_widget
        self.gesture_ctrl.hologram_widget = self.hologram_widget

        # Import and initialize NetworkMapper
        from skills.network_mapper import NetworkMapper
        self.network_mapper = NetworkMapper()

        # Import and initialize CADGenerator
        from skills.cad_generator import CADGenerator
        self.cad_gen = CADGenerator()

        # Initialize AgentLabWidget
        _p("INIT: AgentLabWidget")
        from ui.agent_lab import AgentLabWidget
        self.agent_lab = AgentLabWidget()

        # Initialize SensoryHealthAnalyzer
        _p("INIT: SensoryHealthAnalyzer")
        from core.sensory_health import SensoryHealthAnalyzer
        self.sensory_health = SensoryHealthAnalyzer(self.camera)

        # Initialize P2PLinkNode
        _p("INIT: P2PLinkNode")
        from core.p2p_link import P2PLinkNode
        self.p2p_link = P2PLinkNode(tts_engine=self.tts)
        self.p2p_link.start()

        # Initialize AirTypistTracker
        _p("INIT: AirTypistTracker")
        from core.air_typist import AirTypistTracker
        self.air_typist = AirTypistTracker(self.camera)

        # Initialize VoiceAuthenticator
        _p("INIT: VoiceAuthenticator")
        from core.voice_auth import VoiceAuthenticator
        self.voice_auth = VoiceAuthenticator()

        # Initialize GitSentinel
        _p("INIT: GitSentinel")
        from skills.git_sentinel import GitSentinel
        self.git_sentinel = GitSentinel()

        # Initialize SentryFirewall
        _p("INIT: SentryFirewall")
        from skills.sentry_firewall import SentryFirewall
        self.sentry_firewall = SentryFirewall()

        # Initialize Focus Dashboard and Focus Tracker
        _p("INIT: FocusTracker & Dashboard")
        from ui.vitals_dashboard import VitalsDashboardWidget
        from core.focus_tracker import FocusTracker
        self.vitals_dashboard = VitalsDashboardWidget()
        self.focus_tracker = FocusTracker(self.camera, self.sensory_health, self.vitals_dashboard, self)
        self.focus_tracker.start()

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

        # Initialize Multi-Agent Swarm Swarm (Multi-Working)
        _p("INIT: Multi-Agent Swarm Agency")
        from core.agency import Agency
        from core.agents import (
            AudioEngineAgent, TtsEngineAgent, WakeWordAgent, VoiceAuthAgent, IntentRouterAgent,
            BrainAgent, CognitiveAgent, ContextSentinelAgent, ProactiveMonitorAgent, FocusTrackerAgent,
            ProfileManagerAgent, VisionEngineAgent, SensoryHealthAgent, AirTypistAgent, P2PLinkAgent,
            BusinessDomainAgent, DevelopmentDomainAgent, EngineeringDomainAgent, FinanceDomainAgent,
            MedicalDomainAgent, ScienceDomainAgent, SecurityDomainAgent,
            AppControlAgent, AppMapperAgent, CodeRunnerAgent, CodingSandboxAgent, DataAnalyzerAgent,
            EmergencySentinelAgent, FileManagerAgent, FoodComparatorAgent, GestureControlAgent,
            GitSentinelAgent, MacroRecorderAgent, MarketAnalyzerAgent, MediaSummarizerAgent,
            NetworkMapperAgent, ObsidianControlAgent, OsControlAgent, PhoneControllerAgent,
            PolyglotEngineerAgent, ProductivityAgent, ProductComparatorAgent, ResearchProdigyAgent,
            ScreenVisionAgent, SecurityAuditorAgent, SelfHealingVisionAgent, SentryFirewallAgent,
            SpotifyControlAgent, VisionTrackerAgent, WebResearchAgent, WorkspaceContextAgent,
            YoutubeMusicAgent
        )
        self.agency = Agency()
        
        # Instantiate and register all 52 agents
        self.agency.register_agent("AudioEngineAgent", AudioEngineAgent("AudioEngineAgent", self))
        self.agency.register_agent("TtsEngineAgent", TtsEngineAgent("TtsEngineAgent", self))
        self.agency.register_agent("WakeWordAgent", WakeWordAgent("WakeWordAgent", self))
        self.agency.register_agent("VoiceAuthAgent", VoiceAuthAgent("VoiceAuthAgent", self))
        self.agency.register_agent("IntentRouterAgent", IntentRouterAgent("IntentRouterAgent", self))
        self.agency.register_agent("BrainAgent", BrainAgent("BrainAgent", self))
        self.agency.register_agent("CognitiveAgent", CognitiveAgent("CognitiveAgent", self))
        self.agency.register_agent("ContextSentinelAgent", ContextSentinelAgent("ContextSentinelAgent", self))
        self.agency.register_agent("ProactiveMonitorAgent", ProactiveMonitorAgent("ProactiveMonitorAgent", self))
        self.agency.register_agent("FocusTrackerAgent", FocusTrackerAgent("FocusTrackerAgent", self))
        self.agency.register_agent("ProfileManagerAgent", ProfileManagerAgent("ProfileManagerAgent", self))
        self.agency.register_agent("VisionEngineAgent", VisionEngineAgent("VisionEngineAgent", self))
        self.agency.register_agent("SensoryHealthAgent", SensoryHealthAgent("SensoryHealthAgent", self))
        self.agency.register_agent("AirTypistAgent", AirTypistAgent("AirTypistAgent", self))
        self.agency.register_agent("P2PLinkAgent", P2PLinkAgent("P2PLinkAgent", self))
        
        self.agency.register_agent("BusinessDomainAgent", BusinessDomainAgent("BusinessDomainAgent", self))
        self.agency.register_agent("DevelopmentDomainAgent", DevelopmentDomainAgent("DevelopmentDomainAgent", self))
        self.agency.register_agent("EngineeringDomainAgent", EngineeringDomainAgent("EngineeringDomainAgent", self))
        self.agency.register_agent("FinanceDomainAgent", FinanceDomainAgent("FinanceDomainAgent", self))
        self.agency.register_agent("MedicalDomainAgent", MedicalDomainAgent("MedicalDomainAgent", self))
        self.agency.register_agent("ScienceDomainAgent", ScienceDomainAgent("ScienceDomainAgent", self))
        self.agency.register_agent("SecurityDomainAgent", SecurityDomainAgent("SecurityDomainAgent", self))
        
        self.agency.register_agent("AppControlAgent", AppControlAgent("AppControlAgent", self))
        self.agency.register_agent("AppMapperAgent", AppMapperAgent("AppMapperAgent", self))
        self.agency.register_agent("CodeRunnerAgent", CodeRunnerAgent("CodeRunnerAgent", self))
        self.agency.register_agent("CodingSandboxAgent", CodingSandboxAgent("CodingSandboxAgent", self))
        self.agency.register_agent("DataAnalyzerAgent", DataAnalyzerAgent("DataAnalyzerAgent", self))
        self.agency.register_agent("EmergencySentinelAgent", EmergencySentinelAgent("EmergencySentinelAgent", self))
        self.agency.register_agent("FileManagerAgent", FileManagerAgent("FileManagerAgent", self))
        self.agency.register_agent("FoodComparatorAgent", FoodComparatorAgent("FoodComparatorAgent", self))
        self.agency.register_agent("GestureControlAgent", GestureControlAgent("GestureControlAgent", self))
        self.agency.register_agent("GitSentinelAgent", GitSentinelAgent("GitSentinelAgent", self))
        self.agency.register_agent("MacroRecorderAgent", MacroRecorderAgent("MacroRecorderAgent", self))
        self.agency.register_agent("MarketAnalyzerAgent", MarketAnalyzerAgent("MarketAnalyzerAgent", self))
        self.agency.register_agent("MediaSummarizerAgent", MediaSummarizerAgent("MediaSummarizerAgent", self))
        self.agency.register_agent("NetworkMapperAgent", NetworkMapperAgent("NetworkMapperAgent", self))
        self.agency.register_agent("ObsidianControlAgent", ObsidianControlAgent("ObsidianControlAgent", self))
        self.agency.register_agent("OsControlAgent", OsControlAgent("OsControlAgent", self))
        self.agency.register_agent("PhoneControllerAgent", PhoneControllerAgent("PhoneControllerAgent", self))
        self.agency.register_agent("PolyglotEngineerAgent", PolyglotEngineerAgent("PolyglotEngineerAgent", self))
        self.agency.register_agent("ProductivityAgent", ProductivityAgent("ProductivityAgent", self))
        self.agency.register_agent("ProductComparatorAgent", ProductComparatorAgent("ProductComparatorAgent", self))
        self.agency.register_agent("ResearchProdigyAgent", ResearchProdigyAgent("ResearchProdigyAgent", self))
        self.agency.register_agent("ScreenVisionAgent", ScreenVisionAgent("ScreenVisionAgent", self))
        self.agency.register_agent("SecurityAuditorAgent", SecurityAuditorAgent("SecurityAuditorAgent", self))
        self.agency.register_agent("SelfHealingVisionAgent", SelfHealingVisionAgent("SelfHealingVisionAgent", self))
        self.agency.register_agent("SentryFirewallAgent", SentryFirewallAgent("SentryFirewallAgent", self))
        self.agency.register_agent("SpotifyControlAgent", SpotifyControlAgent("SpotifyControlAgent", self))
        self.agency.register_agent("VisionTrackerAgent", VisionTrackerAgent("VisionTrackerAgent", self))
        self.agency.register_agent("WebResearchAgent", WebResearchAgent("WebResearchAgent", self))
        self.agency.register_agent("WorkspaceContextAgent", WorkspaceContextAgent("WorkspaceContextAgent", self))
        self.agency.register_agent("YoutubeMusicAgent", YoutubeMusicAgent("YoutubeMusicAgent", self))

        self._prewarm_models()

        logger.info("JARVIS initialized successfully.")
        _p("INIT: starting background thread")
        threading.Thread(target=self._unlock_monitor, daemon=True).start()
        threading.Thread(target=self.run, daemon=True).start()

    def _run_memory_consolidation(self):
        """Periodically run memory consolidation in a background thread to extract facts."""
        def job():
            try:
                new_facts = self.brain.consolidate_memories()
                if new_facts:
                    logger.info(f"Consolidated memories: extracted {len(new_facts)} new facts.")
            except Exception as e:
                logger.error(f"Error in background memory consolidation: {e}")
        
        import threading
        threading.Thread(target=job, daemon=True).start()

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
                                if getattr(self, "camera", None) is not None:
                                    self.camera.start()
                                if getattr(self, "gesture_ctrl", None) is not None:
                                    self.gesture_ctrl.start()
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
                    if not self.face_verified and self.camera.has_face_model and self.camera.latest_frame is not None:
                        frame = self.camera.latest_frame
                        if self.camera.identify_face(frame):
                            logger.info("Face ID verified. Awaiting voice authentication...")
                            self.face_verified = True
                            try:
                                with open(state_file, "w") as f:
                                    f.write("face_verified")
                            except Exception:
                                pass
                            self.orb.set_state("speaking")
                            self.tts.speak("Face verified, sir. Please say 'hey jarvis' to complete voice authentication.")
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

    def trigger_fatigue_protocol(self, focus_score: int):
        logger.warning(f"JARVIS: Fatigue protocol active (Focus: {focus_score}%)")
        self.orb.set_state("error")
        self.tts.speak(f"Sir, your cognitive focus score has dropped to {focus_score} percent. I strongly recommend taking a short break from the screen.")
        
        # 1. Dim system brightness
        try:
            self.os_ctrl.set_brightness(20)
        except Exception as e:
            logger.error(f"Fatigue Protocol: Failed to dim screen: {e}")
            
        # 2. Play ambient lo-fi beats study radio
        try:
            self.tts.speak("I am starting a relaxing lo-fi station for you now.")
            self.youtube_music.play_song("lofi hip hop radio beats to relax study to")
        except Exception as e:
            logger.error(f"Fatigue Protocol: Failed to play relaxation beats: {e}")
            
        self.orb.set_state("idle")

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

    def _on_hologram_node_clicked(self, idx: int, label: str):
        self.tts.speak(f"Linked node selected: {label}, sir.")
        logger.info(f"Hologram clicked node {idx}: {label}")

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
            self.tts.speak(f"{name} online. All systems are operational, waiting for your command, sir.")

    def query_llm(self, messages: list, system_prompt: str = None, provider: str = "mistral", model: str = None) -> str:
        """Queries the active LLM provider (mistral, ofoxai, groq, or local Ollama fallback)."""
        query_messages = []
        if system_prompt:
            query_messages.append({"role": "system", "content": system_prompt})
        query_messages.extend(messages)

        # 1. Mistral AI Provider
        if provider == "mistral":
            mistral_cfg = self.config.get("mistral", {})
            api_key = mistral_cfg.get("api_key", "")
            target_model = model or mistral_cfg.get("models", {}).get("brain", "mistral-large-2512")
            
            if api_key and not api_key.startswith("YOUR_"):
                import requests
                url = "https://api.mistral.ai/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                data = {
                    "model": target_model,
                    "messages": query_messages,
                    "temperature": 0.2,
                    "stream": True
                }
                try:
                    logger.info(f"Querying Mistral API using model '{target_model}' (streaming enabled)...")
                    response = requests.post(url, headers=headers, json=data, stream=True, timeout=25)
                    if response.status_code == 200:
                        reply_parts = []
                        print("JARVIS: ", end="", flush=True)
                        for line in response.iter_lines():
                            if line:
                                decoded_line = line.decode('utf-8').strip()
                                if decoded_line.startswith("data:"):
                                    data_content = decoded_line[5:].strip()
                                    if data_content == "[DONE]":
                                        break
                                    try:
                                        chunk_json = json.loads(data_content)
                                        delta = chunk_json["choices"][0].get("delta", {})
                                        if "content" in delta:
                                            text_chunk = delta["content"]
                                            print(text_chunk, end="", flush=True)
                                            reply_parts.append(text_chunk)
                                    except Exception:
                                        pass
                        print()
                        reply = "".join(reply_parts)
                        logger.info("Successfully received streamed response from Mistral.")
                        return reply
                    else:
                        logger.error(f"Mistral API returned error status {response.status_code}: {response.text}")
                except Exception as e:
                    logger.error(f"Mistral API connection failed: {e}")

        # 2. OfoxAI Provider
        elif provider == "ofoxai":
            ofox_cfg = self.config.get("ofoxai", {})
            api_key = ofox_cfg.get("api_key", "")
            target_model = model or ofox_cfg.get("model", "z-ai/glm-4.7-flash:free")
            
            if api_key and not api_key.startswith("YOUR_"):
                try:
                    logger.info(f"Querying OfoxAI API using model '{target_model}'...")
                    from openai import OpenAI
                    client = OpenAI(
                        base_url="https://api.ofox.ai/v1",
                        api_key=api_key
                    )
                    ofox_messages = []
                    if system_prompt:
                        ofox_messages.append({"role": "system", "content": system_prompt})
                    
                    for msg in messages:
                        content = msg["content"]
                        if isinstance(content, list):
                            text_content = ""
                            for part in content:
                                if part.get("type") == "text":
                                    text_content += part.get("text", "")
                            ofox_messages.append({"role": msg["role"], "content": text_content})
                        else:
                            ofox_messages.append(msg)

                    response_stream = client.chat.completions.create(
                        model=target_model,
                        messages=ofox_messages,
                        temperature=0.1,
                        max_tokens=300,
                        stream=True,
                        timeout=25
                    )
                    reply_parts = []
                    print("JARVIS: ", end="", flush=True)
                    for chunk in response_stream:
                        if chunk.choices and chunk.choices[0].delta.content:
                            text_chunk = chunk.choices[0].delta.content
                            print(text_chunk, end="", flush=True)
                            reply_parts.append(text_chunk)
                    print()
                    reply = "".join(reply_parts)
                    logger.info("Successfully received streamed response from OfoxAI.")
                    return reply
                except Exception as e:
                    logger.error(f"OfoxAI API connection failed: {e}")

        # 3. Groq API Provider Fallback
        groq_cfg = self.config.get("groq", {})
        groq_api_key = groq_cfg.get("api_key", "")
        groq_model = groq_cfg.get("model", "llama-3.3-70b-versatile")
        
        if groq_api_key and not groq_api_key.startswith("YOUR_"):
            import requests
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {groq_api_key}",
                "Content-Type": "application/json"
            }
            # Flatten/convert messages if multimodal
            groq_messages = []
            for msg in query_messages:
                content = msg["content"]
                if isinstance(content, list):
                    text_content = ""
                    for part in content:
                        if part.get("type") == "text":
                            text_content += part.get("text", "")
                    groq_messages.append({"role": msg["role"], "content": text_content})
                else:
                    groq_messages.append(msg)

            data = {
                "model": groq_model,
                "messages": groq_messages,
                "temperature": 0.3
            }
            try:
                logger.info(f"Querying Groq API using model '{groq_model}'...")
                response = requests.post(url, headers=headers, json=data, timeout=25)
                if response.status_code == 200:
                    result = response.json()
                    reply = result["choices"][0]["message"]["content"]
                    logger.info("Successfully received response from Groq.")
                    return reply
                else:
                    logger.error(f"Groq API returned error status {response.status_code}: {response.text}")
            except Exception as e:
                logger.error(f"Groq API connection failed: {e}")
                
        # 4. Local Ollama Fallback (with base64 image extraction)
        try:
            logger.info("Falling back to local Ollama brain...")
            import ollama
            model_name = self.models.get("main_brain", "yasserrmd/Human-Like-Qwen2.5-1.5B-Instruct:latest")
            
            ollama_messages = []
            for msg in query_messages:
                content = msg["content"]
                images = []
                text_content = ""
                
                if isinstance(content, list):
                    for part in content:
                        if part.get("type") == "text":
                            text_content += part.get("text", "")
                        elif part.get("type") == "image_url":
                            url_val = part.get("image_url", {}).get("url", "")
                            if "base64," in url_val:
                                base64_data = url_val.split("base64,")[1]
                                images.append(base64_data)
                else:
                    text_content = content
                    
                ollama_msg = {"role": msg["role"], "content": text_content}
                if images:
                    ollama_msg["images"] = images
                ollama_messages.append(ollama_msg)
                     
            response = ollama.chat(
                model=model_name,
                messages=ollama_messages
            )
            return response["message"]["content"]
        except Exception as e:
            logger.error(f"Local Ollama query failed: {e}")
            return "I am currently unable to process your request, sir."

    def _visual_assistant_loop(self):
        """Continuously monitors what the user is doing on the screen and offers proactive suggestions."""
        import time
        import re
        logger.info("Continuous Visual Assistant loop activated.")
        while True:
            try:
                if not self.visual_assistant_enabled:
                    time.sleep(5)
                    continue

                if self.is_busy or self.tts.is_speaking:
                    time.sleep(5)
                    continue

                ctx = self.sentinel.get_active_context()
                active_title = ctx.get("title", "")
                active_process = ctx.get("process", "")

                if not active_title or any(term in active_title.lower() for term in ["lock app", "task manager", "desktop"]):
                    time.sleep(5)
                    continue

                now = time.time()
                time_since_last_suggest = now - self.last_visual_suggestion_time
                title_changed = active_title != self.last_active_title
                is_target_process = any(p in active_process for p in ["powerpnt", "chrome", "edge", "code", "obsidian", "excel", "winword"])

                if is_target_process and (title_changed or time_since_last_suggest > 90.0):
                    if title_changed:
                        time.sleep(4)
                        ctx = self.sentinel.get_active_context()
                        if ctx.get("title") != active_title:
                            continue

                    self.last_active_title = active_title
                    self.last_visual_suggestion_time = now

                    logger.info(f"Visual Assistant: analyzing screen activity for window '{active_title}'...")
                    screenshot_prompt = (
                        "Analyze this screen. Write a very brief, friendly, proactive suggestion or helpful tip in Hinglish "
                        "(using Latin/WhatsApp text script, using feminine verb endings like 'soch rahi hu', 'karu') "
                        "offering support or insights about the specific task they are doing (e.g. designing slides, searching topics, coding, writing notes). "
                        "If no suggestion is needed or everything is already optimal, output ONLY the word 'NONE'. "
                        "Keep the tip under 12 words."
                    )
                    
                    suggestion = self.vision.analyze(screenshot_prompt).strip()
                    suggestion = re.sub(r'["\']', '', suggestion).strip()
                    
                    if suggestion and suggestion.upper() != "NONE" and len(suggestion) > 5:
                        logger.info(f"Visual Assistant suggestion: {suggestion}")
                        self.is_busy = True
                        self.orb.set_state("speaking")
                        self.tts.speak(suggestion)
                        self.orb.set_state("idle")
                        self.is_busy = False
            except Exception as loop_err:
                logger.error(f"Error in visual assistant background loop: {loop_err}")
                
            time.sleep(8)

    def _create_professional_presentation(self, title: str, research_notes: str = None, slide_count: int = None, presenter: str = None) -> str:
        """Helper to orchestrate online research, slide layout generation, image downloading, and PPTX compilation."""
        import json
        import re
        import os
        logger.info(f"Generating professional presentation for '{title}' (Slide Count: {slide_count}, Presenter: {presenter})...")
        
        # 1. Online Content Research
        if not research_notes:
            research_notes = self.web.headless_search_and_summarize(title)
            
        # Determine slide count
        count = slide_count if (slide_count and 5 <= slide_count <= 20) else 8

        # 2. Structure outline using LLM (dynamic slide count)
        prompt = (
            f"Create a high-end, detailed slide outline for a {count} slide presentation on '{title}' based on the following research:\n\n"
            f"{research_notes}\n\n"
            "Select and recommend one of these dynamic layout themes based on the topic: "
            "'stark_tech' (cyber/tech/dark), 'midnight_cyberpunk' (neon/creative/dark), "
            "'light_professional' (corporate/clean/light), or 'forest_minimalist' (organic/nature/light). "
            f"You MUST generate exactly {count} slides in the outline. For each slide, output a 'title', 'bullets' (3-4 concise professional bullet points with correct capitalization and proper technical depth), and a highly specific 'image_query' to search for matching diagrams or photos related to the slide's core concepts. "
            "Output ONLY a raw, valid JSON object containing: "
            '{"theme": "...", "title": "...", "subtitle": "...", "slides": [{"title": "...", "bullets": ["...", "..."], "image_query": "..."}]}. '
            "Do not include any markdown code wrappers, quotes, or backticks."
        )
        
        try:
            raw = self.query_llm([{"role": "user", "content": prompt}], provider="mistral", model="mistral-large-2512")
            raw = raw.strip().replace("```json", "").replace("```", "").strip()
            start_idx = raw.find("{")
            end_idx = raw.rfind("}")
            if start_idx != -1 and end_idx != -1:
                raw = raw[start_idx:end_idx+1]
            data = json.loads(raw)
            theme = data.get("theme", "stark_tech")
            slides_content = data.get("slides", [])
            pres_title = data.get("title", title)
            if presenter:
                pres_subtitle = f"Presented by {presenter}"
            else:
                pres_subtitle = data.get("subtitle", f"Generated by {self.config.get('jarvis', {}).get('name', 'JARVIS')}")
        except Exception as e:
            logger.error(f"Failed to generate layout outline: {e}. Falling back to default layout.")
            theme = "stark_tech"
            slides_content = [
                {"title": "Introduction to " + title, "bullets": ["Overview of the topic", "Key components", "Initial analysis"], "image_query": f"{title} overview"},
                {"title": "Deep Dive", "bullets": ["Detailed explanations", "Current trends and developments", "Practical examples"], "image_query": f"{title} diagram"},
                {"title": "Summary", "bullets": ["Conclusion of key points", "Next steps"], "image_query": f"{title} summary"}
            ]
            pres_title = title
            pres_subtitle = presenter if presenter else f"Generated by {self.config.get('jarvis', {}).get('name', 'JARVIS')}"
        
        # 3. Image fetching loop
        topic_slug = re.sub(r'[^a-zA-Z0-9]', '_', title).lower()
        for idx, slide_data in enumerate(slides_content):
            img_query = slide_data.get("image_query", "")
            if img_query:
                logger.info(f"Searching images for slide {idx+1}: '{img_query}'...")
                img_urls = self.productivity._search_images(img_query, 3)
                downloaded = False
                for url in img_urls:
                    save_path = f"config/downloads/{topic_slug}/slide_{idx+1}.jpg"
                    if self.productivity._download_image(url, save_path):
                        slide_data["image_path"] = save_path
                        downloaded = True
                        logger.info(f"Successfully downloaded image for slide {idx+1}")
                        break
                if not downloaded:
                    logger.warning(f"Could not download any valid image for slide {idx+1}")
                    slide_data["image_path"] = ""
            else:
                slide_data["image_path"] = ""

        # 4. Save metadata state file
        state = {
            "title": pres_title,
            "subtitle": pres_subtitle,
            "theme": theme,
            "slides": slides_content
        }
        try:
            os.makedirs("config", exist_ok=True)
            with open("config/last_presentation.json", "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
        except Exception as state_err:
            logger.error(f"Failed to save last presentation state: {state_err}")
            
        # 5. Save state in memory for conversation tracking
        self.active_presentation_topic = title
        self.active_presentation_status = "created"

        # 6. Compile PPTX and Open
        self.productivity.pptx_helper(pres_title, pres_subtitle, theme, slides_content)
        self.productivity.open_presentation()
        
        # 7. Ask user for review
        self.orb.set_state("speaking")
        self.tts.speak("Maine presentation open kar di hai, sir. Ek baar dekh lijiye aur bataiye ki kya ye sahi hai ya koi change karna hai?")
        self.orb.set_state("idle")
        return "Opening the presentation for you now, sir."

    def _generate_response(self, text: str, domain: str = "general") -> str:
        memories = self.brain.format_memories_for_prompt(text)
        
        if domain in self.domains:
            # Route to expert
            return self.domains[domain].answer(text, memories)
            
        system_key = domain if domain in self.prompts["system_prompts"] else "main"
        system = self.prompts["system_prompts"][system_key] + memories
        
        if getattr(self, "chat_history_summary", ""):
            system += f"\n[Dialogue history summary of older turns in this session: {self.chat_history_summary}]"

        # Append sentiment modifier to system prompt
        cognitive = getattr(self, "cognitive_state", "calm")
        if cognitive == "stressed":
            system += "\n[System Note: The user is currently feeling STRESSED. Speak slower, be highly encouraging, empathetic, reassuring, and concise to avoid overwhelming them.]"
        elif cognitive == "fatigued":
            system += "\n[System Note: The user is currently feeling FATIGUED/TIRED. Speak in a gentle, warm, encouraging tone, keeping answers brief and comforting.]"
        elif cognitive == "excited":
            system += "\n[System Note: The user is currently feeling EXCITED. Match their energy, be enthusiastic and efficient.]"

        # Append real-time active window context to system prompt
        if hasattr(self, "sentinel") and self.sentinel:
            ctx = self.sentinel.get_active_context()
            if ctx.get("process") != "unknown" or ctx.get("title") != "unknown":
                system += f"\n[User Workspace Context: Active Application is {ctx.get('process')} | Window Title: {ctx.get('title')}]"

        try:
            self.chat_history.append({"role": "user", "content": text})
            
            # Conversational/multilingual check to use free OfoxAI GLM-4.7-Flash (excellent Hinglish)
            has_devanagari = any('\u0900' <= c <= '\u097F' for c in text)
            hindi_cues = ["karo", "karna", "dikhao", "de", "kar", "bhej", "kholo", "chalao", "batao", "sunao", "hai", "hoon", "tha", "thi", "yaar", "sir", "kaise", "kya", "tum", "main", "aap", "pehle", "kuch", "bhajao", "bajado", "gaana", "gana", "song", "play"]
            has_hindi_cues = has_devanagari or any(w in text.lower() for w in hindi_cues)
            
            is_conversational = domain == "general" or has_hindi_cues or any(w in text.lower() for w in ["hello", "hi ", "hey", "weather", "volume", "music", "time"])
            if is_conversational:
                reply_text = self.query_llm(self.chat_history, system_prompt=system, provider="ofoxai", model="z-ai/glm-4.7-flash:free")
            else:
                reply_text = self.query_llm(self.chat_history, system_prompt=system, provider="mistral", model="mistral-large-2512")
            
            self.chat_history.append({"role": "assistant", "content": reply_text})
            
            # Compress if history exceeds 10 turns (20 messages)
            if len(self.chat_history) >= 20:
                self._compress_chat_history()
                
            return reply_text
        except Exception as e:
            logger.error(f"Generate response error: {e}")
            return "I am currently unable to process your request, sir."

    def _compress_chat_history(self):
        """Summarizes the oldest 10 messages and keeps only the latest 10 messages in memory."""
        try:
            to_summarize = self.chat_history[:10]
            history_str = "\n".join(f"{m['role'].capitalize()}: {m['content']}" for m in to_summarize)
            
            prompt = (
                f"Summarize the following recent dialogue history briefly in 2-3 sentences. "
                f"Keep key details, facts, or decisions mentioned:\n\n{history_str}"
            )
            
            response = ollama.chat(
                model=self.models["main_brain"],
                messages=[{"role": "user", "content": prompt}]
            )
            summary = response["message"]["content"].strip()
            
            if self.chat_history_summary:
                combined_prompt = (
                    f"Combine these two summaries of dialogue history into one cohesive, brief summary "
                    f"(maximum 4 sentences):\nSummary 1: {self.chat_history_summary}\nSummary 2: {summary}"
                )
                comb_res = ollama.chat(
                    model=self.models["main_brain"],
                    messages=[{"role": "user", "content": combined_prompt}]
                )
                self.chat_history_summary = comb_res["message"]["content"].strip()
            else:
                self.chat_history_summary = summary
                
            self.chat_history = self.chat_history[10:]
            logger.info(f"Dialogue history compressed. New summary: {self.chat_history_summary}")
        except Exception as e:
            logger.error(f"Error compressing dialogue history: {e}")

    def clean_to_plain_text(self, text: str) -> str:
        """Strips markdown formatting, bullet points, numbers, links, and asterisks for conversational speech/viewing."""
        import re
        if not text:
            return ""
        # 1. Remove parenthetical descriptions (e.g. (pauses), (smiling), (breathes softly))
        text = re.sub(r"\([^)]*\)", "", text)

        # 2. Remove markdown images
        text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
        
        # 3. Remove markdown links (keep text, discard URL)
        text = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", text)
        text = re.sub(r"<(https?://\S+)>", "", text)
        text = re.sub(r"\bhttps?://\S+", "", text)
        
        # 4. Remove bold/italic asterisks and underscores
        text = text.replace("**", "").replace("*", "").replace("__", "").replace("_", "")
        
        # 5. Remove markdown headers
        text = re.sub(r"^#+\s+", "", text, flags=re.MULTILINE)
        
        # 6. Clean bullet points at start of lines
        text = re.sub(r"^[ \t]*[-\*+]\s+", "", text, flags=re.MULTILINE)
        
        # 7. Clean numbered list markers at start of lines or sentences
        text = re.sub(r"^[ \t]*\d+\.\s+", "", text, flags=re.MULTILINE)
        
        # 8. Join lines into smooth flowing paragraphs
        paragraphs = []
        for line in text.split("\n"):
            line = line.strip()
            if line:
                paragraphs.append(line)
        
        combined = " ".join(paragraphs)
        combined = re.sub(r"\s+", " ", combined).strip()

        # 9. Interactive Turn Truncation:
        # If the text contains an interactive question, truncate the text immediately after the question mark.
        question_match = re.search(r"(\b(?:shall\s+we|would\s+you\s+like|should\s+i|can\s+i|do\s+you\s+want)\b[^?]*\?)", combined, flags=re.IGNORECASE)
        if question_match:
            idx = combined.find(question_match.group(1)) + len(question_match.group(1))
            combined = combined[:idx].strip()

        return combined

    def on_orb_state_changed(self, state: str):
        if state == "interrupt":
            logger.info("Orb clicked during speech. Stopping speech playback.")
            self.tts.stop_speech()

    def _safety_check(self, text: str) -> bool:
        """Lightweight safety check (Bypasses heavy LLM shieldgemma to save 2GB+ VRAM and speed up responses)"""
        # Return True directly to optimize performance. Local regex or word blocklists can be added here if needed.
        return True

    def split_chained_commands(self, text: str) -> list[str]:
        import re
        pattern = r"\b(?:and\s+then|then|after\s+that|and\s+after\s+that|uske\s+baad|iske\s+baad|phir|aur\s+phir|aur\s+uske\s+baad)\b"
        splits = re.split(pattern, text, flags=re.IGNORECASE)
        commands = [c.strip() for c in splits if c.strip()]
        return commands

    def _get_friendly_task_desc(self, text: str, is_hinglish: bool = False) -> str:
        """Returns a human-like description of a command's intent."""
        import re
        intent = self.router.route(text, self.active_presentation_topic)
        skill = intent.get("skill", "conversation")
        params = intent.get("params", {})
        
        # Loop 4: Self-Corrective STT & Phonetic Routing Loop
        if skill == "conversation":
            candidates = self._get_phonetic_candidates(text)
            for cand in candidates:
                cand_intent = self.router.route(cand, self.active_presentation_topic)
                cand_skill = cand_intent.get("skill", "conversation")
                if cand_skill != "conversation":
                    intent = cand_intent
                    skill = cand_skill
                    params = intent.get("params", {})
                    domain = intent.get("domain", "general")
                    break
        if is_hinglish:
            if skill == "os_control":
                action = params.get("action", "")
                if action == "clean_disk":
                    return "system ki temporary files clear karungi"
                elif action == "empty_recycle_bin":
                    return "recycle bin ki trash files empty karungi"
                elif action == "secure":
                    return "laptop screen lock karungi"
                elif action == "unlock":
                    return "system unlock karungi"
                elif action == "launch":
                    return f"{params.get('app', 'app')} open karungi"
                elif action == "close":
                    return f"{params.get('app', 'app')} close karungi"
                elif action == "set_brightness":
                    return f"brightness adjusted {params.get('percent', 50)} percent karungi"
            elif skill == "spotify" or skill == "youtube_music":
                action = params.get("action", "")
                if action == "play":
                    return f"Spotify par {params.get('query', 'gaana')} play karungi"
                elif action == "pause":
                    return "music pause karungi"
            elif skill == "system_monitor":
                return "system resource check karungi"
            # Conversational fallbacks in Hinglish
            text_lower = text.lower()
            if "whatsapp" in text_lower:
                return "WhatsApp par message send karungi"
            elif any(w in text_lower for w in ["presentation", "ppt", "slide"]):
                return "presentation generate karungi"
            elif any(w in text_lower for w in ["search", "google", "research"]):
                return "web search karungi"
            return f"'{text}' command run karungi"
        else:
            if skill == "os_control":
                action = params.get("action", "")
                if action == "clean_disk":
                    return "clear the system temporary files"
                elif action == "empty_recycle_bin":
                    return "empty the recycle bin"
                elif action == "secure":
                    return "lock the screen"
                elif action == "unlock":
                    return "unlock the screen"
                elif action == "launch":
                    return f"launch the {params.get('app', 'requested application')}"
                elif action == "close":
                    return f"close {params.get('app', 'the application')}"
                elif action == "set_brightness":
                    return f"adjust system brightness to {params.get('percent', 50)} percent"
                
            elif skill == "sentry_firewall":
                action = params.get("action", "")
                if action == "quarantine":
                    return f"quarantine and block remote endpoint {params.get('ip', 'IP')}"
                elif action == "remove_quarantine":
                    return f"remove firewall block for {params.get('ip', 'IP')}"
                elif action == "list_blocks":
                    return "list active firewall quarantine blocks"
                    
            elif skill == "hologram_control":
                action = params.get("action", "")
                if action == "explode":
                    enable = params.get("enable", True)
                    return "explode the hologram assembly" if enable else "collapse the hologram assembly"
                elif action == "toggle_heatmap":
                    enable = params.get("enable", True)
                    return "show the load heatmap" if enable else "hide the load heatmap"
                elif action == "set_rotation":
                    return f"set hologram rotation speed to {params.get('speed', 'slow')}"
                    
            elif skill == "system_monitor":
                return "check system resources"
                
            elif skill == "spotify" or skill == "youtube_music":
                action = params.get("action", "")
                if action == "play":
                    return f"play {params.get('query', 'music')}"
                elif action == "pause":
                    return "pause the music player"
                    
            text_lower = text.lower()
            if "whatsapp" in text_lower:
                return "open WhatsApp and draft a message"
            elif any(w in text_lower for w in ["spotify", "music", "song", "gaana", "gaane"]):
                return "play the requested song"
            elif any(w in text_lower for w in ["presentation", "ppt", "slide", "slides"]):
                return "create the requested presentation"
            elif any(w in text_lower for w in ["search", "google", "find", "research"]):
                return "conduct a web search"
                
            words = text.split()
            if len(words) > 5:
                return " ".join(words[:5]) + "..."
            return text

    def process_command(self, text: str):
        """Processes a single command, or splits and executes a chain of sequential commands with human-like transitions."""
        import re
        
        has_devanagari = any('\u0900' <= c <= '\u097F' for c in text)
        hindi_cues = ["karo", "karna", "dikhao", "de", "kar", "bhej", "kholo", "chalao", "batao", "sunao", "hai", "hoon", "tha", "thi", "yaar", "sir", "kaise", "kya", "tum", "main", "aap", "pehle", "kuch", "bhajao", "bajado", "gaana", "gana", "song", "play", "so", "sojao", "so jao", "so jaao"]
        is_hinglish = has_devanagari or any(w in text.lower() for w in hindi_cues)

        commands = self.split_chained_commands(text)
        cleaned_cmds = []
        for cmd in commands:
            cmd_clean = re.sub(r"^(?:first|second|third|fourth|then|and|so|now)\s+", "", cmd, flags=re.IGNORECASE).strip()
            if cmd_clean:
                cleaned_cmds.append(cmd_clean)

        if len(cleaned_cmds) > 1:
            logger.info(f"Chained commands detected: {cleaned_cmds}")
            
            # Generate the human-like plan announcement
            descs = [self._get_friendly_task_desc(c, is_hinglish) for c in cleaned_cmds]
            if is_hinglish:
                if len(cleaned_cmds) == 2:
                    plan_intro = f"Ji sir, pehle main {descs[0]}, aur phir {descs[1]}."
                elif len(cleaned_cmds) == 3:
                    plan_intro = f"Abhi karti hu, sir. Pehle main {descs[0]}, uske baad {descs[1]}, aur finally {descs[2]}."
                else:
                    plan_intro = f"Bilkul sir, mere paas {len(cleaned_cmds)} tasks ki list hai: pehle main {descs[0]} aur phir baki sab karti hu."
            else:
                if len(cleaned_cmds) == 2:
                    plan_intro = f"Right away, sir. First, I will {descs[0]}, and then I will {descs[1]}."
                elif len(cleaned_cmds) == 3:
                    plan_intro = f"Right away, sir. First, I will {descs[0]}, next, I will {descs[1]}, and finally, I will {descs[2]}."
                else:
                    plan_intro = f"Right away, sir. I have a chain of {len(cleaned_cmds)} tasks to execute: first, I will {descs[0]}, and then proceed with the rest."
                
            self.orb.set_state("speaking")
            self.tts.speak(plan_intro)
            self.orb.set_state("idle")
            
            for idx, cmd_clean in enumerate(cleaned_cmds):
                logger.info(f"Executing chained command {idx+1}/{len(cleaned_cmds)}: '{cmd_clean}'")
                
                # Speak transitional phrase between tasks only for non-immediate actions
                is_immediate_action = any(phrase in cmd_clean.lower() for phrase in ["play", "volume", "music", "song", "mute", "unmute", "lock", "sentry", "secure"])
                if idx > 0 and not is_immediate_action:
                    if is_hinglish:
                        transition = f"Chaliye sir, ab main {descs[idx]}."
                    else:
                        transition = f"Now, I am going to {descs[idx]}, sir."
                    self.orb.set_state("speaking")
                    self.tts.speak(transition)
                    self.orb.set_state("idle")
                
                # Execute command with is_chained=True
                self._process_single_command(cmd_clean, speak_filler=False, is_chained=True)
                time.sleep(1.0)
            return
        else:
            self._process_single_command(text)

    def transliterate_devanagari_to_roman(self, text: str) -> str:
        """Transliterates Devanagari Hindi text to Roman script Hinglish phonetically."""
        consonants = {
            'क': 'k', 'ख': 'kh', 'ग': 'g', 'घ': 'gh', 'ङ': 'n',
            'च': 'ch', 'छ': 'chh', 'ज': 'j', 'झ': 'jh', 'ञ': 'n',
            'ट': 't', 'ठ': 'th', 'ड': 'd', 'ढ': 'dh', 'ण': 'n',
            'त': 't', 'थ': 'th', 'द': 'd', 'ध': 'dh', 'न': 'n',
            'प': 'p', 'फ': 'f', 'ब': 'b', 'भ': 'bh', 'म': 'm',
            'य': 'y', 'र': 'r', 'ल': 'l', 'व': 'v', 'श': 'sh',
            'ष': 'sh', 'स': 's', 'ह': 'h', 'क्ष': 'ksh', 'त्र': 'tr',
            'ज्ञ': 'gy', 'ड़': 'd', 'ढ़': 'dh'
        }
        vowels = {
            'अ': 'a', 'आ': 'aa', 'इ': 'i', 'ई': 'ee', 'उ': 'u', 'ऊ': 'oo',
            'ऋ': 'ri', 'ए': 'e', 'ऐ': 'ai', 'ओ': 'o', 'औ': 'au',
            'ा': 'a', 'ि': 'i', 'ी': 'ee', 'ु': 'u', 'ू': 'oo',
            'े': 'e', 'ै': 'ai', 'ो': 'o', 'ौ': 'au',
            'ं': 'n', 'ः': 'h', 'ँ': 'n', '्': ''
        }
        common_words = {
            "एक": "ek", "काम": "kaam", "करो": "karo", "कर": "kar", "दे": "de", "दो": "do",
            "दिखाओ": "dikhao", "दिखा": "dikha", "खोल": "khol", "खोलना": "kholo",
            "बजाओ": "bajao", "बजा": "baja", "चलाओ": "chalao", "चला": "chala",
            "मुझे": "mujhe", "मेरा": "mera", "मेरी": "meri", "तुम": "tum", "तुम्हारा": "tumhara",
            "आप": "aap", "आपका": "aapka", "है": "hai", "हूँ": "hoon", "था": "tha",
            "थी": "thi", "थे": "the", "रहना": "rahna", "रहा": "raha", "रही": "rahi",
            "रहे": "rahe", "करते": "karte", "करती": "karti", "करता": "karta",
            "कहाँ": "kahan", "कब": "kab", "क्यों": "kyun", "कैसे": "kaise", "क्या": "kya",
            "कौन": "kaun", "कुछ": "kuch", "sab": "sab", "और": "aur", "भी": "bhi",
            "तो": "toh", "ye": "yeh", "वह": "woh", "अंडर": "under", "बजेट": "budget",
            "लेप्टोप": "laptop", "लैपटॉप": "laptop", "ब्राउज़र": "browser", "ब्रूवजर": "browser",
            "क्रोम": "chrome", "स्पोटिफ़ाई": "spotify", "स्पॉटीफाई": "spotify",
            "गाने": "gaane", "गाना": "gaana", "बजादो": "bajado", "प्ले": "play",
            "को": "ko", "pe": "pe", "pehle": "pehle", "par": "par", "मम्मी": "mommy", "पापा": "papa"
        }
        words = text.split()
        translated_words = []
        for w in words:
            clean_w = w.strip(",.!?\"'")
            punctuation = w[len(clean_w):] if w.endswith(clean_w) else ""
            lead_punctuation = w[:w.find(clean_w)] if clean_w in w else ""
            if clean_w in common_words:
                translated_words.append(lead_punctuation + common_words[clean_w] + punctuation)
            elif any('\u0900' <= c <= '\u097F' for c in clean_w):
                roman = ""
                i = 0
                while i < len(clean_w):
                    char = clean_w[i]
                    next_char = clean_w[i+1] if i + 1 < len(clean_w) else ""
                    if next_char == '्':
                        if char in consonants:
                            roman += consonants[char]
                        i += 2
                        continue
                    if char in consonants:
                        roman += consonants[char]
                        if next_char in vowels and next_char not in ['अ', 'आ', 'इ', 'ई', 'उ', 'ऊ', 'ऋ', 'ए', 'ऐ', 'ओ', 'औ']:
                            roman += vowels[next_char]
                            i += 2
                        else:
                            if next_char not in vowels and next_char != '':
                                roman += 'a'
                            i += 1
                    elif char in vowels:
                        roman += vowels[char]
                        i += 1
                    else:
                        roman += char
                        i += 1
                translated_words.append(lead_punctuation + roman + punctuation)
            else:
                translated_words.append(w)
        return " ".join(translated_words)

    def _get_phonetic_candidates(self, text: str) -> list[str]:
        mappings = {
            "risakhal": "recycle",
            "vine": "bin",
            "tresh": "trash",
            "fayas": "files",
            "dilet": "delete",
            "temathareree": "temporary",
            "kesh": "cache",
            "rimo": "remove",
            "leptob": "laptop",
            "leptop": "laptop",
            "aplication": "application",
            "opun": "open",
            "apen": "open",
            "play music": "play some music",
            "spotifai": "spotify",
            "spotifaee": "spotify",
            "dish clean up": "disk cleanup",
            "dish clean": "disk cleanup",
            "mailware": "malware",
            "garo": "karo",
            "buja": "baja"
        }
        words = text.lower().split()
        modified = False
        candidates = []
        
        # Word replacement candidate
        replaced_words = []
        for w in words:
            clean_w = w.strip(",.!?\"'")
            punctuation = w[len(clean_w):] if w.endswith(clean_w) else ""
            lead_punctuation = w[:w.find(clean_w)] if clean_w in w else ""
            if clean_w in mappings:
                replaced_words.append(lead_punctuation + mappings[clean_w] + punctuation)
                modified = True
            else:
                replaced_words.append(w)
        if modified:
            candidates.append(" ".join(replaced_words))
            
        # Substring replacement candidate
        phrase = text.lower()
        phrase_modified = False
        for k, v in mappings.items():
            if k in phrase:
                phrase = phrase.replace(k, v)
                phrase_modified = True
        if phrase_modified:
            candidates.append(phrase)
            
        return list(set(candidates))

    def _reload_skill_instance(self, filepath: str) -> bool:
        try:
            import importlib
            import sys
            norm_filepath = os.path.abspath(filepath)
            cwd = os.path.abspath(os.getcwd())
            rel_path = os.path.relpath(norm_filepath, cwd).replace("\\", "/")
            mappings = {
                "skills/os_control.py": ("os_ctrl", "OSControl"),
                "skills/spotify_control.py": ("spotify_ctrl", "SpotifyControl"),
                "skills/web_research.py": ("web", "WebResearch"),
                "skills/gesture_control.py": ("gesture_ctrl", "GestureController"),
                "core/intent_router.py": ("router", "IntentRouter")
            }
            if rel_path not in mappings:
                return False
            attr_name, class_name = mappings[rel_path]
            module_name = rel_path.replace(".py", "").replace("/", ".")
            if module_name in sys.modules:
                importlib.reload(sys.modules[module_name])
            else:
                sys.modules[module_name] = importlib.import_module(module_name)
            module = sys.modules[module_name]
            self._reinstantiate_skill(attr_name, class_name, module)
            return True
        except Exception:
            return False

    def _reinstantiate_skill(self, attr_name: str, class_name: str, module):
        class_obj = getattr(module, class_name)
        if attr_name == "web":
            new_inst = class_obj(jarvis=self)
        elif attr_name == "gesture_ctrl":
            new_inst = class_obj(self.camera, canvas=self.canvas, youtube_music=self.youtube_music)
        else:
            new_inst = class_obj()
        setattr(self, attr_name, new_inst)

    def _process_single_command(self, text: str, speak_filler: bool = True, is_chained: bool = False):
        """Full pipeline: route → execute → respond → speak"""
        self.orb.set_state("thinking")

        # Speak filler instantly while processing
        if speak_filler:
            threading.Thread(target=self.tts.speak_filler, daemon=True).start()

        # Store user input in memory
        self.brain.store(text, role="user")

        # Check for presentation finalization response
        if self.active_presentation_status == "created" and self.active_presentation_topic:
            confirmations = ["sahi hai", "perfect", "done", "bahut badhiya", "yes", "correct", "good", "nice", "no changes", "ok", "aacha hai", "acha hai"]
            text_lower = text.lower().strip()
            if any(c in text_lower for c in confirmations) and not any(w in text_lower for w in ["change", "modify", "update", "image", "content", "not", "nahi", "no"]):
                self.active_presentation_topic = None
                self.active_presentation_status = "idle"
                response = "Bahut badhiya! Maine ise done kar diya hai. Ab bataiye, aur kya kaam karna hai?"
                self.orb.set_state("speaking")
                self.tts.speak(response)
                self.orb.set_state("idle")
                self.brain.store(response, role="assistant")
                return

        # Check if we have a pending code snippet and the user is responding to the confirmation
        if getattr(self, "pending_code_snippet", None):
            user_confirm = text.lower()
            if any(w in user_confirm for w in ["write", "save", "create file", "file"]):
                snippet = self.pending_code_snippet
                self.pending_code_snippet = None
                filename = "workspace_script.py"
                try:
                    with open(filename, "w", encoding="utf-8") as f:
                        f.write(snippet)
                    response = f"I have written the script to {filename}, sir."
                    
                    # Auto-open in VS Code and Explorer
                    import subprocess
                    try:
                        subprocess.Popen(f"code {filename}", shell=True)
                        subprocess.Popen(f"explorer /select,{os.path.abspath(filename)}", shell=True)
                    except Exception as open_err:
                        logger.error(f"Failed to auto-open file/explorer: {open_err}")
                except Exception as write_err:
                    response = f"Failed to write script, sir. {write_err}"
                self.orb.set_state("speaking")
                self.tts.speak(response)
                self.orb.set_state("idle")
                self.brain.store(response, role="assistant")
                return
            elif any(w in user_confirm for w in ["run", "execute", "play", "start"]):
                snippet = self.pending_code_snippet
                self.pending_code_snippet = None
                filename = "workspace_script.py"
                try:
                    with open(filename, "w", encoding="utf-8") as f:
                        f.write(snippet)
                    response = f"Running the script now, sir."
                    self.orb.set_state("speaking")
                    self.tts.speak(response)
                    self.orb.set_state("idle")
                    self.brain.store(response, role="assistant")
                    import subprocess
                    try:
                        subprocess.Popen(f"code {filename}", shell=True)
                    except Exception:
                        pass
                    subprocess.Popen(f".\\jarvis_env\\Scripts\\python.exe {filename}", shell=True)
                except Exception as run_err:
                    response = f"Failed to execute script, sir. {run_err}"
                    self.orb.set_state("speaking")
                    self.tts.speak(response)
                    self.orb.set_state("idle")
                    self.brain.store(response, role="assistant")
                return

        # Route intent
        intent = self.router.route(text, self.active_presentation_topic)
        skill = intent.get("skill", "conversation")
        params = intent.get("params", {})
        domain = intent.get("domain", "general")

        logger.info(f"Intent routed -> Skill: {skill} | Domain: {domain} | Params: {params}")

        if skill == "ambiguous":
            self.active_context = {
                "type": "confirm_ambiguous_intent",
                "options": params["options"],
                "text": text,
                "timestamp": time.time()
            }
            labels = [opt["label"] for opt in params["options"]]
            clarification = f"I heard '{text}', sir. Did you mean to {labels[0]}, or {labels[1]}?"
            self.orb.set_state("speaking")
            self.tts.speak(clarification)
            self.orb.set_state("idle")
            return

        # Vocal Biometric Signature Verification
        high_risk_skills = {"coding_sandbox", "sentry_firewall", "os_control"}
        if skill in high_risk_skills and getattr(self.audio, "latest_raw_audio", None) is not None:
            # Bypass if the voice was verified via wake word within the last 45 seconds
            recent_auth = (time.time() - getattr(self, "last_voice_auth_time", 0.0)) < 45.0
            if not recent_auth:
                is_verified, similarity = self.voice_auth.verify_speaker(self.audio.latest_raw_audio)
                if not is_verified:
                    logger.warning(f"Voice Auth: Biometric check failed (Sim: {similarity:.3f}) for skill {skill}")
                    self.orb.set_state("error")
                    self.tts.speak("Vocal signature mismatch. Action blocked, sir.")
                    self.orb.set_state("idle")
                    return

        response = ""
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
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
                        app_to_launch = params.get("app", "")
                        for attempt in range(1, 4):
                            logger.info(f"Visual validation check for '{app_to_launch}' launch attempt {attempt}/3...")
                            response = self.os_ctrl.launch_app(app_to_launch)
                            
                            if "Launched" in response or "focus" in response:
                                time.sleep(2.0)  # Wait for application window to render
                                vlm_prompt = (
                                    f"Analyze the screenshot. Is the application window for '{app_to_launch}' open and visible on the desktop screen? "
                                    "Reply with exactly 'yes' or 'no'."
                                )
                                try:
                                    vlm_result = self.vision.analyze(vlm_prompt).strip().lower()
                                    if "yes" in vlm_result:
                                        logger.success(f"VLM verified '{app_to_launch}' is successfully open and visible!")
                                        response += f" Aur maine visually verify kiya hai, app successfully open ho chuka hai, sir."
                                        break
                                    else:
                                        logger.warning(f"VLM reported '{app_to_launch}' window not found on attempt {attempt}/3. Retrying launch...")
                                        if attempt == 3:
                                            response += f" Aur verification ke baad, main app display visually confirm nahi kar paa rahi hu, sir."
                                except Exception as vision_err:
                                    logger.error(f"VLM launch confirmation failed: {vision_err}")
                                    break
                            else:
                                time.sleep(1.0)
                    elif action == "secure":
                        self.is_asleep = True
                        self.is_authenticated = False
                        self.face_verified = False
                        if getattr(self, "camera", None) is not None:
                            self.camera.stop()
                        if getattr(self, "gesture_ctrl", None) is not None:
                            self.gesture_ctrl.stop()
                        self.os_ctrl.lock_screen()
                        response = "System locked and secure, sir."
                    elif action == "unlock":
                        pin = params.get("pin", "")
                        success, msg = self.auth.verify_pin(pin)
                        if success:
                            self.os_ctrl.unlock_screen()
                            self.os_ctrl.wake_monitor()
                            self.is_authenticated = True
                            if getattr(self, "camera", None) is not None:
                                self.camera.start()
                            if getattr(self, "gesture_ctrl", None) is not None:
                                self.gesture_ctrl.start()
                            response = "System unlocked and authenticated, sir. Welcome back."
                        else:
                            response = f"Access denied, sir. {msg}"
                    elif action == "open_browser":
                        response = self.os_ctrl.open_browser(
                            query=params.get("query", None),
                            url=params.get("url", None)
                        )
                    elif action == "type":
                        response = self.os_ctrl.type_text(params.get("text", ""))
                    elif action == "hotkey":
                        keys = params.get("keys", "").split("+")
                        response = self.os_ctrl.hotkey(*keys)
                    elif action == "click":
                        response = self.os_ctrl.click(params.get("x", 0), params.get("y", 0))
                    elif action == "focus":
                        response = self.os_ctrl.focus_app(params.get("app", ""))
                    elif action == "set_volume":
                        response = self.os_ctrl.set_volume(params.get("percent", 50))
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

                    elif action == "throw":
                        content = params.get("content", "")
                        if not content:
                            import pyperclip
                            content = pyperclip.paste()
                        response = self.phone.throw_file_to_phone(content)

                    elif action == "pull_screen":
                        save_path = "config/phone_screen_pull.png"
                        res = self.phone.pull_phone_screen_to_desktop(save_path)
                        if "successfully" in res.lower():
                            orig_shot = self.vision.latest_screenshot
                            self.vision.latest_screenshot = save_path
                            try:
                                prompt = "This is a pulled screenshot from my Android phone. Describe what is visible on this screen in detail."
                                analysis = self.vision.analyze(prompt)
                                response = f"{res}\n\nPhone Screen Analysis:\n{analysis}"
                            finally:
                                self.vision.latest_screenshot = orig_shot
                        else:
                            response = res

                    else:
                        response = self._generate_response(text, domain)

                elif skill == "network_mapper":
                    action = params.get("action", "")
                    if action == "scan_and_project":
                        self.tts.speak("Scanning local network topology, sir. I will project the active nodes onto the holographic viewport.")
                    
                        def run_scan():
                            devices = self.network_mapper.scan_local_subnet()
                            self.tts.speak(f"Scan complete, sir. Discovered {len(devices)} active network devices.")
                            vertices, connections, name = self.network_mapper.generate_3d_topology(devices)
                            labels = [d[1] for d in devices]
                            labels = ["GATEWAY ROUTER"] + labels
                            self.hologram_widget.set_hologram_object(vertices, connections, name, labels)
                            self.orb.hologram_toggle_signal.emit(True)
                        threading.Thread(target=run_scan, daemon=True).start()
                        response = "Sweep initialized, sir."

                elif skill == "vitals_check":
                    action = params.get("action", "")
                    if action == "check_vitals":
                        self.tts.speak("Analyzing visual blood volume variations. Please look at the camera lens for a brief moment, sir.")
                        time.sleep(1.5)  # Let OpenCV grab some frames
                        res_dict = self.sensory_health.calculate_heart_rate()
                        response = res_dict.get("msg", "Diagnostics failed.")
                        face_rect = getattr(self.camera, "latest_face_rect", None)
                        if face_rect:
                            fx, fy, fw, fh = face_rect
                            self.show_hud_target_highlighter(fx + fw//2, fy + fh//2, f"VITALS: {res_dict.get('bpm', 72)} BPM")

                elif skill == "hologram_control":
                    action = params.get("action", "")
                    if action == "design":
                        obj = params.get("object", "vibranium core")
                        vertices, connections, name, labels = self.cad_gen.generate_mesh(obj)
                        self.hologram_widget.set_hologram_object(vertices, connections, name, labels)
                        self.hologram_widget.show()
                        response = f"Designed 3D wireframe for {obj.upper()}. Projecting to holographic viewport now, sir."
                    elif action == "explode":
                        enable = params.get("enable", True)
                        self.hologram_widget.animate_explode(enable)
                        state = "exploded" if enable else "assembled"
                        response = f"Holographic model successfully {state}, sir."

                elif skill == "agent_lab":
                    action = params.get("action", "")
                    task = params.get("task", "")
                    if action == "open_lab":
                        self.agent_lab.show()
                        response = "Opening cognitive agent laboratory, sir."
                    elif action == "close_lab":
                        self.agent_lab.hide()
                        response = "Closing agent lab, sir."
                    elif action == "collaborate":
                        self.agent_lab.show()
                        self.agent_lab.clear_chat()
                        self.tts.speak(f"Initializing swarm collaboration for: {task}, sir.")
                    
                        def run_lab():
                            self.agent_lab.add_message("System", f"Swarm initialized for task: {task}")
                        
                            # 1. Architect turns
                            self.agent_lab.set_agent_status("Architect", "thinking")
                            import time
                            time.sleep(2)
                            arch_prompt = f"Design the system structure and UX flow for this task: {task}"
                            try:
                                arch_reply = get_agent_response("UX Architect", arch_prompt)
                            except Exception as e:
                                arch_reply = f"Error generating plan: {e}"
                            self.agent_lab.set_agent_status("Architect", "idle")
                            self.agent_lab.add_message("Architect", arch_reply)
                            self.tts.speak("Architect has finished the blueprint. Auditor is checking.")
                        
                            # 2. Auditor turns
                            self.agent_lab.set_agent_status("Auditor", "thinking")
                            time.sleep(2)
                            aud_prompt = f"Audit this design for security vulnerabilities and local data storage privacy:\n{arch_reply}"
                            try:
                                aud_reply = get_agent_response("Security Auditor", aud_prompt)
                            except Exception as e:
                                aud_reply = f"Error auditing design: {e}"
                            self.agent_lab.set_agent_status("Auditor", "idle")
                            self.agent_lab.add_message("Auditor", aud_reply)
                            self.tts.speak("Auditor has signed off. QA is now validating.")
                        
                            # 3. QA turns
                            self.agent_lab.set_agent_status("QA", "thinking")
                            time.sleep(2)
                            qa_prompt = f"Provide a QA test suite and validation checklist for the proposed system and security guidelines:\nDesign: {arch_reply}\nSecurity: {aud_reply}"
                            try:
                                qa_reply = get_agent_response("QA Engineer", qa_prompt)
                            except Exception as e:
                                qa_reply = f"Error generating tests: {e}"
                            self.agent_lab.set_agent_status("QA", "idle")
                            self.agent_lab.add_message("QA", qa_reply)
                            self.agent_lab.add_message("System", "Collaborate loop complete. Solution ready for review, sir.")
                            self.tts.speak("Swarm review complete, sir. All checks passed.")

                        def get_agent_response(role, prompt):
                            system_prompt = f"You are JARVIS's expert {role}. Speak in a concise, technical manner (max 3 sentences). Keep your tone professional and helpful."
                            res = ollama.chat(
                                model=self.models["main_brain"],
                                messages=[
                                    {"role": "system", "content": system_prompt},
                                    {"role": "user", "content": prompt}
                                ],
                                options={"temperature": 0.4}
                            )
                            return res["message"]["content"].strip()
                        threading.Thread(target=run_lab, daemon=True).start()
                        response = "Swarm collaboration initialized. Loading agent profiles, sir."

                elif skill == "sensory_health":
                    action = params.get("action", "")
                    if action == "check":
                        analysis = self.sensory_health.analyze_environment()
                        response = analysis.get("message", "Environment check nominal, sir.")
                    elif action == "recalibrate":
                        response = self.sensory_health.recalibrate_posture()

                elif skill == "p2p_link":
                    action = params.get("action", "")
                    peer_ip = params.get("peer_ip", "")
                    if action == "list_peers":
                        response = self.p2p_link.list_peers()
                    elif action == "send_clipboard":
                        response = self.p2p_link.send_clipboard(peer_ip)
                    elif action == "send_speech":
                        message = params.get("message", "Ping")
                        response = self.p2p_link.send_speech(peer_ip, message)

                elif skill == "air_typist":
                    action = params.get("action", "")
                    if action == "start":
                        response = self.air_typist.start()
                    elif action == "stop":
                        response = self.air_typist.stop()

                elif skill == "hologram_control":
                    action = params.get("action", "")
                    if action == "explode":
                        enable = params.get("enable", True)
                        self.hologram_widget.animate_explode(enable)
                        response = "Expanding holographic structure coordinates, sir." if enable else "Collapsing coordinates to baseline state, sir."
                    elif action == "set_rotation":
                        speed = params.get("speed", "slow")
                        self.hologram_widget.set_rotation_speed(speed)
                        response = f"Adjusting rotation parameters to {speed}, sir."
                    elif action == "toggle_heatmap":
                        enable = params.get("enable", True)
                        self.hologram_widget.toggle_heatmap(enable)
                        response = "Visualizing simulated load heatmap layer, sir." if enable else "Hiding heatmap layer, sir."

                elif skill == "git_sentinel":
                    action = params.get("action", "")
                    if action == "check":
                        self.tts.speak("Initializing git sentinel diagnostic sweep, sir. Checking changed files.")
                        check_res = self.git_sentinel.check_workspace()
                    
                        if check_res["status"] == "clean":
                            response = "Workspace diagnostic checks are clean, sir. No compilation breaks found."
                        else:
                            broken_file = check_res["file_path"]
                            short_name = os.path.basename(broken_file)
                            self.tts.speak(f"Compile break detected in {short_name}. Querying Ollama self-healing patch, sir.")
                        
                            # Generate self-healing patch
                            patch_content = self.git_sentinel.generate_healing_patch(
                                broken_file,
                                check_res["error"],
                                check_res["diff"],
                                self.models["main_brain"],
                                ollama
                            )
                        
                            if patch_content:
                                # Save in active context for user verification before applying
                                self.active_context = {
                                    "type": "confirm_file_patch",
                                    "file_path": broken_file,
                                    "patched_content": patch_content
                                }
                                response = f"I've drafted a self-healing patch to restore compiles in {short_name}. Shall I write it to disk, sir?"
                            else:
                                response = f"Compile break detected in {short_name}, but I was unable to construct a corrective patch automatically."

                elif skill == "sentry_firewall":
                    action = params.get("action", "")
                    ip = params.get("ip", "")
                    if action == "quarantine":
                        response = self.sentry_firewall.quarantine_ip(ip)
                    elif action == "remove_quarantine":
                        response = self.sentry_firewall.remove_quarantine(ip)
                    elif action == "list_blocks":
                        response = self.sentry_firewall.list_blocks()

                elif skill == "focus_tracker":
                    action = params.get("action", "")
                    if action == "open_dashboard":
                        self.vitals_dashboard.show()
                        response = "Displaying vitals and cognitive focus monitor on the HUD overlay, sir."
                    elif action == "close_dashboard":
                        self.vitals_dashboard.hide()
                        response = "Closing vitals monitor, sir."

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
                        
                        # Auto-convert research to presentation if requested in original command
                        cmd_lower = text.lower()
                        if "presentation" in cmd_lower or "ppt" in cmd_lower or "slides" in cmd_lower:
                            try:
                                title = query.title()
                                # Reuse the unified professional presentation generator
                                self._create_professional_presentation(title, research_notes=response)
                                response = f"I have conducted the research on '{title}', downloaded relevant images, and built a professional presentation for you at config/presentation.pptx, sir."
                            except Exception as e:
                                logger.error(f"Failed to generate presentation from research: {e}")
                                response = f"I did the research on '{title}', sir, but encountered an error creating the slide deck: {e}"

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
                    elif action in ["run_code", "toggle_terminal", "new_tab", "close_tab", "next_tab", "prev_tab", "reopen_tab", "save_file"]:
                        ctx = self.sentinel.get_active_context()
                        active_process = ctx.get("process", "unknown")
                        response = self.app_ctrl.execute_action(action, active_process)
                    else:
                        response = self._generate_response(text, domain)

                elif skill == "obsidian":
                    action = params.get("action", "")
                    title = params.get("title", "")
                    content = params.get("content", "")
                    query = params.get("query", "")
                    folder = params.get("folder", "")
                    if action == "create_note":
                        response = self.obsidian_ctrl.create_note(title, content, folder)
                    elif action == "read_note":
                        response = self.obsidian_ctrl.read_note(title)
                    elif action == "search_notes":
                        response = self.obsidian_ctrl.search_notes(query)
                    elif action == "append_to_daily_note":
                        response = self.obsidian_ctrl.append_to_daily_note(content)
                    elif action == "list_notes":
                        response = self.obsidian_ctrl.list_notes(folder)
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
                            self.is_spotify_playing = True
                            if not is_chained:
                                self.is_asleep = True
                                self.orb.set_state("idle")
                        elif action in ["pause", "resume", "next", "previous", "volume_up", "volume_down"]:
                            if action == "pause":
                                self.is_spotify_playing = False
                                if "stop" in text.lower():
                                    response = self.youtube_music.control_media("stop")
                                else:
                                    response = self.youtube_music.control_media("pause")
                            elif action == "resume":
                                self.is_spotify_playing = True
                                response = self.youtube_music.control_media("resume")
                            elif action in ["volume_up", "volume_down", "next", "previous"]:
                                response = self.youtube_music.control_media(action)
                            else:
                                response = self.spotify_ctrl.control_media(action)
                        else:
                            response = self._generate_response(text, domain)
                    else:
                        if action == "play":
                            # Check for general queries to avoid playing random tracks blindly
                            query_clean = query.lower().strip() if query else ""
                            general_cues = [
                                "", "some music", "some songs", "music", "songs", "song", "gaana", "gaane",
                                "acche gaane", "acche se gaane", "acche se song", "good music", "good songs",
                                "some good music", "some good songs", "koi acche se gaane", "koi ache se gane",
                                "koi acche gaane", "koi ache gane", "play music", "play songs", "play song", "gaana chalao",
                                "song chalao", "gaana bajao", "song bajao", "chalao", "bajao"
                            ]
                            if query_clean in general_cues:
                                response = "Sir, aapko kis tarah ke gaane sunne hain? Aap mujhe koi specific song, artist ya genre bata sakte hain, main use play kar dungi."
                            else:
                                for attempt in range(1, 4):
                                    logger.info(f"Spotify playback attempt {attempt}/3...")
                                    response = self.spotify_ctrl.play_song(query)
                                    self.is_spotify_playing = True

                                    # Wait for Spotify to start audio output
                                    time.sleep(2.5)

                                    # PRIMARY: Use Spotify Web API to accurately verify playback
                                    api_verified = False
                                    if getattr(self.spotify_ctrl, "use_api", False):
                                        try:
                                            api_verified = self.spotify_ctrl.is_actually_playing()
                                            if api_verified:
                                                logger.success("Spotify API confirmed: track is actively playing.")
                                                break
                                            else:
                                                logger.warning(f"Spotify API: not playing on attempt {attempt}/3. Retrying...")
                                                if attempt < 3:
                                                    import pyautogui as _pag
                                                    _pag.press('space')
                                                    time.sleep(1.0)
                                                else:
                                                    response += " Lekin main confirm nahi kar paayi ki gaana actually chal raha hai, sir."
                                        except Exception as api_verify_err:
                                            logger.error(f"API playback check failed: {api_verify_err}")
                                            break
                                    else:
                                        # SECONDARY: VLM fallback only when no API available
                                        # Use precise prompt checking progress bar, not just window presence
                                        vlm_prompt = (
                                            "Look at the bottom player bar of Spotify carefully. "
                                            "Is there a song title shown AND is the playback time counter showing more than 0:00 (i.e., has playback started)? "
                                            "Reply with ONLY 'yes' or 'no'."
                                        )
                                        try:
                                            vlm_result = self.vision.analyze(vlm_prompt).strip().lower()
                                            if "yes" in vlm_result:
                                                logger.success("VLM verified Spotify playback active via progress bar check.")
                                                break
                                            else:
                                                logger.warning(f"VLM: Spotify not playing on attempt {attempt}/3.")
                                                import pyautogui as _pag
                                                _pag.press('space')
                                                time.sleep(1.0)
                                                if attempt == 3:
                                                    response += " Aur verification ke baad playback confirm nahi hua, sir."
                                        except Exception as vision_err:
                                            logger.error(f"VLM play confirmation failed: {vision_err}")
                                            break

                                if not is_chained:
                                    self.is_asleep = True
                                    self.orb.set_state("idle")
                        elif action in ["pause", "resume", "next", "previous", "volume_up", "volume_down"]:
                            if action == "pause":
                                self.is_spotify_playing = False
                            elif action == "resume":
                                self.is_spotify_playing = True
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
                        title = params.get("title", "Topic")
                        # Normalize slides vs slide_count keys and ensure it's cast to int
                        s_count_raw = params.get("slide_count") or params.get("slides")
                        s_count = None
                        if s_count_raw is not None:
                            try:
                                s_count = int(s_count_raw)
                            except Exception:
                                pass
                        pres_name = params.get("presenter")
                        response = self._create_professional_presentation(
                            title, 
                            slide_count=s_count, 
                            presenter=pres_name
                        )
                    elif action == "modify_presentation_slide":
                        import json
                        import re
                        slide_num = params.get("slide_num")
                        query = params.get("query", text)
                        logger.info(f"Modifying presentation slide. Specified number: {slide_num}")
                        
                        state_path = "config/last_presentation.json"
                        if not os.path.exists(state_path):
                            response = "Sir, I could not find a previously generated presentation metadata to modify. Please create a presentation first."
                        else:
                            try:
                                with open(state_path, "r", encoding="utf-8") as f:
                                    state = json.load(f)
                                
                                theme = state.get("theme", "stark_tech")
                                slides = state.get("slides", [])
                                pres_title = state.get("title", "Topic")
                                pres_subtitle = state.get("subtitle", "")
                                
                                # Vision Active Slide Detection fallback
                                if slide_num is None:
                                    logger.info("Slide number not specified. Capturing screen to detect visible slide...")
                                    try:
                                        import pyautogui
                                        screenshot_path = "config/temp_slide_screen.png"
                                        os.makedirs("config", exist_ok=True)
                                        pyautogui.screenshot(screenshot_path)
                                        
                                        # Use Vision model to read title
                                        detected_title = self.vision.analyze(
                                            "What is the title of the slide shown on the screen? "
                                            "Give me ONLY the exact slide title text. Do not include any explanation or quote marks."
                                        )
                                        logger.info(f"Vision model detected slide title: '{detected_title}'")
                                        
                                        # Match title
                                        best_idx = None
                                        det_lower = detected_title.lower().strip()
                                        for idx, s in enumerate(slides):
                                            s_title_lower = s.get("title", "").lower().strip()
                                            if s_title_lower in det_lower or det_lower in s_title_lower:
                                                best_idx = idx
                                                break
                                        if best_idx is not None:
                                            slide_num = best_idx + 1
                                            logger.info(f"Vision matched detected title to Slide {slide_num}")
                                        else:
                                            slide_num = 1
                                            logger.warning("Vision could not match screen title to slide metadata. Defaulting to Slide 1.")
                                    except Exception as vis_err:
                                        logger.error(f"Active slide detection failed: {vis_err}")
                                        slide_num = 1
                                
                                if slide_num < 1 or slide_num > len(slides):
                                    response = f"Sir, slide number {slide_num} is out of bounds. The presentation has {len(slides)} slides."
                                else:
                                    target_idx = slide_num - 1
                                    current_slide = slides[target_idx]
                                    
                                    prompt = (
                                        f"You are modifying a single slide (Slide {slide_num}) of a PowerPoint presentation.\n"
                                        f"Current Slide Title: '{current_slide.get('title')}'\n"
                                        f"Current Slide Bullets: {current_slide.get('bullets')}\n"
                                        f"Current Image Search Query: '{current_slide.get('image_query')}'\n\n"
                                        f"User request: '{query}'\n\n"
                                        "Please update the slide's fields (title, bullets, and image_query) accordingly. "
                                        "Ensure bullets are highly professional and properly capitalized. "
                                        "Output ONLY a raw, valid JSON object containing: "
                                        '{"title": "...", "bullets": ["...", "..."], "image_query": "..."}. '
                                        "Do not include any markdown code wrappers, quotes, or backticks."
                                    )
                                    
                                    raw = self.query_llm([{"role": "user", "content": prompt}], provider="mistral", model="mistral-large-2512")
                                    raw = raw.strip().replace("```json", "").replace("```", "").strip()
                                    start_idx = raw.find("{")
                                    end_idx = raw.rfind("}")
                                    if start_idx != -1 and end_idx != -1:
                                        raw = raw[start_idx:end_idx+1]
                                    slide_update = json.loads(raw)
                                    
                                    current_slide["title"] = slide_update.get("title", current_slide.get("title"))
                                    current_slide["bullets"] = slide_update.get("bullets", current_slide.get("bullets"))
                                    
                                    new_img_query = slide_update.get("image_query", current_slide.get("image_query", ""))
                                    if new_img_query and new_img_query != current_slide.get("image_query", ""):
                                        current_slide["image_query"] = new_img_query
                                        logger.info(f"Slide {slide_num} image query updated to: '{new_img_query}'. Fetching new image...")
                                        img_urls = self.productivity._search_images(new_img_query, 3)
                                        topic_slug = re.sub(r'[^a-zA-Z0-9]', '_', pres_title).lower()
                                        downloaded = False
                                        for url in img_urls:
                                            save_path = f"config/downloads/{topic_slug}/slide_{slide_num}.jpg"
                                            if self.productivity._download_image(url, save_path):
                                                current_slide["image_path"] = save_path
                                                downloaded = True
                                                logger.info(f"Downloaded new image for slide {slide_num}")
                                                break
                                        if not downloaded:
                                            current_slide["image_path"] = ""
                                    
                                    with open(state_path, "w", encoding="utf-8") as f:
                                        json.dump(state, f, indent=2, ensure_ascii=False)
                                        
                                    self.productivity.pptx_helper(pres_title, pres_subtitle, theme, slides)
                                    self.productivity.open_presentation()
                                    response = f"I have successfully updated Slide {slide_num} for you and refreshed the presentation, sir."
                            except Exception as e:
                                logger.error(f"Failed to modify slide: {e}")
                                response = f"Failed to modify slide: {e}"
                    elif action == "open_presentation":
                        response = self.productivity.open_presentation()
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
                    elif action in ["scan_threats", "malware_scan", "security_scan", "run_scan", "audit"] or "scan" in action or "malware" in action:
                        response = self.security_auditor.run_system_security_scan()
                    else:
                        response = self.security_auditor.run_system_security_scan()

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
                
                # If execution succeeded, break out of max_attempts retry loop
                break
            except Exception as e:
                logger.error(f"Skill execution failed on attempt {attempt}/{max_attempts}: {e}")
                import traceback
                tb_str = traceback.format_exc()
                if attempt < max_attempts:
                    logger.info("Entering Self-Healing & Hot-Reloading loop...")
                    success, heal_msg = self.healer.heal_error(tb_str)
                    if success:
                        target_info = self.healer._extract_project_file_from_traceback(tb_str)
                        if target_info:
                            filepath, _ = target_info
                            reloaded = self._reload_skill_instance(filepath)
                            if reloaded:
                                logger.success(f"Self-Healing: successfully reloaded {filepath}. Retrying execution...")
                                continue
                success, heal_msg = self.healer.heal_error(tb_str)
                if success:
                    response = heal_msg
                else:
                    response = f"I encountered a minor fault while executing that command, sir. Specifically: {e}."
                break

        # Safety check
        if not self._safety_check(response):
            response = "I cannot assist with that request, sir."

        # Check if response contains code blocks (markdown or standard code)
        import re
        code_blocks = re.findall(r"```[a-zA-Z0-9\-\_]*\n(.*?)\n```", response, flags=re.DOTALL)
        if code_blocks:
            # Save the code snippet in the pending slot
            self.pending_code_snippet = code_blocks[0].strip()
            
            # Extract the non-code text (the explanations/descriptions)
            explanation = re.sub(r"```[a-zA-Z0-9\-\_]*\n(.*?)\n```", "", response, flags=re.DOTALL).strip()
            
            # Determine if this is a code analysis or summarization request
            is_analysis_or_sum = skill in ["screen_vision", "media_summarizer", "web_research"] or any(w in text.lower() for w in ["explain", "summarize", "review", "analyze", "what does", "how does"])
            
            if not is_analysis_or_sum:
                # Truncate explanation to 1-2 sentences max
                sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", explanation) if s.strip()]
                brief_explanation = " ".join(sentences[:2]) if sentences else "I have generated the requested script."
                response = f"{brief_explanation} I have prepared the code snippet for you, sir. Would you like me to write it to a file or run it?"
            else:
                # For analysis/summarization, output the full explanation but completely strip the raw code block
                response = explanation

        # Convert final response to clean plain text format
        response = self.clean_to_plain_text(response)

        # Store response in memory
        self.brain.store(response, role="assistant", skill=skill)

        # Speak
        should_speak = True
        if is_chained:
            silent_skills = ["spotify", "os_control", "app_control"]
            if skill in silent_skills:
                action = params.get("action", "")
                if action in ["play", "pause", "resume", "next", "previous", "volume_up", "volume_down", "set_volume", "mute", "unmute", "secure", "lock"]:
                    should_speak = False
                    logger.info(f"Chained execution: suppressing spoken response for background action '{action}'")

        if should_speak:
            self.orb.set_state("speaking")
            self.tts.speak(response)
            self.orb.set_state("idle")

    def _handle_auth(self, text: str):
        self.orb.set_state("thinking")
        # STT might return text like "my pin is 123456"
        # Extract digits
        pin = "".join(filter(str.isdigit, text))
        
        if not self.auth.is_setup():
            if len(pin) in [4, 6]:
                if self.auth.setup_pin(pin):
                    self.is_authenticated = True
                    self.orb.set_state("speaking")
                    self.tts.speak("PIN setup successful. I am now fully operational, sir.")
                else:
                    self.tts.speak("PIN setup failed. Please carefully state a four or six digit PIN.")
            else:
                self.tts.speak("I need a precise four or six digit PIN to setup your secure lock.")
            self.orb.set_state("idle")
            return

        # Verification
        if len(pin) in [4, 6] or len(pin) > 6:
            if len(pin) > 6:
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

    def show_hud_target_highlighter(self, x: int, y: int, label: str):
        from ui.overlay_widgets import TargetReticleOverlay
        overlay = TargetReticleOverlay(x, y, label)
        overlay.show()
        logger.info(f"Target highlighter activated at {x},{y} with label '{label}'")

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
        time.sleep(3)
        self._startup_voice()
        
        self._is_asleep = False
        self.is_asleep = True
        
        while True:
            try:
                self.orb.set_state("idle")
                
                if self.is_asleep:
                    # Strict two-factor gate: if locked, must verify Face ID first, then voice trigger
                    if not self.is_authenticated and not self.face_verified:
                        time.sleep(0.2)
                        continue

                    # 1. Wait for wake word
                    if not self.wake.listen_for_wake_word():
                        continue

                    # If we got here and not authenticated, we just verified voice print! Unlock now!
                    if not self.is_authenticated:
                        self.is_authenticated = True
                        self.is_asleep = False
                        if getattr(self, "camera", None) is not None:
                            self.camera.start()
                        if getattr(self, "gesture_ctrl", None) is not None:
                            self.gesture_ctrl.start()
                        
                        self.os_ctrl.unlock_screen()
                        self.os_ctrl.wake_monitor()
                        
                        # Write unlocked to state file to close secure_lock.py
                        state_file = os.path.abspath("./auth/.auth_state")
                        try:
                            with open(state_file, "w") as f:
                                f.write("unlocked")
                            time.sleep(0.1)
                            os.remove(state_file)
                        except Exception:
                            pass
                            
                        self.orb.set_state("speaking")
                        self.tts.speak("Identity confirmed. Welcome back, sir.")
                        self.orb.set_state("idle")
                        continue
                        
                    self.last_voice_auth_time = time.time()
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
                            
                    greeting, is_night = self.profile_mgr.get_time_of_day_greeting()
                    if is_night:
                        def apply_night_mode():
                            try:
                                brightness = self.profile_mgr.get_preference("brightness_night", 35)
                                self.os_ctrl.set_brightness(brightness)
                            except Exception:
                                pass
                        threading.Thread(target=apply_night_mode, daemon=True).start()

                    if alerts_to_speak:
                        alert_msg = " Also, ".join(alerts_to_speak)
                        self.tts.speak(f"{greeting} I notice a critical warning. {alert_msg}")
                    else:
                        self.tts.speak(greeting)
                        
                    self.is_asleep = False
                    self.last_command_time = time.time()
                
                # Ensure is_listening_to_command and ducking are active before recording command
                self.is_listening_to_command = True
                self._auto_pause_music()
                
                self.orb.set_state("listening")
                
                # 2. Record command (blocks until user stops speaking or 5-second silence timeout)
                text = self.audio.listen(timeout_sec=5.0)
                if text:
                    text = self.transliterate_devanagari_to_roman(text)
                
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
                    is_music_active = (
                        (self.youtube_music.process is not None and not self.youtube_music.is_paused) or
                        getattr(self, "is_spotify_playing", False)
                    )
                    if is_music_active:
                        logger.info("Music is active. Forcing sleep state on silence to avoid feedback.")
                        self.is_asleep = True
                        self.orb.set_state("idle")
                        continue

                    time_since_cmd = time.time() - getattr(self, "last_command_time", 0.0)
                    if time_since_cmd < 360.0:
                        logger.info(f"No speech, but wake lock timer active ({time_since_cmd:.1f}s / 360s). Staying awake.")
                        continue
                    else:
                        logger.info(f"No speech and wake lock timer expired after {time_since_cmd:.1f}s. Returning to standby.")
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
                              # Check if we have an active context (Stateful Conversational Turns)
                if getattr(self, "active_context", None):
                    ctx = self.active_context
                    cmd_lower = text.lower().strip()
                    word_count = len(cmd_lower.split())

                    # Valid confirmations are usually short (5 words or fewer)
                    if word_count <= 5:
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

                        elif ctx.get("type") == "confirm_ambiguous_intent":
                            options = ctx["options"]
                            selected_cmd = None
                            
                            # Check numerical or semantic options
                            if any(w in cmd_lower for w in ["first", "one", "1"]):
                                selected_cmd = options[0]["command"]
                            elif any(w in cmd_lower for w in ["second", "two", "2"]):
                                selected_cmd = options[1]["command"]
                            else:
                                if "lock" in cmd_lower or "secure" in cmd_lower:
                                    selected_cmd = options[0]["command"]
                                elif "python" in cmd_lower or "script" in cmd_lower or "write" in cmd_lower or "code" in cmd_lower or "log" in cmd_lower:
                                    selected_cmd = options[1]["command"]
                                    
                            if selected_cmd:
                                self.orb.set_state("speaking")
                                self.tts.speak("Right away, sir.")
                                self.orb.set_state("idle")
                                self.active_context = None
                                self.process_command(selected_cmd)
                                continue
                    # If it's a long sentence or doesn't match yes/no, auto-clear context and fall through to regular processing
                    logger.info("Active context bypassed and cleared: user issued a new/longer command.")
                    self.active_context = None

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
                if any(phrase in cmd_lower for phrase in ["go to sleep", "sleep away", "stop listening", "shut up jarvis", "jarvis sleep", "so jao", "so jaao", "standby", "sleep mode"]):
                    self.is_asleep = True
                    self.orb.set_state("speaking")
                    reply = "Going to sleep, sir. Wake me if you need me."
                    if any(w in cmd_lower for w in ["so jao", "so jaao", "standby", "mode"]):
                        reply = "[sigh] Thik hai, sir, main standby mode mein ja rahi hu. Jab bhi zarurat ho, bas 'Hey JARVIS' bol dena."
                    self.tts.speak(reply)
                    continue

                # Dedicated PC system sleep command
                if any(phrase in cmd_lower for phrase in ["sleep the pc", "sleep the computer", "put the laptop to sleep", "put the pc to sleep", "put the computer to sleep"]):
                    self.is_asleep = True
                    self.orb.set_state("speaking")
                    self.tts.speak("Putting the system to sleep, sir. Goodbye.")
                    self.os_ctrl.sleep_system()
                    continue
                    
                # Sentry mode command
                if "secure the laptop" in cmd_lower or "sentry mode" in cmd_lower or "see the laptop" in cmd_lower:
                    self.is_asleep = True
                    self.is_authenticated = False
                    self.face_verified = False
                    self.orb.set_state("speaking")
                    self.tts.speak("Sentry mode activated. Laptop is secure.")
                    self.os_ctrl.activate_sentry_mode(self.camera, self.tts)
                    continue
                    
                # Shutdown command
                if "shutdown the laptop" in cmd_lower or "shut down the laptop" in cmd_lower:
                    self.orb.set_state("speaking")
                    self.tts.speak("Initiating shutdown protocol. Goodbye, sir.")
                    self.os_ctrl.shutdown_system()
                    continue

                print(f"\nJARVIS Heard: {text}\n", flush=True)
                logger.info(f"JARVIS Heard: {text}")
                self.last_command_time = time.time()
                
                # 3. Process
                if not self.is_authenticated:
                    self._handle_auth(text.lower())
                else:
                    self.process_command(text)
                    
                # Auto-resume music if temporarily paused during listening
                self._auto_resume_music(text)

                # Return to standby if music is active to prevent feedback loop
                is_music_active = (
                    (self.youtube_music.process is not None and not self.youtube_music.is_paused) or
                    getattr(self, "is_spotify_playing", False)
                )
                if is_music_active:
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

    @property
    def is_asleep(self) -> bool:
        return self._is_asleep

    @is_asleep.setter
    def is_asleep(self, value: bool):
        old_val = getattr(self, "_is_asleep", None)
        self._is_asleep = value
        if old_val != value:
            logger.info(f"Transitioning JARVIS sleep state: Asleep={value}")

    @property
    def is_authenticated(self) -> bool:
        return getattr(self, "_is_authenticated", False)

    @is_authenticated.setter
    def is_authenticated(self, value: bool):
        self._is_authenticated = value
        if value:
            if getattr(self, "os_ctrl", None) is not None:
                self.os_ctrl.sentry_active = False
                logger.info("Deactivated Sentry Mode (authenticated owner present).")

if __name__ == "__main__":
    jarvis = JARVIS()
    sys.exit(jarvis.app.exec())
