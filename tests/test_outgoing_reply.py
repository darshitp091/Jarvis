"""What happens when JARVIS replies to a message on the user's behalf.

Moved verbatim out of main.py, so these are the first tests either function has
had. The point of writing them before deduplicating the ~50 lines the two share
is that the AST gate can prove a move and nothing else -- these are the only
thing that will be able to say the dedup preserved behaviour.

Both functions import ollama, pyautogui, webbrowser, threading and urllib.parse
inside their bodies, so those are supplied by substituting sys.modules entries:
an import resolves through sys.modules at call time, so the substitution is seen
by the function under test and by nothing already imported. `time` is a
module-level name and is rebound on the module itself, which also keeps the
4.5-second wait from being real.

The threading shim runs the target synchronously on .start(), so the Enter press
is observable without a real thread or a real wait.
"""
import ast
import io
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))

from jarvis.skills import outgoing_reply  # noqa: E402

DB = os.path.join("config", "outgoing_replies.json")
STAMP = "2026-08-22 09:15:00"


class ModuleShim:
    """Answers from `overrides` first, then delegates to the real module."""

    def __init__(self, real, **overrides):
        self._real = real
        self._overrides = overrides

    def __getattr__(self, attr):
        try:
            return self._overrides[attr]
        except KeyError:
            return getattr(self._real, attr)


class Clock:
    def __init__(self):
        self.sleeps = []

    def sleep(self, seconds):
        self.sleeps.append(seconds)

    def strftime(self, fmt):
        return STAMP


class Phone:
    """Stand-in for self.phone: a contact book and a connection state."""

    def __init__(self, contacts=None, connected=False):
        self.contacts = contacts or {}
        self.connected = connected
        self.lookups = []

    def get_contact_by_name(self, name):
        self.lookups.append(name)
        return self.contacts.get(name)

    def is_device_connected(self):
        return self.connected


class Browser:
    def __init__(self):
        self.opened = []

    def open(self, url):
        self.opened.append(url)
        return True


class AutoGui:
    def __init__(self):
        self.pressed = []

    def press(self, key):
        self.pressed.append(key)


class Thread:
    """Runs the target on .start(), so no real thread and no real waiting."""

    instances = []

    def __init__(self, target=None, daemon=None):
        self.target = target
        self.daemon = daemon
        self.started = False
        Thread.instances.append(self)

    def start(self):
        self.started = True
        self.target()


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(outgoing_reply, "time", c)
    return c


@pytest.fixture
def desktop(monkeypatch):
    """webbrowser, pyautogui and threading, none of which CI has or wants."""
    import threading as real_threading
    import webbrowser as real_webbrowser

    browser, gui = Browser(), AutoGui()
    Thread.instances = []
    monkeypatch.setitem(sys.modules, "webbrowser",
                        ModuleShim(real_webbrowser, open=browser.open))
    monkeypatch.setitem(sys.modules, "pyautogui", gui)
    monkeypatch.setitem(sys.modules, "threading",
                        ModuleShim(real_threading, Thread=Thread))
    return type("Desktop", (), {"browser": browser, "gui": gui,
                                "threads": Thread.instances})()


@pytest.fixture
def cwd(tmp_path, monkeypatch):
    """config/ exists, as it does in a real checkout."""
    (tmp_path / "config").mkdir()
    monkeypatch.chdir(tmp_path)
    return tmp_path


def records():
    with io.open(DB, encoding="utf-8") as fh:
        return json.load(fh)


def reply(text="theek hai", sender="Aarav", channel="WhatsApp", **kwargs):
    kwargs.setdefault("phone", Phone())
    return outgoing_reply.log_direct_reply(sender, channel, text, **kwargs)


# --- the outgoing log -------------------------------------------------------

def test_a_reply_is_appended_to_the_outgoing_database(cwd, clock):
    reply("theek hai", channel="SMS")
    assert records() == [{
        "timestamp": STAMP,
        "channel": "SMS",
        "recipient": "Aarav",
        "message_body": "theek hai",
        "status": "SENT",
    }]


def test_existing_records_are_preserved(cwd, clock):
    io.open(DB, "w", encoding="utf-8").write(
        json.dumps([{"message_body": "older"}]))
    reply("newer", channel="SMS")
    assert [r["message_body"] for r in records()] == ["older", "newer"]


def test_the_file_is_created_when_absent(cwd, clock):
    assert not os.path.exists(DB)
    reply(channel="SMS")
    assert len(records()) == 1


