import cv2
import numpy as np
from loguru import logger

class SensoryHealthAnalyzer:
    """Analyzes workspace ambient lighting and user posture metrics using active camera feeds."""

    def __init__(self, camera_engine):
        self.camera = camera_engine
        # Baseline calibrations (calibrated on initial clean posture)
        self.baseline_fy = 200.0  # expected face center Y coordinate
        self.baseline_fh = 120.0  # expected face height (size)

    def analyze_environment(self) -> dict:
        """
        Analyzes the latest camera frame for lighting levels and posture parameters.
        Returns:
            dict containing:
                "status": "ok" | "warning" | "error"
                "brightness": float
                "glare": bool
                "posture": "good" | "slouching" | "too_close" | "absent"
                "message": str
        """
        result = {
            "status": "ok",
            "brightness": 120.0,
            "glare": False,
            "posture": "absent",
            "message": "Sir, environment checks are nominal."
        }

        if not self.camera or not self.camera.is_running:
            result["status"] = "error"
            result["message"] = "Camera engine is offline, sir."
            return result

        frame = getattr(self.camera, "latest_frame", None)
        if frame is None:
            result["status"] = "error"
            result["message"] = "Unable to read camera frame buffer, sir."
            return result

        # 1. Brightness & Glare check
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        mean_brightness = np.mean(gray)
        std_brightness = np.std(gray)
        result["brightness"] = float(mean_brightness)

        # Brightness thresholds (0-255 scale)
        if mean_brightness < 45.0:
            result["status"] = "warning"
            result["message"] = "Sir, the room is too dark. Please activate workspace lighting to avoid eye strain."
        elif mean_brightness > 220.0 or (mean_brightness > 180.0 and std_brightness < 20.0):
            result["glare"] = True
            result["status"] = "warning"
            result["message"] = "Sir, high glare detected on screen. Recommend adjusting blinds or display angle."

        # 2. Posture & Distance check (using latest face rect detected by camera cascade)
        face_rect = getattr(self.camera, "latest_face_rect", None)
        if face_rect:
            fx, fy, fw, fh = face_rect
            face_cy = fy + fh / 2.0
            
            # Posture checks
            # Distance: larger face height 'fh' means they are leaning too close
            if fh > (self.baseline_fh * 1.55):
                result["posture"] = "too_close"
                result["status"] = "warning"
                result["message"] = "Sir, you are sitting too close to the screen. Please sit back for comfort."
            # Vertical height: lower face center 'face_cy' means they are slouching downwards
            elif face_cy > (self.baseline_fy * 1.45):
                result["posture"] = "slouching"
                result["status"] = "warning"
                result["message"] = "Sir, I notice you are slouching. Recommend adjusting your chair or spine alignment."
            else:
                result["posture"] = "good"
        else:
            result["posture"] = "absent"

        return result

    def recalibrate_posture(self):
        """Sets current face metrics as the baseline/good posture standard."""
        face_rect = getattr(self.camera, "latest_face_rect", None)
        if face_rect:
            fx, fy, fw, fh = face_rect
            self.baseline_fy = fy + fh / 2.0
            self.baseline_fh = fh
            logger.info(f"Sensory Health: Recalibrated baseline posture to center Y={self.baseline_fy:.1f}, height={self.baseline_fh:.1f}")
            return "Sensory posture metrics successfully calibrated to current position, sir."
        return "Cannot recalibrate. No face visible in current frame, sir."
