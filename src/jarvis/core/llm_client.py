"""Which model answers, and what happens when it will not.

Everything JARVIS says comes through this module, by two routes that were written
separately and only became visible to each other when `query_llm` moved here out
of `main.py`:

* `bynara_chat_wrapper` is installed as `ollama.chat` by `patch_ollama()`, so it
  intercepts every Ollama call in the process. It routes to NaraRouter
  (router.bynara.id) first, then Mistral, and only when both are unconfigured or
  fail does it hand the call back to the real ollama binding on this machine.
  Both remote legs speak the OpenAI dialect, so one `_openai_chat` helper serves
  both -- the base URL, the key and the model name are all that differ.
* `query_llm` is the named-provider cascade a caller asks for by name. Its own
  last step calls `ollama.chat`, which is this wrapper -- so "falling back to the
  local brain" from query_llm re-enters the same bynara -> mistral -> local path.

Vision rides the same seam. The call sites that show JARVIS the screen pass a
screenshot as base64 in an `images` list inside the message dict; the wrapper
detects that and routes the call to bynara's vision model rather than its text
model. `vision_enabled: false` keeps text remote while forcing any call that
carries a screenshot to stay on this machine.

The provider that used to sit here was Cloudflare Workers AI, reached through its
own non-OpenAI endpoint. It was removed: a live Cloudflare token had already
reached git history through settings.yaml, and NaraRouter serves both text and
vision from one key. That key is resolved "settings.yaml, else BYNARA_API_KEY" so
it can live in a git-ignored .env instead of the config file.

Nothing at module level imports ollama: the lines that need it are inside
`patch_ollama()` and inside `query_llm`'s fallback. That keeps this module
importable -- and therefore testable -- in an environment without a local Ollama
binding, which is the environment CI runs in.
"""
import os
import time
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
# `bynara_chat_wrapper` becomes reachable only by being installed as
# `ollama.chat`, so patch_ollama() has always run before it is called and this
# is set by then. A test calling the wrapper directly sets it itself.
_original_chat = None

# How long a remote provider gets before the call is demoted to the next one.
# There is a local model behind both, so a stalled router must never hang the
# assistant -- but bynara is the *primary* now rather than a bonus path, so the
# budget is wide enough that a normal answer is not cut off and demoted. A vision
# call ships a screenshot and reasons over it, so it gets longer than a sentence.
_TEXT_TIMEOUT = 45
_VISION_TIMEOUT = 90

# Defaults for anything the config does not say. Both roles are the same model
# on purpose: measured against the live router on the free tier, ox-alpha-bynara
# is the only id that answers at conversational speed (~11s) and it reads images
# too, so it serves as both brain and eyes. mistral-large answers but takes ~25s
# for a one-line reply, which a voice assistant cannot spend; every other
# weight-1 id in the catalogue returns "insufficient credits" without a top-up.
# They live here as fallbacks only -- the config is where they are meant to be
# changed when the router's catalogue moves or the account gains credits.
_BYNARA_BASE_URL = "https://router.bynara.id/v1"
_BYNARA_TEXT_MODEL = "ox-alpha-bynara"
_BYNARA_VISION_MODEL = "ox-alpha-bynara"
_MISTRAL_BASE_URL = "https://api.mistral.ai/v1"

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

def _coerce_json(content):
    """Reduce a model reply to the bare JSON object the caller will parse.

    Kept from the Cloudflare wrapper unchanged, because the downstream contract is
    unchanged: callers that pass format="json" -- the intent router among them --
    call json.loads on this content. A model that fences its JSON in markdown or
    narrates around it would otherwise break every one of them.
    """
    if isinstance(content, (dict, list)):
        content = json.dumps(content)
    cleaned = _clean_json_response(content)
    if not _is_json(cleaned):
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            cleaned = match.group(0)
    return cleaned


def _load_settings():
    """config/settings.yaml as a dict, or {} if it is missing or unreadable.

    Re-read on every call, deliberately: switching provider or turning vision off
    takes effect without restarting JARVIS. The cost is one file read per LLM call.

    Returning {} rather than raising is what keeps a broken config from taking the
    process down, since this runs inside every LLM call there is.
    """
    config_path = "config/settings.yaml"
    if not os.path.exists(config_path):
        return {}
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logger.warning(f"llm_client: Failed to read settings.yaml: {e}")
        return {}


