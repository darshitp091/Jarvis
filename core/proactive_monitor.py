import os
import json
import time
import threading
from datetime import datetime
from loguru import logger

class ProactiveMonitor:
    """Monitors system resources, battery levels, and local calendar events in the background."""

    def __init__(self, config_dir: str = "config", camera_engine=None, alert_callback=None):
        self.config_dir = config_dir
        self.calendar_path = os.path.join(self.config_dir, "calendar.json")
        self.camera = camera_engine
        self.alert_callback = alert_callback
        self.is_running = False
        self.thread = None

        # Lock for thread safety on calendar updates
        self.lock = threading.Lock()

        # Monitoring states
        self.last_battery_percent = None
        self.last_power_plugged = None
        self.cpu_high_ticks = 0
        self.confusion_ticks = 0

        # Initialize calendar file if missing
        os.makedirs(self.config_dir, exist_ok=True)
        if not os.path.exists(self.calendar_path):
            with open(self.calendar_path, "w") as f:
                json.dump([], f, indent=2)

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()
        logger.info("Proactive Monitor background thread started.")

    def stop(self):
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=2)
        logger.info("Proactive Monitor background thread stopped.")

    def _trigger_alert(self, text: str):
        logger.info(f"[PROACTIVE ALERT]: {text}")
        if self.alert_callback:
            self.alert_callback(text)

    def _check_battery(self):
        try:
            import psutil
            battery = psutil.sensors_battery()
            if not battery:
                return
            
            percent = battery.percent
            power_plugged = battery.power_plugged

            # Alert if charger plugged in / unplugged
            if self.last_power_plugged is not None and power_plugged != self.last_power_plugged:
                if power_plugged:
                    self._trigger_alert("AC power connected, sir.")
                else:
                    self._trigger_alert("AC power disconnected. Operating on battery power, sir.")

            # Alert on critical battery drop
            if percent <= 20 and not power_plugged:
                if self.last_battery_percent is None or self.last_battery_percent > 20:
                    self._trigger_alert(f"Warning, sir. Battery level is low at {percent} percent. Please connect a charger.")
            elif percent <= 10 and not power_plugged:
                if self.last_battery_percent is None or self.last_battery_percent > 10:
                    self._trigger_alert(f"Sir, battery level is critical at {percent} percent. Core systems offline imminent.")

            self.last_battery_percent = percent
            self.last_power_plugged = power_plugged
        except Exception as e:
            logger.debug(f"Battery check error: {e}")

    def _check_performance(self):
        try:
            import psutil
            cpu = psutil.cpu_percent()
            ram = psutil.virtual_memory().percent

            if cpu > 90:
                self.cpu_high_ticks += 1
                if self.cpu_high_ticks == 3:  # high for ~30 seconds (10s checks)
                    self._trigger_alert("Sir, CPU workload is exceptionally heavy. Temperatures may rise.")
            else:
                self.cpu_high_ticks = 0

            if ram > 92:
                self._trigger_alert("Warning, sir. System memory utilization is exceeding 92 percent.")
        except Exception as e:
            logger.debug(f"Performance check error: {e}")

    def _check_calendar(self):
        if not os.path.exists(self.calendar_path):
            return

        with self.lock:
            try:
                with open(self.calendar_path, "r", encoding="utf-8") as f:
                    events = json.load(f)
            except Exception as e:
                logger.error(f"Failed to read calendar database: {e}")
                return

            now = datetime.now()
            updated = False

            for event in events:
                if event.get("triggered", False):
                    continue
                
                try:
                    event_time = datetime.fromisoformat(event["time"])
                    # Trigger alert if current time is equal to or past event time (and within 5 mins to avoid old alarms)
                    time_diff = (now - event_time).total_seconds()
                    if 0 <= time_diff <= 300:
                        self._trigger_alert(f"Sir, a calendar reminder: {event['text']}")
                        event["triggered"] = True
                        updated = True
                except Exception as e:
                    logger.warning(f"Error parsing event timestamp {event.get('time')}: {e}")

            if updated:
                try:
                    with open(self.calendar_path, "w", encoding="utf-8") as f:
                        json.dump(events, f, indent=2)
                except Exception as e:
                    logger.error(f"Failed to save calendar updates: {e}")

    def add_calendar_event(self, time_iso: str, text: str):
        """Helper to programmatically add calendar events"""
        with self.lock:
            try:
                events = []
                if os.path.exists(self.calendar_path):
                    with open(self.calendar_path, "r", encoding="utf-8") as f:
                        events = json.load(f)
                
                events.append({
                    "time": time_iso,
                    "text": text,
                    "triggered": False
                })
                
                with open(self.calendar_path, "w", encoding="utf-8") as f:
                    json.dump(events, f, indent=2)
                logger.info(f"Added calendar event: {text} at {time_iso}")
                return True
            except Exception as e:
                logger.error(f"Failed to add calendar event: {e}")
                return False

    def _check_disk_space(self):
        try:
            import shutil
            total, used, free = shutil.disk_usage("/")
            free_percent = (free / total) * 100
            if free_percent < 10.0:
                self._trigger_alert("Sir, main storage partition free space is running critically low. Under 10 percent remaining.")
        except Exception:
            pass

    def _check_work_session(self):
        if not hasattr(self, "awake_timer_seconds"):
            self.awake_timer_seconds = 0
        self.awake_timer_seconds += 10
        if self.awake_timer_seconds >= 3600:
            self.awake_timer_seconds = 0
            self._trigger_alert("Sir, you have been working continuously for an hour. I suggest taking a short break.")

    def _check_hardware(self):
        try:
            import GPUtil
            gpus = GPUtil.getGPUs()
            if gpus:
                gpu_load = gpus[0].load * 100
                if gpu_load > 90:
                    self._trigger_alert("Sir, graphics processing unit load is exceeding 90 percent.")
        except Exception:
            pass

    def _check_user_confusion(self):
        """Monitors user facial expressions for prolonged brow furrowing to trigger proactive advice."""
        if not self.camera:
            return
        try:
            # Check if user is present and showing confusion landmarks
            if getattr(self.camera, "is_present", False) and getattr(self.camera, "is_confused", False):
                self.confusion_ticks += 1
                # Trigger alert after ~30 seconds of continuous confusion (3 checks)
                if self.confusion_ticks >= 3:
                    self.confusion_ticks = 0
                    self._trigger_alert("Sir, you look a bit puzzled. Would you like me to analyze your active window or screen code?")
            else:
                self.confusion_ticks = 0
        except Exception:
            pass

    def _monitor_loop(self):
        calendar_check_timer = 0
        while self.is_running:
            # 1. Check battery & performance every 10 seconds
            self._check_battery()
            self._check_performance()
            self._check_disk_space()
            self._check_work_session()
            self._check_hardware()
            self._check_user_confusion()

            # 2. Check calendar events every 30 seconds
            calendar_check_timer += 10
            if calendar_check_timer >= 30:
                self._check_calendar()
                calendar_check_timer = 0

            # Sleep in small steps to respond quickly to shutdown requests
            for _ in range(10):
                if not self.is_running:
                    break
                time.sleep(1)


if __name__ == "__main__":
    print("Testing Proactive Monitor in standalone mode (Ctrl+C to stop)...")
    
    def test_callback(text):
        print(f"\n>>> JARVIS SPEAKS: \"{text}\"\n")

    monitor = ProactiveMonitor(alert_callback=test_callback)
    
    # Add a mock reminder 10 seconds into the future
    from datetime import timedelta
    future_time = (datetime.now() + timedelta(seconds=15)).isoformat()
    monitor.add_calendar_event(future_time, "Time to test the Stark reactor core.")

    monitor.start()
    try:
        time.sleep(30)
    except KeyboardInterrupt:
        pass
    finally:
        monitor.stop()
