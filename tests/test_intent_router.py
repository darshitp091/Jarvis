"""Characterization tests for IntentRouter._regex_route.

These do not assert what the router *should* do. They record what it *does*,
today, so the Phase 3 split of the 1,439-line _regex_route into ordered rule
modules can be proven behavior-preserving. Every expected value here was
captured by executing the current router, not reasoned out.

They must pass UNCHANGED after the refactor. If a value here needs updating to
make the refactor pass, the refactor changed behavior -- that is the finding,
not a test to edit.

Two cases are marked KNOWN GAP: real Hinglish word-order defects that return
None and fall through to the LLM router. They are pinned as-is deliberately.
Fixing them belongs in its own test-paired commit, not mixed into the baseline
the refactor is measured against.
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.intent_router import IntentRouter


@pytest.fixture
def router():
    """An IntentRouter with __init__ skipped.

    _regex_route reads no instance attributes -- scanning its body for `self.`
    returns zero hits -- so it needs no constructed state. Skipping __init__
    also avoids reading config/settings.yaml, which is gitignored and therefore
    absent in CI. If _regex_route ever starts reading self state, these tests
    fail with AttributeError, which is the correct loud signal.
    """
    return IntentRouter.__new__(IntentRouter)


# --------------------------------------------------------------- purity guard

def test_regex_route_reads_no_instance_state():
    """Guards the __new__ fixture above, and a property Phase 3 depends on.

    Because _regex_route is state-free it can become a module-level function in
    routing/, with no mixin and no `self` threading. If a `self.` reference is
    introduced here, both the fixture and that plan assumption break.
    """
    src = open(
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "core", "intent_router.py"),
        encoding="utf-8",
    ).read()

    body = src[src.index("def _regex_route"):src.index("def route(")]
    hits = [ln.strip() for ln in body.splitlines() if re.search(r"\bself\.", ln)]
    assert not hits, (
        "_regex_route now reads instance state, so it is no longer a pure "
        f"function of its arguments: {hits[:5]}"
    )


# ------------------------------------------------------- skill/action mapping

# (command, expected_skill, expected_action)
ROUTES = [
    # Browser opening. Checked before everything else in the chain.
    ("open chrome and search for python tutorials", "os_control", "open_browser"),
    ("browser me laptop dikhao",                    "os_control", "open_browser"),

    # Reminders. Cancel and list precede create, so a cancel phrase containing
    # "reminder" is not mistaken for a new reminder.
    ("cancel reminder number 3",      "reminder", "cancel"),
    ("snooze for 15 minutes",         "reminder", "snooze"),
    ("snooze",                        "reminder", "snooze"),
    ("what are my reminders",         "reminder", "list"),
    ("remind me to call mom at 6 pm", "reminder", "create"),
    ("wake me up at 7 am",            "reminder", "create"),

    # Calendar. add_event precedes agenda; see the dedicated test below.
    ("schedule a meeting with Roshan tomorrow at 4 pm", "calendar", "add_event"),
    ("what's on my agenda today",                       "calendar", "agenda"),
    ("next meeting kab hai",                            "calendar", "next_event"),
    ("am i free tomorrow afternoon",                     "calendar", "free_slots"),

    # Notes. Must come after the reminder rules: "remember" is a note trigger
    # and "remind me" would otherwise be swallowed by it.
    ("remember this: wifi password is hunter2", "obsidian", "create_note"),
]


@pytest.mark.parametrize("cmd,skill,action", ROUTES, ids=[r[0] for r in ROUTES])
def test_route_maps_to_expected_skill_and_action(router, cmd, skill, action):
    out = router._regex_route(cmd)
    assert out is not None, f"{cmd!r} no longer matches any rule"
    assert out["skill"] == skill
    assert out["params"]["action"] == action
    assert out["domain"] == "general"


# ------------------------------------------------- exact params, order-critical

def test_cancel_extracts_the_job_number(router):
    assert router._regex_route("cancel reminder number 3") == {
        "skill": "reminder",
        "params": {"action": "cancel", "job_id": 3, "all": False},
        "domain": "general",
    }


def test_snooze_defaults_to_ten_minutes_when_unspecified(router):
    assert router._regex_route("snooze")["params"]["minutes"] == 10
    assert router._regex_route("snooze for 15 minutes")["params"]["minutes"] == 15


def test_alarm_and_reminder_are_distinguished_by_kind(router):
    assert router._regex_route("wake me up at 7 am")["params"]["kind"] == "alarm"
    assert router._regex_route("remind me to call mom at 6 pm")["params"]["kind"] == "reminder"


def test_create_passes_the_original_text_not_the_normalised_command(router):
    """Downstream time parsing needs the raw text; _regex_route lowercases and
    strips punctuation into `cmd` but must hand `text` over untouched."""
    out = router._regex_route("Remind me to call Mom at 6 PM.")
    assert out["params"]["query"] == "Remind me to call Mom at 6 PM."


def test_event_creation_beats_the_agenda_rule(router):
    """The end-to-end defect this ordering exists to prevent.

    "schedule a meeting ... tomorrow at 4 pm" contains both a creation verb and
    a day word. When the agenda rule matched first, JARVIS read the calendar
    back instead of creating the event and nothing was ever saved.

    tests/test_agents.py checks this by comparing source positions. This checks
    the behavior, so it survives Phase 3 moving the rules into separate files.
    """
    out = router._regex_route("schedule a meeting with Roshan tomorrow at 4 pm")
    assert out["params"]["action"] == "add_event"


def test_agenda_resolves_the_day_word(router):
    assert router._regex_route("what's on my agenda today")["params"]["day"] == "today"
    assert router._regex_route("agenda for tomorrow")["params"]["day"] == "tomorrow"


def test_note_capture_strips_the_trigger_phrase(router):
    out = router._regex_route("remember this: wifi password is hunter2")
    assert out["params"]["content"] == "wifi password is hunter2"


def test_browser_query_has_the_command_words_removed(router):
    """Pinned verbatim, double space included. The stripping regexes leave
    whitespace artifacts; that is current behavior and the search still works.
    Phase 3 must not quietly 'tidy' this -- if the output changes, the rule
    changed."""
    out = router._regex_route("open chrome and search for python tutorials")
    assert out["params"]["query"] == "and  for python tutorials"


def test_hinglish_browser_command_routes_to_open_browser(router):
    out = router._regex_route("browser me laptop dikhao")
    assert out["skill"] == "os_control"
    assert out["params"]["query"] == "me laptop"


# ------------------------------------------------------ stateful presentation

def test_presentation_topic_captures_slide_follow_ups(router):
    """With an active topic, a bare "make slide 3 shorter" is a refinement of
    the existing deck rather than a new request."""
    out = router._regex_route("make slide 3 shorter", "quantum entanglement")
    assert out["skill"] == "productivity"
    assert out["params"]["action"] == "modify_presentation_slide"
    assert out["params"]["slide_num"] == 3
    assert out["params"]["query"] == "make slide 3 shorter"


def test_same_text_without_an_active_topic_is_a_new_deck_not_a_slide_edit(router):
    """The state is what makes the refinement rule fire. Without it the same
    text is parsed as a brand-new presentation request -- with a nonsense title
    of "3 shorter", which is current behavior and pinned as such. The point is
    that it must not reach modify_presentation_slide with no deck to modify.
    """
    out = router._regex_route("make slide 3 shorter")
    assert out["skill"] == "productivity"
    assert out["params"]["action"] == "create_presentation"
    assert out["params"]["title"] == "3 shorter"


# ---------------------------------------------------------------- fall-through

def test_general_question_falls_through_to_the_llm(router):
    """Returning None is the contract for "no fast path applies" -- the caller
    then asks the LLM router. A rule that greedily claimed this would break
    ordinary conversation."""
    assert router._regex_route("what is the capital of France") is None


# ------------------------------------------------------------------ KNOWN GAPS

@pytest.mark.parametrize("cmd,why", [
    (
        "sabhi reminders hata do",
        "the cancel rule needs the verb before the noun, and \\breminder\\b "
        "cannot match inside 'reminders'",
    ),
    (
        "mera kal ka schedule batao",
        "the agenda rule needs 'mera' immediately followed by 'schedule', but "
        "Hinglish puts 'kal ka' between them",
    ),
])
def test_known_hinglish_word_order_gaps_return_none(router, cmd, why):
    """KNOWN GAP -- pinned, not endorsed.

    These are real defects: valid Hinglish that should route but does not, so it
    falls through to the LLM router which may or may not recover. They are
    recorded as current behavior because Phase 2 preserves behavior; fixing them
    inside the characterization baseline would destroy the reference the Phase 3
    refactor is measured against.

    Fix each in its own commit, paired with the assertion flipped to the correct
    route. When that happens this test SHOULD fail -- that is the signal the fix
    landed, and this case moves up into ROUTES.
    """
    assert router._regex_route(cmd) is None, (
        f"{cmd!r} now routes -- if that was deliberate, move it into ROUTES with "
        f"its real expected value and drop this case. Gap was: {why}"
    )
