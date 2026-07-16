import subprocess
import re
import time
import urllib.parse
import os
from loguru import logger

class PhoneController:
    """Manages an Android device connected via USB using ADB (Android Debug Bridge)."""

    def __init__(self):
        self.adb_path = "adb"  # assumed in PATH, as verified
        self.flashlight_on = False
        self.cached_volume = 7  # default stream music index (range 0-15)
        self.last_reminder = None
        
        # Start ADB wireless auto-bridge in the background
        import threading
        threading.Thread(target=self.auto_bridge_wireless, daemon=True).start()

    def _get_best_device_serial(self) -> str or None:
        """Returns the best connected device serial (prefers USB over wireless)."""
        try:
            cmd = [self.adb_path, "devices"]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
            if result.returncode != 0:
                return None
            
            lines = result.stdout.strip().splitlines()
            devices = []
            for line in lines[1:]:
                if line.strip():
                    parts = line.split()
                    if len(parts) >= 2 and parts[1] == "device":
                        devices.append(parts[0])
            
            if not devices:
                return None
            
            # Prefer physical USB devices (serials without ':' or '5555')
            usb_devices = [d for d in devices if ":" not in d]
            if usb_devices:
                return usb_devices[0]
            
            # Fallback to wireless device
            return devices[0]
        except Exception:
            return None

    def _run_adb_cmd(self, args: list[str]) -> tuple[bool, str]:
        """Runs an adb command and returns (Success, OutputString)"""
        try:
            # Avoid recursion if checking devices or connecting/disconnecting
            cmd_type = args[0] if args else ""
            if cmd_type not in ["devices", "connect", "disconnect", "version", "start-server", "kill-server"]:
                serial = self._get_best_device_serial()
                if serial:
                    args = ["-s", serial] + args
            
            cmd = [self.adb_path] + args
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
            if result.returncode == 0:
                return True, result.stdout.strip()
            else:
                return False, result.stderr.strip()
        except subprocess.TimeoutExpired:
            return False, "ADB command timed out."
        except Exception as e:
            return False, str(e)

    def is_device_connected(self) -> bool:
        """Returns True if at least one Android device is connected via USB debugging."""
        return self._get_best_device_serial() is not None

    def make_call(self, phone_number: str) -> str:
        """Dials and initiates a phone call on the connected device."""
        if not self.is_device_connected():
            return "Please connect your Android device via USB and enable USB debugging, sir."

        # Clean number (digits only, keep '+' if present at the start)
        clean_num = re.sub(r"[^\d+]", "", phone_number)
        if not clean_num:
            return "Invalid phone number provided, sir."

        # Launch call intent
        success, output = self._run_adb_cmd([
            "shell", "am", "start", "-a", "android.intent.action.CALL", "-d", f"tel:{clean_num}"
        ])
        
        if success:
            return f"Dialing {phone_number} on your mobile, sir."
        else:
            # Fallback: open dialer with pre-filled number if direct CALL action is blocked by permissions
            success_dial, _ = self._run_adb_cmd([
                "shell", "am", "start", "-a", "android.intent.action.DIAL", "-d", f"tel:{clean_num}"
            ])
            if success_dial:
                return f"Opening dialer with number {phone_number}, sir. Please press call on the screen."
            return f"Failed to initiate call: {output}"

    def throw_file_to_phone(self, content_or_path: str) -> str:
        """Pushes a file or text content to the Android device and displays it instantly."""
        if not self.is_device_connected():
            return "Please connect your Android device via USB, sir."

        # If it's a file path that exists, use it. Otherwise, write content to a temp file.
        pc_path = content_or_path
        is_temp = False
        if not os.path.exists(pc_path):
            pc_path = "config/temp_throw.txt"
            os.makedirs("config", exist_ok=True)
            with open(pc_path, "w", encoding="utf-8") as f:
                f.write(content_or_path)
            is_temp = True

        try:
            # 1. Push file to phone SD card
            phone_dest = "/sdcard/workspace_throw.txt"
            success_push, err = self._run_adb_cmd(["push", pc_path, phone_dest])
            if not success_push:
                return f"ADB push failed: {err}"

            # 2. Trigger Android action view intent to open the file on screen
            self._run_adb_cmd([
                "shell", "am", "start", "-a", "android.intent.action.VIEW", 
                "-d", f"file://{phone_dest}", "-t", "text/plain"
            ])
            
            # 3. Clean up local temp file
            if is_temp and os.path.exists(pc_path):
                os.remove(pc_path)

            return f"File successfully thrown to your mobile device at '{phone_dest}', sir."
        except Exception as e:
            return f"Failed to transfer document to phone: {str(e)}"

    def pull_phone_screen_to_desktop(self, save_path: str = "config/phone_screen_pull.png") -> str:
        """Captures the phone screen buffer and downloads it to the desktop."""
        if not self.is_device_connected():
            return "Please connect your Android device via USB, sir."

        try:
            # 1. Capture screen on Android
            phone_tmp = "/sdcard/screen_pull.png"
            success_cap, err = self._run_adb_cmd(["shell", "screencap", "-p", phone_tmp])
            if not success_cap:
                return f"Failed to capture screen: {err}"

            # 2. Pull screen back to PC
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            success_pull, err = self._run_adb_cmd(["pull", phone_tmp, save_path])
            if not success_pull:
                return f"Failed to pull screen: {err}"

            # 3. Delete temp capture on phone to save space
            self._run_adb_cmd(["shell", "rm", phone_tmp])

            return f"Phone screen successfully pulled to '{save_path}', sir."
        except Exception as e:
            return f"Failed to sync phone screen: {str(e)}"

    def check_call_state(self) -> dict:
        """
        Checks current call state from telephony registries.
        Returns a dict: {"state": int, "number": str}
        States: 0 = IDLE, 1 = RINGING, 2 = OFFHOOK (Active Call)
        """
        if not self.is_device_connected():
            return {"state": 0, "number": ""}

        success, output = self._run_adb_cmd(["shell", "dumpsys", "telephony.registry"])
        if not success:
            return {"state": 0, "number": ""}

        call_state = 0
        incoming_number = ""

        # Parse output for mCallState and mCallIncomingNumber
        state_match = re.search(r"mCallState=(\d+)", output)
        number_match = re.search(r"mCallIncomingNumber=([+\d]*)", output)

        if state_match:
            call_state = int(state_match.group(1))
        if number_match:
            incoming_number = number_match.group(1).strip()

        return {"state": call_state, "number": incoming_number}

    def answer_call(self) -> bool:
        """Answers an incoming ringing call."""
        success, _ = self._run_adb_cmd(["shell", "input", "keyevent", "5"])
        return success

    def hangup_call(self) -> bool:
        """Rejects or terminates an active call."""
        success, _ = self._run_adb_cmd(["shell", "input", "keyevent", "6"])
        return success

    def _fetch_all_contacts(self) -> dict[str, str]:
        """Queries contacts database via ADB shell content query, returns dict of {normalized_name: number}"""
        contacts = {}
        cache_path = "config/contacts_cache.json"
        
        if not self.is_device_connected():
            if os.path.exists(cache_path):
                try:
                    with open(cache_path, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception:
                    pass
            return contacts

        # Query phones database
        success, output = self._run_adb_cmd([
            "shell", "content", "query", "--uri", "content://com.android.contacts/data/phones",
            "--projection", "display_name:data1"
        ])
        
        if not success:
            # Fallback older URI schema
            success, output = self._run_adb_cmd([
                "shell", "content", "query", "--uri", "content://contacts/phones",
                "--projection", "display_name:number"
            ])
            if not success:
                if os.path.exists(cache_path):
                    try:
                        with open(cache_path, "r", encoding="utf-8") as f:
                            return json.load(f)
                    except Exception:
                        pass
                return contacts

        # Parse outputs (e.g. Row: 0 display_name=Karan Aujla, data1=1234567890)
        lines = output.splitlines()
        for line in lines:
            name_match = re.search(r"display_name=([^,\n]+)", line)
            num_match = re.search(r"(?:data1|number)=([^,\n]+)", line)
            
            if name_match and num_match:
                name = name_match.group(1).strip().lower()
                number = num_match.group(1).strip()
                # Clean number
                clean_num = re.sub(r"[^\d+]", "", number)
                contacts[name] = clean_num
                
        # Cache the contacts
        if contacts:
            try:
                os.makedirs("config", exist_ok=True)
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(contacts, f, indent=2, ensure_ascii=False)
            except Exception:
                pass
                
        return contacts

    def get_contact_by_name(self, name: str) -> str | None:
        """Searches contacts for a name and returns the phone number if matched."""
        contacts = self._fetch_all_contacts()
        query_name = name.lower().strip()
        
        # 1. Exact match
        if query_name in contacts:
            return contacts[query_name]

        # 2. Substring match (e.g. "karan" matches "karan aujla")
        for contact_name, number in contacts.items():
            if query_name in contact_name or contact_name in query_name:
                logger.info(f"Fuzzy contact match: '{name}' matched to '{contact_name}'")
                return number
                
        return None

    def save_contact(self, name: str, number: str) -> bool:
        """Saves a new contact to the phone address book."""
        if not self.is_device_connected():
            return False

        success, _ = self._run_adb_cmd([
            "shell", "am", "start", "-a", "android.intent.action.INSERT",
            "-t", "vnd.android.cursor.dir/contact",
            "-e", "name", name,
            "-e", "phone", number
        ])
        return success

    def launch_app_on_phone(self, app_name: str) -> str:
        """Finds and launches a third-party application on the phone by matching packages."""
        if not self.is_device_connected():
            return "Please connect your mobile device, sir."

        # Fetch installed packages
        success, output = self._run_adb_cmd(["shell", "pm", "list", "packages", "-3"])
        if not success:
            return "Failed to query applications on your mobile device, sir."

        app_clean = app_name.lower().replace(" ", "")
        packages = [line.replace("package:", "").strip() for line in output.splitlines() if line.strip()]

        matched_package = None
        for pkg in packages:
            pkg_simple = pkg.split(".")[-1]
            pkg_full_clean = pkg.replace(".", "").lower()
            
            if app_clean in pkg_simple or app_clean in pkg_full_clean or pkg_simple in app_clean:
                matched_package = pkg
                break

        if matched_package:
            # Launch via monkey tool
            success_launch, _ = self._run_adb_cmd([
                "shell", "monkey", "-p", matched_package, "1"
            ])
            if success_launch:
                return f"Launching {app_name} on your phone, sir."
            return f"Located application {matched_package} but launch request failed."
        
        return f"I could not find an application matching {app_name} installed on your mobile, sir."

    # --- Component 7: Android ADB-based System Controls ---

    def go_home(self) -> str:
        """Navigates to the phone's home screen."""
        if not self.is_device_connected():
            return "Please connect your Android device, sir."
        self._run_adb_cmd(["shell", "input", "keyevent", "3"])
        return "Instantly returning to the home screen, sir."

    def set_flashlight(self, state: bool) -> str:
        """Turns the device flashlight on or off."""
        if not self.is_device_connected():
            return "Please connect your Android device, sir."
        mode = "on" if state else "off"
        success, _ = self._run_adb_cmd(["shell", "cmd", "flashlight", mode])
        if success:
            self.flashlight_on = state
            return f"Flashlight turned {mode} instantly, sir."
        return f"I failed to turn the flashlight {mode}, sir."

    def toggle_flashlight(self) -> str:
        """Toggles the flashlight state."""
        return self.set_flashlight(not self.flashlight_on)

    def open_camera(self) -> str:
        """Launches the camera app immediately."""
        if not self.is_device_connected():
            return "Please connect your Android device, sir."
        success, _ = self._run_adb_cmd(["shell", "am", "start", "-a", "android.media.action.STILL_IMAGE_CAMERA"])
        if success:
            return "Camera launched immediately, sir."
        return "Failed to open camera on your device, sir."

    def click_shutter(self) -> str:
        """Simulates clicking the camera shutter button when the camera is open."""
        if not self.is_device_connected():
            return "Please connect your Android device, sir."
        self._run_adb_cmd(["shell", "input", "keyevent", "27"])
        return "Clicking camera shutter, sir."

    def flip_camera(self) -> str:
        """Simulates camera flip shortcut button (keycode 98)."""
        if not self.is_device_connected():
            return "Please connect your Android device, sir."
        self._run_adb_cmd(["shell", "input", "keyevent", "98"])
        return "Flipping camera feed, sir."

    def take_photo_handsfree(self) -> str:
        """Launches camera app and takes a photo automatically after a small delay."""
        if not self.is_device_connected():
            return "Please connect your Android device, sir."
        self.open_camera()
        time.sleep(2.5)
        self.click_shutter()
        return "Photo captured hands-free, sir."

    def capture_screen_for_analysis(self) -> str:
        """Captures a screenshot of the phone screen and pulls it to the local configuration directory."""
        if not self.is_device_connected():
            return "Error: Device not connected"
        self._run_adb_cmd(["shell", "screencap", "-p", "/sdcard/jarvis_screencap.png"])
        local_dir = os.path.abspath("./config")
        os.makedirs(local_dir, exist_ok=True)
        local_path = os.path.join(local_dir, "jarvis_screencap.png")
        success, _ = self._run_adb_cmd(["pull", "/sdcard/jarvis_screencap.png", local_path])
        self._run_adb_cmd(["shell", "rm", "/sdcard/jarvis_screencap.png"])
        return local_path if success else "Error: Failed to pull image"

    def capture_camera_for_analysis(self) -> str:
        """Takes a photo on the phone, pulls it to local PC cache, and returns path."""
        if not self.is_device_connected():
            return "Error: Device not connected"
        self.open_camera()
        time.sleep(2.5)
        self.click_shutter()
        time.sleep(2.0)
        self.go_home()
        success, ls_out = self._run_adb_cmd(["shell", "ls", "-t", "/sdcard/DCIM/Camera"])
        if success and ls_out.strip():
            latest = ls_out.splitlines()[0].strip()
            phone_path = f"/sdcard/DCIM/Camera/{latest}"
            local_dir = os.path.abspath("./config")
            local_path = os.path.join(local_dir, "jarvis_camcap.jpg")
            success_pull, _ = self._run_adb_cmd(["pull", phone_path, local_path])
            if success_pull:
                return local_path
        return "Error: Failed to capture camera image"

    def adjust_volume(self, direction: str) -> str:
        """Increases or decreases volume smoothly."""
        if not self.is_device_connected():
            return "Please connect your Android device, sir."
        keycode = "24" if direction.lower() == "up" else "25"
        for _ in range(3):
            self._run_adb_cmd(["shell", "input", "keyevent", keycode])
            time.sleep(0.1)
        return f"Volume adjusted {direction} smoothly, sir."

    def set_volume_level(self, percent: int) -> str:
        """Sets music stream volume to a specific percentage (mapped to 0-15 index)."""
        if not self.is_device_connected():
            return "Please connect your Android device, sir."
        index = int(percent * 15 / 100)
        success, _ = self._run_adb_cmd(["shell", "media", "volume", "--stream", "3", "--set", str(index)])
        if success:
            return f"Volume level set to {percent} percent, sir."
        return "Failed to set volume level, sir."

    def mute_unmute(self, mute: bool) -> str:
        """Mutes or restores the volume level."""
        if not self.is_device_connected():
            return "Please connect your Android device, sir."
        if mute:
            success, output = self._run_adb_cmd(["shell", "media", "volume", "--stream", "3", "--get"])
            if success:
                match = re.search(r"volume is\s+(\d+)", output)
                if match:
                    self.cached_volume = int(match.group(1))
            self._run_adb_cmd(["shell", "media", "volume", "--stream", "3", "--set", "0"])
            return "Media sound muted, sir."
        else:
            self._run_adb_cmd(["shell", "media", "volume", "--stream", "3", "--set", str(self.cached_volume)])
            return "Media sound restored, sir."

    def set_sound_profile(self, profile: str) -> str:
        """Sets the sound profile (silent, vibrate, normal)."""
        if not self.is_device_connected():
            return "Please connect your Android device, sir."
        prof = profile.lower()
        if prof == "silent":
            mode = "0"
        elif prof == "vibrate":
            mode = "1"
        else:
            mode = "2"
        success, _ = self._run_adb_cmd(["shell", "cmd", "audio", "set-ringer-mode", mode])
        if success:
            return f"Sound profile switched to {prof} mode, sir."
        return f"Failed to switch sound profile to {prof}, sir."

    def get_volume_status(self) -> str:
        """Gets current volume percentage."""
        if not self.is_device_connected():
            return "Please connect your Android device, sir."
        success, output = self._run_adb_cmd(["shell", "media", "volume", "--stream", "3", "--get"])
        if success:
            match = re.search(r"volume is\s+(\d+)", output)
            if match:
                vol = int(match.group(1))
                pct = int(vol * 100 / 15)
                return f"Current music volume level is {pct} percent, sir."
        return "Unable to determine volume level status, sir."

    def adjust_brightness(self, direction: str) -> str:
        """Smoothly increases or decreases screen brightness."""
        if not self.is_device_connected():
            return "Please connect your Android device, sir."
        success, output = self._run_adb_cmd(["shell", "settings", "get", "system", "screen_brightness"])
        if success:
            try:
                curr = int(output.strip())
                offset = 35 if direction.lower() == "up" else -35
                target = max(0, min(255, curr + offset))
                self._run_adb_cmd(["shell", "settings", "put", "system", "screen_brightness", str(target)])
                return f"Adjusting screen brightness {direction}, sir."
            except ValueError:
                pass
        return "Failed to adjust brightness level, sir."

    def set_brightness_level(self, percent: int) -> str:
        """Sets system screen brightness to a percentage (mapped to 0-255)."""
        if not self.is_device_connected():
            return "Please connect your Android device, sir."
        val = int(percent * 255 / 100)
        success, _ = self._run_adb_cmd(["shell", "settings", "put", "system", "screen_brightness", str(val)])
        if success:
            return f"Brightness set to {percent} percent, sir."
        return "Failed to set screen brightness level, sir."

    def set_brightness_max_min(self, max_brightness: bool) -> str:
        """Sets brightness to absolute max or min instantly."""
        level = 100 if max_brightness else 0
        return self.set_brightness_level(level)

    def set_auto_brightness(self, enable: bool) -> str:
        """Enables or disables automatic system brightness."""
        if not self.is_device_connected():
            return "Please connect your Android device, sir."
        val = "1" if enable else "0"
        success, _ = self._run_adb_cmd(["shell", "settings", "put", "system", "screen_brightness_mode", val])
        if success:
            state = "enabled" if enable else "disabled"
            return f"Automatic brightness adjustment {state}, sir."
        return "Failed to configure auto brightness mode, sir."

    def get_brightness_status(self) -> str:
        """Checks current screen brightness percentage."""
        if not self.is_device_connected():
            return "Please connect your Android device, sir."
        success, output = self._run_adb_cmd(["shell", "settings", "get", "system", "screen_brightness"])
        if success:
            try:
                val = int(output.strip())
                pct = int(val * 100 / 255)
                return f"Your screen brightness is currently at {pct} percent, sir."
            except ValueError:
                pass
        return "Failed to retrieve screen brightness status, sir."

    def set_smart_reminder(self, message: str, time_str: str) -> str:
        """Parses natural language time and dispatches SET_ALARM intent."""
        if not self.is_device_connected():
            return "Please connect your Android device, sir."
        hour = 8
        minute = 0
        
        match = re.search(r"(\d+):(\d+)\s*(am|pm)?", time_str.lower())
        if match:
            hour = int(match.group(1))
            minute = int(match.group(2))
            ampm = match.group(3)
            if ampm == "pm" and hour < 12:
                hour += 12
            elif ampm == "am" and hour == 12:
                hour = 0
        else:
            min_match = re.search(r"in\s+(\d+)\s*min", time_str.lower())
            if min_match:
                offset = int(min_match.group(1))
                t = time.localtime(time.time() + offset * 60)
                hour, minute = t.tm_hour, t.tm_min
            else:
                return f"Could not resolve scheduling time '{time_str}', sir."

        success, _ = self._run_adb_cmd([
            "shell", "am", "start", "-a", "android.intent.action.SET_ALARM",
            "--ei", "android.intent.extra.alarm.HOUR", str(hour),
            "--ei", "android.intent.extra.alarm.MINUTES", str(minute),
            "--es", "android.intent.extra.alarm.MESSAGE", message,
            "--ez", "android.intent.extra.alarm.SKIP_ROUND_SHOW", "true"
        ])
        if success:
            self.last_reminder = {"message": message, "hour": hour, "minute": minute}
            return f"Smart reminder set for {hour:02d}:{minute:02d} with message: '{message}', sir."
        return "Failed to dispatch reminder alarm request, sir."

    def dismiss_last_reminder(self) -> str:
        """Dismisses the last configured alarm/reminder via DISMISS_ALARM intent."""
        if not self.is_device_connected():
            return "Please connect your Android device, sir."
        if not self.last_reminder:
            return "I could not find a record of a previously configured reminder in my memory, sir."
            
        message = self.last_reminder["message"]
        hour = self.last_reminder["hour"]
        minute = self.last_reminder["minute"]
        
        # 1. Dismiss by label
        self._run_adb_cmd([
            "shell", "am", "start", "-a", "android.intent.action.DISMISS_ALARM",
            "--es", "android.intent.extra.alarm.SEARCH_MODE", "android.label",
            "--es", "android.intent.extra.alarm.LABEL", message,
            "--ez", "android.intent.extra.alarm.SKIP_ROUND_SHOW", "true"
        ])
        
        # 2. Dismiss by time
        self._run_adb_cmd([
            "shell", "am", "start", "-a", "android.intent.action.DISMISS_ALARM",
            "--es", "android.intent.extra.alarm.SEARCH_MODE", "android.time",
            "--ei", "android.intent.extra.alarm.HOUR", str(hour),
            "--ei", "android.intent.extra.alarm.MINUTES", str(minute),
            "--ez", "android.intent.extra.alarm.SKIP_ROUND_SHOW", "true"
        ])
        
        self.last_reminder = None
        return f"Dismissed the previous alarm for {hour:02d}:{minute:02d} ('{message}'), sir."

    def get_device_time_date(self) -> str:
        """Gets device local time and date details combined."""
        if not self.is_device_connected():
            return "Please connect your Android device, sir."
        success, output = self._run_adb_cmd(["shell", "date"])
        if success:
            return f"Mobile device reports: {output}, sir."
        return "Failed to query system date on mobile device, sir."

    def get_battery_status(self) -> str:
        """Checks battery percentage and charging status."""
        if not self.is_device_connected():
            return "Please connect your Android device, sir."
        success, output = self._run_adb_cmd(["shell", "dumpsys", "battery"])
        if success:
            level = re.search(r"level:\s+(\d+)", output)
            charging = re.search(r"status:\s+(\d+)", output)
            lvl_val = level.group(1) if level else "Unknown"
            
            # Status: 2 = charging, 5 = full
            is_charging = "charging" if charging and charging.group(1) in ["2", "5"] else "discharging"
            return f"Phone battery is at {lvl_val} percent and is currently {is_charging}, sir."
        return "Failed to fetch battery telemetry, sir."

    def get_local_weather(self, location: str = "") -> str:
        """Opens Google search weather query inside default mobile browser."""
        if not self.is_device_connected():
            return "Please connect your Android device, sir."
        q = location or "my location"
        url = f"https://www.google.com/search?q=weather+{urllib.parse.quote(q)}"
        success, _ = self._run_adb_cmd(["shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", url])
        if success:
            return f"Opening local weather for {q} on your mobile, sir."
        return "Failed to display weather info, sir."

    def get_current_location(self) -> str:
        """Launches map intent centered on device GPS coordinates."""
        if not self.is_device_connected():
            return "Please connect your Android device, sir."
        success, _ = self._run_adb_cmd(["shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", "geo:0,0?q=my+location"])
        if success:
            return "Acquiring coordinates. Opening location map on device, sir."
        return "Failed to resolve current location, sir."

    def send_sms(self, phone: str, message: str) -> str:
        """Compose and preload text message draft."""
        if not self.is_device_connected():
            return "Please connect your Android device, sir."
        
        # Fuzzy resolve name if not a number
        phone_num = phone
        if any(c.isalpha() for c in phone):
            resolved = self.get_contact_by_name(phone)
            if resolved:
                phone_num = resolved
            else:
                return f"Could not locate a contact matching name {phone}, sir."
                
        success, _ = self._run_adb_cmd([
            "shell", "am", "start", "-a", "android.intent.action.SENDTO",
            "-d", f"sms:{phone_num}",
            "--es", "sms_body", message
        ])
        if success:
            return f"SMS draft prepared for {phone} with message content, sir."
        return "Failed to open SMS composer, sir."

    def send_whatsapp_message_adb(self, phone: str, message: str) -> str:
        """Send fully autonomous WhatsApp messages."""
        if not self.is_device_connected():
            return "Please connect your Android device, sir."

        phone_num = phone
        if any(c.isalpha() for c in phone):
            resolved = self.get_contact_by_name(phone)
            if resolved:
                phone_num = resolved
            else:
                return f"Could not find a WhatsApp contact named {phone}, sir."

        clean_phone = "".join(c for c in phone_num if c.isdigit())
        if len(clean_phone) == 10:
            clean_phone = "91" + clean_phone  # Add India prefix as default fallback

        encoded_msg = urllib.parse.quote(message)
        url = f"https://api.whatsapp.com/send?phone={clean_phone}&text={encoded_msg}"
        self._run_adb_cmd(["shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", url])
        
        # Give WhatsApp 3 seconds to render UI
        time.sleep(3.0)
        # Send keyevent sequence to press send button
        self._run_adb_cmd(["shell", "input", "keyevent", "22"])  # Dpad Right
        time.sleep(0.3)
        self._run_adb_cmd(["shell", "input", "keyevent", "22"])  # Dpad Right
        time.sleep(0.3)
        self._run_adb_cmd(["shell", "input", "keyevent", "66"])  # Enter
        return f"Autonomous WhatsApp dispatch trigger fired for {phone_num}, sir."

    def start_navigation(self, query: str) -> str:
        """Starts turn-by-turn directions to a place."""
        if not self.is_device_connected():
            return "Please connect your Android device, sir."
        url = f"google.navigation:q={urllib.parse.quote(query)}"
        success, _ = self._run_adb_cmd(["shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", url])
        if success:
            return f"Starting turn-by-turn navigation to {query}, sir."
        return "Failed to launch maps navigation, sir."

    def view_on_map(self, query: str) -> str:
        """Locates specific address on map."""
        if not self.is_device_connected():
            return "Please connect your Android device, sir."
        url = f"geo:0,0?q={urllib.parse.quote(query)}"
        success, _ = self._run_adb_cmd(["shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", url])
        if success:
            return f"Displaying {query} on your maps viewport, sir."
        return "Failed to locate place on map, sir."

    def find_nearby_places(self, query: str) -> str:
        """Finds nearby places (ATMs, restaurants, etc.)."""
        return self.view_on_map(f"nearby {query}")

    def lock_phone(self) -> str:
        """Turns off screen and locks phone (KEYCODE_SLEEP = 223)."""
        if not self.is_device_connected():
            return "Please connect your Android device, sir."
        self._run_adb_cmd(["shell", "input", "keyevent", "223"])
        return "Locking device screen immediately, sir."

    def open_power_menu(self) -> str:
        """Opens secure system power menu."""
        if not self.is_device_connected():
            return "Please connect your Android device, sir."
        self._run_adb_cmd(["shell", "input", "keyevent", "--longpress", "26"])
        return "Opening Android system power settings overlay, sir."

    def play_spotify_track(self, query: str) -> str:
        """Plays specific song query directly on Spotify."""
        if not self.is_device_connected():
            return "Please connect your Android device, sir."
        success, _ = self._run_adb_cmd([
            "shell", "am", "start", "-a", "android.media.action.MEDIA_PLAY_FROM_SEARCH",
            "-e", "query", query
        ])
        if success:
            return f"Searching and playing '{query}' on phone Spotify, sir."
        return "Failed to trigger Spotify search intent, sir."

    def resume_playback(self) -> str:
        """Resumes active playing media."""
        if not self.is_device_connected():
            return "Please connect your Android device, sir."
        self._run_adb_cmd(["shell", "input", "keyevent", "126"])  # KEYCODE_MEDIA_PLAY
        return "Resuming music playback on your mobile, sir."

    def toggle_network(self, interface: str, enable: bool) -> str:
        """Turns WiFi, Bluetooth, or Mobile Data on and off."""
        if not self.is_device_connected():
            return "Please connect your Android device, sir."
        action = "enable" if enable else "disable"
        if interface.lower() == "wifi":
            success, _ = self._run_adb_cmd(["shell", "svc", "wifi", action])
        elif interface.lower() == "bluetooth":
            success, _ = self._run_adb_cmd(["shell", "svc", "bluetooth", action])
        else:
            success, _ = self._run_adb_cmd(["shell", "svc", "data", action])
            
        if success:
            return f"Interface {interface} has been {action}d successfully, sir."
        return f"Failed to modify connectivity interface {interface}, sir."

    def toggle_airplane_mode(self, enable: bool) -> str:
        """Toggles device airplane mode state."""
        if not self.is_device_connected():
            return "Please connect your Android device, sir."
        val = "1" if enable else "0"
        state = "true" if enable else "false"
        self._run_adb_cmd(["shell", "settings", "put", "global", "airplane_mode_on", val])
        success, _ = self._run_adb_cmd([
            "shell", "am", "broadcast", "-a", "android.intent.action.AIRPLANE_MODE",
            "--ez", "state", state
        ])
        if success:
            return f"Airplane mode {'activated' if enable else 'deactivated'} successfully, sir."
        return "Failed to dispatch airplane mode broadcast, sir."

    def whatsapp_call_adb(self, name_or_number: str, video: bool = False) -> str:
        """Queries database row ID for WhatsApp contacts and initiates VoIP audio or video calls."""
        if not self.is_device_connected():
            return "Please connect your Android device, sir."

        mimetype = (
            "vnd.android.cursor.item/vnd.com.whatsapp.video.call"
            if video
            else "vnd.android.cursor.item/vnd.com.whatsapp.voip.call"
        )
        call_type = "video" if video else "voice"

        # Content query contacts data provider
        success, output = self._run_adb_cmd([
            "shell", "content", "query", "--uri", "content://com.android.contacts/data",
            "--projection", "_id:display_name:data1:mimetype"
        ])
        
        if not success or not output:
            return "I could not access your device contacts database, sir."

        row_id = None
        matched_display_name = None
        search_query = name_or_number.lower().strip()

        # Parse row records in Python for safety
        for line in output.splitlines():
            if mimetype not in line:
                continue
            
            id_match = re.search(r"_id=(\d+)", line)
            name_match = re.search(r"display_name=([^,\n]+)", line)
            data1_match = re.search(r"data1=([^,\n]+)", line)

            if id_match:
                curr_id = id_match.group(1)
                curr_name = name_match.group(1).strip() if name_match else ""
                curr_num = data1_match.group(1).strip() if data1_match else ""
                
                curr_name_lower = curr_name.lower()
                clean_curr_num = re.sub(r"\D", "", curr_num)
                clean_search_num = re.sub(r"\D", "", search_query)
                
                if (search_query in curr_name_lower) or (clean_search_num and clean_search_num in clean_curr_num):
                    row_id = curr_id
                    matched_display_name = curr_name
                    break

        if row_id:
            success_launch, err = self._run_adb_cmd([
                "shell", "am", "start", "-a", "android.intent.action.VIEW",
                "-t", mimetype, "-d", f"content://com.android.contacts/data/{row_id}"
            ])
            if success_launch:
                return f"Initiating WhatsApp {call_type} call to {matched_display_name}, sir."
            return f"Found contact but failed to start WhatsApp VoIP intent: {err}"
            
        return f"I could not locate a WhatsApp contact matching '{name_or_number}' in your address book, sir."

    def get_connected_devices(self) -> list[str]:
        """Returns a list of all currently connected device identifiers."""
        success, output = self._run_adb_cmd(["devices"])
        if not success:
            return []
        devices = []
        for line in output.splitlines()[1:]:
            if line.strip() and "device" in line and "emulator" not in line:
                parts = line.split()
                if parts:
                    devices.append(parts[0])
        return devices

    def get_usb_device(self, devices: list[str]) -> str | None:
        """Finds the device identifier that corresponds to a USB connection."""
        for d in devices:
            if ":" not in d:
                return d
        return None

    def setup_wireless_adb(self, usb_device: str) -> str | None:
        """Fetches USB device IP, sets tcpip 5555, and connects wirelessly."""
        ip = None
        success, out = self._run_adb_cmd(["-s", usb_device, "shell", "ip", "route"])
        if success:
            match = re.search(r"src\s+([0-9.]+)", out)
            if match:
                ip = match.group(1)
        
        if not ip:
            success, out = self._run_adb_cmd(["-s", usb_device, "shell", "ip", "addr", "show", "wlan0"])
            if success:
                match = re.search(r"inet\s+([0-9.]+)", out)
                if match:
                    ip = match.group(1)
                    
        if not ip:
            logger.warning("Could not extract local IP address from Android device.")
            return None
            
        logger.info(f"Android USB device IP found: {ip}")
        
        success, out = self._run_adb_cmd(["-s", usb_device, "tcpip", "5555"])
        if not success:
            logger.warning(f"Failed to set adb tcpip 5555: {out}")
            return None
            
        time.sleep(1.5)
        
        success_conn, out_conn = self._run_adb_cmd(["connect", f"{ip}:5555"])
        if success_conn:
            logger.info(f"Successfully bridged wireless ADB to {ip}:5555")
            self._save_cached_ip(ip)
            return ip
        return None

    def _save_cached_ip(self, ip: str):
        config_path = os.path.abspath("./auth/.adb_wireless_config")
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        try:
            with open(config_path, "w") as f:
                f.write(ip)
        except Exception as e:
            logger.error(f"Failed to save cached IP: {e}")

    def _get_cached_ip(self) -> str | None:
        config_path = os.path.abspath("./auth/.adb_wireless_config")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    return f.read().strip()
            except Exception:
                pass
        return None

    def _get_local_subnet_ips(self) -> list[str]:
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            
            parts = local_ip.split(".")
            if len(parts) == 4:
                prefix = ".".join(parts[:3])
                return [f"{prefix}.{i}" for i in range(1, 255) if f"{prefix}.{i}" != local_ip]
        except Exception as e:
            logger.error(f"Failed to get local subnet prefix: {e}")
        return []

    def _check_port_5555(self, ip: str) -> str | None:
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.2)
            result = s.connect_ex((ip, 5555))
            s.close()
            if result == 0:
                return ip
        except Exception:
            pass
        return None

    def discover_wireless_device(self) -> str | None:
        """Scans local subnet for active port 5555 listeners."""
        ips = self._get_local_subnet_ips()
        if not ips:
            return None
            
        logger.info("Scanning subnet for ADB wireless listeners on port 5555...")
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
            results = executor.map(self._check_port_5555, ips)
            for res in results:
                if res:
                    logger.info(f"Discovered ADB listener at {res}")
                    return res
        return None

    def auto_bridge_wireless(self):
        """Background thread that establishes/re-establishes wireless ADB bridge."""
        logger.info("Starting ADB wireless auto-bridge monitor...")
        time.sleep(3.0)
        
        while True:
            try:
                devices = self.get_connected_devices()
                usb_device = self.get_usb_device(devices)
                
                if usb_device:
                    has_wireless = any(":5555" in d for d in devices)
                    if not has_wireless:
                        logger.info("USB device detected. Configuring wireless bridge...")
                        self.setup_wireless_adb(usb_device)
                else:
                    has_wireless = any(":5555" in d for d in devices)
                    if not has_wireless:
                        cached_ip = self._get_cached_ip()
                        connected = False
                        if cached_ip:
                            logger.info(f"No USB device found. Attempting connection to cached IP: {cached_ip}")
                            success, _ = self._run_adb_cmd(["connect", f"{cached_ip}:5555"])
                            if success:
                                time.sleep(1.5)
                                devices_now = self.get_connected_devices()
                                if any(cached_ip in d for d in devices_now):
                                    logger.info("Successfully connected wirelessly to cached IP.")
                                    connected = True
                                    
                        if not connected:
                            discovered_ip = self.discover_wireless_device()
                            if discovered_ip:
                                logger.info(f"Connecting to discovered device IP: {discovered_ip}")
                                success, _ = self._run_adb_cmd(["connect", f"{discovered_ip}:5555"])
                                if success:
                                    self._save_cached_ip(discovered_ip)
            except Exception as e:
                logger.error(f"Error in ADB wireless auto-bridge: {e}")
                
            time.sleep(15.0)




if __name__ == "__main__":
    print("Testing Phone Controller...")
    ctrl = PhoneController()
    connected = ctrl.is_device_connected()
    print(f"Device Connected: {connected}")
    if connected:
        print("\nAll Contacts:")
        contacts = ctrl._fetch_all_contacts()
        for name, num in list(contacts.items())[:5]:
            print(f" -> {name}: {num}")
            
        print("\nChecking Call State:")
        print(ctrl.check_call_state())
