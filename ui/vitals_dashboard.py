import sys
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QApplication, QFrame
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor

class VitalsDashboardWidget(QWidget):
    # Signals for thread-safe UI updates
    update_metrics_signal = pyqtSignal(int, int, int, str) # (focus_score, typing_cpm, blink_rate, posture_str)
    show_signal = pyqtSignal()
    hide_signal = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(260, 360)
        self.drag_pos = None

        self.setup_ui()
        self.position_widget()

        self.update_metrics_signal.connect(self._update_metrics_internal)
        self.show_signal.connect(super().show)
        self.hide_signal.connect(super().hide)

    def position_widget(self):
        try:
            screen = QApplication.primaryScreen().geometry()
            # Position at bottom-right corner of the screen
            self.move(screen.width() - self.width() - 40, screen.height() - self.height() - 80)
        except Exception:
            self.move(1000, 500)

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)

        # Style System: Glassmorphic panel with cyan glow border
        self.panel = QFrame()
        self.panel.setObjectName("MainPanel")
        self.set_panel_style("nominal")
        
        panel_layout = QVBoxLayout(self.panel)
        panel_layout.setContentsMargins(12, 12, 12, 12)

        # Header Title
        title_lay = QHBoxLayout()
        title_lbl = QLabel("JARVIS // BIOMETRICS")
        title_lbl.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
        title_lbl.setStyleSheet("color: #64ffda; border: none; background: transparent;")
        
        self.indicator_dot = QLabel("●")
        self.indicator_dot.setStyleSheet("color: #64ffda; font-size: 14px; border: none; background: transparent;")
        
        title_lay.addWidget(title_lbl)
        title_lay.addStretch()
        title_lay.addWidget(self.indicator_dot)
        panel_layout.addLayout(title_lay)

        # Horizontal separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background-color: rgba(0, 210, 255, 45); max-height: 1px; border: none;")
        panel_layout.addWidget(sep)
        panel_layout.addSpacing(5)

        # Focus Score Meter
        focus_title = QLabel("COGNITIVE FOCUS RATE")
        focus_title.setFont(QFont("Segoe UI", 9))
        focus_title.setStyleSheet("color: #8892b0; border: none; background: transparent;")
        panel_layout.addWidget(focus_title)

        self.focus_bar = QProgressBar()
        self.focus_bar.setRange(0, 100)
        self.focus_bar.setValue(100)
        self.focus_bar.setTextVisible(True)
        self.focus_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.focus_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid rgba(0, 210, 255, 70);
                border-radius: 6px;
                background-color: rgba(2, 12, 27, 180);
                color: #e6f1ff;
                font-family: 'Consolas', monospace;
                font-weight: bold;
                height: 22px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                                  stop:0 #00d2ff, stop:1 #64ffda);
                border-radius: 5px;
            }
        """)
        panel_layout.addWidget(self.focus_bar)
        panel_layout.addSpacing(15)

        # Biometric Metrics
        self.cpm_lbl = self.create_metric_row(panel_layout, "TYPING CADENCE:", "120 CPM")
        self.blink_lbl = self.create_metric_row(panel_layout, "BLINK METRIC:", "14 BPM")
        self.posture_lbl = self.create_metric_row(panel_layout, "POSTURE NOMINAL:", "YES")

        panel_layout.addStretch()

        # Warning / Alert footer
        self.footer_status = QLabel("MONITOR NOMINAL // VITAL SENSORS")
        self.footer_status.setFont(QFont("Consolas", 8))
        self.footer_status.setStyleSheet("color: rgba(100, 255, 218, 140); border: none; background: transparent;")
        self.footer_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        panel_layout.addWidget(self.footer_status)

        layout.addWidget(self.panel)

    def create_metric_row(self, layout, label_text, val_text) -> QLabel:
        row = QHBoxLayout()
        lbl = QLabel(label_text)
        lbl.setFont(QFont("Consolas", 9))
        lbl.setStyleSheet("color: #8892b0; border: none; background: transparent;")
        
        val = QLabel(val_text)
        val.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        val.setStyleSheet("color: #e6f1ff; border: none; background: transparent;")
        
        row.addWidget(lbl)
        row.addStretch()
        row.addWidget(val)
        layout.addLayout(row)
        layout.addSpacing(8)
        return val

    def set_panel_style(self, state: str):
        """Sets the panel border glow stylesheet color based on focus state."""
        if state == "warning":
            border_color = "rgba(255, 120, 0, 160)"
            bg_color = "rgba(18, 10, 0, 215)"
        elif state == "alert":
            border_color = "rgba(255, 80, 80, 200)"
            bg_color = "rgba(20, 0, 0, 220)"
        else: # nominal
            border_color = "rgba(0, 210, 255, 140)"
            bg_color = "rgba(10, 25, 47, 210)"

        self.panel.setStyleSheet(f"""
            QFrame#MainPanel {{
                background-color: {bg_color};
                border: 2px solid {border_color};
                border-radius: 12px;
            }}
        """)

    def _update_metrics_internal(self, focus_score: int, typing_cpm: int, blink_rate: int, posture_str: str):
        # Update focus bar
        self.focus_bar.setValue(focus_score)
        
        # Update labels
        self.cpm_lbl.setText(f"{typing_cpm} CPM")
        self.blink_lbl.setText(f"{blink_rate} BPM")
        
        posture_upper = posture_str.upper()
        self.posture_lbl.setText(posture_upper)

        # Style updates based on fatigue
        if focus_score < 40:
            self.set_panel_style("alert")
            self.indicator_dot.setStyleSheet("color: #ff5252; font-size: 14px; border: none; background: transparent;")
            self.footer_status.setText("CRITICAL FOCUS WARNING")
            self.footer_status.setStyleSheet("color: #ff5252; border: none; background: transparent;")
            self.posture_lbl.setStyleSheet("color: #ff5252; font-weight: bold; border: none; background: transparent;")
        elif focus_score < 65:
            self.set_panel_style("warning")
            self.indicator_dot.setStyleSheet("color: #ff9800; font-size: 14px; border: none; background: transparent;")
            self.footer_status.setText("FATIGUE WARNING DETECTED")
            self.footer_status.setStyleSheet("color: #ff9800; border: none; background: transparent;")
            self.posture_lbl.setStyleSheet("color: #ff9800; font-weight: bold; border: none; background: transparent;")
        else:
            self.set_panel_style("nominal")
            self.indicator_dot.setStyleSheet("color: #64ffda; font-size: 14px; border: none; background: transparent;")
            self.footer_status.setText("MONITOR NOMINAL // VITAL SENSORS")
            self.footer_status.setStyleSheet("color: rgba(100, 255, 218, 140); border: none; background: transparent;")
            self.posture_lbl.setStyleSheet("color: #64ffda; font-weight: bold; border: none; background: transparent;")

    # Public helper slots
    def update_metrics(self, focus_score: int, typing_cpm: int, blink_rate: int, posture_str: str):
        self.update_metrics_signal.emit(focus_score, typing_cpm, blink_rate, posture_str)

    def show(self):
        self.show_signal.emit()

    def hide(self):
        self.hide_signal.emit()

    # Draggable behavior
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
    w = VitalsDashboardWidget()
    w.show()
    w.update_metrics(45, 180, 16, "Nominal")
    sys.exit(app.exec())
