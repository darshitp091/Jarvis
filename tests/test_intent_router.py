"""Characterization tests for IntentRouter._regex_route.

These do not assert what the router *should* do. They record what it *does*,
today, so the Phase 3 split of the 1,439-line _regex_route into ordered rule
modules can be proven behavior-preserving. Every expected value here was
captured by executing the current router, not reasoned out.

They must pass UNCHANGED after the refactor. If a value here needs updating to
make the refactor pass, the refactor changed behavior -- that is the finding,
not a test to edit.

Tests whose name begins `test_known_gap_` record defects, not intentions. Two
are real Hinglish word-order failures that return None and fall through to the
LLM router; the rest were found while fixing neighbouring rules. They are pinned
as-is deliberately, and each says in its docstring what fixing it would look
like. Fixing one belongs in its own test-paired commit, not mixed into the
baseline the refactor is measured against.

Cases that have since been fixed keep their history in a comment or docstring
where they used to live, because the cause is usually more instructive than the
symptom -- "run this python code" opened a YouTube video because "yt" was
matched as a bare substring and hides inside "python".
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jarvis.core.intent_router import IntentRouter


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
                     "src", "jarvis", "core", "intent_router.py"),
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
    ("sabhi reminders hata do",       "reminder", "cancel"),
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

    # --- one row per remaining regex-reachable skill -----------------------
    # Derived from each rule's own keyword lists, then verified by execution.
    # Phrases are terse because that is what the rules match; readability of the
    # phrase matters less than it provably hitting the intended rule.
    ("open swarm lab",        "agent_lab",         "open_lab"),
    ("turn on gaze pointer",  "air_typist",        "start"),
    ("execute code",          "app_control",       "run_code"),
    ("run this python code",  "code_runner",       "run_code"),
    ("solve air canvas",      "coding_sandbox",    "execute_task"),
    ("customization protocol", "customizer",       "enter"),
    ("explorer show hidden",  "file_manager",      "toggle_show_hidden_files"),
    ("order food from swiggy", "food_ordering",    None),
    ("show vitals",           "focus_tracker",     "open_dashboard"),
    ("git sentinel check",    "git_sentinel",      "check"),
    ("explode hologram",      "hologram_control",  "explode"),
    ("pichla hata",           "image_editor",      "remove_background"),
    ("start recording macro", "macro_recorder",    "start"),
    ("suggest buy",           "market_analyzer",   "analyze"),
    ("scan network",          "network_mapper",    "scan_and_project"),
    ("open notepad",          "os_control",        "launch"),
    ("list network devices",  "p2p_link",          "list_peers"),
    ("phone home screen",     "phone",             "go_home"),
    ("port scan",             "security_auditor",  "scan_ports"),
    ("click the",             "self_healing",      "click_element"),
    ("check environment",     "sensory_health",    "check"),
    ("buy shoes on amazon",   "shopping",          "search_product"),
    ("please stop",           "spotify",           "pause"),
    ("diagnostic check",      "system_monitor",    "stark_diagnostics"),
    ("what objects",          "vision_tracker",    "detect_objects"),
    ("check stress level",    "vitals_check",      "check_vitals"),
    ("explain my workspace",  "workspace_context", "explain_workspace"),

    # productivity and web_research are also exercised by dedicated tests below,
    # but they need a ROUTES row too: the accounting test derives its covered
    # set from this table alone, so a skill tested only elsewhere would read as
    # uncharacterized.
    ("make a presentation on physics", "productivity",  "create_presentation"),
    ("summarize this video",           "web_research",  "open_youtube_video"),

    # screen_vision returns no "action" key at all. None means "assert the skill
    # only" -- see the test body.
    ("what can you see",      "screen_vision",     None),
]


@pytest.mark.parametrize("cmd,skill,action", ROUTES, ids=[r[0] for r in ROUTES])
def test_route_maps_to_expected_skill_and_action(router, cmd, skill, action):
    out = router._regex_route(cmd)
    assert out is not None, f"{cmd!r} no longer matches any rule"
    assert out["skill"] == skill
    if action is None:
        # screen_vision emits params with no "action" key. Pinning its absence
        # matters: adding one would change what the dispatcher branches on.
        assert "action" not in out["params"], (
            f"{cmd!r} gained an action param: {out['params']}"
        )
    else:
        assert out["params"]["action"] == action
    assert out["domain"] == "general"


# ------------------------------------------------- exact params, order-critical

def test_cancel_extracts_the_job_number(router):
    assert router._regex_route("cancel reminder number 3") == {
        "skill": "reminder",
        "params": {"action": "cancel", "job_id": 3, "all": False},
        "domain": "general",
    }


def test_cancel_reaches_the_rule_with_the_noun_before_the_verb(router):
    """Hinglish puts the verb last -- "reminders hata do" rather than "cancel the
    reminders" -- so the cancel rule carries a second, noun-first branch. That
    branch listed only the singular nouns, and `\\breminder\\b` cannot match
    inside "reminders", so every plural phrasing fell through to the LLM.
    """
    assert router._regex_route("sabhi reminders hata do") == {
        "skill": "reminder",
        "params": {"action": "cancel", "job_id": None, "all": True},
        "domain": "general",
    }
    # Singular still works, and so does the verb-first English order.
    assert router._regex_route("reminder cancel karo")["params"]["action"] == "cancel"
    assert router._regex_route("delete all reminders")["params"]["all"] is True


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


# All three cases that once filled a `test_known_rule_shadowing` table have been
# fixed, so the table is gone rather than left standing empty. Their causes are
# kept, because each is a distinct mechanism and any rule added to this file can
# reproduce one of them:
#
# - "run this python code" opened a YouTube video. The video intercept tested
#   `"yt" in cmd` as a bare substring, and "yt" hides inside "python",
#   "anything" and "everything". The rule that steals a command is not always
#   the rule that looks related to it.
# - "start recording macro" tried to launch an app named "recording macro". The
#   macro rule demanded a name the phrase does not contain, so it declined and a
#   later, greedier rule took the remains. A rule need not run before yours to
#   shadow it -- it only needs yours to decline.
# - "order food from swiggy" searched Amazon. A generic `order (.+)` rule sat
#   ~750 lines above food_ordering's own "order ..." rule, leaving that rule
#   unreachable dead code. Fixing it promoted a third rule that had been queued
#   behind the same phrase, which is the shape of this whole class: unblocking
#   one rule hands the phrase to the next one in line, not to the right one.
#
# An explicitly ordered rule list is what makes all three visible at a glance,
# which is the substantive win of the Phase 3 split rather than a side effect.


@pytest.mark.parametrize("cmd,why", [
    ("order pizza",
     "no platform is named, and the generic order rule is ~750 lines earlier"),
    ("search biryani on swiggy",
     "swiggy is in the shopping rule's platform list as well as food_ordering's"),
])
def test_known_gap_food_without_a_named_platform_goes_to_shopping(router, cmd, why):
    """KNOWN GAP -- pinned, not endorsed.

    Naming swiggy or zomato now reaches food_ordering, but *food* is not a signal
    the router can read: "order pizza" is indistinguishable from "order shoes" to
    a regex, and the shopping rule comes first. Closing this needs a food lexicon
    or the LLM rather than another ordering tweak, so it is recorded instead of
    patched -- and recorded rather than left silent, because "food_ordering is
    now reachable" is true and would otherwise be mistaken for "food orders now
    work".
    """
    out = router._regex_route(cmd)
    assert out is not None
    assert out["skill"] == "shopping", (
        f"{cmd!r} now routes to {out['skill']} instead of shopping ({why}); if it "
        "reaches food_ordering the gap closed -- move it into ROUTES"
    )


@pytest.mark.parametrize("cmd", [
    "tell me anything about mars",
    "everything is fine",
    "check disk bytes",
    "show me the analytics report",
])
def test_words_merely_containing_yt_are_not_video_requests(router, cmd):
    """Regression guard for the substring that stole unrelated commands.

    The video intercept used to test `"yt" in cmd`, and "yt" is a substring of
    "python", "anything", "everything", "bytes" and "analytics". Every phrase
    here was routed to the YouTube player as a result, which is what made the
    "run this python code" defect a class rather than one bad phrase: none of
    these mentions video at all. Declining them is correct -- they fall through
    to the LLM router, which is what None means here.
    """
    out = router._regex_route(cmd)
    assert out is None or out["params"].get("action") != "open_youtube_video", (
        f"{cmd!r} was claimed by the video intercept as {out}; the trigger has "
        "gone back to matching \"yt\" as a bare substring"
    )


@pytest.mark.parametrize("cmd", [
    "yt pe koi gaana chalao",
    "play video of cats",
    "summarize this video",
])
def test_real_video_requests_still_reach_the_player(router, cmd):
    """The other half of that fix, and the reason it is a fix and not a deletion.

    Narrowing the trigger to a word boundary is only correct if the abbreviation
    people actually type keeps working. Without this test the guard above could
    be satisfied by removing "yt" from the trigger list altogether.
    """
    out = router._regex_route(cmd)
    assert out is not None, f"{cmd!r} no longer matches any rule"
    assert out["skill"] == "web_research"
    assert out["params"].get("action") == "open_youtube_video"


def test_run_code_flags_a_missing_code_payload(router):
    """"run this python code" names a language but supplies nothing to run.

    An empty temp file executes successfully and prints nothing, so routing this
    to run_code unguarded would be a silent no-op -- the same failure shape as
    the dead hologram branch. The router marks the gap and main.py asks for the
    code instead. The flag is pinned in both states because the dispatcher
    branches on it: dropping it restores the no-op with no test noticing.
    """
    missing = router._regex_route("run this python code")
    assert missing["params"]["code_text"] == ""
    assert missing["params"]["needs_code_text"] is True

    supplied = router._regex_route("run python code print(1)")
    assert supplied["params"]["code_text"] == "print(1)"
    assert supplied["params"]["needs_code_text"] is False


def test_known_gap_code_payloads_lose_their_punctuation(router):
    """KNOWN GAP -- pinned, not endorsed. Pre-existing, and wider than run_code.

    _regex_route strips `. , ? ! " '` from the whole command before any rule
    sees it, so a code payload arrives already mangled: console.log becomes
    consolelog. Every rule that captures free text out of `cmd` inherits this,
    which is why it is recorded here rather than patched inside the code_runner
    rule -- the normalization is the defect, and moving it touches every rule at
    once. Until then, dictated code is usable only when it happens to contain no
    punctuation.

    When that normalization is fixed this test SHOULD fail. That is the signal.
    """
    out = router._regex_route("execute js code console.log(2)")
    assert out["skill"] == "code_runner"
    assert out["params"]["code_text"] == "consolelog(2)", (
        "the punctuation strip at the top of _regex_route has changed; if code "
        "payloads now survive intact, delete this test and pin the real value"
    )


@pytest.mark.parametrize("cmd,name", [
    ("start recording macro",        "default_macro"),
    ("recording macro",              "default_macro"),
    ("start macro recording",        "default_macro"),
    ("start recording macro backup", "backup"),
])
def test_macro_recording_starts_with_or_without_a_name(router, cmd, name):
    """Start now agrees with stop about what a nameless macro is called.

    The start rule demanded a name, so the nameless phrasings failed it and fell
    through to the generic app launcher, which cheerfully tried to open an
    application called "recording macro". Stop had defaulted to "default_macro"
    all along, which made the recorder undrivable by voice: the phrase that
    begins a recording and the phrase that ends it disagreed about the name.
    Both defaults are pinned because the pair is only useful if they match.
    """
    out = router._regex_route(cmd)
    assert out is not None, f"{cmd!r} no longer matches any rule"
    assert out["skill"] == "macro_recorder"
    assert out["params"]["action"] == "start"
    assert out["params"]["name"] == name


@pytest.mark.parametrize("cmd,name", [
    ("stop recording macro",        "default_macro"),
    ("stop recording",              "default_macro"),
    ("stop recording macro backup", "backup"),
])
def test_macro_recording_stop_is_unchanged(router, cmd, name):
    """The half that already worked, pinned so the start fix cannot break it.

    The start rule is tested first in the same chain and is anchored at `^`, so
    a phrase beginning with "stop" must never reach it. Loosening the start
    pattern is exactly the kind of change that would.
    """
    out = router._regex_route(cmd)
    assert out is not None
    assert out["skill"] == "macro_recorder"
    assert out["params"]["action"] == "stop"
    assert out["params"]["name"] == name


def test_generic_app_launch_still_works_after_the_macro_fix(router):
    """The launcher that was catching the macro phrase must keep its own job.

    "start recording macro" was reaching os_control because the launcher accepts
    any 1-3 word tail after "start". Narrowing what escapes to it is only
    correct if what legitimately belongs to it still arrives.
    """
    out = router._regex_route("start spotify")
    assert out["skill"] == "os_control"
    assert out["params"]["action"] == "launch"
    assert out["params"]["app"] == "spotify"


def test_known_gap_playing_a_macro_is_claimed_by_spotify(router):
    """KNOWN GAP -- pinned, not endorsed. Found while fixing the start rule.

    `^(?:play|execute|run)\\s+macro\\s+(.+)` sits ~10 lines below the start rule
    but an earlier Spotify rule owns "play", so "play macro backup" starts music
    instead. macro_recorder is out of LLM_ONLY_SKILLS because start reaches it;
    that is not the same as the skill being wholly reachable, and this test
    exists so the difference is written down rather than implied.

    When the Spotify rule stops swallowing it this test SHOULD fail.
    """
    out = router._regex_route("play macro backup")
    assert out is not None
    assert out["skill"] == "spotify", (
        f"'play macro backup' now routes to {out['skill']}; if it reaches "
        "macro_recorder the shadowing was fixed -- move it into ROUTES"
    )


@pytest.mark.parametrize("cmd", [
    "order food from swiggy",
    "order biryani from zomato",
])
def test_orders_naming_a_delivery_platform_reach_food_ordering(router, cmd):
    """A named delivery platform decides which skill owns the phrase.

    swiggy and zomato appeared in the shopping rule's platform list *and* in
    food_ordering's, and the shopping rule ran first, so food_ordering's own
    "order ..." rule was unreachable. Both skills claiming the same platforms is
    the underlying defect; declining them in the generic rule is the fix.
    """
    out = router._regex_route(cmd)
    assert out is not None, f"{cmd!r} no longer matches any rule"
    assert out["skill"] == "food_ordering"


def test_generic_food_search_still_reaches_web_research(router):
    """The rule that surfaced mid-fix must keep the phrasing that is really its.

    `^(?:search|find|order)\\s+food\\s+(.+)` was dead code behind the generic
    order rule. It now declines when a delivery platform is named -- and only
    then, so an ordinary food search is unaffected.
    """
    out = router._regex_route("search food for biryani")
    assert out["skill"] == "web_research"
    assert out["params"]["action"] == "search_food"
    assert out["params"]["query"] == "biryani"


def test_shopping_exclusions_do_not_fire_inside_longer_words(router):
    """"purchase headphones" matched no rule at all before this.

    The shopping rule declines a few non-product categories so later rules can
    claim them, and the list was tested with `in`: "phone" fires inside
    "headphones", so the rule declined, nothing downstream wanted it, and the
    request fell out of the router entirely. Same defect as the "yt" substring,
    in a different rule -- which is why both are pinned rather than just fixed.
    """
    out = router._regex_route("purchase headphones")
    assert out is not None, "'purchase headphones' matches no rule again"
    assert out["skill"] == "shopping"
    assert out["params"]["query"] == "headphones"


@pytest.mark.parametrize("cmd", ["order a new phone", "order tickets"])
def test_non_food_orders_are_not_ordered_as_food(router, cmd):
    """The excluded categories must not simply fall through to food_ordering.

    The shopping rule declines these, and food_ordering's "order ..." rule used
    to accept whatever fell through -- so "order a new phone" was ordered as
    food. Both rules now decline, and returning None is the honest answer: no
    regex here understands the phrase, so the LLM router should see it.
    Plurals are covered because the pre-fix `in` test matched "tickets" through
    "ticket", and a word-boundary rewrite would silently have dropped that.
    """
    assert router._regex_route(cmd) is None, (
        f"{cmd!r} is claimed by a regex rule again: {router._regex_route(cmd)}"
    )


# --------------------------------------------------------- coverage accounting

# Skills that appear in intent_router.py but that _regex_route cannot reach.
# Every phrase derived from their own rule text either returns None or is
# claimed by an earlier rule, so they are reachable only via the LLM router.
#
# This is not a wish list -- it is a measured property of the current rule
# ordering, and it is the reason the table above stops at 33 of 42. Shrinking
# this set is real work with real user-visible value; see the follow-ups table
# in the plan.
#
# A skill leaving this set means one route into it was proven, not that all of
# its actions are reachable: macro_recorder is reached by "start recording
# macro" while "play macro backup" is still taken by Spotify, and food_ordering
# is reached by naming swiggy or zomato while "order pizza" still goes shopping.
# See the two test_known_gap_* cases that pin exactly that difference.
LLM_ONLY_SKILLS = {
    "ambiguous",          # deliberate: the disambiguation branch, not a route
    "conversation",       # deliberate: the explicit fall-through skill
    "data_analyzer",
    "media_summarize",
    "memory_ops",
    "polyglot_engineer",
    "product_comparison",
    "research_prodigy",
    "sentry_firewall",
}


def _skills_in_router_source() -> set:
    src = open(
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "src", "jarvis", "core", "intent_router.py"),
        encoding="utf-8",
    ).read()
    return set(re.findall(r"""["']skill["']\s*:\s*["']([a-z_0-9]+)["']""", src))


