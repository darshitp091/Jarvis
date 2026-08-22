"""What JARVIS says it is about to do, before it does it.

`friendly_task_desc` produces one clause of the spoken plan announcement -- the
"open WhatsApp and draft a message" in "First, I will open WhatsApp and draft a
message, and then I will ...". It routes the text to find out what the command
means, then picks a phrase for it.

Two things this file is arranged around.

The first is that the phrase and the intent can disagree. Routing happens here
purely to choose wording, so any skill the wording tables do not list falls
through to keyword-matching the raw words -- and a keyword match is a guess. A
file deletion whose text mentions "find" is announced as a web search.

The second is that the Hinglish and English tables are not the same size.
English has phrases for the firewall and the hologram; Hinglish does not, so the
same command is described in one language and merely quoted back in the other.
"""
import ast
import io
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))

from jarvis.core import task_narration  # noqa: E402


class Router:
    """Answers route() from a text -> intent map, and records what it was asked.

    The recording is the point of several tests below: describing a command
    routes it, and `process_command` then routes it again to run it.
    """

    def __init__(self, intents=None, default=None):
        self.intents = intents or {}
        self.default = default or {"skill": "conversation"}
        self.calls = []

    def route(self, text, topic=None):
        self.calls.append((text, topic))
        return dict(self.intents.get(text, self.default))

    @property
    def routed(self):
        return [text for text, _ in self.calls]


def intent(skill, **params):
    return {"skill": skill, "params": params}


def say(text, is_hinglish=False, router=None, candidates=(), topic=None):
    return task_narration.friendly_task_desc(
        text, is_hinglish,
        router=router if router is not None else Router(),
        active_presentation_topic=topic,
        get_phonetic_candidates=lambda t: list(candidates))


# --- the phrase tables, side by side -----------------------------------------

OS_CONTROL = [
    # action, params, Hinglish, English
    ("clean_disk", {}, "system ki temporary files clear karungi",
     "clear the system temporary files"),
    ("empty_recycle_bin", {}, "recycle bin ki trash files empty karungi",
     "empty the recycle bin"),
    ("secure", {}, "laptop screen lock karungi", "lock the screen"),
    ("unlock", {}, "system unlock karungi", "unlock the screen"),
    ("launch", {"app": "notepad"}, "notepad open karungi", "launch the notepad"),
    ("close", {"app": "chrome"}, "chrome close karungi", "close chrome"),
    ("set_brightness", {"percent": 70},
     "brightness adjusted 70 percent karungi",
     "adjust system brightness to 70 percent"),
]


@pytest.mark.parametrize("action,params,hinglish,english",
                         OS_CONTROL, ids=[row[0] for row in OS_CONTROL])
def test_every_os_control_action_is_announced_in_both_languages(
        action, params, hinglish, english):
    router = Router(default=intent("os_control", action=action, **params))
    assert say("do it", is_hinglish=True, router=router) == hinglish
    assert say("do it", router=router) == english


def test_a_system_monitor_check_is_announced_in_both_languages():
    router = Router(default=intent("system_monitor"))
    assert say("vitals", is_hinglish=True, router=router) == "system resource check karungi"
    assert say("vitals", router=router) == "check system resources"


@pytest.mark.parametrize("action,expected", [
    ("quarantine", "quarantine and block remote endpoint 10.0.0.5"),
    ("remove_quarantine", "remove firewall block for 10.0.0.5"),
    ("list_blocks", "list active firewall quarantine blocks"),
])
def test_the_firewall_actions_are_announced_in_english(action, expected):
    router = Router(default=intent("sentry_firewall", action=action, ip="10.0.0.5"))
    assert say("block it", router=router) == expected


@pytest.mark.parametrize("params,expected", [
    ({"action": "explode", "enable": True}, "explode the hologram assembly"),
    ({"action": "explode", "enable": False}, "collapse the hologram assembly"),
    ({"action": "toggle_heatmap", "enable": True}, "show the load heatmap"),
    ({"action": "toggle_heatmap", "enable": False}, "hide the load heatmap"),
    ({"action": "set_rotation", "speed": "fast"},
     "set hologram rotation speed to fast"),
])
def test_the_hologram_actions_are_announced_in_english(params, expected):
    assert say("hologram", router=Router(default=intent("hologram_control", **params))) == expected


