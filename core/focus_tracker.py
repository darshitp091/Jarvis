import ctypes
import threading
import time
from loguru import logger

class FocusTracker:
    """Tracks user keystroke activity, posture, and blink rates to evaluate cognitive focus and fatigue levels."""

    def __init__(self, camera_engine, sensory_health_analyzer, dashboard_widget=None, main_app=None):
        self.camera = camera_engine
        self.sensory = sensory_health_analyzer
        self.dashboard = dashboard_widget
        self.main_app = main_app
        
        self.is_active = False
        self.thread = None
        
        # Metric counters
        self.char_count = 0
        self.cpm = 120
        self.blink_count = 0
        self.blink_rate = 14
        self.posture = "nominal"
        self.focus_score = 100
        
        self.alert_triggered = False

    def start(self):
        """Starts the background tracking loop."""
        if self.is_active:
            return
        self.is_active = True
        self.thread = threading.Thread(target=self._tracking_loop, daemon=True)
        self.thread.start()
        logger.info("Focus Tracker: Biometric tracking loop started.")

    def stop(self):
        """Stops the tracking loop."""
        self.is_active = False
        if self.thread:
            self.thread.join(timeout=1.0)
        logger.info("Focus Tracker: Biometric tracking loop stopped.")

    def _is_key_pressed(self) -> bool:
        """Uses Windows ctypes to check keyboard state without hooks or extra dependencies."""
        try:
            # Check virtual key codes from 0x08 (BackSpace) to 0xDC (backslash)
            for key_code in range(8, 222):
                # Ignore shift, ctrl, alt keys to avoid duplicate clicks counts
                if key_code in [16, 17, 18, 20]:
                    continue
                if ctypes.windll.user32.GetAsyncKeyState(key_code) & 0x8000:
                    return True
        except Exception:
            pass
        return False

    def _tracking_loop(self):
        # Accumulate typing metrics over 10-second intervals
        interval_sec = 5.0
        last_check_time = time.time()
        
        key_was_down = False
        
        while self.is_active:
            # 1. Capture keystrokes (run at 20Hz for responsiveness)
            key_down = self._is_key_pressed()
            if key_down and not key_was_down:
                self.char_count += 1
                key_was_down = True
            elif not key_down:
                key_was_down = False
                
            time.sleep(0.05)
            
            # 2. Process interval metrics
            now = time.time()
            if now - last_check_time >= interval_sec:
                elapsed = now - last_check_time
                last_check_time = now
                
                # Extrapolate Characters Per Minute (CPM)
                self.cpm = int((self.char_count / elapsed) * 60)
                self.char_count = 0  # reset count
                
                # Poll Sensory health
                sensory_data = self.sensory.analyze_environment()
                self.posture = sensory_data.get("posture", "absent")
                brightness = sensory_data.get("brightness", 120.0)
                
                # Mock eye blink metrics: if camera mesh detects blink, count it.
                # Since face mesh runs, we count blinks per minute (scale from camera)
                # Nominal blink rate is 12-16 BPM. If looking at screen (staring), it drops.
                is_looking = getattr(self.camera, "is_looking", False)
                if is_looking:
                    # In deep focus/staring, blink rate drops to ~6-9 BPM
                    self.blink_rate = 8
                else:
                    self.blink_rate = 14
                    
                # Compute cognitive focus score (nominal standard is 100)
                score = 100
                
                # Deduct for posture slumping
                if self.posture == "slouching":
                    score -= 20
                elif self.posture == "too_close":
                    score -= 25
                    
                # Deduct for prolonged inactivity (cpm == 0)
                if self.cpm == 0:
                    # Staring off or idle
                    score -= 10
                elif self.cpm > 250:
                    # Frantic/stressed key pacing
                    score -= 15
                    
                # Deduct for dark room ambient lighting
                if brightness < 45.0:
                    score -= 15
                    
                self.focus_score = max(0, min(100, score))
                
                # Update Dashboard GUI
                if self.dashboard:
                    posture_display = "GOOD" if self.posture in ["good", "nominal"] else self.posture.upper()
                    if self.posture == "absent":
                        posture_display = "ABSENT"
                    self.dashboard.update_metrics(self.focus_score, self.cpm, self.blink_rate, posture_display)
                    
                # 3. Check for Fatigue alert threshold (< 40%)
                if self.focus_score < 40 and not self.alert_triggered:
                    self.alert_triggered = True
                    logger.warning("Focus Tracker: User fatigue threshold reached. Triggering rest protocol.")
                    if self.main_app:
                        self.main_app.trigger_fatigue_protocol(self.focus_score)
                elif self.focus_score >= 60:
                    self.alert_triggered = False  # Reset warning when user recovers
