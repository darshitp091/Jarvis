import cv2
import threading
import time
import os
import numpy as np
from loguru import logger

class CameraEngine:
    """Continuously monitors camera for presence, gaze, and confusion using OpenCV and MediaPipe."""

    def __init__(self, camera_index=0):
        self.camera_index = camera_index
        self.is_running = False
        self.is_present = False
        self.last_seen_time = 0
        self.thread = None
        self.latest_frame = None
        self.lock = threading.Lock()
        
        # User gaze and confusion state flags
        self.is_looking = False
        self.is_confused = False
        self.face_mesh = None
        self.last_mesh_time = 0.0
        self.latest_face_rect = None

        # OpenCV Haar Cascade for Face Detection
        cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        self.face_cascade = cv2.CascadeClassifier(cascade_path)
        
        if self.face_cascade.empty():
            logger.error("Failed to load OpenCV face cascade classifier!")

        # Initialize LBPH Face ID Recognizer
        self.model_path = os.path.join(os.path.dirname(__file__), "..", "auth", "face_model.xml")
        os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
        self.face_recognizer = cv2.face.LBPHFaceRecognizer_create()
        self.has_face_model = False
        if os.path.exists(self.model_path):
            try:
                self.face_recognizer.read(self.model_path)
                self.has_face_model = True
                logger.info("LBPH Face Recognition model loaded successfully.")
            except Exception as e:
                logger.error(f"Failed to load LBPH face model: {e}")

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        self.thread = threading.Thread(target=self._vision_loop, daemon=True)
        self.thread.start()
        logger.info("Camera Engine started.")

    def stop(self):
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=2)
        logger.info("Camera Engine stopped.")

    def _vision_loop(self):
        cap = cv2.VideoCapture(self.camera_index)
        if not cap.isOpened():
            logger.warning("Camera could not be opened. Camera Engine disabled.")
            self.is_running = False
            return

        # Initialize MediaPipe Face Mesh inside the background thread
        try:
            import mediapipe as mp
            self.face_mesh = mp.solutions.face_mesh.FaceMesh(
                max_num_faces=1,
                refine_landmarks=True,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5
            )
            logger.info("MediaPipe Face Mesh initialized for gaze and confusion tracking.")
        except Exception as e:
            logger.error(f"Failed to initialize MediaPipe Face Mesh: {e}")

        while self.is_running:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.1)
                continue

            self.latest_frame = frame.copy()

            # Convert frame to grayscale for cascade detection
            gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            # Detect faces - thread-safe
            with self.lock:
                faces = self.face_cascade.detectMultiScale(
                    gray_frame, 
                    scaleFactor=1.1, 
                    minNeighbors=5, 
                    minSize=(30, 30)
                )

            if len(faces) > 0:
                self.latest_face_rect = faces[0].tolist()
                self.is_present = True
                self.last_seen_time = time.time()
                
                # Analyze landmarks for gaze and confusion once every 2.0 seconds
                if self.face_mesh and (time.time() - self.last_mesh_time >= 2.0):
                    self.last_mesh_time = time.time()
                    try:
                        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        results = self.face_mesh.process(rgb_frame)
                        
                        if results.multi_face_landmarks:
                            landmarks = results.multi_face_landmarks[0].landmark
                            
                            # 1. Gaze Tracking (Is user looking at the screen/camera?)
                            # Left corner [33], Right corner [133], Left Iris [468]
                            left_eye_l = landmarks[33].x
                            left_eye_r = landmarks[133].x
                            left_iris = landmarks[468].x
                            left_gaze = (left_iris - left_eye_l) / (left_eye_r - left_eye_l)
                            
                            # Right corner [362], Left corner [263], Right Iris [473]
                            right_eye_l = landmarks[362].x
                            right_eye_r = landmarks[263].x
                            right_iris = landmarks[473].x
                            right_gaze = (right_iris - right_eye_l) / (right_eye_r - right_eye_l)
                            
                            # Centered gaze indicates they are looking towards the screen
                            self.is_looking = (0.28 < left_gaze < 0.72) and (0.28 < right_gaze < 0.72)
                            
                            # 2. Confusion (Eyebrow Furrowing)
                            # Left inner brow [70], Right inner brow [300]
                            # Normalized by eye-to-eye distance [33] to [263]
                            brow_dist = np.sqrt((landmarks[70].x - landmarks[300].x)**2 + (landmarks[70].y - landmarks[300].y)**2)
                            eye_dist = np.sqrt((landmarks[33].x - landmarks[263].x)**2 + (landmarks[33].y - landmarks[263].y)**2)
                            brow_ratio = brow_dist / eye_dist
                            
                            # Low brow ratio indicates eyebrows are furrowed/pulled together
                            self.is_confused = brow_ratio < 0.185
                        else:
                            self.is_looking = False
                            self.is_confused = False
                    except Exception as e:
                        logger.debug(f"MediaPipe landmark analysis error: {e}")
            else:
                self.latest_face_rect = None
                self.is_present = False
                self.is_looking = False
                self.is_confused = False

            # Run at ~30 FPS for smooth hand gestures
            time.sleep(0.01)

        if self.face_mesh:
            self.face_mesh.close()
        cap.release()

    def get_time_since_last_seen(self) -> float:
        """Returns seconds since a face was last detected."""
        if self.last_seen_time == 0:
            return float('inf')
        return time.time() - self.last_seen_time

    def calibrate_owner(self) -> bool:
        """Captures 15 frames of the user's face and trains the LBPH face recognizer"""
        logger.info("Starting Face ID calibration...")
        
        # Pause background loop to release camera
        was_running = self.is_running
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=2)

        cap = cv2.VideoCapture(self.camera_index)
        if not cap.isOpened():
            logger.error("Calibration failed: Camera could not be opened.")
            if was_running:
                self.start()
            return False

        faces_data = []
        labels = []
        captured_count = 0
        
        # Give camera a moment to warm up/adjust exposure
        time.sleep(1.0)
        
        start_time = time.time()
        # Loop for maximum 20 seconds to capture 15 frames
        while captured_count < 15 and (time.time() - start_time) < 20:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.1)
                continue
                
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = self.face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
            
            for (x, y, w, h) in faces:
                face_crop = cv2.resize(gray[y:y+h, x:x+w], (200, 200))
                faces_data.append(face_crop)
                labels.append(1)  # Label 1 for Owner
                captured_count += 1
                logger.info(f"Captured face calibration frame {captured_count}/15")
                time.sleep(0.3)  # delay to capture different facial expressions/angles
                break
                
        cap.release()

        if len(faces_data) < 10:
            logger.error("Calibration failed: Not enough face frames captured. Ensure face is well-lit.")
            if was_running:
                self.start()
            return False

        try:
            import numpy as np
            self.face_recognizer.train(faces_data, np.array(labels))
            self.face_recognizer.write(self.model_path)
            self.has_face_model = True
            logger.info("Face ID calibration successful. Model saved to disk.")
            if was_running:
                self.start()
            return True
        except Exception as e:
            logger.error(f"Error training face model: {e}")
            if was_running:
                self.start()
            return False

    def identify_face(self, frame) -> bool:
        """Returns True if a face in the frame matches the trained owner profile (confidence <= 85)"""
        if not self.has_face_model or frame is None:
            return False
            
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            with self.lock:
                faces = self.face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
                
                for (x, y, w, h) in faces:
                    face_crop = cv2.resize(gray[y:y+h, x:x+w], (200, 200))
                    label, confidence = self.face_recognizer.predict(face_crop)
                    # Lower confidence score in LBPH means closer distance (better match)
                    logger.debug(f"Face ID Predict -> Label: {label}, Confidence: {confidence:.2f}")
                    if label == 1 and confidence <= 85.0:
                        return True
        except Exception as e:
            logger.error(f"Error predicting face: {e}")
                
        return False
