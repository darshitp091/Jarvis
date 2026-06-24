import os
import re
import yaml
import requests
from loguru import logger

class PolyglotEngineer:
    """Master principal engineer agent that designs architectures, writes polyglot code, and reviews DSA/OOP layouts."""

    def __init__(self, config_path: str = "config/settings.yaml"):
        self.config_path = config_path

    def _get_groq_config(self) -> tuple[str, str]:
        api_key = os.environ.get("GROQ_API_KEY", "")
        model = "llama-3.3-70b-versatile"
        
        if not api_key and os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f)
                    groq_cfg = config.get("groq", {})
                    api_key = groq_cfg.get("api_key", "")
                    model = groq_cfg.get("model", "llama-3.3-70b-versatile")
            except Exception as e:
                logger.error(f"Failed to read settings.yaml for Groq config: {e}")
                
        return api_key, model

    def _call_groq(self, system_prompt: str, user_prompt: str) -> str:
        api_key, model = self._get_groq_config()
        if not api_key:
            return "ERROR: Groq API key is not configured, sir."

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
            "temperature": 0.2
        }
        
        try:
            r = requests.post("https://api.groq.com/openai/v1/chat/completions", json=payload, headers=headers, timeout=25)
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"]
            else:
                return f"ERROR: Groq API returned status {r.status_code}: {r.text}"
        except Exception as e:
            return f"ERROR: HTTP request failed: {str(e)}"

    def design_architecture(self, description: str) -> str:
        """Generates software architecture specs and Mermaid diagrams."""
        logger.info(f"Designing architecture for: {description}")
        system_prompt = (
            "You are a Principal Software Architect. Design a production-grade software architecture based on the user's description. "
            "Explain the components, data flows, database schemas, and OOP class structures. "
            "You MUST include a clean Mermaid.js diagram representing the architecture."
        )
        user_prompt = f"Design a software architecture for: {description}"
        return self._call_groq(system_prompt, user_prompt)

    def review_code(self, language: str, code: str) -> str:
        """Reviews code for DSA, OOP, concurrency safety, memory leaks, and idioms."""
        logger.info(f"Reviewing {language} code...")
        system_prompt = (
            f"You are a Principal Code Reviewer specializing in {language}. "
            "Analyze the code for syntax faults, memory safety, concurrency bugs, algorithmic efficiency (Big O), and design patterns. "
            "Highlight issues clearly and provide optimized snippets."
        )
        user_prompt = f"Please review this {language} code:\n```\n{code}\n```"
        return self._call_groq(system_prompt, user_prompt)

    def write_polyglot_solution(self, language: str, task: str) -> str:
        """Writes high-quality, optimal code solutions in any programming language (Rust, Go, C++, Zig, Zig-lang, etc.)."""
        logger.info(f"Writing {language} solution for: {task}")
        system_prompt = (
            f"You are a Principal Software Engineer. Write an optimal, production-grade {language} code solution for the given task. "
            "Adhere to design patterns, OOP, memory management, and language-specific idioms (e.g. ownership in Rust, goroutines in Go, manual memory in Zig). "
            "Include explanation of data structures and algorithms (DSA) used."
        )
        user_prompt = f"Write a complete, optimized {language} program/snippet for: {task}"
        return self._call_groq(system_prompt, user_prompt)