# --- the two tables are not the same size ------------------------------------

@pytest.mark.parametrize("skill,params", [
    ("sentry_firewall", {"action": "quarantine", "ip": "10.0.0.5"}),
    ("hologram_control", {"action": "explode", "enable": True}),
], ids=["sentry_firewall", "hologram_control"])
def test_hinglish_has_no_phrase_for_what_english_describes(skill, params):
    """The same routed intent: described in English, quoted back in Hinglish.

    Nothing marks the Hinglish answer as a fallback -- it is the same sentence
    shape used for a command that did not route at all.
    """
    router = Router(default=intent(skill, **params))
    english = say("block that address", router=router)
    hinglish = say("block that address", is_hinglish=True, router=router)
    assert english != "block that address"
    assert hinglish == "'block that address' command run karungi"


def test_hinglish_has_no_music_keyword_in_its_fallback():
    """"gaana" is in the English keyword list and not the Hinglish one."""
    assert say("mera gaana chalao", is_hinglish=True) == "'mera gaana chalao' command run karungi"
    assert say("mera gaana chalao") == "play the requested song"


# --- a phrase and an intent that disagree ------------------------------------

def test_an_intent_the_tables_do_not_list_is_described_from_the_words_instead():
    """The defect this file leads with.

    `file_manager` has no phrase, so the routed intent is discarded and the raw
    words are keyword-matched: "find" wins, and a delete is announced as a
    search. The announcement is spoken before the command runs, so this is what
    the user is told is about to happen.
    """
    router = Router(default=intent("file_manager", action="delete"))
    assert say("find the old invoices", router=router) == "conduct a web search"


def test_music_wins_over_search_in_the_english_fallback():
    """Both keywords are present; the order of the elif chain decides."""
    assert say("search for that song") == "play the requested song"


@pytest.mark.parametrize("text,expected", [
    ("message him on whatsapp", "open WhatsApp and draft a message"),
    ("build me a ppt", "create the requested presentation"),
    ("google the weather", "conduct a web search"),
])
def test_the_english_fallback_keywords(text, expected):
    assert say(text) == expected


@pytest.mark.parametrize("text,expected", [
    ("whatsapp par bhejo", "WhatsApp par message send karungi"),
    ("ek slide banao", "presentation generate karungi"),
    ("google karo", "web search karungi"),
])
def test_the_hinglish_fallback_keywords(text, expected):
    assert say(text, is_hinglish=True) == expected


# --- what the last resort says -----------------------------------------------

def test_a_short_english_command_is_echoed_back_as_its_own_description():
    """Five words or fewer come back unchanged, so the sentence around it may not parse.

    The caller says "First, I will {desc}", which reads correctly for an
    imperative and not at all for a question.
    """
    assert say("open the side panel") == "open the side panel"
    assert say("what is the time") == "what is the time"


def test_a_long_english_command_is_truncated_with_a_spoken_ellipsis():
    assert say("copy the quarterly numbers into the deck for review") == \
        "copy the quarterly numbers into..."


def test_hinglish_quotes_the_command_rather_than_truncating_it():
    """The quote characters are handed to the speech engine as-is."""
    assert say("kuch bhi karo yaar abhi", is_hinglish=True) == \
        "'kuch bhi karo yaar abhi' command run karungi"


# --- invented defaults -------------------------------------------------------

def test_a_missing_brightness_percent_is_announced_as_fifty():
    """The router extracted no number; 50 is announced as though it had."""
    router = Router(default=intent("os_control", action="set_brightness"))
    assert say("brightness", router=router) == "adjust system brightness to 50 percent"
    assert say("brightness", is_hinglish=True, router=router) == \
        "brightness adjusted 50 percent karungi"


def test_a_missing_app_name_is_announced_as_a_placeholder():
    router = Router(default=intent("os_control", action="launch"))
    assert say("open it", is_hinglish=True, router=router) == "app open karungi"
    assert say("open it", router=router) == "launch the requested application"


def test_a_hologram_action_with_no_flag_is_announced_as_exploding():
    router = Router(default=intent("hologram_control", action="explode"))
    assert say("hologram", router=router) == "explode the hologram assembly"


