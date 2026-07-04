import os
import sys
import json
import re
import time
import tempfile
import subprocess
import requests
import yaml
from loguru import logger

class AutonomousCodingSandbox:
    """Uses Groq's coding model and a local isolated sandbox to iteratively write, run, and self-heal Python code."""

    def __init__(self, config_path: str = "config/settings.yaml"):
        self.config_path = config_path
        self.max_attempts = 5

    def _get_groq_config(self) -> tuple[str, str]:
        """Retrieves Mistral API key and model from environment or settings.yaml (replaces Groq)."""
        api_key = ""
        model = "devstral-2512"
        
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f)
                    mistral_cfg = config.get("mistral", {})
                    api_key = mistral_cfg.get("api_key", "")
                    model = mistral_cfg.get("models", {}).get("code", "devstral-2512")
            except Exception as e:
                logger.error(f"Failed to read settings.yaml for Mistral config: {e}")
                
        return api_key, model

    def _call_groq(self, system_prompt: str, user_prompt: str) -> str:
        """Hits Mistral's completions endpoint (replaces Groq)."""
        api_key, model = self._get_groq_config()
        if not api_key:
            return "ERROR: Mistral API key is not configured, sir. Please check settings.yaml."

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.1
        }
        
        try:
            r = requests.post("https://api.mistral.ai/v1/chat/completions", json=payload, headers=headers, timeout=25)
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"]
            else:
                return f"ERROR: Mistral API returned status {r.status_code}: {r.text}"
        except Exception as e:
            return f"ERROR: HTTP request failed: {str(e)}"

    def execute_task(self, task_description: str) -> str:
        """Runs the iterative write-execute-debug sandbox loop."""
        api_key, _ = self._get_groq_config()
        if not api_key:
            return "I cannot initiate the coding sandbox, sir. The Groq API key has not been configured insettings.yaml or environment variables."

        logger.info(f"Starting autonomous sandbox task: '{task_description}'")
        
        system_prompt = (
            "You are JARVIS's Autonomous Coding Agent. Write a clean, self-contained Python script to solve the user's task. "
            "IMPORTANT: Your response must be ONLY the executable Python code inside a markdown block: ```python ... ```. "
            "Do not include any chat, explanations, setup guides, or summaries outside the code block."
        )
        
        user_prompt = f"Write a Python script that completes this task on Windows: {task_description}"
        code = ""
        
        for attempt in range(1, self.max_attempts + 1):
            logger.info(f"Sandbox Attempt {attempt}/{self.max_attempts} - Prompting Groq...")
            response = self._call_groq(system_prompt, user_prompt)
            
            if response.startswith("ERROR"):
                return response
                
            # Extract Python code
            code_match = re.search(r"```python(.*?)```", response, re.DOTALL)
            if code_match:
                code = code_match.group(1).strip()
            else:
                code = response.replace("```", "").strip()

            # Execute in temp file
            with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w", encoding="utf-8") as f:
                f.write(code)
                temp_path = f.name
                
            try:
                result = subprocess.run(
                    [sys.executable, temp_path], 
                    capture_output=True, 
                    text=True, 
                    timeout=20, 
                    shell=True
                )
                
                # Cleanup
                try: os.unlink(temp_path)
                except Exception: pass
                
                # Check for success
                if result.returncode == 0:
                    logger.success(f"Sandbox script ran successfully on attempt {attempt}!")
                    output = result.stdout or "Script completed with no stdout."
                    return (
                        f"Autonomous execution successful on attempt {attempt}, sir.\n\n"
                        f"### Executed Script:\n```python\n{code}\n```\n\n"
                        f"### Execution Output:\n```\n{output}\n```"
                    )
                else:
                    logger.warning(f"Sandbox script execution failed (Exit code: {result.returncode}) on attempt {attempt}.")
                    # Update prompt for debugging
                    user_prompt = (
                        f"Your previous script failed. Here is the code you wrote:\n```python\n{code}\n```\n\n"
                        f"It failed with this error/traceback:\n```\n{result.stderr}\n```\n\n"
                        f"Please analyze the error, self-heal the script, and output the entire corrected script inside the ```python ... ``` block."
                    )
            except subprocess.TimeoutExpired:
                try: os.unlink(temp_path)
                except Exception: pass
                logger.warning(f"Sandbox script execution timed out on attempt {attempt}.")
                user_prompt = (
                    f"Your previous script timed out after 20 seconds. Here is the code you wrote:\n```python\n{code}\n```\n\n"
                    "Please optimize the script to prevent blocking or long execution times, and output the corrected script."
                )
            except Exception as run_err:
                try: os.unlink(temp_path)
                except Exception: pass
                logger.error(f"Sandbox run error: {run_err}")
                return f"Sandbox execution environment encountered a fatal error: {run_err}"
                
        return (
            f"Sir, I attempted to self-heal the script {self.max_attempts} times, but it continues to fail.\n\n"
            f"### Last Attempt Script:\n```python\n{code}\n```\n\n"
            f"### Error Log:\n```\n{result.stderr if 'result' in locals() else 'Unknown execution error'}\n```"
        )


