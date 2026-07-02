import os
import json
import numpy as np
from loguru import logger
from core.wake_word import compute_mean_mfcc, cosine_similarity

class VoiceAuthenticator:
    """Verifies spoken voice commands against the calibrated speaker profile."""

    def __init__(self, profile_path="config/voice_profile.json"):
        self.profile_path = profile_path
        self.mean_vector = None
        self.threshold = 0.75
        self.has_profile = False
        
        self.load_profile()

    def load_profile(self):
        """Loads the calibrated speaker profile vector and similarity threshold."""
        if not os.path.exists(self.profile_path):
            # Fallback path check
            fallback = os.path.join(os.path.dirname(__file__), "..", self.profile_path)
            if os.path.exists(fallback):
                self.profile_path = fallback
            else:
                logger.warning(f"Voice Auth: No speaker profile found at {self.profile_path}. Speaker verification is inactive.")
                return

        try:
            with open(self.profile_path, "r") as f:
                data = json.load(f)
            self.mean_vector = np.array(data["mean_vector"])
            self.threshold = float(data["threshold"])
            self.has_profile = True
            logger.info(f"Voice Auth: Calibrated speaker profile loaded (Threshold: {self.threshold:.3f}).")
        except Exception as e:
            logger.error(f"Voice Auth: Failed to load speaker profile: {e}")

    def verify_speaker(self, raw_audio: np.ndarray, sample_rate: int = 16000) -> tuple:
        """
        Compares the raw audio vector of the spoken command to the calibrated profile.
        Returns:
            (is_verified: bool, similarity: float)
        """
        # If no profile exists yet, allow execution but log warning (fail-open to avoid locking out the user)
        if not self.has_profile:
            logger.warning("Voice Auth: Speaker signature profile missing. Bypass validation.")
            return True, 1.0

        if raw_audio is None or len(raw_audio) == 0:
            logger.warning("Voice Auth: Empty audio command buffer received.")
            return False, 0.0

        try:
            # 1. Extract mean MFCC from the command audio
            cmd_mfcc = compute_mean_mfcc(raw_audio, sample_rate)
            
            # 2. Compute similarity against the profile's average vector
            similarity = cosine_similarity(self.mean_vector, cmd_mfcc)
            
            # 3. Check threshold
            is_verified = (similarity >= self.threshold)
            logger.info(f"Voice Auth: Verification result - Match: {is_verified} (Sim: {similarity:.4f}, Req: {self.threshold:.3f})")
            
            return is_verified, similarity
        except Exception as e:
            logger.error(f"Voice Auth: Error running speaker verification check: {e}")
            return False, 0.0
