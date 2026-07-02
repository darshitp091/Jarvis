import subprocess
import os
from loguru import logger

class SentryFirewall:
    """Manages active network port blocking and remote IP quarantines using Windows Defender Firewall."""

    def __init__(self):
        pass

    def quarantine_ip(self, ip: str) -> str:
        """
        Adds a blocking rule in the Windows Defender Firewall for the specified IP.
        """
        rule_name = f"JARVIS_QUARANTINE_{ip}"
        
        # Windows command to block inbound traffic from remote IP
        cmd = [
            "netsh", "advfirewall", "firewall", "add", "rule",
            f"name={rule_name}",
            "dir=in",
            "action=block",
            f"remoteip={ip}"
        ]
        
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            if proc.returncode == 0:
                logger.info(f"SentryFirewall: Blocked IP {ip} successfully.")
                return f"Sir, I have added a firewall rule to block and quarantine IP address {ip}."
            else:
                stderr = proc.stderr.strip()
                logger.error(f"SentryFirewall: Failed to block IP {ip}: {stderr}")
                if "Run as administrator" in stderr or "privileges" in stderr:
                    return f"Unable to quarantine {ip}, sir. JARVIS requires administrator privileges to write firewall rules."
                return f"Failed to quarantine IP address {ip}, sir. Error: {stderr}"
                
        except Exception as e:
            logger.error(f"SentryFirewall: Error executing block command: {e}")
            return f"Error executing quarantine block, sir. Details: {e}"

    def remove_quarantine(self, ip: str) -> str:
        """Removes the firewall block rule for the specified IP."""
        rule_name = f"JARVIS_QUARANTINE_{ip}"
        cmd = ["netsh", "advfirewall", "firewall", "delete", "rule", f"name={rule_name}"]
        
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            if proc.returncode == 0:
                logger.info(f"SentryFirewall: Removed block on IP {ip}.")
                return f"Sir, I have successfully removed the quarantine block on IP address {ip}."
            else:
                return f"Failed to remove quarantine rule for {ip}, sir. Rule may not exist."
        except Exception as e:
            return f"Error removing quarantine block, sir. Details: {e}"

    def list_blocks(self) -> str:
        """Lists active firewall rules starting with JARVIS_QUARANTINE."""
        cmd = ["netsh", "advfirewall", "firewall", "show", "rule", "name=all"]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            if proc.returncode != 0:
                return "No active quarantine rules detected or unable to query firewall rules, sir."
                
            blocked_ips = []
            for line in proc.stdout.splitlines():
                if "Rule Name:" in line and "JARVIS_QUARANTINE_" in line:
                    parts = line.split("JARVIS_QUARANTINE_")
                    if len(parts) == 2:
                        ip = parts[1].strip()
                        blocked_ips.append(ip)
                        
            if not blocked_ips:
                return "No active JARVIS quarantine blocks found in the Windows Firewall configuration, sir."
                
            reply = "Active network quarantine blocks:\n"
            for ip in blocked_ips:
                reply += f" - Blocked Remote Endpoint: {ip}\n"
            return reply
            
        except Exception as e:
            return f"Unable to list firewall blocks, sir. Error: {e}"
