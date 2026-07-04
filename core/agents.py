from core.agency import Agent, Message
from loguru import logger

class SwarmAgent(Agent):
    """Unified base class for all JARVIS swarm agents holding reference to the main application orchestrator."""
    def __init__(self, name: str, jarvis, agency=None):
        super().__init__(name, agency)
        self.jarvis = jarvis

# ==========================================
# 1. Core Agents (15)
# ==========================================
class AudioEngineAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        logger.debug(f"AudioEngineAgent: processing action '{msg.action}'")

class TtsEngineAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        if msg.action == "speak":
            text = msg.content.get("text", "")
            self.jarvis.tts.speak(text)

class WakeWordAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        logger.debug(f"WakeWordAgent: processing action '{msg.action}'")

class VoiceAuthAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        logger.debug(f"VoiceAuthAgent: processing action '{msg.action}'")

class IntentRouterAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        logger.debug(f"IntentRouterAgent: processing action '{msg.action}'")

class BrainAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        logger.debug(f"BrainAgent: processing action '{msg.action}'")

class CognitiveAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        logger.debug(f"CognitiveAgent: processing action '{msg.action}'")

class ContextSentinelAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        logger.debug(f"ContextSentinelAgent: processing action '{msg.action}'")

class ProactiveMonitorAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        logger.debug(f"ProactiveMonitorAgent: processing action '{msg.action}'")

class FocusTrackerAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        logger.debug(f"FocusTrackerAgent: processing action '{msg.action}'")

class ProfileManagerAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        logger.debug(f"ProfileManagerAgent: processing action '{msg.action}'")

class VisionEngineAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        logger.debug(f"VisionEngineAgent: processing action '{msg.action}'")

class SensoryHealthAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        logger.debug(f"SensoryHealthAgent: processing action '{msg.action}'")

class AirTypistAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        logger.debug(f"AirTypistAgent: processing action '{msg.action}'")

class P2PLinkAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        logger.debug(f"P2PLinkAgent: processing action '{msg.action}'")


# ==========================================
# 2. Domain Expert Agents (7)
# ==========================================
class BusinessDomainAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        logger.debug(f"BusinessDomainAgent: processing action '{msg.action}'")

class DevelopmentDomainAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        logger.debug(f"DevelopmentDomainAgent: processing action '{msg.action}'")

class EngineeringDomainAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        logger.debug(f"EngineeringDomainAgent: processing action '{msg.action}'")

class FinanceDomainAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        logger.debug(f"FinanceDomainAgent: processing action '{msg.action}'")

class MedicalDomainAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        logger.debug(f"MedicalDomainAgent: processing action '{msg.action}'")

class ScienceDomainAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        logger.debug(f"ScienceDomainAgent: processing action '{msg.action}'")

class SecurityDomainAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        logger.debug(f"SecurityDomainAgent: processing action '{msg.action}'")


# ==========================================
# 3. Action Skill Agents (30)
# ==========================================
class AppControlAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        logger.debug(f"AppControlAgent: processing action '{msg.action}'")

class AppMapperAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        logger.debug(f"AppMapperAgent: processing action '{msg.action}'")

class CodeRunnerAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        logger.debug(f"CodeRunnerAgent: processing action '{msg.action}'")

class CodingSandboxAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        logger.debug(f"CodingSandboxAgent: processing action '{msg.action}'")

class DataAnalyzerAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        logger.debug(f"DataAnalyzerAgent: processing action '{msg.action}'")

class EmergencySentinelAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        logger.debug(f"EmergencySentinelAgent: processing action '{msg.action}'")

class FileManagerAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        logger.debug(f"FileManagerAgent: processing action '{msg.action}'")

class FoodComparatorAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        logger.debug(f"FoodComparatorAgent: processing action '{msg.action}'")

class GestureControlAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        logger.debug(f"GestureControlAgent: processing action '{msg.action}'")

class GitSentinelAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        logger.debug(f"GitSentinelAgent: processing action '{msg.action}'")

class MacroRecorderAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        logger.debug(f"MacroRecorderAgent: processing action '{msg.action}'")

class MarketAnalyzerAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        logger.debug(f"MarketAnalyzerAgent: processing action '{msg.action}'")

class MediaSummarizerAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        logger.debug(f"MediaSummarizerAgent: processing action '{msg.action}'")

class NetworkMapperAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        logger.debug(f"NetworkMapperAgent: processing action '{msg.action}'")

class ObsidianControlAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        logger.debug(f"ObsidianControlAgent: processing action '{msg.action}'")

class OsControlAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        logger.debug(f"OsControlAgent: processing action '{msg.action}'")

class PhoneControllerAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        logger.debug(f"PhoneControllerAgent: processing action '{msg.action}'")

class PolyglotEngineerAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        logger.debug(f"PolyglotEngineerAgent: processing action '{msg.action}'")

class ProductivityAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        logger.debug(f"ProductivityAgent: processing action '{msg.action}'")

class ProductComparatorAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        logger.debug(f"ProductComparatorAgent: processing action '{msg.action}'")

class ResearchProdigyAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        logger.debug(f"ResearchProdigyAgent: processing action '{msg.action}'")

class ScreenVisionAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        logger.debug(f"ScreenVisionAgent: processing action '{msg.action}'")

class SecurityAuditorAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        logger.debug(f"SecurityAuditorAgent: processing action '{msg.action}'")

class SelfHealingVisionAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        logger.debug(f"SelfHealingVisionAgent: processing action '{msg.action}'")

class SentryFirewallAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        logger.debug(f"SentryFirewallAgent: processing action '{msg.action}'")

class SpotifyControlAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        logger.debug(f"SpotifyControlAgent: processing action '{msg.action}'")

class VisionTrackerAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        logger.debug(f"VisionTrackerAgent: processing action '{msg.action}'")

class WebResearchAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        logger.debug(f"WebResearchAgent: processing action '{msg.action}'")

class WorkspaceContextAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        logger.debug(f"WorkspaceContextAgent: processing action '{msg.action}'")

class YoutubeMusicAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        logger.debug(f"YoutubeMusicAgent: processing action '{msg.action}'")
