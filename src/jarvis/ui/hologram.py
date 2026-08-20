import sys
import math
from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtCore import Qt, QPoint, QTimer, QPointF, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush

class HologramSimWidget(QWidget):
    update_object_signal = pyqtSignal(list, list, str, list)
    node_clicked_signal = pyqtSignal(int, str)
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
        self.labels = ["Carbon", "Hydrogen 1", "Hydrogen 2", "Hydrogen 3", "Hydrogen 4"]
        self.selected_node_idx = None
        self.object_name = "METHANE MOLECULE"
        
        # Rotation angles
        self.angle_x = 0.0
        self.angle_y = 0.0
        self.angle_z = 0.0
        
        # Advanced Visual States
        self.explode_factor = 0.0
        self.target_explode_factor = 0.0
        self.heatmap_active = False
        self.base_rotation_speed_y = 0.02
        
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
        self.angle_x += 0.012
        self.angle_y += self.base_rotation_speed_y
        self.angle_z += 0.005
        
        # Smoothly interpolate explode factor
        self.explode_factor += (self.target_explode_factor - self.explode_factor) * 0.1
        
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
            # Radial explosion displacement
            dist = math.sqrt(pt[0]**2 + pt[1]**2 + pt[2]**2)
            if dist > 0:
                dx = pt[0] / dist
                dy = pt[1] / dist
                dz = pt[2] / dist
                ex = pt[0] + dx * self.explode_factor * 100.0
                ey = pt[1] + dy * self.explode_factor * 100.0
                ez = pt[2] + dz * self.explode_factor * 100.0
            else:
                ex, ey, ez = pt[0], pt[1], pt[2]
                
            rx, ry, rz = self.rotate_point(ex, ey, ez)
            proj_x = cx + rx + self.offset_x
            proj_y = cy + ry + self.offset_y
            projected.append(QPointF(proj_x, proj_y))

        # Draw connections (bonds)
        for c in self.connections:
            if c[0] < len(projected) and c[1] < len(projected):
                if self.heatmap_active:
                    # Heatmap mode: connections to center/gateway are red, others orange
                    color = QColor(255, 60, 60, 200) if (c[0] == 0 or c[1] == 0) else QColor(255, 140, 0, 180)
                else:
                    color = QColor(0, 210, 255, 180)
                pen_bond = QPen(color, 2)
                painter.setPen(pen_bond)
                painter.drawLine(projected[c[0]], projected[c[1]])

        # Draw all vertices as glowing nodes
        for idx, pt in enumerate(projected):
            if idx == self.selected_node_idx:
                painter.setPen(QPen(QColor(255, 100, 100), 2))
                painter.setBrush(QBrush(QColor(255, 50, 50, 220)))
                size = 9
            elif self.heatmap_active:
                if idx == 0:
                    painter.setPen(QPen(QColor(255, 50, 50), 2))
                    painter.setBrush(QBrush(QColor(255, 0, 0, 230)))
                    size = 8
                else:
                    painter.setPen(QPen(QColor(255, 165, 0), 2))
                    painter.setBrush(QBrush(QColor(255, 215, 0, 210)))
                    size = 6
            else:
                painter.setPen(QPen(QColor(0, 255, 180), 2))
                painter.setBrush(QBrush(QColor(0, 210, 255, 180)))
                size = 6
            painter.drawEllipse(pt.toPoint(), size, size)
            
            # Draw node label if present
            if hasattr(self, "labels") and idx < len(self.labels):
                label_text = self.labels[idx]
                if label_text:
                    painter.setPen(QColor(255, 255, 255, 200) if idx == self.selected_node_idx else QColor(0, 255, 180, 200))
                    painter.drawText(int(pt.x()) + 10, int(pt.y()) + 5, label_text)
            
        # Header text
        painter.setPen(QColor(0, 210, 255, 220))
        painter.drawText(20, 30, f"JARVIS HOLOGRAMSIM: {self.object_name}")
        painter.drawText(20, 50, f"PARALLAX OFFSET X: {self.offset_x:.2f}")
        painter.drawText(20, 70, f"PARALLAX OFFSET Y: {self.offset_y:.2f}")
        status = "CAMERA TRACKING" if (self.camera and self.camera.latest_face_rect) else "MOUSE EMULATION"
        painter.drawText(20, 90, f"TRACKING STATUS: {status}")

    def set_hologram_object(self, vertices, connections, type_name="METHANE MOLECULE", labels=None):
        self.update_object_signal.emit(vertices, connections, type_name, labels or [])

    def _set_hologram_object_internal(self, vertices, connections, type_name="METHANE MOLECULE", labels=None):
        """Load a custom 3D wireframe mesh shape into the hologram viewer."""
        self.vertices = vertices
        self.connections = connections
        self.object_name = type_name.upper()
        self.labels = labels or []
        self.selected_node_idx = None
        self.update()

    def show(self):
        self.show_signal.emit()

    def hide(self):
        self.hide_signal.emit()

    def animate_explode(self, enable=True):
        self.target_explode_factor = 1.0 if enable else 0.0

    def set_rotation_speed(self, speed_str):
        if speed_str == "fast":
            self.base_rotation_speed_y = 0.08
        elif speed_str == "slow":
            self.base_rotation_speed_y = 0.015
        elif speed_str == "stop":
            self.base_rotation_speed_y = 0.0

    def toggle_heatmap(self, enable=True):
        self.heatmap_active = enable
        self.update()

    # Draggable window behavior & node selection click detection
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            click_pos = event.position()
            w = self.width()
            h = self.height()
            cx, cy = w // 2, h // 2
            
            clicked_node_idx = None
            for idx, pt in enumerate(self.vertices):
                rx, ry, rz = self.rotate_point(pt[0], pt[1], pt[2])
                proj_x = cx + rx + self.offset_x
                proj_y = cy + ry + self.offset_y
                if math.hypot(click_pos.x() - proj_x, click_pos.y() - proj_y) < 14:
                    clicked_node_idx = idx
                    break
                    
            if clicked_node_idx is not None:
                self.selected_node_idx = clicked_node_idx
                lbl = self.labels[clicked_node_idx] if clicked_node_idx < len(self.labels) else f"Node {clicked_node_idx}"
                self.node_clicked_signal.emit(clicked_node_idx, lbl)
                self.update()
            else:
                self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self.drag_pos and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_pos)

    def mouseReleaseEvent(self, event):
        self.drag_pos = None
