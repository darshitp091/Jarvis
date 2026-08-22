"""Headless tests for the agent swarm.

These never touch a microphone, camera, GPU, or network. A FakeJarvis stands in
for the orchestrator, so every agent can be exercised in milliseconds.

The most valuable test here is test_every_router_skill_has_a_handler, which is
the regression guard for the class of bug that left reminders and calendar
silently unreachable: the router emitted a skill name that main.py never handled,
so the command fell through to the chat LLM and looked like it worked.
"""

import ast
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jarvis.core.agency import Agency, AgentNotFound, Message
from jarvis.core.agents import CalendarAgent, FileManagerAgent, ReminderAgent, SwarmAgent
from jarvis.services.calendar_service import CalendarService
from jarvis.services.db import Database, utc_now
from jarvis.services.scheduler import Scheduler

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# -- fixtures ------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    database = Database(str(tmp_path / "test.db"))
    yield database
    database.close()


class FakeJarvis:
    """Minimal stand-in for the JARVIS orchestrator.

    Real service objects for db/scheduler/calendar so time logic is genuinely
    exercised; MagicMock for every hardware-backed skill.
    """

    def __init__(self, db=None, scheduler=None, calendar=None):
        self.db = db
        self.scheduler = scheduler
        self.calendar = calendar
        for attr in (
            "audio", "tts", "wake", "router", "brain", "sentinel", "profile_mgr",
            "camera", "vision", "os_ctrl", "web", "media", "app_map", "app_ctrl",
            "spotify_ctrl", "youtube_music", "obsidian_ctrl", "shopping",
            "macro_recorder", "market_analyzer", "gesture_ctrl", "workspace_context",
            "self_healing", "healer", "phone", "file_manager", "data_analyzer",
            "productivity", "image_editor", "security_auditor", "vision_tracker",
            "code_runner", "product_comparator", "food_comparator", "coding_sandbox",
            "compiler_repair", "sentiment_tracker", "network_mapper", "cad_gen",
            "sensory_health", "p2p_link", "air_typist", "voice_auth", "git_sentinel",
            "sentry_firewall", "focus_tracker", "proactive_monitor",
            "polyglot_engineer", "research_prodigy", "emergency_sentinel",
        ):
            setattr(self, attr, MagicMock())
        self.domains = {
            key: MagicMock() for key in
            ("medical", "business", "finance", "security", "development",
             "science", "engineering")
        }


@pytest.fixture
def jarvis(db):
    calendar = CalendarService(db, timezone_name="UTC")
    scheduler = Scheduler(db, poll_interval=1, misfire_grace_minutes=120)
    return FakeJarvis(db=db, scheduler=scheduler, calendar=calendar)


@pytest.fixture
def reminder_agent(jarvis):
    return ReminderAgent("ReminderAgent", jarvis)


@pytest.fixture
def calendar_agent(jarvis):
    return CalendarAgent("CalendarAgent", jarvis)


def msg(action, params=None, **content):
    payload = {"params": params or {}}
    payload.update(content)
    return Message("test", "TargetAgent", action, payload)


# -- agency broker -------------------------------------------------------

def test_request_returns_the_agents_value():
    class Echo(SwarmAgent):
        def receive_message(self, m):
            return f"echo:{m.get('text')}"

    agency = Agency(max_workers=2)
    agency.register_agent("Echo", Echo("Echo", None))
    assert agency.request("Echo", "say", {"text": "hi"}) == "echo:hi"


def test_request_on_unknown_agent_raises():
    agency = Agency(max_workers=2)
    with pytest.raises(AgentNotFound):
        agency.request("Nope", "act", {})


def test_request_propagates_exceptions_for_self_healing():
    """main.py's retry/self-healing loop needs the real traceback, not a swallow."""
    class Boom(SwarmAgent):
        def receive_message(self, m):
            raise ValueError("kaboom")

    agency = Agency(max_workers=2)
    agency.register_agent("Boom", Boom("Boom", None))
    with pytest.raises(ValueError, match="kaboom"):
        agency.request("Boom", "act", {})


def test_background_send_message_swallows_failures():
    """A failing background agent must never take down its caller."""
    class Boom(SwarmAgent):
        def receive_message(self, m):
            raise ValueError("kaboom")

    agency = Agency(max_workers=2)
    agency.register_agent("Boom", Boom("Boom", None))
    future = agency.send_message("test", "Boom", "act", {})
    assert future.result(timeout=5) is None


