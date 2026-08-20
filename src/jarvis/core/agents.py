"""Real handlers for the JARVIS agent swarm.

Every agent owns the action logic for one capability and returns the string
JARVIS should speak. `main.py` routes an intent here via `Agency.request(...)`
instead of holding that logic in its own dispatch chain, so each behaviour lives
in exactly one place.

Contract for `receive_message`:
  - return a string when JARVIS should say something
  - return None when the agent handled the message silently
  - raise on genuine failure, so main.py's retry and self-healing loop still sees
    the original traceback
"""

from datetime import datetime, timedelta

from loguru import logger

from jarvis.core.agency import Agent, Message


class SwarmAgent(Agent):
    """Base class for agents that act on the main application orchestrator."""

    def __init__(self, name: str, jarvis, agency=None):
        super().__init__(name, agency)
        self.jarvis = jarvis

    def unsupported(self, msg: Message) -> str:
        """Uniform reply when an action reaches the right agent but has no handler."""
        logger.warning(f"{self.name}: unsupported action '{msg.action}'")
        return f"Sir, I do not yet support the '{msg.action}' action for {self.label}."

    @property
    def label(self) -> str:
        return self.name.replace("Agent", "")


def _dispatch_by_name(agent: "SwarmAgent", target, msg: Message):
    """Call target.<action>(**params) for skills whose methods mirror router actions.

    Deliberately strict: the action must name a public, callable attribute, and
    only keyword arguments that method actually accepts are forwarded. Without
    those guards a router action could reach a private attribute or raise
    TypeError on an unexpected key.
    """
    import inspect

    action = msg.action or ""
    if action.startswith("_"):
        return agent.unsupported(msg)

    handler = getattr(target, action, None)
    if not callable(handler):
        return agent.unsupported(msg)

    params = {k: v for k, v in msg.params.items() if k != "action"}
    try:
        accepted = set(inspect.signature(handler).parameters)
    except (TypeError, ValueError):
        accepted = None

    if accepted is not None:
        params = {k: v for k, v in params.items() if k in accepted}

    return handler(**params)


