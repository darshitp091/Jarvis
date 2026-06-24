import pyaudio
import numpy as np
import os
import yaml
import time
from openwakeword.model import Model
from loguru import logger
from collections import deque
import scipy.fftpack as fftpack
import json

def compute_mean_mfcc(audio_data: np.ndarray, sample_rate: int = 16000) -> np.ndarray:
    """Extracts mean MFCC coefficients (excluding the 0-th coefficient) for speaker verification."""
    if audio_data.dtype != np.float32:
        audio_data = audio_data.astype(np.float32)
        if np.max(np.abs(audio_data)) > 1.0:
            audio_data /= 32768.0

    # Pre-emphasis
    signal = np.append(audio_data[0], audio_data[1:] - 0.97 * audio_data[:-1])
    
    # Framing (25ms window, 10ms step)
    frame_len = int(0.025 * sample_rate)
    frame_step = int(0.010 * sample_rate)
    signal_len = len(signal)
    
    if signal_len <= frame_len:
        pad_len = frame_len + 1
        signal = np.pad(signal, (0, pad_len - signal_len), mode='constant')
        signal_len = len(signal)
        
    num_frames = int(np.ceil(float(np.abs(signal_len - frame_len)) / frame_step)) + 1
    pad_signal_len = num_frames * frame_step + frame_len
    pad_signal = np.pad(signal, (0, pad_signal_len - signal_len), mode='constant')
    
    indices = np.tile(np.arange(0, frame_len), (num_frames, 1)) + \
              np.tile(np.arange(0, num_frames * frame_step, frame_step), (frame_len, 1)).T
    frames = pad_signal[indices.astype(np.int32, copy=False)]
    
    # Hamming window
    frames *= np.hamming(frame_len)
    
    # FFT
    NFFT = 512
    mag_frames = np.absolute(np.fft.rfft(frames, NFFT))
    pow_frames = ((1.0 / NFFT) * ((mag_frames) ** 2))
    
    # Mel Filterbanks (26 filters)
    num_filters = 26
    low_freq_mel = 0
    high_freq_mel = (2595 * np.log10(1 + (sample_rate / 2.0) / 700.0))
    mel_points = np.linspace(low_freq_mel, high_freq_mel, num_filters + 2)
    hz_points = (700 * (10**(mel_points / 2595.0) - 1))
    bin = np.floor((NFFT + 1) * hz_points / sample_rate)
    
    fbank = np.zeros((num_filters, int(NFFT / 2 + 1)))
    for m in range(1, num_filters + 1):
        f_m_minus = int(bin[m - 1])
        f_m = int(bin[m])
        f_m_plus = int(bin[m + 1])
        
        for k in range(f_m_minus, f_m):
            fbank[m - 1, k] = (k - bin[m - 1]) / (bin[m] - bin[m - 1])
        for k in range(f_m, f_m_plus):
            fbank[m - 1, k] = (bin[m + 1] - k) / (bin[m + 1] - bin[m])
            
    filter_banks = np.dot(pow_frames, fbank.T)
    filter_banks = np.where(filter_banks == 0, np.finfo(float).eps, filter_banks)
    filter_banks = 20 * np.log10(filter_banks)
    
    # DCT to get 13 MFCCs
    mfccs = fftpack.dct(filter_banks, type=2, axis=1, norm='ortho')[:, :13]
    mean_mfcc = np.mean(mfccs, axis=0)
    return mean_mfcc

def cosine_similarity(v1: np.ndarray, v2: np.ndarray) -> float:
    # Exclude 0-th coefficient (energy) for spectral shape matching
    v1_cut = v1[1:]
    v2_cut = v2[1:]
    norm1 = np.linalg.norm(v1_cut)
    norm2 = np.linalg.norm(v2_cut)
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return float(np.dot(v1_cut, v2_cut) / (norm1 * norm2))

