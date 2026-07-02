import sys
import sounddevice as sd
import numpy as np
import tempfile
import wave
import os
from faster_whisper import WhisperModel
from loguru import logger


class AudioEngine:
    """Handles microphone recording with VAD and Whisper STT"""

    def __init__(self, sample_rate: int = 16000, silence_sec: float = 1.5):
        self.sample_rate = sample_rate
        self.silence_sec = silence_sec
        # We use a simple RMS energy threshold for Voice Activity Detection
        self.energy_threshold = 100  
        self.last_avg_rms = 100.0
        self.last_speech_rate = 3.0
        self.latest_raw_audio = None
        logger.info("Loading Whisper model (base)...")
        try:
            # Try to load Whisper on GPU (CUDA)
            self.whisper = WhisperModel("base", device="cuda", compute_type="int8_float16")
            
            # Force lazy-loaded CUDA DLL checks by transcribing a silent dummy buffer
            dummy_audio = np.zeros(16000, dtype=np.int16)
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                tmp_path = f.name
                with wave.open(tmp_path, "wb") as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(16000)
                    wav.writeframes(dummy_audio.tobytes())
            try:
                # Evaluate generator to trigger library loading
                list(self.whisper.transcribe(tmp_path)[0])
                logger.info("Whisper loaded on GPU (CUDA) and verified successfully.")
            finally:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"Failed to load/verify Whisper on GPU (CUDA): {e}. Falling back to CPU.")
            self.whisper = WhisperModel("base", device="cpu", compute_type="int8")
            logger.info("Whisper loaded on CPU")
        self.is_speaking_cb = None
        self.sarvam_config = {}
        try:
            import yaml
            config_path = "config/settings.yaml"
            if not os.path.exists(config_path):
                config_path = os.path.join(os.path.dirname(__file__), "..", config_path)
            if os.path.exists(config_path):
                with open(config_path, "r") as f:
                    settings = yaml.safe_load(f) or {}
                    self.sarvam_config = settings.get("sarvam", {})
        except Exception as config_err:
            logger.warning(f"AudioEngine: Failed to load settings.yaml: {config_err}")

    def _is_speech(self, chunk: bytes) -> bool:
        try:
            # Simple RMS energy check
            audio_data = np.frombuffer(chunk, dtype=np.int16)
            rms = np.sqrt(np.mean(np.square(audio_data.astype(np.float32))))
            return rms > self.energy_threshold
        except Exception:
            return False

    def listen(self, timeout_sec: float = 4.0) -> str | None:
        """Record until silence, return transcribed text"""
        logger.info("JARVIS: Listening...")
        sys.stdout.write("JARVIS: Listening...\n")
        sys.stdout.flush()
        frame_duration = 30  # ms
        frame_size = int(self.sample_rate * frame_duration / 1000)
        silence_frames_needed = int(self.silence_sec * 1000 / frame_duration)
        
        # Max recording length: 12 seconds to prevent infinite hangs
        max_duration_sec = 12.0
        max_frames = int(max_duration_sec * 1000 / frame_duration)

        audio_frames = []
        silence_count = 0
        speaking = False
        max_silence_before_start = int(timeout_sec * 1000 / frame_duration) 


        with sd.RawInputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="int16",
            blocksize=frame_size,
        ) as stream:
            # Calibrate threshold on the fly using the first 5 frames (150ms)
            calibration_rms = []
            for _ in range(5):
                try:
                    data, _ = stream.read(frame_size)
                    chunk = bytes(data)
                    audio_data = np.frombuffer(chunk, dtype=np.int16)
                    rms = np.sqrt(np.mean(np.square(audio_data.astype(np.float32))))
                    calibration_rms.append(rms)
                except Exception:
                    calibration_rms.append(100.0)
            
            avg_noise_rms = np.mean(calibration_rms)
            # Cap the ambient noise floor at 25.0 during calibration to prevent the threshold
            # from being inflated if the user starts speaking immediately after the wake word.
            if avg_noise_rms > 25.0:
                avg_noise_rms = 25.0
                
            # Threshold is 3x the ambient noise floor, or at least 30 to support quiet microphones
            self.energy_threshold = max(avg_noise_rms * 3.0, 30.0)
            logger.debug(f"VAD Calibrated: Ambient Noise RMS = {avg_noise_rms:.1f}, Energy Threshold = {self.energy_threshold:.1f}")

            pre_start_count = 0
            while True:
                # If TTS is speaking, clear buffer and wait to prevent self-listening feedback
                if self.is_speaking_cb and self.is_speaking_cb():
                    audio_frames.clear()
                    speaking = False
                    silence_count = 0
                    time.sleep(0.05)
                    continue

                data, _ = stream.read(frame_size)
                chunk = bytes(data)
                is_speech = self._is_speech(chunk)

                if is_speech:
                    speaking = True
                    silence_count = 0
                    audio_frames.append(chunk)
                elif speaking:
                    silence_count += 1
                    audio_frames.append(chunk)
                    if silence_count >= silence_frames_needed:
                        break
                else:
                    pre_start_count += 1
                    if pre_start_count > max_silence_before_start:
                        logger.debug("No speech detected (timeout).")
                        return None  # no speech detected
                
                # Check maximum recording duration
                if len(audio_frames) >= max_frames:
                    logger.debug("Maximum command recording duration reached (12s). Stopping.")
                    break

        if not audio_frames:
            return None

        # Calculate average RMS of all recorded frames to filter out silence hallucinations
        all_data = np.frombuffer(b"".join(audio_frames), dtype=np.int16)
        self.latest_raw_audio = all_data.astype(np.float32) / 32768.0
        avg_rms = np.sqrt(np.mean(np.square(all_data.astype(np.float32))))
        self.last_avg_rms = avg_rms
        
        # Discard if the overall average RMS is below our speech threshold
        min_speech_rms = max(self.energy_threshold * 1.3, 50.0)
        if avg_rms < min_speech_rms:
            logger.debug(f"Recorded audio average RMS {avg_rms:.1f} is below speech threshold {min_speech_rms:.1f}. Discarding as silence.")
            return None
            
        logger.debug(f"Transcribing audio with average RMS: {avg_rms:.1f}")

        # Save to temp wav and transcribe
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp_path = f.name
            with wave.open(tmp_path, "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(self.sample_rate)
                wav.writeframes(b"".join(audio_frames))

        try:
            # Set initial prompt to guide Whisper towards correct English and Hinglish song names in Roman script
            initial_prompt = "Hey JARVIS, play some songs, gaana bajao, lagao, Arijit Singh, Shreya Ghoshal, Kaise Hua, Tum Hi Ho, Apna Bana Le, play music, play bollywood songs"
            segments, info = self.whisper.transcribe(tmp_path, language="en", initial_prompt=initial_prompt)
            local_text = " ".join(s.text for s in segments).strip()

            # Post-processing filter for common Whisper hallucinations on low-energy signals
            hallucinations = {"thank you very much.", "thank you.", "and listen to today.", "you.", "and listen to today", "please.", "please"}
            if local_text.lower().strip(" .!,?") in hallucinations and avg_rms < min_speech_rms * 1.5:
                logger.debug(f"Discarding suspected Whisper hallucination: '{local_text}' (RMS: {avg_rms:.1f})")
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
                return None

            # Check if Sarvam AI STT is enabled and we have an API key
            api_key = os.getenv("SARVAM_API_KEY") or self.sarvam_config.get("api_key")
            if self.sarvam_config.get("enabled", False) and api_key:
                # Detect Hindi/Hinglish cues
                has_devanagari = any('\u0900' <= c <= '\u097F' for c in local_text)
                hindi_triggers = {
                    "karo", "kholo", "chalao", "batao", "gaana", "kya", "kaise", "band", "lagao", 
                    "ha", "nahin", "nahi", "tum", "mera", "aap", "hu", "hai", "tha", "raha", "kar", 
                    "se", "ko", "par", "ek", "yeh", "woh", "suno", "namaste", "shukriya", "bataiye"
                }
                words_clean = set(local_text.lower().replace(",", "").replace(".", "").replace("!", "").replace("?", "").split())
                has_hindi_words = not words_clean.isdisjoint(hindi_triggers)

                if has_devanagari or has_hindi_words:
                    try:
                        from sarvamai import SarvamAI
                        client = SarvamAI(api_subscription_key=api_key)
                        logger.info("Hindi/Hinglish cues detected. Transcribing with Sarvam AI Saaras v3...")
                        with open(tmp_path, "rb") as audio_file:
                            response = client.speech.to_text(
                                file=audio_file,
                                model="saaras:v3",
                                mode="transcribe",
                                language_code=self.sarvam_config.get("language", "hi-IN")
                            )
                        
                        sarvam_text = ""
                        if isinstance(response, dict):
                            sarvam_text = response.get("transcript", "")
                        elif hasattr(response, "transcript"):
                            sarvam_text = getattr(response, "transcript", "")
                        else:
                            sarvam_text = str(response)
                            
                        logger.info(f"Sarvam AI STT Transcribed: '{sarvam_text}'")
                        try:
                            os.unlink(tmp_path)
                        except Exception:
                            pass
                        return sarvam_text.strip()
                    except Exception as sarvam_err:
                        logger.error(f"Sarvam AI STT error: {sarvam_err}. Falling back to local Whisper result.")

            # If not Hindi/Hinglish or Sarvam disabled, return local Whisper result directly
            logger.info(f"Local Whisper Transcribed: '{local_text}'")
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
            return local_text
            
            # Post-processing filter for common Whisper hallucinations on low-energy signals
            hallucinations = {"thank you very much.", "thank you.", "and listen to today.", "you.", "and listen to today", "please.", "please"}
            if text.lower().strip(" .!,?") in hallucinations and avg_rms < min_speech_rms * 1.5:
                logger.debug(f"Discarding suspected Whisper hallucination: '{text}' (RMS: {avg_rms:.1f})")
                return None
                
            # Filter out repetitive phrase hallucinations (e.g. "play music, play music, play music")
            words = text.lower().replace(",", "").replace(".", "").replace("!", "").replace("?", "").split()
            if len(words) > 3:
                from collections import Counter
                counts = Counter(words)
                most_common_word, count = counts.most_common(1)[0]
                if count / len(words) > 0.5:
                    logger.debug(f"Discarding suspected repetitive word/phrase hallucination: '{text}' (RMS: {avg_rms:.1f})")
                    return None
                    
            # Filter out numeric hallucinations (e.g. "4-0-0-0-0-0-0-0" or "1 0 0 0 0 0") on low-energy signals
            clean_text = text.replace("-", "").replace(" ", "").strip()
            if clean_text.isdigit() and len(clean_text) > 4 and avg_rms < min_speech_rms * 2.0:
                logger.debug(f"Discarding suspected numeric Whisper hallucination: '{text}' (RMS: {avg_rms:.1f})")
                return None
                
            # Calculate speech rate (syllables per second)
            duration_sec = len(audio_frames) * 0.03
            duration_sec = max(duration_sec, 0.5)
            words_list = text.split()
            if words_list:
                import re
                syllables = sum(max(1, len(re.findall(r'[aeiouy]+', w.lower()))) for w in words_list)
                self.last_speech_rate = syllables / duration_sec
                logger.debug(f"Computed speech rate: {self.last_speech_rate:.2f} syllables/sec over {duration_sec:.2f}s")
            else:
                self.last_speech_rate = 3.0

            logger.info(f"JARVIS Heard: {text}")
            sys.stdout.write(f"JARVIS Heard: {text}\n")
            sys.stdout.flush()
            return text if text else None
        except Exception as e:
            logger.error(f"Transcription error: {e}")
            return None
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    def listen_raw(self, timeout_sec: float = 4.0) -> np.ndarray | None:
        """Records until silence (VAD) and returns the raw float32 normalized audio data."""
        frame_duration = 30  # ms
        frame_size = int(self.sample_rate * frame_duration / 1000)
        silence_frames_needed = int(self.silence_sec * 1000 / frame_duration)
        
        max_duration_sec = 8.0
        max_frames = int(max_duration_sec * 1000 / frame_duration)

        audio_frames = []
        silence_count = 0
        speaking = False
        max_silence_before_start = int(timeout_sec * 1000 / frame_duration) 

        with sd.RawInputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="int16",
            blocksize=frame_size,
        ) as stream:
            # Calibrate threshold on the fly using the first 5 frames (150ms)
            calibration_rms = []
            for _ in range(5):
                try:
                    data, _ = stream.read(frame_size)
                    chunk = bytes(data)
                    audio_data = np.frombuffer(chunk, dtype=np.int16)
                    rms = np.sqrt(np.mean(np.square(audio_data.astype(np.float32))))
                    calibration_rms.append(rms)
                except Exception:
                    calibration_rms.append(100.0)
            
            avg_noise_rms = np.mean(calibration_rms)
            if avg_noise_rms > 25.0:
                avg_noise_rms = 25.0
                
            self.energy_threshold = max(avg_noise_rms * 3.0, 30.0)

            pre_start_count = 0
            while True:
                data, _ = stream.read(frame_size)
                chunk = bytes(data)
                is_speech = self._is_speech(chunk)

                if is_speech:
                    speaking = True
                    silence_count = 0
                    audio_frames.append(chunk)
                elif speaking:
                    silence_count += 1
                    audio_frames.append(chunk)
                    if silence_count >= silence_frames_needed:
                        break
                else:
                    pre_start_count += 1
                    if pre_start_count > max_silence_before_start:
                        return None
                
                if len(audio_frames) >= max_frames:
                    break

        if not audio_frames:
            return None

        # Convert to float32 normalized
        all_bytes = b"".join(audio_frames)
        audio_np = np.frombuffer(all_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        return audio_np




if __name__ == "__main__":
    engine = AudioEngine()
    print("Speak now...")
    text = engine.listen()
    print(f"Transcription: {text}")