def test_the_record_is_written_before_anything_is_sent(cwd, clock):
    """Pinned, not fixed -- status "SENT" is a hope, not an observation.

    The record is appended with status "SENT" and flushed to disk before the
    channel is even looked at, and nothing ever revises it. So the outgoing
    database is a log of messages JARVIS intended to send, presented as a log of
    messages it did send. Every count, audit or "what did I reply?" query built
    on this file inherits that.
    """
    phone = Phone()                            # no contacts: nothing can be sent
    outgoing_reply.log_direct_reply("Unknown", "WhatsApp", "hi", phone=phone)
    assert records()[0]["status"] == "SENT"


def test_devanagari_is_written_literally(cwd, clock):
    reply("रिप्लाई", channel="SMS")
    raw = io.open(DB, encoding="utf-8").read()
    assert "\\u0930" not in raw, "ensure_ascii=False keeps the script readable"
    assert records()[0]["message_body"] == "रिप्लाई"


def test_the_file_is_indented(cwd, clock):
    reply(channel="SMS")
    assert "\n  " in io.open(DB, encoding="utf-8").read()


# --- the outgoing log, when it goes wrong -----------------------------------

def test_a_corrupt_database_drops_the_reply_and_every_later_one(cwd, clock):
    """Pinned, not fixed -- the worst of the defects here.

    The try block covers both the read and the write, so a file that will not
    parse means json.load raises, the append never happens, and json.dump is
    never reached. The corrupt file therefore stays corrupt, and every reply
    from then on is silently dropped the same way -- permanently, with no
    recovery path and no signal to the user, who is still told the message was
    sent. Reading and writing in separate try blocks, or treating a parse
    failure as an empty log, both fix it.
    """
    io.open(DB, "w", encoding="utf-8").write("{not json")
    assert reply("lost", channel="SMS").startswith("Sir, maine")
    assert io.open(DB, encoding="utf-8").read() == "{not json", "not repaired"


def test_a_database_holding_a_dict_drops_the_reply(cwd, clock):
    """Pinned, not fixed. Same swallow, different cause: replies.append is an
    AttributeError on a dict, inside the same try."""
    io.open(DB, "w", encoding="utf-8").write('{"a": 1}')
    reply("lost", channel="SMS")
    assert json.loads(io.open(DB, encoding="utf-8").read()) == {"a": 1}


def test_a_missing_config_directory_drops_the_reply(tmp_path, monkeypatch, clock):
    """Pinned, not fixed.

    The path is relative and the directory is never created, so on any working
    directory without a config/ the open-for-write raises FileNotFoundError,
    which the same except swallows. The user is told the message was sent.
    os.makedirs(os.path.dirname(path), exist_ok=True) is the whole fix.
    """
    monkeypatch.chdir(tmp_path)                # no config/
    assert reply("lost", channel="SMS").startswith("Sir, maine")
    assert not os.path.exists(DB)


def test_the_reply_is_still_claimed_sent_after_a_write_failure(tmp_path,
                                                               monkeypatch, clock):
    monkeypatch.chdir(tmp_path)
    assert "bol diya hai" in reply("lost", channel="SMS")


# --- the WhatsApp path ------------------------------------------------------

def test_a_non_whatsapp_channel_touches_the_phone_at_all(cwd, clock):
    phone = Phone(contacts={"Aarav": "9876543210"})
    outgoing_reply.log_direct_reply("Aarav", "SMS", "hi", phone=phone)
    assert phone.lookups == [], "SMS is logged and nothing else"


def test_an_unknown_contact_sends_nothing(cwd, clock, desktop):
    phone = Phone(contacts={})
    outgoing_reply.log_direct_reply("Nobody", "WhatsApp", "hi", phone=phone)
    assert phone.lookups == ["Nobody"]
    assert desktop.browser.opened == []


def test_a_ten_digit_number_gets_the_country_code(cwd, clock, desktop):
    phone = Phone(contacts={"Aarav": "9876543210"})
    outgoing_reply.log_direct_reply("Aarav", "WhatsApp", "hi", phone=phone)
    assert "phone=919876543210" in desktop.browser.opened[0]


def test_punctuation_is_stripped_from_the_number(cwd, clock, desktop):
    phone = Phone(contacts={"Aarav": "+91 98765-43210"})
    outgoing_reply.log_direct_reply("Aarav", "WhatsApp", "hi", phone=phone)
    assert "phone=919876543210" in desktop.browser.opened[0]


