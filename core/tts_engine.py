import os
import random
import sounddevice as sd
import subprocess
from loguru import logger

import numpy as np

# Monkey-patch numpy.load to allow pickle loading for Kokoro voices-v1.0.bin
orig_load = np.load
def patched_load(*args, **kwargs):
    kwargs['allow_pickle'] = True
    return orig_load(*args, **kwargs)
np.load = patched_load

try:
    from kokoro_onnx import Kokoro
except ImportError:
    Kokoro = None
    logger.warning("kokoro_onnx not installed. Please run `pip install kokoro-onnx`")

FILLER_PHRASES = [
    "On it, sir.",
    "Let me check that.",
    "Right away.",
    "Looking into that now.",
    "One moment.",
    "Certainly.",
    "Consider it done.",
    "Already on it.",
]

class TTSEngine:
    """Kokoro TTS for human-like voice output with support for multiple languages and accents."""

    def __init__(self, model_path: str = "kokoro-v1.0.onnx", voices_path: str = "voices-v1.0.bin", default_voice: str = "af_heart", default_speed: float = 1.0):
        self.model_path = model_path
        self.voices_path = voices_path
        self.default_voice = default_voice
        self.default_speed = default_speed
        self.kokoro = None
        self.interrupted = False
        
        self.on_speak_start = None
        self.on_speak_end = None
        
        self._load_kokoro()

    def _load_kokoro(self):
        if not Kokoro:
            return

        try:
            if not os.path.exists(self.model_path):
                logger.warning(f"Kokoro model not found at {self.model_path}. You might need to download it.")
                logger.info("Run: wget https://github.com/thewh1teagle/kokoro-onnx/releases/download/model/kokoro-v1.0.onnx")
            if not os.path.exists(self.voices_path):
                logger.warning(f"Kokoro voices json not found at {self.voices_path}. You might need to download it.")
                logger.info("Run: wget https://github.com/thewh1teagle/kokoro-onnx/releases/download/model/voices.json")
            
            if os.path.exists(self.model_path) and os.path.exists(self.voices_path):
                # Ensure espeak-ng is installed and in path, which Kokoro uses under the hood for phonemizing
                import onnxruntime as rt
                if "CUDAExecutionProvider" in rt.get_available_providers():
                    os.environ["ONNX_PROVIDER"] = "CUDAExecutionProvider"
                    logger.info("Attempting to load Kokoro TTS with CUDA Execution Provider...")
                else:
                    os.environ["ONNX_PROVIDER"] = "CPUExecutionProvider"
                
                try:
                    self.kokoro = Kokoro(self.model_path, self.voices_path)
                    logger.info("Kokoro TTS loaded successfully")
                except Exception as gpu_err:
                    logger.warning(f"Failed to load Kokoro with GPU/CUDA: {gpu_err}. Retrying on CPU.")
                    os.environ["ONNX_PROVIDER"] = "CPUExecutionProvider"
                    self.kokoro = Kokoro(self.model_path, self.voices_path)
                    logger.info("Kokoro TTS loaded successfully on CPU")
        except Exception as e:
            logger.error(f"Failed to load Kokoro: {e}")

    def speak(self, text: str, voice: str = None, speed: float = None, lang: str = "en-us", volume: float = 1.0, whisper: bool = False):
        """Speak text aloud using Kokoro with adjustable speed, volume, and whisper support."""
        if not text:
            return
            
        import time
        self.speak_start_time = time.time()
        self.interrupted = False
        use_voice = voice if voice else self.default_voice
        use_speed = speed if speed is not None else self.default_speed
        
        if whisper:
            volume = 0.25
            use_speed = 0.8
            logger.info("Whisper mode enabled for speech output.")
            
        if self.on_speak_start:
            try:
                self.on_speak_start()
            except Exception as cb_err:
                logger.error(f"Error in on_speak_start callback: {cb_err}")

        try:
            if self.kokoro:
                samples, sample_rate = self.kokoro.create(
                    text, voice=use_voice, speed=use_speed, lang=lang 
                )
                
                # Apply volume adjustment
                if volume != 1.0:
                    samples = samples * volume

                # Prepend a small silent padding (e.g. 0.2 seconds) to allow the audio output device
                # to initialize and wake up, avoiding the first syllable being cut off (e.g. "vis" instead of "Jarvis").
                silence_duration = 0.2  # seconds
                silence_samples = np.zeros(int(silence_duration * sample_rate), dtype=np.float32)
                samples = np.concatenate([silence_samples, samples])
                
                # Play audio using sounddevice asynchronously
                sd.play(samples, sample_rate)
                
                import time
                while sd.get_stream().active:
                    if self.interrupted:
                        sd.stop()
                        logger.info("Speech playback stopped mid-sentence via interruption signal.")
                        break
                    time.sleep(0.02)
                
                time.sleep(0.3)  # Clear room echo before microphone opens
            else:
                self._fallback_speak(text)
        except Exception as e:
            logger.error(f"TTS error: {e}")
            self._fallback_speak(text)
        finally:
            if self.on_speak_end:
                try:
                    self.on_speak_end()
                except Exception as cb_err:
                    logger.error(f"Error in on_speak_end callback: {cb_err}")

    def stop_speech(self):
        """Stops active speech immediately."""
        self.interrupted = True
        try:
            sd.stop()
        except Exception:
            pass

    def _fallback_speak(self, text: str):
        """Fallback to Windows built-in TTS if Kokoro fails"""
        try:
            safe_text = text.replace("'", "''")
            cmd = f'powershell -Command "Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak(\'{safe_text}\')"'
            subprocess.run(cmd, shell=True)
            import time
            time.sleep(0.3)
        except Exception as e:
            logger.error(f"Fallback TTS failed: {e}")
            print(f"[JARVIS SAYS]: {text}")

    def speak_filler(self):
        """Speak a random filler while main model thinks"""
        self.speak(random.choice(FILLER_PHRASES))


if __name__ == "__main__":
    engine = TTSEngine()
    engine.speak("JARVIS online. All systems operational.")
    
    # Example for Indian English
    # engine.speak("Namaste, I am JARVIS. How can I assist you today?", lang="en-in")
