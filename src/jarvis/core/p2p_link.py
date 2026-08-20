import socket
import threading
import time
import pyperclip
from loguru import logger

class P2PLinkNode:
    """Offline Peer-to-Peer node for copying clipboards and sending messages between JARVIS instances."""

    def __init__(self, listen_ip="0.0.0.0", udp_port=55556, tcp_port=55557, tts_engine=None):
        self.listen_ip = listen_ip
        self.udp_port = udp_port
        self.tcp_port = tcp_port
        self.tts = tts_engine
        
        self.peers = {}  # maps IP -> hostname
        self.is_running = False
        
        self.udp_socket = None
        self.tcp_socket = None

    def start(self):
        """Starts the P2P listener threads."""
        if self.is_running:
            return
        self.is_running = True
        
        # 1. Start UDP Listener (Discovery)
        self.udp_thread = threading.Thread(target=self._udp_listener, daemon=True)
        self.udp_thread.start()
        
        # 2. Start TCP Listener (Commands/Data)
        self.tcp_thread = threading.Thread(target=self._tcp_listener, daemon=True)
        self.tcp_thread.start()
        
        # 3. Start Periodic Beacon Broadcast
        self.beacon_thread = threading.Thread(target=self._beacon_sender, daemon=True)
        self.beacon_thread.start()
        logger.info(f"P2P Link: Listeners started on UDP port {self.udp_port} and TCP port {self.tcp_port}")

    def stop(self):
        """Stops the listeners."""
        self.is_running = False
        if self.udp_socket:
            try: self.udp_socket.close()
            except Exception: pass
        if self.tcp_socket:
            try: self.tcp_socket.close()
            except Exception: pass

    def _udp_listener(self):
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Allow multiple listeners on same port
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.udp_socket.bind(("", self.udp_port))
        except Exception as e:
            logger.error(f"P2P Link: Failed to bind UDP socket: {e}")
            return

        my_hostname = socket.gethostname()
        while self.is_running:
            try:
                data, addr = self.udp_socket.recvfrom(1024)
                ip = addr[0]
                text = data.decode("utf-8", errors="ignore")
                
                # Check for beacon
                if text.startswith("JARVIS_BEACON:"):
                    parts = text.split(":")
                    if len(parts) >= 3:
                        peer_name = parts[1]
                        peer_tcp_port = int(parts[2])
                        # Ignore self
                        if peer_name == my_hostname and peer_tcp_port == self.tcp_port:
                            continue
                            
                        # Store or update peer (key by IP and Port for multi-node local testing)
                        peer_key = f"{ip}:{peer_tcp_port}"
                        if peer_key not in self.peers:
                            self.peers[peer_key] = {"name": peer_name, "ip": ip, "port": peer_tcp_port, "last_seen": time.time()}
                            logger.info(f"P2P Link: Discovered peer '{peer_name}' at {ip}:{peer_tcp_port}")
                        else:
                            self.peers[peer_key]["last_seen"] = time.time()
            except Exception:
                break

    def _beacon_sender(self):
        client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        my_hostname = socket.gethostname()
        beacon_msg = f"JARVIS_BEACON:{my_hostname}:{self.tcp_port}".encode("utf-8")
        
        while self.is_running:
            try:
                # Broadcast to subnet broadcast address
                client.sendto(beacon_msg, ("255.255.255.255", self.udp_port))
            except Exception as e:
                logger.debug(f"P2P Link: Beacon broadcast error: {e}")
            time.sleep(8.0)  # broadcast every 8 seconds

    def _tcp_listener(self):
        self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.tcp_socket.bind((self.listen_ip, self.tcp_port))
            self.tcp_socket.listen(5)
        except Exception as e:
            logger.error(f"P2P Link: Failed to bind TCP socket: {e}")
            return

        while self.is_running:
            try:
                conn, addr = self.tcp_socket.accept()
                threading.Thread(target=self._handle_tcp_connection, args=(conn, addr), daemon=True).start()
            except Exception:
                break

    def _handle_tcp_connection(self, conn, addr):
        ip = addr[0]
        try:
            data = conn.recv(4096).decode("utf-8", errors="ignore")
            if not data:
                return
                
            # Command format: COMMAND_TYPE|DATA
            parts = data.split("|", 1)
            if len(parts) == 2:
                cmd_type, payload = parts[0], parts[1]
                if cmd_type == "CLIPBOARD":
                    pyperclip.copy(payload)
                    logger.info(f"P2P Link: Received remote clipboard contents from {ip}.")
                    if self.tts:
                        self.tts.speak("Sir, I've updated your local copy clipboard from your connected workstation.")
                elif cmd_type == "SPEAK":
                    logger.info(f"P2P Link: Remote speech request: '{payload}'")
                    if self.tts:
                        self.tts.speak(f"Sir, incoming voice note: {payload}")
        except Exception as e:
            logger.error(f"P2P Link: Error handling connection from {ip}: {e}")
        finally:
            conn.close()

    def send_clipboard(self, peer_target: str) -> str:
        """Sends local clipboard text to a peer node."""
        clip_text = pyperclip.paste().strip()
        if not clip_text:
            return "Local clipboard is empty, sir."
            
        return self._send_to_peer(peer_target, f"CLIPBOARD|{clip_text}")

    def send_speech(self, peer_target: str, message: str) -> str:
        """Sends a text speech command to a peer node."""
        return self._send_to_peer(peer_target, f"SPEAK|{message}")

    def _send_to_peer(self, target: str, payload: str) -> str:
        matched_key = None
        for key, info in self.peers.items():
            if target == key or target == info["ip"] or target.lower() in info["name"].lower():
                matched_key = key
                break

        if not matched_key:
            return f"Peer target '{target}' is not currently discovered or linked, sir."
            
        ip = self.peers[matched_key]["ip"]
        port = self.peers[matched_key]["port"]
        name = self.peers[matched_key]["name"]
        
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(3.0)
            s.connect((ip, port))
            s.sendall(payload.encode("utf-8"))
            s.close()
            return f"Successfully transmitted payload to peer '{name}', sir."
        except Exception as e:
            logger.error(f"P2P Link: Failed to send data to {ip}:{port}: {e}")
            return f"Failed to connect to peer at {ip}, sir."

    def list_peers(self) -> str:
        """Returns a string description of discovered LAN peers."""
        # Clean stale peers (unseen for > 25s)
        now = time.time()
        self.peers = {k: v for k, v in self.peers.items() if now - v["last_seen"] < 25.0}
        
        if not self.peers:
            return "No other active JARVIS nodes detected on the local subnet, sir."
            
        peer_list = "Active local network P2P link endpoints:\n"
        for key, info in self.peers.items():
            peer_list += f" - Host: {info['name']} | IP: {info['ip']} | Port: {info['port']}\n"
        return peer_list
