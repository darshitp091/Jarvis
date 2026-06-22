import os
import subprocess
from loguru import logger

class YouTubeMusicPlayer:
    """Streams audio from YouTube in the background using local yt-dlp and VLC player"""
    
    def __init__(self):
        self.vlc_path = r"C:\Program Files\VideoLAN\VLC\vlc.exe"
        if not os.path.exists(self.vlc_path):
            self.vlc_path = r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe"
            
        self.vlc_exists = os.path.exists(self.vlc_path)
        self.process = None
        self.current_song = None
        self.is_paused = False
        
    def is_available(self) -> bool:
        return self.vlc_exists
        
    def play_song(self, query: str) -> str:
        if not self.vlc_exists:
            return "VLC is not installed, sir. Please install VLC to enable background streaming."
            
        # Stop any currently playing song first
        self.stop_song()
        
        try:
            import yt_dlp
        except ImportError:
            return "yt-dlp is not installed, sir. Please install it to search songs."
            
        logger.info(f"Searching YouTube for: {query}")
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'noplaylist': True,
            'quiet': True,
            'extract_flat': False,
            'skip_download': True,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"ytsearch:{query}", download=False)
                if not info or 'entries' not in info or len(info['entries']) == 0:
                    return f"Could not find any songs matching '{query}' on YouTube, sir."
                    
                first_entry = info['entries'][0]
                stream_url = first_entry['url']
                title_raw = first_entry.get('title', query)
                self.current_song = "".join(c for c in title_raw if ord(c) < 65536)
                
                # Extract HTTP headers from yt-dlp to authorize streaming in VLC
                http_headers = first_entry.get('http_headers', {})
                user_agent = http_headers.get('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
                referer = http_headers.get('Referer', 'https://www.youtube.com/')
                
            logger.info(f"Streaming audio in background: {self.current_song}")
            
            # Start VLC in remote control (rc) mode without video, silently
            self.process = subprocess.Popen(
                [
                    self.vlc_path, 
                    "-I", "rc", 
                    "--rc-fake-tty", 
                    "--no-video", 
                    "--dummy-quiet", 
                    f"--http-user-agent={user_agent}",
                    f"--http-referrer={referer}",
                    stream_url
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            self.is_paused = False
            return f"Playing '{self.current_song}' in the background, sir."
            
        except Exception as e:
            logger.error(f"Failed to play song from YouTube: {e}")
            return "I encountered an error trying to stream the song, sir."
            
    def stop_song(self) -> str:
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=2)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            self.process = None
            self.current_song = None
            self.is_paused = False
            return "Music stopped, sir."
        return "No music is currently playing, sir."
        
    def pause_song(self) -> str:
        if self.process and not self.is_paused:
            try:
                self.process.stdin.write("pause\n")
                self.process.stdin.flush()
                self.is_paused = True
                return "Playback paused, sir."
            except Exception as e:
                logger.error(f"Failed to pause: {e}")
        return "No active music playback to pause, sir."
        
    def resume_song(self) -> str:
        if self.process and self.is_paused:
            try:
                self.process.stdin.write("pause\n") # In VLC rc, "pause" toggles play/pause state
                self.process.stdin.flush()
                self.is_paused = False
                return "Playback resumed, sir."
            except Exception as e:
                logger.error(f"Failed to resume: {e}")
        return "No paused music playback to resume, sir."
        
    def control_media(self, action: str) -> str:
        if not self.process:
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
        return f"Unknown background music action '{action}', sir."

    def adjust_volume(self, change: int) -> str:
        if self.process:
            try:
                cmd = "volup 1\n" if change > 0 else "voldown 1\n"
                for _ in range(abs(change)):
                    self.process.stdin.write(cmd)
                self.process.stdin.flush()
                return "Volume adjusted, sir."
            except Exception as e:
                logger.error(f"Failed to adjust volume: {e}")
        return "No active playback to adjust volume, sir."
