import sys
from PyQt6.QtWidgets import QApplication, QWidget, QMenu
from PyQt6.QtCore import Qt, QPoint, QTimer, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QRadialGradient, QAction
import math


class JarvisOrb(QWidget):
    """Floating draggable orb — JARVIS visual indicator"""

    state_changed = pyqtSignal(str)
    set_state_signal = pyqtSignal(str)
    dashboard_toggle_signal = pyqtSignal(bool)
    eyecare_toggle_signal = pyqtSignal(bool)
    ruler_toggle_signal = pyqtSignal(bool)
    snipping_tool_signal = pyqtSignal()
    notification_signal = pyqtSignal(str, str)
    hologram_toggle_signal = pyqtSignal(bool)

    STATES = {
        "idle":      (QColor(0, 120, 255), QColor(0, 60, 180)),
        "listening": (QColor(0, 220, 255), QColor(0, 160, 200)),
        "thinking":  (QColor(180, 180, 255), QColor(100, 100, 200)),
        "speaking":  (QColor(255, 255, 255), QColor(180, 180, 255)),
        "error":     (QColor(255, 60, 60), QColor(180, 0, 0)),
    }

    def __init__(self):
        super().__init__()
        self.state = "idle"
        self.drag_pos = None
        self.pulse = 0.0
        self.pulse_dir = 1
        self.toggle_callback = None
        self.set_state_signal.connect(self._set_state_internal)
        self._setup_window()
        self._setup_system_tray()
        self._start_pulse_timer()

    def _setup_system_tray(self):
        """Creates a Windows System Tray Icon in taskbar showing live status & controls."""
        try:
            from PyQt6.QtWidgets import QSystemTrayIcon, QMenu
            from PyQt6.QtGui import QIcon, QPixmap, QColor, QPainter

            pixmap = QPixmap(32, 32)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setBrush(QColor(0, 220, 255))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(4, 4, 24, 24)
            painter.end()

            self.tray_icon = QSystemTrayIcon(QIcon(pixmap), self)
            self.tray_icon.setToolTip("🎙️ JARVIS — AI Assistant Active & Listening")

            tray_menu = QMenu()
            show_action = QAction("🖥️ Show/Hide Dashboard", self)
            show_action.triggered.connect(lambda: self.dashboard_toggle_signal.emit(True))
            tray_menu.addAction(show_action)

            hologram_action = QAction("🌌 Toggle Hologram Sim", self)
            hologram_action.triggered.connect(lambda: self.hologram_toggle_signal.emit(True))
            tray_menu.addAction(hologram_action)

            eyecare_action = QAction("👁️ Toggle EyeCare Overlay", self)
            eyecare_action.triggered.connect(lambda: self.eyecare_toggle_signal.emit(True))
            tray_menu.addAction(eyecare_action)

            tray_menu.addSeparator()
            exit_action = QAction("❌ Exit JARVIS", self)
            exit_action.triggered.connect(QApplication.instance().quit)
            tray_menu.addAction(exit_action)

            self.tray_icon.setContextMenu(tray_menu)
            self.tray_icon.show()
        except Exception as e:
            pass

    def _setup_window(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(100, 100)

        # Center top of screen
        try:
            screen = QApplication.primaryScreen().geometry()
            self.move((screen.width() - 100) // 2, 20)
        except Exception:
            self.move(500, 20)
        
        self.show()

    def _start_pulse_timer(self):
        self.timer = QTimer()
        self.timer.timeout.connect(self._update_pulse)
        self.timer.start(30)

    def _update_pulse(self):
        speed = 0.05 if self.state == "idle" else 0.12
        self.pulse += speed * self.pulse_dir
        if self.pulse >= 1.0:
            self.pulse_dir = -1
        elif self.pulse <= 0.0:
            self.pulse_dir = 1
        self.update()

    def set_state(self, state: str):
        self.set_state_signal.emit(state)

    def _set_state_internal(self, state: str):
        if state in self.STATES:
            self.state = state
            self.update()
            self.state_changed.emit(state)
            if hasattr(self, "tray_icon") and self.tray_icon:
                tooltips = {
                    "idle": "⚡ JARVIS — Idle & Ready (Say 'Hey Jarvis')",
                    "listening": "🎙️ JARVIS — Listening to your voice...",
                    "thinking": "🧠 JARVIS — Processing command...",
                    "speaking": "🗣️ JARVIS — Speaking...",
                    "error": "⚠️ JARVIS — System Warning",
                }
                self.tray_icon.setToolTip(tooltips.get(state, "🎙️ JARVIS Active"))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        center_x, center_y = 50, 50
        base_radius = 30
        pulse_extra = self.pulse * 8

        inner_color, outer_color = self.STATES[self.state]

        # Outer glow
        glow = QRadialGradient(center_x, center_y, base_radius + pulse_extra + 15)
        glow_color = QColor(inner_color)
        glow_color.setAlpha(60)
        glow.setColorAt(0, glow_color)
        glow.setColorAt(1, QColor(0, 0, 0, 0))
        painter.setBrush(glow)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(
            int(center_x - base_radius - pulse_extra - 15),
            int(center_y - base_radius - pulse_extra - 15),
            int((base_radius + pulse_extra + 15) * 2),
            int((base_radius + pulse_extra + 15) * 2),
        )

        # Main orb
        grad = QRadialGradient(center_x - 8, center_y - 8, base_radius + pulse_extra)
        grad.setColorAt(0, inner_color)
        grad.setColorAt(1, outer_color)
        painter.setBrush(grad)
        painter.drawEllipse(
            int(center_x - base_radius - pulse_extra / 2),
            int(center_y - base_radius - pulse_extra / 2),
            int((base_radius + pulse_extra / 2) * 2),
            int((base_radius + pulse_extra / 2) * 2),
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            if self.state == "speaking":
                self.set_state("idle")
                self.state_changed.emit("interrupt")
        elif event.button() == Qt.MouseButton.RightButton:
            self._show_context_menu(event.globalPosition().toPoint())

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._trigger_toggle()

    def mouseMoveEvent(self, event):
        if self.drag_pos and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_pos)

    def mouseReleaseEvent(self, event):
        self.drag_pos = None

    def _show_context_menu(self, pos: QPoint):
        menu = QMenu(self)
        
        toggle_action = QAction("Toggle HUD Dashboard", self)
        toggle_action.triggered.connect(self._trigger_toggle)
        menu.addAction(toggle_action)
        
        quit_action = QAction("Quit JARVIS", self)
        quit_action.triggered.connect(QApplication.quit)
        menu.addAction(quit_action)
        menu.exec(pos)

    def _trigger_toggle(self):
        if hasattr(self, "toggle_callback") and self.toggle_callback:
            self.toggle_callback()



if __name__ == "__main__":
    app = QApplication(sys.argv)
    orb = JarvisOrb()
    
    # Simple state rotation for testing
    states = list(JarvisOrb.STATES.keys())
    current_idx = 0
    
    def switch_state():
        global current_idx
        current_idx = (current_idx + 1) % len(states)
        orb.set_state(states[current_idx])
        print(f"State: {states[current_idx]}")
        
    timer = QTimer()
    timer.timeout.connect(switch_state)
    timer.start(2000)
    
    print("Testing JARVIS Orb UI. Right click to close.")
    sys.exit(app.exec())
