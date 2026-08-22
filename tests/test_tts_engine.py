"""Headless tests for the TTS backend selection and audio decoding.

No network, no audio device, no API key required. The Fish Audio path is
exercised against a fake ``requests.post`` that mimics the real OpenRouter
response, including its raw-PCM content type.
"""

import sys
import types
import numpy as np
import pytest

sys.path.insert(0, ".")

from jarvis.core.tts_engine import TTSEngine, OPENROUTER_SPEECH_URL


class FakeResponse:
    def __init__(self, status_code=200, content=b"", headers=None, text=""):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}
        self.text = text


@pytest.fixture
def engine(monkeypatch):
    """A TTSEngine with config loading stubbed out to a known state."""
    monkeypatch.setattr(TTSEngine, "__init__", lambda self, **kw: None)
    e = TTSEngine()
    e.interrupted = False
    e.is_speaking = False
    e.speak_start_time = 0.0
    e.on_speak_start = None
    e.on_speak_end = None
    e.settings = {}
    e.voices_config = {"hinglish": {"ref_speaker": "hi-IN-SwaraNeural"}}
    e.default_voice = "hinglish"
    e.default_speed = 1.3
    e.default_pitch = -12
    e.engine = "fish"
    e.fish_conf = {"model": "fish-audio/s2.1-pro-free:free", "api_key": "test-key"}
    e._fish_key_warned = False
    return e


def _pcm_bytes(n=1000, rate=44100):
    """Deterministic int16 PCM payload."""
    t = np.linspace(0, 1, n, endpoint=False)
    return (np.sin(2 * np.pi * 3 * t) * 10000).astype("<i2").tobytes()


# --------------------------------------------------------------- content type

@pytest.mark.parametrize(
    "ctype,expected",
    [
        ("audio/pcm;rate=44100;channels=1", (44100, 1)),
        ("audio/pcm;rate=24000;channels=2", (24000, 2)),
        ("audio/pcm", (44100, 1)),
        ("audio/pcm;rate=bogus;channels=1", (44100, 1)),
    ],
)
def test_parse_pcm_params(ctype, expected):
    assert TTSEngine._parse_pcm_params(ctype) == expected


def test_decode_pcm_is_normalised_float32(engine):
    audio, rate = engine._decode_audio_response(_pcm_bytes(), "audio/pcm;rate=44100;channels=1")
    assert rate == 44100
    assert audio.dtype == np.float32
    assert audio.size == 1000
    assert np.abs(audio).max() <= 1.0


def test_decode_pcm_downmixes_stereo(engine):
    stereo = np.repeat(np.array([1000, 2000], dtype="<i2"), 2).tobytes()
    audio, rate = engine._decode_audio_response(stereo, "audio/pcm;rate=24000;channels=2")
    assert rate == 24000
    assert audio.size == 2


def test_decode_empty_pcm_raises(engine):
    with pytest.raises(RuntimeError, match="no samples"):
        engine._decode_audio_response(b"", "audio/pcm;rate=44100;channels=1")


# ------------------------------------------------------------------ fish path

def test_synthesize_fish_sends_expected_request(engine, monkeypatch):
    seen = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        seen.update(url=url, headers=headers, json=json, timeout=timeout)
        return FakeResponse(
            content=_pcm_bytes(),
            headers={"Content-Type": "audio/pcm;rate=44100;channels=1",
                     "X-Generation-Id": "gen-test"},
        )

    monkeypatch.setattr("requests.post", fake_post)
    audio, rate = engine._synthesize_fish("hello sir")

    assert seen["url"] == OPENROUTER_SPEECH_URL
    assert seen["json"] == {"model": "fish-audio/s2.1-pro-free:free", "input": "hello sir"}
    assert seen["headers"]["Authorization"] == "Bearer test-key"
    assert rate == 44100 and audio.size == 1000


def test_optional_fields_only_sent_when_configured(engine, monkeypatch):
    seen = {}
    monkeypatch.setattr("requests.post", lambda url, headers=None, json=None, timeout=None:
                        (seen.update(json=json),
                         FakeResponse(content=_pcm_bytes(),
                                      headers={"Content-Type": "audio/pcm;rate=44100;channels=1"}))[1])

    engine.fish_conf.update(voice="", speed=1.2, http_referer="", app_title="JARVIS")
    engine._synthesize_fish("hi")

    assert "voice" not in seen["json"], "blank values must not be sent"
    assert seen["json"]["speed"] == 1.2


