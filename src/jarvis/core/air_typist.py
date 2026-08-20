import cv2
import numpy as np
import pyautogui
import time
import threading
import os
from contextlib import contextmanager

@contextmanager
def silence_stderr():
    """Silences OS-level stderr completely (e.g. C/C++ library absl warnings)."""
    new_target = open(os.devnull, 'w')
    old_stderr_fd = os.dup(2)
    os.dup2(new_target.fileno(), 2)
    try:
        yield
    finally:
        os.dup2(old_stderr_fd, 2)
        os.close(old_stderr_fd)
        new_target.close()

from loguru import logger

class AirTypistTracker:
    """Uses face landmarks to control screen cursor coordinates and execute click events via eye blinks."""

    def __init__(self, camera_engine):
        self.camera = camera_engine
        self.is_active = False
        self.thread = None
        
        # Screen dimensions
        self.screen_w, self.screen_h = pyautogui.size()
        
        # Tracking states
        self.smoothing = 0.25
        self.prev_x, self.prev_y = self.screen_w // 2, self.screen_h // 2
        self.blink_start_time = None
        self.is_blinking = False

    def start(self):
        """Starts the air typist tracking thread."""
        if self.is_active:
            return "Air typist is already running, sir."
        self.is_active = True
        pyautogui.FAILSAFE = True
        self.thread = threading.Thread(target=self._tracking_loop, daemon=True)
        self.thread.start()
        logger.info("Air Typist: Eye/Gaze mouse control thread started.")
        return "Air typist activated. Tilt your head to move the pointer, blink for half a second to click."

    def stop(self):
        """Stops the tracking thread."""
        if not self.is_active:
            return "Air typist is already idle, sir."
        self.is_active = False
        if self.thread:
            self.thread.join(timeout=1.0)
        logger.info("Air Typist: Gaze pointer tracking stopped.")
        return "Air typist deactivated, sir. Normal peripheral mouse control restored."

    def _calculate_ear(self, landmarks, eye_indices) -> float:
        """Calculates Eye Aspect Ratio (EAR) to detect blinks."""
        # eye_indices: [top, bottom, left, right]
        p_top = np.array([landmarks[eye_indices[0]].x, landmarks[eye_indices[0]].y])
        p_bottom = np.array([landmarks[eye_indices[1]].x, landmarks[eye_indices[1]].y])
        p_left = np.array([landmarks[eye_indices[2]].x, landmarks[eye_indices[2]].y])
        p_right = np.array([landmarks[eye_indices[3]].x, landmarks[eye_indices[3]].y])
        
        vertical_dist = np.linalg.norm(p_top - p_bottom)
        horizontal_dist = np.linalg.norm(p_left - p_right)
        
        if horizontal_dist == 0:
            return 0.0
        return vertical_dist / horizontal_dist

    def _tracking_loop(self):
        # Local imports of mediapipe inside the thread to avoid startup delays
        try:
            with silence_stderr():
                import mediapipe as mp
                face_mesh = mp.solutions.face_mesh.FaceMesh(
                    max_num_faces=1,
                    refine_landmarks=True,
                    min_detection_confidence=0.5,
                    min_tracking_confidence=0.5
                )
        except ImportError:
            logger.error("Air Typist: MediaPipe is required for high-accuracy gaze tracking.")
            self.is_active = False
            return

        # Eyelid landmarks for EAR calculation
        # Left eye: top [159], bottom [145], left [33], right [133]
        left_eye_indices = [159, 145, 33, 133]
        # Right eye: top [386], bottom [374], left [362], right [263]
        right_eye_indices = [386, 374, 362, 263]

        while self.is_active:
            frame = getattr(self.camera, "latest_frame", None)
            if frame is None:
                time.sleep(0.05)
                continue

            h, w, _ = frame.shape
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = face_mesh.process(rgb_frame)

            if results.multi_face_landmarks:
                landmarks = results.multi_face_landmarks[0].landmark
                
                # 1. Pointer control: Track relative nose coordinates
                # Nose tip is landmark 4. Left contour [234], Right contour [454]
                nose = landmarks[4]
                left_bound = landmarks[234]
                right_bound = landmarks[454]
                top_bound = landmarks[10]    # Top forehead
                bottom_bound = landmarks[152] # Chin
                
                # Calculate relative position of nose tip inside face box boundaries
                face_width = abs(right_bound.x - left_bound.x)
                face_height = abs(bottom_bound.y - top_bound.y)
                
                if face_width > 0 and face_height > 0:
                    rel_x = (nose.x - left_bound.x) / face_width
                    rel_y = (nose.y - top_bound.y) / face_height
                    
                    # Scale to screen dimensions (with offset margins for comfortable reach)
                    target_x = int((rel_x - 0.3) * (self.screen_w / 0.4))
                    target_y = int((rel_y - 0.3) * (self.screen_h / 0.4))
                    
                    # Clip boundaries
                    target_x = max(0, min(self.screen_w - 1, target_x))
                    target_y = max(0, min(self.screen_h - 1, target_y))
                    
                    # Smooth cursor moves
                    smooth_x = int(self.prev_x + (target_x - self.prev_x) * self.smoothing)
                    smooth_y = int(self.prev_y + (target_y - self.prev_y) * self.smoothing)
                    
                    # Move cursor
                    pyautogui.moveTo(smooth_x, smooth_y)
                    self.prev_x, self.prev_y = smooth_x, smooth_y

                # 2. Click control: EAR blink check
                left_ear = self._calculate_ear(landmarks, left_eye_indices)
                right_ear = self._calculate_ear(landmarks, right_eye_indices)
                avg_ear = (left_ear + right_ear) / 2.0
                
                # Blink threshold
                if avg_ear < 0.18:
                    if not self.is_blinking:
                        self.is_blinking = True
                        self.blink_start_time = time.time()
                else:
                    if self.is_blinking:
                        self.is_blinking = False
                        blink_duration = time.time() - self.blink_start_time
                        # Require a slightly prolonged blink (0.35s to 0.9s) to trigger a click,
                        # avoiding normal involuntary rapid blinks.
                        if 0.35 < blink_duration < 0.9:
                            pyautogui.click()
                            logger.info(f"Air Typist: Executed click (blink duration: {blink_duration:.2f}s)")
                            
            time.sleep(0.033)  # Loop at ~30 FPS
