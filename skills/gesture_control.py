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
    """Tracks hand landmarks and translates them into smooth mouse, click, and window gestures."""

    def __init__(self, camera_engine, canvas=None):
        self.camera = camera_engine
        self.canvas = canvas
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

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        self.thread = threading.Thread(target=self._gesture_loop, daemon=True)
        self.thread.start()
        logger.info("Smooth Hand Gesture Control thread started.")

    def stop(self):
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=2)
        logger.info("Smooth Hand Gesture Control thread stopped.")

    def _gesture_loop(self):
        try:
            import mediapipe as mp
            mp_hands = mp.solutions.hands
            hands = mp_hands.Hands(
                max_num_hands=2,
                min_detection_confidence=0.7,
                min_tracking_confidence=0.7
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
                
                if results.multi_hand_landmarks:
                    landmarks = results.multi_hand_landmarks[0].landmark
                    
                    # 1. Coordinate Scaling & Smoothing
                    hx = landmarks[8].x # Tip of index finger
                    hy = landmarks[8].y
                    
                    # Mirror X axis for camera inversion
                    raw_x = 1.0 - hx
                    raw_y = hy
                    
                    # Map center region [0.2, 0.8] to [0.0, 1.0] for comfortable edge-reaching bounds
                    scaled_x = (raw_x - 0.2) / 0.6
                    scaled_y = (raw_y - 0.2) / 0.6
                    
                    # Clamp to screen edges
                    scaled_x = max(0.0, min(1.0, scaled_x))
                    scaled_y = max(0.0, min(1.0, scaled_y))
                    
                    # Scale to pixel resolution
                    target_x = int(scaled_x * screen_w)
                    target_y = int(scaled_y * screen_h)
                    
                    # Apply Exponential Moving Average (EMA) smoothing
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
                    
                    # 3. Pinch Distances
                    thumb_index_dist = get_dist(landmarks[4], landmarks[8])
                    thumb_middle_dist = get_dist(landmarks[4], landmarks[12])
                    thumb_pinky_dist = get_dist(landmarks[4], landmarks[20])

                    # 4. Gesture Classification State Machine
                    
                    # GESTURE A: Air Writing (Rock-On Sign: Index + Pinky extended, Middle & Ring folded)
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
                            
                    # GESTURE B: Left Click / Drag (Index extended + Thumb pinched to Index tip)
                    elif index_extended and not middle_extended and not ring_extended and not pinky_extended and thumb_index_dist < 0.045:
                        self.fist_start_time = None
                        self.is_dragging = False
                        self.is_scrolling = False
                        if self.is_drawing:
                            self.is_drawing = False
                            if self.canvas:
                                self.canvas.signals.hide_canvas.emit()
                                self.canvas.signals.clear_canvas.emit()
                        
                        ctypes.windll.user32.SetCursorPos(cx, cy)
                        
                        if not self.is_left_clicked:
                            pyautogui.mouseDown()
                            self.is_left_clicked = True
                            logger.info("Gesture Controller: Mouse Down (Drag active)")
 
                    # GESTURE C: Right Click (Middle extended + Thumb pinched to Middle tip)
                    elif middle_extended and not index_extended and not ring_extended and not pinky_extended and thumb_middle_dist < 0.045:
                        self.fist_start_time = None
                        self.is_dragging = False
                        self.is_scrolling = False
                        pyautogui.rightClick()
                        logger.info("Gesture Controller: Right click executed")
                        time.sleep(0.5)
 
                    # GESTURE D: Double Click (Pinky extended + Thumb pinched to Pinky tip)
                    elif pinky_extended and not index_extended and not middle_extended and not ring_extended and thumb_pinky_dist < 0.045:
                        self.fist_start_time = None
                        self.is_dragging = False
                        self.is_scrolling = False
                        pyautogui.doubleClick()
                        logger.info("Gesture Controller: Double click executed")
                        time.sleep(0.5)
 
                    # GESTURE E: Scroll Mode (Index + Middle + Ring extended, Pinky folded)
                    elif index_extended and middle_extended and ring_extended and not pinky_extended:
                        self.fist_start_time = None
                        self.is_dragging = False
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
 
                    # GESTURE F: Drag & Move Active Window (Index + Middle extended, others folded - No pinch)
                    elif index_extended and middle_extended and not ring_extended and not pinky_extended:
                        self.fist_start_time = None
                        self.is_scrolling = False
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
 
                    # GESTURE G: Closed Fist (Close Foreground Window with Debounce)
                    elif not index_extended and not middle_extended and not ring_extended and not pinky_extended:
                        self.is_scrolling = False
                        self.is_dragging = False
                        if self.is_left_clicked:
                            pyautogui.mouseUp()
                            self.is_left_clicked = False
                        
                        if self.fist_start_time is None:
                            self.fist_start_time = time.time()
                        elif time.time() - self.fist_start_time >= 1.5:
                            hwnd_to_close = get_active_window_hwnd()
                            if hwnd_to_close:
                                # Get the PID of the active window to prevent closing self/terminal
                                active_pid = ctypes.c_ulong()
                                ctypes.windll.user32.GetWindowThreadProcessId(hwnd_to_close, ctypes.byref(active_pid))
                                if active_pid.value != os.getpid():
                                    logger.info("Gesture Controller: Closed fist held for 1.5s. Closing foreground window.")
                                    close_window_hwnd(hwnd_to_close)
                                    self.fist_start_time = None
                                    time.sleep(1.0) # Debounce
                                else:
                                    logger.info("Gesture Controller: Excluded closing self/terminal process window.")
                                    self.fist_start_time = None
 
                    # GESTURE H: Standard Hover (Index extended, others folded - No pinch)
                    elif index_extended and not middle_extended and not ring_extended and not pinky_extended:
                        self.fist_start_time = None
                        self.is_scrolling = False
                        self.is_dragging = False
                        if self.is_left_clicked:
                            pyautogui.mouseUp()
                            self.is_left_clicked = False
                            logger.info("Gesture Controller: Mouse Up (Release drag)")
                        
                        if self.is_drawing:
                            self.is_drawing = False
                            if self.canvas:
                                self.canvas.signals.hide_canvas.emit()
                                self.canvas.signals.clear_canvas.emit()
                        
                        ctypes.windll.user32.SetCursorPos(cx, cy)
                    
                    # DEFAULT: Palm Open / Relaxed (Release all clicks/drawings)
                    else:
                        self.fist_start_time = None
                        self.is_scrolling = False
                        self.is_dragging = False
                        if self.is_left_clicked:
                            pyautogui.mouseUp()
                            self.is_left_clicked = False
                            logger.info("Gesture Controller: Mouse Up (Release drag)")
                        
                        if self.is_drawing:
                            self.is_drawing = False
                            if self.canvas:
                                self.canvas.signals.hide_canvas.emit()
                                self.canvas.signals.clear_canvas.emit()
                else:
                    # No hands detected: release clicks and reset dragging
                    self.fist_start_time = None
                    self.is_dragging = False
                    self.is_scrolling = False
                    if self.is_left_clicked:
                        pyautogui.mouseUp()
                        self.is_left_clicked = False
                    if self.is_drawing:
                        self.is_drawing = False
                        if self.canvas:
                            self.canvas.signals.hide_canvas.emit()
                            self.canvas.signals.clear_canvas.emit()
            except Exception as e:
                logger.debug(f"Gesture loop processing exception: {e}")

            # Match FPS of camera updates
            time.sleep(0.015)

        hands.close()

if __name__ == "__main__":
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from core.vision_engine import CameraEngine
    camera = CameraEngine()
    camera.start()
    controller = GestureController(camera)
    controller.start()
    
    print("Testing Gesture Controller in standalone mode. Control windows in air!")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        controller.stop()
        camera.stop()