def test_a_number_that_already_has_a_country_code_is_left_alone(cwd, clock, desktop):
    phone = Phone(contacts={"Aarav": "919876543210"})
    outgoing_reply.log_direct_reply("Aarav", "WhatsApp", "hi", phone=phone)
    assert "phone=919876543210" in desktop.browser.opened[0]


def test_a_short_number_is_used_as_is(cwd, clock, desktop):
    """Pinned, not fixed: only a length of exactly 10 gets the 91 prefix, so a
    nine-digit typo is handed to WhatsApp unprefixed rather than rejected."""
    phone = Phone(contacts={"Aarav": "987654321"})
    outgoing_reply.log_direct_reply("Aarav", "WhatsApp", "hi", phone=phone)
    assert "phone=987654321" in desktop.browser.opened[0]


def test_the_message_is_url_encoded_into_the_deep_link(cwd, clock, desktop):
    phone = Phone(contacts={"Aarav": "9876543210"})
    outgoing_reply.log_direct_reply("Aarav", "WhatsApp", "kal milte hai?",
                                    phone=phone)
    url = desktop.browser.opened[0]
    assert url.startswith("whatsapp://send?phone=919876543210&text=")
    assert "kal%20milte%20hai%3F" in url


def test_enter_is_pressed_on_a_daemon_thread_after_four_and_a_half_seconds(
        cwd, clock, desktop):
    phone = Phone(contacts={"Aarav": "9876543210"})
    outgoing_reply.log_direct_reply("Aarav", "WhatsApp", "hi", phone=phone)
    assert len(desktop.threads) == 1
    assert desktop.threads[0].daemon is True
    assert desktop.threads[0].started
    assert clock.sleeps == [4.5]
    assert desktop.gui.pressed == ["enter"]


def test_a_connected_device_sends_nothing_at_all(cwd, clock, desktop):
    """Pinned, not fixed.

    When the phone reports itself connected the branch is a bare `pass` under a
    comment saying sending "is already handled in phone skill if active" -- but
    nothing in this function or its callers does that. So the one configuration
    where sending should be most reliable is the one where no send is attempted:
    the record is written, the desktop path is skipped, and the user is told the
    message went out.
    """
    phone = Phone(contacts={"Aarav": "9876543210"}, connected=True)
    outgoing_reply.log_direct_reply("Aarav", "WhatsApp", "hi", phone=phone)
    assert desktop.browser.opened == []
    assert desktop.gui.pressed == []
    assert records()[0]["status"] == "SENT"


def test_a_browser_failure_is_swallowed(cwd, clock, monkeypatch, desktop):
    def boom(url):
        raise OSError("no handler for whatsapp://")

    import webbrowser as real_webbrowser
    monkeypatch.setitem(sys.modules, "webbrowser",
                        ModuleShim(real_webbrowser, open=boom))
    phone = Phone(contacts={"Aarav": "9876543210"})
    out = outgoing_reply.log_direct_reply("Aarav", "WhatsApp", "hi", phone=phone)
    assert "bol diya hai" in out
    assert desktop.gui.pressed == [], "the Enter thread never started"


def test_the_channel_substring_match_is_loose(cwd, clock, desktop):
    """Pinned, not fixed: the test is `"WhatsApp" in channel`, so a channel
    named "Not WhatsApp" or "WhatsApp Business" takes the same path."""
    phone = Phone(contacts={"Aarav": "9876543210"})
    outgoing_reply.log_direct_reply("Aarav", "Not WhatsApp", "hi", phone=phone)
    assert len(desktop.browser.opened) == 1


# --- what the user is told --------------------------------------------------

def test_the_confirmation_names_the_channel_and_the_recipient(cwd, clock):
    out = outgoing_reply.log_direct_reply("Aarav", "SMS", "theek hai",
                                          phone=Phone())
    assert out == "Sir, maine SMS par Aarav ko bol diya hai: 'theek hai'."


# --- drafting in the user's voice -------------------------------------------

MODELS = {"main_brain": "test-brain:latest"}
FALLBACK = "Sir, thodi der me message karti hu."


class Brain:
    def __init__(self, content="haan bro, abhi aata hu", error=None, reply=None):
        self.calls = []
        self.error = error
        self.reply = reply if reply is not None else {"message": {"content": content}}

    def chat(self, model=None, messages=None, options=None):
        self.calls.append({"model": model, "messages": messages, "options": options})
        if self.error is not None:
            raise self.error
        return self.reply


