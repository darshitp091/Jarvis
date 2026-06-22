import sys
import time
from loguru import logger
from core.vision_engine import CameraEngine

if __name__ == "__main__":
    logger.info("Initializing Face ID Calibration...")
    camera = CameraEngine()
    
    print("\n" + "="*60)
    print("                  JARVIS FACE ID CALIBRATION")
    print("="*60)
    print("INSTRUCTIONS:")
    print("1. Ensure your face is well-lit (avoid strong background lighting).")
    print("2. Look directly at the camera lens.")
    print("3. Slightly tilt and rotate your head to capture different angles.")
    print("\nCalibration will begin in 3 seconds... Get ready!")
    print("="*60 + "\n")
    
    time.sleep(3)
    
    success = camera.calibrate_owner()
    
    if success:
        print("\n" + "="*60)
        print(" SUCCESS: Face calibration complete! Model saved to auth/face_model.xml")
        print("="*60 + "\n")
    else:
        print("\n" + "="*60)
        print(" ERROR: Calibration failed.")
        print(" Please ensure your webcam is connected and your face is visible.")
        print("="*60 + "\n")
