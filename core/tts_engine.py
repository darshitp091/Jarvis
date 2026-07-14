import os
import sys
import random
import re
import time
import asyncio
import numpy as np
import sounddevice as sd
import soundfile as sf
import subprocess
from loguru import logger

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
    """High-Fidelity Edge TTS Engine with Punctuation & Rule-Based Emotion Mapping."""

    def __init__(self, default_voice: str = "hinglish", default_speed: float = 1.15):
        self.default_voice = default_voice
        self.default_speed = default_speed
        self.interrupted = False
        self.on_speak_start = None
        self.on_speak_end = None
        self.is_speaking = False
        
        # Load settings
        self.settings = {}
        try:
            import yaml
            config_path = "config/settings.yaml"
            if not os.path.exists(config_path):
                config_path = os.path.join(os.path.dirname(__file__), "..", config_path)
            if os.path.exists(config_path):
                with open(config_path, "r") as f:
                    self.settings = yaml.safe_load(f) or {}
                    tts_conf = self.settings.get("tts", {})
                    self.default_voice = tts_conf.get("default_voice", default_voice)
                    self.voices_config = tts_conf.get("voices", {})
                    self.default_speed = tts_conf.get("speaking_rate", default_speed)
                    self.default_pitch = tts_conf.get("speaking_pitch", -12)
        except Exception as config_err:
            logger.warning(f"TTSEngine: Failed to load settings.yaml: {config_err}")
            self.voices_config = {}
            self.default_pitch = -12

        logger.info("Edge TTS Engine initialized.")

    @staticmethod
    def _detect_language(text: str) -> str:
        """Auto-detect if text is Hindi/Hinglish or English based on content."""
        devanagari_count = sum(1 for c in text if '\u0900' <= c <= '\u097F')
        if devanagari_count > 2:
            return "hi"
        hindi_markers = ['hai', 'hoon', 'kya', 'nahi', 'aap', 'kaise', 'kar', 'rahi', 'raha',
                         'mein', 'main', 'yeh', 'woh', 'toh', 'bhi', 'aur', 'lekin', 'abhi',
                         'karo', 'dijiye', 'chaliye', 'thoda', 'bohot', 'bahut', 'accha',
                         'namaste', 'dhanyavaad', 'suno', 'bolo', 'dekho', 'chalo', 'sir',
                         'haan', 'ji', 'acha', 'theek', 'samajh', 'pata', 'kuch', 'sab']
        words = text.lower().split()
        hindi_word_count = sum(1 for w in words if w.strip('.,!?') in hindi_markers)
        if hindi_word_count >= 2 or (len(words) > 0 and hindi_word_count / max(len(words), 1) > 0.15):
            return "hi"
        return "en"

    def _parse_emotion_rules(self, text: str):
        """Rule-based emotion mapping from text context, punctuation, and keyword signals."""
        emotion = None
        # Detect legacy bracketed tags if present in LLM response
        for tag in ["excited", "thoughtful", "sigh", "sad", "laugh", "laziness", "happy", "serious", "energetic"]:
            if f"[{tag}]" in text.lower():
                emotion = tag
                break

        # Sentiment keywords and punctuation rules
        text_lower = text.lower()
        
        if "!" in text or any(w in text_lower for w in ["great", "perfect", "amazing", "awesome", "success", "yes!"]):
            if not emotion:
                emotion = "excited"
        elif "?" in text or any(w in text_lower for w in ["checking", "analyzing", "hmm", "let me see"]):
            if not emotion:
                emotion = "thoughtful"
        elif any(w in text_lower for w in ["sorry", "error", "failed", "broken", "unfortunately", "wrong"]):
            if not emotion:
                emotion = "serious"

        # Default voice offset adjustments (Hz-based, tuned to sound natural yet expressive)
        rate_offset = 0
        pitch_offset = 0

        if emotion in ["excited", "happy"]:
            rate_offset = 8       # Speed up slightly
            pitch_offset = 12     # Raise pitch (+12Hz for cheerfulness)
        elif emotion == "thoughtful":
            rate_offset = -6      # Slow down slightly
            pitch_offset = -3     # Lower pitch slightly
        elif emotion in ["sigh", "laziness"]:
            rate_offset = -10     # Slow down
            pitch_offset = -6     # Lower pitch (-6Hz for sigh/laziness)
        elif emotion in ["serious", "sad"]:
            rate_offset = -8      # Slow down
            pitch_offset = -8     # Lower pitch (-8Hz for sadness)
        elif emotion == "energetic":
            rate_offset = 12      # Speed up
            pitch_offset = 15     # Raise pitch (+15Hz)

        clean_text = re.sub(r'\[.*?\]', '', text).strip()
        return clean_text, emotion, rate_offset, pitch_offset

    def speak(self, text: str, voice: str = None, speed: float = None, lang: str = None, volume: float = 1.0, whisper: bool = False, telephone: bool = False):
        """Synthesize and play expressive Hinglish/English speech."""
        if not text:
            return

        self.is_speaking = True
        self.interrupted = False

        # Output text immediately to console
        try:
            sys.stdout.write(f"JARVIS Replied: {text}\n")
            sys.stdout.flush()
        except Exception:
            try:
                print(f"JARVIS Replied: {text.encode('ascii', errors='replace').decode('ascii')}")
            except Exception:
                pass

        if self.on_speak_start:
            try:
                self.on_speak_start()
            except Exception as cb_err:
                logger.error(f"Error in on_speak_start callback: {cb_err}")

        # Clean markdown code blocks from spoken output
        spoken_text = text
        if "```" in spoken_text:
            spoken_text = re.sub(
                r"```[a-zA-Z0-9\-\_]*\n(.*?)\n```",
                " [Code output generated and displayed on screen, sir.] ",
                spoken_text,
                flags=re.DOTALL
            )

        # Parse rule-based emotions
        clean_text, emotion, rate_off, pitch_off = self._parse_emotion_rules(spoken_text)
        if not clean_text:
            self.is_speaking = False
            return

        # Determine speaker profile
        spk = voice if voice else self.default_voice
        if spk not in self.voices_config:
            spk = "hinglish"
        voice_params = self.voices_config.get(spk, {})
        ref_speaker = voice_params.get("ref_speaker", "hi-IN-SwaraNeural")

        try:
            # Calculate speaking rate for Edge TTS (base rate + emotion offset)
            base_speed = speed if speed else self.default_speed
            # Base percentage offset from 1.0
            rate_percentage = int((base_speed - 1.0) * 100) + rate_off
            rate_str = f"{'+' if rate_percentage >= 0 else ''}{rate_percentage}%"
            pitch_val = getattr(self, "default_pitch", -12) + pitch_off
            pitch_str = f"{'+' if pitch_val >= 0 else ''}{pitch_val}Hz"
            volume_str = "+0%"

            logger.info(f"Synthesizing Edge TTS ({ref_speaker}) | Emotion: {emotion or 'neutral'} | Text: '{clean_text[:60]}...'")
            
            # Run asynchronous speech generation in a synchronous wrapper
            asyncio.run(self._speak_edge_async(clean_text, ref_speaker, rate_str, pitch_str, volume_str, whisper, telephone, volume))
        except Exception as e:
            logger.error(f"Edge TTS Generation Error: {e}")
            self._fallback_speak(clean_text)

    async def _speak_edge_async(self, text: str, voice_name: str, rate_str: str, pitch_str: str, volume_str: str, whisper: bool, telephone: bool, base_vol: float):
        """Asynchronously stream voice, convert format, and play live."""
        import edge_tts
        temp_dir = "scratch"
        os.makedirs(temp_dir, exist_ok=True)
        temp_mp3 = os.path.join(temp_dir, f"edge_{int(time.time())}_{random.randint(100, 999)}.mp3")
        temp_wav = temp_mp3.replace(".mp3", ".wav")

        try:
            # Generate Edge TTS MP3
            communicate = edge_tts.Communicate(text, voice_name, rate=rate_str, pitch=pitch_str, volume=volume_str)
            await communicate.save(temp_mp3)

            # Convert to 24kHz mono wav using ffmpeg
            cmd = ["ffmpeg", "-y", "-i", temp_mp3, "-ar", "24000", "-ac", "1", temp_wav]
            res = subprocess.run(cmd, capture_output=True)
            if res.returncode != 0:
                raise RuntimeError(f"FFmpeg conversion failed: {res.stderr.decode('utf-8', errors='ignore')}")

            # Load and play audio
            audio, sr = sf.read(temp_wav, dtype='float32')
            audio = audio.flatten()

            if audio is not None and len(audio) > 0:
                # Add environment effects (whisper/telephone) if requested
                from pedalboard import Pedalboard, HighpassFilter, LowpassFilter
                dsp_effects = []
                if whisper:
                    dsp_effects.append(HighpassFilter(cutoff_frequency_hz=1000))
                    base_vol *= 0.25
                elif telephone:
                    dsp_effects.append(HighpassFilter(cutoff_frequency_hz=350))
                    dsp_effects.append(LowpassFilter(cutoff_frequency_hz=3200))

                if dsp_effects:
                    active_board = Pedalboard(dsp_effects)
                    audio = active_board(audio, sr)

                if base_vol != 1.0:
                    audio *= base_vol

                # Pad silence to prevent audio pops
                silence = np.zeros(int(0.1 * sr), dtype=np.float32)
                audio = np.concatenate([silence, audio])

                sd.play(audio, sr)
                while sd.get_stream().active:
                    if self.interrupted:
                        sd.stop()
                        break
                    await asyncio.sleep(0.02)

        finally:
            self.is_speaking = False
            if self.on_speak_end:
                try:
                    self.on_speak_end()
                except Exception as cb_err:
                    logger.error(f"Error in on_speak_end: {cb_err}")

            # Clear temporary files
            for fp in [temp_mp3, temp_wav]:
                if os.path.exists(fp):
                    try:
                        os.remove(fp)
                    except Exception:
                        pass

    def stop_speech(self):
        """Stops active speech immediately."""
        self.interrupted = True
        try:
            sd.stop()
        except Exception:
            pass

    def _fallback_speak(self, text: str):
        """Fallback to Windows SAPI speech if everything fails."""
        try:
            safe_text = text.replace("'", "''")
            cmd = f'powershell -Command "Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak(\'{safe_text}\')"'
            subprocess.run(cmd, shell=True)
            time.sleep(0.3)
        except Exception as e:
            logger.error(f"Fallback SAPI failed: {e}")
            print(f"[JARVIS SAYS]: {text}")

    def speak_filler(self):
        """Speak a random filler while main model thinks."""
        self.speak(random.choice(FILLER_PHRASES))

if __name__ == "__main__":
    engine = TTSEngine()
    engine.speak("Namaste sir, kaise hain aap? [excited] I am speaking using high-fidelity edge tts! Let's analyze the code error.")
