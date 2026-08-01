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

# OpenRouter's OpenAI-compatible speech endpoint.
OPENROUTER_SPEECH_URL = "https://openrouter.ai/api/v1/audio/speech"


class TTSEngine:
    """Expressive TTS with pluggable backends.

    Backends:
      * ``fish``  - Fish Audio S2.1 Pro via OpenRouter. Most human/expressive.
      * ``edge``  - Microsoft Edge TTS. Fast, offline-ish, no API key.
      * SAPI      - last-resort Windows fallback, used automatically.

    Selection comes from ``tts.engine`` in settings.yaml and can be overridden
    per call via ``speak(..., engine="edge")``. If the primary backend raises,
    we degrade to the next one rather than going silent.
    """

    def __init__(self, default_voice: str = "hinglish", default_speed: float = 1.15):
        self.default_voice = default_voice
        self.default_speed = default_speed
        self.interrupted = False
        self.on_speak_start = None
        self.on_speak_end = None
        self.is_speaking = False
        # Read by main.py's barge-in monitor to suppress self-triggering on
        # JARVIS's own audio onset. Must be set every time speech begins.
        self.speak_start_time = 0.0

        # Defaults first, so a missing/broken config can never leave these unset.
        self.settings = {}
        self.voices_config = {}
        self.default_pitch = -12
        self.engine = "edge"
        self.fish_conf = {}
        self._fish_key_warned = False

        try:
            import yaml
            config_path = "config/settings.yaml"
            if not os.path.exists(config_path):
                config_path = os.path.join(os.path.dirname(__file__), "..", config_path)
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    self.settings = yaml.safe_load(f) or {}
                tts_conf = self.settings.get("tts", {}) or {}
                self.default_voice = tts_conf.get("default_voice", default_voice)
                self.voices_config = tts_conf.get("voices", {}) or {}
                self.default_speed = tts_conf.get("speaking_rate", default_speed)
                self.default_pitch = tts_conf.get("speaking_pitch", -12)
                self.engine = str(tts_conf.get("engine", "edge") or "edge").lower()
                self.fish_conf = tts_conf.get("fish_audio", {}) or {}
        except Exception as config_err:
            logger.warning(f"TTSEngine: Failed to load settings.yaml: {config_err}")

        logger.info(f"TTS Engine initialized (backend: {self.engine}).")
        self._sweep_stale_temps()

    # ------------------------------------------------------------------ utils

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

    @staticmethod
    def _temp_dir() -> str:
        """Scratch space for synthesis artifacts. Gitignored, cleaned per call."""
        d = os.path.join("scratch", "tts")
        os.makedirs(d, exist_ok=True)
        return d

    def _sweep_stale_temps(self, max_age_s: int = 900):
        """Delete orphaned synthesis artifacts from previous runs.

        Per-call cleanup lives in a ``finally``, but a hard kill mid-playback
        (JARVIS closed while speaking, daemon thread torn down at exit) skips
        it. Without this sweep those files accumulate in scratch/ forever.
        """
        try:
            now = time.time()
            for name in os.listdir(self._temp_dir()):
                fp = os.path.join(self._temp_dir(), name)
                try:
                    if os.path.isfile(fp) and (now - os.path.getmtime(fp)) > max_age_s:
                        os.remove(fp)
                except Exception:
                    pass
        except Exception:
            pass

    def _temp_mp3(self, prefix: str) -> str:
        return os.path.join(
            self._temp_dir(),
            f"{prefix}_{int(time.time())}_{random.randint(100, 999)}.mp3",
        )

    # ------------------------------------------------------------- fish audio

    def _resolve_fish_key(self) -> str:
        """API key from settings.yaml, else OPENROUTER_API_KEY env var."""
        key = (self.fish_conf.get("api_key") or "").strip()
        if not key:
            key = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
        return key

    def _synthesize_fish(self, text: str):
        """POST to OpenRouter and return ``(samples, sample_rate)``.

        Despite the docs example writing an ``.mp3``, this endpoint returns
        headerless raw PCM (``audio/pcm;rate=44100;channels=1``). We parse the
        real rate/channels off the Content-Type and decode with NumPy, so no
        ffmpeg round-trip is needed on this path.

        Raises on any non-audio response so the caller can fall back.
        """
        import requests  # lazy, mirrors edge_tts/pedalboard import style

        key = self._resolve_fish_key()
        if not key:
            raise RuntimeError(
                "Fish Audio selected but no API key found "
                "(set tts.fish_audio.api_key or OPENROUTER_API_KEY)."
            )

        model = self.fish_conf.get("model") or "fish-audio/s2.1-pro-free:free"
        timeout = float(self.fish_conf.get("timeout", 30))

        # The documented endpoint takes only model+input. Everything else is
        # sent solely when explicitly configured, so we never break the
        # contract with speculative fields.
        payload = {"model": model, "input": text}
        for cfg_key, api_key_name in (
            ("voice", "voice"),
            ("speed", "speed"),
            ("response_format", "response_format"),
        ):
            val = self.fish_conf.get(cfg_key)
            if val not in (None, ""):
                payload[api_key_name] = val

        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        referer = (self.fish_conf.get("http_referer") or "").strip()
        title = (self.fish_conf.get("app_title") or "").strip()
        if referer:
            headers["HTTP-Referer"] = referer
        if title:
            headers["X-OpenRouter-Title"] = title

        resp = requests.post(
            OPENROUTER_SPEECH_URL, headers=headers, json=payload, timeout=timeout
        )

        if resp.status_code != 200:
            detail = resp.text[:300] if resp.text else f"HTTP {resp.status_code}"
            raise RuntimeError(f"OpenRouter TTS failed ({resp.status_code}): {detail}")

        ctype = (resp.headers.get("Content-Type") or "").lower()
        # A JSON body on a 200 means an error envelope, not audio.
        if "json" in ctype:
            raise RuntimeError(f"OpenRouter returned JSON, not audio: {resp.text[:300]}")
        if not resp.content:
            raise RuntimeError("OpenRouter returned an empty audio body.")

        gen_id = resp.headers.get("X-Generation-Id")
        logger.info(
            f"Fish Audio synthesized {len(resp.content)} bytes [{ctype or 'unknown type'}]"
            + (f" (generation {gen_id})" if gen_id else "")
        )

        return self._decode_audio_response(resp.content, ctype)

    @staticmethod
    def _parse_pcm_params(ctype: str):
        """Pull rate/channels out of e.g. ``audio/pcm;rate=44100;channels=1``."""
        rate, channels = 44100, 1
        for part in ctype.split(";")[1:]:
            if "=" not in part:
                continue
            k, _, v = part.partition("=")
            try:
                if k.strip() == "rate":
                    rate = int(v.strip())
                elif k.strip() == "channels":
                    channels = int(v.strip())
            except ValueError:
                pass
        return rate, channels

    def _decode_audio_response(self, raw: bytes, ctype: str):
        """Decode an API audio body to ``(float32 mono samples, rate)``."""
        if "pcm" in ctype:
            rate, channels = self._parse_pcm_params(ctype)
            samples = np.frombuffer(raw, dtype="<i2")
            if channels > 1:
                usable = (samples.size // channels) * channels
                samples = samples[:usable].reshape(-1, channels).mean(axis=1)
            # int16 -> float32 in [-1, 1] for the shared playback path.
            audio = (samples.astype(np.float32) / 32768.0).flatten()
            if audio.size == 0:
                raise RuntimeError("Decoded PCM contained no samples.")
            return audio, rate

        # Container formats (mp3/wav/opus) if the API is ever configured for them.
        tmp = self._temp_mp3("fish_raw")
        try:
            with open(tmp, "wb") as f:
                f.write(raw)
            audio, rate = self._decode_container(tmp)
            return audio, rate
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except Exception:
                    pass

    # -------------------------------------------------------------- playback

    def _decode_container(self, path: str):
        """Convert a container file to 24kHz mono float32 via ffmpeg."""
        wav_path = os.path.splitext(path)[0] + "_dec.wav"
        try:
            cmd = ["ffmpeg", "-y", "-i", path, "-ar", "24000", "-ac", "1", wav_path]
            res = subprocess.run(cmd, capture_output=True)
            if res.returncode != 0:
                raise RuntimeError(
                    f"FFmpeg conversion failed: {res.stderr.decode('utf-8', errors='ignore')}"
                )
            audio, sr = sf.read(wav_path, dtype="float32")
            return audio.flatten(), sr
        finally:
            if os.path.exists(wav_path):
                try:
                    os.remove(wav_path)
                except Exception:
                    pass

    def _play_samples(self, audio, sr: int, whisper: bool, telephone: bool, base_vol: float):
        """Apply DSP and play, honouring barge-in. Shared by every backend."""
        if audio is None or len(audio) == 0:
            return

        from pedalboard import Pedalboard, HighpassFilter, LowpassFilter
        dsp_effects = []
        if whisper:
            dsp_effects.append(HighpassFilter(cutoff_frequency_hz=1000))
            base_vol *= 0.25
        elif telephone:
            dsp_effects.append(HighpassFilter(cutoff_frequency_hz=350))
            dsp_effects.append(LowpassFilter(cutoff_frequency_hz=3200))

        if dsp_effects:
            audio = Pedalboard(dsp_effects)(audio, sr)

        if base_vol != 1.0:
            audio = audio * base_vol

        # Pad silence to prevent audio pops
        silence = np.zeros(int(0.1 * sr), dtype=np.float32)
        audio = np.concatenate([silence, audio])

        sd.play(audio, sr)
        try:
            stream = sd.get_stream()
            while stream.active:
                if self.interrupted:
                    sd.stop()
                    break
                time.sleep(0.02)
        except Exception:
            # No queryable stream; block until done so we still honour timing.
            sd.wait()

    def _play_mp3(self, mp3_path: str, whisper: bool, telephone: bool, base_vol: float):
        """Decode a container file and play it, cleaning up afterwards."""
        try:
            audio, sr = self._decode_container(mp3_path)
            self._play_samples(audio, sr, whisper, telephone, base_vol)
        finally:
            if os.path.exists(mp3_path):
                try:
                    os.remove(mp3_path)
                except Exception:
                    pass

    # ------------------------------------------------------------ edge backend

    async def _edge_download(self, text: str, voice_name: str, rate_str: str,
                             pitch_str: str, volume_str: str, out_path: str):
        import edge_tts
        communicate = edge_tts.Communicate(
            text, voice_name, rate=rate_str, pitch=pitch_str, volume=volume_str
        )
        await communicate.save(out_path)

    def _speak_edge(self, text: str, voice: str, speed: float, volume: float,
                    whisper: bool, telephone: bool):
        """Edge TTS path, including its rule-based rate/pitch emotion mapping."""
        clean_text, emotion, rate_off, pitch_off = self._parse_emotion_rules(text)
        if not clean_text:
            return

        spk = voice if voice else self.default_voice
        if spk not in self.voices_config:
            spk = "hinglish"
        voice_params = self.voices_config.get(spk, {}) or {}
        ref_speaker = voice_params.get("ref_speaker", "hi-IN-SwaraNeural")

        base_speed = speed if speed else self.default_speed
        rate_percentage = int((base_speed - 1.0) * 100) + rate_off
        rate_str = f"{'+' if rate_percentage >= 0 else ''}{rate_percentage}%"
        pitch_val = self.default_pitch + pitch_off
        pitch_str = f"{'+' if pitch_val >= 0 else ''}{pitch_val}Hz"

        logger.info(
            f"Synthesizing Edge TTS ({ref_speaker}) | Emotion: {emotion or 'neutral'} "
            f"| Text: '{clean_text[:60]}...'"
        )

        mp3_path = self._temp_mp3("edge")
        try:
            asyncio.run(
                self._edge_download(clean_text, ref_speaker, rate_str, pitch_str, "+0%", mp3_path)
            )
        except Exception:
            if os.path.exists(mp3_path):
                try:
                    os.remove(mp3_path)
                except Exception:
                    pass
            raise
        self._play_mp3(mp3_path, whisper, telephone, volume)

    # ------------------------------------------------------------ fish backend

    # Bracket tags emitted by the LLM (see config/prompts.yaml) mapped to the
    # natural-language cues Fish responds to. Measured: a parenthetical cue
    # raises pitch variation to ~8st vs ~2.7st for the bare sentence, so
    # stripping these outright was discarding the main expressiveness signal.
    FISH_EMOTION_CUES = {
        "laugh": "laughing",
        "excited": "excitedly",
        "happy": "cheerfully",
        "energetic": "energetically",
        "thoughtful": "thoughtfully",
        "sigh": "sighing",
        "sad": "sadly",
        "serious": "seriously",
        "laziness": "wearily",
        "whisper": "whispering",
    }

    def _prepare_fish_text(self, text: str) -> str:
        """Translate ``[laugh]``-style tags into cues Fish actually honours.

        The first recognised tag becomes a leading parenthetical (Fish reads
        these as delivery direction); any remaining tags are dropped so they
        are never spoken aloud as literal words.
        """
        cue = None
        for tag, spoken in self.FISH_EMOTION_CUES.items():
            if f"[{tag}]" in text.lower():
                cue = spoken
                break
        body = re.sub(r'\[.*?\]', '', text).strip()
        body = re.sub(r'\s{2,}', ' ', body)
        if not body:
            return ""
        return f"({cue}) {body}" if cue else body

    def _speak_fish(self, text: str, volume: float, whisper: bool, telephone: bool):
        """Fish Audio path. Emotion cues are passed through, not stripped."""
        prepared = self._prepare_fish_text(text)
        if not prepared:
            return
        logger.info(f"Synthesizing Fish Audio S2.1 | Text: '{prepared[:70]}...'")
        audio, sr = self._synthesize_fish(prepared)
        self._play_samples(audio, sr, whisper, telephone, volume)

    # ----------------------------------------------------------------- public

    def speak(self, text: str, voice: str = None, speed: float = None, lang: str = None,
              volume: float = 1.0, whisper: bool = False, telephone: bool = False,
              engine: str = None):
        """Synthesize and play speech, degrading gracefully across backends."""
        if not text:
            return

        self.is_speaking = True
        self.interrupted = False
        self.speak_start_time = time.time()

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

        # Strip code blocks from spoken output
        spoken_text = text
        if "```" in spoken_text:
            spoken_text = re.sub(
                r"```[a-zA-Z0-9\-\_]*\n(.*?)\n```",
                " [Code output generated and displayed on screen, sir.] ",
                spoken_text,
                flags=re.DOTALL
            )

        chosen = (engine or self.engine or "edge").lower()
        if chosen in ("fish", "fish_audio", "fishaudio"):
            if not self._resolve_fish_key():
                if not self._fish_key_warned:
                    logger.warning(
                        "tts.engine is 'fish' but no API key is configured; using Edge TTS."
                    )
                    self._fish_key_warned = True
                chosen = "edge"

        try:
            if chosen in ("fish", "fish_audio", "fishaudio"):
                try:
                    self._speak_fish(spoken_text, volume, whisper, telephone)
                except Exception as fish_err:
                    logger.warning(f"Fish Audio failed ({fish_err}); falling back to Edge TTS.")
                    self._speak_edge(spoken_text, voice, speed, volume, whisper, telephone)
            else:
                self._speak_edge(spoken_text, voice, speed, volume, whisper, telephone)
        except Exception as e:
            logger.error(f"TTS generation error: {e}")
            clean_text = re.sub(r'\[.*?\]', '', spoken_text).strip()
            if clean_text:
                self._fallback_speak(clean_text)
        finally:
            self.is_speaking = False
            if self.on_speak_end:
                try:
                    self.on_speak_end()
                except Exception as cb_err:
                    logger.error(f"Error in on_speak_end: {cb_err}")

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
        """Speak a random filler while the main model thinks.

        Fillers run on Edge by default: they fire on nearly every command, and
        spending a rate-limited free Fish quota on throwaway phrases would
        starve the real answers. Set tts.fish_audio.use_for_fillers: true to
        override.
        """
        filler_engine = "fish" if self.fish_conf.get("use_for_fillers") else "edge"
        self.speak(random.choice(FILLER_PHRASES), engine=filler_engine)


if __name__ == "__main__":
    engine = TTSEngine()
    engine.speak(
        "Namaste sir, kaise hain aap? I am speaking using the new Fish Audio engine. "
        "Let's analyze the code error."
    )
