import pyautogui
import base64
import tempfile
import ollama
import yaml
import os
import platform
from loguru import logger


class ScreenVision:
    """PaliGemma-powered screen analysis"""

    def __init__(self, config_path: str = "config/settings.yaml"):
        # Resolve config path gracefully based on current working directory
        if not os.path.exists(config_path):
            fallback = os.path.join(os.path.dirname(__file__), "..", config_path)
            if os.path.exists(fallback):
                config_path = fallback

        try:
            with open(config_path) as f:
                settings = yaml.safe_load(f)
                self.model = settings.get("models", {}).get("vision", "paligemma")
        except Exception as e:
            logger.warning(f"Failed to load vision model from config: {e}. Defaulting to paligemma.")
            self.model = "paligemma"

    def capture(self) -> str:
        """Take screenshot, save to temp file, return path"""
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            path = f.name
        screenshot = pyautogui.screenshot()
        # Resize to max width 1024 to speed up Ollama vision model and reduce memory usage
        screenshot.thumbnail((1024, 1024))
        screenshot.save(path)
        return path

    def analyze(self, question: str = "Describe what you see on the screen") -> str:
        path = self.capture()
        try:
            # 1. Retrieve Active Window Title
            active_title = "Unknown Application"
            try:
                import pygetwindow as gw
                active_win = gw.getActiveWindow()
                if active_win and active_win.title:
                    active_title = active_win.title
            except Exception:
                pass
                
            # 2. Retrieve OCR Text
            ocr_text = ""
            try:
                from PIL import Image
                import pytesseract
                if platform.system() == "Windows":
                    tesseract_path = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
                    if os.path.exists(tesseract_path):
                        pytesseract.pytesseract.tesseract_cmd = tesseract_path
                ocr_text = pytesseract.image_to_string(Image.open(path)).strip()
            except Exception:
                pass

            # 3. Compile context-aware visual query
            context_prompt = (
                f"User Question: {question}\n\n"
                f"OS Context (Active Window Title): '{active_title}'\n\n"
            )
            if ocr_text:
                context_prompt += f"OCR Extracted Screen Text:\n\"\"\"\n{ocr_text[:3000]}\n\"\"\"\n\n"
            context_prompt += "Using this OS metadata, text data, and the screenshot, answer the user's question directly."

            with open(path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode()

            response = ollama.chat(
                model=self.model,
                messages=[{
                    "role": "user",
                    "content": context_prompt,
                    "images": [img_b64]
                }]
            )
            return response["message"]["content"]
        except Exception as e:
            logger.error(f"Vision error: {e}")
            return "I had trouble analyzing the screen, sir."
        finally:
            try:
                os.unlink(path)
            except Exception:
                pass

    def read_text_on_screen(self) -> str:
        """OCR fallback using pytesseract"""
        try:
            import pytesseract
            from PIL import Image
            
            # Windows specific handling for Tesseract path
            if platform.system() == "Windows":
                # Assuming standard installation path
                tesseract_path = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
                if os.path.exists(tesseract_path):
                    pytesseract.pytesseract.tesseract_cmd = tesseract_path
            
            path = self.capture()
            text = pytesseract.image_to_string(Image.open(path))
            
            try:
                os.unlink(path)
            except Exception:
                pass
                
            return text.strip() or "No readable text found on screen."
        except Exception as e:
            logger.error(f"OCR failed: {e}")
            return "OCR failed. Note: Tesseract-OCR must be installed on your system to use this fallback."


if __name__ == "__main__":
    vision = ScreenVision()
    print(f"Testing Screen Vision using model: '{vision.model}'")
    print("Capturing screen and analyzing...")
    
    result = vision.analyze("What applications or text are currently visible on the screen?")
    print(f"\nJARVIS sees:\n{result}")
