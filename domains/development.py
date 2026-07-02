import ollama
import yaml
import os
from loguru import logger


class DevelopmentDomain:
    """Specialized handler for development queries using codegemma"""

    def __init__(self, config_path: str = "config", jarvis = None):
        self.jarvis = jarvis
        if not os.path.exists(config_path):
            fallback = os.path.join(os.path.dirname(__file__), "..", config_path)
            if os.path.exists(fallback):
                config_path = fallback

        try:
            with open(os.path.join(config_path, "settings.yaml")) as f:
                self.settings = yaml.safe_load(f)
            with open(os.path.join(config_path, "prompts.yaml")) as f:
                self.prompts = yaml.safe_load(f)

            self.model = self.settings.get("models", {}).get("code", "codegemma")
            self.system_prompt = self.prompts.get("system_prompts", {}).get("development", "You are JARVIS with software development knowledge.")
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            self.model = "codegemma"
            self.system_prompt = "You are JARVIS with software development knowledge."

    def answer(self, query: str, memories: str = "") -> str:
        system_content = f"{self.system_prompt}\n{memories}"
        if self.jarvis is not None:
            return self.jarvis.query_llm([{"role": "user", "content": query}], system_prompt=system_content, provider="mistral", model="codestral-2405")
            
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
            logger.error(f"Development domain error: {e}")
            return "My development and coding modules are unresponsive, sir."


if __name__ == "__main__":
    expert = DevelopmentDomain()
    print("Testing Development Domain...")
    print(expert.answer("Write a simple Python function to calculate the Fibonacci sequence."))
