"""Which model answers, and what happens when it will not.

Everything JARVIS says comes through this module, by two routes that were written
separately and only became visible to each other when `query_llm` moved here out
of `main.py`:

* `query_llm` is the four-provider cascade a caller asks for by name: Mistral
  (streaming), OfoxAI (streaming, only when named), Groq, then local Ollama.
  Each step logs its failure and falls to the next; the last one returns a fixed
  apology rather than raising.
* `cloudflare_chat_wrapper` is installed as `ollama.chat` by `patch_ollama()`, so
  it intercepts every Ollama call in the process -- including step 4 of that
  cascade. It routes to Cloudflare Workers AI when settings.yaml is configured
  for it, and falls back to the real ollama binding when it is not, or when the
  remote call fails.

So "falling back to the local brain" may in fact reach Cloudflare, and only if
*that* fails does a model on this machine answer. Five possible responders behind
one function call, and the config file that picks between them is re-read on
every single request.

Nothing at module level imports ollama: the two lines that need it are inside
`patch_ollama()` and inside `query_llm`'s fallback. That keeps this module
importable -- and therefore testable -- in an environment without a local Ollama
binding, which is the environment CI runs in.
"""
import os
import yaml
import requests
import json
import re
from loguru import logger

# The original `ollama.chat`, captured by patch_ollama() rather than at import
# time. Importing ollama here made this module unimportable without a local
# Ollama binding installed -- which meant nothing in it could be tested, in an
# environment that deliberately does not install one. The two lines that need
# ollama are both inside patch_ollama(); nothing else here touches it.
#
# `cloudflare_chat_wrapper` becomes reachable only by being installed as
# `ollama.chat`, so patch_ollama() has always run before it is called and this
# is set by then. A test calling the wrapper directly sets it itself.
_original_chat = None

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
    global _original_chat
    import ollama
    # Only the first call captures. Without the guard a second call would
    # capture the wrapper as its own original and recurse forever; capturing at
    # import time used to make double-patching harmless, and this keeps it so.
    if _original_chat is None:
        _original_chat = ollama.chat
    ollama.chat = cloudflare_chat_wrapper
    logger.info("ollama.chat monkey-patched with Cloudflare Workers AI redirect wrapper.")


# ---------------------------------------------------------------------------
# The provider cascade, moved verbatim out of JARVIS.query_llm.
#
# It belongs beside cloudflare_chat_wrapper rather than in the orchestrator, and
# putting the two in one file makes a relationship visible that was invisible
# while they lived apart: step 4 below calls `ollama.chat`, which patch_ollama()
# has replaced with the wrapper above. So "falling back to the local brain" may
# reach Cloudflare instead, and if that fails the wrapper falls back to the real
# ollama binding. Two layers of fallback, previously in two different files.
# ---------------------------------------------------------------------------

