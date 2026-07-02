import ollama
import yaml
import os
from loguru import logger


class MedicalDomain:
    """Specialized handler for medical queries using medgemma"""

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

            self.model = self.settings.get("models", {}).get("medical", "medgemma")
            self.system_prompt = self.prompts.get("system_prompts", {}).get("medical", "You are JARVIS with medical knowledge.")
        except Exception as e:
            logger.error(f"Failed to load config in MedicalDomain: {e}")
            self.model = "medgemma"
            self.system_prompt = "You are JARVIS with medical knowledge."

    def answer(self, query: str, memories: str = "") -> str:
        """Process a medical query"""
        system_content = f"{self.system_prompt}\n{memories}"
        if self.jarvis is not None:
            return self.jarvis.query_llm([{"role": "user", "content": query}], system_prompt=system_content)
            
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
            logger.error(f"Medical domain error: {e}")
            return "I am currently unable to access my medical knowledge base, sir."


if __name__ == "__main__":
    expert = MedicalDomain()
    print("Testing Medical Domain...")
    print(expert.answer("What are the common symptoms of a mild concussion?"))