def test_request_runs_inline_on_the_calling_thread():
    """Qt widgets are touched inside handlers, so they must not hop threads."""
    import threading
    seen = {}

    class Probe(SwarmAgent):
        def receive_message(self, m):
            seen["thread"] = threading.current_thread().name
            return "ok"

    agency = Agency(max_workers=2)
    agency.register_agent("Probe", Probe("Probe", None))
    agency.request("Probe", "act", {})
    assert seen["thread"] == threading.current_thread().name


def test_base_agent_rejects_unimplemented_actions():
    agency = Agency(max_workers=2)
    from jarvis.core.agency import Agent
    agency.register_agent("Bare", Agent("Bare"))
    with pytest.raises(NotImplementedError):
        agency.request("Bare", "anything", {})


# -- reminders -----------------------------------------------------------

def test_create_reminder_persists_a_job(reminder_agent, jarvis):
    reply = reminder_agent.receive_message(
        msg("create", {"action": "create", "kind": "reminder",
                       "query": "remind me to call mom in 30 minutes"})
    )
    jobs = jarvis.scheduler.pending_jobs("reminder")
    assert len(jobs) == 1
    assert "call mom" in jobs[0]["payload"]["text"]
    assert "call mom" in reply


def test_create_alarm_uses_alarm_kind(reminder_agent, jarvis):
    reminder_agent.receive_message(
        msg("create", {"action": "create", "kind": "alarm",
                       "query": "set an alarm for 7 am"})
    )
    assert len(jarvis.scheduler.pending_jobs("alarm")) == 1


def test_reminder_without_a_time_asks_instead_of_guessing(reminder_agent, jarvis):
    reply = reminder_agent.receive_message(
        msg("create", {"action": "create", "kind": "reminder",
                       "query": "remind me to call mom"})
    )
    assert jarvis.scheduler.pending_jobs() == []
    assert "when" in reply.lower()


def test_recurring_reminder_keeps_its_recurrence(reminder_agent, jarvis):
    reminder_agent.receive_message(
        msg("create", {"action": "create", "kind": "reminder",
                       "query": "remind me to stretch every day at 5 pm"})
    )
    jobs = jarvis.scheduler.pending_jobs("reminder")
    assert jobs[0]["recurrence"] == "daily"


def test_list_reminders_reports_pending(reminder_agent, jarvis):
    reminder_agent.receive_message(
        msg("create", {"action": "create", "kind": "reminder",
                       "query": "remind me to submit taxes in 2 hours"})
    )
    reply = reminder_agent.receive_message(msg("list", {"action": "list"}))
    assert "submit taxes" in reply


def test_list_with_nothing_pending(reminder_agent):
    reply = reminder_agent.receive_message(msg("list", {"action": "list"}))
    assert "no pending" in reply.lower()


def test_cancel_single_pending_reminder_needs_no_number(reminder_agent, jarvis):
    reminder_agent.receive_message(
        msg("create", {"action": "create", "query": "remind me to eat in 1 hour"})
    )
    reply = reminder_agent.receive_message(msg("cancel", {"action": "cancel", "job_id": None}))
    assert jarvis.scheduler.pending_jobs() == []
    assert "cancel" in reply.lower()


def test_cancel_is_ambiguous_with_several_pending(reminder_agent, jarvis):
    for q in ("remind me to a in 1 hour", "remind me to b in 2 hours"):
        reminder_agent.receive_message(msg("create", {"action": "create", "query": q}))
    reply = reminder_agent.receive_message(msg("cancel", {"action": "cancel", "job_id": None}))
    # Refuses to guess which one, and leaves both intact.
    assert len(jarvis.scheduler.pending_jobs()) == 2
    assert "which" in reply.lower()


def test_cancel_all_clears_everything(reminder_agent, jarvis):
    for q in ("remind me to a in 1 hour", "remind me to b in 2 hours"):
        reminder_agent.receive_message(msg("create", {"action": "create", "query": q}))
    reminder_agent.receive_message(msg("cancel", {"action": "cancel", "all": True}))
    assert jarvis.scheduler.pending_jobs() == []


