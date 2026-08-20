"""Tests for the local-first service layer.

These run with no network, no API keys, and no Ollama: everything under test is
standard library plus SQLite. Each test gets a fresh temporary database.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from jarvis.services.calendar_service import CalendarService
from jarvis.services.db import Database, from_iso, to_iso, utc_now
from jarvis.services.scheduler import Scheduler, next_occurrence


@pytest.fixture()
def db(tmp_path):
    database = Database(str(tmp_path / "test.db"))
    yield database
    database.close()


@pytest.fixture()
def calendar(db):
    # UTC keeps the assertions readable; timezone conversion is covered separately.
    return CalendarService(db, timezone_name="UTC")


@pytest.fixture()
def scheduler(db):
    return Scheduler(db, poll_interval=1, misfire_grace_minutes=120)


# -- database ------------------------------------------------------------
def test_migrations_apply_and_are_idempotent(tmp_path):
    path = str(tmp_path / "migrate.db")
    first = Database(path)
    assert first.schema_version == 1
    first.close()

    # Re-opening must not re-run migrations or lose data.
    second = Database(path)
    assert second.schema_version == 1
    second.close()


def test_iso_roundtrip_assumes_utc_for_naive_values():
    naive = datetime(2026, 3, 1, 12, 30, 0)
    parsed = from_iso(to_iso(naive))
    assert parsed.tzinfo is not None
    assert parsed.hour == 12


def test_from_iso_accepts_trailing_z():
    assert from_iso("2026-03-01T12:00:00Z").hour == 12


def test_audit_log_records_actions(db):
    db.audit(actor="test", action="did_something", target="thing", risk="local_write")
    row = db.query_one("SELECT * FROM audit_log ORDER BY id DESC LIMIT 1")
    assert row["actor"] == "test"
    assert row["action"] == "did_something"


# -- scheduler recurrence maths -----------------------------------------
def test_next_occurrence_skips_windows_missed_while_offline():
    """A daily job offline for a week should fire once, not seven times."""
    base = datetime(2026, 3, 1, 8, 0, tzinfo=timezone.utc)
    now = datetime(2026, 3, 8, 9, 0, tzinfo=timezone.utc)
    nxt = next_occurrence(base, "daily", after=now)
    assert nxt == datetime(2026, 3, 9, 8, 0, tzinfo=timezone.utc)


def test_next_occurrence_returns_none_for_one_shot():
    assert next_occurrence(utc_now(), "none") is None


def test_next_occurrence_monthly_clamps_short_months():
    jan31 = datetime(2026, 1, 31, 9, 0, tzinfo=timezone.utc)
    nxt = next_occurrence(jan31, "monthly", after=jan31)
    assert (nxt.month, nxt.day) == (2, 28)


def test_next_occurrence_interval_requires_positive_seconds():
    assert next_occurrence(utc_now(), "interval", interval_secs=0) is None


# -- scheduler behaviour -------------------------------------------------
def test_due_job_runs_and_completes(scheduler):
    fired = []
    scheduler.register_handler("reminder", lambda payload: fired.append(payload["text"]))
    job_id = scheduler.schedule(
        "reminder", utc_now() - timedelta(seconds=5), {"text": "drink water"}
    )

    assert scheduler.run_due_jobs() == 1
    assert fired == ["drink water"]

    row = scheduler.db.query_one("SELECT * FROM scheduled_jobs WHERE id=?", (job_id,))
    assert row["status"] == "done"
    assert row["run_count"] == 1


def test_future_job_does_not_run_early(scheduler):
    fired = []
    scheduler.register_handler("reminder", lambda payload: fired.append(payload))
    scheduler.schedule("reminder", utc_now() + timedelta(hours=1), {"text": "later"})

    assert scheduler.run_due_jobs() == 0
    assert fired == []


def test_recurring_job_is_rescheduled_after_firing(scheduler):
    calls = []
    scheduler.register_handler("briefing", lambda payload: calls.append(1))
    job_id = scheduler.schedule(
        "briefing", utc_now() - timedelta(minutes=1), {}, recurrence="daily"
    )

    scheduler.run_due_jobs()
    row = scheduler.db.query_one("SELECT * FROM scheduled_jobs WHERE id=?", (job_id,))

    assert len(calls) == 1
    assert row["status"] == "pending"  # still active
    assert from_iso(row["next_run_utc"]) > utc_now()

    # A second pass in the same moment must not double-fire.
    scheduler.run_due_jobs()
    assert len(calls) == 1


def test_job_missed_while_offline_is_flagged_not_fired(scheduler):
    """An alarm from hours ago should be reported, not blared on startup."""
    fired = []
    scheduler.register_handler("alarm", lambda payload: fired.append(payload))
    job_id = scheduler.schedule("alarm", utc_now() - timedelta(hours=6), {})

    scheduler.run_due_jobs()
    row = scheduler.db.query_one("SELECT * FROM scheduled_jobs WHERE id=?", (job_id,))

    assert fired == []
    assert row["status"] == "missed"


def test_handler_exception_is_recorded_without_stopping_scheduler(scheduler):
    def explode(payload):
        raise RuntimeError("handler blew up")

    scheduler.register_handler("bad", explode)
    scheduler.register_handler("good", lambda payload: "fine")
    bad_id = scheduler.schedule("bad", utc_now() - timedelta(seconds=1), {})
    scheduler.schedule("good", utc_now() - timedelta(seconds=1), {})

    # The good job still runs even though the bad one raised.
    assert scheduler.run_due_jobs() == 1
    bad = scheduler.db.query_one("SELECT * FROM scheduled_jobs WHERE id=?", (bad_id,))
    assert bad["status"] == "error"
    assert "blew up" in bad["last_error"]


def test_job_with_no_handler_is_marked_error(scheduler):
    job_id = scheduler.schedule("unknown_kind", utc_now() - timedelta(seconds=1), {})
    scheduler.run_due_jobs()
    row = scheduler.db.query_one("SELECT * FROM scheduled_jobs WHERE id=?", (job_id,))
    assert row["status"] == "error"


def test_cancel_and_snooze(scheduler):
    scheduler.register_handler("reminder", lambda payload: None)
    job_id = scheduler.schedule("reminder", utc_now() + timedelta(hours=2), {})

    assert scheduler.snooze(job_id, 30) is True
    assert scheduler.cancel(job_id) is True
    assert scheduler.cancel(job_id) is False  # already cancelled
    assert scheduler.pending_jobs() == []


def test_invalid_recurrence_is_rejected(scheduler):
    with pytest.raises(ValueError):
        scheduler.schedule("reminder", utc_now(), {}, recurrence="fortnightly")


# -- calendar ------------------------------------------------------------
def test_add_and_retrieve_event(calendar):
    start = utc_now() + timedelta(days=1)
    calendar.add_event("Dentist", start, start + timedelta(hours=1), location="Clinic")

    events = calendar.events_on(start.date())
    assert len(events) == 1
    assert events[0]["title"] == "Dentist"
    assert events[0]["location"] == "Clinic"


def test_event_requires_title(calendar):
    with pytest.raises(ValueError):
        calendar.add_event("   ", utc_now())


def test_event_cannot_end_before_it_starts(calendar):
    start = utc_now()
    with pytest.raises(ValueError):
        calendar.add_event("Backwards", start, start - timedelta(hours=1))


def test_next_event_ignores_the_past(calendar):
    calendar.add_event("Yesterday", utc_now() - timedelta(days=1))
    calendar.add_event("Tomorrow", utc_now() + timedelta(days=1))
    assert calendar.next_event()["title"] == "Tomorrow"


def test_daily_recurring_event_appears_on_later_days(calendar):
    start = utc_now().replace(hour=9, minute=0, second=0, microsecond=0)
    calendar.add_event("Standup", start, start + timedelta(minutes=15), recurrence="daily")

    later = (start + timedelta(days=3)).date()
    titles = [e["title"] for e in calendar.events_on(later)]
    assert "Standup" in titles


def test_conflict_detection_finds_overlap(calendar):
    start = utc_now() + timedelta(days=1)
    calendar.add_event("Design review", start, start + timedelta(hours=2))
    calendar.add_event("Client call", start + timedelta(hours=1), start + timedelta(hours=3))

    conflicts = calendar.find_conflicts()
    assert len(conflicts) == 1


def test_no_conflict_for_back_to_back_meetings(calendar):
    start = utc_now() + timedelta(days=1)
    calendar.add_event("First", start, start + timedelta(hours=1))
    calendar.add_event("Second", start + timedelta(hours=1), start + timedelta(hours=2))
    assert calendar.find_conflicts() == []


def test_free_slots_exclude_busy_time(calendar):
    day = (utc_now() + timedelta(days=1)).date()
    busy_start = datetime.combine(day, datetime.min.time()).replace(
        hour=10, tzinfo=timezone.utc
    )
    calendar.add_event("Workshop", busy_start, busy_start + timedelta(hours=2))

    slots = calendar.find_free_slots(day, duration_minutes=30)
    assert slots, "expected free time around a two-hour meeting"
    # No suggested slot may overlap the meeting.
    for slot_start, slot_end in slots:
        assert not (slot_start < busy_start + timedelta(hours=2) and busy_start < slot_end)


def test_reschedule_preserves_duration(calendar):
    start = utc_now() + timedelta(days=1)
    event_id = calendar.add_event("Review", start, start + timedelta(hours=1))

    new_start = start + timedelta(days=2)
    assert calendar.reschedule_event(event_id, new_start) is True

    moved = calendar.events_on(new_start.date())[0]
    assert moved["end_utc"] - moved["start_utc"] == timedelta(hours=1)


def test_delete_event(calendar):
    event_id = calendar.add_event("Temporary", utc_now() + timedelta(days=1))
    assert calendar.delete_event(event_id) is True
    assert calendar.delete_event(event_id) is False


def test_describe_agenda_speaks_clearly(calendar):
    assert "clear" in calendar.describe_agenda().lower()

    start = utc_now().replace(hour=15, minute=0, second=0, microsecond=0)
    calendar.add_event("Board meeting", start, start + timedelta(hours=1))
    spoken = calendar.describe_agenda()
    assert "Board meeting" in spoken


# -- .ics interoperability ----------------------------------------------
SAMPLE_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Example Corp//Calendar//EN
BEGIN:VEVENT
UID:evt-1@example.com
DTSTAMP:20260301T090000Z
DTSTART:20260315T093000Z
DTEND:20260315T103000Z
SUMMARY:Quarterly planning\\, with the board
LOCATION:Room 4
DESCRIPTION:Bring the deck
END:VEVENT
BEGIN:VEVENT
UID:evt-2@example.com
DTSTART;VALUE=DATE:20260316
SUMMARY:Company holiday
END:VEVENT
BEGIN:VEVENT
UID:evt-3@example.com
DTSTART:20260317T060000Z
SUMMARY:A very long summary line that a real calendar would
  fold across two physical lines
RRULE:FREQ=WEEKLY;COUNT=5
END:VEVENT
END:VCALENDAR
"""


