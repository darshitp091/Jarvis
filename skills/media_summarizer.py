import yt_dlp
import tempfile
import os
from faster_whisper import WhisperModel
import ollama
import yaml
from loguru import logger


class MediaSummarizer:
    """Summarize YouTube videos, local audio/video, and long media"""

    def __init__(self, config_path: str = "config/settings.yaml"):
        # Resolve config path gracefully based on current working directory
        if not os.path.exists(config_path):
            fallback = os.path.join(os.path.dirname(__file__), "..", config_path)
            if os.path.exists(fallback):
                config_path = fallback

        try:
            with open(config_path) as f:
                settings = yaml.safe_load(f)
                self.model = settings.get("models", {}).get("main_brain", "qwen2.5")
        except Exception as e:
            logger.warning(f"Failed to load config: {e}. Defaulting to qwen2.5")
            self.model = "qwen2.5"

        logger.info("Loading Whisper model for media transcription...")
        self.whisper = WhisperModel("base.en", device="cpu", compute_type="int8")

    def summarize_youtube(self, url: str) -> str:
        """Downloads audio from a YouTube URL and summarizes it"""
        with tempfile.TemporaryDirectory() as tmpdir:
            opts = {
                "format": "bestaudio/best",
                "outtmpl": f"{tmpdir}/audio.%(ext)s",
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "wav",
                }],
                "quiet": True,
            }
            try:
                logger.info(f"Downloading audio from: {url}")
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([url])

                audio_file = next(
                    (os.path.join(tmpdir, f) for f in os.listdir(tmpdir) if f.endswith(".wav")),
                    None
                )
                if not audio_file:
                    return "Could not download audio, sir."

                return self._transcribe_and_summarize(audio_file)
            except Exception as e:
                logger.error(f"YouTube error: {e}")
                return "Failed to process the YouTube video, sir. Please check the URL or your connection."

    def summarize_local(self, file_path: str) -> str:
        """Transcribes and summarizes a local audio or video file"""
        if not os.path.exists(file_path):
            return "I could not find that file, sir."
            
        return self._transcribe_and_summarize(file_path)

    def _transcribe_and_summarize(self, audio_path: str) -> str:
        """Core logic to run STT and feed the transcript to the LLM"""
        try:
            logger.info("Transcribing audio...")
            segments, _ = self.whisper.transcribe(audio_path)
            transcript = " ".join(s.text for s in segments)

            if len(transcript) < 50:
                return "The media didn't contain enough intelligible speech to summarize, sir."

            logger.info("Summarizing transcript via LLM...")
            # We slice transcript[:8000] roughly to prevent exceeding standard context windows
            response = ollama.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are JARVIS. Summarize the following transcript into 5 key bullet points. Be concise and extract the most important information."},
                    {"role": "user", "content": f"Transcript:\n{transcript[:8000]}"}
                ]
            )
            return response["message"]["content"]
        except Exception as e:
            logger.error(f"Summarize error: {e}")
            return "Transcription or summarization failed, sir."


if __name__ == "__main__":
    summarizer = MediaSummarizer()
    print("\nMedia Summarizer Module Loaded Successfully.")
    print("Example usage:")
    print("summary = summarizer.summarize_youtube('https://www.youtube.com/watch?v=dQw4w9WgXcQ')")
    
    # Note: To fully test it, you need ffmpeg installed in your system PATH.
