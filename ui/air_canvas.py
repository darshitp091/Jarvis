import sys
from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QPen, QColor
from PyQt6.QtCore import Qt, QPoint, pyqtSignal, QObject

class AirCanvasSignals(QObject):
    add_point = pyqtSignal(int, int)
    start_stroke = pyqtSignal()
    clear_canvas = pyqtSignal()
    show_canvas = pyqtSignal()
    hide_canvas = pyqtSignal()

class AirCanvas(QWidget):
    """Transparent full-screen whiteboard overlay for virtual neon air writing."""
    
    def __init__(self):
        super().__init__()
        # Set borderless, transparent, stays on top, and ignores mouse clicks so it is click-through
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.SubWindow
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        
        # Maximize to full screen
        self.showFullScreen()
        
        # Stroke collection: list of lists of QPoints
        self.strokes = []
        self.current_stroke = []
        
        # Signals for thread-safe cross-thread calls from the gesture controller
        self.signals = AirCanvasSignals()
        self.signals.add_point.connect(self._add_point)
        self.signals.start_stroke.connect(self._start_stroke)
        self.signals.clear_canvas.connect(self._clear_canvas)
        self.signals.show_canvas.connect(self.show)
        self.signals.hide_canvas.connect(self.hide)
        
        self.hide() # Hidden by default until activated by gesture

    def _start_stroke(self):
        if self.current_stroke:
            self.strokes.append(self.current_stroke)
        self.current_stroke = []

    def _add_point(self, x, y):
        self.current_stroke.append(QPoint(x, y))
        self.update()

    def _clear_canvas(self):
        self.strokes = []
        self.current_stroke = []
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        
        # Draw strokes with a bright neon green pen
        pen = QPen(
            QColor(0, 255, 127), 
            6, 
            Qt.PenStyle.SolidLine, 
            Qt.PenCapStyle.RoundCap, 
            Qt.PenJoinStyle.RoundJoin
        )
        painter.setPen(pen)
        
        # Draw completed strokes
        for stroke in self.strokes:
            for i in range(len(stroke) - 1):
                painter.drawLine(stroke[i], stroke[i+1])
                
        # Draw current active stroke
        if len(self.current_stroke) > 1:
            for i in range(len(self.current_stroke) - 1):
                painter.drawLine(self.current_stroke[i], self.current_stroke[i+1])