@pytest.fixture
def brain(monkeypatch):
    b = Brain()
    monkeypatch.setitem(sys.modules, "ollama", b)
    return b


def draft(instruction="bol do busy hu", sender="Aarav", channel="SMS",
          msg_body="kahan ho?", models=None, phone=None):
    return outgoing_reply.draft_and_send_style_reply(
        sender, channel, msg_body, instruction,
        models=MODELS if models is None else models,
        phone=phone if phone is not None else Phone())


def test_the_configured_brain_writes_the_draft(cwd, clock, brain):
    draft()
    assert brain.calls[0]["model"] == "test-brain:latest"
    assert brain.calls[0]["options"] == {"temperature": 0.5}


def test_the_prompt_carries_the_incoming_message_and_the_instruction(cwd, clock,
                                                                    brain):
    draft(instruction="bol do kal call karunga", sender="Aarav",
          channel="WhatsApp", msg_body="kahan ho?")
    system, user = brain.calls[0]["messages"]
    assert system["role"] == "system" and user["role"] == "user"
    assert "Darshit" in system["content"], "the user's name is baked into the prompt"
    assert "Aarav" in user["content"] and "WhatsApp" in user["content"]
    assert "kahan ho?" in user["content"]
    assert "bol do kal call karunga" in user["content"]


def test_the_draft_is_what_gets_logged(cwd, clock, brain):
    brain.reply = {"message": {"content": "  abhi busy hu  "}}
    draft()
    assert records()[0]["message_body"] == "abhi busy hu"


def test_surrounding_quotes_are_removed(cwd, clock, brain):
    brain.reply = {"message": {"content": '"abhi busy hu"'}}
    draft()
    assert records()[0]["message_body"] == "abhi busy hu"


def test_a_trailing_quoted_word_loses_its_closing_quote(cwd, clock, brain):
    """Pinned, not fixed.

    The cleanup is .strip().strip('"').strip("'"), which strips those characters
    from both ends unconditionally rather than only as a matched pair. A model
    that writes `kal milte hai 'bro'` has the closing apostrophe eaten and the
    opening one left, so the message sent carries an unbalanced quote.
    """
    brain.reply = {"message": {"content": "kal milte hai 'bro'"}}
    draft()
    assert records()[0]["message_body"] == "kal milte hai 'bro"


def test_the_draft_is_what_gets_sent(cwd, clock, brain, desktop):
    brain.reply = {"message": {"content": "abhi busy hu"}}
    draft(channel="WhatsApp", phone=Phone(contacts={"Aarav": "9876543210"}))
    assert "abhi%20busy%20hu" in desktop.browser.opened[0]


def test_the_confirmation_quotes_the_draft_back(cwd, clock, brain):
    brain.reply = {"message": {"content": "abhi busy hu"}}
    out = draft(channel="SMS")
    assert out == ("Sir, maine aapki taraf se SMS par Aarav ko reply bhej diya "
                   "hai. Message tha: 'abhi busy hu'.")


# --- drafting, when the brain will not answer -------------------------------

@pytest.mark.parametrize("failure", [
    {"error": RuntimeError("model not pulled")},
    {"reply": {"no message key": True}},
    {"reply": {"message": {}}},
])
def test_a_canned_message_is_sent_when_drafting_fails(cwd, clock, monkeypatch,
                                                      failure):
    """Pinned, not fixed -- the most consequential defect of the pair.

    Any failure to draft falls back to a hardcoded string and then treats it
    exactly like a real draft: it is written to the outgoing log and, on
    WhatsApp, actually sent to the contact. So a model that is not pulled, or a
    reply shaped unexpectedly, results in a message going out to another person
    in the user's name that the user never wrote and never saw -- and the
    confirmation quotes it back as though it were their reply.

    The string is also in the wrong voice twice over: it opens with "Sir",
    addressing the recipient the way JARVIS addresses the user, and uses a
    feminine verb form while the system prompt three lines above instructs the
    model to write as Darshit ("karta hu"). Whoever receives it can tell it was
    not written by the person whose name is on it.
    """
    monkeypatch.setitem(sys.modules, "ollama", Brain(**failure))
    out = draft(channel="SMS")
    assert records()[0]["message_body"] == FALLBACK
    assert FALLBACK in out


def test_a_missing_ollama_module_also_sends_the_canned_message(cwd, clock,
                                                              monkeypatch):
    """Which is the situation in CI, and on any machine without ollama."""
    monkeypatch.setitem(sys.modules, "ollama", None)   # import binds None
    out = draft(channel="SMS")
    assert FALLBACK in out