def test_youtube_music_is_announced_as_spotify_in_hinglish():
    """One phrase serves both players, and it names the wrong one."""
    router = Router(default=intent("youtube_music", action="play", query="lag ja gale"))
    assert say("gaana", is_hinglish=True, router=router) == \
        "Spotify par lag ja gale play karungi"
    assert say("gaana", router=router) == "play lag ja gale"


def test_a_missing_query_is_announced_as_a_placeholder():
    router = Router(default=intent("spotify", action="play"))
    assert say("play", is_hinglish=True, router=router) == "Spotify par gaana play karungi"
    assert say("play", router=router) == "play music"


# --- routing a second time, to retry a mishearing ----------------------------

def test_a_mishearing_that_routes_is_described_from_the_candidate():
    router = Router(intents={"lock the screen": intent("os_control", action="secure")})
    said = say("loch the screen", candidates=["loch the screen", "lock the screen"],
               router=router)
    assert said == "lock the screen"
    assert router.routed == ["loch the screen", "loch the screen", "lock the screen"]


def test_the_first_candidate_that_routes_wins():
    router = Router(intents={"empty the bin": intent("os_control", action="empty_recycle_bin"),
                             "empty the tin": intent("os_control", action="clean_disk")})
    said = say("empty the din", router=router,
               candidates=["empty the bin", "empty the tin"])
    assert said == "empty the recycle bin"
    assert "empty the tin" not in router.routed


def test_no_candidate_routing_leaves_it_to_the_keyword_fallback():
    router = Router()
    assert say("google it", router=router, candidates=["google it", "goggle it"]) == \
        "conduct a web search"
    assert router.routed == ["google it", "google it", "goggle it"]


def test_describing_one_command_routes_it_once_per_candidate():
    """The cost of the announcement, before the command is routed again to run it."""
    router = Router()
    say("do the thing", router=router, candidates=["a", "b", "c", "d"])
    assert len(router.calls) == 5


def test_a_command_that_already_routes_is_not_reheard():
    router = Router(default=intent("system_monitor"))
    say("vitals", router=router, candidates=["vitals", "widgets"])
    assert router.routed == ["vitals"]


def test_the_presentation_topic_reaches_the_router_with_every_candidate():
    router = Router()
    say("next slide", router=router, candidates=["next slide"], topic="Q3 results")
    assert router.calls == [("next slide", "Q3 results"), ("next slide", "Q3 results")]


# --- the two dead lines, now gone --------------------------------------------

def test_the_body_carries_nothing_that_does_nothing():
    """Both lines predated the move and came across with it, verbatim.

    `import re` had no user anywhere in the function, and `domain` was assigned
    inside the phonetic loop and never read. Removing them changes the body, so
    the AST equivalence gate that proved the move could not also prove the
    removal -- every other test in this file is what proves it, unchanged from
    the commit that moved the code.
    """
    source = io.open(task_narration.__file__, encoding="utf-8").read()
    fn = next(n for n in ast.parse(source).body
              if isinstance(n, ast.FunctionDef) and n.name == "friendly_task_desc")
    body = ast.unparse(fn)
    assert "import" not in body, "the function imports something again"
    assert "domain" not in body, "the unread domain assignment is back"
    assert not [n for n in ast.walk(fn) if isinstance(n, (ast.Import, ast.ImportFrom))]


# --- the sentence built around those clauses ---------------------------------
#
# `plan_announcement` is spoken once, before any of the chain runs, so every
# string here is something the user hears described as about to happen.

TWO = ["open the notepad", "lock the screen"]
THREE = TWO + ["check system resources"]


def test_two_commands_are_both_named():
    assert task_narration.plan_announcement(TWO) == \
        "Right away, sir. First, I will open the notepad, and then I will lock the screen."
    assert task_narration.plan_announcement(TWO, True) == \
        "Ji sir, pehle main open the notepad, aur phir lock the screen."


def test_three_commands_are_all_named():
    assert task_narration.plan_announcement(THREE) == (
        "Right away, sir. First, I will open the notepad, next, I will lock the "
        "screen, and finally, I will check system resources.")
    assert task_narration.plan_announcement(THREE, True) == (
        "Abhi karti hu, sir. Pehle main open the notepad, uske baad lock the "
        "screen, aur finally check system resources.")