def test_import_ics_reads_real_world_shapes(calendar, tmp_path):
    path = tmp_path / "invite.ics"
    path.write_text(SAMPLE_ICS, encoding="utf-8")

    result = calendar.import_ics(str(path))
    assert "Imported 3 events" in result

    events = calendar.events_between(
        datetime(2026, 3, 15, tzinfo=timezone.utc),
        datetime(2026, 3, 16, tzinfo=timezone.utc),
    )
    titles = [e["title"] for e in events]
    # Escaped comma must be unescaped on the way in.
    assert "Quarterly planning, with the board" in titles


def test_import_ics_handles_all_day_and_folded_lines(calendar, tmp_path):
    path = tmp_path / "invite.ics"
    path.write_text(SAMPLE_ICS, encoding="utf-8")
    calendar.import_ics(str(path))

    rows = calendar.db.query("SELECT * FROM calendar_events ORDER BY start_utc")
    all_day = [r for r in rows if r["all_day"]]
    assert len(all_day) == 1
    assert all_day[0]["title"] == "Company holiday"

    folded = [r for r in rows if "fold across two physical lines" in r["title"]]
    assert folded, "folded continuation line should be joined"
    assert folded[0]["recurrence"] == "weekly"


def test_reimporting_the_same_ics_does_not_duplicate(calendar, tmp_path):
    path = tmp_path / "invite.ics"
    path.write_text(SAMPLE_ICS, encoding="utf-8")

    calendar.import_ics(str(path))
    first = calendar.db.query_one("SELECT COUNT(*) AS c FROM calendar_events")["c"]
    calendar.import_ics(str(path))
    second = calendar.db.query_one("SELECT COUNT(*) AS c FROM calendar_events")["c"]

    assert first == second == 3


def test_missing_ics_file_is_reported_gracefully(calendar):
    assert "could not find" in calendar.import_ics("nope/missing.ics").lower()


def test_export_then_import_round_trips(calendar, tmp_path, db):
    start = utc_now() + timedelta(days=2)
    calendar.add_event("Strategy offsite", start, start + timedelta(hours=3), location="HQ")

    out = tmp_path / "out.ics"
    assert "Exported" in calendar.export_ics(str(out))
    assert out.exists()

    # Import into a clean database to prove the file stands on its own.
    other_db = Database(str(tmp_path / "other.db"))
    other = CalendarService(other_db, timezone_name="UTC")
    other.import_ics(str(out))

    titles = [r["title"] for r in other_db.query("SELECT title FROM calendar_events")]
    assert "Strategy offsite" in titles
    other_db.close()


def test_export_escapes_special_characters(calendar, tmp_path):
    start = utc_now() + timedelta(days=1)
    calendar.add_event("Budget; review, final", start, start + timedelta(hours=1))

    out = tmp_path / "escaped.ics"
    calendar.export_ics(str(out))
    text = out.read_text(encoding="utf-8")

    assert "Budget\\; review\\, final" in text
