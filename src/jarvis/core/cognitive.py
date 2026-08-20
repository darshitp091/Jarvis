import re
from loguru import logger

class CognitiveSentimentTracker:
    """Analyzes text semantics and acoustic volume levels to predict user sentiment state."""
    
    def __init__(self):
        self.sentiment_state = "calm" # Default state
        
    def analyze(self, text: str = "", avg_rms: float = 100.0) -> str:
        """Classify user state into: calm, stressed, fatigued, excited"""
        if not text:
            return self.sentiment_state
            
        cmd = text.lower().strip()
        
        # 1. Text Keyword Semantics
        fatigued_words = ["tired", "exhausted", "sleepy", "fatigue", "yawns", "bored", "lazy", "slow down", "rest"]
        stressed_words = ["panic", "stressed", "broken", "bug", "crash", "error", "fault", "urgent", "failed", "help me", "problem", "hang"]
        excited_words = ["awesome", "great", "cool", "wonderful", "excited", "happy", "yes!", "stark", "amazing", "wohoo", "yeah", "love"]
        
        text_sentiment = None
        if any(w in cmd for w in fatigued_words):
            text_sentiment = "fatigued"
        elif any(w in cmd for w in stressed_words):
            text_sentiment = "stressed"
        elif any(w in cmd for w in excited_words):
            text_sentiment = "excited"
            
        # 2. Acoustic Volume Features (avg_rms)
        # Standard quiet microphone voice is typically ~30-60, normal speaking ~70-160.
        acoustic_sentiment = None
        if avg_rms > 280.0:
            acoustic_sentiment = "stressed" if text_sentiment == "stressed" else "excited"
        elif avg_rms < 40.0:
            acoustic_sentiment = "fatigued"
            
        # 3. Decision Logic Fusion
        if text_sentiment and acoustic_sentiment:
            self.sentiment_state = text_sentiment
        elif text_sentiment:
            self.sentiment_state = text_sentiment
        elif acoustic_sentiment:
            self.sentiment_state = acoustic_sentiment
        else:
            self.sentiment_state = "calm"
            
        logger.info(f"Cognitive Sentiment Tracker -> State: {self.sentiment_state.upper()} (Acoustic RMS: {avg_rms:.1f})")
        return self.sentiment_state