def test_every_router_skill_is_covered_or_declared():
    """No skill may be silently uncharacterized going into the Phase 3 split.

    Either a skill has a row in ROUTES proving how it is reached, or it is named
    in LLM_ONLY_SKILLS with the reason. A skill in neither set is one the
    refactor could break with nothing to notice.
    """
    emitted = _skills_in_router_source()
    assert len(emitted) >= 35, (
        f"the source scan found only {len(emitted)} skills -- the regex has "
        "stopped matching, so this accounting proves nothing"
    )

    covered = {row[1] for row in ROUTES}
    unaccounted = sorted(emitted - covered - LLM_ONLY_SKILLS)
    assert not unaccounted, (
        "these skills are neither characterized in ROUTES nor declared in "
        f"LLM_ONLY_SKILLS: {unaccounted}. Add a verified row, or declare it "
        "with the reason it is unreachable."
    )


def test_declared_unreachable_skills_really_are_unreachable(router):
    """Keeps LLM_ONLY_SKILLS honest.

    If a rule change makes one of these reachable, the declaration is stale and
    the skill belongs in ROUTES with a real expected value.
    """
    covered = {row[1] for row in ROUTES}
    overlap = sorted(LLM_ONLY_SKILLS & covered)
    assert not overlap, (
        f"{overlap} are both declared unreachable and characterized in ROUTES; "
        "remove them from LLM_ONLY_SKILLS"
    )
