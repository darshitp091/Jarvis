"""Tests for jarvis.core.llm_client.query_llm -- the four-provider cascade.

188 lines that lived in `main.py` as `JARVIS.query_llm` and so could not be
tested: main.py imports PyQt6, ollama and pyautogui at module level. It is the
function every spoken answer passes through, and it silently changes provider
four times before giving up.

The cascade, in the order the code tries it: Mistral (streaming), OfoxAI
(streaming, only if `provider="ofoxai"` was asked for), Groq (always tried if
neither returned), then local Ollama. Each step logs its failure and falls to the
next; the last one returns a fixed apology.

Nothing here touches the network. `requests.post` is patched as an attribute of
the shared module object rather than by rebinding a name, because the function
does its own `import requests` inside the body -- a local rebinding would not be
seen. `openai` and `ollama` are injected into sys.modules as stand-ins, which
also keeps them off the test environment's dependency list.
"""

import ast
import inspect
import json
import os
import sys
import types

import pytest

from jarvis.core import llm_client

MESSAGES = [{"role": "user", "content": "kitna time hua hai"}]

# A config with no usable provider: every branch is skipped and control reaches
# the Ollama fallback. Tests that want one provider live enable just that one.
NO_PROVIDERS = {
    "mistral": {"api_key": "YOUR_MISTRAL_KEY"},
    "ofoxai": {"api_key": ""},
    "groq": {"api_key": "YOUR_GROQ_KEY"},
}
MODELS = {"main_brain": "test-brain:latest"}


class FakeStream:
    """A requests response whose iter_lines() replays server-sent event lines."""

    def __init__(self, lines, status_code=200, text=""):
        self._lines = lines
        self.status_code = status_code
        self.text = text

    def iter_lines(self):
        for line in self._lines:
            yield line if isinstance(line, bytes) else line.encode("utf-8")


class FakeJson:
    """A non-streaming requests response."""

    def __init__(self, payload=None, status_code=200, text=""):
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def sse(*contents):
    """The SSE frames Mistral sends for a reply delivered in `contents` chunks."""
    frames = ['data: {"choices": [{"delta": {"content": %s}}]}' % json.dumps(c)
              for c in contents]
    return frames + ["data: [DONE]"]


