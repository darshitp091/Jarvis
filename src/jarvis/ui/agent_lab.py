import sys
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextBrowser, QApplication, QFrame
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QTimer
from PyQt6.QtGui import QColor, QFont

class AgentLabWidget(QWidget):
    # Signals for thread-safe UI updates from background orchestrator
    add_message_signal = pyqtSignal(str, str)  # (agent_name, text)
    set_status_signal = pyqtSignal(str, str)    # (agent_name, status)
    clear_signal = pyqtSignal()
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
        self.setFixedSize(650, 480)
        self.drag_pos = None

        # Custom glassmorphic styling
        self.setStyleSheet("""
            QWidget {
                background-color: rgba(10, 25, 47, 210);
                border: 2px solid rgba(0, 210, 255, 140);
                border-radius: 14px;
                color: #e6f1ff;
                font-family: 'Consolas', 'Segoe UI', monospace;
            }
            QTextBrowser {
                background-color: rgba(2, 12, 27, 200);
                border: 1px solid rgba(0, 210, 255, 60);
                border-radius: 8px;
                padding: 10px;
                color: #8892b0;
                font-size: 13px;
            }
            QLabel {
                border: none;
                background: transparent;
            }
        """)

        self.setup_ui()
        self.center_window()

        # Connect signals to slots
        self.add_message_signal.connect(self._add_message_internal)
        self.set_status_signal.connect(self._set_status_internal)
        self.clear_signal.connect(self._clear_internal)
        self.show_signal.connect(super().show)
        self.hide_signal.connect(super().hide)

    def center_window(self):
        try:
            screen = QApplication.primaryScreen().geometry()
            self.move((screen.width() - self.width()) // 2, (screen.height() - self.height()) // 2)
        except Exception:
            self.move(200, 200)

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)

        # Title Bar
        title_layout = QHBoxLayout()
        self.title_label = QLabel("JARVIS // COGNITIVE AGENT LAB")
        self.title_label.setFont(QFont("Consolas", 12, QFont.Weight.Bold))
        self.title_label.setStyleSheet("color: #64ffda; letter-spacing: 2px;")
        
        self.status_general = QLabel("OFFLINE")
        self.status_general.setStyleSheet("color: rgba(100, 255, 218, 120); font-size: 11px;")
        
        title_layout.addWidget(self.title_label)
        title_layout.addStretch()
        title_layout.addWidget(self.status_general)
        main_layout.addLayout(title_layout)

        # Horizontal separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background-color: rgba(0, 210, 255, 40); max-height: 1px;")
        main_layout.addWidget(sep)

        # Middle Content Layout: Left sidebar (agent status), Right panel (chat history)
        content_layout = QHBoxLayout()

        # Left Agent Status Sidebar
        sidebar = QFrame()
        sidebar.setStyleSheet("""
            QFrame {
                background-color: rgba(2, 12, 27, 100);
                border: 1px solid rgba(0, 210, 255, 40);
                border-radius: 8px;
                min-width: 170px;
                max-width: 170px;
            }
            QLabel {
                font-size: 11px;
            }
        """)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(10, 10, 10, 10)

        sidebar_title = QLabel("SWARM STATUS")
        sidebar_title.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        sidebar_title.setStyleSheet("color: #00d2ff; padding-bottom: 5px;")
        sidebar_layout.addWidget(sidebar_title)

        # Agent status items
        self.agent_labels = {}
        self.agent_dots = {}
        
        agents = [
            ("Architect", "UX ARCHITECT"),
            ("Auditor", "SECURITY AUDITOR"),
            ("QA", "QA ENGINEER")
        ]

        for code_name, display_name in agents:
            agent_frame = QFrame()
            agent_frame.setStyleSheet("border: none; background: transparent; margin-bottom: 8px;")
            agent_lay = QVBoxLayout(agent_frame)
            agent_lay.setContentsMargins(0, 0, 0, 0)

            header_lay = QHBoxLayout()
            dot = QLabel("●")
            dot.setStyleSheet("color: #8892b0; font-size: 12px;")  # Grey when idle
            name_lbl = QLabel(display_name)
            name_lbl.setStyleSheet("color: #e6f1ff; font-weight: bold;")
            
            header_lay.addWidget(dot)
            header_lay.addWidget(name_lbl)
            header_lay.addStretch()

            status_lbl = QLabel("IDLE")
            status_lbl.setStyleSheet("color: #8892b0; padding-left: 14px;")

            agent_lay.addLayout(header_lay)
            agent_lay.addWidget(status_lbl)
            
            sidebar_layout.addWidget(agent_frame)
            
            self.agent_dots[code_name] = dot
            self.agent_labels[code_name] = status_lbl

        sidebar_layout.addStretch()
        content_layout.addWidget(sidebar)

        # Right Chat Area
        self.chat_browser = QTextBrowser()
        self.chat_browser.setHtml("<p style='color: #8892b0;'>Laboratory standby mode. Send tasks to initialize collaborate loop.</p>")
        content_layout.addWidget(self.chat_browser)

        main_layout.addLayout(content_layout)

    def _add_message_internal(self, agent_name: str, text: str):
        color_map = {
            "Architect": "#64ffda",
            "Auditor": "#ff5252",
            "QA": "#ffeb3b",
            "System": "#00d2ff"
        }
        color = color_map.get(agent_name, "#e6f1ff")
        display_name = agent_name.upper()
        
        current_html = self.chat_browser.toHtml()
        
        # Clean default text if starting
        if "standby mode" in current_html:
            self.chat_browser.clear()
            
        bubble_html = f"""
        <div style='margin-bottom: 12px;'>
            <span style='color: {color}; font-weight: bold;'>[{display_name}]:</span>
            <span style='color: #e6f1ff; font-family: monospace;'> {text}</span>
        </div>
        """
        self.chat_browser.append(bubble_html)
        # Scroll to bottom
        self.chat_browser.verticalScrollBar().setValue(self.chat_browser.verticalScrollBar().maximum())

    def _set_status_internal(self, agent_name: str, status: str):
        if agent_name in self.agent_labels:
            self.agent_labels[agent_name].setText(status.upper())
            dot = self.agent_dots[agent_name]
            
            if status.lower() == "thinking":
                dot.setStyleSheet("color: #64ffda; font-size: 12px;")  # Green
                self.agent_labels[agent_name].setStyleSheet("color: #64ffda; padding-left: 14px;")
            elif status.lower() == "active":
                dot.setStyleSheet("color: #00d2ff; font-size: 12px;")  # Cyan
                self.agent_labels[agent_name].setStyleSheet("color: #00d2ff; padding-left: 14px;")
            else:
                dot.setStyleSheet("color: #8892b0; font-size: 12px;")  # Grey
                self.agent_labels[agent_name].setStyleSheet("color: #8892b0; padding-left: 14px;")

        # Update general lab status
        any_thinking = any(lbl.text() == "THINKING" for lbl in self.agent_labels.values())
        if any_thinking:
            self.status_general.setText("PROCESSING")
            self.status_general.setStyleSheet("color: #64ffda; font-size: 11px;")
        else:
            self.status_general.setText("STANDBY")
            self.status_general.setStyleSheet("color: rgba(100, 255, 218, 120); font-size: 11px;")

    def _clear_internal(self):
        self.chat_browser.clear()
        for k in self.agent_labels:
            self._set_status_internal(k, "idle")

    # Public helper methods (emit signals for thread safety)
    def add_message(self, agent: str, msg: str):
        self.add_message_signal.emit(agent, msg)

    def set_agent_status(self, agent: str, status: str):
        self.set_status_signal.emit(agent, status)

    def clear_chat(self):
        self.clear_signal.emit()

    def show(self):
        self.show_signal.emit()

    def hide(self):
        self.hide_signal.emit()

    # Draggable Window Methods
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
    w = AgentLabWidget()
    w.show()
    w.add_message("System", "Lab diagnostics starting...")
    w.set_agent_status("Architect", "thinking")
    
    QTimer.singleShot(2000, lambda: w.add_message("Architect", "Designing UI coordinates mapping..."))
    QTimer.singleShot(2500, lambda: w.set_agent_status("Architect", "idle"))
    QTimer.singleShot(3000, lambda: w.set_agent_status("Auditor", "thinking"))
    QTimer.singleShot(4000, lambda: w.add_message("Auditor", "Analyzing security filters..."))
    
    sys.exit(app.exec())
