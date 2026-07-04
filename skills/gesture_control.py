import time
import threading
import ctypes
import pyautogui
import cv2
import warnings
import math
import os
warnings.filterwarnings("ignore")
from loguru import logger

# Screen dimensions
screen_w, screen_h = pyautogui.size()

# Win32 Ctypes structures and calls
class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_int),
        ("top", ctypes.c_int),
        ("right", ctypes.c_int),
        ("bottom", ctypes.c_int)
    ]

def get_active_window_hwnd():
    return ctypes.windll.user32.GetForegroundWindow()

def get_window_rect(hwnd):
    rect = RECT()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top

def move_window_hwnd(hwnd, x, y, w, h):
    # SWP_NOZORDER = 0x0004
    ctypes.windll.user32.SetWindowPos(hwnd, 0, x, y, w, h, 0x0004)

def close_window_hwnd(hwnd):
    # WM_CLOSE = 0x0010
    ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)

class GestureController:
    """Tracks hand landmarks and translates them into smooth mouse, click, and advanced Iron Man window gestures."""

    def __init__(self, camera_engine, canvas=None, youtube_music=None, hologram_widget=None):
        self.camera = camera_engine
        self.canvas = canvas
        self.youtube_music = youtube_music
        self.hologram_widget = hologram_widget
        self.is_running = False
        self.thread = None
        
        # Exponential Moving Average variables for coordinate smoothing
        self.prev_cx = None
        self.prev_cy = None
        self.alpha = 0.75 # Smoothing factor
        
        # Action tracking states
        self.is_left_clicked = False
        self.is_scrolling = False
        self.scroll_start_y = 0
        self.is_drawing = False
        
        # State tracking for drag-and-drop window movements
        self.is_dragging = False
        self.drag_hwnd = None
        self.drag_start_wx = 0
        self.drag_start_wy = 0
        self.drag_start_w = 0
        self.drag_start_h = 0
        self.drag_start_hx = 0
        self.drag_start_hy = 0
        self.fist_start_time = None
        
        # Advanced Iron Man kinetics states
        self.prev_raw_x = None
        self.prev_raw_y = None
        self.prev_two_hand_dist = None
        self.palm_mute_start_time = None
        self.last_swipe_time = 0.0

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        self.thread = threading.Thread(target=self._gesture_loop, daemon=True)
        self.thread.start()
        logger.info("Advanced Hand Gesture Control thread started.")

    def stop(self):
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=2)
        logger.info("Advanced Hand Gesture Control thread stopped.")

    def _gesture_loop(self):
        try:
            import mediapipe as mp
            mp_hands = mp.solutions.hands
            hands = mp_hands.Hands(
                max_num_hands=2,
                min_detection_confidence=0.65,
                min_tracking_confidence=0.65
            )
            logger.info("MediaPipe Hands initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize MediaPipe Hands: {e}")
            self.is_running = False
            return

        def get_dist(p1, p2):
            return math.sqrt((p1.x - p2.x)**2 + (p1.y - p2.y)**2)

        while self.is_running:
            frame = self.camera.latest_frame
            if frame is None:
                time.sleep(0.05)
                continue

            try:
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = hands.process(rgb_frame)
                
                # Check for Two-Hand Zoom/Resize Gesture first
                if results.multi_hand_landmarks and len(results.multi_hand_landmarks) == 2:
                    h1 = results.multi_hand_landmarks[0].landmark
                    h2 = results.multi_hand_landmarks[1].landmark
                    
                    # Distance between the two index finger tips
                    dist = get_dist(h1[8], h2[8])
                    
                    if self.hologram_widget and self.hologram_widget.isVisible():
                        # Map index finger distance (0.1 to 0.7) to explode factor (0.0 to 2.0)
                        factor = max(0.0, min(2.0, (dist - 0.2) * 4.0))
                        self.hologram_widget.target_explode_factor = factor
                        self.prev_two_hand_dist = dist
                        time.sleep(0.02)
                    elif self.prev_two_hand_dist is not None:
                        diff = dist - self.prev_two_hand_dist
                        # If distance changes significantly, trigger system zoom hotkeys
                        if diff > 0.08:
                            logger.debug(f"Two-Hand Gesture: Zooming IN (diff={diff:.3f})")
                            pyautogui.hotkey('ctrl', '=')
                            self.prev_two_hand_dist = dist
                            time.sleep(0.2)
                        elif diff < -0.08:
                            logger.debug(f"Two-Hand Gesture: Zooming OUT (diff={diff:.3f})")
                            pyautogui.hotkey('ctrl', '-')
                            self.prev_two_hand_dist = dist
                            time.sleep(0.2)
                    else:
                        self.prev_two_hand_dist = dist
                        
                    # Reset single hand states to avoid conflict
                    self.fist_start_time = None
                    self.palm_mute_start_time = None
                    time.sleep(0.015)
                    continue
                else:
                    self.prev_two_hand_dist = None

                # Process single-hand gestures
                if results.multi_hand_landmarks and len(results.multi_hand_landmarks) == 1:
                    landmarks = results.multi_hand_landmarks[0].landmark
                    
                    # 1. Coordinate Scaling & Smoothing
                    hx = landmarks[8].x # Tip of index finger
                    hy = landmarks[8].y
                    
                    # Mirror X axis for camera inversion
                    raw_x = 1.0 - hx
                    raw_y = hy
                    
                    # Map center region [0.2, 0.8] to [0.0, 1.0]
                    scaled_x = (raw_x - 0.2) / 0.6
                    scaled_y = (raw_y - 0.2) / 0.6
                    scaled_x = max(0.0, min(1.0, scaled_x))
                    scaled_y = max(0.0, min(1.0, scaled_y))
                    
                    target_x = int(scaled_x * screen_w)
                    target_y = int(scaled_y * screen_h)
                    
                    if self.prev_cx is None:
                        self.prev_cx = target_x
                        self.prev_cy = target_y
                    else:
                        self.prev_cx = int(self.prev_cx * self.alpha + target_x * (1 - self.alpha))
                        self.prev_cy = int(self.prev_cy * self.alpha + target_y * (1 - self.alpha))
                        
                    cx = self.prev_cx
                    cy = self.prev_cy

                    # 2. Finger Extension Status
                    index_extended = landmarks[8].y < landmarks[6].y
                    middle_extended = landmarks[12].y < landmarks[10].y
                    ring_extended = landmarks[16].y < landmarks[14].y
                    pinky_extended = landmarks[20].y < landmarks[18].y
                    thumb_extended = get_dist(landmarks[4], landmarks[2]) > 0.05
                    
                    # 3. Pinch Distances
                    thumb_index_dist = get_dist(landmarks[4], landmarks[8])
                    thumb_middle_dist = get_dist(landmarks[4], landmarks[12])
                    thumb_pinky_dist = get_dist(landmarks[4], landmarks[20])
                    
                    # 4. Advanced Swipe/Throw Hand Gesture
                    # Detect fast hand movement when all fingers are open
                    all_extended = index_extended and middle_extended and ring_extended and pinky_extended and thumb_extended
                    
                    if all_extended and self.prev_raw_x is not None and self.prev_raw_y is not None:
                        vx = raw_x - self.prev_raw_x
                        vy = raw_y - self.prev_raw_y
                        now = time.time()
                        
                        if now - self.last_swipe_time > 0.8: # Debounce swiping
                            # Horizontal swipes
                            if vx > 0.25: # Fast swipe right -> Snap window right
                                logger.info("Kinetic Gesture: Swipe RIGHT detected. Snapping window right.")
                                pyautogui.hotkey('win', 'right')
                                self.last_swipe_time = now
                            elif vx < -0.25: # Fast swipe left -> Snap window left
                                logger.info("Kinetic Gesture: Swipe LEFT detected. Snapping window left.")
                                pyautogui.hotkey('win', 'left')
                                self.last_swipe_time = now
                            # Vertical swipes
                            elif vy < -0.22: # Fast swipe up -> Maximize window
                                logger.info("Kinetic Gesture: Swipe UP detected. Maximizing window.")
                                pyautogui.hotkey('win', 'up')
                                self.last_swipe_time = now
                            elif vy > 0.22: # Fast swipe down -> Minimize window
                                logger.info("Kinetic Gesture: Swipe DOWN detected. Minimizing window.")
                                pyautogui.hotkey('win', 'down')
                                self.last_swipe_time = now
                                
                    self.prev_raw_x = raw_x
                    self.prev_raw_y = raw_y

                    # 5. Advanced Palm Mute Gesture
                    # Raise open palm close to the camera (large distance from wrist to middle tip)
                    hand_scale = get_dist(landmarks[0], landmarks[12])
                    if all_extended and hand_scale > 0.38: # Close to lens
                        if self.palm_mute_start_time is None:
                            self.palm_mute_start_time = time.time()
                        elif time.time() - self.palm_mute_start_time >= 1.2:
                            logger.info("Kinetic Gesture: Palm Mute detected. Toggling media mute.")
                            pyautogui.press('volumemute')
                            self.palm_mute_start_time = None
                            time.sleep(1.0)
                    else:
                        self.palm_mute_start_time = None

                    # 6. Gesture Classification State Machine
                    
                    # GESTURE A: Air Writing (Rock-On Sign)
                    if index_extended and pinky_extended and not middle_extended and not ring_extended:
                        self.fist_start_time = None
                        self.is_dragging = False
                        self.is_scrolling = False
                        if self.is_left_clicked:
                            pyautogui.mouseUp()
                            self.is_left_clicked = False
                        
                        ctypes.windll.user32.SetCursorPos(cx, cy)
                        
                        if self.canvas:
                            if not self.is_drawing:
                                self.is_drawing = True
                                self.canvas.signals.show_canvas.emit()
                                self.canvas.signals.start_stroke.emit()
                            self.canvas.signals.add_point.emit(cx, cy)
                            
                    # GESTURE B: Left Click / Drag (Index pinch to Thumb)
                    elif index_extended and not middle_extended and not ring_extended and not pinky_extended and thumb_index_dist < 0.045:
                        self.fist_start_time = None
                        self.is_dragging = False
                        self.is_scrolling = False
                        self._stop_drawing()
                        
                        ctypes.windll.user32.SetCursorPos(cx, cy)
                        
                        if not self.is_left_clicked:
                            pyautogui.mouseDown()
                            self.is_left_clicked = True
                            logger.debug("Gesture Controller: Mouse Down (Drag active)")
 
                    # GESTURE C: Right Click (Middle pinch to Thumb)
                    elif middle_extended and not index_extended and not ring_extended and not pinky_extended and thumb_middle_dist < 0.045:
                        self.fist_start_time = None
                        self.is_dragging = False
                        self.is_scrolling = False
                        self._stop_drawing()
                        pyautogui.rightClick()
                        logger.debug("Gesture Controller: Right click executed")
                        time.sleep(0.5)
 
                    # GESTURE D: Double Click (Pinky pinch to Thumb)
                    elif pinky_extended and not index_extended and not middle_extended and not ring_extended and thumb_pinky_dist < 0.045:
                        self.fist_start_time = None
                        self.is_dragging = False
                        self.is_scrolling = False
                        self._stop_drawing()
                        pyautogui.doubleClick()
                        logger.debug("Gesture Controller: Double click executed")
                        time.sleep(0.5)
 
                    # GESTURE E: Scroll Mode
                    elif index_extended and middle_extended and ring_extended and not pinky_extended:
                        self.fist_start_time = None
                        self.is_dragging = False
                        self._stop_drawing()
                        if self.is_left_clicked:
                            pyautogui.mouseUp()
                            self.is_left_clicked = False
                        
                        if not self.is_scrolling:
                            self.is_scrolling = True
                            self.scroll_start_y = hy
                        else:
                            dy = hy - self.scroll_start_y
                            if abs(dy) > 0.04:
                                scroll_amount = int(dy * 120)
                                pyautogui.scroll(-scroll_amount)
                                self.scroll_start_y = hy
 
                    # GESTURE F: Drag & Move Active Window
                    elif index_extended and middle_extended and not ring_extended and not pinky_extended and thumb_index_dist >= 0.045:
                        self.fist_start_time = None
                        self.is_scrolling = False
                        self._stop_drawing()
                        if self.is_left_clicked:
                            pyautogui.mouseUp()
                            self.is_left_clicked = False
                        
                        hx_drag = landmarks[8].x
                        hy_drag = landmarks[8].y
                        
                        if not self.is_dragging:
                            self.drag_hwnd = get_active_window_hwnd()
                            if self.drag_hwnd:
                                self.is_dragging = True
                                wx, wy, w, h = get_window_rect(self.drag_hwnd)
                                self.drag_start_wx = wx
                                self.drag_start_wy = wy
                                self.drag_start_w = w
                                self.drag_start_h = h
                                self.drag_start_hx = hx_drag
                                self.drag_start_hy = hy_drag
                        else:
                            dx = hx_drag - self.drag_start_hx
                            dy = hy_drag - self.drag_start_hy
                            dx_pixels = int(dx * screen_w * 1.5)
                            dy_pixels = int(dy * screen_h * 1.5)
                            
                            new_wx = self.drag_start_wx - dx_pixels
                            new_wy = self.drag_start_wy + dy_pixels
                            
                            move_window_hwnd(
                                self.drag_hwnd, 
                                new_wx, 
                                new_wy, 
                                self.drag_start_w, 
                                self.drag_start_h
                            )
 
                    # GESTURE G: Closed Fist (Close window after 1.5s)
                    elif not index_extended and not middle_extended and not ring_extended and not pinky_extended and not thumb_extended:
                        self.is_scrolling = False
                        self.is_dragging = False
                        self._stop_drawing()
                        if self.is_left_clicked:
                            pyautogui.mouseUp()
                            self.is_left_clicked = False
                        
                        if self.fist_start_time is None:
                            self.fist_start_time = time.time()
                        elif time.time() - self.fist_start_time >= 1.5:
                            hwnd_to_close = get_active_window_hwnd()
                            if hwnd_to_close:
                                active_pid = ctypes.c_ulong()
                                ctypes.windll.user32.GetWindowThreadProcessId(hwnd_to_close, ctypes.byref(active_pid))
                                if active_pid.value != os.getpid():
                                    logger.debug("Gesture Controller: Closed fist held for 1.5s. Closing window.")
                                    close_window_hwnd(hwnd_to_close)
                                    self.fist_start_time = None
                                    time.sleep(1.0)
                                else:
                                    logger.debug("Gesture Controller: Excluded closing self process.")
                                    self.fist_start_time = None
 
                    # GESTURE H: Standard Hover
                    elif index_extended and not middle_extended and not ring_extended and not pinky_extended:
                        self.fist_start_time = None
                        self.is_scrolling = False
                        self.is_dragging = False
                        self._stop_drawing()
                        if self.is_left_clicked:
                            pyautogui.mouseUp()
                            self.is_left_clicked = False
                        
                        ctypes.windll.user32.SetCursorPos(cx, cy)

                    # GESTURE I: Virtual Air Keyboard Tapper (V-Shape Pinch: index + middle extended, thumb pinch index)
                    elif index_extended and middle_extended and not ring_extended and not pinky_extended and thumb_index_dist < 0.045:
                        self.fist_start_time = None
                        self.is_dragging = False
                        self.is_scrolling = False
                        self._stop_drawing()
                        if self.is_left_clicked:
                            pyautogui.mouseUp()
                            self.is_left_clicked = False
                        
                        ratio = cx / screen_w
                        now = time.time()
                        if now - self.last_swipe_time > 1.2:  # Debounce keypresses
                            if ratio < 0.33:
                                logger.info("Virtual Keyboard Tap: Backspace")
                                pyautogui.press('backspace')
                            elif ratio > 0.66:
                                logger.info("Virtual Keyboard Tap: Enter")
                                pyautogui.press('enter')
                            else:
                                logger.info("Virtual Keyboard Tap: Space")
                                pyautogui.press('space')
                            self.last_swipe_time = now
                    
                    # DEFAULT: Open Hand / Relaxed
                    else:
                        self.fist_start_time = None
                        self.is_scrolling = False
                        self.is_dragging = False
                        self._stop_drawing()
                        if self.is_left_clicked:
                            pyautogui.mouseUp()
                            self.is_left_clicked = False
                else:
                    self.fist_start_time = None
                    self.is_dragging = False
                    self.is_scrolling = False
                    self.prev_raw_x = None
                    self.prev_raw_y = None
                    self.palm_mute_start_time = None
                    self._stop_drawing()
                    if self.is_left_clicked:
                        pyautogui.mouseUp()
                        self.is_left_clicked = False
            except Exception as e:
                logger.debug(f"Gesture loop processing exception: {e}")
 
            time.sleep(0.015)
 
        hands.close()

    def _stop_drawing(self):
        if self.is_drawing:
            self.is_drawing = False
            self._process_drawn_signature()
            if self.canvas:
                self.canvas.signals.hide_canvas.emit()
                self.canvas.signals.clear_canvas.emit()

    def _process_drawn_signature(self):
        """Classifies the drawn strokes on the canvas and triggers actions."""
        if not self.canvas:
            return
            
        # Extract all points
        all_points = []
        for stroke in self.canvas.strokes:
            all_points.extend(stroke)
        all_points.extend(self.canvas.current_stroke)
        
        if len(all_points) < 15:
            return
            
        try:
            # 1. Normalize and classify
            xs = [p.x() for p in all_points]
            ys = [p.y() for p in all_points]
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)
            w = max_x - min_x
            h = max_y - min_y
            
            if w < 60 or h < 60:
                return
                
            norm_pts = []
            for p in all_points:
                nx = (p.x() - min_x) / w if w > 0 else 0
                ny = (p.y() - min_y) / h if h > 0 else 0
                norm_pts.append((nx, ny))
                
            start = norm_pts[0]
            end = norm_pts[-1]
            
            # Simple shape heuristics
            signature = ""
            dist_start_end = math.sqrt((start[0] - end[0])**2 + (start[1] - end[1])**2)
            
            # Check for Circle
            if dist_start_end < 0.25:
                cx = sum(p[0] for p in norm_pts) / len(norm_pts)
                cy = sum(p[1] for p in norm_pts) / len(norm_pts)
                radii = [math.sqrt((p[0] - cx)**2 + (p[1] - cy)**2) for p in norm_pts]
                avg_r = sum(radii) / len(radii)
                if avg_r > 0.15:
                    signature = "circle"
            else:
                # Divide into 4 quarters
                n = len(norm_pts)
                q1 = norm_pts[0 : n//4]
                q2 = norm_pts[n//4 : n//2]
                q3 = norm_pts[n//2 : 3*n//4]
                q4 = norm_pts[3*n//4 : ]
                
                if q1 and q2 and q3 and q4:
                    avg_q1_x = sum(p[0] for p in q1) / len(q1)
                    avg_q2_x = sum(p[0] for p in q2) / len(q2)
                    avg_q3_x = sum(p[0] for p in q3) / len(q3)
                    avg_q4_x = sum(p[0] for p in q4) / len(q4)
                    
                    avg_q1_y = sum(p[1] for p in q1) / len(q1)
                    avg_q4_y = sum(p[1] for p in q4) / len(q4)
                    
                    # 'C' shape: starts right, sweeps left, ends right, drawn top to bottom
                    if avg_q1_x > 0.55 and avg_q2_x < 0.45 and avg_q3_x < 0.45 and avg_q4_x > 0.55:
                        if avg_q1_y < avg_q4_y:
                            # If ends inward (moving left at the very end) -> 'G'
                            if end[0] < 0.65 and end[1] < 0.75:
                                signature = "G"
                            else:
                                signature = "C"
                    
                    # 'S' shape: starts right/center, goes left, goes right, goes left.
                    # We count center crossings on X
                    if not signature:
                        crossings = 0
                        prev_side = norm_pts[0][0] > 0.5
                        for p in norm_pts:
                            side = p[0] > 0.5
                            if side != prev_side:
                                crossings += 1
                                prev_side = side
                        if crossings >= 2 and start[1] < end[1]:
                            signature = "S"
                            
                    # 'W' shape: Y goes down, up, down, up
                    if not signature:
                        extrema = 0
                        for i in range(1, len(norm_pts) - 1):
                            if (norm_pts[i][1] > norm_pts[i-1][1] and norm_pts[i][1] > norm_pts[i+1][1]) or \
                               (norm_pts[i][1] < norm_pts[i-1][1] and norm_pts[i][1] < norm_pts[i+1][1]):
                                extrema += 1
                        if extrema >= 3:
                            signature = "W"
            
            if signature:
                logger.info(f"Signature Recognized: '{signature}'")
                self.canvas.signals.signature_detected.emit(signature)
        except Exception as err:
            logger.error(f"Error classifying air signature: {err}")
