import os
import sys
import yaml
import requests
import json
from loguru import logger
import ollama

# Store original ollama.chat reference
_original_chat = ollama.chat

def _is_json(text: str) -> bool:
    try:
        json.loads(text)
        return True
    except ValueError:
        return False

def _clean_json_response(text: str) -> str:
    """Strip markdown formatting from JSON output if returned by LLM."""
    text = text.strip()
    if text.startswith("```"):
        # Remove opening ```json or ```
        text = re.sub(r"^```[a-zA-Z0-9]*\n", "", text)
        # Remove closing ```
        text = re.sub(r"\n```$", "", text)
    return text.strip()

def cloudflare_chat_wrapper(model, messages, format=None, options=None, **kwargs):
    """Monkey-patched ollama.chat that transparently routes to Cloudflare Workers AI if configured."""
    # 1. Load settings dynamically to allow runtime configuration changes
    config_path = "config/settings.yaml"
    settings = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                settings = yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning(f"llm_client: Failed to read settings.yaml: {e}")

    cf_conf = settings.get("cloudflare", {})
    account_id = cf_conf.get("account_id")
    api_token = cf_conf.get("api_token")

    # If Cloudflare is enabled and configured, run remote inference
    if account_id and api_token and cf_conf.get("enabled", True):
        # Map models to Cloudflare equivalents
        # Default: Llama 3.1 8B Instruct (great Hinglish, fast, free neuron class)
        cf_model = cf_conf.get("model", "@cf/meta/llama-3.1-8b-instruct")
        
        url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{cf_model}"
        headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json"
        }
        
        # Build payload
        payload = {
            "messages": messages
        }
        
        # Llama 3.1 8B handles temperature in options
        if options and "temperature" in options:
            payload["temperature"] = options["temperature"]

        try:
            logger.debug(f"Cloudflare Workers AI: Routing request to {cf_model}...")
            response = requests.post(url, headers=headers, json=payload, timeout=12)
            
            if response.status_code == 200:
                res_data = response.json()
                if res_data.get("success"):
                    content = res_data["result"]["response"]
                    if isinstance(content, (dict, list)):
                        content = json.dumps(content)
                    
                    # If JSON format was requested, clean and validate it
                    if format == "json":
                        import re
                        cleaned_content = _clean_json_response(content)
                        # If the output is not valid JSON, we attempt to locate the JSON block
                        if not _is_json(cleaned_content):
                            match = re.search(r"\{.*\}", cleaned_content, re.DOTALL)
                            if match:
                                cleaned_content = match.group(0)
                        content = cleaned_content

                    logger.debug("Cloudflare Workers AI: Request successful.")
                    return {
                        "message": {
                            "role": "assistant",
                            "content": content
                        }
                    }
                else:
                    logger.warning(f"Cloudflare Workers AI returned success=False: {res_data}")
            else:
                logger.warning(f"Cloudflare Workers AI API returned status {response.status_code}: {response.text}")
                
        except Exception as e:
            logger.error(f"Cloudflare Workers AI request failed: {e}. Falling back to local Ollama...")

    # Fallback to local Ollama model
    logger.debug(f"Ollama Local: Routing query to local model {model}...")
    return _original_chat(model=model, messages=messages, format=format, options=options, **kwargs)

def patch_ollama():
    """Apply the Cloudflare redirect patch to the ollama module."""
    ollama.chat = cloudflare_chat_wrapper
    logger.info("ollama.chat monkey-patched with Cloudflare Workers AI redirect wrapper.")