# ==========================================================================
# 1. Time: reminders, alarms, calendar
# ==========================================================================
class ReminderAgent(SwarmAgent):
    """Voice-driven reminders and alarms backed by the persistent scheduler.

    Times spoken by the user are naive local wall clock; the scheduler stores UTC,
    so every datetime crosses through CalendarService.to_utc before it is saved.
    """

    def receive_message(self, msg: Message):
        if not self.jarvis.scheduler:
            return "Sir, my scheduler is offline, so I cannot manage reminders right now."

        action = msg.action
        params = msg.params

        if action == "create":
            return self._create(params)
        if action == "list":
            return self._list()
        if action == "cancel":
            return self._cancel(params)
        if action == "snooze":
            return self._snooze(params)
        return self.unsupported(msg)

    def _to_utc(self, local_dt: datetime) -> datetime:
        if self.jarvis.calendar:
            return self.jarvis.calendar.to_utc(local_dt)
        return local_dt.astimezone()

    @staticmethod
    def _clean_subject(raw: str, kind: str) -> str:
        """Turn timeparse's leftover text into something worth reading aloud.

        timeparse removes the time phrase but leaves whatever preceded it, so
        "set an alarm for 7 am" reduces to the dangling word "for". Strip the
        setup verbs and trailing prepositions, then fall back to a generic label.
        """
        import re

        subject = (raw or "").strip()
        subject = re.sub(
            r"^\s*(?:please\s+)?(?:set|create|add|put|make|lagao|laga\s*do)\s+"
            r"(?:an?|the|my)?\s*(?:alarm|reminder|timer)?\s*",
            "", subject, flags=re.IGNORECASE,
        )
        subject = re.sub(r"^\s*(?:an?|the|my)\s+", "", subject, flags=re.IGNORECASE)
        # Drop prepositions/connectives left stranded at either end.
        subject = re.sub(r"^\s*(?:for|at|on|to|about|ki|ke|ko|that)\b\s*", "",
                         subject, flags=re.IGNORECASE)
        subject = re.sub(r"\s*\b(?:for|at|on|to|about)\s*$", "",
                         subject, flags=re.IGNORECASE)
        subject = subject.strip(" ,.-:;")

        if not subject:
            return "your alarm" if kind == "alarm" else "your reminder"
        return subject

    def _create(self, params: dict) -> str:
        from jarvis.services import timeparse

        query = params.get("query", "") or ""
        kind = params.get("kind", "reminder")

        parsed = timeparse.parse_when(query)
        if not parsed:
            # No time phrase at all. Asking beats silently inventing a time.
            return (
                "Sir, I did not catch when you want this. "
                "Try something like 'remind me to call mom at 6 pm', or 'in 20 minutes'."
            )

        subject = self._clean_subject(parsed.subject, kind)

        job_id = self.jarvis.scheduler.schedule(
            kind,
            self._to_utc(parsed.run_at),
            {"text": subject},
            recurrence=parsed.recurrence,
            interval_secs=parsed.interval_secs,
        )

        when = timeparse.describe(parsed.run_at, recurrence=parsed.recurrence,
                                  interval_secs=parsed.interval_secs)
        noun = "alarm" if kind == "alarm" else "reminder"
        reply = f"Done sir. {noun.capitalize()} number {job_id} set for {when}: {subject}."
        if parsed.is_vague:
            # The hour was inferred, so say it back and let the user correct it.
            reply += " I assumed that time of day, so tell me if you meant otherwise."
        logger.info(f"ReminderAgent: scheduled {noun} {job_id} at {parsed.run_at} ({subject})")
        return reply

    def _list(self) -> str:
        from jarvis.services import timeparse

        jobs = [j for j in self.jarvis.scheduler.pending_jobs()
                if j["kind"] in ("reminder", "alarm")]
        if not jobs:
            return "You have no pending reminders or alarms, sir."

        lines = [f"You have {len(jobs)} pending item{'s' if len(jobs) != 1 else ''}, sir:"]
        for job in jobs:
            local = self._local(job["next_run_utc"])
            text = (job.get("payload") or {}).get("text", job["kind"])
            lines.append(f"  - Number {job['id']}: {text}, at {timeparse.describe(local)}")
        return "\n".join(lines)

    def _local(self, value) -> datetime:
        """Scheduler rows carry next_run_utc as an ISO string, so parse before converting."""
        from jarvis.services.db import from_iso

        dt = from_iso(value) if isinstance(value, str) else value
        if self.jarvis.calendar:
            return self.jarvis.calendar.to_local(dt).replace(tzinfo=None)
        return dt.replace(tzinfo=None) if dt.tzinfo else dt

    def _cancel(self, params: dict) -> str:
        if params.get("all"):
            jobs = [j for j in self.jarvis.scheduler.pending_jobs()
                    if j["kind"] in ("reminder", "alarm")]
            cancelled = sum(1 for j in jobs if self.jarvis.scheduler.cancel(j["id"]))
            if not cancelled:
                return "There was nothing pending to cancel, sir."
            return f"Cleared all {cancelled} pending reminders and alarms, sir."

        job_id = params.get("job_id")
        if job_id is None:
            # No number spoken: cancelling the only pending item is unambiguous.
            jobs = [j for j in self.jarvis.scheduler.pending_jobs()
                    if j["kind"] in ("reminder", "alarm")]
            if not jobs:
                return "You have no pending reminders to cancel, sir."
            if len(jobs) > 1:
                return (
                    f"You have {len(jobs)} pending reminders, sir. "
                    "Tell me which number to cancel, or say cancel all reminders."
                )
            job_id = jobs[0]["id"]

        if self.jarvis.scheduler.cancel(int(job_id)):
            return f"Reminder number {job_id} is cancelled, sir."
        return f"I could not find an active reminder numbered {job_id}, sir."

    def _snooze(self, params: dict) -> str:
        minutes = int(params.get("minutes", 10) or 10)
        jobs = [j for j in self.jarvis.scheduler.pending_jobs()
                if j["kind"] in ("reminder", "alarm")]
        job_id = params.get("job_id") or (jobs[0]["id"] if jobs else None)
        if job_id is None:
            return "There is no reminder to snooze, sir."

        if self.jarvis.scheduler.snooze(int(job_id), minutes):
            return f"Snoozed, sir. I will remind you again in {minutes} minutes."
        return f"I could not snooze reminder {job_id}, sir."


