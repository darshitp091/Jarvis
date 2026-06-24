import sys
import math
from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtCore import Qt, QPoint, QTimer, QPointF, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush

class HologramSimWidget(QWidget):
    update_object_signal = pyqtSignal(list, list, str)
    show_signal = pyqtSignal()
    hide_signal = pyqtSignal()
    """Futuristic floating 3D holographic wireframe viewer that skews based on face tracking."""
    def __init__(self, camera_engine=None):
        super().__init__()
        self.camera = camera_engine
        self.update_object_signal.connect(self._set_hologram_object_internal)
        self.show_signal.connect(super().show)
        self.hide_signal.connect(super().hide)
        
        # Borderless, stays on top, tool window, transparent
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(500, 500)
        self.drag_pos = None
        
        # Style
        self.setStyleSheet("""
            QWidget {
                background-color: rgba(10, 24, 47, 180);
                border: 2px solid rgba(0, 210, 255, 120);
                border-radius: 12px;
            }
        """)
        
        # Center on screen
        self.center_window()
        
        # 3D object vertices: Methane molecule (C in center, 4 H at tetrahedral vertices)
        self.vertices = [
            [0, 0, 0],       # Carbon center (0)
            [0, 100, 0],     # Hydrogen 1 (1)
            [94, -33, 0],    # Hydrogen 2 (2)
            [-47, -33, 81],  # Hydrogen 3 (3)
            [-47, -33, -81]  # Hydrogen 4 (4)
        ]
        self.connections = [
            (0, 1), (0, 2), (0, 3), (0, 4)
        ]
        self.object_name = "METHANE MOLECULE"
        
        # Rotation angles
        self.angle_x = 0.0
        self.angle_y = 0.0
        self.angle_z = 0.0
        
        # Viewport offsets for head-tracking parallax
        self.offset_x = 0.0
        self.offset_y = 0.0
        
        # Timer for rotation & head tracking updates (30 FPS)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_simulation)
        self.timer.start(33)

    def center_window(self):
        try:
            screen = QApplication.primaryScreen().geometry()
            self.move((screen.width() - self.width()) // 2, (screen.height() - self.height()) // 2)
        except Exception:
            self.move(300, 300)

    def update_simulation(self):
        # 1. Update rotation angles for ambient movement
        self.angle_x += 0.015
        self.angle_y += 0.02
        self.angle_z += 0.005
        
        # 2. Get head-tracking offset from CameraEngine
        target_offset_x = 0.0
        target_offset_y = 0.0
        
        face_rect = getattr(self.camera, "latest_face_rect", None) if self.camera else None
        if face_rect:
            # Find face center relative to frame center (typically 640x480 resolution)
            fx, fy, fw, fh = face_rect
            face_cx = fx + fw / 2
            face_cy = fy + fh / 2
            
            # Map coordinates (centered around 320, 240) to screen offsets (-80 to 80 pixels)
            target_offset_x = -(face_cx - 320) * 0.4
            target_offset_y = (face_cy - 240) * 0.4
        else:
            # Fallback: follow mouse position relative to widget center
            cursor = self.mapFromGlobal(self.cursor().pos())
            widget_cx = self.width() / 2
            widget_cy = self.height() / 2
            target_offset_x = (cursor.x() - widget_cx) * 0.15
            target_offset_y = (cursor.y() - widget_cy) * 0.15
            
        # Smoothly interpolate offset (lerp)
        self.offset_x += (target_offset_x - self.offset_x) * 0.15
        self.offset_y += (target_offset_y - self.offset_y) * 0.15
        
        self.update()

    def rotate_point(self, x, y, z):
        # Rotate Z-axis
        rad_z = self.angle_z
        x1 = x * math.cos(rad_z) - y * math.sin(rad_z)
        y1 = x * math.sin(rad_z) + y * math.cos(rad_z)
        z1 = z
        
        # Rotate Y-axis
        rad_y = self.angle_y
        x2 = x1 * math.cos(rad_y) + z1 * math.sin(rad_y)
        y2 = y1
        z2 = -x1 * math.sin(rad_y) + z1 * math.cos(rad_y)
        
        # Rotate X-axis
        rad_x = self.angle_x
        x3 = x2
        y3 = y2 * math.cos(rad_x) - z2 * math.sin(rad_x)
        z3 = y2 * math.sin(rad_x) + z2 * math.cos(rad_x)
        
        return x3, y3, z3

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        
        w = self.width()
        h = self.height()
        cx, cy = w // 2, h // 2
        
        # Background glassmorphic grid
        painter.setPen(QPen(QColor(0, 210, 255, 30), 1))
        grid_space = 25
        for x in range(0, w, grid_space):
            painter.drawLine(x, 0, x, h)
        for y in range(0, h, grid_space):
            painter.drawLine(0, y, w, y)
            
        # Project 3D points to 2D screen with head-tracking offset parallax
        projected = []
        for pt in self.vertices:
            rx, ry, rz = self.rotate_point(pt[0], pt[1], pt[2])
            proj_x = cx + rx + self.offset_x
            proj_y = cy + ry + self.offset_y
            projected.append(QPointF(proj_x, proj_y))

        # Draw connections (bonds)
        pen_bond = QPen(QColor(0, 210, 255, 180), 2)
        painter.setPen(pen_bond)
        for c in self.connections:
            painter.drawLine(projected[c[0]], projected[c[1]])

        # Draw all vertices as glowing nodes
        painter.setPen(QPen(QColor(0, 255, 180), 2))
        painter.setBrush(QBrush(QColor(0, 210, 255, 180)))
        for pt in projected:
            painter.drawEllipse(pt.toPoint(), 6, 6)
            
        # Header text
        painter.setPen(QColor(0, 210, 255, 220))
        painter.drawText(20, 30, f"JARVIS HOLOGRAMSIM: {self.object_name}")
        painter.drawText(20, 50, f"PARALLAX OFFSET X: {self.offset_x:.2f}")
        painter.drawText(20, 70, f"PARALLAX OFFSET Y: {self.offset_y:.2f}")
        status = "CAMERA TRACKING" if (self.camera and self.camera.latest_face_rect) else "MOUSE EMULATION"
        painter.drawText(20, 90, f"TRACKING STATUS: {status}")

    def set_hologram_object(self, vertices, connections, type_name="METHANE MOLECULE"):
        self.update_object_signal.emit(vertices, connections, type_name)

    def _set_hologram_object_internal(self, vertices, connections, type_name="METHANE MOLECULE"):
        """Load a custom 3D wireframe mesh shape into the hologram viewer."""
        self.vertices = vertices
        self.connections = connections
        self.object_name = type_name.upper()
        self.update()

    def show(self):
        self.show_signal.emit()

    def hide(self):
        self.hide_signal.emit()

    # Draggable window behavior
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self.drag_pos and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_pos)

    def mouseReleaseEvent(self, event):
        self.drag_pos = None
