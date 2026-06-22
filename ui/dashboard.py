import sys
import os
import json
import time
import cv2
import psutil
from PyQt6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, 
    QProgressBar, QFrame, QApplication, QListWidget
)
from PyQt6.QtCore import Qt, QTimer, QPoint
from PyQt6.QtGui import QFont, QColor, QImage, QPixmap
from loguru import logger

# Add root folder to sys.path to resolve imports cleanly
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from core.vision_engine import CameraEngine

class JarvisDashboard(QWidget):
    """Futuristic Glassmorphic HUD Dashboard showing system stats, schedule, and camera stream."""

    def __init__(self, camera_engine=None):
        super().__init__()
        self.camera = camera_engine if camera_engine else CameraEngine()
        self.drag_pos = None

        self._setup_ui()
        self._start_timers()

    def _setup_ui(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(850, 520)

        # Style sheet representing futuristic glassmorphism
        self.setStyleSheet("""
            QWidget#MainFrame {
                background-color: rgba(10, 20, 35, 0.88);
                border: 2px solid rgba(0, 240, 255, 0.4);
                border-radius: 16px;
            }
            QLabel {
                color: #00f0ff;
                font-family: 'Consolas', 'Segoe UI', monospace;
            }
            QProgressBar {
                border: 1px solid rgba(0, 240, 255, 0.3);
                border-radius: 4px;
                text-align: center;
                background-color: rgba(0, 0, 0, 0.5);
                color: #ffffff;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                                  stop:0 #0066aa, stop:1 #00f0ff);
                border-radius: 3px;
            }
            QListWidget {
                background-color: rgba(0, 0, 0, 0.4);
                border: 1px solid rgba(0, 240, 255, 0.2);
                border-radius: 8px;
                color: #00f0ff;
                font-family: 'Consolas', monospace;
                font-size: 13px;
            }
        """)

        # Main layout wrap
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Outer border frame container
        container = QFrame()
        container.setObjectName("MainFrame")
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(20, 20, 20, 20)

        # ── Title / Header ──
        header_layout = QHBoxLayout()
        self.title_label = QLabel("JARVIS HUD - CORE DIAGNOSTICS")
        self.title_label.setFont(QFont("Consolas", 18, QFont.Weight.Bold))
        
        self.status_label = QLabel("SYSTEM: NOMINAL")
        self.status_label.setFont(QFont("Consolas", 12))
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.status_label.setStyleSheet("color: #33ff66;")

        header_layout.addWidget(self.title_label)
        header_layout.addWidget(self.status_label)
        container_layout.addLayout(header_layout)

        # Separator line
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background-color: rgba(0, 240, 255, 0.3); max-height: 1px;")
        container_layout.addWidget(sep)

        # ── Body Grid (Left: Camera / Right: Stats & Calendar) ──
        body_layout = QHBoxLayout()
        body_layout.setSpacing(20)

        # Left Column: Video Panel
        left_layout = QVBoxLayout()
        self.cam_title = QLabel("CAMERA TARGET STREAM")
        self.cam_title.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
        left_layout.addWidget(self.cam_title)

        self.video_feed = QLabel()
        self.video_feed.setFixedSize(380, 285)
        self.video_feed.setStyleSheet("background-color: rgba(0, 0, 0, 0.6); border: 1px solid rgba(0, 240, 255, 0.3); border-radius: 8px;")
        self.video_feed.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_layout.addWidget(self.video_feed)
        body_layout.addLayout(left_layout, stretch=4)

        # Right Column: Widgets
        right_layout = QVBoxLayout()

        # Widget 1: System stats
        stats_title = QLabel("CORE HARDWARE DIAGNOSTICS")
        stats_title.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
        right_layout.addWidget(stats_title)

        cpu_box = QHBoxLayout()
        self.cpu_label = QLabel("CPU: ")
        self.cpu_label.setFont(QFont("Consolas", 10))
        self.cpu_bar = QProgressBar()
        self.cpu_bar.setRange(0, 100)
        cpu_box.addWidget(self.cpu_label, stretch=1)
        cpu_box.addWidget(self.cpu_bar, stretch=4)
        right_layout.addLayout(cpu_box)

        ram_box = QHBoxLayout()
        self.ram_label = QLabel("RAM: ")
        self.ram_label.setFont(QFont("Consolas", 10))
        self.ram_bar = QProgressBar()
        self.ram_bar.setRange(0, 100)
        ram_box.addWidget(self.ram_label, stretch=1)
        ram_box.addWidget(self.ram_bar, stretch=4)
        right_layout.addLayout(ram_box)

        # Widget 2: Calendar List
        cal_title = QLabel("UPCOMING PROTOCOLS (CALENDAR)")
        cal_title.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
        cal_title.setStyleSheet("margin-top: 10px;")
        right_layout.addWidget(cal_title)

        self.cal_list = QListWidget()
        right_layout.addWidget(self.cal_list)

        body_layout.addLayout(right_layout, stretch=5)
        container_layout.addLayout(body_layout)

        # ── Footer Info ──
        footer_layout = QHBoxLayout()
        self.footer_text = QLabel("SECURE CONTEXT INTERFACE ACTIVE // LEVEL 4 AUTHORIZATION REQUIRED")
        self.footer_text.setFont(QFont("Consolas", 8))
        self.footer_text.setStyleSheet("color: rgba(0, 240, 255, 0.5);")
        
        self.time_label = QLabel()
        self.time_label.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        
        footer_layout.addWidget(self.footer_text)
        footer_layout.addWidget(self.time_label)
        container_layout.addLayout(footer_layout)

        main_layout.addWidget(container)

        # Center on primary screen
        self._center_on_screen()

    def _center_on_screen(self):
        try:
            screen = QApplication.primaryScreen().geometry()
            self.move((screen.width() - self.width()) // 2, (screen.height() - self.height()) // 2)
        except Exception:
            self.move(200, 200)

    def _start_timers(self):
        # 1. 20 FPS Camera Stream Timer (50ms)
        self.cam_timer = QTimer()
        self.cam_timer.timeout.connect(self._update_camera_feed)
        self.cam_timer.start(50)

        # 2. 1Hz System Stats & Time & Calendar Timer (1000ms)
        self.stats_timer = QTimer()
        self.stats_timer.timeout.connect(self._update_stats_and_calendar)
        self.stats_timer.start(1000)
        self._update_stats_and_calendar() # initial load

    def _update_camera_feed(self):
        frame = self.camera.latest_frame
        if frame is None:
            self.video_feed.setText("CAMERA OFFLINE / DISCONNECTED")
            return

        try:
            # We copy the frame to modify it
            img = frame.copy()
            h, w, ch = img.shape
            
            # Detect faces to draw on screen - thread-safe
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            with self.camera.lock:
                faces = self.camera.face_cascade.detectMultiScale(
                    gray, scaleFactor=1.1, minNeighbors=5, minSize=(50, 50)
                )

            # Draw futuristic HUD indicators
            for (x, y, fw, fh) in faces:
                # Bounding box
                cv2.rectangle(img, (x, y), (x+fw, y+fh), (255, 240, 0), 2)  # Cyan in RGB is BGR (255, 240, 0)
                
                # Corner bracket decorations
                length = 15
                # Top left
                cv2.line(img, (x, y), (x + length, y), (255, 240, 0), 4)
                cv2.line(img, (x, y), (x, y + length), (255, 240, 0), 4)
                # Top right
                cv2.line(img, (x + fw, y), (x + fw - length, y), (255, 240, 0), 4)
                cv2.line(img, (x + fw, y), (x, y + length), (255, 240, 0), 4)
                # Bottom left
                cv2.line(img, (x, y + fh), (x + length, y + fh), (255, 240, 0), 4)
                cv2.line(img, (x, y + fh), (x, y + fh - length), (255, 240, 0), 4)
                # Bottom right
                cv2.line(img, (x + fw, y + fh), (x + fw - length, y + fh), (255, 240, 0), 4)
                cv2.line(img, (x + fw, y + fh), (x + fw, y + fh - length), (255, 240, 0), 4)

                # Try face match identification
                face_crop = cv2.resize(gray[y:y+fh, x:x+fw], (200, 200))
                is_owner = False
                confidence = 999
                if self.camera.has_face_model:
                    try:
                        with self.camera.lock:
                            label, confidence = self.camera.face_recognizer.predict(face_crop)
                        if label == 1 and confidence <= 85.0:
                            is_owner = True
                    except Exception:
                        pass
                
                if is_owner:
                    label_str = f"OWNER DETECTED ({confidence:.1f})"
                    color = (0, 255, 0) # Green BGR
                else:
                    label_str = "UNKNOWN VISITOR"
                    color = (0, 0, 255) # Red BGR

                cv2.putText(img, label_str, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)

            # Resize to fit QLabel
            img_resized = cv2.resize(img, (380, 285))
            
            # Convert BGR (OpenCV) to RGB (Qt)
            img_rgb = cv2.cvtColor(img_resized, cv2.COLOR_BGR2RGB)
            
            # Create QImage and QPixmap
            q_img = QImage(img_rgb.data, 380, 285, 380 * 3, QImage.Format.Format_RGB888)
            pixmap = QPixmap.fromImage(q_img)
            self.video_feed.setPixmap(pixmap)
        except Exception as e:
            logger.error(f"Error updating HUD camera feed: {e}")

    def _update_stats_and_calendar(self):
        # 1. Stats
        try:
            cpu = int(psutil.cpu_percent())
            ram = int(psutil.virtual_memory().percent)
            self.cpu_bar.setValue(cpu)
            self.ram_bar.setValue(ram)
        except Exception as e:
            logger.debug(f"Dashboard stats error: {e}")

        # 2. Time
        self.time_label.setText(time.strftime("%H:%M:%S // %Y-%m-%d"))

        # 3. Calendar List
        calendar_path = os.path.abspath("config/calendar.json")
        if os.path.exists(calendar_path):
            try:
                with open(calendar_path, "r", encoding="utf-8") as f:
                    events = json.load(f)
                
                self.cal_list.clear()
                # Sort upcoming items
                events_sorted = []
                for e in events:
                    if not e.get("triggered", False):
                        events_sorted.append(e)

                if not events_sorted:
                    self.cal_list.addItem("NO PENDING PROTOCOLS")
                else:
                    for item in events_sorted[:5]:
                        # Format "2026-06-19T20:28:18" -> "20:28 - Topic"
                        try:
                            t_str = item["time"].split("T")[1][:5]
                        except Exception:
                            t_str = "ALARM"
                        self.cal_list.addItem(f"[{t_str}] {item['text']}")
            except Exception as e:
                logger.error(f"Error updating dashboard calendar: {e}")

    # Drag-and-drop window movements
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self.drag_pos and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_pos)

    def mouseReleaseEvent(self, event):
        self.drag_pos = None


if __name__ == "__main__":
    app = QApplication(sys.argv)
    dashboard = JarvisDashboard()
    dashboard.show()
    sys.exit(app.exec())
