"""Real calendar for JARVIS: SQLite storage plus .ics interoperability.

This replaces the flat `config/calendar.json` file with a queryable store that
understands timezones, recurrence, conflicts, and free time.

On interoperability without API keys: the `.ics` (RFC 5545) format is the common
language of Google Calendar, Outlook, and Apple Calendar. Every one of them can
export a .ics file and import one, so JARVIS can exchange events with any of
them using `import_ics` / `export_ics` and no credentials whatsoever. Live
two-way sync would additionally need CalDAV, which is a user login rather than a
paid key, and can be layered on top of this store later.

The .ics reader/writer here is intentionally written against the standard
library so the feature works on a bare install. It covers the subset real
calendars emit: VEVENT blocks, DTSTART/DTEND with UTC, floating, or all-day
values, folded long lines, escaped text, and simple RRULE frequencies.
"""

from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, time, timedelta, timezone

from loguru import logger

from jarvis.services.db import Database, from_iso, to_iso, utc_now

try:  # Python 3.9+ standard library
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - only on very old interpreters
    ZoneInfo = None  # type: ignore

RECURRENCE_RULES = {"none", "daily", "weekly", "monthly", "yearly"}


class CalendarService:
    """Event storage, querying, and .ics import/export."""

    def __init__(self, db: Database, timezone_name: str = "Asia/Kolkata"):
        self.db = db
        self.timezone_name = timezone_name
        self.tz = self._load_timezone(timezone_name)

    @staticmethod
    def _load_timezone(name: str):
        if ZoneInfo is not None:
            try:
                return ZoneInfo(name)
            except Exception:
                logger.warning(f"Calendar: unknown timezone '{name}', using system local time")
        return None

    # -- timezone helpers ------------------------------------------------
    def to_local(self, dt: datetime) -> datetime:
        """Convert stored UTC into the user's timezone for display."""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(self.tz) if self.tz else dt.astimezone()

    def to_utc(self, dt: datetime) -> datetime:
        """Interpret a naive datetime as local wall-clock time and convert to UTC."""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=self.tz) if self.tz else dt.astimezone().replace(
                tzinfo=datetime.now().astimezone().tzinfo
            )
        return dt.astimezone(timezone.utc)

    # -- writes ----------------------------------------------------------
    def add_event(
        self,
        title: str,
        start: datetime,
        end: datetime | None = None,
        location: str | None = None,
        notes: str | None = None,
        all_day: bool = False,
        recurrence: str = "none",
        source: str = "local",
        external_uid: str | None = None,
        start_is_local: bool = True,
    ) -> int:
        """Create an event and return its id.

        `start_is_local` reflects the common case: a naive datetime parsed from
        speech means the user's wall clock, not UTC.
        """
        if not title or not title.strip():
            raise ValueError("An event needs a title")
        rule = (recurrence or "none").lower()
        if rule not in RECURRENCE_RULES:
            raise ValueError(f"Unsupported recurrence '{recurrence}'")

        start_utc = self.to_utc(start) if (start_is_local and start.tzinfo is None) else start
        if start_utc.tzinfo is None:
            start_utc = start_utc.replace(tzinfo=timezone.utc)
        start_utc = start_utc.astimezone(timezone.utc)

        end_utc = None
        if end is not None:
            end_utc = self.to_utc(end) if (start_is_local and end.tzinfo is None) else end
            if end_utc.tzinfo is None:
                end_utc = end_utc.replace(tzinfo=timezone.utc)
            end_utc = end_utc.astimezone(timezone.utc)
            if end_utc < start_utc:
                raise ValueError("An event cannot end before it starts")

        now = to_iso(utc_now())
        # Upserting on (source, external_uid) makes re-importing the same .ics
        # file update events instead of duplicating them.
        cur = self.db.execute(
            "INSERT INTO calendar_events"
            " (title, start_utc, end_utc, location, notes, all_day, recurrence,"
            "  source, external_uid, created_utc, updated_utc)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            # The unique index on (source, external_uid) is partial, so SQLite
            # requires its WHERE clause repeated here to match the conflict target.
            " ON CONFLICT (source, external_uid) WHERE external_uid IS NOT NULL"
            " DO UPDATE SET"

            "  title=excluded.title, start_utc=excluded.start_utc,"
            "  end_utc=excluded.end_utc, location=excluded.location,"
            "  notes=excluded.notes, all_day=excluded.all_day,"
            "  recurrence=excluded.recurrence, updated_utc=excluded.updated_utc",
            (
                title.strip(),
                to_iso(start_utc),
                to_iso(end_utc) if end_utc else None,
                location,
                notes,
                1 if all_day else 0,
                rule,
                source,
                external_uid,
                now,
                now,
            ),
        )
        event_id = int(cur.lastrowid)
        self.db.audit(
            actor="calendar",
            action="add_event",
            target=title.strip()[:120],
            risk="local_write",
            outcome="ok",
        )
        return event_id

    def delete_event(self, event_id: int) -> bool:
        cur = self.db.execute("DELETE FROM calendar_events WHERE id=?", (event_id,))
        if cur.rowcount:
            self.db.audit(
                actor="calendar",
                action="delete_event",
                target=str(event_id),
                risk="local_write",
                outcome="ok",
            )
        return cur.rowcount > 0

    def reschedule_event(self, event_id: int, new_start: datetime) -> bool:
        """Move an event, preserving its original duration."""
        row = self.db.query_one("SELECT * FROM calendar_events WHERE id=?", (event_id,))
        if not row:
            return False

        old_start = from_iso(row["start_utc"])
        duration = (
            from_iso(row["end_utc"]) - old_start if row["end_utc"] else timedelta(0)
        )
        start_utc = self.to_utc(new_start) if new_start.tzinfo is None else new_start.astimezone(
            timezone.utc
        )
        new_end = start_utc + duration if row["end_utc"] else None

        self.db.execute(
            "UPDATE calendar_events SET start_utc=?, end_utc=?, updated_utc=? WHERE id=?",
            (to_iso(start_utc), to_iso(new_end) if new_end else None, to_iso(utc_now()), event_id),
        )
        return True

    # -- reads -----------------------------------------------------------
    def _expand(self, row, window_start: datetime, window_end: datetime) -> list[dict]:
        """Expand a stored row into concrete occurrences inside a window."""
        base_start = from_iso(row["start_utc"])
        base_end = from_iso(row["end_utc"]) if row["end_utc"] else None
        duration = (base_end - base_start) if base_end else timedelta(0)
        rule = (row["recurrence"] or "none").lower()

        occurrences: list[datetime] = []
        if rule == "none":
            if base_start <= window_end and (base_end or base_start) >= window_start:
                occurrences.append(base_start)
        else:
            cursor = base_start
            step = {"daily": timedelta(days=1), "weekly": timedelta(weeks=1)}.get(rule)
            guard = 0
            while cursor <= window_end and guard < 2000:
                guard += 1
                if cursor + duration >= window_start:
                    occurrences.append(cursor)
                if step:
                    cursor = cursor + step
                elif rule == "monthly":
                    month = cursor.month + 1
                    year = cursor.year + (month - 1) // 12
                    month = (month - 1) % 12 + 1
                    day = min(cursor.day, 28)
                    cursor = cursor.replace(year=year, month=month, day=day)
                elif rule == "yearly":
                    cursor = cursor.replace(year=cursor.year + 1)
                else:
                    break

        results = []
        for occ in occurrences:
            results.append(
                {
                    "id": row["id"],
                    "title": row["title"],
                    "start_utc": occ,
                    "end_utc": (occ + duration) if base_end else None,
                    "start_local": self.to_local(occ),
                    "end_local": self.to_local(occ + duration) if base_end else None,
                    "location": row["location"],
                    "notes": row["notes"],
                    "all_day": bool(row["all_day"]),
                    "recurrence": rule,
                    "source": row["source"],
                }
            )
        return results

    def events_between(self, start: datetime, end: datetime) -> list[dict]:
        """All occurrences overlapping [start, end], recurrence expanded."""
        start_utc = start if start.tzinfo else start.replace(tzinfo=timezone.utc)
        end_utc = end if end.tzinfo else end.replace(tzinfo=timezone.utc)
        start_utc, end_utc = start_utc.astimezone(timezone.utc), end_utc.astimezone(timezone.utc)

        # Non-recurring rows can be filtered in SQL; recurring rows must be
        # expanded in Python because their occurrences are not stored.
        rows = self.db.query(
            "SELECT * FROM calendar_events"
            " WHERE recurrence != 'none'"
            "    OR (start_utc <= ? AND COALESCE(end_utc, start_utc) >= ?)",
            (to_iso(end_utc), to_iso(start_utc)),
        )
        out: list[dict] = []
        for row in rows:
            out.extend(self._expand(row, start_utc, end_utc))
        return sorted(out, key=lambda e: e["start_utc"])

    def events_on(self, day: date) -> list[dict]:
        """Everything on a given local calendar day."""
        start_local = datetime.combine(day, time.min)
        end_local = datetime.combine(day, time.max)
        return self.events_between(self.to_utc(start_local), self.to_utc(end_local))

    def agenda_today(self) -> list[dict]:
        return self.events_on(self.to_local(utc_now()).date())

    def next_event(self) -> dict | None:
        now = utc_now()
        upcoming = self.events_between(now, now + timedelta(days=365))
        for event in upcoming:
            if event["start_utc"] >= now:
                return event
        return None

    def find_conflicts(self) -> list[tuple[dict, dict]]:
        """Overlapping timed events in the next 30 days."""
        now = utc_now()
        events = [
            e
            for e in self.events_between(now, now + timedelta(days=30))
            if e["end_utc"] and not e["all_day"]
        ]
        clashes = []
        for i, first in enumerate(events):
            for second in events[i + 1 :]:
                if second["start_utc"] >= first["end_utc"]:
                    break
                if first["start_utc"] < second["end_utc"] and second["start_utc"] < first["end_utc"]:
                    clashes.append((first, second))
        return clashes

    def find_free_slots(
        self,
        day: date,
        duration_minutes: int = 30,
        work_start_hour: int = 9,
        work_end_hour: int = 18,
    ) -> list[tuple[datetime, datetime]]:
        """Gaps in a working day large enough for a meeting, in local time."""
        window_start = self.to_utc(datetime.combine(day, time(hour=work_start_hour)))
        window_end = self.to_utc(datetime.combine(day, time(hour=work_end_hour)))
        needed = timedelta(minutes=max(1, duration_minutes))

        busy = [
            (e["start_utc"], e["end_utc"] or e["start_utc"])
            for e in self.events_between(window_start, window_end)
            if not e["all_day"]
        ]
        busy.sort()

        free: list[tuple[datetime, datetime]] = []
        cursor = window_start
        for busy_start, busy_end in busy:
            if busy_start - cursor >= needed:
                free.append((self.to_local(cursor), self.to_local(busy_start)))
            cursor = max(cursor, busy_end)
        if window_end - cursor >= needed:
            free.append((self.to_local(cursor), self.to_local(window_end)))
        return free

    # -- spoken output ---------------------------------------------------
    def describe_agenda(self, day: date | None = None) -> str:
        """A briefing worded for text-to-speech."""
        target = day or self.to_local(utc_now()).date()
        events = self.events_on(target)
        label = "today" if target == self.to_local(utc_now()).date() else target.strftime("%d %B")

        if not events:
            return f"Your calendar is clear {label}, sir."

        lines = [f"You have {len(events)} item{'s' if len(events) != 1 else ''} {label}, sir:"]
        for event in events:
            if event["all_day"]:
                lines.append(f"  - {event['title']} (all day)")
            else:
                stamp = event["start_local"].strftime("%I:%M %p").lstrip("0")
                where = f" at {event['location']}" if event["location"] else ""
                lines.append(f"  - {stamp}: {event['title']}{where}")

        conflicts = [
            (a, b)
            for a, b in self.find_conflicts()
            if self.to_local(a["start_utc"]).date() == target
        ]
        if conflicts:
            lines.append(
                f"Note: {len(conflicts)} scheduling conflict"
                f"{'s' if len(conflicts) != 1 else ''} detected."
            )
        return "\n".join(lines)

    # -- .ics interoperability -------------------------------------------
    @staticmethod
    def _unfold_ics(text: str) -> list[str]:
        """RFC 5545 line unfolding: continuation lines begin with space or tab."""
        lines: list[str] = []
        for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            if raw[:1] in (" ", "\t") and lines:
                lines[-1] += raw[1:]
            else:
                lines.append(raw)
        return lines

    @staticmethod
    def _unescape(value: str) -> str:
        return (
            value.replace("\\N", "\n")
            .replace("\\n", "\n")
            .replace("\\,", ",")
            .replace("\\;", ";")
            .replace("\\\\", "\\")
        )

    @staticmethod
    def _escape(value: str) -> str:
        return (
            (value or "")
            .replace("\\", "\\\\")
            .replace(";", "\\;")
            .replace(",", "\\,")
            .replace("\n", "\\n")
        )

    def _parse_ics_datetime(self, value: str, params: dict) -> tuple[datetime, bool]:
        """Parse DTSTART/DTEND. Returns (datetime, is_all_day).

        Handles the three forms real calendars emit: UTC (trailing Z), a named
        TZID, and floating local time. VALUE=DATE means an all-day event.
        """
        raw = value.strip()
        if params.get("VALUE") == "DATE" or (len(raw) == 8 and raw.isdigit()):
            parsed = datetime.strptime(raw, "%Y%m%d")
            return self.to_utc(parsed), True

        if raw.endswith("Z"):
            return datetime.strptime(raw, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc), False

        naive = datetime.strptime(raw, "%Y%m%dT%H%M%S")
        tzid = params.get("TZID")
        if tzid and ZoneInfo is not None:
            try:
                return naive.replace(tzinfo=ZoneInfo(tzid)).astimezone(timezone.utc), False
            except Exception:
                logger.warning(f"Calendar: unknown TZID '{tzid}', treating as local time")
        return self.to_utc(naive), False

    def import_ics(self, path: str, source: str = "ics") -> str:
        """Import a .ics export from any calendar product. No credentials needed."""
        full = os.path.abspath(os.path.expanduser(path))
        if not os.path.exists(full):
            return f"Sir, I could not find a calendar file at {path}."

        try:
            with open(full, "r", encoding="utf-8", errors="ignore") as handle:
                lines = self._unfold_ics(handle.read())
        except Exception as e:
            logger.error(f"Calendar: failed to read {full}: {e}")
            return f"I could not read that calendar file: {e}"

        imported, skipped, inside = 0, 0, False
        current: dict = {}

        for line in lines:
            upper = line.strip().upper()
            if upper == "BEGIN:VEVENT":
                inside, current = True, {}
                continue
            if upper == "END:VEVENT":
                inside = False
                try:
                    if "DTSTART" in current and current.get("SUMMARY"):
                        self.add_event(
                            title=current["SUMMARY"],
                            start=current["DTSTART"][0],
                            end=current.get("DTEND", (None, False))[0],
                            location=current.get("LOCATION"),
                            notes=current.get("DESCRIPTION"),
                            all_day=current["DTSTART"][1],
                            recurrence=current.get("RECURRENCE", "none"),
                            source=source,
                            external_uid=current.get("UID"),
                            start_is_local=False,
                        )
                        imported += 1
                    else:
                        skipped += 1
                except Exception as e:
                    skipped += 1
                    logger.warning(f"Calendar: skipped one .ics event: {e}")
                continue

            if not inside or ":" not in line:
                continue

            name_part, _, value = line.partition(":")
            segments = name_part.split(";")
            key = segments[0].upper()
            params = {}
            for segment in segments[1:]:
                if "=" in segment:
                    param_key, param_value = segment.split("=", 1)
                    params[param_key.upper()] = param_value.strip('"')

            try:
                if key in ("DTSTART", "DTEND"):
                    current[key] = self._parse_ics_datetime(value, params)
                elif key in ("SUMMARY", "LOCATION", "DESCRIPTION", "UID"):
                    current[key] = self._unescape(value.strip())
                elif key == "RRULE":
                    match = re.search(r"FREQ=([A-Z]+)", value.upper())
                    freq = match.group(1).lower() if match else ""
                    current["RECURRENCE"] = (
                        freq if freq in RECURRENCE_RULES else "none"
                    )
            except Exception as e:
                logger.warning(f"Calendar: could not parse '{key}' in .ics: {e}")

        self.db.audit(
            actor="calendar",
            action="import_ics",
            target=full,
            risk="local_write",
            outcome="ok",
            detail=f"imported={imported} skipped={skipped}",
        )
        message = f"Imported {imported} event{'s' if imported != 1 else ''} from that calendar, sir."
        if skipped:
            message += f" {skipped} entr{'ies' if skipped != 1 else 'y'} could not be read."
        return message

    def export_ics(self, path: str, days_ahead: int = 365) -> str:
        """Write upcoming events to a .ics file any calendar app can import."""
        full = os.path.abspath(os.path.expanduser(path))
        parent = os.path.dirname(full)
        if parent:
            os.makedirs(parent, exist_ok=True)

        # Include yesterday so an event in progress is not dropped from the export.
        window_start = utc_now() - timedelta(days=1)
        window_end = utc_now() + timedelta(days=max(1, days_ahead))
        rows = self.db.query(
            "SELECT * FROM calendar_events"
            " WHERE start_utc >= ? AND start_utc <= ? ORDER BY start_utc",
            (to_iso(window_start), to_iso(window_end)),
        )

        out = [

            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//JARVIS//Local Calendar//EN",
            "CALSCALE:GREGORIAN",
        ]
        for row in rows:
            start = from_iso(row["start_utc"])
            # Kept out of the f-string below: nesting same-quote f-strings only
            # parses on Python 3.12+, and this should run on 3.10 too.
            uid = row["external_uid"] or f"jarvis-{row['id']}@local"
            out.append("BEGIN:VEVENT")
            out.append(f"UID:{uid}")

            out.append(f"DTSTAMP:{utc_now().strftime('%Y%m%dT%H%M%SZ')}")
            if row["all_day"]:
                out.append(f"DTSTART;VALUE=DATE:{start.strftime('%Y%m%d')}")
            else:
                out.append(f"DTSTART:{start.strftime('%Y%m%dT%H%M%SZ')}")
                if row["end_utc"]:
                    out.append(f"DTEND:{from_iso(row['end_utc']).strftime('%Y%m%dT%H%M%SZ')}")
            out.append(f"SUMMARY:{self._escape(row['title'])}")
            if row["location"]:
                out.append(f"LOCATION:{self._escape(row['location'])}")
            if row["notes"]:
                out.append(f"DESCRIPTION:{self._escape(row['notes'])}")
            if (row["recurrence"] or "none") != "none":
                out.append(f"RRULE:FREQ={row['recurrence'].upper()}")
            out.append("END:VEVENT")
        out.append("END:VCALENDAR")

        try:
            with open(full, "w", encoding="utf-8", newline="\r\n") as handle:
                handle.write("\r\n".join(out))
        except Exception as e:
            logger.error(f"Calendar: export failed: {e}")
            return f"I could not write that calendar file: {e}"

        self.db.audit(
            actor="calendar", action="export_ics", target=full, risk="local_write", outcome="ok"
        )
        return f"Exported {len(rows)} events to {full}, sir. Any calendar app can import that file."

    # -- migration -------------------------------------------------------
    def migrate_legacy_json(self, path: str = "config/calendar.json") -> str:
        """Pull events out of the old flat JSON file, once."""
        full = os.path.abspath(os.path.expanduser(path))
        if not os.path.exists(full):
            return "No legacy calendar file to migrate."

        try:
            with open(full, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception as e:
            return f"Could not read the legacy calendar file: {e}"

        entries = data if isinstance(data, list) else data.get("events", [])
        migrated = 0
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            title = entry.get("title") or entry.get("name") or entry.get("event")
            when = entry.get("start") or entry.get("datetime") or entry.get("date") or entry.get("time")
            if not title or not when:
                continue
            try:
                start = from_iso(when) if ("T" in str(when) or "-" in str(when)) else None
                if start is None:
                    continue
                self.add_event(
                    title=str(title),
                    start=start,
                    location=entry.get("location"),
                    notes=entry.get("notes") or entry.get("description"),
                    source="legacy_json",
                    external_uid=f"legacy-{migrated}-{title}"[:120],
                    start_is_local=False,
                )
                migrated += 1
            except Exception as e:
                logger.warning(f"Calendar: could not migrate legacy entry '{title}': {e}")

        return f"Migrated {migrated} event{'s' if migrated != 1 else ''} from the legacy calendar file."
