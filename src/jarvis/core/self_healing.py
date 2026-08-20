import os
import sys
import re
import subprocess
from loguru import logger

class SelfHealingEngine:
    """Catches exceptions from active skills, calls LLM to generate patches, and compiles/applies them in a sandbox."""

    def __init__(self, settings_path: str = "config/settings.yaml"):
        self.project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.scratch_dir = os.path.join(self.project_root, "scratch")
        os.makedirs(self.scratch_dir, exist_ok=True)

    def _extract_project_file_from_traceback(self, traceback_str: str) -> tuple[str, int] | None:
        """Parse traceback to identify the exact custom project script and line number that crashed."""
        # Find all file lines in the traceback
        matches = re.findall(r'File "([^"]+)", line (\d+)', traceback_str)
        if not matches:
            return None
        
        # Traverse from most recent to oldest call
        for filepath, line_num in reversed(matches):
            filepath = os.path.abspath(filepath)
            # Ensure the file is in our project workspace and not inside virtualenv or site-packages
            if filepath.startswith(self.project_root) and "jarvis_env" not in filepath and "site-packages" not in filepath:
                return filepath, int(line_num)
        
        # Fallback to the very last workspace file matching the target
        return None

    def heal_error(self, traceback_str: str) -> tuple[bool, str]:
        """Runs the self-healing workflow. Returns (success_bool, message_str)."""
        logger.info("Self-Healing Engine triggered.")
        
        # 1. Identify target file
        target_info = self._extract_project_file_from_traceback(traceback_str)
        if not target_info:
            logger.warning("Self-Healing: Could not identify any project script in the traceback.")
            return False, "I couldn't identify the specific project script that caused the crash in the traceback, sir."
        
        filepath, line_num = target_info
        filename = os.path.basename(filepath)
        logger.info(f"Self-Healing: Target identified -> {filepath} (Line {line_num})")

        # 2. Read broken file content
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                broken_code = f.read()
        except Exception as read_err:
            logger.error(f"Self-Healing: Failed to read file {filepath}: {read_err}")
            return False, f"I failed to read the broken script file: {filename}, sir."

        # 3. Call LLM (Llama 3.1 8B via Cloudflare) to fix the file
        import ollama
        
        sys_prompt = (
            "You are an autonomous self-healing software engineer.\n"
            "An exception occurred in a Python file. Analyze the traceback, identify the bug, and write the corrected code.\n"
            "You MUST output the entire corrected python file contents. Return ONLY the code. Do NOT add explanations, do NOT write markdown code blocks, do NOT write ```python."
        )
        
        user_prompt = (
            f"Traceback of Exception:\n{traceback_str}\n\n"
            f"File Path: {filepath}\n"
            f"Error occurred near line: {line_num}\n\n"
            f"Broken File Contents:\n{broken_code}"
        )

        try:
            logger.info("Self-Healing: Querying Llama for code patch...")
            response = ollama.chat(
                model="qwen2.5-coder:7b",
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            )
            raw_patch = response["message"]["content"].strip()
            
            # Clean markdown code wrapper blocks if the LLM outputted them despite instructions
            if raw_patch.startswith("```"):
                raw_patch = re.sub(r"^```[a-zA-Z0-9]*\n", "", raw_patch)
                raw_patch = re.sub(r"\n```$", "", raw_patch)
            
            patched_code = raw_patch.strip()
            if not patched_code:
                raise ValueError("LLM returned an empty patch code.")
                
        except Exception as llm_err:
            logger.error(f"Self-Healing: LLM patch generation failed: {llm_err}")
            return False, f"I failed to generate a code patch for {filename} using the LLM, sir."

        # 4. Save to sandbox and compile check
        patch_temp_path = os.path.join(self.scratch_dir, f"healed_patch_{filename}")
        try:
            with open(patch_temp_path, "w", encoding="utf-8") as f:
                f.write(patched_code)
                
            # Compile check in subprocess
            res = subprocess.run(
                [sys.executable, "-m", "py_compile", patch_temp_path],
                capture_output=True
            )
            
            if res.returncode == 0:
                logger.info(f"Self-Healing: Sandbox syntax compilation passed for {filename}!")
                
                # 5. Overwrite the original file with the corrected code
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(patched_code)
                
                # Clean up temporary patch
                if os.path.exists(patch_temp_path):
                    os.remove(patch_temp_path)
                    
                return True, f"Sir, I caught an error in '{filename}'. I have successfully generated a patch, verified it in my sandbox compiler, and deployed the fix. You can retry your command now!"
            else:
                compile_err = res.stderr.decode("utf-8", errors="ignore")
                logger.warning(f"Self-Healing: Sandbox compile check failed for patch: {compile_err}")
                return False, f"Sir, I generated a patch for '{filename}', but it failed the sandbox compile checks. I did not deploy the patch to avoid breaking the system."
                
        except Exception as file_err:
            logger.error(f"Self-Healing: File patching failed: {file_err}")
            return False, f"An error occurred while trying to deploy the patch for {filename}, sir."

if __name__ == "__main__":
    healer = SelfHealingEngine()
    print("SelfHealingEngine initialized successfully.")