def test_http_error_raises(engine, monkeypatch):
    monkeypatch.setattr("requests.post", lambda *a, **k:
                        FakeResponse(status_code=429, text="rate limited"))
    with pytest.raises(RuntimeError, match="429"):
        engine._synthesize_fish("hi")


def test_json_body_on_200_raises(engine, monkeypatch):
    monkeypatch.setattr("requests.post", lambda *a, **k:
                        FakeResponse(content=b'{"error":"nope"}',
                                     headers={"Content-Type": "application/json"},
                                     text='{"error":"nope"}'))
    with pytest.raises(RuntimeError, match="JSON, not audio"):
        engine._synthesize_fish("hi")


def test_empty_body_raises(engine, monkeypatch):
    monkeypatch.setattr("requests.post", lambda *a, **k:
                        FakeResponse(content=b"",
                                     headers={"Content-Type": "audio/pcm;rate=44100;channels=1"}))
    with pytest.raises(RuntimeError, match="empty audio body"):
        engine._synthesize_fish("hi")


# ----------------------------------------------------------------- key lookup

def test_key_from_config_wins(engine, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "env-key")
    assert engine._resolve_fish_key() == "test-key"


def test_key_falls_back_to_env(engine, monkeypatch):
    engine.fish_conf["api_key"] = ""
    monkeypatch.setenv("OPENROUTER_API_KEY", "env-key")
    assert engine._resolve_fish_key() == "env-key"


def test_missing_key_raises_in_synthesize(engine, monkeypatch):
    engine.fish_conf["api_key"] = ""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="no API key"):
        engine._synthesize_fish("hi")


# ------------------------------------------------------------ backend routing

