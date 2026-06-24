import re
from loguru import logger

class EmergencySentinel:
    """Monitors vocal energy levels and semantic distress indicators to identify emergency situations."""

    def __init__(self):
        self.emergency_keywords = [
            "accident", "accidental", "hurt", "injured", "emergency", "pain", 
            "bleeding", "help me", "call doctor", "heart attack", "chest pain", 
            "stroke", "unconscious", "fire", "police", "ambulance", "break in", 
            "danger", "dying", "save me"
        ]

    def check_for_distress(self, text: str, avg_rms: float) -> dict | None:
        """Evaluates whether the user is in an active distress situation."""
        if not text:
            return None
            
        cmd = text.lower().strip()
        
        # 1. Semantic Check (Match emergency keywords)
        matched_keywords = [kw for kw in self.emergency_keywords if kw in cmd]
        
        # 2. Acoustic Check (Voice energy threshold > 330 indicating panicked shouting)
        is_acoustic_distress = avg_rms > 330.0
        
        if matched_keywords or is_acoustic_distress:
            logger.warning(f"EMERGENCY SENSING TRIGGERED! Keywords: {matched_keywords} | RMS: {avg_rms:.1f}")
            return {
                "distress": True,
                "keywords": matched_keywords,
                "rms": avg_rms,
                "is_shouted": is_acoustic_distress
            }
            
        return None
