"""Tests for jarvis.core.llm_client -- the NaraRouter (bynara) redirect.

`bynara_chat_wrapper` replaces `ollama.chat` process-wide, so every LLM call in
JARVIS goes through it. That is what made re-pointing the provider a one-function
change, and it is also why a defect here is a defect in everything: the wrapper
reads `settings.yaml` on every single call and decides on its own which of three
providers answers.

The cascade under test is bynara -> mistral -> the real local ollama binding.
Three things about it are worth more than the rest, and each has its own section
below: an image in the messages routes the call to a *different model*; a
`vision_enabled: false` config keeps a screenshot on this machine without
disabling text; and every remote failure has to arrive at the local model rather
than at the user.

`requests.post` is patched in this module's namespace so no test reaches the
network, and `no_ambient_keys` clears both API keys from the environment -- the
wrapper reads them as a fallback, so a real key in the developer's shell would
otherwise silently change what these tests exercise. `_original_chat` is set
explicitly by the tests that need it; in production `patch_ollama()` sets it, and
it is None until then by design.
"""

import ast
import inspect
import json
import sys
import types

import pytest

from jarvis.core import llm_client


@pytest.fixture(autouse=True)
def no_ambient_keys(monkeypatch):
    """Both keys resolve from the environment when the config is silent, so a real
    key on the developer's machine would change these tests' meaning."""
    monkeypatch.delenv("BYNARA_API_KEY", raising=False)
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)


def _write_settings(tmp_path, monkeypatch, **sections):
    """Write config/settings.yaml where the wrapper looks for it: the cwd.

    A section passed as None is written as a bare `name:` with nothing under it --
    the shape left behind when someone comments out its contents, which YAML
    parses to None rather than to {}.
    """
    conf = tmp_path / "config"
    if not conf.exists():
        conf.mkdir()
    body = ""
    for name, values in sections.items():
        body += f"{name}:\n"
        if values is None:
            continue
        # json.dumps of a nested dict is a YAML flow mapping, so `models:` works.
        body += "".join(f"  {k}: {json.dumps(v)}\n" for k, v in values.items())
    (conf / "settings.yaml").write_text(body, encoding="utf-8")
    monkeypatch.chdir(tmp_path)


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def _ok(content):
    """A 200 in the OpenAI shape both remote providers answer in."""
    return FakeResponse(payload={
        "choices": [{"message": {"role": "assistant", "content": content}}]})


@pytest.fixture
def local_calls(monkeypatch):
    """Record calls that reach the real local Ollama binding."""
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


@pytest.fixture
def posts(monkeypatch):
    """Capture requests.post calls.

    Set `posts.response` to one response reused for every call, or
    `posts.responses` to a list consumed in order -- the list is how the
    bynara-fails-then-mistral-answers path gets driven.
    """
    calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append({"url": url, "headers": headers, "json": json,
                      "timeout": timeout})
        if fake_post.responses is not None:
            result = fake_post.responses.pop(0)
        else:
            result = fake_post.response
        if isinstance(result, Exception):
            raise result
        return result

    fake_post.response = _ok("hello")
    fake_post.responses = None
    fake_post.calls = calls
    monkeypatch.setattr(llm_client.requests, "post", fake_post)
    return fake_post


BYNARA = {"api_key": "byn-key", "base_url": "https://router.bynara.id/v1",
          "text_model": "mistral-large", "vision_model": "ce-alpha-bynara"}
MISTRAL = {"api_key": "mis-key",
           "models": {"brain": "mistral-large-2512", "vision": "ministral-8b-2512"}}
HI = [{"role": "user", "content": "hi"}]
SHOT = [{"role": "user", "content": "what is on my screen?", "images": ["QUJD"]}]


@pytest.fixture
def bynara_only(tmp_path, monkeypatch):
    """bynara configured and reachable; no secondary behind it."""
    _write_settings(tmp_path, monkeypatch, bynara=dict(BYNARA))


@pytest.fixture
def both(tmp_path, monkeypatch):
    """The full cascade: bynara primary, mistral secondary."""
    _write_settings(tmp_path, monkeypatch, bynara=dict(BYNARA), mistral=dict(MISTRAL))


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


