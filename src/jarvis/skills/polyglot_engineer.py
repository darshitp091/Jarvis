import os
import yaml
from loguru import logger

from jarvis.core.llm_client import query_llm

class PolyglotEngineer:
    """Master principal engineer agent that designs architectures, writes polyglot code, and reviews DSA/OOP layouts."""

    def __init__(self, config_path: str = "config/settings.yaml"):
        self.config_path = config_path

    def _ask_llm(self, system_prompt: str, user_prompt: str) -> str:
        """One turn through the shared cascade: NaraRouter, then Mistral, then local.

        This built its own request to api.groq.com until the provider migration,
        which meant a second provider list to keep in step with the real one and
        no fallback at all when that one provider was down. Groq is now the
        speech-to-text provider only.
        """
        config = {}
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f) or {}
            except Exception as e:
                logger.error(f"Failed to read {self.config_path}: {e}")
        return query_llm(
            [{"role": "user", "content": user_prompt}],
            system_prompt=system_prompt,
            config=config,
            models=config.get("models", {}),
        )

    def design_architecture(self, description: str) -> str:
        """Generates software architecture specs and Mermaid diagrams."""
        logger.info(f"Designing architecture for: {description}")
        system_prompt = (
            "You are a Principal Software Architect. Design a production-grade software architecture based on the user's description. "
            "Explain the components, data flows, database schemas, and OOP class structures. "
            "You MUST include a clean Mermaid.js diagram representing the architecture."
        )
        user_prompt = f"Design a software architecture for: {description}"
        return self._ask_llm(system_prompt, user_prompt)

    def review_code(self, language: str, code: str) -> str:
        """Reviews code for DSA, OOP, concurrency safety, memory leaks, and idioms."""
        logger.info(f"Reviewing {language} code...")
        system_prompt = (
            f"You are a Principal Code Reviewer specializing in {language}. "
            "Analyze the code for syntax faults, memory safety, concurrency bugs, algorithmic efficiency (Big O), and design patterns. "
            "Highlight issues clearly and provide optimized snippets."
        )
        user_prompt = f"Please review this {language} code:\n```\n{code}\n```"
        return self._ask_llm(system_prompt, user_prompt)

    def write_polyglot_solution(self, language: str, task: str) -> str:
        """Writes high-quality, optimal code solutions in any programming language (Rust, Go, C++, Zig, Zig-lang, etc.)."""
        logger.info(f"Writing {language} solution for: {task}")
        system_prompt = (
            f"You are a Principal Software Engineer. Write an optimal, production-grade {language} code solution for the given task. "
            "Adhere to design patterns, OOP, memory management, and language-specific idioms (e.g. ownership in Rust, goroutines in Go, manual memory in Zig). "
            "Include explanation of data structures and algorithms (DSA) used."
        )
        user_prompt = f"Write a complete, optimized {language} program/snippet for: {task}"
        return self._ask_llm(system_prompt, user_prompt)
