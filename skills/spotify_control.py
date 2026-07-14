import os
import time
import pyautogui
import platform
import urllib.parse
import ctypes
from loguru import logger
from pywinauto import Desktop

# Ensure DPI Awareness on Windows to align PyAutoGUI coordinates correctly on scaled screens
if platform.system() == "Windows":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

class SpotifyControl:
    """Controls Spotify playback natively or via the official Spotify Web API SDK"""

    CACHE_PATH = ".cache-jarvis-spotify"

    def __init__(self, config_path: str = "config/settings.yaml"):
        # Resolve config path gracefully
        if not os.path.exists(config_path):
            fallback = os.path.join(os.path.dirname(__file__), "..", config_path)
            if os.path.exists(fallback):
                config_path = fallback

        self.client_id = None
        self.client_secret = None
        self.redirect_uri = "http://localhost:8888/callback"
        self.use_api = False
        self._sp = None  # cached Spotipy client

        try:
            import yaml
            if os.path.exists(config_path):
                with open(config_path) as f:
                    config_data = yaml.safe_load(f)
                    spot_config = config_data.get("spotify", {})
                    self.client_id = spot_config.get("client_id")
                    self.client_secret = spot_config.get("client_secret")
                    self.redirect_uri = spot_config.get("redirect_uri", "http://localhost:8888/callback")
                    self.api_enabled = spot_config.get("api_enabled", True)

                    if self.client_id and self.client_secret and self.api_enabled:
                        if "your_client_id" not in self.client_id.lower() and "your_client_secret" not in self.client_secret.lower():
                            self.use_api = True
                            logger.info("Spotify API credentials loaded. Attempting cached auth...")
                            # Try to restore from cache silently on startup
                            self._sp = self._get_spotify_client(silent=True)
                            if self._sp:
                                logger.success("Spotify API authenticated from cached token.")
                            else:
                                logger.warning("No cached Spotify token found. Run one-time auth to enable API mode.")
                                self.use_api = False
        except Exception as e:
            logger.warning(f"SpotifyControl failed to load config: {e}")

    # ─────────────────────────────────────────────────────────────
    # ONE-TIME AUTH SETUP
    # ─────────────────────────────────────────────────────────────
    def run_one_time_auth(self) -> bool:
        """Opens browser for one-time Spotify OAuth authorization and saves token to disk cache.
        After this runs successfully once, JARVIS will never need to open a browser again."""
        try:
            import spotipy
            from spotipy.oauth2 import SpotifyOAuth

            logger.info("Starting one-time Spotify OAuth setup. Opening browser...")
            print("\n" + "="*60)
            print("  JARVIS: One-Time Spotify Authorization Required")
            print("  Please authorize in the browser window that opens.")
            print("="*60 + "\n")

            auth_manager = SpotifyOAuth(
                client_id=self.client_id,
                client_secret=self.client_secret,
                redirect_uri=self.redirect_uri,
                scope="user-modify-playback-state user-read-playback-state user-read-currently-playing",
                cache_path=self.CACHE_PATH,
                open_browser=True,
            )
            # This will open the browser and block until the user authorizes
            token_info = auth_manager.get_access_token(as_dict=True)
            if token_info:
                self._sp = spotipy.Spotify(auth_manager=auth_manager)
                self.use_api = True
                logger.success("One-time Spotify auth completed! Token cached to disk permanently.")
                print("\n✅ Spotify authorized successfully! JARVIS will remember this forever.\n")
                return True
            return False
        except Exception as e:
            logger.error(f"One-time Spotify auth failed: {e}")
            return False

    def _get_spotify_client(self, silent: bool = False):
        """Returns a cached Spotipy client. Uses disk-cached token silently if available."""
        try:
            import spotipy
            from spotipy.oauth2 import SpotifyOAuth

            auth_manager = SpotifyOAuth(
                client_id=self.client_id,
                client_secret=self.client_secret,
                redirect_uri=self.redirect_uri,
                scope="user-modify-playback-state user-read-playback-state user-read-currently-playing",
                cache_path=self.CACHE_PATH,
                open_browser=False,  # Never open browser automatically
            )

            cached_token = auth_manager.get_cached_token()
            if not cached_token:
                if not silent:
                    logger.warning("No cached Spotify token found. Please run one-time auth.")
                return None

            # Refresh expired token automatically
            if auth_manager.is_token_expired(cached_token):
                logger.info("Spotify token expired — refreshing silently...")
                cached_token = auth_manager.refresh_access_token(cached_token["refresh_token"])

            sp = spotipy.Spotify(auth_manager=auth_manager)
            # Quick connection test
            sp.current_user()
            return sp
        except Exception as e:
            if not silent:
                logger.error(f"Failed to initialize Spotipy client: {e}")
            return None

    def _get_sp(self):
        """Returns the cached Spotipy client, refreshing if needed."""
        if self._sp is None and self.use_api:
            self._sp = self._get_spotify_client(silent=False)
        return self._sp

    # ─────────────────────────────────────────────────────────────
    # INTELLIGENT QUERY EXTRACTOR
    # ─────────────────────────────────────────────────────────────
    def _extract_search_query(self, raw_query: str) -> str:
        """Strips Hinglish/English filler words from spoken queries and returns
        a clean, precise search term for Spotify search.

        Examples:
          "agar Lofi focus track ready hai toh fir kuch Lofi song baza do" → "Lofi"
          "Arijit Singh ke gaane bajao" → "Arijit Singh"
          "Tum Hi Ho bajao" → "Tum Hi Ho"
          "play some Coldplay songs" → "Coldplay"
        """
        import re

        # Filler tokens that should be stripped (Hinglish + English)
        # NOTE: 'tum', 'ho', 'hai' etc. are intentionally excluded because they appear in real song titles
        FILLER_TOKENS = {
            "agar", "toh", "fir", "kuch", "ka", "ke", "ki", "gaane", "gaana",
            "bajao", "baza", "baja", "do", "play", "chalao", "laga", "lagao", "wala",
            "type", "songs", "song", "music", "karo", "de", "na", "please", "zara",
            "yaar", "sun", "sunao", "bana", "ek", "aur", "suno", "ab",
            "chalo", "chala", "abhi", "mujhe", "some", "a", "an", "the",
            "ready", "track", "focus", "koi", "acche", "acchi", "ache", "se",
            "raha", "rahi", "main", "mein", "latest", "new", "best",
        }

        # Common artist patterns — if we detect these, keep the full name
        KNOWN_ARTISTS = [
            "arijit singh", "shreya ghoshal", "sonu nigam", "lata mangeshkar",
            "a r rahman", "ar rahman", "kishore kumar", "kumar sanu", "udit narayan",
            "pritam", "vishal shekhar", "amit trivedi", "shankar ehsaan loy",
            "taylor swift", "ed sheeran", "the weeknd", "drake", "eminem",
            "coldplay", "imagine dragons", "linkin park", "one direction",
            "bts", "blackpink", "lofi", "lo-fi", "lo fi",
        ]

        query_lower = raw_query.lower().strip()

        # Check for known artist names first — return them directly
        for artist in KNOWN_ARTISTS:
            if artist in query_lower:
                # Capitalize properly
                return " ".join(w.capitalize() for w in artist.split())

        # Tokenize and strip ONLY leading and trailing filler words
        # (preserve middle words that may be part of a song/album title like "Tum Hi Ho")
        words = re.findall(r"[a-zA-Z']+", raw_query)
        # Strip leading fillers
        while words and words[0].lower() in FILLER_TOKENS:
            words.pop(0)
        # Strip trailing fillers
        while words and words[-1].lower() in FILLER_TOKENS:
            words.pop()

        if words:
            extracted = " ".join(words)
            # If still too long (>5 words), keep first 4 meaningful words
            extracted_words = extracted.split()
            if len(extracted_words) > 4:
                extracted = " ".join(extracted_words[:4])
            logger.debug(f"Extracted search query: '{extracted}' from raw: '{raw_query}'")
            return extracted

        # Fallback: return raw query trimmed
        return raw_query.strip()

    def is_actually_playing(self) -> bool:
        """Uses Spotify Web API to definitively check if audio is actively playing."""
        try:
            sp = self._get_sp()
            if sp:
                playback = sp.current_playback()
                if playback and playback.get("is_playing"):
                    logger.debug(f"API confirms playback active: {playback['item']['name']}")
                    return True
                return False
        except Exception as e:
            logger.warning(f"Could not verify playback via API: {e}")
        return False

    def _click_green_play_button(self, spotify_window) -> bool:
        try:
            import pyautogui
            rect = spotify_window.rectangle()
            wx, wy, w_width, w_height = rect.left, rect.top, rect.width(), rect.height()

            screenshot = pyautogui.screenshot()

            start_x = int(wx + w_width * 0.2)
            end_x = int(wx + w_width * 0.75)
            start_y = int(wy + w_height * 0.25)
            end_y = int(wy + w_height * 0.7)

            screen_w, screen_h = pyautogui.size()
            start_x = max(0, min(start_x, screen_w - 1))
            end_x = max(0, min(end_x, screen_w - 1))
            start_y = max(0, min(start_y, screen_h - 1))
            end_y = max(0, min(end_y, screen_h - 1))

            green_pixels = []
            for x in range(start_x, end_x, 4):
                for y in range(start_y, end_y, 4):
                    r, g, b = screenshot.getpixel((x, y))
                    if r < 60 and 140 < g < 230 and 50 < b < 150:
                        green_pixels.append((x, y))

            if len(green_pixels) >= 8:
                avg_x = sum(p[0] for p in green_pixels) // len(green_pixels)
                avg_y = sum(p[1] for p in green_pixels) // len(green_pixels)
                pyautogui.click(avg_x, avg_y)
                logger.info(f"Clicked green Play button at ({avg_x}, {avg_y}) [Cluster size: {len(green_pixels)}]")
                return True
            else:
                logger.warning(f"Could not find green Play button via color search (found {len(green_pixels)} candidate pixels).")
                return False
        except Exception as e:
            logger.error(f"Error in _click_green_play_button: {e}")
            return False

    def play_song(self, query: str) -> str:
        is_windows = platform.system() == "Windows"
        if not is_windows:
            return "Spotify automation is only supported on Windows, sir."

        logger.info(f"Opening Spotify and playing: {query}")

        query_clean = query.lower().strip() if query else ""
        is_liked_songs = query_clean in [
            "liked songs", "my liked songs", "liked playlist", "liked song",
            "music", "song", "some music", "some song", "songs", "some songs",
            "gaana", "gaane", "music chalao", "song bajao", "gaana bajao",
            "tum bas song bajao", "bas song bajao", "song chalao", "gaana chalao",
            "play music", "play song", "play gaana", "play some songs"
        ]

        # Extract a clean search term from the raw spoken query
        clean_search_query = self._extract_search_query(query) if not is_liked_songs else query

        # 1. Ensure local Spotify client app is running
        import psutil
        spotify_running = False
        for proc in psutil.process_iter(['name']):
            try:
                if proc.info['name'] and proc.info['name'].lower() == "spotify.exe":
                    spotify_running = True
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        if not spotify_running:
            logger.info("Spotify is not running. Launching desktop client...")
            try:
                if is_liked_songs:
                    os.startfile("spotify:collection:tracks")
                else:
                    os.startfile("spotify:")
                time.sleep(5.0)
            except Exception as e:
                logger.error(f"Failed to launch Spotify app: {e}")
        else:
            if is_liked_songs:
                try:
                    os.startfile("spotify:collection:tracks")
                    time.sleep(2.5)
                except Exception as e:
                    logger.error(f"Failed to open Liked Songs URI: {e}")

        # 2. API Mode Playback
        if self.use_api and not is_liked_songs:
            sp = self._get_sp()
            if sp:
                try:
                    # Search using the extracted clean query (not the raw sentence)
                    logger.info(f"Spotify API search: '{clean_search_query}'")
                    results = sp.search(q=clean_search_query, limit=1, type="track")
                    if results and results["tracks"]["items"]:
                        track = results["tracks"]["items"][0]
                        track_uri = track["uri"]
                        track_name = track["name"]
                        artist_name = track["artists"][0]["name"]

                        devices = sp.devices()
                        device_id = None
                        if devices and devices.get("devices"):
                            for d in devices["devices"]:
                                if d["is_active"]:
                                    device_id = d["id"]
                                    break
                            if not device_id:
                                device_id = devices["devices"][0]["id"]

                        if device_id:
                            try:
                                artist_id = track["artists"][0]["id"]
                                top_tracks = sp.artist_top_tracks(artist_id)
                                related_uris = [t["uri"] for t in top_tracks["tracks"] if t["uri"] != track_uri]
                                playback_uris = [track_uri] + related_uris[:10]
                                logger.info(f"Populated playback queue with {len(playback_uris)} tracks from artist '{artist_name}'.")
                            except Exception as queue_err:
                                logger.warning(f"Failed to fetch artist top tracks: {queue_err}. Defaulting to single track.")
                                playback_uris = [track_uri]

                            sp.start_playback(device_id=device_id, uris=playback_uris)
                            logger.success(f"Started playing '{track_name}' via Spotify API.")
                            clean_t = track_name.split("|")[0].split("-")[0].strip()
                            if len(clean_t) > 35:
                                return f"Playing '{artist_name}' on Spotify, sir."
                            return f"Playing '{clean_t}' by {artist_name} on Spotify, sir."
                        else:
                            logger.warning("No active Spotify device found. Opening Spotify app...")
                            os.startfile("spotify:")
                            time.sleep(4.0)
                            # Retry device lookup once
                            devices = sp.devices()
                            if devices and devices.get("devices"):
                                device_id = devices["devices"][0]["id"]
                                sp.start_playback(device_id=device_id, uris=[track_uri])
                                return f"Playing '{track_name}' by {artist_name} on Spotify, sir."
                    else:
                        logger.warning(f"No tracks found matching '{clean_search_query}' via API. Trying GUI search...")
                except Exception as api_err:
                    logger.error(f"Spotify API playback error: {api_err}. Falling back to keyboard controls.")
                    if "403" in str(api_err) or "PREMIUM" in str(api_err).upper():
                        logger.warning("Disabling Spotify API mode due to Premium/Free limitations.")
                        self.use_api = False

        # 3. Fallback GUI Keyboard/Mouse Automation
        spotify_window = None
        try:
            d = Desktop(backend="win32")
            for w in d.windows():
                classname = w.element_info.class_name
                if "chrome_widgetwin" in classname.lower():
                    try:
                        proc = psutil.Process(w.process_id())
                        if proc.name().lower() == "spotify.exe":
                            spotify_window = w
                            break
                    except Exception:
                        pass
        except Exception as e:
            logger.warning(f"Error focusing window: {e}")

        if spotify_window:
            try:
                hwnd = spotify_window.handle
                ctypes.windll.user32.ShowWindow(hwnd, 9)
                ctypes.windll.user32.SetForegroundWindow(hwnd)
                time.sleep(0.5)
                pyautogui.press('esc')
                time.sleep(0.1)
                pyautogui.press('esc')
                time.sleep(0.3)
            except Exception as e:
                logger.warning(f"Failed to focus/prepare Spotify window: {e}")

        # Liked songs: click play button
        if is_liked_songs:
            if spotify_window:
                clicked = self._click_green_play_button(spotify_window)
                if clicked:
                    return "Playing your Liked Songs on Spotify, sir."

            try:
                if spotify_window:
                    rect = spotify_window.rectangle()
                    cx = rect.left + rect.width() // 2
                    cy = rect.top + rect.height() // 2
                    pyautogui.click(cx, cy)
                    time.sleep(0.3)
                    pyautogui.press('space')
                    return "Opened Liked Songs. Triggered playback via keyboard focus, sir."
                else:
                    pyautogui.press('space')
                    return "Opened Liked Songs. Attempted spacebar playback trigger, sir."
            except Exception as e:
                logger.error(f"Spacebar playback fallback failed: {e}")
                return "I opened your Liked Songs, sir. Please press play to start."

        # GUI fallback: Ctrl+K search using the CLEAN extracted query (not the raw sentence)
        logger.info(f"GUI Ctrl+K fallback search using clean query: '{clean_search_query}'")
        try:
            pyautogui.hotkey('ctrl', 'k')
            time.sleep(1.2)  # Wait for Quick Search overlay to mount

            import pyperclip
            pyperclip.copy(clean_search_query)  # Use extracted clean query
            time.sleep(0.1)
            pyautogui.hotkey('ctrl', 'v')
            time.sleep(1.5)  # Wait for autocomplete results

            # Navigate to first result and play
            pyautogui.press('down')
            time.sleep(0.3)
            pyautogui.press('enter')
            time.sleep(2.0)  # Wait for playback to begin

            # Verify playback via API if available
            if self.use_api:
                sp = self._get_sp()
                if sp:
                    playback = sp.current_playback()
                    if playback and playback.get("is_playing"):
                        now_playing = playback["item"]["name"]
                        artist = playback["item"]["artists"][0]["name"]
                        return f"Playing '{now_playing}' by {artist} on Spotify, sir."

            return f"Searching and playing '{clean_search_query}' on Spotify, sir."
        except Exception as e:
            logger.error(f"GUI Quick Search play failed: {e}")
            try:
                encoded_query = urllib.parse.quote(clean_search_query)
                search_uri = f"spotify:search:{encoded_query}"
                os.startfile(search_uri)
                return f"I opened Spotify and searched for '{clean_search_query}', sir."
            except Exception:
                return "I couldn't open Spotify, sir."

    def control_media(self, action: str) -> str:
        if self.use_api:
            sp = self._get_sp()
            if sp:
                try:
                    if action == "pause":
                        sp.pause_playback()
                        return "Playback paused, sir."
                    elif action == "resume":
                        sp.start_playback()
                        return "Playback resumed, sir."
                    elif action == "next":
                        sp.next_track()
                        return "Skipped to next track, sir."
                    elif action == "previous":
                        sp.previous_track()
                        return "Returned to previous track, sir."
                    elif action == "volume_up":
                        current = sp.current_playback()
                        if current and current.get("device"):
                            vol = min(100, current["device"]["volume_percent"] + 10)
                            sp.volume(vol)
                            return f"Volume set to {vol} percent, sir."
                    elif action == "volume_down":
                        current = sp.current_playback()
                        if current and current.get("device"):
                            vol = max(0, current["device"]["volume_percent"] - 10)
                            sp.volume(vol)
                            return f"Volume set to {vol} percent, sir."
                except Exception as api_err:
                    logger.error(f"API media control failed: {api_err}. Trying media keys fallback.")
                    if "403" in str(api_err) or "PREMIUM" in str(api_err).upper():
                        logger.warning("Disabling Spotify API mode due to Premium/Free limitations.")
                        self.use_api = False

        # Fallback media hotkeys
        actions = {
            "pause": "playpause",
            "resume": "playpause",
            "next": "nexttrack",
            "previous": "prevtrack",
            "volume_up": "volumeup",
            "volume_down": "volumedown"
        }
        if action in actions:
            try:
                pyautogui.press(actions[action])
                return f"Media {action} executed, sir."
            except Exception as e:
                logger.error(f"Failed to press media key: {e}")
                return "I couldn't control the media keys, sir."
        return f"Unknown playback command '{action}', sir."
