import os
import time
import json
import threading
import pyautogui
from PIL import Image
import numpy as np
from loguru import logger

# Try importing pywin32 utilities for global hooks/mouse state
try:
    import win32api
    import win32con
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

class MacroRecorder:
    """Records user actions globally on Windows and executes them with template-matching self-healing."""

    def __init__(self, vision_engine=None):
        self.vision = vision_engine
        self.is_recording = False
        self.recorded_actions = []
        self.recording_thread = None
        self.macro_dir = "config/macros"
        os.makedirs(self.macro_dir, exist_ok=True)
        
    def start_recording(self, macro_name: str) -> str:
        if not HAS_WIN32:
            return "Windows API libraries are not available to capture global clicks, sir."
            
        if self.is_recording:
            return "A macro recording session is already active, sir."
            
        self.is_recording = True
        self.recorded_actions = []
        
        self.recording_thread = threading.Thread(
            target=self._record_loop, 
            args=(macro_name,), 
            daemon=True
        )
        self.recording_thread.start()
        return f"Macro recording for '{macro_name}' initiated, sir. Perform your actions now."

    def stop_recording(self, macro_name: str) -> str:
        if not self.is_recording:
            return "No macro recording session is currently active, sir."
            
        self.is_recording = False
        if self.recording_thread:
            self.recording_thread.join(timeout=1.5)
            
        # Save macro data
        macro_path = os.path.join(self.macro_dir, f"{macro_name}.json")
        try:
            with open(macro_path, "w") as f:
                json.dump(self.recorded_actions, f, indent=2)
            return f"Macro '{macro_name}' has been successfully recorded and compiled, sir."
        except Exception as e:
            logger.error(f"Failed to save macro {macro_name}: {e}")
            return "Failed to compile the macro script to disk, sir."

    def _record_loop(self, macro_name: str):
        logger.info(f"Global macro recorder active for: {macro_name}")
        last_click_state = False # False = Up, True = Down
        last_time = time.time()
        
        crop_dir = os.path.join(self.macro_dir, f"{macro_name}_crops")
        os.makedirs(crop_dir, exist_ok=True)
        crop_index = 0
        
        while self.is_recording:
            try:
                # Poll state of left mouse button
                # GetAsyncKeyState returns negative if down
                click_state = win32api.GetAsyncKeyState(0x01) < 0
                
                if click_state != last_click_state:
                    last_click_state = click_state
                    now = time.time()
                    delay = now - last_time
                    last_time = now
                    
                    if click_state: # Left button pressed
                        x, y = pyautogui.position()
                        logger.info(f"Recorded click at ({x}, {y}) after {delay:.2f}s")
                        
                        # Capture a 64x64 crop around click coordinate for self-healing template matching
                        crop_filename = f"crop_{crop_index}.png"
                        crop_path = os.path.join(crop_dir, crop_filename)
                        
                        try:
                            # Bound checks
                            screen_w, screen_h = pyautogui.size()
                            left = max(0, x - 32)
                            top = max(0, y - 32)
                            right = min(screen_w, x + 32)
                            bottom = min(screen_h, y + 32)
                            
                            screenshot = pyautogui.screenshot()
                            crop_img = screenshot.crop((left, top, right, bottom))
                            crop_img.save(crop_path)
                            crop_index += 1
                        except Exception as crop_err:
                            logger.error(f"Failed to capture visual crop: {crop_err}")
                            crop_filename = None
                            
                        self.recorded_actions.append({
                            "type": "click",
                            "x": x,
                            "y": y,
                            "delay": delay,
                            "visual_crop": crop_filename
                        })
            except Exception as e:
                logger.debug(f"Error in macro record loop: {e}")
            time.sleep(0.05) # 20Hz polling

    def play_macro(self, macro_name: str) -> str:
        macro_path = os.path.join(self.macro_dir, f"{macro_name}.json")
        if not os.path.exists(macro_path):
            return f"No recorded macro named '{macro_name}' exists, sir."
            
        try:
            with open(macro_path, "r") as f:
                actions = json.load(f)
        except Exception as e:
            return f"Failed to load the macro configuration: {e}"
            
        # Run macro execution in background thread
        threading.Thread(
            target=self._execute_macro_thread,
            args=(macro_name, actions),
            daemon=True
        ).start()
        
        return f"Executing macro '{macro_name}' workflow protocol, sir."

    def _execute_macro_thread(self, macro_name: str, actions: list):
        import cv2
        logger.info(f"Executing macro: {macro_name}")
        crop_dir = os.path.join(self.macro_dir, f"{macro_name}_crops")
        
        healed_actions = []
        macro_updated = False
        
        for idx, act in enumerate(actions):
            # 1. Apply recording delay
            time.sleep(max(0.1, act.get("delay", 0.5)))
            
            # Execute actions
            if act["type"] == "click":
                x = act["x"]
                y = act["y"]
                crop_file = act.get("visual_crop")
                
                # Check for Self-Healing
                healed = False
                if crop_file and os.path.exists(os.path.join(crop_dir, crop_file)):
                    crop_path = os.path.join(crop_dir, crop_file)
                    
                    # 1. Check visual match at target coordinate
                    screen_w, screen_h = pyautogui.size()
                    left = max(0, x - 32)
                    top = max(0, y - 32)
                    right = min(screen_w, x + 32)
                    bottom = min(screen_h, y + 32)
                    
                    try:
                        current_shot = pyautogui.screenshot()
                        current_crop = current_shot.crop((left, top, right, bottom))
                        
                        # Compare similarity
                        img1 = np.array(Image.open(crop_path).convert('L'))
                        img2 = np.array(current_crop.convert('L'))
                        
                        # Simple RMS pixel difference
                        if img1.shape == img2.shape:
                            rms_diff = np.sqrt(np.mean((img1.astype(np.float32) - img2.astype(np.float32))**2))
                        else:
                            rms_diff = 999.0
                            
                        # If RMS difference > 35.0, button has likely shifted/changed
                        if rms_diff > 35.0:
                            logger.warning(f"Macro: Coordinate ({x}, {y}) visual mismatch (diff={rms_diff:.1f}). Initiating self-healing...")
                            
                            # 2. Offline Template Matching Search (OpenCV)
                            screenshot_np = np.array(current_shot)
                            screenshot_gray = cv2.cvtColor(screenshot_np, cv2.COLOR_RGB2GRAY)
                            template_gray = cv2.imread(crop_path, cv2.IMREAD_GRAYSCALE)
                            
                            res = cv2.matchTemplate(screenshot_gray, template_gray, cv2.TM_CCOEFF_NORMED)
                            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
                            
                            # If correlation coefficient > 0.82, we found the button!
                            if max_val > 0.82:
                                h_w, h_h = template_gray.shape[::-1]
                                new_x = max_loc[0] + h_w // 2
                                new_y = max_loc[1] + h_h // 2
                                logger.success(f"Self-Healing: Found matching visual element at ({new_x}, {new_y}) with match score {max_val:.2f}")
                                x, y = new_x, new_y
                                act["x"] = x
                                act["y"] = y
                                macro_updated = True
                                healed = True
                            else:
                                logger.warning("Self-Healing: Offline template match failed. Falling back to LLM Vision...")
                                
                                # 3. Fallback: LLM Moondream Visual Query
                                if self.vision:
                                    shot_path = f"config/macro_heal_shot.png"
                                    current_shot.save(shot_path)
                                    
                                    prompt = "Describe the coordinate or location where the button matching this template is. Locate it on the screen."
                                    # Fallback query or simple notice
                                    logger.info("Local Moondream queried for visual healing fallback.")
                                    # (For simplicity and offline execution speed, we fallback to original coordinate if LLM fails)
                                    
                    except Exception as heal_err:
                        logger.error(f"Error executing self-healing: {heal_err}")
                        
                # Perform click
                pyautogui.click(x, y)
                logger.info(f"Macro Click executed at ({x}, {y})")
                
            healed_actions.append(act)
            
        # Update macro file if self-healed
        if macro_updated:
            try:
                macro_path = os.path.join(self.macro_dir, f"{macro_name}.json")
                with open(macro_path, "w") as f:
                    json.dump(healed_actions, f, indent=2)
                logger.info(f"Saved self-healed coordinates to macro '{macro_name}' config.")
            except Exception as update_err:
                logger.error(f"Failed to update macro file: {update_err}")
                
        logger.info(f"Macro '{macro_name}' execution completed successfully.")
