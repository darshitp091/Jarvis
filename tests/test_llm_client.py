"""Tests for jarvis.core.llm_client -- the Cloudflare Workers AI redirect.

This module could not be tested at all until now. It imported `ollama` at module
level to capture `ollama.chat`, and the environment CI runs deliberately does not
install ollama, so importing it raised ModuleNotFoundError before any test could
run. The capture moved into `patch_ollama()`, where the only other line needing
ollama already was.

What that was hiding: `cloudflare_chat_wrapper` replaces `ollama.chat` process-
wide, so every LLM call in JARVIS goes through it. It reads `settings.yaml` on
every single call, and it decides on its own when to fall back to the local
model. None of those branches had ever been exercised.

`requests.post` is patched in this module's namespace so no test reaches the
network. `_original_chat` is set explicitly by the tests that need it -- in
production `patch_ollama()` sets it, and it is None until then by design.
"""

import ast
import inspect
import json
import sys
import types

import pytest

from jarvis.core import llm_client

# -- _is_json ------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ('{"a": 1}', True),
        ("[1, 2, 3]", True),
        # json.loads accepts bare scalars, so these are JSON too.
        ("42", True),
        ('"hello"', True),
        ("{not json}", False),
        ("", False),
        ("```json\n{}\n```", False),
    ],
)
def test_is_json(text, expected):
    assert llm_client._is_json(text) is expected


# -- _clean_json_response ------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ('```json\n{"a": 1}\n```', '{"a": 1}'),
        ('```\n{"a": 1}\n```', '{"a": 1}'),
        ('```JSON\n{"a": 1}\n```', '{"a": 1}'),
        # No fence: returned stripped and otherwise untouched.
        ('  {"a": 1}  ', '{"a": 1}'),
        ("", ""),
    ],
)
def test_clean_json_response(text, expected):
    assert llm_client._clean_json_response(text) == expected


def test_an_unterminated_fence_loses_its_opening_marker_anyway():
    """The closing regex is anchored to a newline at end-of-string, so a fence the
    model never closed has nothing to strip -- but the opening marker is removed
    regardless. Here that lands on valid JSON, so the asymmetry is harmless; it is
    recorded because it is the shape a truncated response arrives in."""
    assert llm_client._clean_json_response('```json\n{"a": 1}') == '{"a": 1}'


# -- cloudflare_chat_wrapper: configuration gating -----------------------


def _settings(tmp_path, monkeypatch, cloudflare):
    """Write config/settings.yaml where the wrapper looks for it: the cwd."""
    conf = tmp_path / "config"
    conf.mkdir()
    body = "" if cloudflare is None else "cloudflare:\n" + "".join(
        "  %s: %s\n" % (k, json.dumps(v)) for k, v in cloudflare.items())
    (conf / "settings.yaml").write_text(body, encoding="utf-8")
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def local_calls(monkeypatch):
    """Record calls that reach the local Ollama fallback instead of Cloudflare."""
    seen = []

    def fake_original(**kwargs):
        seen.append(kwargs)
        return {"message": {"role": "assistant", "content": "from local"}}

    monkeypatch.setattr(llm_client, "_original_chat", fake_original)
    return seen


@pytest.fixture
def no_network(monkeypatch):
    """Any HTTP request is a test failure unless a test opts into one."""
    def explode(*a, **k):
        raise AssertionError("the wrapper reached the network")

    monkeypatch.setattr(llm_client.requests, "post", explode)


@pytest.mark.parametrize(
    "cloudflare",
    [
        None,
        {"account_id": "acct"},                              # token missing
        {"api_token": "tok"},                                # account missing
        {"account_id": "acct", "api_token": "tok", "enabled": False},
    ],
    ids=["no-section", "no-token", "no-account", "disabled"],
)
def test_incomplete_cloudflare_config_goes_straight_to_local(
        tmp_path, monkeypatch, local_calls, no_network, cloudflare):
    _settings(tmp_path, monkeypatch, cloudflare)
    out = llm_client.cloudflare_chat_wrapper("llama3", [{"role": "user", "content": "hi"}])
    assert out["message"]["content"] == "from local"
    assert len(local_calls) == 1
    assert local_calls[0]["model"] == "llama3"


