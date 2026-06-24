import sys
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QApplication
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint
from PyQt6.QtGui import QColor, QPainter, QLinearGradient

class HudToast(QWidget):
    """A sleek glassmorphism-style Stark-themed floating notification toast."""

    def __init__(self, title: str, message: str, duration_ms: int = 5000):
        super().__init__()
        self.title = title
        self.message = message
        self.duration_ms = duration_ms
        self._setup_ui()
        self._animate_entry()

    def _setup_ui(self):
        # Frameless, stays on top, tool window (no taskbar icon)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.SubWindow
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(5)
        
        # Title Label
        self.title_label = QLabel(self.title)
        self.title_label.setStyleSheet("color: #00d2ff; font-weight: bold; font-size: 13px; font-family: 'Segoe UI', Arial;")
        layout.addWidget(self.title_label)
        
        # Message Label
        self.msg_label = QLabel(self.message)
        self.msg_label.setWordWrap(True)
        self.msg_label.setStyleSheet("color: #ffffff; font-size: 11px; font-family: 'Segoe UI', Arial;")
        layout.addWidget(self.msg_label)

        self.setFixedSize(300, 80)
        
        # Position in top-right of screen
        try:
            screen = QApplication.primaryScreen().geometry()
            self.x_pos = screen.width() - 320
        except Exception:
            self.x_pos = 1000
        self.y_pos = 40
        self.move(self.x_pos, self.y_pos)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Semi-transparent dark blue glass background
        gradient = QLinearGradient(0, 0, self.width(), self.height())
        gradient.setColorAt(0, QColor(10, 25, 47, 210))
        gradient.setColorAt(1, QColor(0, 40, 80, 210))
        
        painter.setBrush(gradient)
        
        # Neon blue border
        painter.setPen(QColor(0, 210, 255, 180))
        painter.drawRoundedRect(0, 0, self.width() - 1, self.height() - 1, 8, 8)

    def _animate_entry(self):
        self.setWindowOpacity(0.0)
        self.show()
        
        # Fade animation
        self.fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self.fade_anim.setDuration(400)
        self.fade_anim.setStartValue(0.0)
        self.fade_anim.setEndValue(1.0)
        self.fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        # Position slide animation
        self.slide_anim = QPropertyAnimation(self, b"pos")
        self.slide_anim.setDuration(400)
        self.slide_anim.setStartValue(QPoint(self.x_pos + 100, self.y_pos))
        self.slide_anim.setEndValue(QPoint(self.x_pos, self.y_pos))
        self.slide_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        self.fade_anim.start()
        self.slide_anim.start()
        
        # Dismiss Timer
        self.dismiss_timer = QTimer(self)
        self.dismiss_timer.setSingleShot(True)
        self.dismiss_timer.timeout.connect(self._animate_exit)
        self.dismiss_timer.start(self.duration_ms)

    def _animate_exit(self):
        self.exit_fade = QPropertyAnimation(self, b"windowOpacity")
        self.exit_fade.setDuration(400)
        self.exit_fade.setStartValue(1.0)
        self.exit_fade.setEndValue(0.0)
        self.exit_fade.setEasingCurve(QEasingCurve.Type.InCubic)
        self.exit_fade.finished.connect(self.close)
        self.exit_fade.start()

class HudNotificationManager:
    """Manages active toast notifications, stacking them vertically."""
    
    _active_toasts = []

    @classmethod
    def show_toast(cls, title: str, message: str, duration_ms: int = 5000):
        # Shift existing toasts down
        for i, toast in enumerate(cls._active_toasts):
            try:
                if toast.isVisible():
                    # Move down by 90 pixels
                    new_y = 40 + (len(cls._active_toasts) - i) * 90
                    toast.move(toast.x_pos, new_y)
            except Exception:
                pass
                
        # Create and display new toast
        toast = HudToast(title, message, duration_ms)
        cls._active_toasts.append(toast)
        
        # Clean up reference when closed
        toast.destroyed.connect(lambda: cls._remove_toast(toast))
        
    @classmethod
    def _remove_toast(cls, toast):
        if toast in cls._active_toasts:
            cls._active_toasts.remove(toast)