class CalendarAgent(SwarmAgent):
    """Agenda, conflicts, free slots, and ICS import/export over the local calendar."""

    def receive_message(self, msg: Message):
        if not self.jarvis.calendar:
            return "Sir, my calendar service is offline right now."

        action = msg.action
        params = msg.params
        cal = self.jarvis.calendar

        if action == "agenda":
            day = None
            if params.get("day") == "tomorrow":
                day = (cal.to_local(self._now()) + timedelta(days=1)).date()
            return cal.describe_agenda(day)

        if action == "next_event":
            event = cal.next_event()
            if not event:
                return "You have nothing else on the calendar, sir."
            stamp = event["start_local"].strftime("%A %d %B at %I:%M %p").replace(" 0", " ")
            where = f", at {event['location']}" if event.get("location") else ""
            return f"Your next item is {event['title']}, on {stamp}{where}, sir."

        if action == "conflicts":
            clashes = cal.find_conflicts()
            if not clashes:
                return "No scheduling conflicts in the next 30 days, sir."
            lines = [f"I found {len(clashes)} clash{'es' if len(clashes) != 1 else ''}, sir:"]
            for first, second in clashes:
                stamp = first["start_local"].strftime("%d %b %I:%M %p")
                lines.append(f"  - {first['title']} overlaps {second['title']} around {stamp}")
            return "\n".join(lines)

        if action == "free_slots":
            return self._free_slots(cal, params)

        if action == "add_event":
            return self._add_event(cal, params)

        if action == "import_ics":
            path = params.get("path")
            if not path:
                return "Sir, tell me the path of the calendar file you want me to import."
            return cal.import_ics(path)

        if action == "export_ics":
            path = params.get("path") or "jarvis_calendar.ics"
            return cal.export_ics(path)

        return self.unsupported(msg)

    def _now(self):
        from jarvis.services.db import utc_now
        return utc_now()

    def _free_slots(self, cal, params: dict) -> str:
        import re

        query = params.get("query", "") or ""
        day = cal.to_local(self._now()).date()
        if re.search(r"\b(tomorrow|kal)\b", query, re.IGNORECASE):
            day = day + timedelta(days=1)

        duration = 30
        found = re.search(r"(\d+)\s*(?:min|minute|minutes|hour|hours|ghante|ghanta)", query, re.IGNORECASE)
        if found:
            value = int(found.group(1))
            duration = value * 60 if re.search(r"hour|ghant", found.group(0), re.IGNORECASE) else value

        slots = cal.find_free_slots(day, duration_minutes=duration)
        if not slots:
            return f"You have no free {duration} minute window on {day.strftime('%d %B')}, sir."

        lines = [f"You are free for {duration} minutes at, sir:"]
        for start, end in slots[:5]:
            lines.append(
                f"  - {start.strftime('%I:%M %p').lstrip('0')} to {end.strftime('%I:%M %p').lstrip('0')}"
            )
        return "\n".join(lines)

    def _add_event(self, cal, params: dict) -> str:
        from jarvis.services import timeparse

        query = params.get("query", "") or ""
        parsed = timeparse.parse_when(query)
        if not parsed:
            return (
                "Sir, I need a time for that. "
                "Try 'schedule a meeting with Roshan tomorrow at 4 pm'."
            )

        title = (parsed.subject or "").strip()
        # Strip the scheduling verb so the event reads "meeting with Roshan".
        import re
        title = re.sub(
            r"^\s*(?:schedule|add|create|put|book|lagao|laga\s*do|daal\s*do)\s+(?:a|an|the)?\s*",
            "", title, flags=re.IGNORECASE,
        ).strip()
        if not title:
            title = "Untitled event"
        # timeparse lowercases while normalizing, so lift the first letter back
        # for a calendar entry that reads properly.
        title = title[0].upper() + title[1:]

        # parsed.run_at is naive local wall clock, which is what add_event expects
        # by default (start_is_local=True).
        event_id = cal.add_event(title, parsed.run_at, recurrence=parsed.recurrence)
        when = timeparse.describe(parsed.run_at)
        logger.info(f"CalendarAgent: created event {event_id} '{title}' at {parsed.run_at}")
        return f"Added to your calendar, sir: {title}, {when}."