@pytest.mark.parametrize("n", [4, 5, 6])
def test_beyond_three_only_the_first_is_named_and_the_rest_are_a_number(n):
    """`descs[1:]` is never spoken. The count stands in for all of them."""
    descs = [f"do thing {i}" for i in range(n)]
    english = task_narration.plan_announcement(descs)
    hinglish = task_narration.plan_announcement(descs, True)
    assert english == (f"Right away, sir. I have a chain of {n} tasks to execute: "
                       "first, I will do thing 0, and then proceed with the rest.")
    assert hinglish == (f"Bilkul sir, mere paas {n} tasks ki list hai: pehle main "
                        "do thing 0 aur phir baki sab karti hu.")
    for later in descs[1:]:
        assert later not in english
        assert later not in hinglish


def test_one_command_falls_into_the_many_branch_and_says_so_wrongly():
    """There is no branch for one, because `process_command` never asks for one.

    It only calls this after splitting an utterance into more than one command.
    So the `else` has never had to be right for a single task -- and it is not:
    it announces a chain of one and promises to proceed with a rest that does
    not exist. Anything that starts calling this unconditionally gets that.
    """
    assert task_narration.plan_announcement(["lock the screen"]) == (
        "Right away, sir. I have a chain of 1 tasks to execute: first, I will "
        "lock the screen, and then proceed with the rest.")
    assert task_narration.plan_announcement(["lock the screen"], True) == (
        "Bilkul sir, mere paas 1 tasks ki list hai: pehle main lock the screen "
        "aur phir baki sab karti hu.")


def test_no_commands_at_all_raises():
    with pytest.raises(IndexError):
        task_narration.plan_announcement([])


def test_the_transition_between_two_commands():
    assert task_narration.task_transition("lock the screen") == \
        "Now, I am going to lock the screen, sir."
    assert task_narration.task_transition("lock the screen", True) == \
        "Chaliye sir, ab main lock the screen."


def test_the_clause_and_the_sentence_fit_together():
    """The two halves used to live in different files. This is the seam.

    It also shows what the five-word echo does once it is inside a sentence: a
    question comes back as its own description, and the sentence wraps it as
    though it were an imperative.
    """
    descs = [say("message him on whatsapp"), say("what is the time")]
    assert task_narration.plan_announcement(descs) == (
        "Right away, sir. First, I will open WhatsApp and draft a message, and "
        "then I will what is the time.")


# --- whether a transition is spoken at all -----------------------------------

@pytest.mark.parametrize("command", [
    "play the next track", "turn the volume up", "start the music",
    "put on a song", "mute it", "lock the screen", "sentry mode on",
    "secure the machine",
])
def test_an_urgent_command_is_not_narrated_first(command):
    assert task_narration.is_immediate_action(command) is True


@pytest.mark.parametrize("command", [
    "open the notepad", "check system resources", "draft a message to him",
    "build me a presentation", "search for the invoice", "",
])
def test_everything_else_gets_its_transition(command):
    assert task_narration.is_immediate_action(command) is False


def test_the_test_is_case_insensitive():
    assert task_narration.is_immediate_action("LOCK THE SCREEN") is True


@pytest.mark.parametrize("command,matched", [
    ("display the clock", "play"),      # and "lock", twice over
    ("unblock port 8080", "lock"),
    ("check my commute times", "mute"),
    ("replay the meeting notes", "play"),
    ("unlock the door", "lock"),
])
def test_a_word_that_merely_contains_one_loses_its_transition(command, matched):
    """Substring containment, not word matching.

    None of these are urgent, and every one of them is treated as urgent, so the
    spoken transition before it is skipped. "display the clock" is caught twice.
    """
    assert matched in command.lower()
    assert task_narration.is_immediate_action(command) is True


def test_unmute_is_an_unreachable_entry_in_the_list():
    """"mute" is listed before it and matches every string "unmute" does."""
    assert task_narration.is_immediate_action("unmute the mic") is True
    both = [p for p in ("mute", "unmute") if p in "unmute the mic"]
    assert both == ["mute", "unmute"], "both match; the second can never decide"