# -- _coerce_json --------------------------------------------------------
#
# Extracted from the old Cloudflare wrapper so the JSON salvaging can be tested
# without a fake HTTP response around it. The behaviour is unchanged, including
# the two warts recorded below: callers pass format="json" and then call
# json.loads on what comes back, so this is load-bearing for the intent router.


def test_a_fenced_object_is_unwrapped():
    assert llm_client._coerce_json('```json\n{"intent": "play_music"}\n```') == \
        '{"intent": "play_music"}'


def test_prose_around_the_object_is_discarded():
    """A model narrating before its JSON is the common failure mode."""
    out = llm_client._coerce_json(
        'Sure! Here you go:\n{"intent": "play_music"}\nHope that helps.')
    assert json.loads(out) == {"intent": "play_music"}


def test_the_extraction_is_greedy_across_several_objects():
    """Pinned, not fixed. `\\{.*\\}` with DOTALL spans from the first brace to the
    last, so two objects come back as one unparseable string. Preferring the first
    would need a real scan, and a model emitting two objects for one request is
    already off-contract."""
    assert llm_client._coerce_json('{"a": 1}\nand also\n{"b": 2}') == \
        '{"a": 1}\nand also\n{"b": 2}'


def test_unsalvageable_output_is_returned_as_is():
    """No braces to find: the content passes through and the caller's json.loads
    raises. Nothing here pretends to have produced JSON."""
    assert llm_client._coerce_json("I cannot do that.") == "I cannot do that."


def test_a_structured_reply_is_serialised():
    """Defensive: an OpenAI `content` is a string, but a router that answers with
    a real object would otherwise hand a dict to callers expecting text."""
    assert llm_client._coerce_json({"intent": "play_music"}) == \
        '{"intent": "play_music"}'


# -- _section ------------------------------------------------------------


def test_a_missing_section_is_an_empty_dict():
    assert llm_client._section({}, "bynara") == {}


def test_a_commented_out_section_is_an_empty_dict_not_none():
    """The defect this helper exists for, now fixed.

    A bare `bynara:` with its keys commented out is how a person disables a YAML
    section, and it parses to None, not {}. `settings.get("bynara", {})` only
    defaults when the key is *absent*, so the section came back None and the next
    attribute access raised -- above the try/except, in a function installed as
    `ollama.chat` process-wide. One commented-out config key took down every LLM
    call in JARVIS with an AttributeError naming neither the provider nor the
    config file. `settings.get(name) or {}` is the whole fix.
    """
    assert llm_client._section({"bynara": None}, "bynara") == {}


def test_a_present_section_comes_back_whole():
    assert llm_client._section({"bynara": {"api_key": "k"}}, "bynara") == \
        {"api_key": "k"}


# -- _resolve_key --------------------------------------------------------


def test_the_config_key_wins(monkeypatch):
    monkeypatch.setenv("BYNARA_API_KEY", "from-env")
    assert llm_client._resolve_key({"api_key": "from-config"}, "BYNARA_API_KEY") == \
        "from-config"


@pytest.mark.parametrize("conf", [{}, {"api_key": ""}, {"api_key": "   "},
                                  {"api_key": None}],
                         ids=["absent", "empty", "whitespace", "null"])
def test_the_environment_fills_in_when_the_config_is_silent(monkeypatch, conf):
    """The point of the .env mechanism: a key never has to be written into
    settings.yaml, which is the file that once carried a live token into git."""
    monkeypatch.setenv("BYNARA_API_KEY", "from-env")
    assert llm_client._resolve_key(conf, "BYNARA_API_KEY") == "from-env"


def test_a_placeholder_key_is_not_a_key():
    """`YOUR_API_KEY_HERE` left in a copied config must not be sent as a Bearer
    token -- it would earn a 401 and a slow fallback instead of an instant one."""
    assert llm_client._resolve_key({"api_key": "YOUR_KEY_HERE"}, "BYNARA_API_KEY") == ""