def _section(settings, name):
    """One provider block, defaulting to {} when it is absent *or* None.

    `settings.get(name, {})` is not enough and the difference was a real defect: a
    section whose keys are all commented out parses to None, not {}, and the
    default only applies when the key is missing entirely. Since this module is
    every LLM call in the process, one commented-out config key used to take the
    whole assistant down with an AttributeError naming neither the provider nor
    the config file.
    """
    return settings.get(name) or {}


def _resolve_key(conf, env_var):
    """API key from the config block, else the environment.

    The repo idiom -- tts_engine._resolve_fish_key does the same for
    OPENROUTER_API_KEY -- so a secret can live in a git-ignored .env, loaded at
    boot by jarvis.core.env_loader, instead of in settings.yaml, which is the file
    that once carried a live token into git history.

    A "YOUR_..." placeholder left in the config counts as no key, not as a key.
    """
    key = (conf.get("api_key") or "").strip()
    if not key:
        key = (os.environ.get(env_var) or "").strip()
    return "" if key.startswith("YOUR_") else key


def _has_images(messages):
    """Whether this call is a vision call.

    An image reaches this seam as base64 in an `images` list beside `content`,
    which is how ollama carries one. That makes the vision decision a property of
    the messages rather than something the caller has to declare, and is why
    routing vision to a different model needed no change at any of the call sites.
    """
    return any(msg.get("images") for msg in messages)


def _to_openai_messages(messages):
    """ollama-shaped messages -> OpenAI chat format.

    This wrapper stands in for `ollama.chat`, so its input is ollama-shaped:
    `content` is a plain string and any screenshot is raw base64 in an `images`
    list. OpenAI-compatible endpoints instead want the image inside `content`, as
    an `image_url` part holding a data URL. A text-only message keeps its string
    content, which both dialects accept.

    The mime type is declared png because that is what the screen-capture sites
    produce; endpoints sniff the actual bytes, so a jpeg still works.
    """
    converted = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        images = msg.get("images") or []
        if not images:
            converted.append({"role": role, "content": content})
            continue
        parts = []
        if content:
            parts.append({"type": "text", "text": content})
        for image in images:
            # Already a data URL from a caller that built one itself: don't
            # prefix it twice.
            url = (image if str(image).startswith("data:")
                   else f"data:image/png;base64,{image}")
            parts.append({"type": "image_url", "image_url": {"url": url}})
        converted.append({"role": role, "content": parts})
    return converted


def _openai_chat(base_url, api_key, model, messages, options, timeout, label):
    """One non-streaming OpenAI-compatible /chat/completions call.

    Returns the assistant's content, or None if this provider did not answer --
    which is the signal to try the next one. Every failure is a None rather than
    an exception because "did not answer" is the normal case here, not an error:
    the cascade exists precisely because providers fail.

    An empty or whitespace-only reply counts as not answering. It is technically a
    200, but it gives the user silence, and the next provider can do better.
    """
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {"model": model, "messages": messages}
    # Only temperature crosses over. The other ollama options (num_predict,
    # top_p, stop) have no single OpenAI equivalent, so they are dropped rather
    # than guessed at -- silently, which is a known wart kept from the Cloudflare
    # wrapper rather than a new one.
    if options and "temperature" in options:
        payload["temperature"] = options["temperature"]

    try:
        logger.debug(f"{label}: routing request to {model}...")
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
    except Exception as e:
        logger.error(f"{label} request failed: {e}")
        return None

    if response.status_code != 200:
        logger.warning(
            f"{label} returned status {response.status_code}: {response.text}")
        return None

    try:
        content = response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning(f"{label} returned a body this code cannot read: {e}")
        return None

    if content is None:
        logger.warning(f"{label} returned a null content field.")
        return None
    if not isinstance(content, str):
        content = json.dumps(content)
    if not content.strip():
        logger.warning(f"{label} returned an empty reply.")
        return None

    logger.debug(f"{label}: request successful.")
    return content


def _try_bynara(settings, messages, wants_vision, options):
    """The primary provider. Content, or None if off, unconfigured, or failed.

    A call carrying a screenshot goes to the vision model rather than the text
    model; `enabled: false` turns the provider off entirely and hands the call to
    the secondary.
    """
    conf = _section(settings, "bynara")
    if not conf.get("enabled", True):
        return None
    api_key = _resolve_key(conf, "BYNARA_API_KEY")
    if not api_key:
        return None

    if wants_vision:
        model = conf.get("vision_model", _BYNARA_VISION_MODEL)
        timeout = _VISION_TIMEOUT
    else:
        model = conf.get("text_model", _BYNARA_TEXT_MODEL)
        timeout = _TEXT_TIMEOUT

    return _openai_chat(conf.get("base_url", _BYNARA_BASE_URL), api_key, model,
                        messages, options, timeout, "Bynara")