def test_a_chain_of_urgent_commands_announces_one_and_silently_does_the_rest():
    """The two defects composed, which is how a user meets them.

    Four commands, so only the first is named. Every command after it is urgent,
    so none of them gets a transition either. The user is told about one task
    and four run.
    """
    cmds = ["open the notepad", "play something", "lock the screen", "mute it"]
    descs = [f"desc for {c}" for c in cmds]
    spoken = [task_narration.plan_announcement(descs)]
    for idx, cmd in enumerate(cmds):
        if idx > 0 and not task_narration.is_immediate_action(cmd):
            spoken.append(task_narration.task_transition(descs[idx]))
    assert len(spoken) == 1, "a transition was spoken after all"
    assert "chain of 4 tasks" in spoken[0]
    assert "desc for open the notepad" in spoken[0]
    for later in descs[1:]:
        assert later not in spoken[0]


# --- the delegation in main.py ----------------------------------------------
#
# main.py imports PyQt6 at module level, which the environment CI runs in does
# not have, so the shim is checked by parsing it rather than importing it.

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


def test_the_method_is_only_a_delegation():
    fn = _jarvis_method("_get_friendly_task_desc")
    assert len(fn.body) == 2, "the body came back"
    assert isinstance(fn.body[0], ast.Expr), "the docstring is gone"
    assert isinstance(fn.body[1], ast.Return)
    call = fn.body[1].value
    assert ast.unparse(call.func) == "task_narration.friendly_task_desc"
    assert [ast.unparse(a) for a in call.args] == ["text", "is_hinglish"]
    assert {k.arg: ast.unparse(k.value) for k in call.keywords} == {
        "router": "self.router",
        "active_presentation_topic": "self.active_presentation_topic",
        "get_phonetic_candidates": "self._get_phonetic_candidates",
    }


def test_the_injected_state_is_keyword_only():
    """So the positional contract is the one the method always had.

    A call site passing two positionals cannot accidentally bind a collaborator,
    and the AST gate compares the same positional signature on both sides.
    """
    import inspect
    params = inspect.signature(task_narration.friendly_task_desc).parameters
    positional = [n for n, p in params.items() if p.kind is not p.KEYWORD_ONLY]
    kwonly = sorted(n for n, p in params.items() if p.kind is p.KEYWORD_ONLY)
    assert positional == ["text", "is_hinglish"]
    assert kwonly == ["active_presentation_topic", "get_phonetic_candidates", "router"]
    assert [a.arg for a in _jarvis_method("_get_friendly_task_desc").args.args] == \
        ["self", "text", "is_hinglish"]


def _calls_in(name):
    """Every call in a JARVIS method, as `callee(args)` source strings."""
    return [ast.unparse(n) for n in ast.walk(_jarvis_method(name))
            if isinstance(n, ast.Call)]


def test_process_command_asks_this_module_for_all_three():
    calls = _calls_in("process_command")
    assert "task_narration.plan_announcement(descs, is_hinglish)" in calls
    assert "task_narration.is_immediate_action(cmd_clean)" in calls
    assert "task_narration.task_transition(descs[idx], is_hinglish)" in calls


def test_process_command_no_longer_phrases_anything_itself():
    """The sentences left main.py; nothing should grow a second copy there.

    Checked as source text rather than by call graph, because a duplicate would
    most likely appear as a literal f-string the way the original did.

    Each fragment has to be unique to these sentences. "Right away, sir" is not
    and so is not listed: main.py speaks exactly that as a standalone
    acknowledgement when it resolves an ambiguous command, which has nothing to
    do with announcing a chain.
    """
    with io.open(MAIN_PY, encoding="utf-8") as fh:
        main_src = fh.read()
    for fragment in ("First, I will", "I have a chain of", "Now, I am going to",
                     "pehle main", "uske baad", "tasks ki list hai", "Chaliye sir"):
        assert fragment not in main_src, f"{fragment!r} is being phrased in main.py again"


def test_the_orb_and_the_speaking_stayed_in_main():
    """The move took the phrasing and left the side effects behind."""
    calls = _calls_in("process_command")
    assert calls.count("self.orb.set_state('speaking')") == 2
    assert calls.count("self.orb.set_state('idle')") == 2
    assert "self.tts.speak(plan_intro)" in calls
    assert "self.tts.speak(task_narration.task_transition(descs[idx], is_hinglish))" in calls