def test_surrounding_whitespace_is_stripped(monkeypatch):
    monkeypatch.setenv("BYNARA_API_KEY", "  padded  ")
    assert llm_client._resolve_key({}, "BYNARA_API_KEY") == "padded"


def test_no_key_anywhere_is_an_empty_string():
    assert llm_client._resolve_key({}, "BYNARA_API_KEY") == ""


# -- _has_images ---------------------------------------------------------


@pytest.mark.parametrize(
    "messages,expected",
    [
        ([], False),
        ([{"role": "user", "content": "hi"}], False),
        ([{"role": "user", "content": "hi", "images": []}], False),
        ([{"role": "user", "content": "hi", "images": ["QUJD"]}], True),
        # The screenshot is rarely in the first message: a system prompt or a
        # couple of turns of history usually precede it.
        ([{"role": "system", "content": "you are"},
          {"role": "user", "content": "look", "images": ["QUJD"]}], True),
    ],
    ids=["empty", "no-key", "empty-list", "one-image", "later-message"],
)
def test_has_images(messages, expected):
    assert llm_client._has_images(messages) is expected


# -- _to_openai_messages -------------------------------------------------


def test_a_text_message_keeps_its_string_content():
    """Both dialects accept a plain string, so a text call is passed through
    unchanged rather than being wrapped in a single-part list."""
    assert llm_client._to_openai_messages(HI) == [{"role": "user", "content": "hi"}]


def test_an_image_becomes_a_data_url_part_after_the_text():
    out = llm_client._to_openai_messages(SHOT)
    assert out == [{
        "role": "user",
        "content": [
            {"type": "text", "text": "what is on my screen?"},
            {"type": "image_url",
             "image_url": {"url": "data:image/png;base64,QUJD"}},
        ],
    }]


def test_an_image_that_is_already_a_data_url_is_not_prefixed_twice():
    """A caller that built its own data URL would otherwise produce
    `data:image/png;base64,data:image/...` and a rejected request."""
    out = llm_client._to_openai_messages(
        [{"role": "user", "content": "", "images": ["data:image/jpeg;base64,QUJD"]}])
    assert out[0]["content"][0]["image_url"]["url"] == "data:image/jpeg;base64,QUJD"


def test_several_images_become_several_parts():
    out = llm_client._to_openai_messages(
        [{"role": "user", "content": "compare", "images": ["QQ", "Qg"]}])
    assert [p["type"] for p in out[0]["content"]] == \
        ["text", "image_url", "image_url"]


def test_an_image_with_no_prompt_yields_only_the_image_part():
    """An empty text part is not sent: some endpoints reject a blank one."""
    out = llm_client._to_openai_messages(
        [{"role": "user", "content": "", "images": ["QUJD"]}])
    assert [p["type"] for p in out[0]["content"]] == ["image_url"]


def test_a_message_without_a_role_is_treated_as_the_user():
    assert llm_client._to_openai_messages([{"content": "hi"}])[0]["role"] == "user"


def test_history_survives_alongside_a_screenshot():
    """The order and roles of the other messages must be untouched -- the vision
    call sites send a system prompt and prior turns with the image."""
    out = llm_client._to_openai_messages(
        [{"role": "system", "content": "you are"},
         {"role": "assistant", "content": "ok"},
         {"role": "user", "content": "look", "images": ["QUJD"]}])
    assert [m["role"] for m in out] == ["system", "assistant", "user"]
    assert out[0]["content"] == "you are"
    assert isinstance(out[2]["content"], list)


# -- the wrapper: reaching the local model -------------------------------
#
# Every test here asserts `no_network` as well, because "fell back to local" and
# "tried the network first and then fell back" are different behaviours and only
# one of them is correct when nothing is configured.


def test_a_missing_settings_file_goes_straight_to_local(
        tmp_path, monkeypatch, local_calls, no_network):
    """No config/settings.yaml at all -- the common case on a fresh checkout."""
    monkeypatch.chdir(tmp_path)
    out = llm_client.bynara_chat_wrapper("llama3", HI)
    assert out["message"]["content"] == "from local"
    assert local_calls[0]["model"] == "llama3"


