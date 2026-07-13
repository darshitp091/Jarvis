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
                    
                    # Enable API if credentials are set and not placeholders
                    if self.client_id and self.client_secret and self.api_enabled:
                        if "your_client_id" not in self.client_id and "your_client_secret" not in self.client_secret:
                            self.use_api = True
                            logger.info("Spotify API credentials loaded. Using Spotipy SDK mode.")
        except Exception as e:
            logger.warning(f"SpotifyControl failed to load config: {e}")

    def _get_spotify_client(self):
        try:
            import spotipy
            from spotipy.oauth2 import SpotifyOAuth
            
            auth_manager = SpotifyOAuth(
                client_id=self.client_id,
                client_secret=self.client_secret,
                redirect_uri=self.redirect_uri,
                scope="user-modify-playback-state user-read-playback-state"
            )
            return spotipy.Spotify(auth_manager=auth_manager)
        except Exception as e:
            logger.error(f"Failed to initialize Spotipy client: {e}")
            return None

    def _click_green_play_button(self, spotify_window) -> bool:
        try:
            import pyautogui
            rect = spotify_window.rectangle()
            wx, wy, w_width, w_height = rect.left, rect.top, rect.width(), rect.height()
            
            # Take screenshot of the screen
            screenshot = pyautogui.screenshot()
            
            # Scan only the center region of the Spotify window
            # X: from 20% to 75% of window width
            # Y: from 25% to 70% of window height
            start_x = int(wx + w_width * 0.2)
            end_x = int(wx + w_width * 0.75)
            start_y = int(wy + w_height * 0.25)
            end_y = int(wy + w_height * 0.7)
            
            # Bound check
            screen_w, screen_h = pyautogui.size()
            start_x = max(0, min(start_x, screen_w - 1))
            end_x = max(0, min(end_x, screen_w - 1))
            start_y = max(0, min(start_y, screen_h - 1))
            end_y = max(0, min(end_y, screen_h - 1))
            
            green_pixels = []
            for x in range(start_x, end_x, 4): # Step by 4 pixels for speed
                for y in range(start_y, end_y, 4):
                    r, g, b = screenshot.getpixel((x, y))
                    # Spotify green matches: r < 60, 140 < g < 230, 50 < b < 150
                    if r < 60 and 140 < g < 230 and 50 < b < 150:
                        green_pixels.append((x, y))
            
            # Ensure it is a significant cluster (a button, not a single stray pixel)
            if len(green_pixels) >= 8:
                # Find the average coordinate (center of the play button)
                avg_x = sum(p[0] for p in green_pixels) // len(green_pixels)
                avg_y = sum(p[1] for p in green_pixels) // len(green_pixels)
                
                # Move mouse and click
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
                time.sleep(5.0) # Wait for device initialization
            except Exception as e:
                logger.error(f"Failed to launch Spotify app: {e}")
        else:
            if is_liked_songs:
                try:
                    os.startfile("spotify:collection:tracks")
                    time.sleep(2.5)
                except Exception as e:
                    logger.error(f"Failed to open Liked Songs URI: {e}")

        # 2. API Mode Playback (Skip if liked songs since it requires special handling)
        if self.use_api and not is_liked_songs:
            sp = self._get_spotify_client()
            if sp:
                try:
                    # Search for track query
                    results = sp.search(q=query, limit=1, type="track")
                    if results and results["tracks"]["items"]:
                        track = results["tracks"]["items"][0]
                        track_uri = track["uri"]
                        track_name = track["name"]
                        artist_name = track["artists"][0]["name"]
                        
                        # Find active or available device
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
                            # Retrieve artist's top tracks to populate the queue for autoplays/skips
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
                            clean_t = track_name
                            if len(clean_t) > 40:
                                clean_t = clean_t.split("|")[0].split("-")[0].strip()
                            if len(clean_t) > 30:
                                return "Playing the track on Spotify, sir."
                            return f"Playing '{clean_t}' by {artist_name} on Spotify, sir."
                    else:
                        logger.warning(f"No tracks found matching '{query}' via API. Trying GUI search...")
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
                # Force restore and focus using Win32 API
                hwnd = spotify_window.handle
                ctypes.windll.user32.ShowWindow(hwnd, 9)  # 9 = SW_RESTORE
                ctypes.windll.user32.SetForegroundWindow(hwnd)
                time.sleep(0.5)
                
                # Dismiss any promo cards or splash ads
                pyautogui.press('esc')
                time.sleep(0.1)
                pyautogui.press('esc')
                time.sleep(0.3)
            except Exception as e:
                logger.warning(f"Failed to focus/prepare Spotify window: {e}")

        # If liked songs command, click play button
        if is_liked_songs:
            if spotify_window:
                clicked = self._click_green_play_button(spotify_window)
                if clicked:
                    return "Playing your Liked Songs on Spotify, sir."
            
            # Keyboard fallback for Liked Songs if click failed
            try:
                # Click in the middle of the window to gain keyboard focus, then press Space
                if spotify_window:
                    rect = spotify_window.rectangle()
                    cx = rect.left + rect.width() // 2
                    cy = rect.top + rect.height() // 2
                    pyautogui.click(cx, cy)
                    time.sleep(0.3)
                    pyautogui.press('space')
                    return "Opened Liked Songs. Triggered playback via keyboard focus, sir."
                else:
                    # Generic press space fallback
                    pyautogui.press('space')
                    return "Opened Liked Songs. Attempted spacebar playback trigger, sir."
            except Exception as e:
                logger.error(f"Spacebar playback fallback failed: {e}")
                return "I opened your Liked Songs, sir. Please press play to start."

        # Otherwise, search and play specific song using Ctrl+K Quick Search
        try:
            # Open Quick Search
            pyautogui.hotkey('ctrl', 'k')
            time.sleep(0.5)
            
            # Type song name
            pyautogui.write(query)
            time.sleep(1.2) # Wait for search results to load
            
            # Press down arrow to highlight first track
            pyautogui.press('down')
            time.sleep(0.2)
            
            # Press enter to play
            pyautogui.press('enter')
            clean_q = query
            if len(clean_q) > 40:
                clean_q = clean_q.split("|")[0].split("-")[0].strip()
            if len(clean_q) > 30:
                return "Searching and playing the track on Spotify, sir."
            return f"Searching and playing '{clean_q}' on Spotify, sir."
        except Exception as e:
            logger.error(f"GUI Quick Search play failed: {e}")
            # Fallback to search URI
            try:
                encoded_query = urllib.parse.quote(query)
                search_uri = f"spotify:search:{encoded_query}"
                os.startfile(search_uri)
                clean_q = query
                if len(clean_q) > 40:
                    clean_q = clean_q.split("|")[0].split("-")[0].strip()
                if len(clean_q) > 30:
                    return "I opened Spotify and searched for the track, sir."
                return f"I opened Spotify and searched for '{clean_q}', sir."
            except Exception:
                return "I couldn't open Spotify, sir."

    def control_media(self, action: str) -> str:
        if self.use_api:
            sp = self._get_spotify_client()
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