@pytest.fixture(autouse=True)
def no_ambient_keys(monkeypatch):
    """No provider is live here unless a test's config says so.

    Every key in these configs is fake, but a blank one falls back to the
    environment -- so a real key exported in the shell, or one left behind by
    another test file, would silently promote a provider the test meant to skip
    and steal the leg being asserted on.
    """
    for name in ("BYNARA_API_KEY", "MISTRAL_API_KEY", "GROQ_API_KEY"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def http(monkeypatch):
    """Patch requests.post on the module object the function-local import sees."""
    calls = []

    def fake_post(url, headers=None, json=None, stream=False, timeout=None):
        calls.append({"url": url, "headers": headers, "json": json,
                      "stream": stream, "timeout": timeout})
        result = fake_post.response
        if isinstance(result, Exception):
            raise result
        return result

    fake_post.calls = calls
    fake_post.response = FakeStream(sse("hi"))
    monkeypatch.setattr(llm_client.requests, "post", fake_post)
    return fake_post


@pytest.fixture
def ollama(monkeypatch):
    """A stand-in ollama module, recording the chat() call it receives."""
    module = types.ModuleType("ollama")
    module.calls = []

    def chat(model=None, messages=None, **kwargs):
        module.calls.append({"model": model, "messages": messages, **kwargs})
        if isinstance(module.response, Exception):
            raise module.response
        return module.response

    module.chat = chat
    module.response = {"message": {"content": "from ollama"}}
    monkeypatch.setitem(sys.modules, "ollama", module)
    return module


def query(**kwargs):
    kwargs.setdefault("config", NO_PROVIDERS)
    kwargs.setdefault("models", MODELS)
    kwargs.setdefault("messages", MESSAGES)
    return llm_client.query_llm(**kwargs)


# -- Mistral, the first provider tried -----------------------------------


MISTRAL_ON = {"mistral": {"api_key": "real-key",
                          "models": {"brain": "mistral-small-2503"}},
              "groq": {"api_key": ""}}


def test_a_streamed_mistral_reply_is_joined_in_order(http, ollama):
    http.response = FakeStream(sse("Sir, ", "it is ", "half past three."))
    assert query(config=MISTRAL_ON) == "Sir, it is half past three."
    assert ollama.calls == [], "the fallback should not have been reached"


def test_the_stream_stops_at_the_done_sentinel(http, ollama):
    http.response = FakeStream(sse("kept") + ['data: {"choices": [{"delta": '
                                              '{"content": "after DONE"}}]}'])
    assert query(config=MISTRAL_ON) == "kept"


def test_a_malformed_frame_is_skipped_without_losing_the_rest(http, ollama):
    """The bare `except Exception: pass` in the chunk loop. A provider emitting
    one bad frame mid-stream must not cost the whole reply."""
    http.response = FakeStream(['data: {"choices": [{"delta": {"content": "a"}}]}',
                                "data: {not json}",
                                'data: {"choices": []}',
                                'data: {"choices": [{"delta": {"content": "b"}}]}',
                                "data: [DONE]"])
    assert query(config=MISTRAL_ON) == "ab"


def test_frames_without_content_contribute_nothing(http, ollama):
    """The role-only opening frame and the finish_reason closing frame."""
    http.response = FakeStream(['data: {"choices": [{"delta": {"role": "assistant"}}]}',
                                'data: {"choices": [{"delta": {"content": "x"}}]}',
                                'data: {"choices": [{"delta": {}, "finish_reason": "stop"}]}',
                                "data: [DONE]"])
    assert query(config=MISTRAL_ON) == "x"


def test_lines_that_are_not_data_frames_are_ignored(http, ollama):
    """Keep-alive comments and blank lines are part of the SSE wire format."""
    http.response = FakeStream(["", ": keep-alive", b"",
                                'data: {"choices": [{"delta": {"content": "y"}}]}',
                                "data: [DONE]"])
    assert query(config=MISTRAL_ON) == "y"


def test_the_reply_is_printed_as_it_streams(http, ollama, capsys):
    """User-visible: the console shows the answer arriving word by word, which is
    why the function prints as well as returns."""
    http.response = FakeStream(sse("one ", "two"))
    query(config=MISTRAL_ON)
    assert capsys.readouterr().out == "JARVIS: one two\n"


def test_the_request_is_addressed_and_shaped_from_the_config(http, ollama):
    query(config=MISTRAL_ON, system_prompt="You are JARVIS.")
    call = http.calls[0]
    assert call["url"] == "https://api.mistral.ai/v1/chat/completions"
    assert call["headers"]["Authorization"] == "Bearer real-key"
    assert call["json"]["model"] == "mistral-small-2503"
    assert call["json"]["stream"] is True
    assert call["json"]["temperature"] == 0.2
    assert call["stream"] is True
    assert call["timeout"] == 25


def test_the_system_prompt_is_prepended_as_a_system_message(http, ollama):
    query(config=MISTRAL_ON, system_prompt="You are JARVIS.")
    assert http.calls[0]["json"]["messages"] == [
        {"role": "system", "content": "You are JARVIS."},
        {"role": "user", "content": "kitna time hua hai"},
    ]


def test_without_a_system_prompt_only_the_messages_are_sent(http, ollama):
    query(config=MISTRAL_ON)
    assert http.calls[0]["json"]["messages"] == MESSAGES


def test_an_explicit_model_argument_beats_the_configured_one(http, ollama):
    query(config=MISTRAL_ON, model="mistral-large-2512")
    assert http.calls[0]["json"]["model"] == "mistral-large-2512"


def test_with_no_model_configured_a_default_is_used(http, ollama):
    query(config={"mistral": {"api_key": "k"}, "groq": {"api_key": ""}})
    assert http.calls[0]["json"]["model"] == "mistral-large-2512"


@pytest.mark.parametrize(
    "mistral",
    [
        {"api_key": ""},
        {"api_key": "YOUR_MISTRAL_API_KEY_HERE"},
        {},
        {"api_key": None},
    ],
    ids=["empty", "placeholder", "absent", "none"],
)
def test_an_unusable_mistral_key_skips_the_provider_entirely(http, ollama, mistral):
    """The `YOUR_` prefix check is what makes a fresh settings.yaml.example work
    without editing: the placeholder keys are recognised, not attempted."""
    query(config={"mistral": mistral, "groq": {"api_key": ""}})
    assert http.calls == [], "no HTTP call should have been made"
    assert len(ollama.calls) == 1


@pytest.mark.parametrize(
    "response",
    [
        FakeStream([], status_code=500, text="server error"),
        FakeStream([], status_code=401, text="bad key"),
        FakeStream([], status_code=429, text="slow down"),
    ],
    ids=["500", "401", "429"],
)
def test_a_mistral_http_error_falls_through_to_the_next_provider(
        http, ollama, response):
    http.response = response
    assert query(config=MISTRAL_ON) == "from ollama"


def test_a_mistral_connection_error_falls_through(http, ollama):
    http.response = llm_client.requests.exceptions.Timeout("timed out")
    assert query(config=MISTRAL_ON) == "from ollama"


def test_an_empty_stream_is_returned_as_success(http, ollama):
    """Pinned, not fixed. A 200 whose stream carries no content frames -- a
    truncated response, a refusal, a model that emitted only a stop -- makes
    `reply` the empty string, and the function returns it and logs
    "Successfully received streamed response". Nothing downstream tries the
    other three providers, so the user gets silence where a fallback existed.

    Guarding it is one line (`if reply:` before the return), but the choice is
    not free: an empty reply is occasionally the honest answer, and turning it
    into three more provider attempts adds latency to that case. Recorded here so
    the decision is made deliberately rather than by default.
    """
    http.response = FakeStream(["data: [DONE]"])
    assert query(config=MISTRAL_ON) == ""
    assert ollama.calls == []


# -- local Ollama, the floor of the cascade ------------------------------


def test_the_fallback_uses_the_configured_brain(http, ollama):
    assert query() == "from ollama"
    assert ollama.calls[0]["model"] == "test-brain:latest"


def test_with_no_brain_configured_a_default_model_is_used(http, ollama):
    query(models={})
    assert ollama.calls[0]["model"].startswith("yasserrmd/Human-Like-Qwen2.5")


def test_plain_messages_reach_ollama_unchanged_in_role_and_text(http, ollama):
    query(system_prompt="You are JARVIS.")
    assert ollama.calls[0]["messages"] == [
        {"role": "system", "content": "You are JARVIS."},
        {"role": "user", "content": "kitna time hua hai"},
    ]


def test_a_base64_image_is_lifted_out_into_ollamas_images_field(http, ollama):
    """The one provider that can actually see the screenshot: Ollama takes images
    as a separate list of base64 payloads rather than inline in the content, so
    this is a reshaping, not a flattening like the other two providers do."""
    query(messages=[{
        "role": "user",
        "content": [{"type": "text", "text": "what is on screen?"},
                    {"type": "image_url",
                     "image_url": {"url": "data:image/png;base64,QUJD"}}],
    }])
    assert ollama.calls[0]["messages"] == [
        {"role": "user", "content": "what is on screen?", "images": ["QUJD"]}]


def test_several_images_in_one_message_are_all_carried(http, ollama):
    query(messages=[{
        "role": "user",
        "content": [{"type": "image_url", "image_url": {"url": "data:image/png;base64,AA"}},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,BB"}}],
    }])
    assert ollama.calls[0]["messages"][0]["images"] == ["AA", "BB"]


def test_a_message_with_no_image_has_no_images_key(http, ollama):
    """Sending an empty list would make every text message look multimodal."""
    query(messages=[{"role": "user", "content": [{"type": "text", "text": "hi"}]}])
    assert ollama.calls[0]["messages"] == [{"role": "user", "content": "hi"}]


def test_an_image_url_that_is_not_base64_is_dropped(http, ollama):
    """The extraction keys off the literal "base64," marker, so a plain http
    image URL is silently discarded rather than passed on -- correct, since
    Ollama cannot fetch it, but the text arrives with the question unanswerable."""
    query(messages=[{
        "role": "user",
        "content": [{"type": "text", "text": "see this"},
                    {"type": "image_url", "image_url": {"url": "https://x.io/a.png"}}],
    }])
    assert ollama.calls[0]["messages"] == [{"role": "user", "content": "see this"}]


def test_when_even_ollama_fails_the_user_gets_an_apology_not_a_traceback(http, ollama):
    """The floor of the cascade. Every provider is down or unconfigured; this
    string is what gets spoken."""
    ollama.response = RuntimeError("connection refused")
    assert query() == "I am currently unable to process your request, sir."


def test_a_reply_missing_its_message_key_is_also_caught(http, ollama):
    ollama.response = {"unexpected": "shape"}
    assert query() == "I am currently unable to process your request, sir."


def test_the_local_leg_bypasses_the_patched_chat(http, ollama, monkeypatch):
    """The local leg must call the *real* ollama binding, not the wrapper that
    patch_ollama() installs over `ollama.chat`.

    This is what makes provider="local" mean local. Going through the wrapper
    would re-try bynara and mistral -- the two providers this cascade has already
    asked and been declined by -- and would send a caller who explicitly wanted
    the local brain out to the cloud instead. That was the defect."""
    real = []

    def really_local(model=None, messages=None, **kwargs):
        real.append(model)
        return {"message": {"content": "from the real binding"}}

    def wrapper(model=None, messages=None, **kwargs):
        raise AssertionError("the local leg went through the patched wrapper")

    monkeypatch.setattr(llm_client, "_original_chat", really_local)
    monkeypatch.setattr(sys.modules["ollama"], "chat", wrapper)

    assert query() == "from the real binding"
    assert real == ["test-brain:latest"]


# -- the cascade's order and entry points --------------------------------
#
# query_llm's callers speak the OpenAI dialect, so these exercise the bynara leg
# through that shape rather than ollama's `images` one.

BYNARA_ON = {"bynara": {"api_key": "bynara-key", "text_model": "ox-alpha-bynara",
                        "vision_model": "ox-vision"},
             "mistral": {"api_key": "real-key"}}


def _bynara_reply(text):
    return FakeJson({"choices": [{"message": {"content": text}}]})


def test_bynara_answers_first_and_mistral_is_never_asked(http, ollama):
    """The whole point of the migration: the primary provider goes first, and a
    reply from it ends the cascade."""
    http.response = _bynara_reply("from bynara")
    assert query(config=BYNARA_ON) == "from bynara"
    assert len(http.calls) == 1
    assert "router.bynara.id" in http.calls[0]["url"]
    assert ollama.calls == []


def test_an_unrecognised_provider_name_starts_at_bynara(http, ollama):
    """Replaces the old characterisation test, which pinned a typo landing on
    Groq's cloud. A misspelled name now enters at the primary, which is the
    harmless default rather than a silent detour to a deleted provider."""
    http.response = _bynara_reply("from bynara")
    assert query(config=BYNARA_ON, provider="mistrall") == "from bynara"
    assert "router.bynara.id" in http.calls[0]["url"]


def test_provider_local_skips_both_remote_legs(http, ollama):
    """The defect this commit fixes. These call sites exist in main.py precisely
    to degrade to the local brain, and they were reaching the cloud instead."""
    http.response = _bynara_reply("should never be asked for")
    assert query(config=BYNARA_ON, provider="local") == "from ollama"
    assert http.calls == []
    assert len(ollama.calls) == 1


def test_the_model_argument_names_the_local_brain(http, ollama):
    """provider="local" call sites pass the local model name and were ignored --
    the request went to the cloud, where that name meant nothing."""
    assert query(provider="local", model="qwen2.5-coder:7b") == "from ollama"
    assert ollama.calls[0]["model"] == "qwen2.5-coder:7b"


def test_an_image_part_selects_bynaras_vision_model(http, ollama):
    """A screenshot arrives from screen_vision.py as an OpenAI `image_url` part,
    not ollama's `images` list, so it needs its own detection to reach the vision
    model rather than the text one."""
    http.response = _bynara_reply("a login screen")
    messages = [{"role": "user", "content": [
        {"type": "text", "text": "what is this?"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,QUJD"}},
    ]}]
    assert query(config=BYNARA_ON, messages=messages) == "a login screen"
    assert http.calls[0]["json"]["model"] == "ox-vision"


def test_a_text_call_selects_bynaras_text_model(http, ollama):
    http.response = _bynara_reply("hello")
    assert query(config=BYNARA_ON) == "hello"
    assert http.calls[0]["json"]["model"] == "ox-alpha-bynara"


# -- vision_enabled: no screenshot leaves the machine --------------------------
#
# The flag was honoured on the ollama.chat path and ignored here, which is the
# path screen_vision.py takes -- so the one setting that promises a screenshot
# stays local was broken for the only skill that sends one.

VISION_OFF = {"bynara": {"api_key": "bynara-key", "vision_model": "ox-vision",
                         "vision_enabled": False},
              "mistral": {"api_key": "real-key",
                          "models": {"vision": "ministral-8b-2512"}}}

SCREENSHOT = [{"role": "user", "content": [
    {"type": "text", "text": "what is on my screen?"},
    {"type": "image_url", "image_url": {"url": "data:image/png;base64,QUJD"}},
]}]


def test_vision_disabled_sends_the_screenshot_to_no_provider_at_all(http, ollama):
    """Not even the secondary: its cloud is equally off this machine."""
    http.response = _bynara_reply("should never be asked for")
    assert query(config=VISION_OFF, messages=SCREENSHOT) == "from ollama"
    assert http.calls == []
    assert ollama.calls[0]["messages"][0]["images"] == ["QUJD"]


def test_vision_disabled_still_lets_text_go_remote(http, ollama):
    """The flag is about screenshots, not about switching the provider off."""
    http.response = _bynara_reply("hello")
    assert query(config=VISION_OFF) == "hello"
    assert len(http.calls) == 1


def test_a_local_screenshot_reaches_the_local_vision_model(http, ollama):
    """The text brain cannot see an image, so naming no model must not land one
    there. screen_vision.py now names none, leaving each leg its own choice."""
    assert query(config=VISION_OFF, messages=SCREENSHOT,
                 models={"main_brain": "text-only:latest",
                         "vision": "moondream:latest"}) == "from ollama"
    assert ollama.calls[0]["model"] == "moondream:latest"


def test_mistrals_vision_model_is_used_when_bynara_declines(http, ollama):
    """Mistral names a model per role, so a screenshot reaching the secondary must
    not be addressed to its text model."""
    http.response = FakeStream(sse("a login screen"))
    config = {"bynara": {"api_key": ""},
              "mistral": {"api_key": "real-key",
                          "models": {"brain": "mistral-large-2512",
                                     "vision": "ministral-8b-2512"}}}
    assert query(config=config, messages=SCREENSHOT) == "a login screen"
    assert http.calls[0]["json"]["model"] == "ministral-8b-2512"


def test_no_deleted_provider_endpoint_survives_in_the_module():
    """groq is STT-only now and ofoxai is gone; neither may be reachable as a
    text provider from this module."""
    src = inspect.getsource(llm_client)
    assert "api.ofox.ai" not in src
    assert "api.groq.com" not in src


# -- main.py's side of the seam ------------------------------------------
#
# The call sites did not change: JARVIS.query_llm is still called the same way
# from 20-odd places. So a shim that quietly grows a branch, a `self.` lookup or
# a second statement would be invisible to every test above. main.py is parsed
# rather than imported -- it pulls in PyQt6 at module level, which this
# environment deliberately does not have.

MAIN_PY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "main.py")


def _jarvis_method(name):
    with open(MAIN_PY, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    cls = next(n for n in tree.body
               if isinstance(n, ast.ClassDef) and n.name == "JARVIS")
    return tree, next(n for n in cls.body
                      if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                      and n.name == name)


def test_main_py_imports_llm_client_at_top_level():
    tree, _ = _jarvis_method("query_llm")
    assert any(isinstance(n, ast.ImportFrom) and n.module == "jarvis.core"
               and any(a.name == "llm_client" for a in n.names)
               for n in tree.body), "expected `from jarvis.core import llm_client`"


def test_the_jarvis_method_is_only_a_delegation():
    _, fn = _jarvis_method("query_llm")
    assert len(fn.body) == 1, "the shim grew past one statement"
    stmt = fn.body[0]
    assert isinstance(stmt, ast.Return)
    call = stmt.value
    assert isinstance(call, ast.Call)
    assert isinstance(call.func, ast.Attribute) and call.func.attr == "query_llm"
    assert isinstance(call.func.value, ast.Name) and call.func.value.id == "llm_client"


def test_the_delegation_passes_its_parameters_straight_through():
    """Positionally and in order, so no argument can be quietly reordered."""
    _, fn = _jarvis_method("query_llm")
    call = fn.body[0].value
    params = [a.arg for a in fn.args.args[1:]]        # everything after self
    assert [ast.unparse(a) for a in call.args] == params
    assert params == ["messages", "system_prompt", "provider", "model"]


def test_the_delegation_injects_exactly_config_and_models():
    """The only additions, and both read from self -- if a third piece of state
    appears here, the extraction leaked coupling back into the orchestrator."""
    _, fn = _jarvis_method("query_llm")
    call = fn.body[0].value
    assert {kw.arg: ast.unparse(kw.value) for kw in call.keywords} == {
        "config": "self.config", "models": "self.models"}


def test_the_two_signatures_agree():
    """The shim's parameters must still match what the moved function accepts.
    A drift here is a TypeError at every one of the call sites."""
    _, fn = _jarvis_method("query_llm")
    moved = inspect.signature(llm_client.query_llm).parameters
    positional = [(name, p.default) for name, p in moved.items()
                  if p.kind is not p.KEYWORD_ONLY]

    assert [a.arg for a in fn.args.args[1:]] == [name for name, _ in positional]

    # Defaults line up to the tail of the parameter list on both sides.
    shim_defaults = [ast.unparse(d) for d in fn.args.defaults]
    moved_defaults = [repr(default) for _, default in positional
                      if default is not inspect.Parameter.empty]
    assert shim_defaults == moved_defaults

    kwonly = sorted(name for name, p in moved.items()
                    if p.kind is p.KEYWORD_ONLY)
    assert kwonly == ["config", "models"]
    assert fn.args.kwonlyargs == [], "the shim takes no keyword-only arguments"