def test_a_models_dict_without_a_main_brain_sends_the_canned_message(cwd, clock,
                                                                     brain):
    """Pinned, not fixed: models["main_brain"] is a subscript inside the try, so
    a misconfigured models dict is indistinguishable from a model failure."""
    out = draft(models={}, channel="SMS")
    assert brain.calls == [], "it never reached the model"
    assert FALLBACK in out


def test_an_empty_draft_is_sent_as_an_empty_message(cwd, clock, brain, desktop):
    """Pinned, not fixed: whitespace strips to "", which is logged and sent."""
    brain.reply = {"message": {"content": "   "}}
    draft(channel="WhatsApp", phone=Phone(contacts={"Aarav": "9876543210"}))
    assert records()[0]["message_body"] == ""
    assert desktop.browser.opened[0].endswith("&text=")


# --- the duplication, and what replaced it -----------------------------------

def test_both_entry_points_route_through_one_helper():
    """The successor to the test that compared the two copies statement by statement.

    Until the commit that added _record_and_send, the tail of each function was
    the other's -- fifty lines differing in one place, the word "direct" in an
    error message. Both now delegate instead, and this fails if either grows its
    own copy back. That is the easy mistake to make here, because each function
    reads perfectly well on its own once it has been inlined.
    """
    source = io.open(outgoing_reply.__file__, encoding="utf-8").read()
    fns = {n.name: n for n in ast.parse(source).body
           if isinstance(n, ast.FunctionDef)}

    for name, variable in (("draft_and_send_style_reply", "draft"),
                           ("log_direct_reply", "reply_text")):
        call = fns[name].body[-2].value
        assert ast.unparse(call.func) == "_record_and_send"
        assert [ast.unparse(a) for a in call.args] == ["sender", "channel", variable]
        assert {k.arg: ast.unparse(k.value) for k in call.keywords} == {"phone": "phone"}
        body = ast.unparse(fns[name])
        assert "out_db_path" not in body, "%s writes the database itself again" % name
        assert "get_contact_by_name" not in body, "%s sends the message itself again" % name


# --- the delegations in main.py ---------------------------------------------
#
# main.py cannot be imported here -- it constructs PyQt6 objects, which the
# environment CI runs in does not have -- so the shims are checked by parsing it.

MAIN_PY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "main.py")


def _jarvis_method(name):
    with io.open(MAIN_PY, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    cls = next(n for n in tree.body
               if isinstance(n, ast.ClassDef) and n.name == "JARVIS")
    return next(n for n in cls.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                and n.name == name)


@pytest.mark.parametrize("method, function", [
    ("_draft_and_send_style_reply", "outgoing_reply.draft_and_send_style_reply"),
    ("_log_direct_reply", "outgoing_reply.log_direct_reply"),
])
def test_each_method_is_only_a_delegation(method, function):
    fn = _jarvis_method(method)
    assert len(fn.body) == 1, "the body came back"
    assert isinstance(fn.body[0], ast.Return)
    assert ast.unparse(fn.body[0].value.func) == function


def test_the_drafting_delegation_forwards_its_arguments_and_injects_state():
    call = _jarvis_method("_draft_and_send_style_reply").body[0].value
    assert [ast.unparse(a) for a in call.args] == [
        "sender", "channel", "msg_body", "user_instruction"]
    assert {k.arg: ast.unparse(k.value) for k in call.keywords} == {
        "models": "self.models", "phone": "self.phone"}


def test_the_direct_delegation_injects_only_the_phone():
    call = _jarvis_method("_log_direct_reply").body[0].value
    assert [ast.unparse(a) for a in call.args] == ["sender", "channel", "reply_text"]
    assert {k.arg: ast.unparse(k.value) for k in call.keywords} == {
        "phone": "self.phone"}


def test_the_signatures_agree_with_the_moved_functions():
    import inspect
    for method, fn in (("_draft_and_send_style_reply",
                        outgoing_reply.draft_and_send_style_reply),
                       ("_log_direct_reply", outgoing_reply.log_direct_reply)):
        shim = [a.arg for a in _jarvis_method(method).args.args]
        params = inspect.signature(fn).parameters
        positional = [n for n, p in params.items() if p.kind is not p.KEYWORD_ONLY]
        assert shim[0] == "self"
        assert shim[1:] == positional, method

