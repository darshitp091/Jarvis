import subprocess
import os
import tempfile
import sys
import webbrowser
from loguru import logger

class CodeRunner:
    """Manages local code execution, Git operations, Docker containers, and browser testing tools for JARVIS."""

    def run_code(self, language: str, code_text: str) -> str:
        """Saves code to a temporary file and runs it locally, returning stdout/stderr."""
        lang = language.lower().strip()
        suffix = ".py"
        cmd_args = [sys.executable]  # default to current python interpreter
        
        if lang in ["js", "javascript", "node"]:
            suffix = ".js"
            cmd_args = ["node"]
        elif lang in ["bat", "batch", "cmd"]:
            suffix = ".bat"
            cmd_args = []
        elif lang != "python":
            # If not python/JS, we default to running it as python
            suffix = ".py"
        
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False, mode="w", encoding="utf-8") as f:
                f.write(code_text)
                temp_path = f.name
            
            logger.info(f"Executing local {lang} code file...")
            if cmd_args:
                run_cmd = cmd_args + [temp_path]
            else:
                run_cmd = [temp_path]
                
            result = subprocess.run(run_cmd, capture_output=True, text=True, timeout=10, shell=True)
            
            try:
                os.unlink(temp_path)
            except Exception:
                pass
                
            output = f"Execution Output (Exit Code: {result.returncode}):\n"
            if result.stdout:
                output += f"Stdout:\n{result.stdout}\n"
            if result.stderr:
                output += f"Stderr:\n{result.stderr}\n"
            return output
        except subprocess.TimeoutExpired:
            try: os.unlink(temp_path)
            except Exception: pass
            return "Execution timed out after 10 seconds, sir."
        except Exception as e:
            return f"Failed to run code: {str(e)}"

    def git_command(self, action: str, args: str = "") -> str:
        """Automates local git operations: status, commit, push, pull, branch."""
        act = action.lower().strip()
        cmd = ["git"]
        
        if act == "status":
            cmd.append("status")
        elif act == "commit":
            commit_msg = args or "Auto git commit by JARVIS"
            # run add first
            subprocess.run(["git", "add", "."], capture_output=True)
            cmd += ["commit", "-m", commit_msg]
        elif act == "push":
            cmd.append("push")
        elif act == "pull":
            cmd.append("pull")
        elif act == "branch":
            if args:
                cmd += ["checkout", "-b", args]
            else:
                cmd.append("branch")
        else:
            return f"Unsupported Git action '{action}', sir."

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15, shell=True)
            out = f"Git {action.capitalize()} results:\n"
            if result.stdout: out += f"Stdout:\n{result.stdout}\n"
            if result.stderr: out += f"Stderr:\n{result.stderr}\n"
            return out
        except Exception as e:
            return f"Git operation failed: {str(e)}"

    def docker_command(self, action: str, args: str = "") -> str:
        """Automates Docker commands: list, start, stop, logs."""
        act = action.lower().strip()
        cmd = ["docker"]
        
        if act in ["list", "ps"]:
            cmd += ["ps", "-a"]
        elif act == "start":
            if not args: return "Please specify container name or ID to start, sir."
            cmd += ["start", args]
        elif act == "stop":
            if not args: return "Please specify container name or ID to stop, sir."
            cmd += ["stop", args]
        elif act == "logs":
            if not args: return "Please specify container name or ID for logs, sir."
            cmd += ["logs", "--tail", "50", args]
        else:
            return f"Unsupported Docker action '{action}', sir."

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15, shell=True)
            out = f"Docker {action.capitalize()} results:\n"
            if result.stdout: out += f"Stdout:\n{result.stdout}\n"
            if result.stderr: out += f"Stderr:\n{result.stderr}\n"
            return out
        except Exception as e:
            return f"Docker operation failed: {str(e)}"

    def mobile_view_emulation(self, url: str) -> str:
        """Launches Chrome in mobile device emulation mode (iPhone viewport)."""
        if not url.startswith("http"):
            url = "http://" + url
            
        # Target Chrome with mobile configuration
        chrome_cmd = [
            "chrome.exe",
            f"--window-size=375,812",
            f"--user-agent=Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1",
            url
        ]
        try:
            subprocess.Popen(chrome_cmd, shell=True)
            return f"Launching responsive mobile emulation for {url} in Chrome, sir."
        except Exception as e:
            logger.warning(f"Failed to launch Chrome with custom args: {e}. Falling back to default browser.")
            webbrowser.open(url)
            return f"Opened {url} in your default browser, sir."

    def deploy_app(self, project_path: str, port: int = 3000) -> str:
        """Automates app production builds (npm run build) and runs a local server process."""
        path = os.path.abspath(os.path.expanduser(project_path))
        if not os.path.exists(path):
            return f"Sir, the project path at {project_path} does not exist."

        try:
            logger.info(f"Running production compile in {path}...")
            # Check if package.json exists
            if os.path.exists(os.path.join(path, "package.json")):
                subprocess.run(["npm", "run", "build"], cwd=path, shell=True, capture_output=True, timeout=60)
                # Launch background server
                server_cmd = f"npm start -- --port {port}"
                subprocess.Popen(server_cmd, cwd=path, shell=True)
                return f"Build compiled and server initiated on port {port} for project {os.path.basename(path)}, sir."
            
            # Python server fallback
            elif os.path.exists(os.path.join(path, "requirements.txt")) or any(f.endswith(".py") for f in os.listdir(path)):
                server_cmd = f"{sys.executable} -m http.server {port}"
                subprocess.Popen(server_cmd, cwd=path, shell=True)
                return f"Python static server initiated on port {port} in directory {os.path.basename(path)}, sir."
                
            return f"No NPM or Python configurations found in project directory to deploy, sir."
        except Exception as e:
            return f"Failed to deploy application: {str(e)}"