def test_snooze_pushes_the_job_later(reminder_agent, jarvis):
    """Snooze sets an absolute time relative to now, so assert that contract.

    Comparing against the pre-snooze value would only hold when the fixture
    timezone matches the machine's local clock, which is not guaranteed.
    """
    from jarvis.services.db import from_iso

    reminder_agent.receive_message(
        msg("create", {"action": "create", "query": "remind me to stand in 5 minutes"})
    )
    original = jarvis.scheduler.pending_jobs()[0]["next_run_utc"]
    reminder_agent.receive_message(msg("snooze", {"action": "snooze", "minutes": 15}))
    after = jarvis.scheduler.pending_jobs()[0]["next_run_utc"]

    assert after != original
    delta = from_iso(after) - utc_now()
    assert timedelta(minutes=14) < delta < timedelta(minutes=16)


def test_reminder_agent_degrades_when_scheduler_offline():
    agent = ReminderAgent("ReminderAgent", FakeJarvis())
    reply = agent.receive_message(msg("list", {"action": "list"}))
    assert "offline" in reply.lower()


def test_unknown_reminder_action_is_reported(reminder_agent):
    reply = reminder_agent.receive_message(msg("teleport", {"action": "teleport"}))
    assert "do not yet support" in reply


# -- calendar ------------------------------------------------------------

def test_agenda_when_calendar_is_empty(calendar_agent):
    reply = calendar_agent.receive_message(msg("agenda", {"action": "agenda", "day": "today"}))
    assert "clear" in reply.lower()


def test_agenda_lists_todays_event(calendar_agent, jarvis):
    start = jarvis.calendar.to_local(utc_now()).replace(hour=14, minute=0, second=0, microsecond=0)
    jarvis.calendar.add_event("Standup", start.replace(tzinfo=None))
    reply = calendar_agent.receive_message(msg("agenda", {"action": "agenda", "day": "today"}))
    assert "Standup" in reply


def test_next_event_when_nothing_scheduled(calendar_agent):
    reply = calendar_agent.receive_message(msg("next_event", {"action": "next_event"}))
    assert "nothing else" in reply.lower()


def test_next_event_reports_the_upcoming_item(calendar_agent, jarvis):
    future = (jarvis.calendar.to_local(utc_now()) + timedelta(days=1)).replace(tzinfo=None)
    jarvis.calendar.add_event("Dentist", future)
    reply = calendar_agent.receive_message(msg("next_event", {"action": "next_event"}))
    assert "Dentist" in reply


def test_no_conflicts_on_an_empty_calendar(calendar_agent):
    reply = calendar_agent.receive_message(msg("conflicts", {"action": "conflicts"}))
    assert "no scheduling conflicts" in reply.lower()


def test_overlapping_events_are_reported_as_a_clash(calendar_agent, jarvis):
    base = (jarvis.calendar.to_local(utc_now()) + timedelta(days=1)).replace(
        hour=10, minute=0, second=0, microsecond=0, tzinfo=None
    )
    jarvis.calendar.add_event("Call A", base, base + timedelta(hours=2))
    jarvis.calendar.add_event("Call B", base + timedelta(minutes=30), base + timedelta(hours=3))
    reply = calendar_agent.receive_message(msg("conflicts", {"action": "conflicts"}))
    assert "Call A" in reply and "Call B" in reply


def test_add_event_creates_a_calendar_row(calendar_agent, jarvis):
    reply = calendar_agent.receive_message(
        msg("add_event", {"action": "add_event",
                          "query": "schedule a meeting with Roshan tomorrow at 4 pm"})
    )
    rows = jarvis.db.query("SELECT * FROM calendar_events")
    assert len(rows) == 1
    # The scheduling verb is stripped from the stored title.
    assert not rows[0]["title"].lower().startswith("schedule")
    # timeparse lowercases during normalization, so compare case-insensitively.
    assert "roshan" in reply.lower()


def test_alarm_subject_drops_dangling_prepositions(reminder_agent, jarvis):
    """'set an alarm for 7 am' left timeparse with the bare word 'for'."""
    reply = reminder_agent.receive_message(
        msg("create", {"action": "create", "kind": "alarm", "query": "set an alarm for 7 am"})
    )
    text = jarvis.scheduler.pending_jobs("alarm")[0]["payload"]["text"]
    assert text == "your alarm"
    assert " for." not in reply


def test_reminder_subject_survives_cleanup(reminder_agent, jarvis):
    """Cleanup must not eat a legitimate subject."""
    reminder_agent.receive_message(
        msg("create", {"action": "create", "query": "remind me to call mom at 6 pm"})
    )
    assert jarvis.scheduler.pending_jobs()[0]["payload"]["text"] == "call mom"