def query_llm(messages: list, system_prompt: str = None, provider: str = "mistral", model: str = None, *,
              config: dict, models: dict) -> str:
    """Queries the active LLM provider (mistral, ofoxai, groq, or local Ollama fallback)."""
    query_messages = []
    if system_prompt:
        query_messages.append({"role": "system", "content": system_prompt})
    query_messages.extend(messages)

    # 1. Mistral AI Provider
    if provider == "mistral":
        mistral_cfg = config.get("mistral", {})
        api_key = mistral_cfg.get("api_key", "")
        target_model = model or mistral_cfg.get("models", {}).get("brain", "mistral-large-2512")

        if api_key and not api_key.startswith("YOUR_"):
            import requests
            url = "https://api.mistral.ai/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            data = {
                "model": target_model,
                "messages": query_messages,
                "temperature": 0.2,
                "stream": True
            }
            try:
                logger.info(f"Querying Mistral API using model '{target_model}' (streaming enabled)...")
                response = requests.post(url, headers=headers, json=data, stream=True, timeout=25)
                if response.status_code == 200:
                    reply_parts = []
                    print("JARVIS: ", end="", flush=True)
                    for line in response.iter_lines():
                        if line:
                            decoded_line = line.decode('utf-8').strip()
                            if decoded_line.startswith("data:"):
                                data_content = decoded_line[5:].strip()
                                if data_content == "[DONE]":
                                    break
                                try:
                                    chunk_json = json.loads(data_content)
                                    delta = chunk_json["choices"][0].get("delta", {})
                                    if "content" in delta:
                                        text_chunk = delta["content"]
                                        print(text_chunk, end="", flush=True)
                                        reply_parts.append(text_chunk)
                                except Exception:
                                    pass
                    print()
                    reply = "".join(reply_parts)
                    logger.info("Successfully received streamed response from Mistral.")
                    return reply
                else:
                    logger.error(f"Mistral API returned error status {response.status_code}: {response.text}")
            except Exception as e:
                logger.error(f"Mistral API connection failed: {e}")

    # 2. OfoxAI Provider
    elif provider == "ofoxai":
        ofox_cfg = config.get("ofoxai", {})
        api_key = ofox_cfg.get("api_key", "")
        target_model = model or ofox_cfg.get("model", "z-ai/glm-4.7-flash:free")

        if api_key and not api_key.startswith("YOUR_"):
            try:
                logger.info(f"Querying OfoxAI API using model '{target_model}'...")
                from openai import OpenAI
                client = OpenAI(
                    base_url="https://api.ofox.ai/v1",
                    api_key=api_key
                )
                ofox_messages = []
                if system_prompt:
                    ofox_messages.append({"role": "system", "content": system_prompt})

                for msg in messages:
                    content = msg["content"]
                    if isinstance(content, list):
                        text_content = ""
                        for part in content:
                            if part.get("type") == "text":
                                text_content += part.get("text", "")
                        ofox_messages.append({"role": msg["role"], "content": text_content})
                    else:
                        ofox_messages.append(msg)

                response_stream = client.chat.completions.create(
                    model=target_model,
                    messages=ofox_messages,
                    temperature=0.1,
                    max_tokens=300,
                    stream=True,
                    timeout=25
                )
                reply_parts = []
                print("JARVIS: ", end="", flush=True)
                for chunk in response_stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        text_chunk = chunk.choices[0].delta.content
                        print(text_chunk, end="", flush=True)
                        reply_parts.append(text_chunk)
                print()
                reply = "".join(reply_parts)
                logger.info("Successfully received streamed response from OfoxAI.")
                return reply
            except Exception as e:
                logger.error(f"OfoxAI API connection failed: {e}")

    # 3. Groq API Provider Fallback
    groq_cfg = config.get("groq", {})
    groq_api_key = groq_cfg.get("api_key", "")
    groq_model = groq_cfg.get("model", "llama-3.3-70b-versatile")

    if groq_api_key and not groq_api_key.startswith("YOUR_"):
        import requests
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {groq_api_key}",
            "Content-Type": "application/json"
        }
        # Flatten/convert messages if multimodal
        groq_messages = []
        for msg in query_messages:
            content = msg["content"]
            if isinstance(content, list):
                text_content = ""
                for part in content:
                    if part.get("type") == "text":
                        text_content += part.get("text", "")
                groq_messages.append({"role": msg["role"], "content": text_content})
            else:
                groq_messages.append(msg)

        data = {
            "model": groq_model,
            "messages": groq_messages,
            "temperature": 0.3
        }
        try:
            logger.info(f"Querying Groq API using model '{groq_model}'...")
            response = requests.post(url, headers=headers, json=data, timeout=25)
            if response.status_code == 200:
                result = response.json()
                reply = result["choices"][0]["message"]["content"]
                logger.info("Successfully received response from Groq.")
                return reply
            else:
                logger.error(f"Groq API returned error status {response.status_code}: {response.text}")
        except Exception as e:
            logger.error(f"Groq API connection failed: {e}")

    # 4. Local Ollama Fallback (with base64 image extraction)
    try:
        logger.info("Falling back to local Ollama brain...")
        import ollama
        model_name = models.get("main_brain", "yasserrmd/Human-Like-Qwen2.5-1.5B-Instruct:latest")

        ollama_messages = []
        for msg in query_messages:
            content = msg["content"]
            images = []
            text_content = ""

            if isinstance(content, list):
                for part in content:
                    if part.get("type") == "text":
                        text_content += part.get("text", "")
                    elif part.get("type") == "image_url":
                        url_val = part.get("image_url", {}).get("url", "")
                        if "base64," in url_val:
                            base64_data = url_val.split("base64,")[1]
                            images.append(base64_data)
            else:
                text_content = content

            ollama_msg = {"role": msg["role"], "content": text_content}
            if images:
                ollama_msg["images"] = images
            ollama_messages.append(ollama_msg)

        response = ollama.chat(
            model=model_name,
            messages=ollama_messages
        )
        return response["message"]["content"]
    except Exception as e:
        logger.error(f"Local Ollama query failed: {e}")
        return "I am currently unable to process your request, sir."