def _try_mistral(settings, messages, wants_vision, options):
    """The secondary provider, reached only when bynara did not answer.

    Mistral names its models per role in the config rather than offering one id,
    so the vision role is picked here the same way the text role is.
    """
    conf = _section(settings, "mistral")
    api_key = _resolve_key(conf, "MISTRAL_API_KEY")
    if not api_key:
        return None

    named = conf.get("models") or {}
    if wants_vision:
        model = named.get("vision", "ministral-8b-2512")
        timeout = _VISION_TIMEOUT
    else:
        model = named.get("brain", "mistral-large-2512")
        timeout = _TEXT_TIMEOUT

    return _openai_chat(_MISTRAL_BASE_URL, api_key, model, messages, options,
                        timeout, "Mistral")


def bynara_chat_wrapper(model, messages, format=None, options=None, **kwargs):
    """Monkey-patched `ollama.chat`: NaraRouter, then Mistral, then local Ollama.

    Installed process-wide by patch_ollama(), so every ollama.chat call in JARVIS
    arrives here -- which is what makes this one function the whole provider
    migration. `model` is the caller's *local* model name; it is used only if the
    call gets as far as the local binding, because the remote model comes from the
    config instead.

    Always returns ollama's response shape, `{"message": {"role": ..., "content":
    ...}}`. That shape is the real contract, more binding than the signature:
    every call site in the tree reads `response["message"]["content"]`.
    """
    settings = _load_settings()
    wants_vision = _has_images(messages)

    # A screenshot is not the same class of data as a sentence. With vision
    # switched off, a call that needs vision goes straight to the local model --
    # which can see the image -- and is not offered to the secondary either, since
    # that is equally off this machine. Text-only calls are unaffected.
    if wants_vision and not _section(settings, "bynara").get("vision_enabled", True):
        logger.debug("Vision is disabled: this screenshot stays on this machine.")
    else:
        remote_messages = _to_openai_messages(messages)
        content = _try_bynara(settings, remote_messages, wants_vision, options)
        if content is None:
            content = _try_mistral(settings, remote_messages, wants_vision, options)
        if content is not None:
            if format == "json":
                content = _coerce_json(content)
            return {"message": {"role": "assistant", "content": content}}

    # Fallback to the local Ollama model. The original messages go through, not
    # the converted ones: the local binding wants the ollama shape it was handed.
    logger.debug(f"Ollama Local: Routing query to local model {model}...")
    return _original_chat(model=model, messages=messages, format=format, options=options, **kwargs)

def patch_ollama():
    """Install the bynara redirect as `ollama.chat`, capturing the real one once."""
    global _original_chat
    import ollama
    # Only the first call captures. Without the guard a second call would
    # capture the wrapper as its own original and recurse forever; capturing at
    # import time used to make double-patching harmless, and this keeps it so.
    if _original_chat is None:
        _original_chat = ollama.chat
    ollama.chat = bynara_chat_wrapper
    logger.info("ollama.chat monkey-patched with the bynara -> mistral -> local redirect.")


# ---------------------------------------------------------------------------
# The provider cascade, moved verbatim out of JARVIS.query_llm.
#
# It belongs beside bynara_chat_wrapper rather than in the orchestrator, and
# putting the two in one file makes the relationship between them explicit.
# They are two cascades over the same three providers, reached by callers that
# speak two different message dialects: the wrapper stands in for `ollama.chat`
# and so takes ollama-shaped messages, while these callers pass OpenAI-shaped
# ones. That is the only reason both exist. This one runs bynara -> mistral
# itself and then calls the *real* ollama binding, so the two do not nest.
# ---------------------------------------------------------------------------

def _local_chat():
    """The real `ollama.chat`, never the wrapper installed over it.

    query_llm runs its own bynara -> mistral cascade before reaching this leg, so
    the leg has to be the genuine local binding. Going through the patched
    `ollama.chat` instead would retry the two remote providers that just declined,
    and -- worse -- would send a `provider="local"` call to the cloud, which is
    the defect this replaces. `_original_chat` holds the real one once
    patch_ollama has run; before that, `ollama.chat` is still itself.
    """
    import ollama
    return _original_chat or ollama.chat


def _has_image_parts(messages) -> bool:
    """Is this an OpenAI-shaped vision call?

    query_llm's callers speak the OpenAI dialect directly -- `content` is a list
    of parts and a screenshot arrives as an `image_url` part (see
    screen_vision.py). That is a different shape from the ollama one
    `_has_images` looks for, which is why this is a second detector rather than a
    reuse of that one.
    """
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "image_url":
                    return True
    return False


