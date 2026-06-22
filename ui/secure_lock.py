import sys
import os
from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QColor

# Add root folder to sys.path to resolve imports cleanly
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from auth.local_auth import LocalAuth

class JarvisSecureLock(QWidget):
    """A full-screen, impenetrable overlay representing JARVIS Sentry Mode."""

    def __init__(self):
        super().__init__()
        
        # Make it full screen, frameless, and always on top
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Tool |
            Qt.WindowType.X11BypassWindowManagerHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background-color: black;")
        self.setWindowTitle("JARVIS_SECURE_LOCK")
        
        self.auth = LocalAuth()
        self.pin_buffer = ""
        self.state_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "auth", ".auth_state"))
        
        # Clean any stale auth states
        if os.path.exists(self.state_file):
            try:
                os.remove(self.state_file)
            except Exception:
                pass

        self.showFullScreen()

        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.label = QLabel("JARVIS SENTRY MODE ACTIVE")
        self.label.setStyleSheet("color: red; font-weight: bold;")
        self.label.setFont(QFont("Consolas", 48))
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.sub_label = QLabel("SYSTEM SECURED. AWAITING VOICE OR KEYBOARD PIN.")
        self.sub_label.setStyleSheet("color: darkred;")
        self.sub_label.setFont(QFont("Consolas", 24))
        self.sub_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.pin_label = QLabel("ENTER PIN: ")
        self.pin_label.setStyleSheet("color: white; font-family: Consolas; font-weight: bold;")
        self.pin_label.setFont(QFont("Consolas", 28))
        self.pin_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(self.label)
        layout.addWidget(self.sub_label)
        layout.addWidget(self.pin_label)
        
        self.setLayout(layout)
        
        self.blink = True
        self.timer = QTimer()
        self.timer.timeout.connect(self._toggle_blink)
        self.timer.start(1000)

    def _toggle_blink(self):
        self.blink = not self.blink
        if self.blink:
            self.label.setStyleSheet("color: red; font-weight: bold;")
        else:
            self.label.setStyleSheet("color: darkred; font-weight: bold;")

    def keyPressEvent(self, event):
        key = event.key()
        
        # Handle digits
        if Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
            digit = chr(key)
            self.pin_buffer += digit
            self.pin_label.setText("ENTER PIN: " + "*" * len(self.pin_buffer))
            
            # Check length
            if len(self.pin_buffer) == 6:
                success, msg = self.auth.verify_pin(self.pin_buffer)
                if success:
                    # Write to state file for main.py to read
                    try:
                        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
                        with open(self.state_file, "w") as f:
                            f.write("unlocked")
                    except Exception as e:
                        print(f"Error writing auth state: {e}")
                    
                    self.close()
                else:
                    self.pin_label.setText("ENTER PIN: INVALID")
                    self.pin_buffer = ""
                    # Reset label after 1.5 seconds
                    QTimer.singleShot(1500, lambda: self.pin_label.setText("ENTER PIN: "))
                    
        # Handle Backspace
        elif key == Qt.Key.Key_Backspace:
            if len(self.pin_buffer) > 0:
                self.pin_buffer = self.pin_buffer[:-1]
                self.pin_label.setText("ENTER PIN: " + "*" * len(self.pin_buffer))

    def closeEvent(self, event):
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    lock = JarvisSecureLock()
    sys.exit(app.exec())
