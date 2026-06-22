import os
import json
import base64
import tempfile
import pyautogui
import ollama
import yaml
import re
from loguru import logger

class SelfHealingVision:
    """Uses vision analysis to find UI elements on screen, caching coordinates to self-heal coordinates mappings."""

    def __init__(self, config_path: str = "config/settings.yaml"):
        if not os.path.exists(config_path):
            fallback = os.path.join(os.path.dirname(__file__), "..", config_path)
            if os.path.exists(fallback):
                config_path = fallback

        try:
            with open(config_path) as f:
                settings = yaml.safe_load(f)
                self.model = settings.get("models", {}).get("vision", "moondream:latest")
        except Exception as e:
            logger.warning(f"Failed to load vision settings: {e}. Using fallback.")
            self.model = "moondream:latest"

        self.cache_dir = "config"
        self.cache_path = os.path.join(self.cache_dir, "element_coordinates.json")
        os.makedirs(self.cache_dir, exist_ok=True)
        self._load_cache()

    def _load_cache(self):
        self.cache = {}
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    self.cache = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load coordinates cache: {e}")

    def _save_cache(self):
        try:
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save coordinates cache: {e}")

    def _get_screenshot_b64(self) -> tuple[str, str]:
        """Captures a screenshot, returns (temp_file_path, base64_string)"""
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            path = f.name
        
        screenshot = pyautogui.screenshot()
        screenshot.save(path)
        
        with open(path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()
            
        return path, img_b64

    def locate_element_visually(self, element_name: str) -> tuple[int, int] | None:
        """Locates the center of a named element on the screen using VLM."""
        element_key = element_name.lower().strip()
        
        # Check cache first
        if element_key in self.cache:
            rel_x, rel_y = self.cache[element_key]
            width, height = pyautogui.size()
            x = int(rel_x * width)
            y = int(rel_y * height)
            logger.info(f"Retrieved element '{element_name}' from cache: {x, y} ({rel_x*100:.1f}%, {rel_y*100:.1f}%)")
            return x, y

        logger.info(f"Locating '{element_name}' visually on the screen...")
        path, img_b64 = self._get_screenshot_b64()
        
        try:
            prompt = (
                f"Identify the center of the UI element: '{element_name}'. "
                "Respond in JSON format ONLY, containing 'x' and 'y' keys as integer percentages from 0 to 100 "
                "representing the position relative to screen width and height. "
                "Example: {\"x\": 45, \"y\": 20}"
            )

            response = ollama.chat(
                model=self.model,
                messages=[{
                    "role": "user",
                    "content": prompt,
                    "images": [img_b64]
                }],
                options={"temperature": 0.1}
            )
            
            raw_content = response["message"]["content"].strip()
            logger.info(f"VLM raw response: {raw_content}")

            # Parse JSON block
            raw_json = raw_content.replace("```json", "").replace("```", "").strip()
            match = re.search(r"\{.*?\}", raw_json)
            if match:
                data = json.loads(match.group(0))
                rx = float(data["x"]) / 100.0
                ry = float(data["y"]) / 100.0
                
                # Bounds check
                if 0.0 <= rx <= 1.0 and 0.0 <= ry <= 1.0:
                    self.cache[element_key] = [rx, ry]
                    self._save_cache()
                    
                    width, height = pyautogui.size()
                    x = int(rx * width)
                    y = int(ry * height)
                    return x, y

            # Regex search backup if JSON parse fails
            nums = re.findall(r"\d+", raw_content)
            if len(nums) >= 2:
                rx = float(nums[0]) / 100.0
                ry = float(nums[1]) / 100.0
                if 0.0 <= rx <= 1.0 and 0.0 <= ry <= 1.0:
                    self.cache[element_key] = [rx, ry]
                    self._save_cache()
                    width, height = pyautogui.size()
                    x = int(rx * width)
                    y = int(ry * height)
                    return x, y

        except Exception as e:
            logger.error(f"Failed to visually locate element: {e}")
        finally:
            try:
                os.unlink(path)
            except Exception:
                pass

        return None

    def click_element_visually(self, element_name: str) -> bool:
        """Finds and clicks an element on the screen. Returns True if successful."""
        coords = self.locate_element_visually(element_name)
        if coords:
            x, y = coords
            logger.info(f"Clicking visually located element '{element_name}' at {x, y}")
            # Save original position
            orig_x, orig_y = pyautogui.position()
            
            # Click
            pyautogui.click(x, y)
            
            # Return cursor
            pyautogui.moveTo(orig_x, orig_y)
            return True
        else:
            logger.warning(f"Could not locate element '{element_name}' on screen.")
            return False


if __name__ == "__main__":
    print("Testing Self-Healing Vision module...")
    healing = SelfHealingVision()
    
    # Run a test query against cache first
    test_element = "test_click_target"
    healing.cache[test_element] = [0.5, 0.5] # center screen
    healing._save_cache()
    
    coords = healing.locate_element_visually(test_element)
    print(f"Location of '{test_element}': {coords}")