def test_add_event_without_a_time_asks_for_one(calendar_agent, jarvis):
    reply = calendar_agent.receive_message(
        msg("add_event", {"action": "add_event", "query": "schedule a meeting with Roshan"})
    )
    assert jarvis.db.query("SELECT * FROM calendar_events") == []
    assert "need a time" in reply.lower()


def test_free_slots_reports_windows(calendar_agent):
    reply = calendar_agent.receive_message(
        msg("free_slots", {"action": "free_slots", "query": "am i free for 60 minutes tomorrow"})
    )
    assert "free" in reply.lower()


def test_export_ics_writes_a_file(calendar_agent, jarvis, tmp_path):
    target = tmp_path / "out.ics"
    calendar_agent.receive_message(
        msg("export_ics", {"action": "export_ics", "path": str(target)})
    )
    assert target.exists()


def test_import_ics_without_a_path_asks(calendar_agent):
    reply = calendar_agent.receive_message(msg("import_ics", {"action": "import_ics"}))
    assert "path" in reply.lower()


def test_calendar_agent_degrades_when_offline():
    agent = CalendarAgent("CalendarAgent", FakeJarvis())
    reply = agent.receive_message(msg("agenda", {"action": "agenda"}))
    assert "offline" in reply.lower()


# -- skill agent delegation ---------------------------------------------

def test_file_manager_agent_delegates_to_the_skill(jarvis):
    agent = FileManagerAgent("FileManagerAgent", jarvis)
    jarvis.file_manager.create_file.return_value = "created"
    result = agent.receive_message(
        msg("create_file", {"action": "create_file", "path": "a.txt", "content": "hi"})
    )
    jarvis.file_manager.create_file.assert_called_once_with("a.txt", "hi")
    assert result == "created"


def test_file_manager_purge_can_also_empty_the_bin(jarvis):
    agent = FileManagerAgent("FileManagerAgent", jarvis)
    jarvis.file_manager.purge_folder_contents.return_value = "purged."
    jarvis.os_ctrl.empty_recycle_bin.return_value = "bin emptied."
    result = agent.receive_message(
        msg("purge_folder", {"action": "purge_folder", "target": "Downloads",
                             "also_empty_bin": True})
    )
    jarvis.os_ctrl.empty_recycle_bin.assert_called_once()
    assert "purged." in result and "bin emptied." in result


def test_unsupported_file_action_is_rejected(jarvis):
    agent = FileManagerAgent("FileManagerAgent", jarvis)
    result = agent.receive_message(msg("levitate", {"action": "levitate"}))
    assert "not supported" in result.lower()


# -- name-based dispatch guards ------------------------------------------

def test_name_dispatch_calls_the_matching_method(jarvis):
    from jarvis.core.agents import PhoneControllerAgent

    agent = PhoneControllerAgent("PhoneControllerAgent", jarvis)

    def flashlight(state=False):
        return f"flashlight={state}"

    jarvis.phone.flashlight = flashlight
    result = agent.receive_message(msg("flashlight", {"action": "flashlight", "state": True}))
    assert result == "flashlight=True"


def test_name_dispatch_drops_params_the_method_does_not_accept(jarvis):
    """A stray router key must not raise TypeError inside the skill."""
    from jarvis.core.agents import PhoneControllerAgent

    agent = PhoneControllerAgent("PhoneControllerAgent", jarvis)

    def battery():
        return "battery 80%"

    jarvis.phone.battery = battery
    result = agent.receive_message(
        msg("battery", {"action": "battery", "unexpected_key": "junk"})
    )
    assert result == "battery 80%"


def test_name_dispatch_refuses_private_attributes(jarvis):
    from jarvis.core.agents import PhoneControllerAgent

    agent = PhoneControllerAgent("PhoneControllerAgent", jarvis)
    result = agent.receive_message(msg("_secret", {"action": "_secret"}))
    assert "do not yet support" in result


def test_name_dispatch_rejects_non_callable_attributes(jarvis):
    from jarvis.core.agents import ImageEditorAgent

    agent = ImageEditorAgent("ImageEditorAgent", jarvis)
    jarvis.image_editor.some_value = "not a function"
    result = agent.receive_message(msg("some_value", {"action": "some_value"}))
    assert "do not yet support" in result


def test_domain_agent_reads_from_the_domains_dict(jarvis):
    from jarvis.core.agents import MedicalDomainAgent

    agent = MedicalDomainAgent("MedicalDomainAgent", jarvis)
    jarvis.domains["medical"].answer.return_value = "medical answer"
    result = agent.receive_message(msg("ask", {}, text="what is a fever"))
    assert result == "medical answer"
    jarvis.domains["medical"].answer.assert_called_once()


