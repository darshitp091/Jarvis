"""Persistent scheduler for JARVIS reminders, alarms, and recurring jobs.

Why this exists: reminders previously depended on an Android intent fired over
ADB, so they silently died whenever the phone was unplugged. This scheduler
runs on the PC, stores every job in SQLite, and therefore survives a restart.

Key behaviours:
  * Jobs are polled from the database rather than held only in memory, so a
    crash loses nothing.
  * A job that came due while JARVIS was closed still fires on the next start,
    provided it is within the misfire grace window. Older jobs are marked
    'missed' and reported rather than firing a surprise alarm at 3am.
  * Recurring jobs roll forward past any windows that elapsed while offline,
    so a daily 08:00 briefing does not fire five times after a long weekend.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone

from loguru import logger

from services.db import Database, from_iso, to_iso, utc_now

VALID_RECURRENCE = {"none", "minutely", "hourly", "daily", "weekly", "monthly", "yearly"}


def _add_months(dt: datetime, months: int) -> datetime:
    """Advance by calendar months, clamping to the end of a shorter month."""
    month_index = dt.month - 1 + months
    year = dt.year + month_index // 12
    month = month_index % 12 + 1
    days_in_month = [
        31,
        29
        if (year % 4 == 0 and year % 100 != 0) or year % 400 == 0
        else 28,
        31, 30, 31, 30, 31, 31, 30, 31, 30, 31,
    ][month - 1]
    return dt.replace(year=year, month=month, day=min(dt.day, days_in_month))


def next_occurrence(
    current: datetime,
    recurrence: str,
    interval_secs: int | None = None,
    after: datetime | None = None,
) -> datetime | None:
    """Return the next run time strictly after `after` (default: now).

    Returns None for one-shot jobs. Rolling forward in a loop keeps a daily job
    from firing repeatedly to "catch up" after JARVIS was offline.
    """
    rule = (recurrence or "none").lower()
    if rule == "none":
        return None

    reference = after or utc_now()
    nxt = current

    # Bound the loop so a malformed interval cannot spin forever.
    for _ in range(10000):
        if rule == "minutely":
            nxt += timedelta(minutes=1)
        elif rule == "hourly":
            nxt += timedelta(hours=1)
        elif rule == "daily":
            nxt += timedelta(days=1)
        elif rule == "weekly":
            nxt += timedelta(weeks=1)
        elif rule == "monthly":
            nxt = _add_months(nxt, 1)
        elif rule == "yearly":
            nxt = _add_months(nxt, 12)
        elif rule == "interval":
            if not interval_secs or interval_secs <= 0:
                return None
            nxt += timedelta(seconds=interval_secs)
        else:
            return None

        if nxt > reference:
            return nxt
    return None


class Scheduler:
    """Database-backed job runner.

    Handlers are registered by job kind. A handler receives the payload dict and
    may return a string, which is stored as the job outcome for the audit trail.
    """

    def __init__(
        self,
        db: Database,
        poll_interval: int = 20,
        misfire_grace_minutes: int = 120,
    ):
        self.db = db
        self.poll_interval = max(1, int(poll_interval))
        self.misfire_grace = timedelta(minutes=max(0, int(misfire_grace_minutes)))
        self._handlers: dict[str, callable] = {}
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    # -- registration ----------------------------------------------------
    def register_handler(self, kind: str, handler) -> None:
        self._handlers[kind] = handler
        logger.info(f"Scheduler: registered handler for job kind '{kind}'")

    # -- job management --------------------------------------------------
    def schedule(
        self,
        kind: str,
        run_at: datetime,
        payload: dict | None = None,
        recurrence: str = "none",
        interval_secs: int | None = None,
    ) -> int:
        """Persist a job and return its id."""
        rule = (recurrence or "none").lower()
        if rule not in VALID_RECURRENCE and rule != "interval":
            raise ValueError(f"Unsupported recurrence '{recurrence}'")
        if rule == "interval" and (not interval_secs or interval_secs <= 0):
            raise ValueError("An 'interval' job requires a positive interval_secs")

        cur = self.db.execute(
            "INSERT INTO scheduled_jobs"
            " (kind, payload, next_run_utc, recurrence, interval_secs, status, created_utc)"
            " VALUES (?, ?, ?, ?, ?, 'pending', ?)",
            (
                kind,
                json.dumps(payload or {}),
                to_iso(run_at),
                rule,
                interval_secs,
                to_iso(utc_now()),
            ),
        )
        job_id = int(cur.lastrowid)
        logger.info(f"Scheduler: job {job_id} ({kind}) set for {to_iso(run_at)}")
        return job_id

    def cancel(self, job_id: int) -> bool:
        cur = self.db.execute(
            "UPDATE scheduled_jobs SET status='cancelled'"
            " WHERE id=? AND status IN ('pending','missed')",
            (job_id,),
        )
        return cur.rowcount > 0

    def snooze(self, job_id: int, minutes: int) -> bool:
        """Push a job forward, which is what 'remind me again in 10 minutes' does."""
        row = self.db.query_one("SELECT id FROM scheduled_jobs WHERE id=?", (job_id,))
        if not row:
            return False
        new_time = utc_now() + timedelta(minutes=max(1, int(minutes)))
        self.db.execute(
            "UPDATE scheduled_jobs SET next_run_utc=?, status='pending' WHERE id=?",
            (to_iso(new_time), job_id),
        )
        return True

    def pending_jobs(self, kind: str | None = None) -> list[dict]:
        sql = (
            "SELECT * FROM scheduled_jobs WHERE status='pending'"
            + (" AND kind=?" if kind else "")
            + " ORDER BY next_run_utc"
        )
        rows = self.db.query(sql, (kind,) if kind else ())
        return [self._row_to_dict(r) for r in rows]

    @staticmethod
    def _row_to_dict(row) -> dict:
        data = dict(row)
        try:
            data["payload"] = json.loads(data.get("payload") or "{}")
        except json.JSONDecodeError:
            data["payload"] = {}
        return data

    # -- execution -------------------------------------------------------
    def run_due_jobs(self, now: datetime | None = None) -> int:
        """Execute everything currently due. Returns the number of jobs run.

        Called on a timer by the background thread, but exposed directly so the
        behaviour is testable without waiting on wall-clock time.
        """
        now = now or utc_now()
        rows = self.db.query(
            "SELECT * FROM scheduled_jobs WHERE status='pending' AND next_run_utc <= ?"
            " ORDER BY next_run_utc",
            (to_iso(now),),
        )

        executed = 0
        for row in rows:
            job = self._row_to_dict(row)
            job_id = job["id"]
            scheduled_for = from_iso(job["next_run_utc"])
            recurrence = job.get("recurrence") or "none"

            # Too late to fire safely: record it instead of startling the user.
            if self.misfire_grace and (now - scheduled_for) > self.misfire_grace:
                follow_up = next_occurrence(
                    scheduled_for, recurrence, job.get("interval_secs"), after=now
                )
                if follow_up:
                    self.db.execute(
                        "UPDATE scheduled_jobs SET next_run_utc=?, last_error=? WHERE id=?",
                        (to_iso(follow_up), "missed while offline", job_id),
                    )
                else:
                    self.db.execute(
                        "UPDATE scheduled_jobs SET status='missed', last_error=? WHERE id=?",
                        ("missed while offline", job_id),
                    )
                logger.warning(f"Scheduler: job {job_id} ({job['kind']}) missed while offline")
                continue

            handler = self._handlers.get(job["kind"])
            if handler is None:
                self.db.execute(
                    "UPDATE scheduled_jobs SET status='error', last_error=? WHERE id=?",
                    (f"no handler registered for kind '{job['kind']}'", job_id),
                )
                logger.error(f"Scheduler: no handler for job kind '{job['kind']}'")
                continue

            outcome, error = None, None
            try:
                outcome = handler(job["payload"])
                executed += 1
            except Exception as e:
                error = str(e)
                logger.error(f"Scheduler: job {job_id} ({job['kind']}) failed: {e}")

            follow_up = next_occurrence(
                scheduled_for, recurrence, job.get("interval_secs"), after=now
            )
            if follow_up:
                self.db.execute(
                    "UPDATE scheduled_jobs SET next_run_utc=?, last_run_utc=?,"
                    " last_error=?, run_count=run_count+1 WHERE id=?",
                    (to_iso(follow_up), to_iso(now), error, job_id),
                )
            else:
                self.db.execute(
                    "UPDATE scheduled_jobs SET status=?, last_run_utc=?,"
                    " last_error=?, run_count=run_count+1 WHERE id=?",
                    ("error" if error else "done", to_iso(now), error, job_id),
                )

            self.db.audit(
                actor="scheduler",
                action=f"job:{job['kind']}",
                target=str(job_id),
                risk="local_write",
                outcome="error" if error else "ok",
                detail=error or (str(outcome)[:500] if outcome else None),
            )
        return executed

    # -- lifecycle -------------------------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="JarvisScheduler", daemon=True
        )
        self._thread.start()
        logger.info("Scheduler: background loop started")

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.run_due_jobs()
            except Exception as e:
                # Never let one bad job kill the scheduler thread.
                logger.error(f"Scheduler: poll cycle failed: {e}")
            self._stop.wait(self.poll_interval)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Scheduler: background loop stopped")