class CompilerRepairEngine:
    """Runs a project's build command and autonomously self-heals compiler errors by rewriting failing source lines."""

    def __init__(self, coding_sandbox: AutonomousCodingSandbox):
        self.sandbox = coding_sandbox
        self.max_retries = 3

    def compile_and_repair(self, build_command: str) -> str:
        """Executes a build command and loops to patch code syntax/compilation errors using Groq."""
        api_key, _ = self.sandbox._get_groq_config()
        if not api_key:
            return "I cannot initiate the compiler repair loop, sir. The Groq API key is not configured."

        logger.info(f"Initiating build and compile-repair engine for command: '{build_command}'")
        
        for retry in range(1, self.max_retries + 1):
            logger.info(f"Build Loop {retry}/{self.max_retries} - Running command...")
            result = subprocess.run(build_command, capture_output=True, text=True, timeout=30, shell=True)
            
            if result.returncode == 0:
                logger.success(f"Project built successfully on build iteration {retry}!")
                return f"Sir, the project compiled successfully.\n\nStdout:\n```\n{result.stdout or 'No stdout output'}\n```"
                
            error_log = result.stderr or result.stdout
            logger.warning(f"Build failed with error. Attempting compiler auto-repair...")
            
            # 1. Parse traceback or compiler logs for file/line/error
            # Patterns like "File \"path.py\", line 12" or "path.py:12:error:"
            file_match = re.search(r'File "([^"]+)", line (\d+)', error_log)
            if not file_match:
                # C-style or JavaScript patterns: "path.js:12"
                file_match = re.search(r'([a-zA-Z0-9_\-\./\\]+\.[a-zA-Z0-9]+):(\d+)', error_log)
                
            if not file_match:
                return (
                    f"Sir, the build failed, but I was unable to parse the exact file path from the logs.\n\n"
                    f"### Error Logs:\n```\n{error_log}\n```"
                )
                
            file_path = file_match.group(1).strip()
            line_number = int(file_match.group(2))
            
            # Resolve relative file path safely
            if not os.path.exists(file_path):
                # Try finding in current directory recursively
                found = False
                for root, dirs, files in os.walk("."):
                    if os.path.basename(file_path) in files:
                        file_path = os.path.join(root, os.path.basename(file_path))
                        found = True
                        break
                if not found:
                    return f"Build failed, but I could not locate the source file '{file_path}' in the workspace, sir."
            
            logger.info(f"Auto-Repair targeted: '{file_path}' at line {line_number}")
            
            # 2. Read context around the failing line
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
            except Exception as read_err:
                return f"Failed to read source file '{file_path}' to apply patch: {read_err}"
                
            # Grab context window (5 lines before, 5 lines after target line)
            start_ctx = max(0, line_number - 6)
            end_ctx = min(len(lines), line_number + 5)
            context_code = "".join(f"{i+1}: {lines[i]}" for i in range(start_ctx, end_ctx))
            
            # 3. Request a code patch from Groq
            system_prompt = (
                "You are JARVIS's Compiler Repair Agent. Your task is to provide the exact replacement code for a targeted range of lines. "
                "Output ONLY the corrected code inside a ```python ... ``` or similar code block corresponding to the language of the file. "
                "Do not include explanation, preamble, or any conversational text."
            )
            
            user_prompt = (
                f"File: '{file_path}'\n"
                f"Failing Line: {line_number}\n\n"
                f"Compiler Error Logs:\n```\n{error_log}\n```\n\n"
                f"Code Context around Line {line_number}:\n```\n{context_code}\n```\n\n"
                f"Please output the corrected block of code replacing lines {start_ctx+1} to {end_ctx} (inclusive). "
                "Make sure it fits perfectly with the surrounding code and resolves the syntax/runtime error."
            )
            
            patch_response = self.sandbox._call_groq(system_prompt, user_prompt)
            if patch_response.startswith("ERROR"):
                return patch_response
                
            # Extract code patch block
            code_match = re.search(r"```[a-zA-Z]*(.*?)```", patch_response, re.DOTALL)
            patch_code = code_match.group(1).strip() if code_match else patch_response.strip()
            
            # 4. Apply the patch
            try:
                new_lines = lines[:start_ctx] + [patch_code + "\n"] + lines[end_ctx:]
                with open(file_path, "w", encoding="utf-8") as f:
                    f.writelines(new_lines)
                logger.success(f"Successfully applied auto-repair code patch to {file_path}")
            except Exception as write_err:
                return f"Failed to write patch to source file '{file_path}': {write_err}"
                
        # If we loop out, return failure
        return (
            f"Sir, I applied patches to the project {self.max_retries} times, but the compiler continues to fail.\n\n"
            f"### Final Compile Errors:\n```\n{error_log}\n```"
        )
