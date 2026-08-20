import socket
import subprocess
import platform
import math
import concurrent.futures
from loguru import logger

class NetworkMapper:
    """Discovers active local network hosts and generates 3D wireframe topology coordinates."""

    def __init__(self):
        self.gateway_ip = self._get_gateway_ip()

    def _get_gateway_ip(self) -> str:
        """Retrieves the default gateway/local IP address prefix."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            return local_ip
        except Exception:
            return "192.168.1.1"

    def ping_ip(self, ip: str) -> str | None:
        """Pings a single IP address and returns its resolved hostname/IP if alive."""
        is_win = platform.system().lower() == "windows"
        param = "-n" if is_win else "-c"
        timeout_param = "-w" if is_win else "-W"
        timeout_val = "300" if is_win else "1"
        
        command = ["ping", param, "1", timeout_param, timeout_val, ip]
        startupinfo = None
        if is_win:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        try:
            res = subprocess.run(
                command, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                startupinfo=startupinfo, 
                timeout=0.8
            )
            if res.returncode == 0:
                # Try to resolve hostname
                try:
                    hostname, _, _ = socket.gethostbyaddr(ip)
                    return f"{hostname} ({ip})"
                except Exception:
                    return ip
        except Exception:
            pass
        return None

    def scan_local_subnet(self) -> list[tuple[str, str]]:
        """Scans the local subnet using a thread pool and returns a list of (ip, name)."""
        local_ip = self._get_gateway_ip()
        parts = local_ip.split(".")
        if len(parts) != 4:
            return []
            
        prefix = ".".join(parts[:3])
        ips_to_scan = [f"{prefix}.{i}" for i in range(1, 255)]
        
        active_devices = []
        logger.info(f"Initiating network topology scan on subnet: {prefix}.0/24...")
        
        # Limit worker count to prevent CPU thrashing during multi-pings
        with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
            results = executor.map(self.ping_ip, ips_to_scan)
            for ip, result in zip(ips_to_scan, results):
                if result:
                    active_devices.append((ip, result))
                    
        return active_devices

    def generate_3d_topology(self, active_devices: list[tuple[str, str]]) -> tuple[list, list, str]:
        """
        Translates a list of active devices into 3D coordinates.
        Returns: (vertices, connections, name)
        """
        # Central gateway node at (0, 0, 0)
        vertices = [[0, 0, 0]]
        connections = []
        name = "NETWORK TOPOLOGY"
        
        if not active_devices:
            # Fallback placeholder if scan result is empty
            active_devices = [("127.0.0.1", "LOCALHOST")]

        n = len(active_devices)
        radius = 120
        
        for i, (ip, dev_name) in enumerate(active_devices):
            # Evenly distribute nodes on a sphere using Golden Spiral
            phi = math.acos(1.0 - 2.0 * (i + 0.5) / n)
            theta = math.pi * (1.0 + 5.0**0.5) * (i + 0.5)
            
            x = radius * math.sin(phi) * math.cos(theta)
            y = radius * math.sin(phi) * math.sin(theta)
            z = radius * math.cos(phi)
            
            vertices.append([int(x), int(y), int(z)])
            # Connect every orbital node to the central gateway (node 0)
            connections.append((0, i + 1))
            
        # Optional: interconnect adjacent orbital nodes to form a web ring
        if n > 1:
            for i in range(1, n):
                connections.append((i, i + 1))
            connections.append((n, 1))
            
        return vertices, connections, name

if __name__ == "__main__":
    mapper = NetworkMapper()
    print("Scanning subnet...")
    devices = mapper.scan_local_subnet()
    print(f"Active devices found: {devices}")
    v, c, name = mapper.generate_3d_topology(devices)
    print(f"Vertices: {v}")
    print(f"Connections: {c}")