def test_an_empty_cloudflare_section_crashes_every_llm_call(
        tmp_path, monkeypatch, local_calls, no_network):
    """Pinned, not fixed -- and the worst of the defects found so far.

    A bare `cloudflare:` with its keys commented out is how a person disables a
    YAML section, and it parses to None, not {}. `settings.get("cloudflare", {})`
    only defaults when the key is *absent*, so cf_conf is None and the next line
    raises. That line sits above the try/except, so there is no fallback: this
    wrapper is installed as `ollama.chat` process-wide, so one commented-out
    config key takes down every LLM call in JARVIS with an AttributeError that
    names neither Cloudflare nor the config file.

    The fix is `settings.get("cloudflare") or {}`. It is held back because this
    commit's claim is that llm_client became importable and testable without its
    behaviour moving; the fix lands next with this test flipped.
    """
    conf = tmp_path / "config"
    conf.mkdir()
    (conf / "settings.yaml").write_text("cloudflare:\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(AttributeError):
        llm_client.cloudflare_chat_wrapper("llama3", [])
    assert local_calls == [], "it never reaches the fallback"


def test_a_missing_settings_file_goes_to_local(tmp_path, monkeypatch,
                                               local_calls, no_network):
    """No config/settings.yaml at all -- the common case on a fresh checkout."""
    monkeypatch.chdir(tmp_path)
    out = llm_client.cloudflare_chat_wrapper("llama3", [])
    assert out["message"]["content"] == "from local"


def test_unreadable_settings_are_a_warning_not_a_crash(tmp_path, monkeypatch,
                                                       local_calls, no_network):
    """`settings` stays {} on a YAML error, so the call still gets answered.

    This is the branch that keeps a broken config from taking JARVIS down.
    """
    conf = tmp_path / "config"
    conf.mkdir()
    (conf / "settings.yaml").write_text("cloudflare: [unclosed\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    out = llm_client.cloudflare_chat_wrapper("llama3", [])
    assert out["message"]["content"] == "from local"


# -- cloudflare_chat_wrapper: the remote path ----------------------------


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


@pytest.fixture
def enabled(tmp_path, monkeypatch):
    """A complete, enabled Cloudflare config in a temporary cwd."""
    _settings(tmp_path, monkeypatch,
              {"account_id": "acct123", "api_token": "tok456"})


@pytest.fixture
def posts(monkeypatch):
    """Capture requests.post calls; each test sets `posts.response`."""
    calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append({"url": url, "headers": headers, "json": json,
                      "timeout": timeout})
        result = fake_post.response
        if isinstance(result, Exception):
            raise result
        return result

    fake_post.response = FakeResponse(payload={"success": True,
                                               "result": {"response": "hello"}})
    fake_post.calls = calls
    monkeypatch.setattr(llm_client.requests, "post", fake_post)
    return fake_post


def _ok(content):
    return FakeResponse(payload={"success": True, "result": {"response": content}})


def test_a_configured_wrapper_returns_the_remote_answer(enabled, posts, local_calls):
    out = llm_client.cloudflare_chat_wrapper("llama3", [{"role": "user", "content": "hi"}])
    assert out == {"message": {"role": "assistant", "content": "hello"}}
    assert local_calls == [], "the local model should not have been consulted"


def test_the_request_is_addressed_and_authorised_from_the_config(enabled, posts):
    llm_client.cloudflare_chat_wrapper("llama3", [{"role": "user", "content": "hi"}])
    call = posts.calls[0]
    assert call["url"] == ("https://api.cloudflare.com/client/v4/accounts/acct123"
                           "/ai/run/@cf/meta/llama-3.1-8b-instruct")
    assert call["headers"]["Authorization"] == "Bearer tok456"
    assert call["json"] == {"messages": [{"role": "user", "content": "hi"}]}
    # 12s: the fallback to a local model is the point, so the remote call is
    # not allowed to hang the assistant.
    assert call["timeout"] == 12


def test_the_ollama_model_name_is_not_sent_to_cloudflare(enabled, posts):
    """`model` is JARVIS's local name; the remote one comes from the config.

    Worth pinning because the parameter is named `model` and is silently
    ignored on this path -- reading the signature suggests otherwise.
    """
    llm_client.cloudflare_chat_wrapper("qwen2.5:7b", [])
    assert "qwen2.5" not in posts.calls[0]["url"]
    assert "model" not in posts.calls[0]["json"]


def test_a_configured_model_overrides_the_default(tmp_path, monkeypatch, posts):
    _settings(tmp_path, monkeypatch, {"account_id": "a", "api_token": "t",
                                      "model": "@cf/mistral/mistral-7b-instruct-v0.1"})
    llm_client.cloudflare_chat_wrapper("llama3", [])
    assert posts.calls[0]["url"].endswith("/@cf/mistral/mistral-7b-instruct-v0.1")


def test_temperature_is_forwarded_but_only_from_options(enabled, posts):
    llm_client.cloudflare_chat_wrapper("llama3", [], options={"temperature": 0.2})
    assert posts.calls[0]["json"]["temperature"] == 0.2


@pytest.mark.parametrize("options", [None, {}, {"num_predict": 128}],
                         ids=["none", "empty", "other-key"])
def test_no_temperature_means_no_temperature_key(enabled, posts, options):
    """Cloudflare applies its own default; sending null would override it."""
    llm_client.cloudflare_chat_wrapper("llama3", [], options=options)
    assert "temperature" not in posts.calls[0]["json"]


def test_other_ollama_options_are_dropped_silently(enabled, posts):
    """Pinned, not fixed. Only `temperature` crosses over, so `num_predict`,
    `top_p`, `stop` and the rest are lost on the Cloudflare path -- the same
    call gives differently-shaped output depending on config the caller cannot
    see. Recorded because the loss is silent, not because the mapping is
    obviously wrong: the two APIs do not take the same option names."""
    llm_client.cloudflare_chat_wrapper(
        "llama3", [], options={"num_predict": 64, "top_p": 0.1, "temperature": 0.5})
    assert set(posts.calls[0]["json"]) == {"messages", "temperature"}


# -- cloudflare_chat_wrapper: JSON handling ------------------------------


def test_a_fenced_json_response_is_unwrapped_when_json_was_asked_for(enabled, posts):
    posts.response = _ok('```json\n{"intent": "play_music"}\n```')
    out = llm_client.cloudflare_chat_wrapper("llama3", [], format="json")
    assert out["message"]["content"] == '{"intent": "play_music"}'


def test_prose_around_the_object_is_discarded(enabled, posts):
    """The model narrating before its JSON is the common failure, and the
    intent router downstream calls json.loads on this content."""
    posts.response = _ok('Sure! Here you go:\n{"intent": "play_music"}\nHope that helps.')
    out = llm_client.cloudflare_chat_wrapper("llama3", [], format="json")
    assert json.loads(out["message"]["content"]) == {"intent": "play_music"}


def test_the_extraction_is_greedy_across_several_objects(enabled, posts):
    """Pinned, not fixed. `\\{.*\\}` with DOTALL spans from the first brace to
    the last, so two objects come back as one unparseable string. Preferring the
    first would need a real scan, and a model emitting two objects for one
    request is already off-contract."""
    posts.response = _ok('{"a": 1}\nand also\n{"b": 2}')
    out = llm_client.cloudflare_chat_wrapper("llama3", [], format="json")
    assert out["message"]["content"] == '{"a": 1}\nand also\n{"b": 2}'


def test_unsalvageable_output_is_returned_as_is(enabled, posts):
    """No braces to find: the content passes through and the caller's
    json.loads raises. Nothing here pretends to have produced JSON."""
    posts.response = _ok("I cannot do that.")
    out = llm_client.cloudflare_chat_wrapper("llama3", [], format="json")
    assert out["message"]["content"] == "I cannot do that."


def test_without_format_json_a_fence_is_left_alone(enabled, posts):
    """Plain chat replies may legitimately contain code fences."""
    posts.response = _ok('```python\nprint("hi")\n```')
    out = llm_client.cloudflare_chat_wrapper("llama3", [])
    assert out["message"]["content"] == '```python\nprint("hi")\n```'


def test_a_structured_result_is_serialised_before_being_returned(enabled, posts):
    """Cloudflare can answer with a real object rather than a string; callers
    expect content to be text."""
    posts.response = _ok({"intent": "play_music"})
    out = llm_client.cloudflare_chat_wrapper("llama3", [], format="json")
    assert out["message"]["content"] == '{"intent": "play_music"}'


# -- cloudflare_chat_wrapper: every remote failure falls back -------------


@pytest.mark.parametrize(
    "response",
    [
        FakeResponse(status_code=500, text="internal error"),
        FakeResponse(status_code=401, text="bad token"),
        FakeResponse(status_code=429, text="rate limited"),
        FakeResponse(payload={"success": False, "errors": [{"code": 7000}]}),
        FakeResponse(payload={"success": True, "result": {}}),      # no "response"
        FakeResponse(payload={"success": True}),                    # no "result"
        FakeResponse(payload=None),                                 # unparseable body
    ],
    ids=["http-500", "http-401", "http-429", "success-false", "no-response-key",
         "no-result-key", "bad-body"],
)
def test_a_failed_remote_call_falls_back_to_the_local_model(
        enabled, posts, local_calls, response):
    posts.response = response
    out = llm_client.cloudflare_chat_wrapper("llama3", [{"role": "user", "content": "hi"}])
    assert out["message"]["content"] == "from local"
    assert len(local_calls) == 1


def test_a_network_error_falls_back_to_the_local_model(enabled, posts, local_calls):
    posts.response = llm_client.requests.exceptions.Timeout("timed out")
    out = llm_client.cloudflare_chat_wrapper("llama3", [])
    assert out["message"]["content"] == "from local"


def test_the_fallback_passes_every_argument_through(enabled, posts, local_calls):
    """Including **kwargs -- the wrapper stands in for ollama.chat, whose
    callers pass things this module has never heard of."""
    posts.response = FakeResponse(status_code=500)
    messages = [{"role": "user", "content": "hi"}]
    llm_client.cloudflare_chat_wrapper("llama3", messages, format="json",
                                       options={"temperature": 0.7}, keep_alive="5m")
    assert local_calls[0] == {"model": "llama3", "messages": messages,
                              "format": "json", "options": {"temperature": 0.7},
                              "keep_alive": "5m"}


# -- patch_ollama --------------------------------------------------------


@pytest.fixture
def fake_ollama(monkeypatch):
    """Install a stand-in `ollama` module and restore `_original_chat` after.

    patch_ollama() mutates module state in both this module and ollama's, so
    without the restore the first test to run would decide what the rest see.
    """
    module = types.ModuleType("ollama")
    module.chat = lambda **kwargs: {"message": {"content": "real ollama"}}
    monkeypatch.setitem(sys.modules, "ollama", module)
    monkeypatch.setattr(llm_client, "_original_chat", None)
    return module


def test_patch_ollama_installs_the_wrapper_and_keeps_the_original(fake_ollama):
    real = fake_ollama.chat
    llm_client.patch_ollama()
    assert fake_ollama.chat is llm_client.cloudflare_chat_wrapper
    assert llm_client._original_chat is real


def test_patching_twice_does_not_make_the_wrapper_its_own_fallback(
        fake_ollama, tmp_path, monkeypatch):
    """The regression the idempotency guard exists for.

    Capture used to happen at import time, so calling patch_ollama() twice was
    harmless. Now that it happens inside the function, a second call without the
    guard would store the wrapper as `_original_chat` -- and the next fallback
    would call the wrapper, which would fall back to itself, forever. This test
    fails with a RecursionError if the guard goes away.
    """
    real = fake_ollama.chat
    llm_client.patch_ollama()
    llm_client.patch_ollama()
    assert llm_client._original_chat is real

    monkeypatch.chdir(tmp_path)   # no config -> straight to the fallback
    assert fake_ollama.chat(model="llama3", messages=[])["message"]["content"] == "real ollama"


def test_nothing_at_module_level_imports_ollama():
    """The guard on the change that made this file testable at all.

    Asserted against the source rather than by importing, because in an
    environment that has ollama installed an import-based test passes either way
    -- it would prove nothing exactly where it matters. The AST catches both
    `import ollama` and `from ollama import chat`; a function-local import (which
    is where the two lines that need it live) is out of scope by construction,
    since only module-level statements are walked.
    """
    tree = ast.parse(inspect.getsource(llm_client))
    offenders = [
        ast.dump(node) for node in tree.body
        if (isinstance(node, ast.Import)
            and any(a.name.split(".")[0] == "ollama" for a in node.names))
        or (isinstance(node, ast.ImportFrom)
            and (node.module or "").split(".")[0] == "ollama")
    ]
    assert offenders == []
