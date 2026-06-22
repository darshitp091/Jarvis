import os
import time
from PyQt6.QtWidgets import QWidget, QApplication, QLabel, QRubberBand
from PyQt6.QtCore import Qt, QPoint, QSize, QRect, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QGuiApplication
import pyautogui
from PIL import Image

class EyeCareOverlay(QWidget):
    """Transparent overlay window colored amber at 15% opacity to act as a night-light filter."""
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.Tool | 
            Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        
        # Cover all monitors virtual geometry
        rect = QGuiApplication.primaryScreen().virtualGeometry()
        self.setGeometry(rect)
        
    def paintEvent(self, event):
        painter = QPainter(self)
        # Amber/Warm orange color with 15% opacity (38/255)
        painter.fillRect(self.rect(), QColor(255, 176, 0, 38))


class ScreenRuler(QWidget):
    """Transparent fullscreen overlay displaying a draggable ruler with horizontal/vertical pixel guides."""
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # Cover primary screen
        screen = QGuiApplication.primaryScreen().geometry()
        self.setGeometry(screen)
        
        self.mouse_pos = QPoint(0, 0)
        self.setMouseTracking(True)
        self.label = QLabel(self)
        self.label.setStyleSheet("color: white; background-color: rgba(0, 0, 0, 180); padding: 5px; border-radius: 3px; font-weight: bold;")
        self.label.adjustSize()
        self.label.hide()
        
    def mouseMoveEvent(self, event):
        self.mouse_pos = event.position().toPoint()
        self.label.setText(f"X: {self.mouse_pos.x()} px | Y: {self.mouse_pos.y()} px")
        self.label.adjustSize()
        # Position label offset from cursor
        self.label.move(self.mouse_pos.x() + 15, self.mouse_pos.y() + 15)
        self.label.show()
        self.update()
        
    def paintEvent(self, event):
        painter = QPainter(self)
        pen = QPen(QColor(0, 220, 255), 1, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        
        # Draw horizontal and vertical guides crossing at mouse cursor
        w = self.width()
        h = self.height()
        painter.drawLine(0, self.mouse_pos.y(), w, self.mouse_pos.y())
        painter.drawLine(self.mouse_pos.x(), 0, self.mouse_pos.x(), h)
        
        # Draw small tick marks along the guides
        painter.setPen(QPen(QColor(0, 220, 255, 120), 1))
        for x in range(0, w, 50):
            painter.drawLine(x, self.mouse_pos.y() - 5, x, self.mouse_pos.y() + 5)
        for y in range(0, h, 50):
            painter.drawLine(self.mouse_pos.x() - 5, y, self.mouse_pos.x() + 5, y)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()


class SnippingOverlay(QWidget):
    """Fullscreen transparent window allowing the user to click-and-drag to capture a screenshot region."""
    
    snipped = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.CrossCursor)
        
        # Cover virtual geometry of all screens
        rect = QGuiApplication.primaryScreen().virtualGeometry()
        self.setGeometry(rect)
        
        self.origin = QPoint()
        self.rubber_band = QRubberBand(QRubberBand.Shape.Rectangle, self)
        
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.origin = event.position().toPoint()
            self.rubber_band.setGeometry(QRect(self.origin, QSize()))
            self.rubber_band.show()
            
    def mouseMoveEvent(self, event):
        if not self.origin.isNull():
            self.rubber_band.setGeometry(QRect(self.origin, event.position().toPoint()).normalized())
            
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.rubber_band.hide()
            rect = QRect(self.origin, event.position().toPoint()).normalized()
            self.close()
            
            # Crop region
            if rect.width() > 5 and rect.height() > 5:
                # Capture full screen first, then crop
                screenshot = pyautogui.screenshot()
                # Map Qt coordinate systems to pyautogui coordinates
                # PyQt might start relative to virtual coordinates
                left = rect.left()
                top = rect.top()
                width = rect.width()
                height = rect.height()
                
                cropped = screenshot.crop((left, top, left + width, top + height))
                os.makedirs("config", exist_ok=True)
                save_path = f"config/snip_{int(time.time())}.png"
                cropped.save(save_path)
                
                # Copy to clipboard
                try:
                    import io
                    # PyQt6 clipboard image copy
                    from PyQt6.QtGui import QImage
                    image = QImage(save_path)
                    QApplication.clipboard().setImage(image)
                except Exception:
                    pass
                    
                self.snipped.emit(save_path)
            else:
                self.snipped.emit("")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            self.snipped.emit("")
