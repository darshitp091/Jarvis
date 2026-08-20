import cv2
import base64
import os
import tempfile
import ollama
import yaml
from loguru import logger

class VisionTracker:
    """Uses local camera inputs, opencv enhancements, and local VLM to recognize objects, evaluate stress/fatigue, and compensate for low light."""

    def __init__(self, camera_engine, config_path: str = "config/settings.yaml"):
        self.camera = camera_engine
        
        # Resolve config
        if not os.path.exists(config_path):
            fallback = os.path.join(os.path.dirname(__file__), "..", config_path)
            if os.path.exists(fallback):
                config_path = fallback
                
        try:
            with open(config_path) as f:
                settings = yaml.safe_load(f)
                self.model = settings.get("models", {}).get("vision", "moondream:latest")
        except Exception:
            self.model = "moondream:latest"

    def compensate_low_light(self, frame) -> tuple[bool, any]:
        """Applies Contrast Limited Adaptive Histogram Equalization (CLAHE) to compensate for low light (Night Vision)."""
        if frame is None:
            return False, None
            
        try:
            # Convert BGR to YUV to extract luminance channel
            yuv = cv2.cvtColor(frame, cv2.COLOR_BGR2YUV)
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
            yuv[:, :, 0] = clahe.apply(yuv[:, :, 0])
            enhanced_frame = cv2.cvtColor(yuv, cv2.COLOR_YUV2BGR)
            logger.info("Night vision contrast compensation applied.")
            return True, enhanced_frame
        except Exception as e:
            logger.error(f"Low light compensation failed: {e}")
            return False, frame

    def _get_active_frame_b64(self, night_vision: bool = False) -> tuple[str, str] | None:
        """Grabs the latest camera frame, applies night vision if needed, and returns (path, base64_str)."""
        frame = self.camera.latest_frame
        if frame is None:
            # Try to grab video handle directly
            cap = cv2.VideoCapture(self.camera.camera_index)
            if cap.isOpened():
                ret, frame = cap.read()
                cap.release()
                
        if frame is None:
            return None
            
        if night_vision:
            _, frame = self.compensate_low_light(frame)
            
        # Resize frame to max size 640x480 to speed up VLM processing and reduce memory
        if frame is not None:
            h, w = frame.shape[:2]
            if w > 640 or h > 480:
                scaling = min(640.0 / w, 480.0 / h)
                frame = cv2.resize(frame, (int(w * scaling), int(h * scaling)), interpolation=cv2.INTER_AREA)
            
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            path = f.name
            
        cv2.imwrite(path, frame)
        
        try:
            with open(path, "rb") as f_img:
                b64 = base64.b64encode(f_img.read()).decode()
            return path, b64
        except Exception as e:
            logger.error(f"Failed to encode frame: {e}")
            try: os.remove(path)
            except Exception: pass
            return None

    def detect_objects_in_room(self, night_vision: bool = False) -> str:
        """Uses the local camera feed and VLM to identify objects in the room."""
        logger.info("Detecting objects in room...")
        res = self._get_active_frame_b64(night_vision=night_vision)
        if not res:
            return "Sir, my optical sensors are currently offline. Please ensure the webcam is connected."
            
        path, b64 = res
        try:
            prompt = "What objects do you identify in the room? List them clearly."
            response = ollama.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt, "images": [b64]}],
                keep_alive="10s"
            )
            return response["message"]["content"].strip()
        except Exception as e:
            logger.error(f"Object detection failed: {e}")
            return "I encountered an error trying to process the visual frame, sir."
        finally:
            try: os.remove(path)
            except Exception: pass



    def analyze_user_fatigue_and_stress(self, night_vision: bool = False) -> str:
        """Uses camera feed and local VLM to identify stress or fatigue indicators (tired eyes, yawning, body language)."""
        logger.info("Analyzing user fatigue and stress levels...")
        res = self._get_active_frame_b64(night_vision=night_vision)
        if not res:
            return "Sir, I cannot access your camera feed to analyze fatigue indicators."
            
        path, b64 = res
        try:
            prompt = (
                "Analyze the person in this image. Does the user show signs of stress, fatigue, tiredness (like closed/heavy eyes, yawning, head resting on hand)? "
                "Describe their fatigue status and facial expression in one brief, direct sentence."
            )
            response = ollama.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt, "images": [b64]}],
                keep_alive="10s"
            )
            return response["message"]["content"].strip()
        except Exception as e:
            logger.error(f"Fatigue analysis failed: {e}")
            return "I had trouble analyzing your fatigue levels, sir."
        finally:
            try: os.remove(path)
            except Exception: pass

    def analyze_user_appearance(self, prompt: str = "Analyze the person's clothing and suggest matching colors") -> str:
        """Uses the webcam feed to analyze the user's outfit and make color recommendations."""
        logger.info("Analyzing user clothing appearance...")
        res = self._get_active_frame_b64(night_vision=False)
        if not res:
            return "Sir, I cannot access your camera feed to analyze your attire."
            
        path, b64 = res
        try:
            full_prompt = (
                f"Analyze the person in this image. {prompt}. "
                "Describe what they are wearing (colors, style) and recommend 2-3 colors that would match or fit well on them."
            )
            response = ollama.chat(
                model=self.model,
                messages=[{"role": "user", "content": full_prompt, "images": [b64]}],
                keep_alive="10s"
            )
            return response["message"]["content"].strip()
        except Exception as e:
            logger.error(f"User appearance analysis failed: {e}")
            return "I had trouble analyzing your appearance, sir."
        finally:
            try: os.remove(path)
            except Exception: pass