def test_unreadable_settings_are_a_warning_not_a_crash(
        tmp_path, monkeypatch, local_calls, no_network):
    """`settings` stays {} on a YAML error, so the call still gets answered. This
    is the branch that keeps a broken config from taking JARVIS down."""
    conf = tmp_path / "config"
    conf.mkdir()
    (conf / "settings.yaml").write_text("bynara: [unclosed\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    out = llm_client.bynara_chat_wrapper("llama3", HI)
    assert out["message"]["content"] == "from local"


@pytest.mark.parametrize(
    "sections",
    [
        {},
        {"bynara": None},
        {"bynara": {}},
        {"bynara": {"base_url": "https://router.bynara.id/v1"}},
        {"bynara": {"api_key": "YOUR_KEY_HERE"}},
        {"bynara": {"api_key": "byn-key", "enabled": False}},
        {"bynara": {"api_key": "byn-key", "enabled": False},
         "mistral": {"api_key": "YOUR_KEY_HERE"}},
    ],
    ids=["no-sections", "commented-out", "empty-section", "no-key", "placeholder-key",
         "disabled", "disabled-and-no-secondary"],
)
def test_an_unusable_config_reaches_local_without_a_request(
        tmp_path, monkeypatch, local_calls, no_network, sections):
    """`commented-out` is the case that used to raise AttributeError from inside
    every LLM call in the process; the rest are ordinary unconfigured shapes."""
    _write_settings(tmp_path, monkeypatch, **sections)
    out = llm_client.bynara_chat_wrapper("llama3", HI)
    assert out["message"]["content"] == "from local"
    assert len(local_calls) == 1


def test_the_fallback_passes_every_argument_through(bynara_only, posts, local_calls):
    """Including **kwargs -- the wrapper stands in for ollama.chat, whose callers
    pass things this module has never heard of."""
    posts.response = FakeResponse(status_code=500)
    messages = [{"role": "user", "content": "hi"}]
    llm_client.bynara_chat_wrapper("llama3", messages, format="json",
                                   options={"temperature": 0.7}, keep_alive="5m")
    assert local_calls[0] == {"model": "llama3", "messages": messages,
                              "format": "json", "options": {"temperature": 0.7},
                              "keep_alive": "5m"}


def test_the_local_binding_gets_the_ollama_shaped_messages(bynara_only, posts,
                                                           local_calls):
    """The converted OpenAI-shaped messages must not leak into the fallback: the
    real binding wants `images` beside `content`, not an image_url part."""
    posts.response = FakeResponse(status_code=500)
    llm_client.bynara_chat_wrapper("moondream", SHOT)
    assert local_calls[0]["messages"] == SHOT
    assert local_calls[0]["messages"][0]["images"] == ["QUJD"]


# -- the wrapper: the primary provider -----------------------------------


def test_a_configured_wrapper_returns_the_remote_answer(bynara_only, posts,
                                                        local_calls):
    out = llm_client.bynara_chat_wrapper("llama3", HI)
    assert out == {"message": {"role": "assistant", "content": "hello"}}
    assert local_calls == [], "the local model should not have been consulted"


def test_the_request_is_addressed_and_authorised_from_the_config(bynara_only, posts):
    llm_client.bynara_chat_wrapper("llama3", HI)
    call = posts.calls[0]
    assert call["url"] == "https://router.bynara.id/v1/chat/completions"
    assert call["headers"]["Authorization"] == "Bearer byn-key"
    assert call["json"]["messages"] == [{"role": "user", "content": "hi"}]
    assert call["timeout"] == llm_client._TEXT_TIMEOUT


def test_the_local_model_name_is_replaced_by_the_configured_one(bynara_only, posts):
    """`model` is JARVIS's *local* name for a model that is not being used here.

    Worth pinning because the parameter is named `model` and is ignored on this
    path -- reading the signature suggests the caller chooses the remote model,
    and it does not.
    """
    llm_client.bynara_chat_wrapper("qwen2.5-coder:7b", HI)
    assert posts.calls[0]["json"]["model"] == "mistral-large"


def test_a_configured_text_model_overrides_the_default(tmp_path, monkeypatch, posts):
    _write_settings(tmp_path, monkeypatch,
                    bynara={"api_key": "k", "text_model": "glm-4.7"})
    llm_client.bynara_chat_wrapper("llama3", HI)
    assert posts.calls[0]["json"]["model"] == "glm-4.7"


def test_the_defaults_apply_when_the_config_names_only_a_key(tmp_path, monkeypatch,
                                                             posts):
    """A config with nothing but a key still has to reach a real model, because
    `.env`-only setup is the documented happy path."""
    _write_settings(tmp_path, monkeypatch, bynara={"api_key": "k"})
    llm_client.bynara_chat_wrapper("llama3", HI)
    assert posts.calls[0]["url"] == llm_client._BYNARA_BASE_URL + "/chat/completions"
    assert posts.calls[0]["json"]["model"] == llm_client._BYNARA_TEXT_MODEL


def test_a_configured_base_url_is_honoured(tmp_path, monkeypatch, posts):
    """Any OpenAI-compatible host can stand in, which is also how this gets
    pointed at a local proxy for debugging."""
    _write_settings(tmp_path, monkeypatch,
                    bynara={"api_key": "k", "base_url": "http://127.0.0.1:8080/v1/"})
    llm_client.bynara_chat_wrapper("llama3", HI)
    assert posts.calls[0]["url"] == "http://127.0.0.1:8080/v1/chat/completions"


def test_the_key_can_come_from_the_environment_alone(tmp_path, monkeypatch, posts):
    """The whole point of commit 1's .env loader: settings.yaml need not hold it."""
    monkeypatch.setenv("BYNARA_API_KEY", "env-key")
    _write_settings(tmp_path, monkeypatch, bynara={"enabled": True})
    llm_client.bynara_chat_wrapper("llama3", HI)
    assert posts.calls[0]["headers"]["Authorization"] == "Bearer env-key"


def test_temperature_is_forwarded_but_only_from_options(bynara_only, posts):
    llm_client.bynara_chat_wrapper("llama3", HI, options={"temperature": 0.2})
    assert posts.calls[0]["json"]["temperature"] == 0.2


@pytest.mark.parametrize("options", [None, {}, {"num_predict": 128}],
                         ids=["none", "empty", "other-key"])
def test_no_temperature_means_no_temperature_key(bynara_only, posts, options):
    """The provider applies its own default; sending null would override it."""
    llm_client.bynara_chat_wrapper("llama3", HI, options=options)
    assert "temperature" not in posts.calls[0]["json"]


def test_other_ollama_options_are_dropped_silently(bynara_only, posts):
    """Pinned, not fixed, and carried over from the Cloudflare wrapper. Only
    `temperature` crosses over, so `num_predict`, `top_p`, `stop` and the rest are
    lost on the remote path -- the same call gives differently-shaped output
    depending on config the caller cannot see. Recorded because the loss is
    silent, not because the mapping is obviously wrong: the two APIs do not take
    the same option names."""
    llm_client.bynara_chat_wrapper(
        "llama3", HI, options={"num_predict": 64, "top_p": 0.1, "temperature": 0.5})
    assert set(posts.calls[0]["json"]) == {"model", "messages", "temperature"}


# -- the wrapper: vision -------------------------------------------------


def test_a_screenshot_routes_to_the_vision_model(bynara_only, posts):
    """The heart of the vision migration. No call site asked for a vision model;
    the wrapper infers it from the presence of `images`, which is why seven call
    sites needed no change."""
    llm_client.bynara_chat_wrapper("moondream:latest", SHOT)
    assert posts.calls[0]["json"]["model"] == "ce-alpha-bynara"


def test_a_text_call_routes_to_the_text_model(bynara_only, posts):
    llm_client.bynara_chat_wrapper("moondream:latest", HI)
    assert posts.calls[0]["json"]["model"] == "mistral-large"


def test_the_screenshot_is_sent_as_a_data_url(bynara_only, posts):
    llm_client.bynara_chat_wrapper("moondream:latest", SHOT)
    parts = posts.calls[0]["json"]["messages"][0]["content"]
    assert parts[0] == {"type": "text", "text": "what is on my screen?"}
    assert parts[1]["image_url"]["url"] == "data:image/png;base64,QUJD"


def test_a_vision_call_gets_the_longer_timeout(bynara_only, posts):
    """A screenshot takes longer to ship and longer to reason over; sharing the
    text budget would demote every vision call to the local model."""
    llm_client.bynara_chat_wrapper("moondream:latest", SHOT)
    assert posts.calls[0]["timeout"] == llm_client._VISION_TIMEOUT
    assert llm_client._VISION_TIMEOUT > llm_client._TEXT_TIMEOUT


def test_disabling_vision_keeps_the_screenshot_on_this_machine(
        tmp_path, monkeypatch, local_calls, no_network):
    """The privacy switch, and the reason it is checked before the key is: with
    `vision_enabled: false` a call carrying an image must not reach *any* remote
    provider, so there is nothing to authorise. `no_network` is the assertion
    that matters here -- it fails if a screenshot is posted anywhere."""
    _write_settings(tmp_path, monkeypatch,
                    bynara=dict(BYNARA, vision_enabled=False), mistral=dict(MISTRAL))
    out = llm_client.bynara_chat_wrapper("moondream:latest", SHOT)
    assert out["message"]["content"] == "from local"
    assert local_calls[0]["messages"] == SHOT


def test_disabling_vision_leaves_text_remote(tmp_path, monkeypatch, posts,
                                             local_calls):
    """Keeping text remote while never sending a screenshot is one flag, so the
    text path has to be unaffected by it."""
    _write_settings(tmp_path, monkeypatch, bynara=dict(BYNARA, vision_enabled=False))
    out = llm_client.bynara_chat_wrapper("llama3", HI)
    assert out["message"]["content"] == "hello"
    assert local_calls == []


# -- the wrapper: the secondary provider ---------------------------------


def test_a_failed_primary_falls_through_to_mistral(both, posts, local_calls):
    posts.responses = [FakeResponse(status_code=500, text="boom"), _ok("from mistral")]
    out = llm_client.bynara_chat_wrapper("llama3", HI)
    assert out["message"]["content"] == "from mistral"
    assert local_calls == [], "the secondary answered, so local is not consulted"


def test_the_secondary_is_addressed_and_authorised_separately(both, posts):
    posts.responses = [FakeResponse(status_code=500), _ok("from mistral")]
    llm_client.bynara_chat_wrapper("llama3", HI)
    first, second = posts.calls
    assert first["url"].startswith("https://router.bynara.id")
    assert second["url"] == "https://api.mistral.ai/v1/chat/completions"
    assert second["headers"]["Authorization"] == "Bearer mis-key"
    assert second["json"]["model"] == "mistral-large-2512"


def test_an_unconfigured_primary_reaches_the_secondary_directly(
        tmp_path, monkeypatch, posts):
    """No key for bynara is not a reason to skip the secondary and go local."""
    _write_settings(tmp_path, monkeypatch, mistral=dict(MISTRAL))
    out = llm_client.bynara_chat_wrapper("llama3", HI)
    assert out["message"]["content"] == "hello"
    assert len(posts.calls) == 1
    assert posts.calls[0]["url"].startswith("https://api.mistral.ai")


def test_a_disabled_primary_reaches_the_secondary(tmp_path, monkeypatch, posts):
    _write_settings(tmp_path, monkeypatch, bynara=dict(BYNARA, enabled=False),
                    mistral=dict(MISTRAL))
    llm_client.bynara_chat_wrapper("llama3", HI)
    assert posts.calls[0]["url"].startswith("https://api.mistral.ai")


def test_the_secondary_uses_its_own_vision_model_for_a_screenshot(both, posts):
    """Mistral names models per role rather than offering one id, so the vision
    role has to be picked the same way the text role is -- otherwise a screenshot
    would be sent to a text-only model."""
    posts.responses = [FakeResponse(status_code=500), _ok("seen")]
    llm_client.bynara_chat_wrapper("moondream:latest", SHOT)
    assert posts.calls[1]["json"]["model"] == "ministral-8b-2512"


def test_a_successful_primary_never_calls_the_secondary(both, posts):
    llm_client.bynara_chat_wrapper("llama3", HI)
    assert len(posts.calls) == 1


def test_both_providers_failing_reaches_the_local_model(both, posts, local_calls):
    posts.responses = [FakeResponse(status_code=500), FakeResponse(status_code=503)]
    out = llm_client.bynara_chat_wrapper("llama3", HI)
    assert out["message"]["content"] == "from local"
    assert len(posts.calls) == 2


# -- the wrapper: what counts as a failure -------------------------------


@pytest.mark.parametrize(
    "response",
    [
        FakeResponse(status_code=500, text="internal error"),
        FakeResponse(status_code=401, text="bad token"),
        FakeResponse(status_code=429, text="rate limited"),
        FakeResponse(payload=None),
        FakeResponse(payload={}),
        FakeResponse(payload={"choices": []}),
        FakeResponse(payload={"choices": [{"message": {}}]}),
        FakeResponse(payload={"choices": [{"message": {"content": None}}]}),
        FakeResponse(payload={"choices": [{"message": {"content": ""}}]}),
        FakeResponse(payload={"choices": [{"message": {"content": "   \n "}}]}),
        FakeResponse(payload={"error": {"message": "no such model"}}),
    ],
    ids=["http-500", "http-401", "http-429", "bad-body", "empty-body", "no-choices",
         "no-content-key", "null-content", "empty-content", "whitespace-content",
         "error-body"],
)
def test_every_unusable_reply_falls_back(bynara_only, posts, local_calls, response):
    """An empty or whitespace-only reply is a 200 that leaves the user in silence,
    so it is treated as a non-answer like any other -- the local model can do
    better than nothing."""
    posts.response = response
    out = llm_client.bynara_chat_wrapper("llama3", HI)
    assert out["message"]["content"] == "from local"
    assert len(local_calls) == 1


@pytest.mark.parametrize("error", [
    "Timeout", "ConnectionError", "RequestException"])
def test_a_transport_error_falls_back(bynara_only, posts, local_calls, error):
    posts.response = getattr(llm_client.requests.exceptions, error)("nope")
    out = llm_client.bynara_chat_wrapper("llama3", HI)
    assert out["message"]["content"] == "from local"


# -- the wrapper: JSON handling on the remote path -----------------------


def test_json_was_asked_for_so_the_reply_is_salvaged(bynara_only, posts):
    posts.response = _ok('```json\n{"intent": "play_music"}\n```')
    out = llm_client.bynara_chat_wrapper("llama3", HI, format="json")
    assert out["message"]["content"] == '{"intent": "play_music"}'


def test_without_format_json_a_fence_is_left_alone(bynara_only, posts):
    """Plain chat replies may legitimately contain code fences."""
    posts.response = _ok('```python\nprint("hi")\n```')
    out = llm_client.bynara_chat_wrapper("llama3", HI)
    assert out["message"]["content"] == '```python\nprint("hi")\n```'


def test_the_secondary_reply_is_salvaged_too(both, posts):
    """The JSON contract is the caller's, not the provider's, so it cannot depend
    on which leg of the cascade answered."""
    posts.responses = [FakeResponse(status_code=500),
                       _ok('Here:\n{"intent": "stop"}')]
    out = llm_client.bynara_chat_wrapper("llama3", HI, format="json")
    assert json.loads(out["message"]["content"]) == {"intent": "stop"}


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
    assert fake_ollama.chat is llm_client.bynara_chat_wrapper
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
    assert fake_ollama.chat(model="llama3", messages=[])["message"]["content"] == \
        "real ollama"


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


def test_no_cloudflare_url_survives_in_this_module():
    """The provider is gone, not disabled. A leftover endpoint would be a second
    place for a call to escape to, reachable from a stale config section."""
    source = inspect.getsource(llm_client)
    assert "api.cloudflare.com" not in source

