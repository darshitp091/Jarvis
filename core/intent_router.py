try:
    import ollama
except ImportError:
    ollama = None
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

    def _regex_route(self, text: str, active_presentation_topic: str = None) -> dict | None:
        """Fast regex pre-parser to bypass LLM latency/errors for critical commands"""
        import re
        cmd = text.lower().strip()
        cmd = re.sub(r"[,\?\!\.\"\']", "", cmd).strip()

        # Stateful Presentation Follow-ups check
        if active_presentation_topic:
            is_slide_refinement = any(w in cmd for w in ["slide", "page", "prezentation", "presentation", "ppt", "slides", "images", "image", "content", "summarize", "modify", "change", "update", "edit", "entanglement", "physics", "presented by", "by"])
            is_generic_demand = any(w in cmd for w in ["aaj ke aaj", "darshit", "banana", "create", "make", "chahiye", "search karo"]) and not any(w in cmd for w in ["science", "topic", "math", "history"])
            if is_slide_refinement or is_generic_demand:
                pages_match = re.search(r"(\d+)\s*(?:page|slide)", cmd)
                slide_num = None
                specific_slide = re.search(r"slide\s+(\d+)", cmd)
                if specific_slide:
                    slide_num = int(specific_slide.group(1))
                return {
                    "skill": "productivity",
                    "params": {
                        "action": "modify_presentation_slide",
                        "slide_num": slide_num,
                        "query": text
                    },
                    "domain": "general"
                }

        # Smart Browser Opening & Web Searching in Real Browser
        is_browser_cmd = any(w in cmd for w in ["browser", "chrome", "edge", "safari", "braavjer", "brovzer", "brauzar", "ब्रूवजर", "ब्राउज़र", "क्रोम"])
        is_open_action = any(w in cmd for w in [
            "open", "show", "search", "display", "dikha", "dikhao", "chala", "chalao", "apn", "apan", "open karo", "open kar", "bhejo",
            "खोल", "खोलना", "दिखाओ", "दिखा", "चलाओ", "चला", "अपन", "ओपन"
        ])
        if is_browser_cmd and is_open_action:
            q = cmd
            q = re.sub(
                r"\b(?:open|show|search|display|dikha|dikhao|chala|chalao|apn|apan|open\s+karo|open\s+kar|bhejo|pages|page|pejeis|pages\s+ko|page\s+ko|links|link)\b", 
                "", 
                q
            )
            q = re.sub(
                r"\b(?:browser|chrome|edge|safari|braavjer|brovzer|brauzar|in\s+browser|in\s+chrome|on\s+browser|on\s+chrome|browser\s+me|browser\s+mein|chrome\s+me|chrome\s+mein)\b", 
                "", 
                q
            )
            q = re.sub(
                r"(?:ब्रूवजर|ब्राउज़र|क्रोम|में|मे|पे|पर|को|खोल|खोलना|दिखाओ|दिखा|चलाओ|चला|अपन|ओपन|के\s+पेज|के\s+पेjis|के\s+पेजिस|के\s+पेज\s+को|के\s+पेजिस\s+ko)", 
                "", 
                q
            )
            if any(w in cmd for w in ["laptop", "leptop", "leptob"]):
                if "under" in cmd and "budget" in cmd:
                    q = "under budget laptops"
                else:
                    q = re.sub(r"\b(?:ek|kaam|karo|please|plz|kya|tum|kar|sakte|ho|de|kar\s+de|mujhe)\b", "", q)
            else:
                q = re.sub(r"\b(?:ek|kaam|karo|please|plz|kya|tum|kar|sakte|ho|de|kar\s+de|mujhe)\b", "", q)
                
            q = q.strip(",.!? ")
            if not q:
                q = "under budget laptops"
            return {"skill": "os_control", "params": {"action": "open_browser", "query": q}, "domain": "general"}

        # 0. Smart Note Creation & Retrieval (English / Hindi / Hinglish)
        # Handles triggers like: "remember this: ...", "yaad rakhna ki ...", "likh le ..."
        note_create_match = re.search(r"\b(?:note|remember|keep|store|yaad\s+rakhna|likh\s+le|save\s+kar\s+lo)\s+(?:this|that|down|info)?\s*(?::|-)?\s*(.+)", cmd)
        if note_create_match:
            content_val = note_create_match.group(1).strip()
            return {"skill": "obsidian", "params": {"action": "create_note", "content": content_val}, "domain": "general"}

        # Handles triggers like: "what did I save under ...", "maine is name se kya save kiya tha..."
        note_retrieve_match = re.search(r"\b(?:what\s+did\s+i\s+save\s+under|show\s+note|read\s+note|kya\s+save\s+kiya\s+tha|maine\s+kya\s+yaad|kya\s+likha\s+tha)\s+(?:about|under|name|ke\s+name\s+se)?\s*(?::|-)?\s*(.+)", cmd)
        if note_retrieve_match:
            query_val = note_retrieve_match.group(1).strip()
            query_val = re.sub(r"\b(?:batao|bataiye|dikhao|bhejo|tell\s+me|show\s+me|woh|kya\s+tha)\b", "", query_val).strip()
            return {"skill": "obsidian", "params": {"action": "read_note", "title": query_val}, "domain": "general"}

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
        # Check for reminder correction / removal / cancellation
        remove_reminder_match = re.search(
            r"(?:remove|cancel|delete|correct|update)\s+(?:the|that|my)?\s*(?:past|last|previous)\s+reminder(?:\s+and\s+add\s+this\s+to\s+|\s+and\s+|\s+to\s+)?(.*)?", 
            cmd
        )
        if remove_reminder_match:
            remaining = remove_reminder_match.group(1).strip() if remove_reminder_match.group(1) else ""
            # See if remaining contains a new reminder request
            new_remind = re.search(r"remind\s+me\s+to\s+(.+?)\s+(?:at|in)\s+(\d+[:\d\s]*(?:am|pm|min|minutes)?)\s*(?:on\s+phone|on\s+mobile)?", remaining)
            if not new_remind:
                new_remind = re.search(r"(?:to\s+)?(.+?)\s+(?:at|in)\s+(\d+[:\d\s]*(?:am|pm|min|minutes)?)\s*(?:on\s+phone|on\s+mobile)?", remaining)
            
            if new_remind:
                return {
                    "skill": "phone",
                    "params": {
                        "action": "correct_reminder",
                        "remove_last": True,
                        "add_new": True,
                        "message": new_remind.group(1).strip(),
                        "time": new_remind.group(2).strip()
                    },
                    "domain": "general"
                }
            else:
                return {
                    "skill": "phone",
                    "params": {
                        "action": "correct_reminder",
                        "remove_last": True,
                        "add_new": False
                    },
                    "domain": "general"
                }

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

        # Hinglish WhatsApp Messaging
        if "whatsapp" in cmd:
            contact = None
            msg = "hi"
            ko_match = re.search(r"\b([a-zA-Z0-9]+)\s+ko\b", cmd)
            if not ko_match:
                ko_match = re.search(r"\b(?:whatsapp|wa)\s+(?:message\s+|msg\s+)?(?:to\s+|pe\s+|par\s+)?([a-zA-Z0-9]+)\b", cmd)
            if ko_match:
                extracted = ko_match.group(1).strip()
                if extracted not in ["khal", "khol", "open", "send", "kar", "bhej", "pe", "par", "high", "hi", "karo", "karna"]:
                    contact = extracted
            if contact:
                msg_clean = cmd
                split_parts = re.split(r"\b" + re.escape(contact) + r"\b\s+ko\b|\b" + re.escape(contact) + r"\b", msg_clean, flags=re.IGNORECASE)
                if len(split_parts) > 1:
                    msg_clean = " ".join(split_parts[1:])
                else:
                    msg_clean = split_parts[0]
                msg_clean = re.sub(r"\b(?:whatsapp|wa|message|msg|send|karo|khal|khol|open|pe|par|ko|kar\s+de|bhej\s+de|bhejdo|send\s+kar\s+de|khol\s+ke)\b", "", msg_clean)
                msg_clean = re.sub(r"\b(?:high)\b", "hi", msg_clean).strip()
                msg_clean = msg_clean.strip(",.!? ")
                if msg_clean:
                    msg = msg_clean
                return {"skill": "phone", "params": {"action": "whatsapp_message", "contact": contact, "message": msg}, "domain": "general"}

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

        # P2P Node Linking
        if any(p in cmd for p in ["list local devices", "list network peers", "scan local peers", "show active peers", "list network devices"]):
            return {"skill": "p2p_link", "params": {"action": "list_peers"}, "domain": "general"}
        
        p2p_clip_match = re.search(r"\b(?:send\s+clipboard\s+to|sync\s+clipboard\s+to)\s+([0-9\.]+)", cmd)
        if p2p_clip_match:
            return {"skill": "p2p_link", "params": {"action": "send_clipboard", "peer_ip": p2p_clip_match.group(1).strip()}, "domain": "general"}
            
        p2p_speech_match = re.search(r"\b(?:send\s+speech\s+to|speak\s+to)\s+([0-9\.]+)\s+(?:message\s+)?(.+)", cmd)
        if p2p_speech_match:
            return {"skill": "p2p_link", "params": {"action": "send_speech", "peer_ip": p2p_speech_match.group(1).strip(), "message": p2p_speech_match.group(2).strip()}, "domain": "general"}

        # Hologram Assembly Controls
        if any(p in cmd for p in ["explode the assembly", "explode design", "explode hologram"]):
            return {"skill": "hologram_control", "params": {"action": "explode", "enable": True}, "domain": "general"}
        if any(p in cmd for p in ["contract the assembly", "assemble design", "contract design", "assemble hologram"]):
            return {"skill": "hologram_control", "params": {"action": "explode", "enable": False}, "domain": "general"}
        if any(p in cmd for p in ["rotate y axis fast", "rotate hologram fast", "spin hologram fast"]):
            return {"skill": "hologram_control", "params": {"action": "set_rotation", "speed": "fast"}, "domain": "general"}
        if any(p in cmd for p in ["rotate y axis slow", "rotate hologram slow", "spin hologram slow"]):
            return {"skill": "hologram_control", "params": {"action": "set_rotation", "speed": "slow"}, "domain": "general"}
        if any(p in cmd for p in ["stop rotation", "freeze hologram", "stop hologram rotation"]):
            return {"skill": "hologram_control", "params": {"action": "set_rotation", "speed": "stop"}, "domain": "general"}
        if any(p in cmd for p in ["show heat map", "enable heat map", "activate hologram heatmap"]):
            return {"skill": "hologram_control", "params": {"action": "toggle_heatmap", "enable": True}, "domain": "general"}
        if any(p in cmd for p in ["hide heat map", "disable heat map", "deactivate hologram heatmap"]):
            return {"skill": "hologram_control", "params": {"action": "toggle_heatmap", "enable": False}, "domain": "general"}

        # Git Sentinel Auto-CI/CD Controls
        if any(p in cmd for p in ["run sentinel check", "sentinel check", "verify workspace builds", "verify builds", "git sentinel check"]):
            return {"skill": "git_sentinel", "params": {"action": "check"}, "domain": "general"}

        # Network Sentry Active Firewall Controls
        quarantine_match = re.search(r"\b(?:quarantine\s+ip|block\s+connections\s+from|block\s+ip|block\s+remote\s+ip)\s+([0-9\.]+)", cmd)
        if quarantine_match:
            return {"skill": "sentry_firewall", "params": {"action": "quarantine", "ip": quarantine_match.group(1).strip()}, "domain": "general"}
            
        unquarantine_match = re.search(r"\b(?:remove\s+quarantine\s+for|allow\s+ip|unblock\s+ip)\s+([0-9\.]+)", cmd)
        if unquarantine_match:
            return {"skill": "sentry_firewall", "params": {"action": "remove_quarantine", "ip": unquarantine_match.group(1).strip()}, "domain": "general"}
            
        if any(p in cmd for p in ["list quarantine rules", "show blocked ips", "list firewall blocks", "show quarantine list"]):
            return {"skill": "sentry_firewall", "params": {"action": "list_blocks"}, "domain": "general"}

        # Cognitive Focus & Vitals Controls
        if any(p in cmd for p in ["show vitals dashboard", "open focus monitor", "show focus tracker", "open vitals monitor", "show vitals"]):
            return {"skill": "focus_tracker", "params": {"action": "open_dashboard"}, "domain": "general"}
        if any(p in cmd for p in ["hide vitals dashboard", "close focus monitor", "hide focus tracker", "close vitals monitor", "hide vitals"]):
            return {"skill": "focus_tracker", "params": {"action": "close_dashboard"}, "domain": "general"}

        # Spatial Air Typist Controls
        if any(p in cmd for p in ["activate air typist", "enable eye controller", "start air typist", "turn on gaze pointer"]):
            return {"skill": "air_typist", "params": {"action": "start"}, "domain": "general"}
        if any(p in cmd for p in ["deactivate air typist", "disable eye controller", "stop air typist", "turn off gaze pointer"]):
            return {"skill": "air_typist", "params": {"action": "stop"}, "domain": "general"}

        # Ambient Sensory Health Checks
        if any(p in cmd for p in ["monitor sensory health", "check posture", "posture check", "check ambient light", "check environment"]):
            return {"skill": "sensory_health", "params": {"action": "check"}, "domain": "general"}
        if any(p in cmd for p in ["recalibrate posture", "calibrate posture", "set good posture"]):
            return {"skill": "sensory_health", "params": {"action": "recalibrate"}, "domain": "general"}

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

        volume_match = re.search(r"(?:set|change|adjust)\s+(?:master\s+|speaker\s+|system\s+)?volume\s+(?:to\s+)?(\d+)", cmd)
        if volume_match:
            return {"skill": "os_control", "params": {"action": "set_volume", "percent": int(volume_match.group(1))}, "domain": "general"}

        if any(p in cmd for p in ["turn on battery saver", "enable battery saver", "activate battery saver"]):
            return {"skill": "os_control", "params": {"action": "toggle_battery_saver", "enable": True}, "domain": "general"}
        if any(p in cmd for p in ["turn off battery saver", "disable battery saver", "deactivate battery saver"]):
            return {"skill": "os_control", "params": {"action": "toggle_battery_saver", "enable": False}, "domain": "general"}

        # Disk cleaning: any clean verb AND any temp noun in command
        clean_verbs = ["clean", "clear", "delete", "remove", "rimo", "rimove", "clean up"]
        temp_nouns = ["temporary", "temp", "temathareree", "junk", "cache", "kesh"]
        if any(v in cmd for v in clean_verbs) and any(n in cmd for n in temp_nouns):
            return {"skill": "os_control", "params": {"action": "clean_disk"}, "domain": "general"}
            
        # Empty recycle bin: only if NOT a specific folder deletion command
        recycle_verbs = ["empty", "clean", "clear", "remove", "delete", "delet", "dilet", "empty_recycle_bin"]
        recycle_nouns = ["trash", "recycle", "bin", "vine"]
        has_folder_target = any(k in cmd for k in ["screenshot", "screenshots", "downloads", "pictures", "documents", "folder", "subfolder"])
        if not has_folder_target and ((any(v in cmd for v in recycle_verbs) and any(n in cmd for n in recycle_nouns)) or "recycle bin" in cmd):
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

        # --- Vitals & Health Checks ---
        if any(p in cmd for p in ["check my heart rate", "run vitals diagnostics", "check pulse", "vitals status", "check stress level"]):
            return {"skill": "vitals_check", "params": {"action": "check_vitals"}, "domain": "general"}

        # --- Phone Throw/Pull Spatial Bridge ---
        if cmd.startswith("throw to phone") or cmd.startswith("throw file to phone") or cmd.startswith("throw this code to my phone") or cmd.startswith("throw this file to my phone") or cmd.startswith("throw code to my phone"):
            # We will handle pulling the active file content directly in main.py if content is empty
            return {"skill": "phone", "params": {"action": "throw", "content": ""}, "domain": "general"}
        throw_match = re.match(r"^throw\s+(.+?)\s+(?:to my phone|to phone|to mobile)$", cmd)
        if throw_match:
            return {"skill": "phone", "params": {"action": "throw", "content": throw_match.group(1).strip()}, "domain": "general"}
        if any(p in cmd for p in ["pull my phone screen", "pull screen from phone", "sync phone screen", "show mobile screen"]):
            return {"skill": "phone", "params": {"action": "pull_screen"}, "domain": "general"}

        # --- CAD Design & 3D Hologram Mesh ---
        cad_match = re.search(r"\b(?:design|render|generate|create|show)\s+(?:a\s+)?(?:3d\s+)?(arc reactor|gearbox|gear|double helix|dna|sphere|globe|vibranium core)\b", cmd)
        if cad_match:
            return {"skill": "hologram_control", "params": {"action": "design", "object": cad_match.group(1)}, "domain": "general"}

        # --- Hologram Explode / Assemble ---
        if any(p in cmd for p in ["explode the hologram", "explode model", "explode assembly", "pull apart hologram"]):
            return {"skill": "hologram_control", "params": {"action": "explode", "enable": True}, "domain": "general"}
        if any(p in cmd for p in ["assemble the hologram", "assemble model", "assemble gearbox", "put back together hologram"]):
            return {"skill": "hologram_control", "params": {"action": "explode", "enable": False}, "domain": "general"}

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

        # --- E-Commerce & Shopping Assistant ---
        shop_search_match = re.search(r"(?:search|buy|find|open|show)(?:\s+for)?\s+(.+?)\s+on\s+(amazon|flipkart|myntra|swiggy|zomato)", cmd)
        if shop_search_match:
            return {"skill": "shopping", "params": {"action": "search_product", "query": shop_search_match.group(1).strip(), "platform": shop_search_match.group(2).strip()}, "domain": "general"}
        
        buy_prod_match = re.search(r"(?:buy|purchase|order)\s+(.+)", cmd)
        if buy_prod_match and not any(w in cmd for w in ["phone", "course", "ticket", "stock", "crypto"]):
            return {"skill": "shopping", "params": {"action": "search_product", "query": buy_prod_match.group(1).strip(), "platform": "amazon"}, "domain": "general"}

        if any(c in cmd for c in ["add to cart", "cart mein dalo", "cart me dalo", "add this to cart", "cart mein add karo"]):
            return {"skill": "shopping", "params": {"action": "add_to_cart"}, "domain": "general"}
            
        if any(c in cmd for c in ["buy now", "checkout proceed", "order placed karo", "proceed to checkout"]):
            return {"skill": "shopping", "params": {"action": "buy_now"}, "domain": "general"}

        # --- Color Picker, Mind Map & Shredder ---
        if any(c in cmd for c in ["pick color", "color picker", "sample color", "screen color", "color pick karo"]):
            return {"skill": "os_control", "params": {"action": "pick_screen_color"}, "domain": "general"}

        mindmap_match = re.search(r"(?:mind map|mindmap)(?:\s+for|\s+on)?\s+(.+)", cmd)
        if mindmap_match:
            return {"skill": "productivity", "params": {"action": "mindmap", "topic": mindmap_match.group(1).strip()}, "domain": "general"}
            
        shred_match = re.search(r"(?:shred file|secure delete|shred)\s+(.+)", cmd)
        if shred_match:
            return {"skill": "file_manager", "params": {"action": "shred", "path": shred_match.group(1).strip()}, "domain": "general"}

        sign_pdf_match = re.search(r"sign pdf\s+(.+)", cmd)
        if sign_pdf_match:
            return {"skill": "file_manager", "params": {"action": "sign_pdf", "pdf_path": sign_pdf_match.group(1).strip()}, "domain": "general"}

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

        ppt_match = re.search(r"^(?:create|make)\s+(?:a\s+)?presentation\s+(?:for\s+me\s+)?(?:about|on\s+)?(.+)", cmd)
        if ppt_match:
            return {"skill": "productivity", "params": {"action": "create_presentation", "title": ppt_match.group(1).strip()}, "domain": "general"}

        open_ppt_match = re.search(r"\b(?:project|open|show|play)\s+(?:the\s+)?(?:presentation|slides|pptx?)\b", cmd)
        if open_ppt_match:
            return {"skill": "productivity", "params": {"action": "open_presentation"}, "domain": "general"}

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

        # 1. Unlock System
        unlock_match = re.search(r"\b(?:unlock\s+(?:the\s+)?(?:laptop|screen|pc|it)|open\s+(?:the\s+)?(?:laptop|screen|pc|it)\s+with)\s*(?:(?:the\s+)?(?:pin\s+)?)*([0-9]+)", cmd)
        if unlock_match:
            return {"skill": "os_control", "params": {"action": "unlock", "pin": unlock_match.group(1).strip()}, "domain": "general"}

        # App shortcut controls
        if any(p in cmd for p in ["run the code", "run code", "execute code"]):
            return {"skill": "app_control", "params": {"action": "run_code"}, "domain": "general"}
        if any(p in cmd for p in ["toggle terminal", "open terminal", "close terminal", "hide terminal"]):
            return {"skill": "app_control", "params": {"action": "toggle_terminal"}, "domain": "general"}
        if any(p in cmd for p in ["new tab", "open tab"]):
            return {"skill": "app_control", "params": {"action": "new_tab"}, "domain": "general"}
        if any(p in cmd for p in ["close tab", "exit tab"]):
            return {"skill": "app_control", "params": {"action": "close_tab"}, "domain": "general"}
        if any(p in cmd for p in ["next tab", "go to next tab"]):
            return {"skill": "app_control", "params": {"action": "next_tab"}, "domain": "general"}
        if any(p in cmd for p in ["prev tab", "previous tab", "go to previous tab"]):
            return {"skill": "app_control", "params": {"action": "prev_tab"}, "domain": "general"}
        if any(p in cmd for p in ["reopen closed tab", "reopen tab", "restore tab"]):
            return {"skill": "app_control", "params": {"action": "reopen_tab"}, "domain": "general"}
        if any(p in cmd for p in ["save file", "save script", "save workspace"]):
            return {"skill": "app_control", "params": {"action": "save_file"}, "domain": "general"}

        # 2. Sentry/Secure
        lock_patterns = [
            r"\block\b.*\b(?:screen|laptop|pc|system|windows|computer|it)\b",
            r"\bsecure\b.*\b(?:laptop|pc|system|windows|computer|it)\b",
            r"\bsentry\s+mode\b",
            r"\bwindows\s+lock\b"
        ]
        if any(re.search(pat, cmd) for pat in lock_patterns):
            return {"skill": "os_control", "params": {"action": "secure"}, "domain": "general"}

        # Obsidian personal knowledge base routing
        # 1. Create note / Save to Obsidian
        create_note_match = re.search(r"\b(?:save\s+to\s+obsidian|create\s+note|new\s+note|write\s+note)\s+(?:named|as|with\s+title)?\s*([a-zA-Z0-9\-\_\s]+)", cmd)
        if create_note_match:
            title_param = create_note_match.group(1).strip()
            return {"skill": "obsidian", "params": {"action": "create_note", "title": title_param, "content": "I have created the note, sir."}, "domain": "general"}

        # 2. Read note
        read_note_match = re.search(r"\b(?:read|open|show)\s+(?:my\s+)?(?:obsidian\s+)?note\s+([a-zA-Z0-9\-\_\s]+)", cmd)
        if read_note_match:
            title_param = read_note_match.group(1).strip()
            return {"skill": "obsidian", "params": {"action": "read_note", "title": title_param}, "domain": "general"}

        # 3. Search Obsidian
        search_note_match = re.search(r"\b(?:search\s+obsidian|find\s+notes?)\s+(?:for|about)?\s*([a-zA-Z0-9\-\_\s]+)", cmd)
        if search_note_match:
            query_param = search_note_match.group(1).strip()
            return {"skill": "obsidian", "params": {"action": "search_notes", "query": query_param}, "domain": "general"}

        # 4. Append to Daily Note
        daily_note_match = re.search(r"\b(?:add\s+to\s+daily\s+note|log\s+to\s+daily|append\s+to\s+daily)\s+(.+)", cmd)
        if daily_note_match:
            content_param = daily_note_match.group(1).strip()
            return {"skill": "obsidian", "params": {"action": "append_to_daily_note", "content": content_param}, "domain": "general"}

        # 5. List notes
        if any(p in cmd for p in ["list my notes", "show my notes", "list obsidian notes", "show obsidian notes"]):
            return {"skill": "obsidian", "params": {"action": "list_notes"}, "domain": "general"}

        # 2. System Monitor
        words = cmd.split()
        if any(p in cmd for p in ["status check", "vitals check", "stark diagnostics", "system diagnostics", "diagnostic check"]):
            return {"skill": "system_monitor", "params": {"action": "stark_diagnostics"}, "domain": "general"}
        if any(p in cmd for p in ["system monitor", "status of the system", "system resources"]) or "cpu" in words or "ram" in words:
            return {"skill": "system_monitor", "params": {"action": "regular_diagnostics"}, "domain": "general"}

        # 3. Screen Vision
        if not any(w in cmd for w in ["screenshot", "screenshots"]) and any(p in cmd for p in ["screen", "what's on my screen", "describe my screen", "what do you see", "what can you see"]):
            return {"skill": "screen_vision", "params": {}, "domain": "general"}

        # 4. Media Summarization
        youtube_match = re.search(r"(?:summarize|youtube|video)\s+(https?://\S+)", text, re.IGNORECASE)
        if youtube_match:
            return {"skill": "media_summarize", "params": {"url": youtube_match.group(1)}, "domain": "general"}

        # 5. Spotify / Playback Controls
        # Stop / Pause / Resume (Supporting English, Hinglish, and Devanagari)
        # Stop / Pause / Resume (Supporting English, Hinglish, and Devanagari)
        if any(p in cmd for p in [
            "pause music", "pause spotify", "stop music", "stop spotify", "pause song", "stop song",
            "पॉज", "पॉज करो", "रोको", "बंद करो", "म्यूजिक बंद करो"
        ]) or cmd.strip() in ["pause", "stop", "please pause", "please stop"]:
            return {"skill": "spotify", "params": {"action": "pause"}, "domain": "general"}

        is_resume = False
        resume_exact_phrases = {
            "play", "play music", "play spotify", "resume", "resume music", "resume spotify", 
            "resume playlist", "resume the playlist", "resume song", "resume playback", 
            "please play", "please resume", "प्ले", "प्ले करो", "चालू करो", "बजाओ", "गाना बजाओ"
        }
        if cmd.strip() in resume_exact_phrases:
            is_resume = True
        elif any(p in cmd for p in ["resume music", "resume spotify", "resume playlist", "resume the playlist", "resume playback"]):
            is_resume = True

        if is_resume:
            return {"skill": "spotify", "params": {"action": "resume"}, "domain": "general"}

        if any(p in cmd for p in [
            "next song", "skip song", "next track", "skip track", "skip", "play next", "play next song", "skip this song",
            "अगला गाना", "आगे बढ़ाओ"
        ]):
            return {"skill": "spotify", "params": {"action": "next"}, "domain": "general"}
        if any(p in cmd for p in [
            "previous song", "prev song", "previous track", "prev track", "play previous song", "play prev song", "go back",
            "पिछला गाना", "पीछे करो"
        ]):
            return {"skill": "spotify", "params": {"action": "previous"}, "domain": "general"}

        # Play specific song (supports natural voice prefixes like "please play", "can you play", etc.)
        # Match anything starting with "play " or containing " play "
        spotify_play_match = re.search(r"\bplay\s+(.+)", cmd)
        if spotify_play_match:
            query = spotify_play_match.group(1).strip().rstrip('?')
            # Clean up query
            query_clean = re.sub(r'\b(on spotify|in spotify|spotify|by|on youtube|in youtube|youtube)\b', '', query).strip()
            if query_clean not in ["music", "song", "some music", "any song", "something", "songs", "tracks"]:
                return {"skill": "spotify", "params": {"action": "play", "query": query_clean}, "domain": "general"}

        # Hindi / Hinglish / Devanagari / Phonetic play song commands (Robust parsing)
        cmd_lower = cmd.lower().strip()
        verbs = ["bajao", "bajado", "bhajadu", "bhajado", "baja de", "baja do", "baja", "chalao", "chalado", "chala de", "chala do", "chala", "play", "run", "बजाओ", "बजादो", "बजा", "बजा दो", "प्ले करो"]
        nouns = ["gane", "gaane", "gana", "gaana", "song", "songs", "music", "track", "tracks", "playlist", "audio", "गाने", "गाना"]
        
        if any(v in cmd_lower for v in verbs) or any(n in cmd_lower for n in nouns):
            q = cmd_lower
            # Remove command prefixes
            q = re.sub(
                r"\b(?:please|plz|pehle|ek|kaam|karo|so|ae|tum|bas|yaar|spotify\s+mein|spotify\s+pe|on\s+spotify|in\s+spotify|play\s+on\s+spotify|play\s+in\s+spotify|youtube\s+mein|youtube\s+pe|on\s+youtube|in\s+youtube)\b", 
                "", 
                q
            )
            # Remove verbs
            q = re.sub(
                r"\b(?:bajao|bajado|bhajadu|bhajado|baja\s+de|baja\s+do|baja|chalao|chalado|chala\s+de|chala\s+do|chala|play|run|बजाओ|बजादो|बजा\s+दो|बजा|प्ले\s+करो)\b", 
                "", 
                q
            )
            # Remove nouns
            q = re.sub(
                r"\b(?:gane|gaane|gana|gaana|song|songs|music|track|tracks|playlist|audio|गाने|गाना)\b", 
                "", 
                q
            )
            song_query = q.strip()
            # If the user only said "play music" or "gaana bajao", play default or generic music
            if not song_query:
                song_query = "music"
            return {"skill": "spotify", "params": {"action": "play", "query": song_query}, "domain": "general"}

        # 6. Face ID Calibration
        if any(p in cmd for p in ["calibrate my face", "set up face id", "configure face recognition", "calibrate face", "setup face id"]):
            return {"skill": "screen_vision", "params": {"action": "calibrate"}, "domain": "general"}

        # 6b. Voice ID Calibration
        if any(p in cmd for p in ["calibrate voice", "set up voice id", "configure voice recognition", "calibrate my voice", "setup voice id", "calibrate voice id"]):
            return {"skill": "screen_vision", "params": {"action": "calibrate_voice"}, "domain": "general"}

        # Agent Lab Swarm Collaboration
        lab_match = re.search(r"\b(?:collaborate\s+on|ask\s+the\s+swarm\s+to|developer\s+lab\s+for|swarm\s+collaboration\s+on)\s+(.+)", cmd)
        if lab_match:
            return {"skill": "agent_lab", "params": {"action": "collaborate", "task": lab_match.group(1).strip()}, "domain": "general"}
        if any(p in cmd for p in ["open agent lab", "show agent lab", "open swarm lab", "show swarm lab"]):
            return {"skill": "agent_lab", "params": {"action": "open_lab"}, "domain": "general"}
        if any(p in cmd for p in ["close agent lab", "hide agent lab", "close swarm lab", "hide swarm lab"]):
            return {"skill": "agent_lab", "params": {"action": "close_lab"}, "domain": "general"}

        # Advanced Iron Man Features: Coding Sandbox & Compiler Repair
        sandbox_match = re.search(r"\b(?:sandbox|solve|autonomous\s+task|write\s+python\s+script\s+to|write\s+script\s+to)\s+(.+)", cmd)
        if sandbox_match:
            return {"skill": "coding_sandbox", "params": {"action": "execute_task", "task": sandbox_match.group(1).strip()}, "domain": "general"}

        repair_match = re.search(r"\b(?:compile\s+and\s+repair|compiler\s+repair|auto\s+repair|debug\s+build|fix\s+build)\s+(.+)", cmd)
        if repair_match:
            return {"skill": "coding_sandbox", "params": {"action": "compiler_repair", "command": repair_match.group(1).strip()}, "domain": "general"}

        # Air Canvas Coding
        if any(p in cmd for p in ["compile air canvas", "solve drawing", "compile drawing", "compile canvas", "solve air canvas"]):
            return {"skill": "coding_sandbox", "params": {"action": "compile_canvas"}, "domain": "general"}

        # Polyglot Principal Engineering and Architecture
        arch_match = re.search(r"\b(?:design\s+architecture\s+for|software\s+architecture\s+for|architect\s+for)\s+(.+)", cmd)
        if arch_match:
            return {"skill": "polyglot_engineer", "params": {"action": "design_architecture", "task": arch_match.group(1).strip()}, "domain": "general"}
            
        write_lang_match = re.search(r"\b(?:write|create|generate)\s+a\s+([a-zA-Z0-9\+\#\-\_\s]+?)\s+(?:solution|code|program|script)?\s*(?:for|to)\s+(.+)", cmd)
        if write_lang_match:
            return {"skill": "polyglot_engineer", "params": {"action": "write_solution", "language": write_lang_match.group(1).strip(), "task": write_lang_match.group(2).strip()}, "domain": "general"}
            
        review_match = re.search(r"\b(?:review\s+my|review\s+code\s+for|review\s+this)\s+([a-zA-Z0-9\+\#\-\_\s]+?)\s+(?:code)?\b", cmd)
        if review_match:
            return {"skill": "polyglot_engineer", "params": {"action": "review_code", "language": review_match.group(1).strip()}, "domain": "general"}

        # Advanced Iron Man Features: Macro Recorder
        macro_rec_match = re.search(r"^(?:start\s+)?recording\s+macro\s+(.+)", cmd)
        if macro_rec_match:
            return {"skill": "macro_recorder", "params": {"action": "start", "name": macro_rec_match.group(1).strip()}, "domain": "general"}
            
        if any(p in cmd for p in ["stop recording macro", "stop macro recording", "stop recording"]):
            name = "default_macro"
            stop_name_match = re.search(r"stop\s+recording\s+macro\s+(.+)", cmd)
            if stop_name_match:
                name = stop_name_match.group(1).strip()
            return {"skill": "macro_recorder", "params": {"action": "stop", "name": name}, "domain": "general"}
            
        macro_play_match = re.search(r"^(?:play|execute|run)\s+macro\s+(.+)", cmd)
        if macro_play_match:
            return {"skill": "macro_recorder", "params": {"action": "play", "name": macro_play_match.group(1).strip()}, "domain": "general"}

        # Advanced Iron Man Features: Voice Customizer & HUD
        if any(p in cmd for p in ["enter customization mode", "open settings customizer", "voice customizer", "customization protocol"]):
            return {"skill": "customizer", "params": {"action": "enter"}, "domain": "general"}
            
        thresh_match = re.search(r"(?:set|change)\s+(?:voice|similarity)\s+threshold\s+(?:to\s+)?([\d\.]+)", cmd)
        if thresh_match:
            return {"skill": "customizer", "params": {"action": "set_threshold", "value": float(thresh_match.group(1))}, "domain": "general"}
            
        speed_match = re.search(r"(?:set|change)\s+(?:speech|speaking|tts)\s+(?:rate|speed)\s+(?:to\s+)?([\d\.]+)", cmd)
        if speed_match:
            return {"skill": "customizer", "params": {"action": "set_speed", "value": float(speed_match.group(1))}, "domain": "general"}
            
        if any(p in cmd for p in ["toggle hud", "toggle screen overlay", "show hud overlay", "hide hud overlay", "toggle hud overlay"]):
            return {"skill": "customizer", "params": {"action": "toggle_hud"}, "domain": "general"}

        # 7. Memory Operations (Store / Recall)
        remember_match = re.match(r"^(?:can you\s+)?(?:remember|keep in mind|write down)\s+(?:that\s+)?(.+)", cmd)
        if remember_match:
            return {"skill": "memory_ops", "params": {"action": "store", "query": remember_match.group(1).strip()}, "domain": "general"}

        recall_match = re.match(r"^(?:do you remember|what did i tell you about|what did i say about|what is my|who is my|where is my|what was my)\s+(.+)", cmd)
        if recall_match:
            query = recall_match.group(1).strip()
            if not any(kw in query for kw in ["cpu", "ram", "system", "screen", "monitor"]):
                return {"skill": "memory_ops", "params": {"action": "recall", "query": query}, "domain": "general"}



        # Network Sentry Mapper
        if any(p in cmd for p in ["scan network topology", "scan subnet topology", "visualize subnet nodes", "scan network hologram", "holographic network scan", "scan local network", "scan network"]):
            return {"skill": "network_mapper", "params": {"action": "scan_and_project"}, "domain": "general"}

        # Hologram Toggle
        if any(p in cmd for p in ["show hologram", "activate hologram", "open hologram", "start hologram", "activate holographic simulation", "show holographic view", "show holographic simulation"]):
            return {"skill": "os_control", "params": {"action": "show_hologram"}, "domain": "general"}
        if any(p in cmd for p in ["hide hologram", "close hologram", "stop hologram", "deactivate hologram", "close holographic simulation", "hide holographic view"]):
            return {"skill": "os_control", "params": {"action": "hide_hologram"}, "domain": "general"}

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
            app_words = app.split()
            invalid_app = (
                len(app_words) > 3 or 
                any(w in app_words for w in ["what", "how", "why", "who", "when", "if", "im", "on", "my", "your", "phone", "mobile"]) or
                app in ["the laptop", "sentry mode", "screen", "my pc"]
            )
            if not invalid_app:
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
        if cmd.startswith("focus app ") or cmd.startswith("focus window ") or cmd.startswith("bring to front ") or cmd.startswith("focus "):
            app = cmd.replace("focus app ", "").replace("focus window ", "").replace("bring to front ", "").replace("focus ", "").strip()
            return {"skill": "os_control", "params": {"action": "focus", "app": app}, "domain": "general"}

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

        # Open folder / file matcher (matches "pictures folder kholo", "ek kaam karo pictures folder kholo", "DOWNLOAD FOLDER kholo to")
        if any(w in cmd for w in ["kholo", "open", "launch", "show folder", "open folder", "folder kholo", "khol do"]):
            for loc in ["downloads", "download", "pictures", "photos", "documents", "desktop", "videos", "music", "jarvis", "workspace"]:
                if loc in cmd:
                    target_name = "downloads" if loc in ["download", "downloads"] else ("pictures" if loc in ["pictures", "photos"] else loc)
                    return {"skill": "file_manager", "params": {"action": "find_and_open", "target": target_name}, "domain": "general"}

        open_target_match = re.search(r"^(?:open|show|find|launch)\s+(?:folder|directory|file)?\s*([a-zA-Z0-9_\-\.\s]+?)(?:\s+folder|\s+directory)?$", cmd)
        if open_target_match:
            target_str = open_target_match.group(1).strip()
            if any(w in cmd for w in ["folder", "directory", "file", "downloads", "documents", "desktop", "pictures", "photos", "videos", "music", "kholo", "dikhao"]):
                return {"skill": "file_manager", "params": {"action": "find_and_open", "target": target_str}, "domain": "general"}

        # Subfolder Inspection & Purging (e.g. "JARVIS, CHECK KORO, pictures folder mein screenshot folder hai ki nahi hai")
        if any(w in cmd for w in ["check", "inspect", "count", "kitni files", "files hai", "folder hai", "hai ki nahi"]):
            if any(loc in cmd for loc in ["pictures", "downloads", "desktop", "documents", "photos"]):
                parent_loc = "pictures"
                for loc in ["pictures", "downloads", "desktop", "documents", "photos"]:
                    if loc in cmd:
                        parent_loc = loc
                        break
                target_sub = "screenshots"
                for kw in ["screenshot", "screenshots", "images", "temp", "photos", "downloads"]:
                    if kw in cmd and kw != parent_loc:
                        target_sub = kw
                        break
                return {"skill": "file_manager", "params": {"action": "inspect_folder", "target": target_sub, "location": parent_loc}, "domain": "general"}

        inspect_sub_match = re.search(r"(?:check|inspect|count|how many files|kitni files)\s+(?:in\s+)?([a-zA-Z0-9_\-\s]+?)\s+(?:folder\s+)?(?:in|ke andar)\s+(pictures|downloads|desktop|documents|photos)", cmd)
        if inspect_sub_match:
            return {"skill": "file_manager", "params": {"action": "inspect_folder", "target": inspect_sub_match.group(1).strip(), "location": inspect_sub_match.group(2).strip()}, "domain": "general"}

        inspect_sub_match2 = re.search(r"(pictures|downloads|desktop|documents|photos)\s+(?:ke andar\s+)?([a-zA-Z0-9_\-\s]+?)\s+(?:folder\s+)?(?:check karo|inspect karo|chck karo|mein kitni files hai|check)", cmd)
        if inspect_sub_match2:
            return {"skill": "file_manager", "params": {"action": "inspect_folder", "target": inspect_sub_match2.group(2).strip(), "location": inspect_sub_match2.group(1).strip()}, "domain": "general"}

        # Flexible Subfolder Purging / Deletion regex (matches "screenshot folder ke saariya files delete karo", "to jitni bhi, files & screenshots folder mein, sub ko delete kardo", etc.)
        if any(w in cmd for w in ["delete", "remove", "clean", "purge", "clear", "shred", "hatao", "hata do", "saari files", "saariya", "sub ko delete"]):
            if any(target_kw in cmd for target_kw in ["screenshot", "screenshots", "downloads", "temp", "images", "photos", "folder"]):
                target_sub = "screenshots" if ("screenshot" in cmd or "screenshots" in cmd) else "downloads"
                for kw in ["screenshot", "screenshots", "images", "temp", "photos"]:
                    if kw in cmd:
                        target_sub = kw
                        break
                parent_loc = None
                for loc in ["pictures", "downloads", "desktop", "documents", "photos"]:
                    if loc in cmd and loc != target_sub:
                        parent_loc = loc
                        break
                
                and_clean_bin = any(b in cmd for b in ["recycle bin", "disk clean", "trash", "recyclebin", "recycle bin clean"])
                return {"skill": "file_manager", "params": {"action": "purge_folder", "target": target_sub, "location": parent_loc, "also_empty_bin": and_clean_bin}, "domain": "general"}

        purge_sub_match = re.search(r"(?:delete|remove|clean|purge|clear|shred)\s+(?:all\s+files\s+in|everything\s+in|saari\s+files\s+in)?\s*([a-zA-Z0-9_\-\s]+?)\s+(?:folder\s+)?(?:in|ke andar)\s+(pictures|downloads|desktop|documents|photos)", cmd)
        if purge_sub_match:
            return {"skill": "file_manager", "params": {"action": "purge_folder", "target": purge_sub_match.group(1).strip(), "location": purge_sub_match.group(2).strip()}, "domain": "general"}

        purge_sub_match2 = re.search(r"([a-zA-Z0-9_\-\s]+?)\s+(?:folder\s+)?(?:ke andar ki saari files delete kardo|ke andar ki files delete karo|clean kardo|clear kardo|purge kardo|delete kardo)", cmd)
        if purge_sub_match2:
            return {"skill": "file_manager", "params": {"action": "purge_folder", "target": purge_sub_match2.group(1).strip()}, "domain": "general"}

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
            
        # --- Web Research & YouTube Video Player ---
        if any(v in cmd for v in ["play video", "watch video", "open video", "youtube video", "recipe video", "search youtube", "youtube par"]):
            q = cmd
            for prefix in ["play video on ", "play video ", "watch video on ", "watch video ", "open video ", "youtube video on ", "youtube video ", "search youtube for ", "youtube par ", "recipe video "]:
                q = q.replace(prefix, "")
            q = q.replace("kholo", "").replace("open", "").replace("search", "").replace("play", "").replace("show", "").strip()
            return {"skill": "web_research", "params": {"action": "open_youtube_video", "query": q}, "domain": "general"}
        if cmd.startswith("search google for ") or "google search " in cmd or "google par " in cmd or "google check" in cmd:
            q = cmd.replace("search google for ", "").replace("google search ", "").replace("google par ", "").replace("search ", "").strip()
            return {"skill": "web_research", "params": {"action": "search_google", "query": q}, "domain": "general"}
            
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
        if any(p in cmd for p in ["watchlist", "good stocks", "recommend stocks", "suggest stocks", "stock suggestions", "what stocks to buy", "which stocks to buy", "suggest buy"]):
            return {"skill": "market_analyzer", "params": {"action": "analyze", "query": "watchlist"}, "domain": "general"}

        stock_keywords = [
            "stock", "share price", "stock price", "crypto", "price", "trend", 
            "should i buy", "buy suggestion", "buy recommendation", "stock suggestion", "buy target"
        ]
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

        # --- Deep Research Explorer ---
        research_match = re.search(r"\b(?:deep\s+research\s+on|run\s+a\s+deep\s+research\s+paper\s+on|academic\s+research\s+on)\s+(.+)", cmd)
        if research_match:
            return {"skill": "research_prodigy", "params": {"action": "deep_research", "topic": research_match.group(1).strip()}, "domain": "general"}

        # --- Vision Tracker ---
        if any(p in cmd for p in ["detect objects", "what objects", "what's in the room"]):
            return {"skill": "vision_tracker", "params": {"action": "detect_objects"}, "domain": "general"}
        if any(p in cmd for p in ["analyze fatigue", "check my stress", "am i tired", "check fatigue"]):
            return {"skill": "vision_tracker", "params": {"action": "analyze_fatigue"}, "domain": "general"}
        if any(p in cmd for p in ["see me", "tell me what i've wore", "what am i wearing", "analyze appearance", "matching colors on me"]):
            return {"skill": "vision_tracker", "params": {"action": "analyze_appearance"}, "domain": "general"}

        # --- Productivity Presentations ---
        slide_mod_match = re.search(r"\b(?:modify|change|edit|update|replace)\s+(?:the\s+)?slide\s+(\d+)\b", cmd)
        if not slide_mod_match:
            slide_mod_match = re.search(r"\bslide\s+(\d+)\s+(?:ka|ko)\s+(?:content|image|layout|text)?\s*(?:change|modify|update|edit|replace)\b", cmd)
        if not slide_mod_match:
            this_slide_match = re.search(r"\b(?:modify|change|edit|update|replace)\s+(?:this|active|current)\s+slide\b", cmd)
            if this_slide_match:
                return {"skill": "productivity", "params": {"action": "modify_presentation_slide", "slide_num": None, "query": cmd}, "domain": "general"}
        if slide_mod_match:
            return {"skill": "productivity", "params": {"action": "modify_presentation_slide", "slide_num": int(slide_mod_match.group(1)), "query": cmd}, "domain": "general"}

        pres_match = re.search(r"\b(?:make|create|build|generate|design)\s+(?:a\s+)?(?:presentation|ppt|slides?|prezentation)\s+(?:on|about|for|of)?\s*(.+)", cmd)
        if not pres_match:
            pres_match = re.search(r"\b(.+?)\s+(?:par|pe)\s+(?:presentation|ppt|slides?|prezentation)\s+(?:banana|banao|banado|banaye|create|make|design)\b", cmd)
        if pres_match:
            topic = pres_match.group(1).strip()
            topic = re.sub(r"\b(?:hai|please|plz|for\s+the\s+business|business\s+ke\s+liye|so\s+let\s+me\s+make\s+it)\b", "", topic).strip()
            
            # Extract slide count if specified
            slide_count = None
            count_match = re.search(r"(\d+)\s*(?:pages|slides|page|slide)", cmd)
            if count_match:
                slide_count = int(count_match.group(1))
                
            # Extract presenter name if specified
            presenter_name = None
            pres_name_match = re.search(r"(?:presented by|by)\s+([a-zA-Z]+)", cmd)
            if pres_name_match:
                presenter_name = pres_name_match.group(1).strip().capitalize()
                
            return {
                "skill": "productivity",
                "params": {
                    "action": "create_presentation",
                    "title": topic,
                    "slide_count": slide_count,
                    "presenter": presenter_name
                },
                "domain": "general"
            }

        # --- Product Price Comparison ---
        # Match: "compare/find/buy [product] under [budget]" (with or without INR/rupees)
        price_budget_match = re.search(r"(?:compare|find|buy|search\s+for)\s+(.+?)\s+under\s+(\d+)", cmd)
        if price_budget_match:
            return {"skill": "product_comparison", "params": {"query": price_budget_match.group(1).strip(), "budget": int(price_budget_match.group(2))}, "domain": "general"}
            
        # Match: "compare prices for/price of [product]"
        if cmd.startswith("compare prices for ") or cmd.startswith("compare price for "):
            item = cmd.replace("compare prices for ", "").replace("compare price for ", "").strip()
            return {"skill": "product_comparison", "params": {"query": item, "budget": None}, "domain": "general"}

        # --- Food Ordering & Comparison ---
        # Match: "order [food]"
        if cmd.startswith("order "):
            dish = cmd.replace("order ", "").strip()
            return {"skill": "food_ordering", "params": {"query": dish}, "domain": "general"}
            
        # Match: "compare food prices for/find [dish] nearby/near me"
        food_match = re.search(r"(?:compare\s+food\s+prices?\s+(?:for\s+)?|find\s+)(.+?)\s+(?:nearby|near\s+me)", cmd)
        if food_match:
            return {"skill": "food_ordering", "params": {"query": food_match.group(1).strip()}, "domain": "general"}
            
        # Match: "search zomato/swiggy for [dish]"
        if "zomato" in cmd or "swiggy" in cmd:
            dish_match = re.search(r"(?:search\s+)?(?:zomato|swiggy)(?:\s+for\s+)?(.+)", cmd)
            if dish_match:
                return {"skill": "food_ordering", "params": {"query": dish_match.group(1).strip()}, "domain": "general"}

        # --- Image Editor (GIMP / Inkscape / Pillow) ---
        # Background removal
        if any(p in cmd for p in ["background remove", "remove background", "bg remove", "background hata", "bg hata do", "pichla hata"]):
            img_match = re.search(r"(?:image|photo|pic|picture|file)\s+([^\s]+\.\w+)", cmd)
            inp = img_match.group(1) if img_match else ""
            return {"skill": "image_editor", "params": {"action": "remove_background", "input_path": inp}, "domain": "general"}

        # Resize
        resize_match = re.search(r"(?:resize|size\s+change|bada\s+karo|chota\s+karo)\s+(?:image|photo|pic)?.*?(\d+)\s*[xX×]\s*(\d+)", cmd)
        if not resize_match:
            resize_match = re.search(r"(?:image|photo|pic)\s+(?:ko\s+)?(\d+)\s*[xX×]\s*(\d+)\s+(?:mein|ka|resize)", cmd)
        if resize_match:
            return {"skill": "image_editor", "params": {"action": "resize", "width": int(resize_match.group(1)), "height": int(resize_match.group(2))}, "domain": "general"}

        # Format conversion
        fmt_match = re.search(r"(?:convert|badlo|change)\s+(?:image|photo|pic|file)?\s*(?:ko\s+)?(?:from\s+\w+\s+to\s+|to\s+|mein\s+)(png|jpg|jpeg|webp|bmp|tiff|gif)\b", cmd)
        if fmt_match:
            return {"skill": "image_editor", "params": {"action": "convert_format", "output_format": fmt_match.group(1)}, "domain": "general"}

        # Grayscale / Black & White
        if any(p in cmd for p in ["grayscale", "black and white", "black & white", "bw karo", "b&w", "black white", "kala safed"]):
            return {"skill": "image_editor", "params": {"action": "grayscale"}, "domain": "general"}

        # Blur
        blur_match = re.search(r"(?:blur|dhundla)\s+(?:karo|kar|apply)?.*?(?:radius\s+)?(\d+)?", cmd)
        if blur_match and any(p in cmd for p in ["blur", "dhundla"]):
            radius = int(blur_match.group(1)) if blur_match.group(1) else 5
            return {"skill": "image_editor", "params": {"action": "blur", "radius": radius}, "domain": "general"}

        # Sharpen
        if any(p in cmd for p in ["sharpen", "sharp karo", "tez karo"]):
            return {"skill": "image_editor", "params": {"action": "sharpen"}, "domain": "general"}

        # Rotate
        rotate_match = re.search(r"(?:rotate|ghuma|palta)\s+(?:image|photo)?\s*(?:by\s+)?(\d+)\s*(?:degree|°)?", cmd)
        if rotate_match:
            return {"skill": "image_editor", "params": {"action": "rotate", "degrees": int(rotate_match.group(1))}, "domain": "general"}

        # Watermark
        wm_match = re.search(r"(?:watermark|paani\s+nishan|brand)\s+(?:add\s+karo|lagao|dalo)?\s*['\"]?([^'\"]+)['\"]?", cmd)
        if wm_match and any(p in cmd for p in ["watermark", "brand lagao"]):
            return {"skill": "image_editor", "params": {"action": "watermark", "watermark_text": wm_match.group(1).strip()}, "domain": "general"}

        # Image info
        if any(p in cmd for p in ["image info", "photo info", "image size", "resolution kya", "dimensions kya"]):
            return {"skill": "image_editor", "params": {"action": "image_info"}, "domain": "general"}

        # Tools status
        if any(p in cmd for p in ["tools status", "check tools", "gimp hai", "inkscape hai", "creative tools"]):
            return {"skill": "image_editor", "params": {"action": "check_tools"}, "domain": "general"}

        # SVG → PNG
        if re.search(r"svg\s+(?:ko\s+)?png\s+(?:mein\s+)?(?:export|convert|badlo)", cmd) or "svg to png" in cmd:
            svg_match = re.search(r"([^\s]+\.svg)", cmd)
            inp = svg_match.group(1) if svg_match else ""
            dpi_match = re.search(r"(\d+)\s*(?:dpi|resolution)", cmd)
            dpi = int(dpi_match.group(1)) if dpi_match else 300
            return {"skill": "image_editor", "params": {"action": "svg_to_png", "input_path": inp, "dpi": dpi}, "domain": "general"}

        # SVG → PDF
        if re.search(r"svg\s+(?:ko\s+)?pdf\s+(?:mein\s+)?(?:export|convert|badlo)", cmd) or "svg to pdf" in cmd:
            svg_match = re.search(r"([^\s]+\.svg)", cmd)
            inp = svg_match.group(1) if svg_match else ""
            return {"skill": "image_editor", "params": {"action": "svg_to_pdf", "input_path": inp}, "domain": "general"}

        # PNG/image → SVG (trace)
        if re.search(r"(?:png|image|photo)\s+(?:ko\s+)?svg\s+(?:mein\s+)?(?:trace|convert|badlo)", cmd) or "png to svg" in cmd or "image to vector" in cmd:
            img_match = re.search(r"([^\s]+\.(?:png|jpg|jpeg))", cmd)
            inp = img_match.group(1) if img_match else ""
            return {"skill": "image_editor", "params": {"action": "png_to_svg", "input_path": inp}, "domain": "general"}

        return None



    def route(self, text: str, active_presentation_topic: str = None) -> dict:
        """Return routing dict: {skill, params, domain}"""
        # Step 0: Check for ambiguous inputs
        cmd_lower = text.lower()
        words = cmd_lower.split()
        
        # Check A: log vs lock
        if ("log" in words or "logging" in words) and any(w in words for w in ["laptop", "pc", "screen", "system", "computer"]):
            logger.info("Routed to ambiguous intercept: 'log' vs 'lock'")
            return {
                "skill": "ambiguous",
                "params": {
                    "word": "log",
                    "options": [
                        {"label": "Lock the laptop screen", "command": "lock the laptop"},
                        {"label": "Write a Python logging script", "command": "write python logging script"}
                    ]
                },
                "domain": "general",
                "confidence": 0.4
            }

        # Step 1: Check fast regex routes
        regex_result = self._regex_route(text, active_presentation_topic)
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
                format="json",
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
