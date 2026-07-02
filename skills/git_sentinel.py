import os
import subprocess
import sys
from loguru import logger

class GitSentinel:
    """Monitors git workspace files for compilation errors and drafts self-healing corrections."""

    def __init__(self, project_root=r"c:\Users\patel\Jarvis"):
        self.project_root = project_root
        self.python_exe = os.path.join(self.project_root, "jarvis_env", "Scripts", "python.exe")
        if not os.path.exists(self.python_exe):
            self.python_exe = sys.executable

    def check_workspace(self) -> dict:
        """
        Scans modified and untracked python files, checks for syntax/compile issues.
        Returns:
            dict with check results: {"status": "clean"|"broken", "file_path": str, "error": str, "diff": str}
        """
        result = {"status": "clean", "file_path": "", "error": "", "diff": ""}

        try:
            # 1. Get modified/added python files using git status
            # --porcelain format: ' M path/to/file.py' or '?? path/to/file.py'
            status_proc = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            modified_files = []
            for line in status_proc.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                parts = line.split(maxsplit=1)
                if len(parts) == 2:
                    state, filepath = parts[0], parts[1]
                    if filepath.endswith(".py"):
                        modified_files.append(filepath)

            if not modified_files:
                return result

            # 2. Check each file using py_compile
            for filepath in modified_files:
                abs_path = os.path.join(self.project_root, filepath)
                if not os.path.exists(abs_path):
                    continue

                compile_proc = subprocess.run(
                    [self.python_exe, "-m", "py_compile", abs_path],
                    capture_output=True,
                    text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                )

                if compile_proc.returncode != 0:
                    # Compilation broke! Get traceback
                    error_traceback = compile_proc.stderr.strip()
                    logger.warning(f"GitSentinel: Compile error detected in {filepath}")

                    # 3. Get diff for this file
                    diff_proc = subprocess.run(
                        ["git", "diff", filepath],
                        cwd=self.project_root,
                        capture_output=True,
                        text=True,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                    )
                    diff_output = diff_proc.stdout.strip()
                    if not diff_output:
                        # If untracked file, fetch full contents instead of diff
                        try:
                            with open(abs_path, "r", encoding="utf-8") as f:
                                diff_output = f.read()
                        except Exception:
                            diff_output = "Untracked file (unable to read)."

                    result["status"] = "broken"
                    result["file_path"] = abs_path
                    result["error"] = error_traceback
                    result["diff"] = diff_output
                    break  # return first failure for self-healing

        except Exception as e:
            logger.error(f"GitSentinel: Error checking workspace: {e}")
            result["error"] = str(e)

        return result

    def generate_healing_patch(self, filepath: str, error_traceback: str, file_diff: str, model_name: str, ollama_client) -> str:
        """Invokes Ollama to construct the corrected code block based on compile error and diff."""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                current_content = f.read()
        except Exception as e:
            logger.error(f"GitSentinel: Failed to read file {filepath} for healing: {e}")
            return ""

        system_prompt = (
            "You are JARVIS's diagnostic self-healing compiler agent. You fix python code compile breaks. "
            "Examine the code, the compile traceback error, and the recent changes (diff). "
            "Output the COMPLETE corrected file contents. Do not explain anything, do not include markdown code block syntax. "
            "Just output pure runnable python code."
        )

        user_prompt = (
            f"File: {filepath}\n\n"
            f"Compile Error Traceback:\n{error_traceback}\n\n"
            f"Recent Changes (Diff):\n{file_diff}\n\n"
            f"Current File Content:\n{current_content}"
        )

        try:
            response = ollama_client.chat(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            )
            raw_reply = response["message"]["content"].strip()
            
            # Clean possible markdown wrap ```python / ```
            if raw_reply.startswith("```"):
                lines = raw_reply.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                raw_reply = "\n".join(lines).strip()
                
            return raw_reply
        except Exception as e:
            logger.error(f"GitSentinel: Failed to query Ollama for self-healing: {e}")
            return ""
