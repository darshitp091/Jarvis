"""Shared SQLite layer for JARVIS services.

Every long-lived fact JARVIS needs to survive a restart lives here instead of
in loose JSON files: calendar events, reminders, scheduled jobs, and the audit
trail of actions JARVIS took.

Design notes:
  * One connection per Database instance, guarded by a re-entrant lock, so the
    voice thread, the scheduler thread, and the proactive monitor thread can
    all share it safely.
  * Schema changes are applied as ordered, idempotent migrations tracked in a
    schema_version table, so an existing install upgrades in place.
  * All timestamps are stored as ISO-8601 UTC strings. Local time is a
    presentation concern handled at the edges.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timezone

from loguru import logger

DEFAULT_DB_PATH = os.path.join("config", "jarvis.db")


def utc_now() -> datetime:
    """Timezone-aware current UTC time."""
    return datetime.now(timezone.utc)


def to_iso(dt: datetime) -> str:
    """Serialize a datetime to an ISO-8601 UTC string.

    Naive datetimes are assumed to already be UTC, which keeps callers that
    build times with datetime.utcnow() from silently shifting.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def from_iso(value: str) -> datetime:
    """Parse an ISO-8601 string back into an aware UTC datetime."""
    if not value:
        raise ValueError("Cannot parse an empty timestamp")
    text = value.strip()
    # sqlite/older writers may use a space separator or a trailing Z.
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    if " " in text and "T" not in text:
        text = text.replace(" ", "T", 1)
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# Ordered migrations. Append only; never edit a released entry, since installs
# in the wild have already recorded it as applied.
MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        """
        CREATE TABLE IF NOT EXISTS calendar_events (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            title         TEXT    NOT NULL,
            start_utc     TEXT    NOT NULL,
            end_utc       TEXT,
            location      TEXT,
            notes         TEXT,
            all_day       INTEGER NOT NULL DEFAULT 0,
            -- Recurrence as a simple rule JARVIS can reason about out loud:
            -- one of none/daily/weekly/monthly/yearly.
            recurrence    TEXT    NOT NULL DEFAULT 'none',
            -- Where this event came from: local, ics, caldav, outlook.
            source        TEXT    NOT NULL DEFAULT 'local',
            -- Stable id from the external source, used to de-duplicate imports.
            external_uid  TEXT,
            created_utc   TEXT    NOT NULL,
            updated_utc   TEXT    NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_events_start ON calendar_events (start_utc);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_events_external
            ON calendar_events (source, external_uid)
            WHERE external_uid IS NOT NULL;

        CREATE TABLE IF NOT EXISTS scheduled_jobs (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            kind           TEXT    NOT NULL,
            payload        TEXT    NOT NULL DEFAULT '{}',
            next_run_utc   TEXT    NOT NULL,
            recurrence     TEXT    NOT NULL DEFAULT 'none',
            interval_secs  INTEGER,
            status         TEXT    NOT NULL DEFAULT 'pending',
            last_run_utc   TEXT,
            last_error     TEXT,
            run_count      INTEGER NOT NULL DEFAULT 0,
            created_utc    TEXT    NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_jobs_due
            ON scheduled_jobs (status, next_run_utc);

        CREATE TABLE IF NOT EXISTS audit_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_utc       TEXT NOT NULL,
            actor        TEXT NOT NULL,
            action       TEXT NOT NULL,
            target       TEXT,
            risk         TEXT NOT NULL DEFAULT 'read',
            approved     INTEGER NOT NULL DEFAULT 1,
            outcome      TEXT,
            detail       TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log (ts_utc);
        """,
    ),
]


class Database:
    """Thread-safe SQLite wrapper with versioned migrations."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = os.path.abspath(os.path.expanduser(db_path))
        parent = os.path.dirname(self.db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

        with self._lock:
            # WAL keeps the scheduler's writes from blocking dashboard reads.
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.execute("PRAGMA busy_timeout=5000")
        self._migrate()

    # -- schema ----------------------------------------------------------
    def _migrate(self) -> None:
        with self._lock:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_version ("
                " version INTEGER PRIMARY KEY,"
                " applied_utc TEXT NOT NULL)"
            )
            applied = {
                row["version"]
                for row in self._conn.execute("SELECT version FROM schema_version")
            }

            for version, script in MIGRATIONS:
                if version in applied:
                    continue
                try:
                    self._conn.executescript(script)
                    self._conn.execute(
                        "INSERT INTO schema_version (version, applied_utc) VALUES (?, ?)",
                        (version, to_iso(utc_now())),
                    )
                    self._conn.commit()
                    logger.info(f"Database: applied migration v{version}")
                except Exception as e:
                    self._conn.rollback()
                    logger.error(f"Database: migration v{version} failed: {e}")
                    raise

    @property
    def schema_version(self) -> int:
        row = self.query_one("SELECT MAX(version) AS v FROM schema_version")
        return int(row["v"]) if row and row["v"] is not None else 0

    # -- primitives ------------------------------------------------------
    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """Run a write statement and commit."""
        with self._lock:
            try:
                cur = self._conn.execute(sql, params)
                self._conn.commit()
                return cur
            except Exception:
                self._conn.rollback()
                raise

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return list(self._conn.execute(sql, params))

    def query_one(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except Exception:
                pass

    # -- audit -----------------------------------------------------------
    def audit(
        self,
        actor: str,
        action: str,
        target: str | None = None,
        risk: str = "read",
        approved: bool = True,
        outcome: str | None = None,
        detail: str | None = None,
    ) -> int:
        """Record an action JARVIS performed.

        Anything that writes outside the local database, spends money, or
        deletes data should land here so the user can review what happened.
        """
        cur = self.execute(
            "INSERT INTO audit_log"
            " (ts_utc, actor, action, target, risk, approved, outcome, detail)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                to_iso(utc_now()),
                actor,
                action,
                target,
                risk,
                1 if approved else 0,
                outcome,
                detail,
            ),
        )
        return int(cur.lastrowid)