# ==========================================================================
# 2. Core engine agents
# ==========================================================================
class AudioEngineAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        if msg.action == "listen":
            return self.jarvis.audio.listen()
        if msg.action == "listen_raw":
            return self.jarvis.audio.listen_raw()
        return self.unsupported(msg)


class TtsEngineAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        if msg.action == "speak":
            self.jarvis.tts.speak(msg.get("text", ""))
            return None
        if msg.action == "stop":
            self.jarvis.tts.stop_speech()
            return None
        return self.unsupported(msg)


class WakeWordAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        if msg.action == "status":
            return "Wake word detection is active, sir." if self.jarvis.wake else "Wake word engine is offline, sir."
        return self.unsupported(msg)


class VoiceAuthAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        if msg.action == "verify":
            return self.jarvis.voice_auth.verify_speaker(
                msg.get("raw_audio"), msg.get("sample_rate", 16000)
            )
        return self.unsupported(msg)


class IntentRouterAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        if msg.action == "route":
            return self.jarvis.router.route(msg.get("text", ""))
        return self.unsupported(msg)


class BrainAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        action = msg.action
        if action == "store":
            self.jarvis.brain.store(msg.get("text", ""), role=msg.get("role", "user"))
            return None
        if action == "retrieve":
            memories = self.jarvis.brain.retrieve(msg.get("query", ""))
            return self.jarvis.brain.format_memories_for_prompt(msg.get("query", ""))
        if action == "consolidate":
            facts = self.jarvis.brain.consolidate_memories()
            return f"Consolidated {len(facts or [])} new facts, sir."
        return self.unsupported(msg)


class CognitiveAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        if msg.action == "analyze":
            return self.jarvis.sentiment_tracker.analyze(
                msg.get("text", ""), msg.get("avg_rms", 100.0)
            )
        return self.unsupported(msg)


class ContextSentinelAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        if msg.action in ("check", "get_context"):
            return self.jarvis.sentinel.get_active_context()
        return self.unsupported(msg)


class ProactiveMonitorAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        action = msg.action
        if action == "start":
            self.jarvis.proactive_monitor.start()
            return "Proactive monitor started, sir."
        if action == "stop":
            self.jarvis.proactive_monitor.stop()
            return "Proactive monitor stopped, sir."
        if action == "pause":
            self.jarvis.proactive_monitor.paused = True
            return "Proactive screen monitoring paused, sir."
        if action == "resume":
            self.jarvis.proactive_monitor.paused = False
            return "Proactive screen monitoring resumed, sir."
        return self.unsupported(msg)


class FocusTrackerAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        action = msg.action
        if action == "start":
            self.jarvis.focus_tracker.start()
            return "Focus tracking started, sir."
        if action == "stop":
            self.jarvis.focus_tracker.stop()
            return "Focus tracking stopped, sir."
        return self.unsupported(msg)


class ProfileManagerAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        action = msg.action
        if action == "load":
            self.jarvis.profile_mgr.load_profile()
            return "Profile loaded, sir."
        if action == "get_preference":
            key = msg.params.get("key", "")
            default = msg.params.get("default")
            return self.jarvis.profile_mgr.get_preference(key, default)
        return self.unsupported(msg)


class VisionEngineAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        if msg.action == "analyze":
            return self.jarvis.vision.analyze(msg.get("question", ""))
        if msg.action == "read_text":
            return self.jarvis.vision.read_text_on_screen()
        return self.unsupported(msg)


class SensoryHealthAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        action = msg.action
        if action in ("analyze", "check"):
            return self.jarvis.sensory_health.analyze_environment()
        if action == "track_pulse":
            frame = msg.get("frame")
            if frame is not None:
                return self.jarvis.sensory_health.track_pulse(frame)
            return "No frame provided for pulse tracking, sir."
        if action == "heart_rate":
            return self.jarvis.sensory_health.calculate_heart_rate()
        return self.unsupported(msg)


class AirTypistAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        if msg.action == "start":
            return self.jarvis.air_typist.start()
        if msg.action == "stop":
            return self.jarvis.air_typist.stop()
        return self.unsupported(msg)


class P2PLinkAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        action = msg.action
        params = msg.params
        if action == "send_speech":
            return self.jarvis.p2p_link.send_speech(
                params.get("peer", ""), msg.get("text", "")
            )
        if action == "send_clipboard":
            return self.jarvis.p2p_link.send_clipboard(params.get("peer", ""))
        if action == "list_peers":
            peers = self.jarvis.p2p_link.list_peers()
            return f"Connected peers: {', '.join(peers) if peers else 'none'}, sir."
        return self.unsupported(msg)


class EmergencySentinelAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        if msg.action == "check":
            return self.jarvis.emergency_sentinel.check_for_distress(
                msg.get("text", ""), msg.get("avg_rms", 0.0)
            )
        return self.unsupported(msg)


# ==========================================================================
# 3. Domain expert agents
# ==========================================================================
class _DomainAgent(SwarmAgent):
    """Domain experts answer questions using their own system prompt."""

    domain_key = ""

    def receive_message(self, msg: Message):
        if msg.action in ("ask", "answer", "query"):
            domain = self.jarvis.domains.get(self.domain_key)
            if domain is None:
                return f"Sir, my {self.label} knowledge module is not loaded."
            # answer(query, memories) but we pass empty memories since most
            # voice requests don't need memory retrieval overhead.
            return domain.answer(msg.get("text", ""), memories="")
        return self.unsupported(msg)


class BusinessDomainAgent(_DomainAgent):
    domain_key = "business"


class DevelopmentDomainAgent(_DomainAgent):
    domain_key = "development"


class EngineeringDomainAgent(_DomainAgent):
    domain_key = "engineering"


class FinanceDomainAgent(_DomainAgent):
    domain_key = "finance"


class MedicalDomainAgent(_DomainAgent):
    domain_key = "medical"


class ScienceDomainAgent(_DomainAgent):
    domain_key = "science"


class SecurityDomainAgent(_DomainAgent):
    domain_key = "security"


# ==========================================================================
# 4. Action skill agents
# ==========================================================================
class AppControlAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        params = msg.params
        if msg.action == "execute":
            return self.jarvis.app_ctrl.execute_action(
                params.get("action_name", ""), params.get("active_process", "")
            )
        if msg.action == "reload_maps":
            self.jarvis.app_ctrl.load_maps()
            return "Application control maps reloaded, sir."
        return self.unsupported(msg)


class AppMapperAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        params = msg.params
        action = msg.action
        if action == "map_ui":
            return self.jarvis.app_map.map_app_ui(params.get("app_name", ""))
        if action == "click_element":
            return self.jarvis.app_map.click_element(
                params.get("app_name", ""), params.get("element_name", "")
            )
        if action == "fill_field":
            return self.jarvis.app_map.fill_form_field(
                params.get("app_name", ""), params.get("field_label", ""), params.get("text", "")
            )
        return self.unsupported(msg)


class CodeRunnerAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        params = msg.params
        action = msg.action
        if action == "run_code":
            return self.jarvis.code_runner.run_code(
                params.get("language", "python"), params.get("code", "")
            )
        if action == "git":
            return self.jarvis.code_runner.git_command(
                params.get("git_action", ""), params.get("args", "")
            )
        if action == "docker":
            return self.jarvis.code_runner.docker_command(
                params.get("docker_action", ""), params.get("args", "")
            )
        if action == "mobile_view":
            return self.jarvis.code_runner.mobile_view_emulation(params.get("url", ""))
        if action == "deploy":
            return self.jarvis.code_runner.deploy_app(
                params.get("project_path", ""), params.get("port", 8000)
            )
        return self.unsupported(msg)


class CodingSandboxAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        params = msg.params
        if msg.action == "execute_task":
            return self.jarvis.coding_sandbox.execute_task(params.get("task", ""))
        if msg.action == "compile_and_repair":
            return self.jarvis.compiler_repair.compile_and_repair(params.get("build_command", ""))
        return self.unsupported(msg)


class DataAnalyzerAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        params = msg.params
        action = msg.action
        if action == "read_document":
            return self.jarvis.data_analyzer.read_document_text(params.get("filepath", ""))
        if action == "statistics":
            return self.jarvis.data_analyzer.calculate_statistics(
                params.get("filepath", ""), params.get("column", "")
            )
        if action == "log_kpi":
            return self.jarvis.data_analyzer.log_kpi(params.get("name", ""), params.get("value", 0))
        if action == "kpi_history":
            return self.jarvis.data_analyzer.get_kpi_history(params.get("name", ""))
        return self.unsupported(msg)


class FileManagerAgent(SwarmAgent):
    """Owns every file and folder action. Mirrors FileManager's public surface."""

    def receive_message(self, msg: Message):
        fm = self.jarvis.file_manager
        params = msg.params
        action = msg.action
        path = params.get("path", "")

        if action == "create_file":
            return fm.create_file(path, params.get("content", ""))
        if action == "rename_file":
            return fm.rename_file(params.get("old_path", ""), params.get("new_path", ""))
        if action == "move_file":
            return fm.move_file(params.get("src", ""), params.get("dst", ""))
        if action == "delete_file":
            return fm.delete_file(path, params.get("shred", False))
        if action == "create_directory":
            return fm.create_directory(path)
        if action == "delete_directory":
            return fm.delete_directory(path)
        if action == "toggle_show_hidden_files":
            return fm.toggle_show_hidden_files(params.get("show", True))
        if action == "set_file_hidden":
            return fm.set_file_hidden(path, params.get("hide", True))
        if action == "get_folder_size":
            return fm.get_folder_size(path)
        if action == "sync_folders":
            return fm.sync_folders(params.get("src", ""), params.get("dst", ""))
        if action == "backup_to_local_cloud":
            return fm.backup_to_local_cloud(path, params.get("cloud_provider", "onedrive"))
        if action == "find_and_open":
            return fm.find_and_open_target(
                params.get("target", path), specific_location=params.get("location")
            )
        if action == "inspect_folder":
            return fm.inspect_folder_contents(
                params.get("target", path),
                parent_location=params.get("location"),
                lang=msg.get("lang", "en"),
            )
        if action == "purge_folder":
            response = fm.purge_folder_contents(
                params.get("target", path),
                parent_location=params.get("location"),
                lang=msg.get("lang", "en"),
            )
            if params.get("also_empty_bin"):
                response = f"{response} {self.jarvis.os_ctrl.empty_recycle_bin()}"
            return response
        return "File action not supported, sir."


class FoodComparatorAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        params = msg.params
        if msg.action in ("find_food", "order", "compare"):
            return self.jarvis.food_comparator.find_food(
                params.get("query", ""), params.get("budget")
            )
        return self.unsupported(msg)


class GestureControlAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        if msg.action == "start":
            return self.jarvis.gesture_ctrl.start()
        if msg.action == "stop":
            return self.jarvis.gesture_ctrl.stop()
        return self.unsupported(msg)


class GitSentinelAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        if msg.action in ("check", "check_workspace", "status"):
            return self.jarvis.git_sentinel.check_workspace()
        return self.unsupported(msg)


class MacroRecorderAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        params = msg.params
        name = params.get("macro_name", params.get("name", "default"))
        if msg.action == "start_recording":
            return self.jarvis.macro_recorder.start_recording(name)
        if msg.action == "stop_recording":
            return self.jarvis.macro_recorder.stop_recording(name)
        if msg.action == "play":
            return self.jarvis.macro_recorder.play_macro(name)
        return self.unsupported(msg)


class MarketAnalyzerAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        if msg.action in ("analyze", "analyze_asset", "price"):
            return self.jarvis.market_analyzer.analyze_asset(msg.params.get("query", ""))
        return self.unsupported(msg)


class MediaSummarizerAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        params = msg.params
        if msg.action == "summarize_youtube":
            return self.jarvis.media.summarize_youtube(params.get("url", ""))
        if msg.action == "summarize_local":
            return self.jarvis.media.summarize_local(params.get("file_path", ""))
        return self.unsupported(msg)


class NetworkMapperAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        params = msg.params
        action = msg.action
        if action == "ping":
            return self.jarvis.network_mapper.ping_ip(params.get("ip", ""))
        if action in ("scan", "scan_subnet"):
            return self.jarvis.network_mapper.scan_local_subnet()
        if action == "topology":
            devices = self.jarvis.network_mapper.scan_local_subnet()
            return self.jarvis.network_mapper.generate_3d_topology(devices)
        return self.unsupported(msg)


class ObsidianControlAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        params = msg.params
        action = msg.action
        obs = self.jarvis.obsidian_ctrl
        if action == "create_note":
            return obs.create_note(params.get("title", "Untitled"), params.get("content", ""))
        if action == "read_note":
            return obs.read_note(params.get("title", ""))
        if action == "search_notes":
            return obs.search_notes(params.get("query", ""))
        if action == "append_daily":
            return obs.append_to_daily_note(params.get("content", ""))
        if action == "list_notes":
            return obs.list_notes(params.get("folder"))
        return self.unsupported(msg)


class OsControlAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        params = msg.params
        action = msg.action
        os_ctrl = self.jarvis.os_ctrl

        if action == "lock":
            return os_ctrl.lock_screen()
        if action == "sentry_mode":
            return os_ctrl.activate_sentry_mode(self.jarvis.camera, self.jarvis.tts)
        if action == "empty_recycle_bin":
            return os_ctrl.empty_recycle_bin()
        if action == "scroll":
            return os_ctrl.scroll(params.get("direction", "down"), params.get("amount", 3))
        if action == "move_mouse":
            return os_ctrl.move_mouse(params.get("x", 0), params.get("y", 0))
        if action == "toggle_desktop_icons":
            return os_ctrl.toggle_desktop_icons(params.get("show", True))
        return self.unsupported(msg)


class PhoneControllerAgent(SwarmAgent):
    """PhoneController exposes one public method per ADB action, so the router's
    action name maps straight onto it."""

    def receive_message(self, msg: Message):
        return _dispatch_by_name(self, self.jarvis.phone, msg)


class PolyglotEngineerAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        params = msg.params
        action = msg.action
        eng = self.jarvis.polyglot_engineer
        if action == "design_architecture":
            return eng.design_architecture(params.get("description", ""))
        if action == "review_code":
            return eng.review_code(params.get("language", ""), params.get("code", ""))
        if action == "write_solution":
            return eng.write_polyglot_solution(params.get("language", ""), params.get("task", ""))
        return self.unsupported(msg)


class ProductivityAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        params = msg.params
        action = msg.action
        prod = self.jarvis.productivity
        if action == "create_presentation":
            # pptx_helper is the real public method
            return prod.pptx_helper(
                title=params.get("title", params.get("topic", "Presentation")),
                subtitle=params.get("subtitle", ""),
                theme=params.get("theme", "stark_tech"),
                slides_content=params.get("slides_content", []),
                output_path=params.get("output_path", "presentation.pptx"),
            )
        if action == "mindmap":
            return prod.generate_mindmap(params.get("topic", ""))
        if action == "add_todo":
            return prod.add_todo(params.get("task", ""))
        if action == "list_todos":
            return prod.list_todos()
        return self.unsupported(msg)


class ProductComparatorAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        params = msg.params
        if msg.action in ("compare", "search_and_compare"):
            return self.jarvis.product_comparator.search_and_compare(
                params.get("query", ""), params.get("budget")
            )
        return self.unsupported(msg)


class ResearchProdigyAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        if msg.action == "deep_research":
            return self.jarvis.research_prodigy.execute_deep_research(msg.params.get("topic", ""))
        return self.unsupported(msg)


class ScreenVisionAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        params = msg.params
        action = msg.action
        vision = self.jarvis.vision
        if action == "analyze":
            return vision.analyze(params.get("question", ""))
        if action == "read_text":
            return vision.read_text_on_screen()
        if action == "analyze_image":
            return vision.analyze_image(params.get("image_path", ""), params.get("question", ""))
        return self.unsupported(msg)


class SecurityAuditorAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        params = msg.params
        action = msg.action
        auditor = self.jarvis.security_auditor
        if action == "scan_ports":
            return auditor.scan_ports(params.get("host", "127.0.0.1"))
        if action == "scan_network":
            return auditor.scan_network_devices()
        if action == "outbound_connections":
            return auditor.list_active_outbound_connections()
        if action == "audit_password":
            return auditor.audit_password_strength(params.get("password", ""))
        if action == "audit_packages":
            return auditor.audit_installed_packages_for_cves()
        if action == "analyze_logs":
            return auditor.analyze_workspace_logs(params.get("log_path"))
        if action in ("full_scan", "system_scan"):
            return auditor.run_system_security_scan()
        return self.unsupported(msg)


class SelfHealingVisionAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        params = msg.params
        if msg.action == "locate":
            return self.jarvis.self_healing.locate_element_visually(params.get("element", ""))
        if msg.action == "click":
            return self.jarvis.self_healing.click_element_visually(params.get("element", ""))
        return self.unsupported(msg)


class SentryFirewallAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        params = msg.params
        action = msg.action
        fw = self.jarvis.sentry_firewall
        if action == "quarantine":
            return fw.quarantine_ip(params.get("ip", ""))
        if action == "remove_quarantine":
            return fw.remove_quarantine(params.get("ip", ""))
        if action in ("list", "list_blocks"):
            return fw.list_blocks()
        return self.unsupported(msg)


class SpotifyControlAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        params = msg.params
        action = msg.action
        if action == "play":
            return self.jarvis.spotify_ctrl.play_song(params.get("query", ""))
        if action in ("pause", "resume", "next", "previous",
                      "volume_up", "volume_down", "mute", "unmute"):
            return self.jarvis.spotify_ctrl.control_media(action)
        return self.unsupported(msg)


class VisionTrackerAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        params = msg.params
        action = msg.action
        tracker = self.jarvis.vision_tracker
        if action == "detect_objects":
            return tracker.detect_objects_in_room(params.get("night_vision", False))
        if action == "analyze_fatigue":
            return tracker.analyze_user_fatigue_and_stress(params.get("night_vision", False))
        if action == "analyze_appearance":
            return tracker.analyze_user_appearance(params.get("prompt"))
        return self.unsupported(msg)


class WebResearchAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        params = msg.params
        action = msg.action
        if action in ("search", "research"):
            return self.jarvis.web.headless_search_and_summarize(params.get("query", ""))
        if action == "search_google":
            return self.jarvis.web.search_google(params.get("query", ""))
        if action == "news":
            return self.jarvis.web.get_daily_news_summary()
        return self.unsupported(msg)


class WorkspaceContextAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        action = msg.action
        ctx = self.jarvis.workspace_context
        if action == "active_window":
            return ctx.get_active_window_title()
        if action == "clipboard":
            return ctx.read_clipboard()
        if action == "recent_files":
            return ctx.get_recently_modified_files(msg.params.get("limit", 10))
        if action in ("summary", "editor_context"):
            return ctx.get_editor_context_summary()
        return self.unsupported(msg)


class YoutubeMusicAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        params = msg.params
        action = msg.action
        player = self.jarvis.youtube_music
        if action == "play":
            return player.play_song(params.get("query", ""))
        if action in ("pause", "resume", "stop", "next", "previous",
                      "volume_up", "volume_down"):
            return player.control_media(action)
        return self.unsupported(msg)


class ImageEditorAgent(SwarmAgent):
    """ImageEditor's public methods are named after the actions the router emits."""

    def receive_message(self, msg: Message):
        return _dispatch_by_name(self, self.jarvis.image_editor, msg)


class ShoppingAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        params = msg.params
        action = msg.action
        shop = self.jarvis.shopping
        if action in ("search", "show_product"):
            return shop.search_and_show_product(
                params.get("query", ""), params.get("platform", "amazon")
            )
        if action == "add_to_cart":
            return shop.add_to_cart(params.get("query"))
        if action == "buy_now":
            return shop.buy_now_checkout(params.get("query"))
        return self.unsupported(msg)


class CadGeneratorAgent(SwarmAgent):
    def receive_message(self, msg: Message):
        if msg.action in ("generate", "generate_mesh"):
            return self.jarvis.cad_gen.generate_mesh(msg.params.get("prompt", ""))
        return self.unsupported(msg)
