import os
import subprocess
import json
import threading
import time
from loguru import logger

class YouTubeMusicPlayer:
    """Streams audio from YouTube in the background using local yt-dlp and MPV player"""
    
    def __init__(self):
        # Locate mpv.exe inside the project's bin folder
        self.mpv_path = r"c:\Users\patel\Jarvis\bin\mpv.exe"
        if not os.path.exists(self.mpv_path):
            # Fallback path relative to this file
            fallback = os.path.join(os.path.dirname(os.path.dirname(__file__)), "bin", "mpv.exe")
            if os.path.exists(fallback):
                self.mpv_path = fallback

        self.mpv_exists = os.path.exists(self.mpv_path)
        self.process = None
        self.current_song = None
        self.is_paused = False
        
        # Unique naming base for Windows named pipes
        self.pipe_name_base = r"\\.\pipe\mpv-pipe"
        self.active_pipe_name = self.pipe_name_base
        
        self.volume = 100
        self.queue = []
        self.queue_index = 0
        self.on_song_change = None
        
        # Thread safety locks & identifiers
        self.playback_lock = threading.Lock()
        self.current_playback_id = 0
        self.is_ducked = False
        
        # Start background playback monitor
        threading.Thread(target=self._playback_monitor, daemon=True).start()
        
    def is_available(self) -> bool:
        return self.mpv_exists
        
    def _send_ipc_command(self, cmd_list: list) -> bool:
        """Sends a JSON-RPC command to MPV over the Windows named pipe."""
        # Use local ref to process and active_pipe_name to avoid race conditions
        with self.playback_lock:
            proc = self.process
            pipe_name = self.active_pipe_name
            
        if not proc:
            return False
        if proc.poll() is not None:
            return False
            
        payload = json.dumps({"command": cmd_list}) + "\n"
        
        # Retry loop to wait for the named pipe to be created by MPV
        for attempt in range(15):
            try:
                with open(pipe_name, "w") as f:
                    f.write(payload)
                return True
            except FileNotFoundError:
                time.sleep(0.04)
            except Exception as e:
                logger.debug(f"Error writing to MPV named pipe: {e}")
                break
                
        logger.debug(f"Failed to send command {cmd_list} to MPV named pipe (pipe not ready or inactive)")
        return False
            
    def _clean_title(self, title: str) -> str:
        """Cleans YouTube titles to remove metadata, tags, and brackets for natural TTS speech."""
        import re
        # Remove anything inside parenthesis or brackets
        title = re.sub(r'\([^)]*\)', '', title)
        title = re.sub(r'\[[^]]*\]', '', title)
        
        # Replace common separators with a standard dash
        title = title.replace("–", "-").replace("—", "-").replace("•", "-").replace("|", "-")
        
        # Split by dash and filter out corporate jukebox/metadata junk
        if "-" in title:
            parts = [p.strip() for p in title.split("-")]
            clean_parts = []
            for p in parts:
                p_low = p.lower()
                if any(w in p_low for w in ["jukebox", "full album", "hits", "best of", "special", "collection", "lata"]):
                    continue
                clean_parts.append(p)
            if clean_parts:
                title = " - ".join(clean_parts)
            else:
                title = parts[0]
                
        # Remove buzzwords and junk phrases case insensitively
        junk_patterns = [
            r'\b(?:official|video|audio|lyrics|lyrical|music|hd|full|album|jukebox|juke box|hits|best of|special|live|new|latest|2023|2024|2025|2026|song|songs)\b',
            r'\s+[\d\s]+\s*hits\b',
            r'\b Jukebox\b',
            r'\b Juke box\b',
            r'\b JukeBox\b'
        ]
        for pattern in junk_patterns:
            title = re.sub(pattern, '', title, flags=re.IGNORECASE)
            
        # Clean up punctuation and whitespace
        title = re.sub(r'\s+', ' ', title)
        title = title.strip().strip("-:| ")
        
        # Limit length to avoid long runs
        if len(title) > 50:
            title = title[:47] + "..."
        return title

    def _playback_monitor(self):
        """Monitors when the current song finishes naturally to advance the queue."""
        while True:
            time.sleep(1.0)
            target_index = None
            playback_id = None
            
            with self.playback_lock:
                if self.process and self.process.poll() is not None:
                    # Song finished playing naturally
                    logger.info("Background song finished playing naturally. Advancing queue...")
                    self.current_playback_id += 1
                    playback_id = self.current_playback_id
                    self.queue_index += 1
                    target_index = self.queue_index
                    self.process = None
                    
            if target_index is not None and playback_id is not None:
                if self.queue and target_index < len(self.queue):
                    threading.Thread(
                        target=self._play_queue_item_async,
                        args=(target_index, playback_id),
                        daemon=True
                    ).start()
                else:
                    with self.playback_lock:
                        self.current_song = None
                        self.is_paused = False

    def duck(self):
        """Temporarily ducks the volume of the music player."""
        with self.playback_lock:
            self.is_ducked = True
            logger.info("Ducking music volume to 35%")
            if self.process:
                # Send directly without locking to avoid deadlock
                threading.Thread(target=self.set_volume, args=(35,), daemon=True).start()

    def unduck(self):
        """Restores the music volume to its normal level."""
        with self.playback_lock:
            self.is_ducked = False
            logger.info(f"Restoring music volume to {self.volume}%")
            if self.process:
                # Send directly without locking to avoid deadlock
                threading.Thread(target=self.set_volume, args=(self.volume,), daemon=True).start()

    def _stop_song_locked(self):
        """Stops the song while holding the lock."""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=0.8)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            self.process = None
            self.current_song = None
            self.is_paused = False

    def stop_song(self) -> str:
        with self.playback_lock:
            self.current_playback_id += 1 # Cancel any active loading thread
            self._stop_song_locked()
            return "Music stopped, sir."

    def pause_song(self) -> str:
        # Pause is an IPC action, does not change process existence
        if self.process and not self.is_paused:
            if self._send_ipc_command(["set_property", "pause", True]):
                self.is_paused = True
                return "Playback paused, sir."
        return "No active music playback to pause, sir."
        
    def resume_song(self) -> str:
        # Resume is an IPC action, does not change process existence
        if self.process and self.is_paused:
            if self._send_ipc_command(["set_property", "pause", False]):
                self.is_paused = False
                return "Playback resumed, sir."
        return "No paused music playback to resume, sir."

    def _extract_artist(self, query: str, title: str) -> str:
        """Extracts artist name to assist smart queue backfilling."""
        common_artists = [
            "arijit singh", "shreya ghoshal", "karan aujla", "diljit dosanjh", 
            "jubin nautiyal", "neha kakkar", "atif aslam", "lata mangeshkar", 
            "kishore kumar", "kumar sanu", "alka yagnik", "sonu nigam", 
            "sidhu moose wala", "raftaar", "badshah", "yo yo honey singh",
            "taylor swift", "ed sheeran", "billie eilish", "drake", "weekend"
        ]
        q_lower = query.lower()
        for artist in common_artists:
            if artist in q_lower:
                return artist
                
        t_lower = title.lower()
        if " - " in title:
            part1 = title.split(" - ")[0].strip()
            if len(part1) < 25 and not any(w in part1.lower() for w in ["video", "audio", "song", "lyrics", "t-series", "t series"]):
                return part1
        return ""

    def _play_queue_item_async(self, target_index: int, playback_id: int):
        """Asynchronously extracts stream url and launches MPV player."""
        try:
            # 1. Resolve URL (heavy network I/O, done without lock)
            with self.playback_lock:
                if target_index >= len(self.queue):
                    return
                item = self.queue[target_index]
                
            title = item.get("title", "Unknown Track")
            video_url = item.get("url") or f"https://www.youtube.com/watch?v={item.get('id')}"
            
            logger.info(f"Extracting stream URL for queue item {target_index}: {title}")
            import yt_dlp
            ydl_opts = {
                'format': 'bestaudio/best',
                'noplaylist': True,
                'quiet': True,
                'nocheckcertificate': True,
                'no_warnings': True,
                'ignoreerrors': True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=False)
                stream_url = info['url']
                http_headers = info.get('http_headers', {})
                user_agent = http_headers.get('User-Agent', 'Mozilla/5.0')
                referer = http_headers.get('Referer', 'https://www.youtube.com/')
                
            clean_title = self._clean_title(title)
            safe_title = "".join(c for c in clean_title if ord(c) < 65536)
            
            # 2. Acquire lock and check if this play request is still the active one
            with self.playback_lock:
                if playback_id != self.current_playback_id:
                    logger.warning(f"Playback ID mismatch ({playback_id} != {self.current_playback_id}). Aborting play.")
                    return
                    
                # Stop any existing process cleanly
                self._stop_song_locked()
                
                # Generate unique pipe name for Windows to avoid sharing violations
                timestamp = int(time.time() * 1000)
                self.active_pipe_name = rf"\\.\pipe\mpv-pipe-{timestamp}"
                
                self.queue_index = target_index
                self.current_song = safe_title
                
                # Launch MPV process
                self.process = subprocess.Popen(
                    [
                        self.mpv_path, 
                        "--no-video",
                        f"--input-ipc-server={self.active_pipe_name}",
                        f"--user-agent={user_agent}",
                        f"--referrer={referer}",
                        stream_url
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                )
                self.is_paused = False
                
                # Set initial volume (apply ducked volume if JARVIS is currently speaking/listening)
                vol_to_set = 35 if self.is_ducked else self.volume
                logger.info(f"Subprocess MPV launched. Setting initial volume to {vol_to_set}%")
                
                # We start a helper thread to set volume asynchronously using the robust set_volume helper
                def set_vol_delayed(vol):
                    time.sleep(0.1)
                    self.set_volume(vol)
                            
                threading.Thread(target=set_vol_delayed, args=(vol_to_set,), daemon=True).start()
                
            if self.on_song_change:
                self.on_song_change("JARVIS Media Queue", f"Playing: {safe_title}")
                
        except Exception as e:
            logger.error(f"Failed to play queue item {target_index} async: {e}")
            with self.playback_lock:
                if playback_id == self.current_playback_id:
                    self.current_song = None
                    self.is_paused = False

    def play_song(self, query: str) -> str:
        if not self.mpv_exists:
            return "MPV player is not installed, sir. Please install MPV to enable background streaming."
            
        import re
        # Check if query contains volume specifications (e.g. "with 70% volume", "at 50 volume", "40 to 50 minor volume", "at max volume", "high volume")
        parsed_volume = None

        # 1. Check descriptive adjectives (max, high, medium, low, mute, etc.)
        descriptors = {
            r"\b(?:full|max|maximum|highest|100%)\b": 100,
            r"\b(?:high|loud)\b": 80,
            r"\b(?:medium|mid|moderate|normal)\b": 50,
            r"\b(?:low|quiet|soft|min|minimum)\b": 20,
            r"\b(?:silent|mute|zero)\b": 0
        }
        for pattern, val in descriptors.items():
            comb_pattern = rf"\b(?:(?:with|at|set|to)\s+{pattern}(?:\s*(?:minor|major)?\s*(?:volume|vol))?|{pattern}\s*(?:minor|major)?\s*(?:volume|vol))\b"
            match = re.search(comb_pattern, query, re.IGNORECASE)
            if match:
                parsed_volume = val
                query = re.sub(comb_pattern, "", query, flags=re.IGNORECASE).strip()
                query = re.sub(r"\s+", " ", query)
                break

        # 2. Check numerical ranges or plain numbers (e.g. "40 to 50 volume", "at 60 volume")
        if parsed_volume is None:
            num_pattern = r"\b(?:with|at|set|to)?\s*(?:(\d+)\s*(?:to|-)\s*)?(\d+)\s*(?:%|percent)?\s*(?:minor|major)?\s*(?:volume|vol)\b"
            match = re.search(num_pattern, query, re.IGNORECASE)
            if match:
                try:
                    parsed_volume = int(match.group(2))
                    query = re.sub(num_pattern, "", query, flags=re.IGNORECASE).strip()
                    query = re.sub(r"\s+", " ", query)
                except Exception:
                    pass

        # Apply parsed volume if found
        if parsed_volume is not None:
            self.volume = max(0, min(130, parsed_volume))
            logger.info(f"Extracted semantic volume {self.volume}% from play query. Remaining search query: '{query}'")
            
        try:
            import yt_dlp
        except ImportError:
            return "yt-dlp is not installed, sir. Please install it to search songs."
            
        # Cancel any active running loading thread instantly and stop current song
        with self.playback_lock:
            self.current_playback_id += 1
            playback_id = self.current_playback_id
            self._stop_song_locked()
            
        logger.info(f"Searching YouTube for: {query}")
        
        # Async task to search, resolve, play, and populate queue
        def run_search_and_play():
            try:
                # search for query
                ydl_opts = {
                    'format': 'bestaudio/best',
                    'noplaylist': True,
                    'quiet': True,
                    'extract_flat': True,
                    'nocheckcertificate': True,
                }
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(f"ytsearch3:{query}", download=False)
                    if not info or 'entries' not in info or len(info['entries']) == 0:
                        logger.warning(f"Could not find any songs matching '{query}'")
                        return
                    
                    entries = info['entries']
                    first_video = entries[0]
                    first_title = first_video.get("title", "")
                    
                with self.playback_lock:
                    if playback_id != self.current_playback_id:
                        return
                    self.queue = entries
                    self.queue_index = 0
                    
                # Play first item async immediately
                self._play_queue_item_async(0, playback_id)
                
                # 2. Extract artist and backfill queue in a background thread
                artist = self._extract_artist(query, first_title)
                if artist:
                    def backfill_task():
                        try:
                            logger.info(f"Detected artist: '{artist}'. Backfilling queue asynchronously...")
                            with yt_dlp.YoutubeDL(ydl_opts) as ydl_bf:
                                artist_info = ydl_bf.extract_info(f"ytsearch10:{artist} songs", download=False)
                                if artist_info and 'entries' in artist_info:
                                    with self.playback_lock:
                                        # Verify user hasn't started a different playback session
                                        if playback_id == self.current_playback_id:
                                            # Put the currently playing/requested video first
                                            new_queue = [first_video]
                                            seen_ids = {first_video.get("id")}
                                            for entry in artist_info['entries']:
                                                eid = entry.get("id")
                                                if eid and eid not in seen_ids:
                                                    new_queue.append(entry)
                                                    seen_ids.add(eid)
                                            # Fill up to 10 entries
                                            self.queue = new_queue[:10]
                                            logger.info(f"Queue successfully backfilled with {len(self.queue)} tracks for artist '{artist}'.")
                        except Exception as bf_err:
                            logger.warning(f"Background backfill failed: {bf_err}")
                            
                    threading.Thread(target=backfill_task, daemon=True).start()
                    
            except Exception as search_err:
                logger.error(f"Search and play task failed: {search_err}")
                
        threading.Thread(target=run_search_and_play, daemon=True).start()
        
        # Instant feedback for the user
        clean_query = self._clean_title(query)
        if len(clean_query) > 40:
            # Truncate to first meaningful part
            clean_query = clean_query.split("|")[0].split("-")[0].strip()
        if len(clean_query) > 30 or clean_query.lower() in ["song", "music", "some song", "some music"]:
            return "Right away, sir. I've played the track."
        return f"Right away, sir. Playing '{clean_query}'."

    def play_next_song(self) -> str:
        with self.playback_lock:
            if not self.queue:
                return "No songs in the playback queue, sir."
            if self.queue_index + 1 >= len(self.queue):
                return "You've reached the end of the playback queue, sir."
                
            self.current_playback_id += 1
            playback_id = self.current_playback_id
            target_index = self.queue_index + 1
            self._stop_song_locked()
            
        threading.Thread(target=self._play_queue_item_async, args=(target_index, playback_id), daemon=True).start()
        return "Playing the next track, sir."
        
    def play_previous_song(self) -> str:
        with self.playback_lock:
            if not self.queue:
                return "No songs in the playback queue, sir."
            if self.queue_index - 1 < 0:
                return "You are already at the beginning of the playback queue, sir."
                
            self.current_playback_id += 1
            playback_id = self.current_playback_id
            target_index = self.queue_index - 1
            self._stop_song_locked()
            
        threading.Thread(target=self._play_queue_item_async, args=(target_index, playback_id), daemon=True).start()
        return "Playing the previous track, sir."

    def control_media(self, action: str) -> str:
        with self.playback_lock:
            proc_exists = self.process is not None
            
        if not proc_exists and action not in ["next", "previous"]:
            return "No background music is currently active, sir."
            
        if action == "pause":
            return self.pause_song()
        elif action == "resume":
            return self.resume_song()
        elif action == "stop":
            return self.stop_song()
        elif action == "volume_up":
            return self.adjust_volume(10)
        elif action == "volume_down":
            return self.adjust_volume(-10)
        elif action == "next":
            return self.play_next_song()
        elif action == "previous":
            return self.play_previous_song()
        return f"Unknown background music action '{action}', sir."

    def adjust_volume(self, change: int) -> str:
        with self.playback_lock:
            proc_exists = self.process is not None
            
        if proc_exists:
            self.volume = max(0, min(130, self.volume + change))
            # If currently ducked, volume will apply on unduck, but we can set it active now adjusted
            vol_to_send = 35 if self.is_ducked else self.volume
            if self._send_ipc_command(["set_property", "volume", vol_to_send]):
                return "Volume adjusted, sir."
        return "No active playback to adjust volume, sir."

    def set_volume(self, volume: int) -> bool:
        """Lower-level helper (thread-safe, directly sends to pipe using retry logic)"""
        return self._send_ipc_command(["set_property", "volume", volume])
