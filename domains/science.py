import ollama
import yaml
import os
from loguru import logger


class ScienceDomain:
    """Specialized handler for advanced scientific research queries: quantum computing, nanotechnology, biology, and holograms."""

    def __init__(self, config_path: str = "config"):
        if not os.path.exists(config_path):
            fallback = os.path.join(os.path.dirname(__file__), "..", config_path)
            if os.path.exists(fallback):
                config_path = fallback

        try:
            with open(os.path.join(config_path, "settings.yaml")) as f:
                self.settings = yaml.safe_load(f)
            with open(os.path.join(config_path, "prompts.yaml")) as f:
                self.prompts = yaml.safe_load(f)

            self.model = self.settings.get("models", {}).get("science", "yasserrmd/Human-Like-Qwen2.5-1.5B-Instruct:latest")
            self.system_prompt = self.prompts.get("system_prompts", {}).get("science", "You are JARVIS, an expert in quantum mechanics, nanotechnology, molecular simulation, and holography.")
        except Exception as e:
            logger.error(f"Failed to load config in ScienceDomain: {e}")
            self.model = "yasserrmd/Human-Like-Qwen2.5-1.5B-Instruct:latest"
            self.system_prompt = "You are JARVIS, an expert in quantum mechanics, nanotechnology, molecular simulation, and holography."

    def answer(self, query: str, memories: str = "") -> str:
        """Process a scientific research query"""
        system_content = f"{self.system_prompt}\n{memories}"
        try:
            response = ollama.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": query}
                ]
            )
            return response["message"]["content"]
        except Exception as e:
            logger.error(f"Science domain error: {e}")
            return "I am currently unable to access my scientific core databases, sir."


if __name__ == "__main__":
    expert = ScienceDomain()
    print("Testing Science Domain...")
    print(expert.answer("Explain quantum superposition in simple terms."))
