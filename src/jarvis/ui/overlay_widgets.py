import os
import time
from PyQt6.QtWidgets import QWidget, QApplication, QLabel, QRubberBand
from PyQt6.QtCore import Qt, QPoint, QSize, QRect, pyqtSignal, QTimer
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


class IronManHUDOverlay(QWidget):
    """Futuristic Stark-style JARVIS HUD overlay displaying telemetry, gaze reticle, and waveforms."""
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
        
        # Gaze coordinates
        self.target_gaze = QPoint(rect.width() // 2, rect.height() // 2)
        self.current_gaze = QPoint(rect.width() // 2, rect.height() // 2)
        
        # HUD State: "idle", "listening", "thinking", "speaking"
        self.hud_state = "idle"
        
        # Animation variables
        self.anim_phase = 0.0
        self.radar_angle = 0
        
        # Telemetry cache
        self.cpu_pct = 0
        self.ram_pct = 0
        self.battery_pct = 100
        self.battery_plugged = False
        
        # History buffers for telemetry graphs
        self.cpu_history = [0] * 30
        self.ram_history = [0] * 30
        
        # QTimer for animations and telemetry updates
        from PyQt6.QtCore import QTimer
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._on_tick)
        self.timer.start(33) # ~30 FPS
        
        # Less frequent timer for telemetry updates
        self.telemetry_timer = QTimer(self)
        self.telemetry_timer.timeout.connect(self._update_telemetry)
        self.telemetry_timer.start(1000) # Every 1s
        self._update_telemetry()
        
    def set_hud_state(self, state: str):
        self.hud_state = state
        self.update()
        
    def update_gaze(self, x: int, y: int):
        self.target_gaze = QPoint(x, y)
        
    def _on_tick(self):
        # Smoothly interpolate gaze position (lerp)
        dx = self.target_gaze.x() - self.current_gaze.x()
        dy = self.target_gaze.y() - self.current_gaze.y()
        self.current_gaze.setX(int(self.current_gaze.x() + dx * 0.2))
        self.current_gaze.setY(int(self.current_gaze.y() + dy * 0.2))
        
        # Advance animation phases
        self.anim_phase += 0.08
        if self.anim_phase > 6.28:
            self.anim_phase = 0.0
            
        self.radar_angle = (self.radar_angle + 2) % 360
        self.update()
        
    def _update_telemetry(self):
        try:
            import psutil
            self.cpu_pct = int(psutil.cpu_percent())
            self.ram_pct = int(psutil.virtual_memory().percent)
            battery = psutil.sensors_battery()
            if battery:
                self.battery_pct = int(battery.percent)
                self.battery_plugged = battery.power_plugged
        except Exception:
            pass
        
        # Add to history
        self.cpu_history.pop(0)
        self.cpu_history.append(self.cpu_pct)
        self.ram_history.pop(0)
        self.ram_history.append(self.ram_pct)
            
    def paintEvent(self, event):
        import numpy as np
        from PyQt6.QtGui import QPainterPath, QPolygonF, QRadialGradient, QFont
        from PyQt6.QtCore import QPointF, QRectF
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        w = self.width()
        h = self.height()
        
        # Define high-tech holographic colors based on state
        glow_alpha = int(45 + 15 * np.sin(self.anim_phase * 2)) # Pulsing transparency
        if self.hud_state == "listening":
            base_color = QColor(0, 255, 170) # Neon green
            state_label = "LISTENING PROTOCOL"
        elif self.hud_state == "thinking":
            base_color = QColor(255, 170, 0) # Neon orange/yellow
            state_label = "COGNITIVE PROCESS"
        elif self.hud_state == "speaking":
            base_color = QColor(255, 60, 60) # Neon red/crimson
            state_label = "VOCAL TRANSMISSION"
        else:
            base_color = QColor(0, 180, 255) # Classic neon blue
            state_label = "STANDBY MODE"
            
        primary_color = QColor(base_color.red(), base_color.green(), base_color.blue(), 210)
        secondary_color = QColor(base_color.red(), base_color.green(), base_color.blue(), 100)
        dim_color = QColor(base_color.red(), base_color.green(), base_color.blue(), 45)
        glow_color = QColor(base_color.red(), base_color.green(), base_color.blue(), glow_alpha)
        
        # 1. Paint Outer Holographic Frame / Border
        painter.setPen(QPen(dim_color, 1))
        # Draw dotted grid background on borders (15px margin)
        margin = 15
        painter.drawRect(margin, margin, w - 2 * margin, h - 2 * margin)
        
        # 2. Tech Corner Brackets
        painter.setPen(QPen(primary_color, 3))
        bl = 45 # Bracket length
        # Top-Left
        painter.drawLine(margin, margin, margin + bl, margin)
        painter.drawLine(margin, margin, margin, margin + bl)
        painter.drawPoint(margin + bl + 8, margin + 4)
        # Top-Right
        painter.drawLine(w - margin, margin, w - margin - bl, margin)
        painter.drawLine(w - margin, margin, w - margin, margin + bl)
        painter.drawPoint(w - margin - bl - 8, margin + 4)
        # Bottom-Left
        painter.drawLine(margin, h - margin, margin + bl, h - margin)
        painter.drawLine(margin, h - margin, margin, h - margin - bl)
        painter.drawPoint(margin + bl + 8, h - margin - 4)
        # Bottom-Right
        painter.drawLine(w - margin, h - margin, w - margin - bl, h - margin)
        painter.drawLine(w - margin, h - margin, w - margin, h - margin - bl)
        painter.drawPoint(w - margin - bl - 8, h - margin - 4)
        
        # 3. Top Header Bar
        hdr_w = 400
        hdr_h = 32
        hdr_x = (w - hdr_w) // 2
        hdr_y = margin
        
        # Draw tech panel at top center
        painter.setPen(QPen(primary_color, 1))
        painter.setBrush(QColor(base_color.red(), base_color.green(), base_color.blue(), 15))
        painter.drawRect(hdr_x, hdr_y, hdr_w, hdr_h)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        
        # Header text
        font = QFont("Consolas", 10, QFont.Weight.Bold)
        painter.setFont(font)
        painter.setPen(primary_color)
        painter.drawText(QRect(hdr_x, hdr_y, hdr_w, hdr_h), Qt.AlignmentFlag.AlignCenter, "JARVIS CORE AI // MARK-XII")
        
        # State display below header
        font_small = QFont("Consolas", 8, QFont.Weight.Bold)
        painter.setFont(font_small)
        painter.setPen(glow_color)
        painter.drawText(QRect(hdr_x, hdr_y + hdr_h, hdr_w, 20), Qt.AlignmentFlag.AlignCenter, f">> {state_label} <<")
        
        # Digital HUD Clock at Top-Right
        painter.setPen(primary_color)
        clock_str = time.strftime("%H:%M:%S // %d-%m-%Y")
        painter.drawText(w - margin - 220, margin + 15, f"TIME: {clock_str}")
        
        # 4. Floating Left Panel: Core Hardware Graphs
        panel_w = 260
        panel_h = 240
        left_x = margin + 20
        panel_y = margin + 60
        
        # Draw background glass box
        painter.setPen(QPen(secondary_color, 1))
        painter.setBrush(QColor(0, 10, 20, 160))
        painter.drawRect(left_x, panel_y, panel_w, panel_h)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        
        # Draw panel header
        painter.setPen(primary_color)
        painter.drawText(left_x + 10, panel_y + 20, "SYSTEM CORE DIAGNOSTICS")
        painter.setPen(dim_color)
        painter.drawLine(left_x + 10, panel_y + 25, left_x + panel_w - 10, panel_y + 25)
        
        # Render CPU & RAM stats
        painter.setPen(primary_color)
        painter.drawText(left_x + 15, panel_y + 45, f"CPU UTILIZATION: {self.cpu_pct}%")
        painter.drawText(left_x + 15, panel_y + 135, f"RAM ALLOCATION: {self.ram_pct}%")
        
        # Simple progress bars
        bar_w = panel_w - 30
        bar_h = 6
        # CPU Bar
        painter.setPen(QPen(dim_color, 1))
        painter.drawRect(left_x + 15, panel_y + 55, bar_w, bar_h)
        painter.fillRect(left_x + 16, panel_y + 56, int((bar_w - 2) * (self.cpu_pct / 100.0)), bar_h - 2, primary_color)
        # RAM Bar
        painter.drawRect(left_x + 15, panel_y + 145, bar_w, bar_h)
        painter.fillRect(left_x + 16, panel_y + 146, int((bar_w - 2) * (self.ram_pct / 100.0)), bar_h - 2, primary_color)
        
        # Draw historical graphs (mini sparklines)
        graph_w = bar_w
        graph_h = 45
        
        # CPU history graph
        cpu_graph_y = panel_y + 70
        painter.setPen(QPen(dim_color, 1))
        painter.drawRect(left_x + 15, cpu_graph_y, graph_w, graph_h)
        # Plot lines
        painter.setPen(QPen(secondary_color, 1))
        pts_cpu = []
        for idx, val in enumerate(self.cpu_history):
            pt_x = left_x + 15 + idx * (graph_w / 29.0)
            pt_y = cpu_graph_y + graph_h - (val / 100.0 * graph_h)
            pts_cpu.append(QPointF(pt_x, pt_y))
        for i in range(len(pts_cpu) - 1):
            painter.drawLine(pts_cpu[i], pts_cpu[i+1])
            
        # RAM history graph
        ram_graph_y = panel_y + 160
        painter.setPen(QPen(dim_color, 1))
        painter.drawRect(left_x + 15, ram_graph_y, graph_w, graph_h)
        # Plot lines
        painter.setPen(QPen(secondary_color, 1))
        pts_ram = []
        for idx, val in enumerate(self.ram_history):
            pt_x = left_x + 15 + idx * (graph_w / 29.0)
            pt_y = ram_graph_y + graph_h - (val / 100.0 * graph_h)
            pts_ram.append(QPointF(pt_x, pt_y))
        for i in range(len(pts_ram) - 1):
            painter.drawLine(pts_ram[i], pts_ram[i+1])
            
        # 5. Floating Right Panel: Diagnostics/Power
        right_x = w - margin - panel_w - 20
        painter.setPen(QPen(secondary_color, 1))
        painter.setBrush(QColor(0, 10, 20, 160))
        painter.drawRect(right_x, panel_y, panel_w, panel_h)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        
        painter.setPen(primary_color)
        painter.drawText(right_x + 10, panel_y + 20, "ENVIRONMENT TELEMETRY")
        painter.setPen(dim_color)
        painter.drawLine(right_x + 10, panel_y + 25, right_x + panel_w - 10, panel_y + 25)
        
        # Telemetry listings
        painter.setPen(primary_color)
        painter.drawText(right_x + 15, panel_y + 50, f"BATTERY CORE: {self.battery_pct}%")
        state_batt = "CHARGING" if self.battery_plugged else "DISCHARGING"
        painter.drawText(right_x + 15, panel_y + 70, f"BATTERY STATUS: {state_batt}")
        painter.drawText(right_x + 15, panel_y + 90, "CONNECTION LOCK: SECURE")
        painter.drawText(right_x + 15, panel_y + 110, "PING STABILITY: NOMINAL")
        painter.drawText(right_x + 15, panel_y + 130, "AI COGNITIVE CAP: 98.4%")
        painter.drawText(right_x + 15, panel_y + 150, "THREAT METRIC: 0.00%")
        painter.drawText(right_x + 15, panel_y + 170, "AUDIO FEED: READY")
        painter.drawText(right_x + 15, panel_y + 190, "TARGET ENROLLMENT: OK")
        
        # 6. Bottom-Left Arc Reactor Visualization
        arc_cx = margin + 110
        arc_cy = h - margin - 120
        painter.setPen(QPen(dim_color, 1))
        painter.drawEllipse(QPoint(arc_cx, arc_cy), 80, 80)
        painter.drawEllipse(QPoint(arc_cx, arc_cy), 55, 55)
        
        # Rotating outer arc rings
        painter.setPen(QPen(primary_color, 2))
        painter.drawArc(QRect(arc_cx - 70, arc_cy - 70, 140, 140), int(self.radar_angle * 16), int(120 * 16))
        painter.drawArc(QRect(arc_cx - 70, arc_cy - 70, 140, 140), int((self.radar_angle + 180) * 16), int(90 * 16))
        
        # Reverse rotating inner arc ring
        painter.setPen(QPen(secondary_color, 1))
        painter.drawArc(QRect(arc_cx - 45, arc_cy - 45, 90, 90), int((-self.radar_angle * 1.5) * 16), int(180 * 16))
        
        # Tech cross lines in reactor
        painter.setPen(QPen(dim_color, 1))
        painter.drawLine(arc_cx - 85, arc_cy, arc_cx + 85, arc_cy)
        painter.drawLine(arc_cx, arc_cy - 85, arc_cx, arc_cy + 85)
        
        # Center glowing core
        core_grad = QRadialGradient(arc_cx, arc_cy, 20)
        core_grad.setColorAt(0, QColor(base_color.red(), base_color.green(), base_color.blue(), 230))
        core_grad.setColorAt(1, QColor(base_color.red(), base_color.green(), base_color.blue(), 0))
        painter.setBrush(core_grad)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPoint(arc_cx, arc_cy), 20, 20)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        
        # Text label below reactor
        painter.setFont(font_small)
        painter.setPen(primary_color)
        painter.drawText(arc_cx - 60, arc_cy + 105, "ARC CORE STATUS: OK")
        
        # 7. Immersive Interactive Reticle (Follows gaze/mouse cursor)
        # Update gaze coordinates with current mouse cursor position
        mx, my = pyautogui.position()
        self.update_gaze(mx, my)
        
        gx, gy = self.current_gaze.x(), self.current_gaze.y()
        
        # Draw circular reticle
        painter.setPen(QPen(primary_color, 1))
        painter.drawEllipse(QPoint(gx, gy), 20, 20)
        
        # Rotating outer hexagon
        poly = QPolygonF()
        for i in range(6):
            angle = np.radians(self.radar_angle + i * 60)
            px = gx + 32 * np.cos(angle)
            py = gy + 32 * np.sin(angle)
            poly.append(QPointF(px, py))
        painter.setPen(QPen(secondary_color, 1))
        painter.drawPolygon(poly)
        
        # Small inner targeting crosshairs
        painter.setPen(QPen(primary_color, 1))
        painter.drawLine(gx - 28, gy, gx - 12, gy)
        painter.drawLine(gx + 12, gy, gx + 28, gy)
        painter.drawLine(gx, gy - 28, gx, gy - 12)
        painter.drawLine(gx, gy + 12, gx, gy + 28)
        
        # Center lock dot
        painter.setBrush(primary_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPoint(gx, gy), 2, 2)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        
        # Render target coordinates next to reticle
        painter.setFont(font_small)
        painter.setPen(primary_color)
        painter.drawText(gx + 40, gy - 5, f"LOCK_TGT // X:{gx} Y:{my}")
        
        # 8. State-based Animations at the Bottom-Center
        cx = w // 2
        cy = h - margin - 80
        
        if self.hud_state == "listening":
            # Pulsing rings & holographic voice waveform
            pulse_r = int(22 + 18 * abs(np.sin(self.anim_phase * 1.5)))
            painter.setPen(QPen(primary_color, 2))
            painter.drawEllipse(QPoint(cx, cy), pulse_r, pulse_r)
            painter.setPen(QPen(secondary_color, 1))
            painter.drawEllipse(QPoint(cx, cy), 15, 15)
            
            # Flowing sine wave across the bottom
            painter.setPen(QPen(primary_color, 1.5))
            path = QPainterPath()
            path.moveTo(cx - 150, cy)
            for x in range(cx - 150, cx + 150, 4):
                rel_x = x - cx
                # Modulation using sine & cosine multiplication for clean tech waves
                dy_wave = int(20 * np.sin(self.anim_phase * 2.5 + rel_x * 0.08) * np.cos(rel_x * 0.015))
                path.lineTo(x, cy + dy_wave)
            painter.drawPath(path)
            
        elif self.hud_state == "thinking":
            # Rotating concentric orbits
            painter.setPen(QPen(primary_color, 1.5))
            painter.drawEllipse(QPoint(cx, cy), 35, 35)
            painter.setPen(QPen(secondary_color, 1))
            painter.drawEllipse(QPoint(cx, cy), 20, 20)
            
            # Draw rotating orbital nodes
            rad1 = np.radians(self.radar_angle * 1.5)
            rad2 = np.radians(-self.radar_angle * 2.0)
            
            nx1 = int(cx + 35 * np.cos(rad1))
            ny1 = int(cy + 35 * np.sin(rad1))
            nx2 = int(cx + 20 * np.cos(rad2))
            ny2 = int(cy + 20 * np.sin(rad2))
            
            painter.setBrush(primary_color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPoint(nx1, ny1), 4, 4)
            painter.setBrush(secondary_color)
            painter.drawEllipse(QPoint(nx2, ny2), 3, 3)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            
        elif self.hud_state == "speaking":
            # Animated dynamic audio equalizer bars
            painter.setPen(QPen(primary_color, 2))
            num_bars = 15
            spacing = 10
            for idx in range(num_bars):
                offset = idx - num_bars // 2
                bar_x = cx + offset * spacing
                # Randomize height wave based on phase
                h_val = int(8 + 32 * abs(np.sin(self.anim_phase * 2.0 + offset * 0.3)))
                painter.drawLine(bar_x, cy - h_val//2, bar_x, cy + h_val//2)
                
        else: # Idle standby
            # Low frequency ambient breathing circles
            breath_r = int(18 + 5 * np.sin(self.anim_phase))
            painter.setPen(QPen(primary_color, 1.5))
            painter.drawEllipse(QPoint(cx, cy), breath_r, breath_r)
            painter.setPen(QPen(secondary_color, 1))
            painter.drawEllipse(QPoint(cx, cy), 10, 10)
            
            # Ambient grid lines
            painter.setPen(QPen(dim_color, 0.5, Qt.PenStyle.DashLine))
            painter.drawLine(cx - 80, cy, cx + 80, cy)


class TargetReticleOverlay(QWidget):
    """Transparent overlay that draws a neon-green rotating targeting reticle around a coordinate."""
    def __init__(self, x: int, y: int, label_text: str = "TARGET LOCK"):
        super().__init__()
        self.target_x = x
        self.target_y = y
        self.label_text = label_text
        self.angle = 0
        
        # Borderless, stays on top, tool window, transparent input (doesn't block user clicks)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.Tool |
            Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        
        # Cover virtual screen
        rect = QGuiApplication.primaryScreen().virtualGeometry()
        self.setGeometry(rect)
        
        # Timer for rotative animation (30 FPS)
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self.update_animation)
        self.anim_timer.start(33)
        
        # Timer to self-close after 3 seconds
        self.close_timer = QTimer(self)
        self.close_timer.timeout.connect(self.close)
        self.close_timer.setSingleShot(True)
        self.close_timer.start(3000)
        
    def update_animation(self):
        self.angle = (self.angle + 4) % 360
        self.update()
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        
        # Neon green color
        neon_color = QColor(0, 255, 120, 220)
        pen = QPen(neon_color, 2)
        painter.setPen(pen)
        
        # Target center
        tx, ty = self.target_x, self.target_y
        
        # Draw target circular reticle
        radius = 40
        painter.drawEllipse(QPoint(tx, ty), radius, radius)
        
        # Draw outer rotating dashes
        painter.save()
        painter.translate(tx, ty)
        painter.rotate(self.angle)
        for i in range(4):
            painter.rotate(90)
            painter.drawLine(radius + 5, 0, radius + 15, 0)
        painter.restore()
        
        # Draw crosshairs
        painter.drawLine(tx - 10, ty, tx + 10, ty)
        painter.drawLine(tx, ty - 10, tx, ty + 10)
        
        # Draw surrounding square brackets
        offset = 60
        size = 15
        # Top-Left
        painter.drawLine(tx - offset, ty - offset, tx - offset + size, ty - offset)
        painter.drawLine(tx - offset, ty - offset, tx - offset, ty - offset + size)
        # Top-Right
        painter.drawLine(tx + offset, ty - offset, tx + offset - size, ty - offset)
        painter.drawLine(tx + offset, ty - offset, tx + offset, ty - offset + size)
        # Bottom-Left
        painter.drawLine(tx - offset, ty + offset, tx - offset + size, ty + offset)
        painter.drawLine(tx - offset, ty + offset, tx - offset, ty + offset - size)
        # Bottom-Right
        painter.drawLine(tx + offset, ty + offset, tx + offset - size, ty + offset)
        painter.drawLine(tx + offset, ty + offset, tx + offset, ty + offset - size)
        
        # Draw text label under the target
        painter.setFont(QGuiApplication.font())
        painter.setPen(QPen(QColor(0, 255, 120, 255)))
        painter.drawText(tx - 80, ty + offset + 20, 160, 20, Qt.AlignmentFlag.AlignCenter, self.label_text)

