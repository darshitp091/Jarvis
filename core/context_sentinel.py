import ctypes
import time
import threading
from loguru import logger
import psutil

class ContextSentinel:
    """Monitors the active foreground window title and process name in a background thread."""

    def __init__(self, poll_interval: float = 2.0):
        self.poll_interval = poll_interval
        self.active_context = {
            "process": "unknown",
            "title": "unknown",
            "timestamp": time.time()
        }
        self.running = False
        self.thread = None
        self._lock = threading.Lock()
        
        self.start()

    def start(self):
        """Starts the background tracking thread."""
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()
        logger.info("Context Sentinel: Background monitoring thread activated.")

    def stop(self):
        """Stops the background tracking thread."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
            logger.info("Context Sentinel: Background monitoring thread deactivated.")

    def _monitor_loop(self):
        while self.running:
            try:
                hwnd = ctypes.windll.user32.GetForegroundWindow()
                if hwnd:
                    # 1. Extract active window title
                    length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                    title = ""
                    if length > 0:
                        buff = ctypes.create_unicode_buffer(length + 1)
                        ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
                        title = buff.value

                    # 2. Extract active process PID
                    pid = ctypes.c_ulong()
                    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    
                    # 3. Resolve process name using psutil
                    proc_name = "unknown"
                    if pid.value > 0:
                        try:
                            proc = psutil.Process(pid.value)
                            proc_name = proc.name()
                        except Exception:
                            pass

                    # 4. Save to active context
                    with self._lock:
                        self.active_context = {
                            "process": proc_name.lower(),
                            "title": title,
                            "timestamp": time.time()
                        }
            except Exception as e:
                logger.error(f"Context Sentinel error in monitor loop: {e}")
                
            time.sleep(self.poll_interval)

    def get_active_context(self) -> dict:
        """Returns a copy of the active foreground window context."""
        with self._lock:
            return dict(self.active_context)


if __name__ == "__main__":
    sentinel = ContextSentinel(poll_interval=1.0)
    print("Monitoring foreground window. Switch windows to see active context updates. Press Ctrl+C to stop.")
    try:
        while True:
            ctx = sentinel.get_active_context()
            print(f"[{time.strftime('%H:%M:%S')}] Active Process: {ctx['process']} | Title: {ctx['title']}")
            time.sleep(2.0)
    except KeyboardInterrupt:
        sentinel.stop()
        print("Monitoring stopped.")
