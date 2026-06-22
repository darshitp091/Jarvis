import ollama
import json
import yaml
import os
from loguru import logger


class IntentRouter:
    """Routes user speech to correct skill using the main LLM (e.g., qwen2.5)"""

    def __init__(self, config_path: str = "config"):
        # Resolve config path gracefully based on current working directory
        if not os.path.exists(config_path):
            fallback = os.path.join(os.path.dirname(__file__), "..", config_path)
            if os.path.exists(fallback):
                config_path = fallback

        try:
            with open(os.path.join(config_path, "settings.yaml")) as f:
                self.settings = yaml.safe_load(f)
            with open(os.path.join(config_path, "prompts.yaml")) as f:
                self.prompts = yaml.safe_load(f)

            self.main_model = self.settings["models"]["main_brain"]
            self.filler_model = self.settings["models"]["filler"]
        except Exception as e:
            logger.error(f"Failed to load configurations in IntentRouter: {e}")
            # Fallbacks in case config is missing during a pure unit test
            self.main_model = "qwen2.5"
            self.filler_model = "gemma2:2b"
            self.prompts = {"system_prompts": {"intent_router": "Return JSON", "filler": "Respond with one short sentence."}}

    def _regex_route(self, text: str) -> dict | None:
        """Fast regex pre-parser to bypass LLM latency/errors for critical commands"""
        import re
        cmd = text.lower().strip()

        # 13. Mobile phone / ADB Controls (Placed at top to prevent desktop skill trigger conflicts)
        # Navigation & Basic
        if any(p in cmd for p in ["go home on phone", "phone home screen", "return to home screen on phone"]):
            return {"skill": "phone", "params": {"action": "go_home"}, "domain": "general"}
        if any(p in cmd for p in ["turn on flashlight", "enable flashlight", "turn flashlight on", "phone flashlight on"]):
            return {"skill": "phone", "params": {"action": "flashlight", "state": True}, "domain": "general"}
        if any(p in cmd for p in ["turn off flashlight", "disable flashlight", "turn flashlight off", "phone flashlight off"]):
            return {"skill": "phone", "params": {"action": "flashlight", "state": False}, "domain": "general"}
        if any(p in cmd for p in ["toggle flashlight", "toggle phone flashlight"]):
            return {"skill": "phone", "params": {"action": "flashlight", "toggle": True}, "domain": "general"}

        # Volume Controls
        if any(p in cmd for p in ["increase phone volume", "phone volume up", "volume up on phone", "raise phone volume"]):
            return {"skill": "phone", "params": {"action": "volume", "vol_action": "adjust", "direction": "up"}, "domain": "general"}
        if any(p in cmd for p in ["decrease phone volume", "phone volume down", "volume down on phone", "lower phone volume"]):
            return {"skill": "phone", "params": {"action": "volume", "vol_action": "adjust", "direction": "down"}, "domain": "general"}
        if any(p in cmd for p in ["mute phone", "silence phone audio", "mute phone volume"]):
            return {"skill": "phone", "params": {"action": "volume", "vol_action": "mute", "mute": True}, "domain": "general"}
        if any(p in cmd for p in ["unmute phone", "restore phone volume"]):
            return {"skill": "phone", "params": {"action": "volume", "vol_action": "mute", "mute": False}, "domain": "general"}
        if any(p in cmd for p in ["set phone volume to max", "phone max volume", "phone volume 100"]):
            return {"skill": "phone", "params": {"action": "volume", "vol_action": "set_level", "percent": 100}, "domain": "general"}
        vol_pct_match = re.search(r"(?:set|change)\s+phone\s+volume\s+(?:to\s+)?(\d+)", cmd)
        if vol_pct_match:
            return {"skill": "phone", "params": {"action": "volume", "vol_action": "set_level", "percent": int(vol_pct_match.group(1))}, "domain": "general"}
        sound_prof_match = re.search(r"phone\s+(?:sound\s+)?profile\s+(?:to\s+)?(silent|vibrate|normal)", cmd)
        if sound_prof_match:
            return {"skill": "phone", "params": {"action": "volume", "vol_action": "profile", "profile": sound_prof_match.group(1)}, "domain": "general"}
        if any(p in cmd for p in ["phone volume status", "check phone volume", "get phone volume"]):
            return {"skill": "phone", "params": {"action": "volume", "vol_action": "status"}, "domain": "general"}

        # Brightness Controls
        if any(p in cmd for p in ["increase phone brightness", "phone brightness up", "brightness up on phone", "brighten phone screen"]):
            return {"skill": "phone", "params": {"action": "brightness", "bright_action": "adjust", "direction": "up"}, "domain": "general"}
        if any(p in cmd for p in ["decrease phone brightness", "phone brightness down", "brightness down on phone", "dim phone screen"]):
            return {"skill": "phone", "params": {"action": "brightness", "bright_action": "adjust", "direction": "down"}, "domain": "general"}
        if any(p in cmd for p in ["set phone brightness to max", "phone max brightness", "phone brightness 100"]):
            return {"skill": "phone", "params": {"action": "brightness", "bright_action": "max_min", "max": True}, "domain": "general"}
        if any(p in cmd for p in ["set phone brightness to min", "phone min brightness", "phone brightness 0"]):
            return {"skill": "phone", "params": {"action": "brightness", "bright_action": "max_min", "max": False}, "domain": "general"}
        bright_pct_match = re.search(r"(?:set|change)\s+phone\s+brightness\s+(?:to\s+)?(\d+)", cmd)
        if bright_pct_match:
            return {"skill": "phone", "params": {"action": "brightness", "bright_action": "set_level", "percent": int(bright_pct_match.group(1))}, "domain": "general"}
        if any(p in cmd for p in ["enable auto brightness on phone", "turn on auto brightness on phone", "phone auto brightness on"]):
            return {"skill": "phone", "params": {"action": "brightness", "bright_action": "auto", "enable": True}, "domain": "general"}
        if any(p in cmd for p in ["disable auto brightness on phone", "turn off auto brightness on phone", "phone auto brightness off"]):
            return {"skill": "phone", "params": {"action": "brightness", "bright_action": "auto", "enable": False}, "domain": "general"}
        if any(p in cmd for p in ["phone brightness status", "check phone brightness", "get phone brightness"]):
            return {"skill": "phone", "params": {"action": "brightness", "bright_action": "status"}, "domain": "general"}

        # Camera & Vision
        if any(p in cmd for p in ["open phone camera", "launch phone camera", "open camera on phone"]):
            return {"skill": "phone", "params": {"action": "open_camera"}, "domain": "general"}
        if any(p in cmd for p in ["click shutter on phone", "click phone shutter", "press shutter on phone", "shutter click on phone"]):
            return {"skill": "phone", "params": {"action": "click_shutter"}, "domain": "general"}
        if any(p in cmd for p in ["flip phone camera", "flip camera on phone", "switch phone camera"]):
            return {"skill": "phone", "params": {"action": "flip_camera"}, "domain": "general"}
        if any(p in cmd for p in ["take hands free photo", "take photo hands free", "capture photo hands free"]):
            return {"skill": "phone", "params": {"action": "take_photo_handsfree"}, "domain": "general"}
        if any(p in cmd for p in ["analyze phone screen", "describe phone screen", "what's on my phone screen", "describe my phone screen"]):
            return {"skill": "phone", "params": {"action": "screen_analysis"}, "domain": "general"}
        if any(p in cmd for p in ["analyze surroundings on phone", "phone camera analysis", "describe surroundings on phone", "what does phone camera see"]):
            return {"skill": "phone", "params": {"action": "camera_analysis"}, "domain": "general"}

        # Reminders & System Info
        reminder_match = re.search(r"remind\s+me\s+to\s+(.+?)\s+(?:at|in)\s+(\d+[:\d\s]*(?:am|pm|min|minutes)?)\s*(?:on\s+phone|on\s+mobile)?", cmd)
        if reminder_match:
            return {"skill": "phone", "params": {"action": "reminder", "message": reminder_match.group(1).strip(), "time": reminder_match.group(2).strip()}, "domain": "general"}
        if any(p in cmd for p in ["phone battery status", "check phone battery", "phone battery level", "get phone battery"]):
            return {"skill": "phone", "params": {"action": "system_info", "info_type": "battery"}, "domain": "general"}
        if any(p in cmd for p in ["phone time", "phone date", "check phone time", "get phone date"]):
            return {"skill": "phone", "params": {"action": "system_info", "info_type": "time_date"}, "domain": "general"}
        weather_phone_match = re.search(r"weather(?:\s+for\s+)?(.+)?\s+on\s+(?:phone|mobile)", cmd)
        if weather_phone_match:
            loc = weather_phone_match.group(1).strip() if weather_phone_match.group(1) else ""
            return {"skill": "phone", "params": {"action": "system_info", "info_type": "weather", "location": loc}, "domain": "general"}
        if any(p in cmd for p in ["phone location", "current location on phone", "get phone location"]):
            return {"skill": "phone", "params": {"action": "system_info", "info_type": "location"}, "domain": "general"}

        # SMS & WhatsApp Calling / Messaging
        sms_match = re.search(r"^(?:send\s+)?(?:sms|text)(?:\s+message)?\s+(?:to\s+)?([a-zA-Z0-9\s\-]+?)(?:\s+|:)(.+)", cmd)
        if sms_match:
            return {"skill": "phone", "params": {"action": "sms", "phone": sms_match.group(1).strip(), "message": sms_match.group(2).strip()}, "domain": "general"}
        wa_adb_match = re.search(r"^send\s+whatsapp\s+(?:message\s+)?(?:on\s+phone|on\s+mobile)\s+(?:to\s+)?([a-zA-Z0-9\s\-]+?)(?:\s+|:)(.+)", cmd)
        if wa_adb_match:
            return {"skill": "phone", "params": {"action": "whatsapp_message", "contact": wa_adb_match.group(1).strip(), "message": wa_adb_match.group(2).strip()}, "domain": "general"}
        wa_call_match = re.search(r"^whatsapp\s+(?:audio\s+)?call\s+([a-zA-Z0-9\s\-]+)\s+(?:on\s+phone|on\s+mobile)", cmd)
        if wa_call_match:
            return {"skill": "phone", "params": {"action": "whatsapp_call", "name": wa_call_match.group(1).strip(), "video": False}, "domain": "general"}
        wa_video_match = re.search(r"^whatsapp\s+video\s+call\s+([a-zA-Z0-9\s\-]+)\s+(?:on\s+phone|on\s+mobile)", cmd)
        if wa_video_match:
            return {"skill": "phone", "params": {"action": "whatsapp_call", "name": wa_video_match.group(1).strip(), "video": True}, "domain": "general"}

        # Maps & Navigation
        nav_match = re.search(r"navigate\s+to\s+(.+?)\s+(?:on\s+phone|on\s+mobile)", cmd)
        if nav_match:
            return {"skill": "phone", "params": {"action": "navigation", "nav_action": "navigate", "query": nav_match.group(1).strip()}, "domain": "general"}
        map_view_match = re.search(r"(?:view|show)\s+(.+?)\s+(?:on\s+phone\s+map|on\s+mobile\s+map)", cmd)
        if map_view_match:
            return {"skill": "phone", "params": {"action": "navigation", "nav_action": "view", "query": map_view_match.group(1).strip()}, "domain": "general"}
        nearby_match = re.search(r"find\s+nearby\s+(.+?)\s+(?:on\s+phone|on\s+mobile)", cmd)
        if nearby_match:
            return {"skill": "phone", "params": {"action": "navigation", "nav_action": "nearby", "query": nearby_match.group(1).strip()}, "domain": "general"}

        # Lock & Power
        if any(p in cmd for p in ["lock phone screen", "lock phone", "lock mobile screen"]):
            return {"skill": "phone", "params": {"action": "lock_power", "lock_action": "lock"}, "domain": "general"}
        if any(p in cmd for p in ["phone power menu", "open phone power menu", "phone power options"]):
            return {"skill": "phone", "params": {"action": "lock_power", "lock_action": "power_menu"}, "domain": "general"}

        # Spotify Playback
        spotify_phone_match = re.search(r"play\s+(.+?)\s+(?:on\s+phone\s+spotify|on\s+mobile\s+spotify)", cmd)
        if spotify_phone_match:
            return {"skill": "phone", "params": {"action": "spotify", "spotify_action": "play", "query": spotify_phone_match.group(1).strip()}, "domain": "general"}
        if any(p in cmd for p in ["resume phone playback", "resume phone music", "resume phone spotify", "resume music on phone"]):
            return {"skill": "phone", "params": {"action": "spotify", "spotify_action": "resume"}, "domain": "general"}

        # Connectivity Toggles
        wifi_phone_match = re.search(r"(?:turn\s+)?(?:wifi|wi-fi)\s+(on|off)\s+(?:on\s+phone|on\s+mobile)", cmd)
        if wifi_phone_match:
            return {"skill": "phone", "params": {"action": "connectivity", "conn_action": "toggle", "interface": "wifi", "enable": wifi_phone_match.group(1) == "on"}, "domain": "general"}
        bt_phone_match = re.search(r"(?:turn\s+)?bluetooth\s+(on|off)\s+(?:on\s+phone|on\s+mobile)", cmd)
        if bt_phone_match:
            return {"skill": "phone", "params": {"action": "connectivity", "conn_action": "toggle", "interface": "bluetooth", "enable": bt_phone_match.group(1) == "on"}, "domain": "general"}
        data_phone_match = re.search(r"(?:turn\s+)?mobile\s+data\s+(on|off)\s+(?:on\s+phone|on\s+mobile)", cmd)
        if data_phone_match:
            return {"skill": "phone", "params": {"action": "connectivity", "conn_action": "toggle", "interface": "data", "enable": data_phone_match.group(1) == "on"}, "domain": "general"}
        ap_phone_match = re.search(r"(?:turn\s+)?airplane\s+mode\s+(on|off)\s+(?:on\s+phone|on\s+mobile)", cmd)
        if ap_phone_match:
            return {"skill": "phone", "params": {"action": "connectivity", "conn_action": "airplane", "enable": ap_phone_match.group(1) == "on"}, "domain": "general"}

        # Legacy Calls and App Launching Matches
        call_save_match = re.match(r"^(?:can you\s+)?(?:call|dial)\s+(\+?[0-9\s\-]+)\s+and\s+save\s+it\s+as\s+([a-zA-Z\s]+)$", cmd)
        if call_save_match:
            return {"skill": "phone", "params": {"action": "call_and_save", "number": call_save_match.group(1).strip(), "name": call_save_match.group(2).strip()}, "domain": "general"}
        save_match = re.match(r"^(?:can you\s+)?save\s+(\+?[0-9\s\-]+)\s+as\s+([a-zA-Z\s]+)$", cmd)
        if save_match:
            return {"skill": "phone", "params": {"action": "save_contact", "number": save_match.group(1).strip(), "name": save_match.group(2).strip()}, "domain": "general"}
        phone_app_match = re.match(r"^(?:can you\s+)?(?:open|launch)\s+(.+?)\s+on\s+(?:my\s+)?(?:phone|mobile)$", cmd)
        if phone_app_match:
            return {"skill": "phone", "params": {"action": "launch_app", "app_name": phone_app_match.group(1).strip()}, "domain": "general"}
        call_num_match = re.match(r"^(?:can you\s+)?(?:call|dial)\s+(\+?[0-9\s\-]+)$", cmd)
        if call_num_match:
            return {"skill": "phone", "params": {"action": "make_call", "number": call_num_match.group(1).strip()}, "domain": "general"}
        call_name_match = re.match(r"^(?:can you\s+)?(?:call|dial)\s+([a-zA-Z\s]+)$", cmd)
        if call_name_match:
            name_val = call_name_match.group(1).strip()
            if name_val not in ["dashboard", "console", "hud", "the laptop", "sentry mode", "screen", "my pc"]:
                return {"skill": "phone", "params": {"action": "make_call", "name": name_val}, "domain": "general"}
        if any(p in cmd for p in ["answer the call", "receive the call", "answer call", "receive call"]):
            return {"skill": "phone", "params": {"action": "answer"}, "domain": "general"}
        if any(p in cmd for p in ["hangup call", "reject call", "end call", "decline call", "hangup the call", "reject the call", "end the call"]):
            return {"skill": "phone", "params": {"action": "hangup"}, "domain": "general"}

        # --- New System and UI Controls ---
        if any(p in cmd for p in ["turn on eye care", "enable eye care", "activate eye care", "turn eye care on"]):
            return {"skill": "os_control", "params": {"action": "toggle_eye_care", "enable": True}, "domain": "general"}
        if any(p in cmd for p in ["turn off eye care", "disable eye care", "deactivate eye care", "turn eye care off"]):
            return {"skill": "os_control", "params": {"action": "toggle_eye_care", "enable": False}, "domain": "general"}

        if any(p in cmd for p in ["show screen ruler", "activate screen ruler", "open screen ruler", "pixel ruler"]):
            return {"skill": "os_control", "params": {"action": "show_screen_ruler"}, "domain": "general"}
        if any(p in cmd for p in ["show snipping tool", "activate snipping tool", "open snipping tool", "take region screenshot", "capture region"]):
            return {"skill": "os_control", "params": {"action": "show_snipping_tool"}, "domain": "general"}

        brightness_match = re.search(r"(?:set|change|adjust)\s+brightness\s+(?:to\s+)?(\d+)", cmd)
        if brightness_match:
            return {"skill": "os_control", "params": {"action": "set_brightness", "percent": int(brightness_match.group(1))}, "domain": "general"}

        if any(p in cmd for p in ["turn on battery saver", "enable battery saver", "activate battery saver"]):
            return {"skill": "os_control", "params": {"action": "toggle_battery_saver", "enable": True}, "domain": "general"}
        if any(p in cmd for p in ["turn off battery saver", "disable battery saver", "deactivate battery saver"]):
            return {"skill": "os_control", "params": {"action": "toggle_battery_saver", "enable": False}, "domain": "general"}

        if any(p in cmd for p in ["disk cleaner", "clean junk files", "clean temp files", "run disk cleanup", "clean temp folders"]):
            return {"skill": "os_control", "params": {"action": "clean_disk"}, "domain": "general"}
        if any(p in cmd for p in ["empty trash", "empty recycle bin", "clean recycle bin"]):
            return {"skill": "os_control", "params": {"action": "empty_recycle_bin"}, "domain": "general"}

        wifi_conn_match = re.search(r"connect to wifi (?:profile\s+)?(.+)", cmd)
        if wifi_conn_match:
            return {"skill": "os_control", "params": {"action": "wifi_control", "wifi_action": "connect", "profile": wifi_conn_match.group(1).strip()}, "domain": "general"}
        if any(p in cmd for p in ["wifi status", "wifi check", "check wifi", "wifi interface"]):
            return {"skill": "os_control", "params": {"action": "wifi_control", "wifi_action": "status"}, "domain": "general"}

        bt_conn_match = re.search(r"connect bluetooth (?:device\s+)?(.+)", cmd)
        if bt_conn_match:
            return {"skill": "os_control", "params": {"action": "bluetooth_control", "bt_action": "connect", "device": bt_conn_match.group(1).strip()}, "domain": "general"}
        if any(p in cmd for p in ["bluetooth status", "bluetooth check", "check bluetooth", "list bluetooth"]):
            return {"skill": "os_control", "params": {"action": "bluetooth_control", "bt_action": "status"}, "domain": "general"}

        if any(p in cmd for p in ["check network speed", "internet speed test", "check my internet speed", "check speed"]):
            return {"skill": "os_control", "params": {"action": "check_network_speed"}, "domain": "general"}

        if any(p in cmd for p in ["mute my mic", "mute microphone", "mute mic"]):
            return {"skill": "os_control", "params": {"action": "toggle_mute_mic", "mute": True}, "domain": "general"}
        if any(p in cmd for p in ["unmute my mic", "unmute microphone", "unmute mic"]):
            return {"skill": "os_control", "params": {"action": "toggle_mute_mic", "mute": False}, "domain": "general"}

        mouse_match = re.search(r"(?:set|change)\s+mouse\s+speed\s+(?:to\s+)?(\d+)", cmd)
        if mouse_match:
            return {"skill": "os_control", "params": {"action": "set_mouse_speed", "speed": int(mouse_match.group(1))}, "domain": "general"}

        kbd_match = re.search(r"(?:set|change)\s+keyboard\s+(?:lights|rgb|led)\s+(?:to\s+)?(#?[a-f0-9]{6})", cmd)
        if kbd_match:
            return {"skill": "os_control", "params": {"action": "set_keyboard_lights", "color_hex": kbd_match.group(1)}, "domain": "general"}

        if any(p in cmd for p in ["sync time", "sync system clock", "synchronize clock", "synchronize pc clock"]):
            return {"skill": "os_control", "params": {"action": "sync_time"}, "domain": "general"}

        if any(p in cmd for p in ["turn on dark mode", "enable dark mode", "activate dark mode", "set dark theme"]):
            return {"skill": "os_control", "params": {"action": "toggle_dark_mode", "dark": True}, "domain": "general"}
        if any(p in cmd for p in ["turn off dark mode", "disable dark mode", "deactivate dark mode", "set light theme"]):
            return {"skill": "os_control", "params": {"action": "toggle_dark_mode", "dark": False}, "domain": "general"}

        printer_add_match = re.search(r"add printer (?:connection\s+)?(.+)", cmd)
        if printer_add_match:
            return {"skill": "os_control", "params": {"action": "printer_setup", "printer_action": "add", "printer": printer_add_match.group(1).strip()}, "domain": "general"}
        if any(p in cmd for p in ["list printers", "printer status", "check printers"]):
            return {"skill": "os_control", "params": {"action": "printer_setup", "printer_action": "list"}, "domain": "general"}

        if any(p in cmd for p in ["enable game mode", "turn on game mode", "boost game mode"]):
            return {"skill": "os_control", "params": {"action": "toggle_game_mode", "enable": True}, "domain": "general"}
        if any(p in cmd for p in ["disable game mode", "turn off game mode"]):
            return {"skill": "os_control", "params": {"action": "toggle_game_mode", "enable": False}, "domain": "general"}

        if any(p in cmd for p in ["run system update", "run winget upgrade", "update my pc"]):
            return {"skill": "os_control", "params": {"action": "run_auto_update"}, "domain": "general"}

        if any(p in cmd for p in ["pin window topmost", "pin active window", "keep window on top"]):
            return {"skill": "os_control", "params": {"action": "pin_window_topmost", "topmost": True}, "domain": "general"}
        if any(p in cmd for p in ["unpin window topmost", "unpin active window"]):
            return {"skill": "os_control", "params": {"action": "pin_window_topmost", "topmost": False}, "domain": "general"}

        wallpaper_match = re.search(r"set wallpaper\s+(?:to\s+)?(.+)", cmd)
        if wallpaper_match:
            return {"skill": "os_control", "params": {"action": "set_wallpaper", "image_path": wallpaper_match.group(1).strip()}, "domain": "general"}
        if any(p in cmd for p in ["hide desktop icons", "hide desktop shortcuts"]):
            return {"skill": "os_control", "params": {"action": "toggle_desktop_icons", "show": False}, "domain": "general"}
        if any(p in cmd for p in ["show desktop icons", "show desktop shortcuts"]):
            return {"skill": "os_control", "params": {"action": "toggle_desktop_icons", "show": True}, "domain": "general"}

        snap_match = re.search(r"snap window (left|right|up|down)", cmd)
        if snap_match:
            return {"skill": "os_control", "params": {"action": "snap_window", "direction": snap_match.group(1)}, "domain": "general"}
        if any(p in cmd for p in ["refresh desktop", "refresh shell"]):
            return {"skill": "os_control", "params": {"action": "refresh_desktop"}, "domain": "general"}
        copy_path_match = re.search(r"copy file path (?:for\s+)?(.+)", cmd)
        if copy_path_match:
            return {"skill": "os_control", "params": {"action": "copy_file_path", "file_path": copy_path_match.group(1).strip()}, "domain": "general"}
        shortcut_match = re.search(r"create shortcut (?:for\s+)?(.+?)\s+at\s+(.+)", cmd)
        if shortcut_match:
            return {"skill": "os_control", "params": {"action": "create_shortcut", "target_path": shortcut_match.group(1).strip(), "shortcut_path": shortcut_match.group(2).strip()}, "domain": "general"}

        # --- Code Runner operations ---
        run_code_match = re.search(r"^(?:run|execute)\s+(python|javascript|js|batch|bat)\s+code\s+(.+)", cmd)
        if run_code_match:
            return {"skill": "code_runner", "params": {"action": "run_code", "language": run_code_match.group(1), "code_text": run_code_match.group(2).strip()}, "domain": "general"}

        git_match = re.search(r"^git\s+(status|commit|push|pull|branch)(?:\s+(.+))?$", cmd)
        if git_match:
            return {"skill": "code_runner", "params": {"action": "git_command", "git_action": git_match.group(1), "args": git_match.group(2) or ""}, "domain": "general"}

        docker_match = re.search(r"^docker\s+(list|ps|start|stop|logs)(?:\s+(.+))?$", cmd)
        if docker_match:
            return {"skill": "code_runner", "params": {"action": "docker_command", "docker_action": docker_match.group(1), "args": docker_match.group(2) or ""}, "domain": "general"}

        mobile_match = re.search(r"^(?:mobile view|mobile emulation|responsive view)\s+(?:for\s+)?(.+)", cmd)
        if mobile_match:
            return {"skill": "code_runner", "params": {"action": "mobile_view_emulation", "url": mobile_match.group(1).strip()}, "domain": "general"}

        deploy_match = re.search(r"^deploy\s+(?:app|project)\s+(?:at\s+)?(.+?)(?:\s+on\s+port\s+(\d+))?$", cmd)
        if deploy_match:
            port_val = int(deploy_match.group(2)) if deploy_match.group(2) else 3000
            return {"skill": "code_runner", "params": {"action": "deploy_app", "project_path": deploy_match.group(1).strip(), "port": port_val}, "domain": "general"}

        # --- File Manager Additions ---
        if any(p in cmd for p in ["show hidden files", "explorer show hidden"]):
            return {"skill": "file_manager", "params": {"action": "toggle_show_hidden_files", "show": True}, "domain": "general"}
        if any(p in cmd for p in ["hide hidden files", "explorer hide hidden"]):
            return {"skill": "file_manager", "params": {"action": "toggle_show_hidden_files", "show": False}, "domain": "general"}

        hide_file_match = re.search(r"^hide file\s+(.+)", cmd)
        if hide_file_match:
            return {"skill": "file_manager", "params": {"action": "set_file_hidden", "path": hide_file_match.group(1).strip(), "hide": True}, "domain": "general"}
        unhide_file_match = re.search(r"^unhide file\s+(.+)", cmd)
        if unhide_file_match:
            return {"skill": "file_manager", "params": {"action": "set_file_hidden", "path": unhide_file_match.group(1).strip(), "hide": False}, "domain": "general"}

        folder_size_match = re.search(r"^(?:folder size|size of folder)\s+(?:for\s+)?(.+)", cmd)
        if folder_size_match:
            return {"skill": "file_manager", "params": {"action": "get_folder_size", "path": folder_size_match.group(1).strip()}, "domain": "general"}

        sync_match = re.search(r"^sync folder\s+(.+?)\s+to\s+(.+)", cmd)
        if sync_match:
            return {"skill": "file_manager", "params": {"action": "sync_folders", "src": sync_match.group(1).strip(), "dst": sync_match.group(2).strip()}, "domain": "general"}

        backup_match = re.search(r"^backup\s+(.+?)\s+to\s+(onedrive|google_drive|google drive)", cmd)
        if backup_match:
            provider = backup_match.group(2).replace(" ", "_").strip()
            return {"skill": "file_manager", "params": {"action": "backup_to_local_cloud", "path": backup_match.group(1).strip(), "cloud_provider": provider}, "domain": "general"}

        # --- Productivity Planner Additions ---
        if cmd.startswith("merge pdf"):
            pdf_merge_match = re.search(r"merge pdf\s+(.+?)\s+to\s+(.+)", cmd)
            if pdf_merge_match:
                files = [f.strip() for f in pdf_merge_match.group(1).split(",")]
                return {"skill": "productivity", "params": {"action": "edit_pdf", "pdf_action": "merge", "files_list": files, "output_path": pdf_merge_match.group(2).strip()}, "domain": "general"}

        rotate_pdf_match = re.search(r"rotate page\s+(\d+)\s+of pdf\s+(.+?)\s+to\s+(.+?)(?:\s+by\s+(\d+))?$", cmd)
        if rotate_pdf_match:
            angle_val = int(rotate_pdf_match.group(4)) if rotate_pdf_match.group(4) else 90
            return {"skill": "productivity", "params": {"action": "edit_pdf", "pdf_action": "rotate", "files_list": [rotate_pdf_match.group(2).strip()], "output_path": rotate_pdf_match.group(3).strip(), "page_num": int(rotate_pdf_match.group(1)), "angle": angle_val}, "domain": "general"}

        ppt_match = re.search(r"^create presentation\s+(?:about|on\s+)?(.+)", cmd)
        if ppt_match:
            return {"skill": "productivity", "params": {"action": "create_presentation", "title": ppt_match.group(1).strip()}, "domain": "general"}

        mind_map_match = re.search(r"^create mind map\s+(?:for|about|on\s+)?(.+)", cmd)
        if mind_map_match:
            return {"skill": "productivity", "params": {"action": "create_mind_map", "central_idea": mind_map_match.group(1).strip()}, "domain": "general"}

        block_sites_match = re.search(r"^block websites\s+(.+)", cmd)
        if block_sites_match:
            domains = [d.strip() for d in block_sites_match.group(1).split(",")]
            return {"skill": "productivity", "params": {"action": "block_distractions", "domains_list": domains, "block": True}, "domain": "general"}
        unblock_sites_match = re.search(r"^unblock websites\s+(.+)", cmd)
        if unblock_sites_match:
            domains = [d.strip() for d in unblock_sites_match.group(1).split(",")]
            return {"skill": "productivity", "params": {"action": "block_distractions", "domains_list": domains, "block": False}, "domain": "general"}

        sign_match = re.search(r"^sign document\s+(.+?)\s+with\s+(.+?)\s+at\s+(.+)", cmd)
        if sign_match:
            return {"skill": "productivity", "params": {"action": "sign_document", "doc_path": sign_match.group(1).strip(), "sig_img_path": sign_match.group(2).strip(), "output_path": sign_match.group(3).strip()}, "domain": "general"}

        # --- Web Research Additions ---
        whatsapp_match = re.search(r"^(?:send\s+)?whatsapp\s+(?:message\s+)?(?:to\s+)?(\+?\d+[\s\-]?\d+[\s\-]?\d+)(?:\s+|:)(.+)", cmd)
        if whatsapp_match:
            return {"skill": "web_research", "params": {"action": "whatsapp_message", "phone": whatsapp_match.group(1).strip(), "message": whatsapp_match.group(2).strip()}, "domain": "general"}

        food_match = re.search(r"^(?:search|find|order)\s+food\s+(?:for\s+)?(.+)", cmd)
        if food_match:
            return {"skill": "web_research", "params": {"action": "search_food", "query": food_match.group(1).strip()}, "domain": "general"}

        track_pkg_match = re.search(r"^track\s+(fedex|ups|usps|dhl)\s+(?:package\s+)?(?:number\s+)?(\S+)", cmd)
        if track_pkg_match:
            return {"skill": "web_research", "params": {"action": "track_package", "carrier": track_pkg_match.group(1), "tracking_number": track_pkg_match.group(2).strip()}, "domain": "general"}

        # 1. Sentry/Secure
        if any(p in cmd for p in ["secure the laptop", "sentry mode", "lock the screen", "lock the laptop", "secure my pc"]):
            return {"skill": "os_control", "params": {"action": "secure"}, "domain": "general"}

        # 2. System Monitor
        if any(p in cmd for p in ["system monitor", "cpu", "ram", "memory usage", "status of the system", "system resources"]):
            return {"skill": "system_monitor", "params": {}, "domain": "general"}

        # 3. Screen Vision
        if any(p in cmd for p in ["screen", "see", "what's on my screen", "describe my screen", "what do you see"]):
            return {"skill": "screen_vision", "params": {}, "domain": "general"}

        # 4. Media Summarization
        youtube_match = re.search(r"(?:summarize|youtube|video)\s+(https?://\S+)", text, re.IGNORECASE)
        if youtube_match:
            return {"skill": "media_summarize", "params": {"url": youtube_match.group(1)}, "domain": "general"}

        # 5. Spotify / Playback Controls
        # Stop / Pause / Resume
        if cmd in ["pause", "pause music", "pause spotify", "stop music", "stop spotify"]:
            return {"skill": "spotify", "params": {"action": "pause"}, "domain": "general"}
        if cmd in ["resume", "resume music", "resume spotify", "play", "play music", "play spotify"]:
            return {"skill": "spotify", "params": {"action": "resume"}, "domain": "general"}
        if any(p in cmd for p in ["next song", "skip song", "next track", "skip track", "skip"]):
            return {"skill": "spotify", "params": {"action": "next"}, "domain": "general"}
        if any(p in cmd for p in ["previous song", "prev song", "previous track", "prev track"]):
            return {"skill": "spotify", "params": {"action": "previous"}, "domain": "general"}

        # Play specific song (supports e.g., "play boyfriend on spotify" or "open spotify and play boyfriend")
        spotify_play_match = re.match(
            r"^(?:can you\s+)?(?:open\s+spotify\s+and\s+)?play\s+(.+?)(?:\s+(?:on|in)\s+spotify)?$", 
            cmd
        )
        if spotify_play_match:
            query = spotify_play_match.group(1).strip()
            # Clean up query if it starts with "by"
            query_clean = re.sub(r'\bby\b', '', query).strip()
            if query_clean not in ["music", "song", "spotify", "some music", "any song"]:
                return {"skill": "spotify", "params": {"action": "play", "query": query_clean}, "domain": "general"}

        # Hindi / Hinglish / Phonetic play song commands (e.g., "gane bane bajado", "gane bane bhajadu", "gaane bajao")
        if any(p in cmd for p in ["gane", "gaane", "bajao", "bajado", "bhajadu", "bhajado", "gana", "gaana"]):
            song_query = "bollywood hits"
            play_hindi_match = re.search(r"(?:play|bajao|bajado|bhajadu|bhajado)\s+(.+)", cmd)
            if play_hindi_match:
                q = play_hindi_match.group(1).strip()
                q = re.sub(r"\b(gane|gaane|gana|gaana|bajao|bajado|bhajadu|bhajado|on spotify|spotify|kuch|kuchh|bane|kut|dharyas)\b", "", q).strip()
                if q:
                    song_query = q
            return {"skill": "spotify", "params": {"action": "play", "query": song_query}, "domain": "general"}

        # 6. Face ID Calibration
        if any(p in cmd for p in ["calibrate my face", "set up face id", "configure face recognition", "calibrate face", "setup face id"]):
            return {"skill": "screen_vision", "params": {"action": "calibrate"}, "domain": "general"}

        # 7. Memory Operations (Store / Recall)
        remember_match = re.match(r"^(?:can you\s+)?(?:remember|keep in mind|write down)\s+(?:that\s+)?(.+)", cmd)
        if remember_match:
            return {"skill": "memory_ops", "params": {"action": "store", "query": remember_match.group(1).strip()}, "domain": "general"}

        recall_match = re.match(r"^(?:do you remember|what did i tell you about|what did i say about|what is my|who is my|where is my|what was my)\s+(.+)", cmd)
        if recall_match:
            query = recall_match.group(1).strip()
            if not any(kw in query for kw in ["cpu", "ram", "system", "screen", "monitor"]):
                return {"skill": "memory_ops", "params": {"action": "recall", "query": query}, "domain": "general"}



        # 12. Dashboard HUD Toggle
        if any(p in cmd for p in ["open dashboard", "show dashboard", "open console", "show console", "open hud", "show hud"]):
            return {"skill": "os_control", "params": {"action": "show_dashboard"}, "domain": "general"}
        if any(p in cmd for p in ["close dashboard", "hide dashboard", "close console", "hide console", "close hud", "hide hud"]):
            return {"skill": "os_control", "params": {"action": "hide_dashboard"}, "domain": "general"}

        # 8. Launch App (Non-greedy matching to prevent catching commands like "open spotify and play ...")
        launch_match = re.match(
            r"^(?:can you\s+)?(?:open|launch|run|start)\s+([a-z0-9\s\.\-_]+?)(?:\s+(?:and|then|to)\s+.*)?$", 
            cmd
        )
        if launch_match:
            app = launch_match.group(1).strip()
            # Filter out false positives
            if app not in ["the laptop", "sentry mode", "screen", "my pc"]:
                return {"skill": "os_control", "params": {"action": "launch", "app": app}, "domain": "general"}

        # 9. Type text
        type_match = re.match(r"^type\s+(.+)", cmd)
        if type_match:
            return {"skill": "os_control", "params": {"action": "type", "text": type_match.group(1)}, "domain": "general"}

        # 10. Workspace Context
        if any(p in cmd for p in ["explain my code", "look at my code", "read my active file", "workspace status", "explain my workspace"]):
            return {"skill": "workspace_context", "params": {"action": "explain_workspace"}, "domain": "general"}

        if any(p in cmd for p in ["what is on my clipboard", "explain my clipboard", "read my clipboard", "what did i copy"]):
            return {"skill": "workspace_context", "params": {"action": "read_clipboard"}, "domain": "general"}

        # 11. Self-Healing Vision Click
        click_match = re.match(r"^(?:can you\s+)?(?:click on|press the|click the|click)\s+([a-z0-9\s]+?)(?:\s+button|\s+icon)?$", cmd)
        if click_match:
            elem = click_match.group(1).strip()
            if elem not in ["the laptop", "sentry mode", "screen", "my pc"]:
                return {"skill": "self_healing", "params": {"action": "click_element", "element_name": elem}, "domain": "general"}

        # --- New OS Controls (Minimize/Close/Workspace/Drag/Video/Archiving) ---
        if cmd.startswith("close app ") or cmd.startswith("close window "):
            app = cmd.replace("close app ", "").replace("close window ", "").strip()
            return {"skill": "os_control", "params": {"action": "close", "app": app}, "domain": "general"}
            
        if cmd.startswith("minimize app ") or cmd.startswith("minimize window "):
            app = cmd.replace("minimize app ", "").replace("minimize window ", "").strip()
            return {"skill": "os_control", "params": {"action": "minimize", "app": app}, "domain": "general"}
            
        if "switch workspace left" in cmd:
            return {"skill": "os_control", "params": {"action": "switch_workspace", "direction": "left"}, "domain": "general"}
        if "switch workspace right" in cmd or "switch workspace" in cmd:
            return {"skill": "os_control", "params": {"action": "switch_workspace", "direction": "right"}, "domain": "general"}
            
        drag_match = re.search(r"drag from (\d+)\s*,\s*(\d+) to (\d+)\s*,\s*(\d+)", cmd)
        if drag_match:
            return {
                "skill": "os_control",
                "params": {
                    "action": "drag_and_drop",
                    "x1": int(drag_match.group(1)),
                    "y1": int(drag_match.group(2)),
                    "x2": int(drag_match.group(3)),
                    "y2": int(drag_match.group(4))
                },
                "domain": "general"
            }
            
        if "record screen" in cmd or "screen video" in cmd:
            dur_match = re.search(r"(\d+) seconds", cmd)
            dur = float(dur_match.group(1)) if dur_match else 5.0
            return {"skill": "os_control", "params": {"action": "record_screen", "duration": dur}, "domain": "general"}
            
        if "annotate screenshot" in cmd or "take annotated screenshot" in cmd:
            return {"skill": "os_control", "params": {"action": "annotate_screenshot"}, "domain": "general"}
            
        if any(p in cmd for p in ["list startup", "startup programs", "startup apps"]):
            return {"skill": "os_control", "params": {"action": "list_startup"}, "domain": "general"}
            
        # --- File Manager ---
        create_file_match = re.match(r"^create file at (.+?) with content (.+)", cmd)
        if create_file_match:
            return {"skill": "file_manager", "params": {"action": "create_file", "path": create_file_match.group(1).strip(), "content": create_file_match.group(2).strip()}, "domain": "general"}
            
        rename_match = re.match(r"^rename file (.+?) to (.+)", cmd)
        if rename_match:
            return {"skill": "file_manager", "params": {"action": "rename_file", "old_path": rename_match.group(1).strip(), "new_path": rename_match.group(2).strip()}, "domain": "general"}
            
        move_match = re.match(r"^move file (.+?) to (.+)", cmd)
        if move_match:
            return {"skill": "file_manager", "params": {"action": "move_file", "src": move_match.group(1).strip(), "dst": move_match.group(2).strip()}, "domain": "general"}
            
        if cmd.startswith("shred file "):
            return {"skill": "file_manager", "params": {"action": "delete_file", "path": cmd.replace("shred file ", "").strip(), "shred": True}, "domain": "general"}
        if cmd.startswith("delete file "):
            return {"skill": "file_manager", "params": {"action": "delete_file", "path": cmd.replace("delete file ", "").strip(), "shred": False}, "domain": "general"}
            
        if cmd.startswith("create directory ") or cmd.startswith("create folder "):
            path = cmd.replace("create directory ", "").replace("create folder ", "").strip()
            return {"skill": "file_manager", "params": {"action": "create_directory", "path": path}, "domain": "general"}
        if cmd.startswith("delete directory ") or cmd.startswith("delete folder "):
            path = cmd.replace("delete directory ", "").replace("delete folder ", "").strip()
            return {"skill": "file_manager", "params": {"action": "delete_directory", "path": path}, "domain": "general"}

        # --- Data Analyzer ---
        if cmd.startswith("read document ") or cmd.startswith("parse document ") or cmd.startswith("read file "):
            fp = cmd.replace("read document ", "").replace("parse document ", "").replace("read file ", "").strip()
            return {"skill": "data_analyzer", "params": {"action": "read_document", "filepath": fp}, "domain": "general"}
            
        stats_match = re.search(r"calculate statistics of column (.+?) in (.+)", cmd)
        if stats_match:
            return {"skill": "data_analyzer", "params": {"action": "calculate_statistics", "filepath": stats_match.group(2).strip(), "column_name": stats_match.group(1).strip()}, "domain": "general"}
            
        kpi_log_match = re.match(r"^log kpi ([a-zA-Z0-9_\-]+) value (\d+\.?\d*)", cmd)
        if kpi_log_match:
            return {"skill": "data_analyzer", "params": {"action": "log_kpi", "name": kpi_log_match.group(1).strip(), "value": float(kpi_log_match.group(2))}, "domain": "general"}
            
        if cmd.startswith("kpi history of "):
            return {"skill": "data_analyzer", "params": {"action": "kpi_history", "name": cmd.replace("kpi history of ", "").strip()}, "domain": "general"}

        # --- Productivity Planner ---
        if cmd.startswith("add todo "):
            return {"skill": "productivity", "params": {"action": "add_todo", "task": cmd.replace("add todo ", "").strip()}, "domain": "general"}
        if cmd in ["list todos", "show todos", "get todos", "todo list"]:
            return {"skill": "productivity", "params": {"action": "list_todos"}, "domain": "general"}
        if cmd.startswith("complete todo "):
            t_id = cmd.replace("complete todo ", "").strip()
            if t_id.isdigit():
                return {"skill": "productivity", "params": {"action": "complete_todo", "todo_id": int(t_id)}, "domain": "general"}

        if any(p in cmd for p in ["check inbox", "read emails", "check email", "show emails"]):
            return {"skill": "productivity", "params": {"action": "check_inbox"}, "domain": "general"}
            
        if "record meeting" in cmd or "start dictation" in cmd:
            dur_match = re.search(r"(\d+) seconds", cmd)
            dur = int(dur_match.group(1)) if dur_match else 60
            return {"skill": "productivity", "params": {"action": "record_meeting", "duration": dur}, "domain": "general"}
            
        # --- Web Research Enhancements ---
        if cmd.startswith("download file "):
            return {"skill": "web_research", "params": {"action": "download", "url": cmd.replace("download file ", "").strip()}, "domain": "general"}
        if cmd.startswith("track competitor "):
            return {"skill": "web_research", "params": {"action": "track_competitor", "url": cmd.replace("track competitor ", "").strip()}, "domain": "general"}
        if cmd.startswith("extract tables "):
            return {"skill": "web_research", "params": {"action": "extract_tables", "url": cmd.replace("extract tables ", "").strip()}, "domain": "general"}
        if cmd.startswith("monitor rss "):
            return {"skill": "web_research", "params": {"action": "monitor_rss", "url": cmd.replace("monitor rss ", "").strip()}, "domain": "general"}
        if cmd.startswith("search papers "):
            return {"skill": "web_research", "params": {"action": "search_papers", "query": cmd.replace("search papers ", "").strip()}, "domain": "general"}
        if cmd.startswith("fact check "):
            return {"skill": "web_research", "params": {"action": "fact_check", "statement": cmd.replace("fact check ", "").strip()}, "domain": "general"}

        # Daily news briefing triggers
        if any(p in cmd for p in ["today's news", "todays news", "top news", "daily news", "news headlines", "today's headlines", "what is the news", "what are the news"]):
            return {"skill": "web_research", "params": {"action": "daily_news"}, "domain": "general"}

        # Stock/Crypto Market Analysis triggers (Indian, US, HK, Crypto)
        stock_keywords = ["stock", "share price", "stock price", "crypto", "price", "trend"]
        for kw in stock_keywords:
            if kw in cmd:
                asset = cmd.replace(kw, "").replace("analyze", "").replace("check", "").replace("price of", "").replace("trend of", "").strip()
                asset = re.sub(r"\b(of|on|in|the|show|get)\b", "", asset).strip()
                if asset and len(asset.split()) <= 2:
                    return {"skill": "market_analyzer", "params": {"action": "analyze", "query": asset}, "domain": "general"}

        # --- Security Auditor ---
        if any(p in cmd for p in ["scan ports", "port scan"]):
            host_match = re.search(r"host (\S+)", cmd)
            host = host_match.group(1) if host_match else "127.0.0.1"
            return {"skill": "security_auditor", "params": {"action": "scan_ports", "host": host}, "domain": "general"}
        if any(p in cmd for p in ["scan network", "network scan", "devices on my network"]):
            return {"skill": "security_auditor", "params": {"action": "scan_network"}, "domain": "general"}
        if any(p in cmd for p in ["audit connections", "outgoing traffic", "outbound connections"]):
            return {"skill": "security_auditor", "params": {"action": "audit_traffic"}, "domain": "general"}
        if cmd.startswith("audit password "):
            return {"skill": "security_auditor", "params": {"action": "audit_password", "password": cmd.replace("audit password ", "").strip()}, "domain": "general"}
        if any(p in cmd for p in ["cve audit", "audit dependencies", "check packages"]):
            return {"skill": "security_auditor", "params": {"action": "audit_cve"}, "domain": "general"}
        if any(p in cmd for p in ["workspace logs", "check logs", "analyze logs"]):
            return {"skill": "security_auditor", "params": {"action": "audit_logs"}, "domain": "general"}

        # --- Vision Tracker ---
        if any(p in cmd for p in ["detect objects", "what objects", "what's in the room"]):
            return {"skill": "vision_tracker", "params": {"action": "detect_objects"}, "domain": "general"}
        if any(p in cmd for p in ["analyze fatigue", "check my stress", "am i tired", "check fatigue"]):
            return {"skill": "vision_tracker", "params": {"action": "analyze_fatigue"}, "domain": "general"}

        return None


    def route(self, text: str) -> dict:
        """Return routing dict: {skill, params, domain}"""
        # Step 1: Check fast regex routes
        regex_result = self._regex_route(text)
        if regex_result:
            logger.info(f"Routed via regex: {regex_result}")
            return regex_result

        # Step 2: Fallback to LLM chat
        try:
            response = ollama.chat(
                model=self.main_model,
                messages=[
                    {"role": "system", "content": self.prompts["system_prompts"]["intent_router"]},
                    {"role": "user", "content": text}
                ],
                options={"temperature": 0.1}
            )
            raw = response["message"]["content"].strip()
            
            # Clean up JSON blocks
            raw = raw.replace("```json", "").replace("```", "").strip()
            start = raw.find("{")
            end = raw.rfind("}")
            if start != -1 and end != -1 and end > start:
                raw = raw[start:end+1]
                
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning(f"Intent parse failed for: {text}, defaulting to conversation")
            return {"skill": "conversation", "params": {}, "domain": "general"}
        except Exception as e:
            logger.error(f"Routing error: {e}")
            return {"skill": "conversation", "params": {}, "domain": "general"}

    def get_filler(self) -> str:
        """Get instant filler response from the fast filler model (e.g., gemma2:2b)"""
        try:
            response = ollama.chat(
                model=self.filler_model,
                messages=[
                    {"role": "system", "content": self.prompts["system_prompts"]["filler"]},
                    {"role": "user", "content": "generate one filler"}
                ],
                options={"temperature": 0.9, "num_predict": 15}
            )
            return response["message"]["content"].strip()
        except Exception:
            return "On it, sir."


if __name__ == "__main__":
    router = IntentRouter()
    
    print("Testing Intent Router...")
    test_phrases = [
        "open google chrome please",
        "what do you see on my screen right now?",
        "i have a terrible headache and fever",
        "write a python script to scrape a website",
        "open spotify and play boyfriend by karan aujla",
        "play playboy on spotify",
        "pause the music",
        "skip this song",
        "open chrome and search for space news",
        "calibrate my face please",
        "remember that my girlfriend's birthday is on October 5th",
        "what did I tell you about my girlfriend's birthday?"
    ]
    
    for phrase in test_phrases:
        print(f"\nUser: {phrase}")
        result = router.route(phrase)
        print(f"JARVIS Intent: {json.dumps(result, indent=2)}")
        
    print("\nTesting fast filler generation...")
    print(f"Filler: {router.get_filler()}")
