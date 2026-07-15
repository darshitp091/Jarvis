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
                    logger.info(f"Spotify API search: '{clean_search_query}'")

                    # Fetch user's market once to avoid 403 on top-tracks (deprecated country='US')
                    try:
                        user_market = sp.current_user().get("country", "IN")
                    except Exception:
                        user_market = "IN"

                    KNOWN_ARTISTS = [
                        "arijit singh", "shreya ghoshal", "sonu nigam", "lata mangeshkar",
                        "a r rahman", "ar rahman", "kishore kumar", "kumar sanu", "udit narayan",
                        "pritam", "vishal shekhar", "amit trivedi", "shankar ehsaan loy",
                        "taylor swift", "ed sheeran", "the weeknd", "drake", "eminem",
                        "coldplay", "imagine dragons", "linkin park", "one direction",
                        "bts", "blackpink", "lofi", "lo-fi", "lo fi",
                    ]
                    is_artist_query = clean_search_query.lower() in KNOWN_ARTISTS

                    # Resolve active device
                    device_id = None
                    devices = sp.devices()
                    if devices and devices.get("devices"):
                        for d in devices["devices"]:
                            if d["is_active"]:
                                device_id = d["id"]
                                break
                        if not device_id:
                            device_id = devices["devices"][0]["id"]

                    if not device_id:
                        logger.warning("No active Spotify device. Opening app and waiting...")
                        os.startfile("spotify:")
                        time.sleep(4.0)
                        devices = sp.devices()
                        if devices and devices.get("devices"):
                            device_id = devices["devices"][0]["id"]

                    if is_artist_query:
                        # Artist mode — search artist then play their top tracks
                        artist_results = sp.search(q=clean_search_query, limit=1, type="artist")
                        if artist_results and artist_results["artists"]["items"]:
                            artist = artist_results["artists"]["items"][0]
                            artist_id = artist["id"]
                            artist_name = artist["name"]
                            try:
                                # Pass user's own market to avoid 403 (deprecated country param)
                                top_data = sp.artist_top_tracks(artist_id, country=user_market)
                                playback_uris = [t["uri"] for t in top_data["tracks"][:15]]
                            except Exception as tt_err:
                                logger.warning(f"artist_top_tracks failed ({tt_err}), using artist radio instead.")
                                # Fallback: search top 5 tracks by artist name
                                r = sp.search(q=f"artist:{clean_search_query}", limit=10, type="track", market=user_market)
                                playback_uris = [t["uri"] for t in r["tracks"]["items"]] if r and r["tracks"]["items"] else []

                            if playback_uris and device_id:
                                sp.start_playback(device_id=device_id, uris=playback_uris)
                                logger.success(f"Playing top tracks of '{artist_name}' via API.")
                                return f"Playing top tracks of {artist_name} on Spotify, sir."
                        is_artist_query = False  # fall through to track mode

                    if not is_artist_query:
                        # Track mode — search by song title
                        results = sp.search(q=clean_search_query, limit=1, type="track", market=user_market)
                        if results and results["tracks"]["items"]:
                            track = results["tracks"]["items"][0]
                            track_uri = track["uri"]
                            track_name = track["name"]
                            artist_name = track["artists"][0]["name"]

                            if device_id:
                                # Queue: play requested track first, then artist's other top tracks
                                try:
                                    artist_id = track["artists"][0]["id"]
                                    top_data = sp.artist_top_tracks(artist_id, country=user_market)
                                    related = [t["uri"] for t in top_data["tracks"] if t["uri"] != track_uri]
                                    playback_uris = [track_uri] + related[:10]
                                    logger.info(f"Queue: {len(playback_uris)} tracks from '{artist_name}'.")
                                except Exception as queue_err:
                                    logger.warning(f"Top-tracks queue failed ({queue_err}). Single track only.")
                                    playback_uris = [track_uri]

                                sp.start_playback(device_id=device_id, uris=playback_uris)
                                logger.success(f"Playing '{track_name}' via Spotify API.")
                                clean_t = track_name.split("|")[0].split("-")[0].strip()
                                if len(clean_t) > 35:
                                    return f"Playing '{artist_name}' on Spotify, sir."
                                return f"Playing '{clean_t}' by {artist_name} on Spotify, sir."
                        else:
                            logger.warning(f"No tracks found for '{clean_search_query}'. Trying GUI fallback...")

                except Exception as api_err:
                    logger.error(f"Spotify API error: {api_err}. Falling back to GUI.")
                    # Only disable API mode for auth/plan errors, not temporary 5xx
                    err_str = str(api_err)
                    if "403" in err_str and "top-tracks" not in err_str:
                        logger.warning("Disabling Spotify API mode (Premium/auth error).")
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

        # 3. GUI Fallback — Spotify URI search + pyautogui double-click first result
        # Strategy: open spotify:search:<query> URI (reliable, no Ctrl+K timing issues),
        # wait for results to load, then double-click the first track card.
        logger.info(f"GUI fallback: spotify:search URI for '{clean_search_query}'")
        import pyperclip

        try:
            # Open Spotify search page directly via URI scheme
            encoded_query = urllib.parse.quote(clean_search_query)
            os.startfile(f"spotify:search:{encoded_query}")
            time.sleep(3.0)  # Wait for Spotify to load search results

            # Re-fetch Spotify window after URI open
            if not spotify_window:
                try:
                    import psutil as _ps
                    d2 = Desktop(backend="win32")
                    for w in d2.windows():
                        if "chrome_widgetwin" in w.element_info.class_name.lower():
                            proc = _ps.Process(w.process_id())
                            if proc.name().lower() == "spotify.exe":
                                spotify_window = w
                                break
                except Exception:
                    pass

            if spotify_window:
                # Bring Spotify to front
                hwnd = spotify_window.handle
                ctypes.windll.user32.ShowWindow(hwnd, 9)
                ctypes.windll.user32.SetForegroundWindow(hwnd)
                time.sleep(0.6)

                rect = spotify_window.rectangle()
                win_left = rect.left
                win_top = rect.top
                win_w = rect.width()
                win_h = rect.height()

                # ── Strategy A: Tab through results and press Enter to play ──
                # Spotify search results: first focusable track is reachable via Tab
                # Press Tab several times to land on the first song row, then Enter
                pyautogui.click(win_left + win_w // 2, win_top + win_h // 2)
                time.sleep(0.2)

                # Tab into the results grid (typically 3-5 tabs to reach first song)
                for _ in range(6):
                    pyautogui.press('tab')
                    time.sleep(0.08)
                pyautogui.press('enter')  # Play first result
                time.sleep(2.5)

                # ── Verify via API ──────────────────────────────────────────
                if self.use_api:
                    sp = self._get_sp()
                    if sp:
                        try:
                            playback = sp.current_playback()
                            if playback and playback.get("is_playing"):
                                now = playback["item"]["name"]
                                art = playback["item"]["artists"][0]["name"]
                                logger.success(f"GUI fallback confirmed playing: {now} by {art}")
                                return f"Playing '{now}' by {art} on Spotify, sir."
                        except Exception:
                            pass

                # ── Strategy B: Scan window for first track row and double-click ──
                # Sample a vertical strip at ~25% from left (track name column) and
                # find the first non-background row below the search header
                logger.info("Tab+Enter did not start playback. Trying coordinate double-click...")
                screenshot = pyautogui.screenshot()
                scan_x = win_left + int(win_w * 0.25)
                # Start scanning from ~35% down the window (below search bar/header)
                scan_y_start = win_top + int(win_h * 0.35)
                scan_y_end   = win_top + int(win_h * 0.75)

                clicked = False
                prev_row_color = None
                for y in range(scan_y_start, scan_y_end, 3):
                    r, g, b = screenshot.getpixel((min(scan_x, screenshot.width - 1), min(y, screenshot.height - 1)))
                    # Spotify track rows have a slightly lighter bg than the dark sidebar
                    # Look for a row that's noticeably non-black (content area)
                    brightness = (r + g + b) / 3
                    if brightness > 30:  # found content area
                        # Double-click the beginning of this track row to play it
                        click_x = win_left + int(win_w * 0.25)
                        pyautogui.doubleClick(click_x, y)
                        logger.info(f"Double-clicked first track row at ({click_x}, {y})")
                        clicked = True
                        time.sleep(2.0)
                        break

                if clicked and self.use_api:
                    sp = self._get_sp()
                    if sp:
                        try:
                            playback = sp.current_playback()
                            if playback and playback.get("is_playing"):
                                now = playback["item"]["name"]
                                art = playback["item"]["artists"][0]["name"]
                                return f"Playing '{now}' by {art} on Spotify, sir."
                        except Exception:
                            pass

            return f"Opened Spotify search for '{clean_search_query}', sir. Please double-click a track to play."

        except Exception as gui_err:
            logger.error(f"GUI fallback completely failed: {gui_err}")
            return f"I couldn't play '{clean_search_query}' on Spotify, sir."

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