class WakeWordDetector:
    """Listens in the background for the wake word using OpenWakeWord or STT fallback"""

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
                self.jarvis_config = settings.get("jarvis", {})
        except Exception as e:
            logger.warning(f"Failed to load config: {e}. Using default settings.")
            self.audio_config = {}
            self.jarvis_config = {}
            
        self.wake_word = self.jarvis_config.get("wake_word", "hey jarvis").lower().replace(" ", "_")
        self.sensitivity = self.audio_config.get("wake_word_sensitivity", 0.5)
        self.oww_model = None
        self.use_stt_fallback = False
        self.whisper_model = None

        # Check if the wake word is supported by default pre-trained openwakeword models
        built_in_words = ["hey_jarvis", "alexa", "hey_siri", "ok_google", "hey_mycroft"]
        if self.wake_word not in built_in_words:
            logger.info(f"Custom wake word '{self.wake_word}' detected. Activating STT fallback wake engine.")
            self.use_stt_fallback = True
        else:
            logger.info(f"Loading OpenWakeWord model for '{self.wake_word}'...")
            self._load_model()

        self.audio = pyaudio.PyAudio()
        self.voice_profile_path = "config/voice_profile.json"
        self._load_voice_profile()

    def _load_voice_profile(self):
        self.voice_profile = None
        if os.path.exists(self.voice_profile_path):
            try:
                with open(self.voice_profile_path, "r") as f:
                    self.voice_profile = json.load(f)
                logger.info("Speaker verification voice profile loaded successfully.")
            except Exception as e:
                logger.error(f"Failed to load voice profile: {e}")

    def verify_speaker(self, audio_data: np.ndarray) -> bool:
        """Verifies if the audio matches the enrolled owner voice profile."""
        if not self.voice_profile:
            # Voice profile not setup yet, pass by default
            return True
            
        try:
            # 1. Reject too short audio chunks immediately (less than 0.5s)
            if len(audio_data) < 8000:
                logger.debug("Speaker verification failed: Audio signal too short.")
                return False

            # 2. Check if audio is actually voiced (non-silent)
            rms = np.sqrt(np.mean(audio_data.astype(np.float32)**2))
            if rms < 0.002: # arbitrary small threshold for normalized float32
                logger.debug("Speaker verification failed: Audio signal too weak.")
                return False
                
            # 3. Extract input MFCC mean
            input_mean = compute_mean_mfcc(audio_data)
            
            # 4. Compare with enrolled profile
            profile_mean = np.array(self.voice_profile["mean_vector"])
            threshold = self.voice_profile.get("threshold", 0.78)
            
            # Dynamically lower threshold if music is active to account for acoustic distortion
            if getattr(self, "is_music_playing_cb", None) and self.is_music_playing_cb():
                old_threshold = threshold
                threshold = max(0.68, threshold - 0.06)
                logger.info(f"Speaker Verification: Music active. Dynamically adjusted threshold from {old_threshold:.3f} to {threshold:.3f}")

            sim = cosine_similarity(input_mean, profile_mean)
            logger.info(f"Speaker Verification: Cosine Similarity = {sim:.3f} (Threshold: {threshold:.3f})")
            
            if sim >= threshold:
                logger.success("Speaker Verification: Owner voice verified!")
                
                # Dynamic Voice Print Adaptation
                if sim >= 0.93:
                    alpha = 0.08  # Adapt rate (8% weight to new sample)
                    new_mean = alpha * input_mean + (1.0 - alpha) * profile_mean
                    self.voice_profile["mean_vector"] = new_mean.tolist()
                    try:
                        with open(self.voice_profile_path, "w") as f:
                            json.dump(self.voice_profile, f, indent=2)
                        logger.info(f"Speaker Verification: Dynamically updated owner voice print profile (similarity = {sim:.3f}).")
                    except Exception as save_err:
                        logger.error(f"Failed to update voice profile: {save_err}")
                        
                return True
            else:
                logger.warning(f"Speaker Verification: Rejecting trigger (voice similarity {sim:.3f} < {threshold:.3f})")
                return False
        except Exception as e:
            logger.error(f"Error in speaker verification: {e}")
            return False # Safe fallback: reject on failure

    def _denoise_audio(self, audio_data: np.ndarray) -> np.ndarray:
        """Bypasses spectral subtraction to prevent latency and audio feature distortion."""
        return audio_data



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
        if getattr(self, "use_stt_fallback", False):
            return self._listen_stt_fallback()

        # Fallback: if model failed to load, use keyboard Enter as trigger
        if self.oww_model is None:
            logger.warning("Wake word model unavailable. Press Enter to trigger assistant...")
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

        recent_frames = deque(maxlen=25) # keep last 2 seconds of audio chunks

        try:
            while True:
                data = stream.read(CHUNK, exception_on_overflow=False)
                audio_data = np.frombuffer(data, dtype=np.int16)
                
                # Real-Time Spectral Denoising before processing
                denoised_audio = self._denoise_audio(audio_data)
                recent_frames.append(denoised_audio.tobytes())
                
                # Feed the denoised audio frames to openwakeword
                prediction = self.oww_model.predict(denoised_audio)
                
                # Check prediction confidence against our threshold
                for mdl, score in prediction.items():
                    if score >= self.sensitivity:
                        logger.success(f"Wake word detected! (Score: {score:.2f})")
                        
                        # Concatenate rolling buffer to get audio segment for verification
                        recorded_audio = b"".join(recent_frames)
                        audio_np = np.frombuffer(recorded_audio, dtype=np.int16).astype(np.float32) / 32768.0
                        
                        if self.verify_speaker(audio_np):
                            return True
                        else:
                            logger.info("Speaker verification rejected trigger. Flushing audio and starting 1.5s cooldown...")
                            time.sleep(1.5)
                            try:
                                stream.stop_stream()
                                stream.start_stream()
                            except Exception as stream_err:
                                logger.error(f"Failed to restart PyAudio stream: {stream_err}")
                            recent_frames.clear()
                            try:
                                self.oww_model.reset()
                            except Exception:
                                try:
                                    from openwakeword.model import Model
                                    self.oww_model = Model(wakeword_models=[self.wake_word], inference_framework="onnx")
                                except Exception as reset_err:
                                    logger.error(f"Failed to reset OpenWakeWord model: {reset_err}")
                        
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

    def _listen_stt_fallback(self) -> bool:
        """Fallback STT wake word listener using a local CPU-based Whisper tiny.en model with sounddevice."""
        import sounddevice as sd
        from faster_whisper import WhisperModel
        import numpy as np
        import tempfile
        import wave
        import os

        if self.whisper_model is None:
            logger.info("Initializing GPU-based Whisper tiny.en model for custom wake word detection...")
            try:
                self.whisper_model = WhisperModel("tiny.en", device="cuda", compute_type="int8_float16")
                logger.info("Whisper tiny.en model initialized on GPU successfully.")
            except Exception as gpu_err:
                logger.warning(f"Failed to load Whisper on GPU: {gpu_err}. Falling back to CPU.")
                try:
                    self.whisper_model = WhisperModel("tiny.en", device="cpu", compute_type="int8")
                    logger.info("Whisper tiny.en model initialized on CPU successfully.")
                except Exception as e:
                    logger.error(f"Failed to initialize Whisper model on CPU: {e}")
                    # Fallback to keypress
                    logger.warning("Press Enter to trigger assistant...")
                    try:
                        input()
                        return True
                    except (EOFError, KeyboardInterrupt):
                        return False

        logger.info(f"Listening for custom wake word: '{self.wake_word.replace('_', ' ')}'...")
        
        sample_rate = 16000
        frame_duration = 30  # ms
        frame_size = int(sample_rate * frame_duration / 1000)
        silence_needed = int(0.4 * 1000 / frame_duration) # 0.4 seconds of silence to stop recording

        try:
            with sd.RawInputStream(
                samplerate=sample_rate,
                channels=1,
                dtype="int16",
                blocksize=frame_size,
            ) as stream:
                # 1. Calibrate VAD threshold on the fly
                calibration_rms = []
                for _ in range(10): # ~300ms calibration
                    try:
                        data, _ = stream.read(frame_size)
                        chunk = bytes(data)
                        audio_data = np.frombuffer(chunk, dtype=np.int16)
                        rms = np.sqrt(np.mean(audio_data.astype(np.float32)**2))
                        calibration_rms.append(rms)
                    except Exception:
                        calibration_rms.append(50.0)
                
                avg_noise_rms = np.mean(calibration_rms)
                if avg_noise_rms > 25.0:
                    avg_noise_rms = 25.0
                
                threshold = max(avg_noise_rms * 3.0, 30.0)
                logger.debug(f"Wake VAD Calibrated: Noise RMS = {avg_noise_rms:.1f}, Threshold = {threshold:.1f}")

                recording = False
                frames = []
                silence_count = 0
                max_listening_duration_sec = 8.0 # Max length of single utterance
                max_frames = int(max_listening_duration_sec * 1000 / frame_duration)

                # Normalize the configured wake word search term
                target_word = self.wake_word.replace("_", " ").lower() # e.g. "hey jarvis"
                
                # Define phonetic triggers to catch common transcription variants
                phonetic_matches = [target_word]
                if "jarvis" in target_word:
                    phonetic_matches.extend([
                        "jarvis", "jarves", "jarv", "garvis", "java", "charvis", "service",
                        "hey jarvis", "hey java", "hey service", "jaeves", "travis", "jervis"
                    ])

                while True:
                    data, _ = stream.read(frame_size)
                    chunk = bytes(data)
                    audio_data = np.frombuffer(chunk, dtype=np.int16)
                    rms = np.sqrt(np.mean(audio_data.astype(np.float32)**2))

                    if rms > threshold:
                        if not recording:
                            logger.debug("Voice activity detected...")
                            recording = True
                            frames = []
                        frames.append(chunk)
                        silence_count = 0
                    else:
                        if recording:
                            frames.append(chunk)
                            silence_count += 1
                            if silence_count >= silence_needed:
                                logger.debug("Speech finished. Transcribing...")
                                recording = False
                                
                                audio_bytes = b"".join(frames)
                                audio_np = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
                                
                                # Transcribe with very fast settings
                                segments, _ = self.whisper_model.transcribe(audio_np, beam_size=1)
                                transcription = " ".join([seg.text for seg in segments]).lower().strip()
                                logger.debug(f"Wake transcription: '{transcription}'")
                                
                                if any(phrase in transcription for phrase in phonetic_matches):
                                    logger.info(f"JARVIS: Wake word detected! ('{transcription}')")
                                    if self.verify_speaker(audio_np):
                                        return True
                                    else:
                                        frames = []
                                        silence_count = 0
                                        time.sleep(0.2)
                                        continue
                                
                                logger.debug("Wake word not matched. Resetting listening...")
                                frames = []
                                silence_count = 0
                                time.sleep(0.2)
                    
                    if recording and len(frames) >= max_frames:
                        logger.debug("Maximum wake recording duration reached. Transcribing...")
                        recording = False
                        audio_bytes = b"".join(frames)
                        audio_np = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
                        segments, _ = self.whisper_model.transcribe(audio_np, beam_size=1)
                        transcription = " ".join([seg.text for seg in segments]).lower().strip()
                        logger.debug(f"Wake transcription: '{transcription}'")
                        if any(phrase in transcription for phrase in phonetic_matches):
                            logger.info(f"JARVIS: Wake word detected! ('{transcription}')")
                            if self.verify_speaker(audio_np):
                                return True
                        frames = []
                        silence_count = 0
                        time.sleep(0.2)
            
        except Exception as e:
            logger.error(f"Error in custom wake word listener: {e}")
            time.sleep(1.0)
            return False

if __name__ == "__main__":
    detector = WakeWordDetector()
    phrase = detector.wake_word.replace("_", " ").title()
    print(f"Say '{phrase}' to test wake word detection.")
    if detector.listen_for_wake_word():
        print("Wake word successfully triggered!")