def test_speak_falls_back_to_edge_when_fish_fails(engine, monkeypatch):
    calls = []
    monkeypatch.setattr(engine, "_speak_fish",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(engine, "_speak_edge", lambda *a, **k: calls.append("edge"))
    engine.speak("hello")
    assert calls == ["edge"], "a failing Fish call must degrade to Edge, not go silent"


def test_speak_uses_edge_when_key_missing(engine, monkeypatch):
    engine.fish_conf["api_key"] = ""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    calls = []
    monkeypatch.setattr(engine, "_speak_fish", lambda *a, **k: calls.append("fish"))
    monkeypatch.setattr(engine, "_speak_edge", lambda *a, **k: calls.append("edge"))
    engine.speak("hello")
    assert calls == ["edge"]


def test_engine_override_forces_edge(engine, monkeypatch):
    calls = []
    monkeypatch.setattr(engine, "_speak_fish", lambda *a, **k: calls.append("fish"))
    monkeypatch.setattr(engine, "_speak_edge", lambda *a, **k: calls.append("edge"))
    engine.speak("hello", engine="edge")
    assert calls == ["edge"]


def test_fillers_stay_on_edge_by_default(engine, monkeypatch):
    calls = []
    monkeypatch.setattr(engine, "_speak_fish", lambda *a, **k: calls.append("fish"))
    monkeypatch.setattr(engine, "_speak_edge", lambda *a, **k: calls.append("edge"))
    engine.speak_filler()
    assert calls == ["edge"], "free Fish quota must not be spent on filler phrases"


def test_fillers_use_fish_when_opted_in(engine, monkeypatch):
    engine.fish_conf["use_for_fillers"] = True
    calls = []
    monkeypatch.setattr(engine, "_speak_fish", lambda *a, **k: calls.append("fish"))
    monkeypatch.setattr(engine, "_speak_edge", lambda *a, **k: calls.append("edge"))
    engine.speak_filler()
    assert calls == ["fish"]


# -------------------------------------------------------------- speak() state

def test_speak_sets_start_time_for_barge_in_guard(engine, monkeypatch):
    """main.py:931 reads speak_start_time to suppress self-interruption."""
    monkeypatch.setattr(engine, "_speak_fish", lambda *a, **k: None)
    engine.speak("hello")
    assert engine.speak_start_time > 0


def test_speak_clears_is_speaking_even_on_total_failure(engine, monkeypatch):
    monkeypatch.setattr(engine, "_speak_fish",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    monkeypatch.setattr(engine, "_speak_edge",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("y")))
    monkeypatch.setattr(engine, "_fallback_speak", lambda *a, **k: None)
    engine.speak("hello")
    assert engine.is_speaking is False


def test_speak_end_callback_fires_once_on_failure(engine, monkeypatch):
    fired = []
    engine.on_speak_end = lambda: fired.append(1)
    monkeypatch.setattr(engine, "_speak_fish",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    monkeypatch.setattr(engine, "_speak_edge",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("y")))
    monkeypatch.setattr(engine, "_fallback_speak", lambda *a, **k: None)
    engine.speak("hello")
    assert fired == [1], "unbalanced callbacks would leave audio ducked forever"


def test_empty_text_is_a_noop(engine, monkeypatch):
    calls = []
    monkeypatch.setattr(engine, "_speak_fish", lambda *a, **k: calls.append("fish"))
    engine.speak("")
    assert calls == [] and engine.is_speaking is False


# ------------------------------------------------------------- temp file care

def test_sweep_removes_stale_but_keeps_fresh(engine, tmp_path, monkeypatch):
    """A kill mid-playback skips per-call cleanup; the sweep is the backstop."""
    import os
    import time as _t
    monkeypatch.setattr(engine, "_temp_dir", lambda: str(tmp_path))

    stale = tmp_path / "edge_old.mp3"
    fresh = tmp_path / "fish_new.mp3"
    stale.write_bytes(b"x")
    fresh.write_bytes(b"y")
    old = _t.time() - 3600
    os.utime(stale, (old, old))

    engine._sweep_stale_temps(max_age_s=900)

    assert not stale.exists(), "stale artifact should be swept"
    assert fresh.exists(), "an in-flight file must not be deleted mid-playback"


def test_sweep_never_raises_on_bad_dir(engine, monkeypatch):
    monkeypatch.setattr(engine, "_temp_dir", lambda: "/nonexistent/does/not/exist")
    engine._sweep_stale_temps()  # must not raise


# --------------------------------------------------------- emotion tag passing

def test_bracket_tag_becomes_parenthetical_cue(engine):
    """prompts.yaml tells the LLM to emit [laugh]; it must reach Fish as a cue."""
    out = engine._prepare_fish_text("[laugh] Arre sir, aap toh funny ho!")
    assert out == "(laughing) Arre sir, aap toh funny ho!"


@pytest.mark.parametrize("tag,cue", [
    ("excited", "excitedly"),
    ("sad", "sadly"),
    ("sigh", "sighing"),
    ("thoughtful", "thoughtfully"),
])
def test_each_known_tag_maps_to_its_cue(engine, tag, cue):
    assert engine._prepare_fish_text(f"[{tag}] Theek hai sir.") == f"({cue}) Theek hai sir."


def test_tags_never_spoken_literally(engine):
    """Any leftover/unknown tag must be removed, never voiced as a word."""
    out = engine._prepare_fish_text("[laugh] Haan sir [unknown_tag] bilkul!")
    assert "[" not in out and "]" not in out
    assert "unknown_tag" not in out
    assert out == "(laughing) Haan sir bilkul!"


def test_untagged_text_is_unchanged(engine):
    assert engine._prepare_fish_text("Sir, reminder set kar diya.") == "Sir, reminder set kar diya."


def test_tag_only_text_yields_empty(engine):
    assert engine._prepare_fish_text("[laugh]") == ""


def test_speak_fish_skips_api_when_text_is_tag_only(engine, monkeypatch):
    called = []
    monkeypatch.setattr(engine, "_synthesize_fish", lambda t: called.append(t))
    engine._speak_fish("[laugh]", 1.0, False, False)
    assert called == [], "must not spend a request on empty content"


def test_first_recognised_tag_wins(engine):
    """Multiple tags must not produce stacked cues."""
    out = engine._prepare_fish_text("[excited] Wow! [sad] oh no.")
    assert out.count("(") == 1
