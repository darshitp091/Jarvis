import os
import json
import time
import threading
from datetime import datetime
from loguru import logger

class ProactiveMonitor:
    """Monitors system resources, battery levels, and local calendar events in the background."""

    def __init__(self, config_dir: str = "config", camera_engine=None, alert_callback=None, compiler_repair=None):
        self.config_dir = config_dir
        self.calendar_path = os.path.join(self.config_dir, "calendar.json")
        self.notifications_path = os.path.join(self.config_dir, "incoming_notifications.json")
        self.camera = camera_engine
        self.alert_callback = alert_callback
        self.compiler_repair = compiler_repair
        self.is_running = False
        self.thread = None
        self.watcher_thread = None

        # Lock for thread safety on calendar updates
        self.lock = threading.Lock()

        # Monitoring states
        self.last_battery_percent = None
        self.last_power_plugged = None
        self.cpu_high_ticks = 0
        self.confusion_ticks = 0
        self.last_perf_alert_time = 0.0

        # Initialize calendar and notifications files if missing
        os.makedirs(self.config_dir, exist_ok=True)
        if not os.path.exists(self.calendar_path):
            with open(self.calendar_path, "w") as f:
                json.dump([], f, indent=2)
        if not os.path.exists(self.notifications_path):
            with open(self.notifications_path, "w") as f:
                json.dump([], f, indent=2)

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()
        
        # Start file watcher thread
        self.watcher_thread = threading.Thread(target=self._file_watcher_loop, daemon=True)
        self.watcher_thread.start()
        logger.info("Proactive Monitor background threads started.")

    def stop(self):
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=2)
        if self.watcher_thread:
            self.watcher_thread.join(timeout=2)
        logger.info("Proactive Monitor background threads stopped.")

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
            now = time.time()

            if cpu > 90:
                self.cpu_high_ticks += 1
                if self.cpu_high_ticks == 3:  # high for ~30 seconds (10s checks)
                    if now - self.last_perf_alert_time > 300:
                        self._trigger_alert("Sir, CPU workload is exceptionally heavy. Temperatures may rise.")
                        self.last_perf_alert_time = now
            else:
                self.cpu_high_ticks = 0

            if ram > 92:
                if now - self.last_perf_alert_time > 300:
                    self._trigger_alert("Warning, sir. System memory utilization is exceeding 92 percent.")
                    self.last_perf_alert_time = now
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

    def _check_notifications(self):
        """Scans for simulated incoming messages (WhatsApp, Email) and triggers proactive voice alerts."""
        if not os.path.exists(self.notifications_path):
            return

        with self.lock:
            try:
                with open(self.notifications_path, "r", encoding="utf-8") as f:
                    notifications = json.load(f)
            except Exception as e:
                logger.error(f"Failed to read incoming notifications: {e}")
                return

            if not notifications:
                return

            # Processes one notification at a time to prevent audio overlaps
            triggered_any = False
            for n in notifications:
                if n.get("triggered", False):
                    continue
                
                channel = n.get("channel", "WhatsApp")
                sender = n.get("sender", "Someone")
                msg_body = n.get("message", "")
                
                n["triggered"] = True
                triggered_any = True
                
                # Format Hinglish warning alert
                warning_text = f"Sir, aapko {channel} par {sender} ka message aaya hai: '{msg_body}'."
                
                alert_payload = {
                    "type": "incoming_message",
                    "channel": channel,
                    "sender": sender,
                    "message": msg_body,
                    "warning_text": warning_text
                }
                self._trigger_alert(json.dumps(alert_payload))
                break

            # Filter out processed notifications to keep the file clean
            remaining = [n for n in notifications if not n.get("triggered", False)]
            try:
                with open(self.notifications_path, "w", encoding="utf-8") as f:
                    json.dump(remaining, f, indent=2)
            except Exception as e:
                logger.error(f"Failed to save incoming notifications update: {e}")

    def _monitor_loop(self):
        calendar_check_timer = 0
        while self.is_running:
            # 1. Check battery, performance & notifications every 10 seconds
            self._check_battery()
            self._check_performance()
            self._check_disk_space()
            self._check_work_session()
            self._check_hardware()
            self._check_user_confusion()
            self._check_notifications()

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

    def _file_watcher_loop(self):
        # Initial scan of Python files
        file_mtimes = {}
        ignored_dirs = {".git", "__pycache__", "jarvis_env", ".agents", ".gemini", "auth", ".idea"}
        
        def scan_files():
            found = {}
            for root, dirs, files in os.walk("."):
                # Prune ignored directories in place
                dirs[:] = [d for d in dirs if d not in ignored_dirs and not d.startswith(".")]
                for file in files:
                    if file.endswith(".py"):
                        path = os.path.join(root, file)
                        try:
                            found[path] = os.path.getmtime(path)
                        except Exception:
                            pass
            return found

        # Initialize mtimes
        try:
            file_mtimes = scan_files()
        except Exception as e:
            logger.error(f"Error in initial file scan: {e}")

        while self.is_running:
            time.sleep(2.0)
            try:
                current_files = scan_files()
            except Exception as e:
                logger.debug(f"Error scanning files in watcher: {e}")
                continue

            for path, mtime in current_files.items():
                old_mtime = file_mtimes.get(path)
                # If file is new or modified
                if old_mtime is None or mtime > old_mtime:
                    file_mtimes[path] = mtime
                    # Read and check syntax
                    try:
                        with open(path, "r", encoding="utf-8") as f:
                            content = f.read()
                    except Exception:
                        continue

                    # Don't check empty files
                    if not content.strip():
                        continue

                    import ast
                    try:
                        ast.parse(content)
                    except SyntaxError as e:
                        # Syntax error detected!
                        filename = os.path.basename(path)
                        error_msg = f"SyntaxError: {e.msg} at line {e.lineno}, column {e.offset}"
                        logger.warning(f"Proactive Sentinel: Syntax error detected in {path} -> {error_msg}")
                        
                        # Generate self-healed version using Groq in memory
                        if self.compiler_repair:
                            logger.info(f"Proactive Sentinel: Triggering Groq repair for {path}")
                            system_prompt = (
                                "You are JARVIS's Compiler Repair Agent. Your task is to correct syntax errors in a Python file. "
                                "Output ONLY the entire corrected python code. Use a ```python ... ``` block. "
                                "Do not include explanation, preamble, or any conversational text."
                            )
                            user_prompt = (
                                f"File: '{path}'\n"
                                f"Syntax Error details:\n{error_msg}\n\n"
                                f"Original Code:\n```python\n{content}\n```\n\n"
                                "Please output the corrected version of the entire file."
                            )
                            # Call Groq via the sandbox connection
                            response = self.compiler_repair.sandbox._call_groq(system_prompt, user_prompt)
                            
                            if response and not response.startswith("ERROR"):
                                # Extract Python code
                                import re
                                code_match = re.search(r"```python(.*?)```", response, re.DOTALL)
                                if code_match:
                                    patched_code = code_match.group(1).strip()
                                else:
                                    patched_code = response.replace("```", "").strip()
                                
                                # Send alert structured as JSON
                                alert_payload = {
                                    "type": "confirm_file_patch",
                                    "file_path": os.path.abspath(path),
                                    "patched_content": patched_code,
                                    "warning_text": f"Sir, I notice a syntax fault in file {filename}. I've prepared a patch to restore compiles. Shall I write it to disk?"
                                }
                                self._trigger_alert(json.dumps(alert_payload))
                            else:
                                logger.error(f"Proactive Sentinel: Failed to generate patch: {response}")


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