def test_every_registered_agent_has_a_concrete_handler():
    """No agent may inherit the base NotImplementedError handler."""
    import jarvis.core.agents as agents_module
    from jarvis.core.agency import Agent

    src = open(os.path.join(PROJECT_ROOT, "main.py"), encoding="utf-8").read()
    match = re.search(r"for agent_cls in \((.*?)\n        \):", src, re.S)
    assert match, "could not locate the agent registration loop in main.py"
    body = re.sub(r"#[^\n]*", "", match.group(1))
    names = [n.strip() for n in body.replace("\n", " ").split(",")]
    names = [n for n in names if re.fullmatch(r"[A-Z][A-Za-z0-9_]*", n)]

    assert len(names) >= 50, f"expected the full swarm, found {len(names)}"

    missing = [n for n in names if not hasattr(agents_module, n)]
    assert not missing, f"registered but absent from core.agents: {missing}"

    inert = [n for n in names
             if getattr(agents_module, n).receive_message is Agent.receive_message]
    assert not inert, f"agents still using the inert base handler: {inert}"


# -- the regression guard ----------------------------------------------

def _router_skills() -> set:
    src = open(os.path.join(PROJECT_ROOT, "src", "jarvis", "core", "intent_router.py"), encoding="utf-8").read()
    return set(re.findall(r"""["']skill["']\s*:\s*["']([a-z_0-9]+)["']""", src))


def _dispatched_skills() -> set:
    src = open(os.path.join(PROJECT_ROOT, "main.py"), encoding="utf-8").read()
    return set(re.findall(r"""skill\s*==\s*["']([a-z_0-9]+)["']""", src))


# `conversation` is the router's own fallback, and the dispatch chain's final
# `else` is its handler: `response = self._generate_response(text, domain)`.
# Falling through to the chat LLM is the intended outcome for it, not the
# failure this guard hunts -- so it is excluded here by name rather than by
# accident, and test_the_conversation_fallthrough_is_still_there proves the
# `else` it relies on has not been removed.
#
# It was excluded by accident until the Phase 3b move of _get_friendly_task_desc
# out of main.py. That method compared `skill == "conversation"` to decide
# whether to retry routing on a mishearing -- never a dispatch, but enough for
# the regex above to see one. The move took the string with it and the guard
# failed, which is the only reason anybody found out.
FALLS_THROUGH_BY_DESIGN = frozenset({"conversation"})


def _skill_dispatch_else():
    """The `else` block of main.py's if/elif chain over `skill`, as source.

    Found through the AST rather than by line number so it survives the file
    shrinking. Two chains test `skill ==` -- the `ambiguous` clarification guard
    and the dispatcher -- and only the dispatcher has a terminal `else`, so
    "the chain with an else" identifies it without hard-coding a skill name.
    """
    with open(os.path.join(PROJECT_ROOT, "main.py"), encoding="utf-8") as fh:
        tree = ast.parse(fh.read())

    def tests_skill(node):
        t = getattr(node, "test", None)
        return (isinstance(node, ast.If) and isinstance(t, ast.Compare)
                and isinstance(t.left, ast.Name) and t.left.id == "skill"
                and len(t.ops) == 1 and isinstance(t.ops[0], ast.Eq))

    chains = []
    for node in ast.walk(tree):
        if not tests_skill(node):
            continue
        links = 1
        while len(node.orelse) == 1 and tests_skill(node.orelse[0]):
            node = node.orelse[0]
            links += 1
        if node.orelse:                      # a terminal else, not another elif
            chains.append((links, node.orelse))

    # Walking finds every link, and each one looks like a chain head from
    # inside; only the true head reports the full length.
    assert chains, "main.py has no if/elif chain over `skill` with a final else"
    links, orelse = max(chains)
    assert links >= 35, (
        "the dispatch chain this helper found has only %d branches, so it is "
        "probably not the dispatcher; point it at the new one" % links
    )
    return "\n".join(ast.unparse(stmt) for stmt in orelse)


def test_the_conversation_fallthrough_is_still_there():
    """What FALLS_THROUGH_BY_DESIGN is worth, and nothing more.

    Excluding a skill from the handler guard is only honest while the thing it
    falls through to still exists. Delete the chain's final `else` and every
    unrecognised skill starts returning the empty `response` initialised above
    the retry loop -- silence, which is exactly the failure mode the guard was
    written for.
    """
    assert "self._generate_response(text, domain)" in _skill_dispatch_else()


