import pyaudio
import numpy as np
import os
import yaml
from openwakeword.model import Model
from loguru import logger

class WakeWordDetector:
    """Listens in the background for the wake word using OpenWakeWord"""

    def __init__(self, config_path: str = "config/settings.yaml"):
        # Resolve config path gracefully based on current working directory
        if not os.path.exists(config_path):
            # Fallback for testing when running inside the core directory
            fallback = os.path.join(os.path.dirname(__file__), "..", config_path)
            if os.path.exists(fallback):
                config_path = fallback

        try:
            with open(config_path) as f:
                settings = yaml.safe_load(f)
                self.audio_config = settings.get("audio", {})
        except Exception as e:
            logger.warning(f"Failed to load config: {e}. Using default settings.")
            self.audio_config = {}
            
        self.wake_word = "hey_jarvis"
        self.sensitivity = self.audio_config.get("wake_word_sensitivity", 0.5)
        self.oww_model = None

        logger.info(f"Loading OpenWakeWord model for '{self.wake_word}'...")
        self._load_model()


        self.audio = pyaudio.PyAudio()

    def _load_model(self):
        """Load OWW model, auto-downloading if missing."""
        import openwakeword
        model_dir = os.path.join(
            os.path.dirname(openwakeword.__file__), "resources", "models"
        )
        model_file = os.path.join(model_dir, "hey_jarvis_v0.1.onnx")

        if not os.path.exists(model_file):
            logger.info("hey_jarvis model not found. Downloading via openwakeword...")
            try:
                openwakeword.utils.download_models(["hey_jarvis"])
                logger.info("hey_jarvis model downloaded successfully.")
            except Exception as e:
                logger.error(f"Failed to download wake word model: {e}")
                logger.warning("Wake word disabled. JARVIS will listen continuously (press Enter to trigger).")
                return

        try:
            self.oww_model = Model(wakeword_models=[self.wake_word], inference_framework="onnx")
            logger.info("Wake word model loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load wake word model: {e}")
            self.oww_model = None

    def listen_for_wake_word(self) -> bool:

        """Blocks and continuously records audio until the wake word is detected."""
        # Fallback: if model failed to load, use keyboard Enter as trigger
        if self.oww_model is None:
            logger.warning("Wake word model unavailable. Press Enter to trigger JARVIS...")
            try:
                input()
                return True
            except (EOFError, KeyboardInterrupt):
                return False

        logger.info(f"Listening for wake word: '{self.wake_word}'...")
        
        # openwakeword requires 16000Hz, mono, 16-bit audio
        FORMAT = pyaudio.paInt16
        CHANNELS = 1
        RATE = 16000
        CHUNK = 1280

        stream = self.audio.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            frames_per_buffer=CHUNK
        )

        try:
            while True:
                data = stream.read(CHUNK, exception_on_overflow=False)
                audio_data = np.frombuffer(data, dtype=np.int16)
                
                # Feed the audio frames to openwakeword
                prediction = self.oww_model.predict(audio_data)
                
                # Check prediction confidence against our threshold
                for mdl, score in prediction.items():
                    if score >= self.sensitivity:
                        logger.success(f"Wake word detected! (Score: {score:.2f})")
                        return True
                        
        except KeyboardInterrupt:
            logger.info("Wake word listening stopped by user.")
            return False
        except Exception as e:
            logger.error(f"Wake word detection error: {e}")
            return False
        finally:
            if stream:
                stream.stop_stream()
                stream.close()

if __name__ == "__main__":
    detector = WakeWordDetector()
    print("Say 'Hey JARVIS' to test wake word detection.")
    if detector.listen_for_wake_word():
        print("Wake word successfully triggered!")
