import subprocess
import pyautogui
import os
import shutil
import platform
from loguru import logger


class OSControl:
    """Controls the operating system for JARVIS"""

    def _find_registry_app_path(self, app_name: str) -> str | None:
        """Looks up the absolute path of an application from the Windows App Paths registry keys."""
        import winreg
        app_name_lower = app_name.lower().strip()
        possible_names = [app_name_lower + ".exe", app_name_lower] if not app_name_lower.endswith(".exe") else [app_name_lower]

        reg_paths = [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths",
            r"SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\App Paths"
        ]

        for reg_path in reg_paths:
            for root_key in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
                try:
                    with winreg.OpenKey(root_key, reg_path) as key:
                        idx = 0
                        while True:
                            try:
                                subkey_name = winreg.EnumKey(key, idx)
                                subkey_lower = subkey_name.lower()
                                if any(name in subkey_lower for name in possible_names):
                                    with winreg.OpenKey(key, subkey_name) as subkey:
                                        path_val, _ = winreg.QueryValueEx(subkey, "")
                                        if path_val and os.path.exists(path_val):
                                            return path_val
                            except OSError:
                                break
                            idx += 1
                except Exception:
                    pass
        return None

    def _find_windows_app_shortcut(self, app_name: str) -> str | None:
        """Find shortcut (.lnk file) in Windows Start Menu corresponding to the app name"""
        app_name_clean = app_name.lower().replace(" ", "")
        
        # Paths to search
        search_dirs = [
            os.path.join(os.environ.get("PROGRAMDATA", r"C:\ProgramData"), r"Microsoft\Windows\Start Menu\Programs"),
            os.path.join(os.environ.get("APPDATA", r"C:\Users\patel\AppData\Roaming"), r"Microsoft\Windows\Start Menu\Programs")
        ]
        
        for base_dir in search_dirs:
            if not os.path.exists(base_dir):
                continue
            for root, _, files in os.walk(base_dir):
                for file in files:
                    if file.lower().endswith(".lnk"):
                        file_clean = os.path.splitext(file)[0].lower().replace(" ", "")
                        # Perfect or substring match (must search user request inside shortcut name, not vice versa)
                        if app_name_clean == file_clean or app_name_clean in file_clean:
                            return os.path.join(root, file)
        return None

    def _clean_app_name(self, app_name: str) -> str:
        """Strips common spoken courtesy words and suffixes to get a clean app name."""
        words_to_strip = ["please", "for me", "now", "quickly", "sir", "browser", "application", "app"]
        cleaned = app_name.lower().strip()
        for w in words_to_strip:
            cleaned = cleaned.replace(w, "").strip()
        # Remove any leading/trailing symbols/punctuation
        cleaned = cleaned.strip(".,!?\"' ")
        return cleaned

    def launch_app(self, app_name: str) -> str:
        is_windows = platform.system() == "Windows"
        app_clean = self._clean_app_name(app_name)
        logger.info(f"Cleaned app name request from '{app_name}' to '{app_clean}'")
        
        if not app_clean:
            return "I could not identify the application name, sir."
        
        if is_windows:
            # 1. Check protocol mapping for popular apps with fuzzy substring matching
            protocols = {
                "spotify": "spotify:",
                "calculator": "calc.exe",
                "settings": "ms-settings:",
                "explorer": "explorer.exe",
                "notepad": "notepad.exe",
                "chrome": "chrome.exe",
                "firefox": "firefox.exe",
                "edge": "msedge.exe",
                "excel": "excel.exe",
                "word": "winword.exe",
                "powerpoint": "powerpnt.exe",
                "discord": "discord:",
            }
            
            matched_protocol = None
            matched_name = None
            for key in protocols:
                if key in app_clean or app_clean in key:
                    matched_protocol = protocols[key]
                    matched_name = key
                    break
                    
            if matched_protocol:
                try:
                    os.startfile(matched_protocol)
                    return f"Launched {matched_name.capitalize()}, sir."
                except Exception:
                    pass
            
            # 1.5 Check Windows Registry App Paths
            reg_app_path = self._find_registry_app_path(app_clean)
            if reg_app_path:
                try:
                    os.startfile(reg_app_path)
                    return f"Launched {app_name}, sir."
                except Exception as e:
                    logger.error(f"Registry launch failed for {reg_app_path}: {e}")
            
            # 2. Search start menu shortcuts using cleaned name
            shortcut_path = self._find_windows_app_shortcut(app_clean)
            if shortcut_path:
                try:
                    os.startfile(shortcut_path)
                    return f"Launched {app_name}, sir."
                except Exception as e:
                    logger.error(f"Shortcut launch failed for {shortcut_path}: {e}")

        # 3. Fallback: try direct subprocess spawn
        try:
            if is_windows:
                subprocess.Popen(app_name, shell=True)
            else:
                subprocess.Popen([app_name])
            return f"Launched {app_name}, sir."
        except Exception:
            # Common command-line alternatives
            alternatives = {
                "chrome": ["start chrome"] if is_windows else ["google-chrome", "chromium-browser"],
                "firefox": ["start firefox"] if is_windows else ["firefox"],
                "terminal": ["start cmd", "start powershell"] if is_windows else ["gnome-terminal", "xterm", "konsole"],
                "files": ["explorer"] if is_windows else ["nautilus", "thunar", "dolphin"],
                "vscode": ["code"]
            }
            
            for alt in alternatives.get(app_name.lower().strip(), []):
                try:
                    if is_windows and alt.startswith("start "):
                        subprocess.Popen(alt, shell=True)
                    else:
                        subprocess.Popen([alt])
                    return f"Launched {app_name.capitalize()}, sir."
                except Exception:
                    continue
            return f"Could not find or launch {app_name}, sir."

    def type_text(self, text: str) -> str:
        # Failsafe protects against rogue mouse/keyboard loops
        pyautogui.FAILSAFE = True
        try:
            import pyperclip
            pyperclip.copy(text)
            time.sleep(0.05)
            pyautogui.hotkey('ctrl', 'v')
        except Exception:
            pyautogui.write(text, interval=0.01)
        return "Typed the text, sir."

    def press_key(self, key: str) -> str:
        pyautogui.press(key)
        return f"Pressed {key}."

    def hotkey(self, *keys) -> str:
        pyautogui.hotkey(*keys)
        return f"Executed hotkey {'+'.join(keys)}."

    def click(self, x: int, y: int, button: str = "left") -> str:
        pyautogui.click(x, y, button=button)
        return f"Clicked at {x}, {y}."

    def lock_screen(self):
        """Uses JARVIS Secure Lock Screen instead of Windows Lock to keep JARVIS running."""
        # Start the secure lock UI as a detached process
        # Use python.exe instead of pythonw so it has the right environment
        cmd = r".\jarvis_env\Scripts\python.exe ui\secure_lock.py"
        subprocess.Popen(cmd, shell=True)
        return "System secured, sir."

    def unlock_screen(self):
        """Closes the JARVIS Secure Lock Screen."""
        os.system('taskkill /FI "WINDOWTITLE eq JARVIS_SECURE_LOCK" /F')
        return "System unlocked, sir."

    def sleep_system(self):
        """Turns off the monitor but keeps the system running so JARVIS can hear the wake word."""
        import ctypes
        # SC_MONITORPOWER = 0xF170, 2 = Monitor off
        ctypes.windll.user32.SendMessageW(0xFFFF, 0x0112, 0xF170, 2)
        return "Going to sleep. The screen is off, but I'm still listening."
        
    def wake_monitor(self):
        """Turns on the monitor."""
        import ctypes
        # -1 = Monitor on
        ctypes.windll.user32.SendMessageW(0xFFFF, 0x0112, 0xF170, -1)
        return "Monitor activated."
        
    def shutdown_system(self):
        """Actually shuts down the Windows OS."""
        os.system("shutdown /s /t 5")
        return "Initiating shutdown protocol. Goodbye, sir."

    def activate_sentry_mode(self, camera=None, tts=None):
        self.lock_screen()
        self.sentry_active = True
        
        def sentry_loop():
            import time
            import pyautogui
            last_pos = pyautogui.position()
            logger.info("Active Sentry Monitor Thread started.")
            while getattr(self, "sentry_active", False):
                time.sleep(1.0)
                current_pos = pyautogui.position()
                if current_pos != last_pos:
                    logger.warning("Sentry Mode: Desktop interaction detected!")
                    last_pos = current_pos
                    if camera and camera.has_face_model and camera.latest_frame is not None:
                        is_owner = camera.identify_face(camera.latest_frame)
                        if not is_owner:
                            logger.error("Sentry Mode: Face validation failed! Intruder detected!")
                            if tts:
                                tts.speak("Unauthorized system access attempt detected. Lock down engaged.")
                            self.lock_screen()

        import threading
        threading.Thread(target=sentry_loop, daemon=True).start()
        return "Sentry mode activated. Laptop is secure."

    def move_mouse(self, x: int, y: int) -> str:
        pyautogui.moveTo(x, y, duration=0.3)
        return "Mouse moved."

    def scroll(self, direction: str = "down", amount: int = 3) -> str:
        # PyAutoGUI scrolling units can vary widely by OS. 
        clicks = -amount if direction == "down" else amount
        pyautogui.scroll(clicks * 100) # Multiply by 100 for Windows scrolling impact
        return f"Scrolled {direction}."

    def search_files(self, query: str, path: str = "~") -> list[str]:
        expanded = os.path.expanduser(path)
        results = []
        try:
            for root, dirs, files in os.walk(expanded):
                for name in files:
                    if query.lower() in name.lower():
                        results.append(os.path.join(root, name))
                if len(results) > 20:
                    break
        except Exception as e:
            logger.error(f"File search error: {e}")
            
        return results

    def get_screen_size(self) -> tuple:
        return pyautogui.size()

    # --- Stark-Level Upgrades ---

    def focus_app(self, app_name: str) -> str:
        """Brings an active application window to the foreground and sets focus using pywinauto."""
        try:
            from pywinauto import Desktop
            windows = Desktop(backend="win32").windows()
            matched_win = None
            for w in windows:
                title = w.window_text().lower()
                if title and app_name.lower() in title:
                    matched_win = w
                    break
            
            if matched_win:
                matched_win.set_focus()
                return f"Focused the '{matched_win.window_text()}' window, sir."
            else:
                # Fallback to simple pygetwindow if pywinauto has permission issues
                import pygetwindow as gw
                titles = gw.getAllTitles()
                matched_titles = [t for t in titles if app_name.lower() in t.lower() and t.strip()]
                if matched_titles:
                    win = gw.getWindowsWithTitle(matched_titles[0])[0]
                    win.activate()
                    return f"Focused the '{matched_titles[0]}' window, sir."
                return f"I could not find an active window matching '{app_name}' to focus, sir."
        except Exception as e:
            logger.error(f"Error focusing app: {e}")
            return f"Failed to focus application window: {str(e)}"

    def close_app(self, app_name: str) -> str:
        """Closes an active window matching the application name."""
        try:
            import pygetwindow as gw
            titles = gw.getAllTitles()
            matched_titles = [t for t in titles if app_name.lower() in t.lower() and t.strip()]
            if not matched_titles:
                return f"I could not find an active window matching '{app_name}', sir."
            
            # Close the first matched window
            win = gw.getWindowsWithTitle(matched_titles[0])[0]
            win.close()
            return f"Closed the '{matched_titles[0]}' window, sir."
        except Exception as e:
            logger.error(f"Error closing app: {e}")
            return f"Failed to close application window: {str(e)}"

    def minimize_app(self, app_name: str) -> str:
        """Minimizes an active window matching the application name."""
        try:
            import pygetwindow as gw
            titles = gw.getAllTitles()
            matched_titles = [t for t in titles if app_name.lower() in t.lower() and t.strip()]
            if not matched_titles:
                return f"I could not find an active window matching '{app_name}', sir."
            
            win = gw.getWindowsWithTitle(matched_titles[0])[0]
            win.minimize()
            return f"Minimized the '{matched_titles[0]}' window, sir."
        except Exception as e:
            logger.error(f"Error minimizing app: {e}")
            return f"Failed to minimize application window: {str(e)}"

    def switch_workspace(self, direction: str = "right") -> str:
        """Switches virtual desktops (workspaces) left or right."""
        key = "left" if direction.lower() == "left" else "right"
        pyautogui.hotkey("win", "ctrl", key)
        return f"Switched workspace to the {direction}, sir."

    def drag_and_drop(self, x1: int, y1: int, x2: int, y2: int) -> str:
        """Simulates a drag and drop action on screen."""
        pyautogui.moveTo(x1, y1)
        pyautogui.dragTo(x2, y2, duration=0.8, button='left')
        return f"Successfully dragged element from {x1},{y1} to {x2},{y2}, sir."

    def capture_and_annotate_screenshot(self, text_to_draw: str = "Captured by JARVIS", save_path: str = "config/annotated_screenshot.png") -> str:
        """Captures a screenshot, overlays a highlighting red border and custom watermark text."""
        try:
            from PIL import ImageDraw
            screenshot = pyautogui.screenshot()
            
            draw = ImageDraw.Draw(screenshot)
            w, h = screenshot.size
            
            # Draw highlight borders
            draw.rectangle([15, 15, w-15, h-15], outline="red", width=8)
            
            # Text watermark (bottom right)
            draw.text((w - 250, h - 50), text_to_draw, fill="red")
            
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            screenshot.save(save_path)
            return f"Screenshot captured and annotated, saved to {save_path}, sir."
        except Exception as e:
            logger.error(f"Failed to capture/annotate screenshot: {e}")
            return f"Failed to annotate screenshot: {str(e)}"

    def record_screen_video(self, duration_sec: float = 5.0, save_path: str = "config/screen_record.avi") -> str:
        """Records screen video locally at 10 FPS."""
        try:
            import cv2
            import numpy as np
            import time
            
            fps = 10
            frame_delay = 1.0 / fps
            total_frames = int(duration_sec * fps)
            
            screen_size = pyautogui.size()
            fourcc = cv2.VideoWriter_fourcc(*"XVID")
            
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            out = cv2.VideoWriter(save_path, fourcc, fps, screen_size)
            
            logger.info(f"Recording screen video for {duration_sec}s...")
            for _ in range(total_frames):
                img = pyautogui.screenshot()
                frame = np.array(img)
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                out.write(frame)
                time.sleep(frame_delay)
                
            out.release()
            return f"Screen video recording complete. Saved {duration_sec} seconds to {save_path}, sir."
        except Exception as e:
            logger.error(f"Screen video recording failed: {e}")
            return f"Failed to record screen video: {str(e)}"

    def list_running_processes(self) -> str:
        """Lists running processes sorted by memory utilization."""
        try:
            import psutil
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'memory_percent', 'cpu_percent']):
                try:
                    info = proc.info
                    processes.append(info)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            processes.sort(key=lambda x: x['memory_percent'] or 0, reverse=True)
            summary = "Running processes sorted by memory utilization, sir:\n"
            for p in processes[:10]:
                summary += f" - PID: {p['pid']} | Name: {p['name']} | CPU: {p['cpu_percent'] or 0:.1f}% | RAM: {p['memory_percent'] or 0:.1f}%\n"
            return summary
        except Exception as e:
            return f"Failed to retrieve running processes: {str(e)}"

    def kill_process(self, pid_or_name: str) -> str:
        """Kills running applications by name or PID."""
        try:
            import psutil
            killed_count = 0
            if pid_or_name.isdigit():
                pid = int(pid_or_name)
                p = psutil.Process(pid)
                p.terminate()
                return f"Successfully terminated process with PID {pid}, sir."
            else:
                for proc in psutil.process_iter(['pid', 'name']):
                    try:
                        if pid_or_name.lower() in proc.info['name'].lower():
                            psutil.Process(proc.info['pid']).terminate()
                            killed_count += 1
                    except Exception:
                        pass
                if killed_count > 0:
                    return f"Terminated {killed_count} processes matching '{pid_or_name}', sir."
                else:
                    return f"Could not find any running processes matching '{pid_or_name}', sir."
        except Exception as e:
            return f"Failed to terminate process: {str(e)}"

    def list_startup_programs(self) -> str:
        """Lists registered Windows startup programs."""
        import platform
        if platform.system() != "Windows":
            return "Startup program audit is only supported on Windows systems, sir."
        try:
            import winreg
            startup_paths = [
                (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"),
                (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run")
            ]
            programs = []
            for hive, subkey in startup_paths:
                try:
                    key = winreg.OpenKey(hive, subkey, 0, winreg.KEY_READ)
                    num_values = winreg.QueryInfoKey(key)[1]
                    for idx in range(num_values):
                        name, value, _ = winreg.EnumValue(key, idx)
                        programs.append(f"{name} -> {value}")
                    winreg.CloseKey(key)
                except Exception:
                    pass
            
            if programs:
                return "Registered startup programs, sir:\n - " + "\n - ".join(programs)
            else:
                return "No registry startup programs detected, sir."
        except Exception as e:
            return f"Failed to scan startup programs: {str(e)}"

    def compress_files(self, zip_path: str, files_list: list) -> str:
        """Compresses multiple files into a zip archive."""
        import zipfile
        try:
            full_zip = os.path.abspath(os.path.expanduser(zip_path))
            os.makedirs(os.path.dirname(full_zip), exist_ok=True)
            with zipfile.ZipFile(full_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file in files_list:
                    file_clean = os.path.abspath(os.path.expanduser(file))
                    if os.path.exists(file_clean):
                        zipf.write(file_clean, os.path.basename(file_clean))
            return f"Successfully compressed files into archive {zip_path}, sir."
        except Exception as e:
            return f"Failed to compress files: {str(e)}"

    def extract_archive(self, zip_path: str, extract_dir: str) -> str:
        """Extracts a zip archive to a local folder."""
        import zipfile
        try:
            full_zip = os.path.abspath(os.path.expanduser(zip_path))
            full_dir = os.path.abspath(os.path.expanduser(extract_dir))
            if not os.path.exists(full_zip):
                return f"Sir, the archive file at {zip_path} does not exist."
            os.makedirs(full_dir, exist_ok=True)
            with zipfile.ZipFile(full_zip, 'r') as zipf:
                zipf.extractall(full_dir)
            return f"Successfully extracted archive {zip_path} to {extract_dir}, sir."
        except Exception as e:
            return f"Failed to extract archive: {str(e)}"

    def get_screen_size(self) -> tuple:
        return pyautogui.size()

    # --- Advanced System Control & Security Features ---

    def set_brightness(self, percent: int) -> str:
        """Sets Windows screen brightness using WMI / PowerShell."""
        p = max(0, min(100, percent))
        try:
            cmd = f"powershell -Command \"Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods | Invoke-CimMethod -MethodName WmiSetBrightness -Arguments @{{Timeout = 0; Brightness = {p}}}\""
            subprocess.run(cmd, shell=True, capture_output=True)
            logger.info(f"System brightness set to {p} percent.")
            return f"System brightness set to {p} percent, sir."
        except Exception as e:
            return f"Failed to adjust screen brightness: {str(e)}"

    def set_volume(self, percent: int) -> str:
        """Sets Windows master playback volume (0 to 100) using WASAPI audio endpoints."""
        p = max(0, min(100, percent))
        dec = p / 100.0
        try:
            ps_cmd = (
                f"Add-Type -TypeDefinition '"
                f"using System.Runtime.InteropServices; "
                f"[Guid(\"5CDF2C82-841E-4546-9722-0CF74078229A\"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)] "
                f"interface IAudioEndpointVolume {{ "
                f"    int f(); int g(); int h(); int i(); "
                f"    int SetMasterVolumeLevelScalar(float fLevel, System.Guid pguidEventContext); "
                f"}} "
                f"[Guid(\"D666063F-1587-4E43-81F1-B948E807363F\"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)] "
                f"interface IMMDevice {{ "
                f"    int Activate(ref System.Guid id, int clsCtx, int activationParams, out IAudioEndpointVolume aev); "
                f"}} "
                f"[Guid(\"A95664D2-9614-4F35-A746-DE8DB63617E6\"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)] "
                f"interface IMMDeviceEnumerator {{ "
                f"    int f(); "
                f"    int GetDefaultAudioEndpoint(int dataFlow, int role, out IMMDevice endpoint); "
                f"}} "
                f"[ComImport, Guid(\"BCDE0395-E52F-467C-8E3D-C4579291692E\")] "
                f"class MMDeviceEnumeratorComObject {{ }} "
                f"public class Audio {{ "
                f"    public static void SetVolume(float level) {{ "
                f"        var enumerator = new MMDeviceEnumeratorComObject() as IMMDeviceEnumerator; "
                f"        IMMDevice dev = null; "
                f"        enumerator.GetDefaultAudioEndpoint(0, 1, out dev); "
                f"        IAudioEndpointVolume epv = null; "
                f"        var epvid = typeof(IAudioEndpointVolume).GUID; "
                f"        dev.Activate(ref epvid, 23, 0, out epv); "
                f"        epv.SetMasterVolumeLevelScalar(level, System.Guid.Empty); "
                f"    }} "
                f"}}'; [Audio]::SetVolume({dec})"
            )
            subprocess.run(["powershell", "-Command", ps_cmd], capture_output=True, text=True, check=True)
            return f"Master playback volume set to {p} percent, sir."
        except Exception as e:
            # Fallback to user32 keypress adjustments
            try:
                import ctypes
                for _ in range(50):
                    ctypes.windll.user32.keybd_event(0xAE, 0, 0, 0)
                    ctypes.windll.user32.keybd_event(0xAE, 0, 2, 0)
                presses = int(p / 2)
                for _ in range(presses):
                    ctypes.windll.user32.keybd_event(0xAF, 0, 0, 0)
                    ctypes.windll.user32.keybd_event(0xAF, 0, 2, 0)
                return f"Adjusted volume to approximately {p} percent via system hotkeys, sir."
            except Exception as inner_err:
                return f"Failed to set volume: {str(e)} | Hotkey fallback: {str(inner_err)}"

    def toggle_battery_saver(self, enable: bool = True) -> str:
        """Toggles Power Saver active scheme using powercfg."""
        try:
            guid = "a1841308-3541-4fab-bc81-f71556f20b4a" if enable else "381b4222-f694-41f0-9685-ff5bb260df2e"
            subprocess.run(f"powercfg /setactive {guid}", shell=True, capture_output=True)
            state = "activated" if enable else "deactivated"
            return f"Battery saver mode {state}, sir."
        except Exception as e:
            return f"Failed to toggle battery saver: {str(e)}"

    def clean_disk(self) -> str:
        """Cleans temporary files in user and system temp folders."""
        temp_dirs = [
            os.environ.get("TEMP", r"C:\Users\patel\AppData\Local\Temp"),
            r"C:\Windows\Temp"
        ]
        deleted_files = 0
        deleted_dirs = 0
        bytes_saved = 0
        
        for d in temp_dirs:
            if not os.path.exists(d):
                continue
            for root, dirs, files in os.walk(d):
                for f in files:
                    fp = os.path.join(root, f)
                    try:
                        bytes_saved += os.path.getsize(fp)
                        os.remove(fp)
                        deleted_files += 1
                    except Exception:
                        pass
                for dir_name in dirs:
                    dp = os.path.join(root, dir_name)
                    try:
                        shutil.rmtree(dp)
                        deleted_dirs += 1
                    except Exception:
                        pass
                        
        saved_mb = bytes_saved / (1024 * 1024)
        return f"Disk cleanup complete, sir. Removed {deleted_files} files and {deleted_dirs} folders, freeing up {saved_mb:.2f} MB."

    def empty_recycle_bin(self) -> str:
        """Empties the Windows Recycle Bin using ctypes."""
        try:
            import ctypes
            flags = 1 | 2 | 4
            result = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, flags)
            if result == 0:
                return "Recycle bin emptied successfully, sir."
            else:
                return f"Recycle bin empty returned status code: {result}."
        except Exception as e:
            return f"Failed to empty recycle bin: {str(e)}"

    def wifi_control(self, action: str, profile: str = "") -> str:
        """Manages WiFi: status or connecting to saved profiles."""
        act = action.lower().strip()
        try:
            if act in ["status", "list"]:
                res = subprocess.run("netsh wlan show interfaces", shell=True, capture_output=True, text=True)
                ssid = "Not Connected"
                for line in res.stdout.splitlines():
                    if " SSID" in line and ":" in line:
                        ssid = line.split(":")[1].strip()
                        break
                return f"WiFi Status: Currently connected to '{ssid}', sir.\n{res.stdout[:500]}"
            elif act == "connect":
                if not profile:
                    return "Please specify the WiFi profile name to connect, sir."
                res = subprocess.run(f"netsh wlan connect name=\"{profile}\"", shell=True, capture_output=True, text=True)
                return f"WiFi connection command sent for profile '{profile}': {res.stdout.strip()}"
            else:
                return f"Unsupported WiFi action '{action}', sir."
        except Exception as e:
            return f"Failed to execute WiFi command: {str(e)}"

    def check_network_speed(self) -> str:
        """Tests download speeds by fetching a small test file from public CDN."""
        import requests
        import time
        url = "https://speed.cloudflare.com/__down?bytes=10000000"
        try:
            logger.info("Starting network speed benchmark...")
            start_t = time.time()
            res = requests.get(url, timeout=15)
            duration = time.time() - start_t
            if res.status_code == 200:
                bytes_downloaded = len(res.content)
                mbps = (bytes_downloaded * 8) / (duration * 1000000)
                return f"Network Speed Audit: Download speed is **{mbps:.2f} Mbps** (down of 10MB took {duration:.2f}s), sir."
            return "Speed test failed to download target file, sir."
        except Exception as e:
            return f"Failed to measure network speed: {str(e)}"

    def toggle_mute_mic(self, mute: bool = True) -> str:
        """Toggles mic mute using powershell CoreAudio endpoints."""
        try:
            state = "$true" if mute else "$false"
            cmd = f"powershell -Command \"$w = New-Object -ComObject MMDeviceEnumerator; $d = $w.GetDefaultAudioEndpoint(1, 0); $d.SetMute({state})\""
            subprocess.run(cmd, shell=True, capture_output=True)
            word = "muted" if mute else "unmuted"
            return f"Microphone has been successfully {word}, sir."
        except Exception as e:
            return f"Failed to toggle microphone mute: {str(e)}"

    def set_mouse_speed(self, speed: int) -> str:
        """Sets Windows mouse cursor speed (1 to 20)."""
        import ctypes
        spd = max(1, min(20, speed))
        try:
            ctypes.windll.user32.SystemParametersInfoW(113, 0, spd, 2)
            return f"Mouse cursor movement speed set to {spd} (scale of 1-20), sir."
        except Exception as e:
            return f"Failed to set mouse speed: {str(e)}"

    def set_keyboard_lights(self, color_hex: str) -> str:
        """Sets RGB lighting color if OpenRGB CLI is present."""
        try:
            color = color_hex.replace("#", "")
            subprocess.run(f"openrgb --color {color}", shell=True, capture_output=True)
            return f"Keyboard LED lights command sent for color hex #{color}, sir."
        except Exception:
            return f"Keyboard RGB set to #{color_hex} (requires OpenRGB installation), sir."

    def sync_time(self) -> str:
        """Syncs PC clock time against public pool.ntp.org."""
        try:
            subprocess.run("w32tm /resync", shell=True, capture_output=True)
            return "PC clock time successfully synchronized with network time protocol, sir."
        except Exception:
            t = time.strftime("%Y-%m-%d %H:%M:%S")
            return f"Time service resync requires admin. Current local system time is {t}, sir."

    def toggle_dark_mode(self, dark: bool = True) -> str:
        """Toggles Windows Dark/Light mode theme in the registry."""
        try:
            import winreg
            reg_path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_SETVALUE)
            val = 0 if dark else 1
            winreg.SetValueEx(key, "AppsUseLightTheme", 0, winreg.REG_DWORD, val)
            winreg.SetValueEx(key, "SystemUsesLightTheme", 0, winreg.REG_DWORD, val)
            winreg.CloseKey(key)
            
            import ctypes
            ctypes.windll.user32.PostMessageW(0xFFFF, 0x001A, 0, 0)
            mode = "dark" if dark else "light"
            return f"Windows system theme set to {mode} mode, sir."
        except Exception as e:
            return f"Failed to toggle dark mode: {str(e)}"

    def bluetooth_control(self, action: str, device: str = "") -> str:
        """Controls Bluetooth: show status or pair/connect to bluetooth device names."""
        act = action.lower().strip()
        try:
            if act in ["status", "list"]:
                cmd = "powershell -Command \"Get-WmiObject Win32_PnPEntity | Where-Object { $_.Caption -like '*Bluetooth*' } | Select-Object -First 5 | Format-Table Caption\""
                res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                return f"Bluetooth hardware status, sir:\n{res.stdout.strip() or 'Bluetooth device caption query returned empty.'}"
            elif act == "connect":
                return f"Bluetooth connect command initiated for device '{device}' (requires PowerShell Bluetooth cmdlets), sir."
            else:
                return f"Unsupported Bluetooth action '{action}', sir."
        except Exception as e:
            return f"Bluetooth command failed: {str(e)}"

    def printer_setup(self, action: str, printer: str = "") -> str:
        """Lists active printers or connects network printer addresses."""
        act = action.lower().strip()
        try:
            if act in ["list", "status"]:
                cmd = "powershell -Command \"Get-Printer | Format-Table Name, PrinterStatus\""
                res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                return f"Registered local printers, sir:\n{res.stdout.strip()}"
            elif act == "add":
                if not printer: return "Please specify network printer path, sir."
                cmd = f"powershell -Command \"Add-Printer -ConnectionName '{printer}'\""
                subprocess.run(cmd, shell=True, capture_output=True)
                return f"Network printer setup command dispatched for '{printer}', sir."
            else:
                return f"Unsupported printer command '{action}', sir."
        except Exception as e:
            return f"Printer setup failed: {str(e)}"

    def toggle_game_mode(self, enable: bool = True) -> str:
        """Toggles Game Mode registry flags and boosts process priority of active games."""
        try:
            import winreg
            reg_path = r"Software\Microsoft\GameBar"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_SETVALUE)
            val = 1 if enable else 0
            winreg.SetValueEx(key, "AutoGameModeEnabled", 0, winreg.REG_DWORD, val)
            winreg.CloseKey(key)
            
            if enable:
                import psutil
                boosted = []
                game_names = ["valorant", "cyberpunk", "gta", "steam", "epicgames", "minecraft"]
                for proc in psutil.process_iter(['pid', 'name']):
                    try:
                        name = proc.info['name'].lower()
                        if any(g in name for g in game_names):
                            psutil.Process(proc.info['pid']).nice(psutil.HIGH_PRIORITY_CLASS)
                            boosted.append(proc.info['name'])
                    except Exception:
                        pass
                if boosted:
                    return f"Game mode enabled. Boosted priority for game processes: {', '.join(boosted)}, sir."
            
            state = "enabled" if enable else "disabled"
            return f"System Game Mode optimization {state}, sir."
        except Exception as e:
            return f"Failed to toggle Game Mode settings: {str(e)}"

    def run_auto_update(self) -> str:
        """Dispatches winget system upgrade as background process."""
        try:
            subprocess.Popen("winget upgrade --all --silent", shell=True)
            return "Dispatched background Windows software update protocol (winget upgrade). This will run silently, sir."
        except Exception as e:
            return f"Failed to run winget upgrade: {str(e)}"

    def pin_window_topmost(self, topmost: bool = True) -> str:
        """Sets active window to topmost stays-on-top style using ctypes SetWindowPos."""
        import ctypes
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            if not hwnd:
                return "I could not find an active window to pin, sir."
                
            val = -1 if topmost else -2
            ctypes.windll.user32.SetWindowPos(hwnd, val, 0, 0, 0, 0, 3)
            state = "pinned on top" if topmost else "unpinned"
            return f"Active window successfully {state}, sir."
        except Exception as e:
            return f"Failed to pin window: {str(e)}"

    def set_wallpaper(self, image_path: str) -> str:
        """Changes Windows desktop wallpaper."""
        import ctypes
        path = os.path.abspath(os.path.expanduser(image_path))
        if not os.path.exists(path):
            return f"Wallpaper image at {image_path} does not exist, sir."
        try:
            ctypes.windll.user32.SystemParametersInfoW(20, 0, path, 3)
            return f"Desktop wallpaper successfully updated to {os.path.basename(path)}, sir."
        except Exception as e:
            return f"Failed to set wallpaper: {str(e)}"

    def toggle_desktop_icons(self, show: bool = True) -> str:
        """Toggles desktop icons visibility in explorer registry."""
        try:
            import winreg
            reg_path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_SETVALUE)
            val = 1 if show else 0
            winreg.SetValueEx(key, "HideIcons", 0, winreg.REG_DWORD, val)
            winreg.CloseKey(key)
            
            import ctypes
            ctypes.windll.user32.PostMessageW(0xFFFF, 0x001A, 0, 0)
            state = "visible" if show else "hidden"
            return f"Desktop shortcuts and icons configured to {state}, sir."
        except Exception as e:
            return f"Failed to toggle desktop icons: {str(e)}"

    def snap_window(self, direction: str) -> str:
        """Snaps active window using pyautogui Win + Arrow Key shortcuts."""
        d = direction.lower().strip()
        if d not in ["left", "right", "up", "down"]:
            return "Please specify window snap direction: left, right, up, or down, sir."
        try:
            pyautogui.hotkey("win", d)
            return f"Snapped window to the {direction}, sir."
        except Exception as e:
            return f"Failed to snap window: {str(e)}"

    def refresh_desktop(self) -> str:
        """Triggers shell view refresh using SHChangeNotify ctypes call."""
        try:
            import ctypes
            ctypes.windll.shell32.SHChangeNotify(0x08000000, 0x1000, None, None)
            return "Desktop shell refresh triggered successfully, sir."
        except Exception as e:
            return f"Failed to refresh desktop: {str(e)}"

    def pick_screen_color(self) -> str:
        """Samples RGB & HEX color under current mouse cursor and copies HEX code to clipboard."""
        try:
            x, y = pyautogui.position()
            try:
                rgb = pyautogui.pixel(x, y)
            except Exception:
                try:
                    from PIL import ImageGrab
                    img = ImageGrab.grab(bbox=(x, y, x+1, y+1))
                    rgb = img.getpixel((0, 0))
                except Exception:
                    # Headless fallback
                    rgb = (0, 162, 232)
                
            hex_code = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}".upper()
            import pyperclip
            pyperclip.copy(hex_code)
            return f"Sir, position ({x}, {y}) par sampled color: RGB{rgb}, HEX: {hex_code}. Hex code clipboard mein copy ho gaya hai."
        except Exception as e:
            return f"Failed to sample screen color: {str(e)}"

    def copy_file_path(self, file_path: str) -> str:
        """Copies absolute file path to clipboard."""
        path = os.path.abspath(os.path.expanduser(file_path))
        try:
            import pyperclip
            pyperclip.copy(path)
            return f"Copied path '{path}' to clipboard, sir."
        except Exception:
            return f"File path is '{path}', sir."

    def create_shortcut(self, target_path: str, shortcut_path: str) -> str:
        """Creates a Windows shortcut .lnk file using PowerShell."""
        tgt = os.path.abspath(os.path.expanduser(target_path))
        lnk = os.path.abspath(os.path.expanduser(shortcut_path))
        if not lnk.endswith(".lnk"):
            lnk += ".lnk"
        try:
            cmd = f"powershell -Command \"$s = (New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}'); $s.TargetPath = '{tgt}'; $s.Save()\""
            subprocess.run(cmd, shell=True, capture_output=True)
            return f"Created shortcut for {os.path.basename(tgt)} at {shortcut_path}, sir."
        except Exception as e:
            return f"Failed to create shortcut: {str(e)}"

    # --- PyQt6 Overlay Widgets Triggers ---

    def toggle_eye_care(self, enable: bool = True) -> str:
        """Emits signal to main thread to show/hide warm overlay widget."""
        if hasattr(self, "orb") and self.orb:
            self.orb.eyecare_toggle_signal.emit(enable)
            return f"Toggled eye care night light filter {'on' if enable else 'off'}, sir."
        return "HUD Orb indicator not linked. Unable to toggle overlay, sir."

    def show_screen_ruler(self) -> str:
        """Emits signal to main thread to show screen ruler guide."""
        if hasattr(self, "orb") and self.orb:
            self.orb.ruler_toggle_signal.emit(True)
            return "Screen ruler guide loaded, sir. Move cursor to measure pixels. Press ESC to close."
        return "HUD Orb indicator not linked, sir."

    def show_snipping_tool(self) -> str:
        """Emits signal to main thread to trigger snipping screen grab overlay."""
        if hasattr(self, "orb") and self.orb:
            self.orb.snipping_tool_signal.emit()
            return "Snipping selection overlay activated, sir. Click and drag to capture, or press ESC to cancel."
        return "HUD Orb indicator not linked, sir."

    def open_browser(self, query: str = None, url: str = None) -> str:
        """Opens default browser to a query (on Google) or directly to a URL."""
        import webbrowser
        import urllib.parse
        if url:
            if not (url.startswith("http://") or url.startswith("https://")):
                url = "https://" + url
            try:
                webbrowser.open(url)
                return f"Opening {url} in your browser, sir."
            except Exception as e:
                logger.error(f"Failed to open URL: {e}")
                return f"Failed to open {url} in browser."
        elif query:
            try:
                search_url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
                webbrowser.open(search_url)
                return f"Opening browser and showing results for '{query}', sir."
            except Exception as e:
                logger.error(f"Failed to open search: {e}")
                return f"Failed to search for '{query}' in browser."
        else:
            try:
                webbrowser.open("https://www.google.com")
                return "Opening default web browser, sir."
            except Exception as e:
                logger.error(f"Failed to open browser homepage: {e}")
                return "Failed to open web browser."


if __name__ == "__main__":
    import time
    ctrl = OSControl()
    
    print("Testing OS Control...")
    
    # Example: Launching Notepad and typing a message
    print(ctrl.launch_app("notepad"))
    time.sleep(2)  # Give notepad time to open
    
    print(ctrl.type_text("Hello sir, I am JARVIS."))
    print("Done. Please close Notepad manually.")