def test_source_scanning_guards_are_not_vacuous():
    """Both helpers below scrape source with a regex, and
    test_every_router_skill_has_a_handler asserts on
    `_router_skills() - _dispatched_skills()`.

    Set subtraction is not symmetric, so only one side can fail silently:

    * `_router_skills()` returning empty makes the guard VACUOUS. `set() - x`
      is empty for any x, so the assertion passes while checking nothing.
      Verified by making the router pattern unmatchable: the handler guard
      reported `1 passed` with zero skills examined.
    * `_dispatched_skills()` returning empty fails LOUDLY -- the difference
      becomes all 42 router skills. Also verified. This side needs no guard,
      but is floored anyway so the pair cannot drift apart unnoticed.

    A moved file raises FileNotFoundError, which is loud. The quiet failure is
    a pattern that no longer matches: Phase 3 rewriting the router's
    `{"skill": "x"}` dict literals into anything else -- a dataclass, an enum,
    a registry lookup -- empties the left-hand set with the file still present
    and readable.

    Floors are well under the measured counts (42 router, 42 dispatched) so
    ordinary edits do not trip them. `conversation` is in the router count and
    not the dispatched one; see FALLS_THROUGH_BY_DESIGN.
    """
    router = _router_skills()
    dispatched = _dispatched_skills()

    assert len(router) >= 35, (
        f"_router_skills() found only {len(router)} skills ({sorted(router)}). "
        "The regex has stopped matching the router source -- fix the pattern or "
        "the path before trusting any guard built on it."
    )
    assert len(dispatched) >= 35, (
        f"_dispatched_skills() found only {len(dispatched)} skills "
        f"({sorted(dispatched)}). The dispatch chain has moved out of the file "
        "this helper reads; point it at the new location."
    )


def test_every_router_skill_has_a_handler():
    """No intent may fall through to the chat LLM and pretend it succeeded.

    This is the guard for the original defect: intent_router returned
    skill="reminder"/"calendar" but main.py had no branch for either, so
    "remind me to call mom at 6pm" produced a friendly reply and no reminder.
    """
    unhandled = sorted(_router_skills() - _dispatched_skills() - FALLS_THROUGH_BY_DESIGN)
    assert not unhandled, (
        "intent_router emits these skills but main.py never dispatches them, "
        f"so they silently fall through to conversation: {unhandled}"
    )


def test_reminder_and_calendar_are_explicitly_dispatched():
    dispatched = _dispatched_skills()
    assert "reminder" in dispatched
    assert "calendar" in dispatched


def test_router_sends_event_creation_to_add_event_not_agenda():
    """Guards the rule-ordering bug found end to end.

    "schedule a meeting ... tomorrow at 4 pm" contains both a creation verb and a
    day word. The agenda rule used to match first, so JARVIS read the calendar
    back instead of creating the event, and nothing was ever saved.
    """
    src = open(os.path.join(PROJECT_ROOT, "src", "jarvis", "core", "intent_router.py"), encoding="utf-8").read()

    add_event_at = src.find('"action": "add_event"')
    agenda_at = src.find('"action": "agenda"')
    assert add_event_at != -1 and agenda_at != -1
    assert add_event_at < agenda_at, (
        "the add_event rule must be evaluated before the agenda rule, otherwise "
        "'schedule a meeting tomorrow' is treated as an agenda query"
    )
    # The agenda rule must also actively refuse creation verbs.
    assert "not creates_event" in src


def test_registered_agent_names_match_class_names():
    """Agency keys are derived from __name__, so a rename cannot desync them."""
    src = open(os.path.join(PROJECT_ROOT, "main.py"), encoding="utf-8").read()
    assert "agent_cls.__name__" in src


def test_agents_module_has_no_logging_only_handlers():
    """Guards against agents regressing back into inert log-only stubs."""
    import ast

    path = os.path.join(PROJECT_ROOT, "src", "jarvis", "core", "agents.py")
    tree = ast.parse(open(path, encoding="utf-8").read())
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name != "receive_message":
            continue
        body = [
            s for s in node.body
            if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))
        ]
        if len(body) == 1 and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Call):
            func = body[0].value.func
            if getattr(func, "attr", getattr(func, "id", "")) in ("debug", "info", "warning"):
                offenders.append(node.lineno)
    assert not offenders, f"log-only receive_message handlers at lines {offenders}"
