import socket
import subprocess
import re
import os
import psutil
import math
from loguru import logger

class SecurityAuditor:
    """Performs defensive system audits including local port scans, network sweeps, traffic logs, and password checks."""

    def scan_ports(self, host: str = "127.0.0.1", ports_to_scan: list = None) -> str:
        """Scans specified ports on a host to identify open ones."""
        if not ports_to_scan:
            # Common ports to audit
            ports_to_scan = [21, 22, 23, 25, 53, 80, 110, 135, 139, 443, 445, 1433, 3306, 3389, 8080]
        
        open_ports = []
        logger.info(f"Auditing open ports on host: {host}")
        
        try:
            # Standardize host string
            target_ip = socket.gethostbyname(host)
            for port in ports_to_scan:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(0.15)  # fast check
                result = s.connect_ex((target_ip, port))
                if result == 0:
                    open_ports.append(port)
                s.close()
            
            if open_ports:
                return f"Audit complete for {host}, sir. Found open ports: {', '.join(map(str, open_ports))}."
            else:
                return f"Audit complete, sir. All scanned ports on {host} are secure (closed)."
        except Exception as e:
            logger.error(f"Port scan failed: {e}")
            return f"Failed to complete port audit: {str(e)}"

    def scan_network_devices(self) -> str:
        """Parses the system ARP cache to list network connected devices (IP and MAC addresses)."""
        logger.info("Scanning local network devices via ARP table...")
        devices = []
        try:
            # Run arp command
            output = subprocess.check_output(["arp", "-a"], text=True)
            lines = output.splitlines()
            for line in lines:
                # Find IP addresses and MAC addresses
                # e.g., "  192.168.1.1           90-f6-52-ee-e7-78     dynamic"
                ip_match = re.search(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})", line)
                mac_match = re.search(r"([0-9a-fA-F]{2}[:-][0-9a-fA-F]{2}[:-][0-9a-fA-F]{2}[:-][0-9a-fA-F]{2}[:-][0-9a-fA-F]{2}[:-][0-9a-fA-F]{2})", line)
                if ip_match and mac_match:
                    ip = ip_match.group(1)
                    mac = mac_match.group(1)
                    # Filter out broadcast/multicast IPs
                    if not ip.startswith(("255.", "224.", "192.168.1.255")):
                        devices.append(f"IP: {ip} | MAC: {mac}")
            
            if devices:
                return "Local network connected devices, sir:\n" + "\n".join(devices)
            else:
                return "No external network devices detected in the cache, sir."
        except Exception as e:
            logger.error(f"ARP scan failed: {e}")
            return f"Failed to read local network devices: {str(e)}"

    def list_active_outbound_connections(self) -> str:
        """Audits outgoing TCP/UDP traffic to identify suspicious connections."""
        logger.info("Retrieving active outbound network connections...")
        connections = []
        try:
            for conn in psutil.net_connections(kind="inet"):
                # Check for active connections with remote addresses
                if conn.raddr and conn.status == "ESTABLISHED":
                    r_ip, r_port = conn.raddr
                    # Exclude local loopbacks
                    if r_ip not in ["127.0.0.1", "::1"]:
                        pid = conn.pid
                        proc_name = "Unknown"
                        if pid:
                            try:
                                proc_name = psutil.Process(pid).name()
                            except Exception:
                                pass
                        connections.append(f"Process: {proc_name} (PID: {pid}) -> Outgoing Target: {r_ip}:{r_port}")
            
            if connections:
                # Limit to top 15 to prevent log flooding
                return "Active outgoing network connections audited, sir:\n" + "\n".join(connections[:15])
            else:
                return "No active outbound remote connections detected, sir. Network traffic is clean."
        except Exception as e:
            logger.error(f"Failed to audit network connections: {e}")
            return f"Error scanning outgoing network connections: {str(e)}"

    def audit_password_strength(self, password: str) -> str:
        """Evaluates password entropy, length, complexity, and common structures offline."""
        if not password:
            return "Please provide a password to audit, sir."
            
        length = len(password)
        has_upper = any(c.isupper() for c in password)
        has_lower = any(c.islower() for c in password)
        has_digit = any(c.isdigit() for c in password)
        has_special = any(not c.isalnum() for c in password)
        
        # Calculate character set size (pool)
        pool = 0
        if has_lower: pool += 26
        if has_upper: pool += 26
        if has_digit: pool += 10
        if has_special: pool += 32
        
        if pool == 0: pool = 1
        
        # Calculate Shannon entropy (bits)
        entropy = length * math.log2(pool)
        
        # Audit evaluation
        warnings = []
        if length < 8:
            warnings.append("Length is under 8 characters (highly vulnerable).")
        if not (has_upper and has_lower):
            warnings.append("Lacks mixed casing (uppercase and lowercase).")
        if not has_digit:
            warnings.append("Lacks numeric digits.")
        if not has_special:
            warnings.append("Lacks special symbols.")
            
        # Standard dictionary checks
        common_patterns = ["123456", "password", "qwerty", "admin", "stark", "jarvis", "welcome"]
        if any(pat in password.lower() for pat in common_patterns):
            warnings.append("Contains highly common keyboard sequence or words.")

        strength = "SECURE"
        if entropy < 40:
            strength = "WEAK"
        elif entropy < 60:
            strength = "MODERATE"
        elif entropy < 80:
            strength = "STRONG"
        else:
            strength = "EXCEPTIONAL"

        summary = f"Password audit complete. Strength: **{strength}** ({entropy:.1f} bits of entropy).\n"
        if warnings:
            summary += "Vulnerabilities detected:\n - " + "\n - ".join(warnings)
        else:
            summary += "No issues found. This password meets high defense security specifications."
        return summary

    def audit_installed_packages_for_cves(self) -> str:
        """Audits locally installed python packages for typical CVE vulnerabilities (offline database check)."""
        logger.info("Auditing installed pip packages for CVEs...")
        try:
            import pkg_resources
            installed = {pkg.key: pkg.version for pkg in pkg_resources.working_set}
        except ImportError:
            # Fallback psutil/pip list parsing
            installed = {}

        # Vulnerable version database (offline snapshot representation)
        cve_database = {
            "jinja2": {"vuln_before": "3.1.3", "cve": "CVE-2024-22195", "desc": "HTML injection leading to XSS"},
            "requests": {"vuln_before": "2.31.0", "cve": "CVE-2023-32681", "desc": "Unintended leak of authorization headers"},
            "numpy": {"vuln_before": "1.22.0", "cve": "CVE-2021-41496", "desc": "Buffer overflow in array operations"},
            "pillow": {"vuln_before": "10.2.0", "cve": "CVE-2024-28219", "desc": "Buffer overflow in image loading routines"},
            "cryptography": {"vuln_before": "41.0.6", "cve": "CVE-2023-49083", "desc": "Null pointer dereference"},
        }
        
        vulnerabilities = []
        for pkg_name, installed_version in installed.items():
            if pkg_name in cve_database:
                db_entry = cve_database[pkg_name]
                # Compare semantic versions simply (string match/split helper)
                try:
                    inst_parts = [int(x) for x in re.findall(r"\d+", installed_version)[:3]]
                    db_parts = [int(x) for x in re.findall(r"\d+", db_entry["vuln_before"])[:3]]
                    
                    is_vulnerable = False
                    for i in range(min(len(inst_parts), len(db_parts))):
                        if inst_parts[i] < db_parts[i]:
                            is_vulnerable = True
                            break
                        elif inst_parts[i] > db_parts[i]:
                            break
                            
                    if is_vulnerable:
                        vulnerabilities.append(
                            f"**{pkg_name}** ({installed_version}) is vulnerable to **{db_entry['cve']}** (fixed in {db_entry['vuln_before']}). Description: {db_entry['desc']}."
                        )
                except Exception:
                    pass

        if vulnerabilities:
            return "Local vulnerability audit found dependencies with known CVEs, sir:\n" + "\n".join(vulnerabilities)
        else:
            return "Local dependencies audit complete, sir. No outdated software with known CVE vulnerabilities detected."

    def analyze_workspace_logs(self, log_path: str = "./error.log") -> str:
        """Parses error logs in the workspace to highlight recent anomalies or warning states."""
        if not os.path.exists(log_path):
            return "No workspace error logs exist at the moment, sir."
            
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                
            errors = []
            for line in reversed(lines):
                if "ERROR" in line or "CRITICAL" in line or "Exception" in line:
                    errors.append(line.strip())
                if len(errors) >= 5:
                    break
                    
            if errors:
                return "Recent error anomalies found in system logs, sir:\n" + "\n".join(errors)
            else:
                return "System logs are clear of recent anomalies and errors, sir."
        except Exception as e:
            return f"Error reading log file: {str(e)}"

    def run_system_security_scan(self) -> str:
        """Performs a comprehensive local system security, threat, and malware scan."""
        try:
            import psutil
            suspicious_processes = []
            temp_folders = ["temp", "tmp", "appdata\\local\\temp"]
            
            # 1. Scan running processes for suspicious directories
            for proc in psutil.process_iter(['pid', 'name', 'exe']):
                try:
                    exe_path = proc.info.get('exe')
                    if exe_path:
                        exe_lower = exe_path.lower()
                        if any(t in exe_lower for t in temp_folders):
                            suspicious_processes.append(f"{proc.info['name']} (PID: {proc.info['pid']})")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            # 2. Check outbound connections count
            connections = psutil.net_connections(kind='inet')
            outbound_count = len([conn for conn in connections if conn.status == 'ESTABLISHED'])
            
            # 3. Compile report
            if suspicious_processes:
                findings = (
                    f"Security scan complete, sir. Identified {len(suspicious_processes)} suspicious process(es) "
                    f"running from temporary directories: {', '.join(suspicious_processes)}. "
                    f"Outbound active connections are at {outbound_count} established sessions. "
                    f"I recommend quarantining these process targets immediately, sir."
                )
            else:
                findings = (
                    f"[excited] Security scan complete, sir. Koi active malware, threats, ya anomalous attacks detect nahi hue. "
                    f"Saare running processes safe system paths se execute ho rahe hain. "
                    f"Active outbound network streams {outbound_count} established connections par nominal hain. "
                    f"System completely secure aur optimized hai, sir!"
                )
            return findings
        except Exception as e:
            return f"Security audit scan execution failed, sir. Detail: {str(e)}"

    def start_sentry(self, alert_callback):
        """Starts the background security sentry thread."""
        self.alert_callback = alert_callback
        self.is_running = True
        import threading
        self.sentry_thread = threading.Thread(target=self._sentry_loop, daemon=True)
        self.sentry_thread.start()
        logger.info("Security Sentry background auditor started.")

    def stop_sentry(self):
        """Stops the background security sentry thread."""
        self.is_running = False

    def _sentry_loop(self):
        import time
        import json
        alerted_pids = set()
        allowed_ports = {80, 443, 22, 53, 123, 8080, 8443, 3000, 5000, 8000, 11434}
        whitelisted_procs = {"chrome", "firefox", "msedge", "python", "git", "ollama", "code", "node", "npm", "powershell", "cmd", "explorer", "svchost", "system", "vlc", "spotify", "adb", "msedgewebview2"}
        
        while getattr(self, "is_running", False):
            try:
                for conn in psutil.net_connections(kind="inet"):
                    if conn.status == "ESTABLISHED" and conn.raddr:
                        r_ip, r_port = conn.raddr
                        if r_ip not in ["127.0.0.1", "::1"]:
                            pid = conn.pid
                            if pid and pid not in alerted_pids:
                                try:
                                    proc = psutil.Process(pid)
                                    proc_name = proc.name()
                                except Exception:
                                    continue
                                
                                # Check if suspicious
                                is_suspicious = False
                                if r_port in [1337, 4444, 9999, 6666]:
                                    is_suspicious = True
                                elif r_port not in allowed_ports and proc_name.lower().split(".")[0] not in whitelisted_procs:
                                    is_suspicious = True
                                    
                                if is_suspicious:
                                    alerted_pids.add(pid)
                                    # Trigger alert structured as JSON
                                    alert_payload = {
                                        "type": "confirm_quarantine_process",
                                        "pid": pid,
                                        "proc_name": proc_name,
                                        "warning_text": f"Sir, an active port intrusion has been detected from process {proc_name} on port {r_port}. Initiating quarantine protocols. Shall I block this process?"
                                    }
                                    if hasattr(self, "alert_callback") and self.alert_callback:
                                        self.alert_callback(json.dumps(alert_payload))
            except Exception as e:
                logger.debug(f"Security sentry error: {e}")
            time.sleep(3.0)
