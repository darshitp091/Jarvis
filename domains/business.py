import ollama
import yaml
import os
from loguru import logger


class BusinessDomain:
    """Specialized handler for business queries"""

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

            self.model = self.settings.get("models", {}).get("main_brain", "qwen2.5")
            self.system_prompt = self.prompts.get("system_prompts", {}).get("business", "You are JARVIS with business knowledge.")
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            self.model = "qwen2.5"
            self.system_prompt = "You are JARVIS with business knowledge."

    def answer(self, query: str, memories: str = "") -> str:
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
            logger.error(f"Business domain error: {e}")
            return "I am unable to access my business data at this moment, sir."


if __name__ == "__main__":
    expert = BusinessDomain()
    print("Testing Business Domain...")
    print(expert.answer("What are the core components of a successful pitch deck?"))