def query_llm(messages: list, system_prompt: str = None, provider: str = "bynara", model: str = None, *,
              config: dict, models: dict) -> str:
    """Queries the LLM cascade: NaraRouter, then Mistral, then the local Ollama brain.

    `provider` selects the *entry point*, not the only provider tried. The default
    and every unrecognised value start at bynara and fall through the whole
    cascade; `provider="local"` is the one value that skips both remote legs, so
    a caller asking for the local brain now actually gets it.

    Messages arrive here already OpenAI-shaped -- `content` may be a list of text
    and `image_url` parts -- which is exactly what the remote legs want, so they
    are forwarded without conversion. Only the local leg needs them rewritten
    into ollama's `images` form.
    """
    query_messages = []
    if system_prompt:
        query_messages.append({"role": "system", "content": system_prompt})
    query_messages.extend(messages)

    wants_vision = _has_image_parts(query_messages)

    # 1. NaraRouter (bynara), the primary. Skipped only when the caller explicitly
    # asked for the local brain. `model` is deliberately ignored here: it names a
    # Mistral or Ollama model at almost every call site, and the bynara model is a
    # config value chosen per role (text vs vision) instead.
    if provider != "local":
        content = _try_bynara(config, query_messages, wants_vision, None)
        if content is not None:
            return content

    # 2. Mistral, the secondary. One path for every entry point: the secondary
    # should not behave differently depending on which name the caller used to
    # get here. Streaming is kept because it prints the reply as it arrives.
    if provider != "local":
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

    # 3. Local Ollama brain, the fallback.
    try:
        logger.info("Falling back to local Ollama brain...")
        import ollama
        # `model` names the local brain at the provider="local" call sites, which
        # passed it and were then ignored while the request went to the cloud.
        model_name = model or models.get("main_brain", "yasserrmd/Human-Like-Qwen2.5-1.5B-Instruct:latest")

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

        response = _local_chat()(
            model=model_name,
            messages=ollama_messages
        )
        return response["message"]["content"]
    except Exception as e:
        logger.error(f"Local Ollama query failed: {e}")
        return "I am currently unable to process your request, sir."


# ---------------------------------------------------------------------------
# Ollama process supervision, moved verbatim out of JARVIS._ensure_ollama_server.
#
# It lives here because this is the module that ends up talking to Ollama, twice
# over: query_llm's last step calls ollama.chat, and bynara_chat_wrapper falls
# back to the real binding when neither remote provider answers. Both of
# those assume a server on port 11434 that nothing in this module was starting
# -- main.py called this at boot and the connection between the two facts was
# not written down anywhere. Now it is: this is the function that makes the
# fallback in both of them possible.
#
# The three imports inside the body are as they were in main.py. os is already
# imported at module level, so the local one is redundant, but it is the first
# statement of the body and therefore shadows nothing that runs before it --
# unlike the mid-function `import os` that took 661ff99 to find.
# ---------------------------------------------------------------------------
def ensure_ollama_server():
    """Checks if Ollama server is running on port 11434, and if not, launches it in the background."""
    import socket
    import subprocess
    import os
    
    def is_running():
        try:
            with socket.create_connection(("localhost", 11434), timeout=1):
                return True
        except OSError:
            return False

    if is_running():
        logger.info("Ollama background server is already active.")
        return

    logger.info("Ollama server not active. Attempting to launch background server...")
    try:
        # Resolve executable path on Windows
        ollama_cmd = "ollama"
        if os.name == 'nt':
            user_profile = os.environ.get("USERPROFILE", "")
            fallback_path = os.path.join(user_profile, "AppData", "Local", "Programs", "Ollama", "ollama.exe")
            if os.path.exists(fallback_path):
                ollama_cmd = fallback_path

        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # SW_HIDE
            
        creationflags = 0
        if os.name == 'nt':
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | 0x08000000 # DETACHED_PROCESS
            
        subprocess.Popen(
            [ollama_cmd, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            startupinfo=startupinfo,
            creationflags=creationflags
        )
        
        # Wait up to 10 seconds for the server to bind and respond
        for attempt in range(10):
            if is_running():
                logger.info("Ollama server successfully launched and active.")
                return
            time.sleep(1)
        logger.warning("Ollama server launched but did not respond on port 11434 within 10 seconds.")
    except Exception as e:
        logger.error(f"Failed to auto-start Ollama server: {e}")
