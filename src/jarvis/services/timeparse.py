"""Natural-language time parsing for JARVIS reminders and calendar commands.

Speech gives us "remind me to call mom in ten minutes" or "meeting kal subah
9 baje". The scheduler needs a concrete datetime plus a recurrence rule. This
module bridges that gap using only the standard library, so it works offline and
adds no dependency.

Scope is deliberately narrow: the phrasings a person actually says out loud to an
assistant. Anything it cannot parse returns None, letting the caller fall back to
the LLM instead of guessing a wrong time and firing an alarm at 3am.

Times are naive local wall-clock datetimes. Converting to UTC is the caller's
job, since only the calendar/scheduler layer knows the configured timezone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

# --------------------------------------------------------------------------
# Vocabulary
# --------------------------------------------------------------------------

# Hinglish terms are included because the wake word and STT models in this
# project are Hinglish-tuned, so mixed-language commands are the norm.
_UNIT_SECONDS: dict[str, int] = {
    "sec": 1, "secs": 1, "second": 1, "seconds": 1,
    "min": 60, "mins": 60, "minute": 60, "minutes": 60, "minit": 60,
    "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600,
    "ghanta": 3600, "ghante": 3600, "ghanto": 3600,
    "day": 86400, "days": 86400, "din": 86400,
    "week": 604800, "weeks": 604800, "hafta": 604800, "hafte": 604800,
}

_WORD_NUMBERS: dict[str, int] = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40,
    "forty five": 45, "fortyfive": 45, "sixty": 60,
    # Hinglish numerals
    "ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "panch": 5,
    "paanch": 5, "chhe": 6, "che": 6, "saat": 7, "aath": 8, "nau": 9,
    "das": 10, "gyarah": 11, "barah": 12, "pandrah": 15, "bees": 20,
    "tees": 30,
}

_WEEKDAYS: dict[str, int] = {
    "monday": 0, "mon": 0, "somvar": 0,
    "tuesday": 1, "tue": 1, "tues": 1, "mangalvar": 1,
    "wednesday": 2, "wed": 2, "budhvar": 2,
    "thursday": 3, "thu": 3, "thurs": 3, "guruvar": 3,
    "friday": 4, "fri": 4, "shukravar": 4,
    "saturday": 5, "sat": 5, "shanivar": 5,
    "sunday": 6, "sun": 6, "ravivar": 6,
}

_MONTHS: dict[str, int] = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}

# Vague parts of the day, mapped to a concrete hour so "remind me tomorrow
# morning" produces something actionable.
_DAYPARTS: dict[str, int] = {
    "morning": 9, "subah": 9, "savere": 9,
    "noon": 12, "dopahar": 13, "afternoon": 15,
    "evening": 18, "shaam": 18,
    "night": 21, "raat": 21, "tonight": 21, "aaj raat": 21,
    "midnight": 0,
}

_RECURRENCE_WORDS: dict[str, str] = {
    "daily": "daily", "everyday": "daily", "every day": "daily",
    "har roz": "daily", "roz": "daily", "rozana": "daily", "har din": "daily",
    "hourly": "hourly", "every hour": "hourly", "har ghante": "hourly",
    "weekly": "weekly", "every week": "weekly", "har hafte": "weekly",
    "monthly": "monthly", "every month": "monthly", "har mahine": "monthly",
    "yearly": "yearly", "annually": "yearly", "every year": "yearly",
    "every minute": "minutely",
}

# Filler left behind after the time phrase is removed.
_LEADING_FILLER = re.compile(
    r"^(?:please\s+|jarvis\s+|hey\s+|remind\s+me\s+(?:to\s+|that\s+|about\s+)?"
    r"|reminder\s+(?:set\s+)?(?:kar\s*do\s+|karo\s+)?(?:to\s+|for\s+|ki\s+)?"
    r"|set\s+(?:a\s+|an\s+)?(?:reminder|alarm)\s+(?:to\s+|for\s+|that\s+)?"
    r"|mujhe\s+|muje\s+|yaad\s+dila\s*(?:do|dena)?\s+(?:ki\s+)?"
    r"|wake\s+me\s+up\s+|alarm\s+(?:lagao|laga\s*do|set\s*karo)\s+)+",
    re.IGNORECASE,
)

_TRAILING_FILLER = re.compile(
    r"(?:\s+(?:please|jarvis|sir|par|pe|ko|ka|ki|hai|ke\s+liye|for|on\s+phone"
    r"|on\s+mobile|yaad\s+dila\s*(?:do|dena)?|reminder|ka\s+reminder))+$",
    re.IGNORECASE,
)


@dataclass
class ParsedWhen:
    """A resolved time expression.

    Attributes:
        run_at: Naive local wall-clock datetime of the first occurrence.
        recurrence: One of none/minutely/hourly/daily/weekly/monthly/yearly/interval.
        interval_secs: Set only when recurrence == "interval".
        subject: The command text with the time phrase removed, e.g. "call mom".
        is_vague: True when the time of day was inferred rather than stated,
            which lets the caller read the assumption back to the user.
    """

    run_at: datetime
    recurrence: str = "none"
    interval_secs: int | None = None
    subject: str = ""
    is_vague: bool = False


def _normalize(text: str) -> str:
    """Lowercase, drop punctuation that STT sprinkles in, collapse whitespace."""
    cleaned = re.sub(r"[,\.\!\?\"']", " ", (text or "").lower())
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _to_number(token: str) -> int | None:
    token = (token or "").strip()
    if not token:
        return None
    if token.isdigit():
        return int(token)
    return _WORD_NUMBERS.get(token)


def _clean_subject(text: str) -> str:
    subject = re.sub(r"\s+", " ", text or "").strip()
    subject = _LEADING_FILLER.sub("", subject).strip()
    subject = _TRAILING_FILLER.sub("", subject).strip()
    # Drop a dangling connector left where the time phrase used to be.
    subject = re.sub(r"\s+(?:at|on|in|by|every|har)$", "", subject, flags=re.IGNORECASE).strip()
    return subject


def _cut(text: str, match: re.Match) -> str:
    """Remove a matched span, leaving a single space in its place."""
    return (text[: match.start()] + " " + text[match.end():]).strip()


# --------------------------------------------------------------------------
# Component parsers
# --------------------------------------------------------------------------

_NUM = r"\d+|" + "|".join(sorted((re.escape(w) for w in _WORD_NUMBERS), key=len, reverse=True))
_UNIT = "|".join(sorted((re.escape(u) for u in _UNIT_SECONDS), key=len, reverse=True))

_RELATIVE_EN = re.compile(rf"\b(?:in|after|within)\s+({_NUM})\s+({_UNIT})\b", re.IGNORECASE)
_RELATIVE_HI = re.compile(rf"\b({_NUM})\s+({_UNIT})\s+(?:baad|bad|me|mein)\b", re.IGNORECASE)

# "half an hour" is its own shape: the fraction applies to the unit rather than
# being a count of it, so it is matched before the generic number+unit rules.
_RELATIVE_HALF = re.compile(
    rf"\b(?:in|after|within)?\s*(?:half|aadha|adha)\s+(?:a\s+|an\s+)?({_UNIT})"
    r"(?:\s+(?:baad|bad))?\b",
    re.IGNORECASE,
)


def _parse_relative(text: str) -> tuple[int, str] | None:
    """Parse 'in 10 minutes' / '10 minute baad' / 'in half an hour'."""
    match = _RELATIVE_HALF.search(text)
    if match:
        unit = _UNIT_SECONDS.get(match.group(1).lower())
        if unit and unit >= 60:
            return unit // 2, _cut(text, match)

    for pattern in (_RELATIVE_EN, _RELATIVE_HI):
        match = pattern.search(text)
        if not match:
            continue
        count = _to_number(match.group(1))
        unit = _UNIT_SECONDS.get(match.group(2).lower())
        if count is None or not unit:
            continue
        return count * unit, _cut(text, match)
    return None


_CLOCK = re.compile(
    r"\b(?:at|@|by)?\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm|a m|p m|baje)?\b",
    re.IGNORECASE,
)


def _parse_clock(text: str) -> tuple[int, int | None, bool, str] | None:
    """Parse an explicit clock time.

    Returns (hour, minute, meridiem_known, leftover). Bare numbers are only
    accepted when introduced by at/by/@ or followed by am/pm/baje, so "call 3
    people" is not mistaken for 3 o'clock.
    """
    for match in _CLOCK.finditer(text):
        hour_raw, minute_raw, suffix = match.group(1), match.group(2), match.group(3)
        prefix = (text[max(0, match.start()): match.start() + 3] or "").lower()
        introduced = bool(re.match(r"\s*(?:at|@|by)\b", match.group(0), re.IGNORECASE)) or "at" in prefix
        if not suffix and not introduced and minute_raw is None:
            continue

        hour = int(hour_raw)
        minute = int(minute_raw) if minute_raw else 0
        if hour > 23 or minute > 59:
            continue

        suffix = (suffix or "").replace(" ", "").lower()
        meridiem_known = suffix in {"am", "pm"}
        if suffix == "pm" and hour < 12:
            hour += 12
        elif suffix == "am" and hour == 12:
            hour = 0
        elif suffix == "baje":
            # "5 baje" without subah/raat is ambiguous; treated like a bare number.
            meridiem_known = False
        return hour, minute, meridiem_known, _cut(text, match)
    return None


def _parse_daypart(text: str) -> tuple[int, str] | None:
    for word in sorted(_DAYPARTS, key=len, reverse=True):
        match = re.search(rf"\b{re.escape(word)}\b", text, re.IGNORECASE)
        if match:
            return _DAYPARTS[word], _cut(text, match)
    return None


def _parse_day(text: str, today: date) -> tuple[date, str] | None:
    """Resolve a day reference: tomorrow, next friday, on 5 august, 5/8."""
    patterns: list[tuple[re.Pattern, callable]] = [
        (re.compile(r"\b(?:day\s+after\s+tomorrow|parson)\b", re.I),
         lambda m: today + timedelta(days=2)),
        (re.compile(r"\b(?:tomorrow|tmrw|kal)\b", re.I),
         lambda m: today + timedelta(days=1)),
        (re.compile(r"\b(?:today|aaj|tonight)\b", re.I), lambda m: today),
    ]
    for pattern, resolve in patterns:
        match = pattern.search(text)
        if match:
            # "tonight" also implies an hour, so leave the word in place for
            # _parse_daypart by only cutting the day words that carry no hour.
            if pattern.pattern.find("tonight") >= 0 and match.group(0).lower() == "tonight":
                return resolve(match), text
            return resolve(match), _cut(text, match)

    # Weekday: "on monday", "next friday".
    weekday_alt = "|".join(sorted((re.escape(d) for d in _WEEKDAYS), key=len, reverse=True))
    match = re.search(rf"\b(?:on\s+|next\s+|is\s+|agle\s+)?({weekday_alt})\b", text, re.I)
    if match:
        target = _WEEKDAYS[match.group(1).lower()]
        ahead = (target - today.weekday()) % 7
        explicit_next = bool(re.search(r"\b(?:next|agle)\b", match.group(0), re.I))
        if ahead == 0 or explicit_next:
            ahead = ahead or 7
            if explicit_next and ahead < 7 and match.group(0).lower().startswith(("next", "agle")):
                ahead = ahead if ahead else 7
        return today + timedelta(days=ahead), _cut(text, match)

    # Day + month, either order.
    month_alt = "|".join(sorted((re.escape(m) for m in _MONTHS), key=len, reverse=True))
    match = re.search(rf"\b(?:on\s+)?(\d{{1,2}})(?:st|nd|rd|th)?\s+({month_alt})\b", text, re.I)
    if not match:
        match = re.search(rf"\b(?:on\s+)?({month_alt})\s+(\d{{1,2}})(?:st|nd|rd|th)?\b", text, re.I)
        if match:
            month, day = _MONTHS[match.group(1).lower()], int(match.group(2))
        else:
            month = day = None
    else:
        day, month = int(match.group(1)), _MONTHS[match.group(2).lower()]

    if match and month and day:
        year = today.year
        try:
            resolved = date(year, month, day)
        except ValueError:
            return None
        if resolved < today:
            try:
                resolved = date(year + 1, month, day)
            except ValueError:
                return None
        return resolved, _cut(text, match)
    return None


def _parse_recurrence(text: str) -> tuple[str, int | None, str] | None:
    """Detect a repeat rule. Returns (rule, interval_secs, leftover)."""
    # "every 30 minutes" becomes an interval job.
    match = re.search(rf"\b(?:every|har)\s+({_NUM})\s+({_UNIT})\b", text, re.IGNORECASE)
    if match:
        count = _to_number(match.group(1))
        unit = _UNIT_SECONDS.get(match.group(2).lower())
        if count and unit:
            return "interval", count * unit, _cut(text, match)

    for phrase in sorted(_RECURRENCE_WORDS, key=len, reverse=True):
        match = re.search(rf"\b{re.escape(phrase)}\b", text, re.IGNORECASE)
        if match:
            return _RECURRENCE_WORDS[phrase], None, _cut(text, match)

    # "every monday" / "every morning" repeat weekly and daily respectively.
    weekday_alt = "|".join(sorted((re.escape(d) for d in _WEEKDAYS), key=len, reverse=True))
    match = re.search(rf"\b(?:every|har)\s+({weekday_alt})\b", text, re.IGNORECASE)
    if match:
        # Leave the weekday in place so _parse_day can anchor the first run.
        return "weekly", None, text.replace(match.group(0), match.group(1), 1)

    daypart_alt = "|".join(sorted((re.escape(d) for d in _DAYPARTS), key=len, reverse=True))
    match = re.search(rf"\b(?:every|har)\s+({daypart_alt})\b", text, re.IGNORECASE)
    if match:
        return "daily", None, text.replace(match.group(0), match.group(1), 1)
    return None


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------


def parse_when(text: str, now: datetime | None = None) -> ParsedWhen | None:
    """Extract a time, a recurrence rule, and the remaining subject from `text`.

    Returns None when no time expression is present, which the caller should
    treat as "ask the user" rather than picking a default.
    """
    if not text or not text.strip():
        return None

    now = (now or datetime.now()).replace(microsecond=0)
    working = _normalize(text)

    recurrence, interval_secs = "none", None
    found = _parse_recurrence(working)
    if found:
        recurrence, interval_secs, working = found

    # A relative offset settles the time outright: "in 10 minutes".
    relative = _parse_relative(working)
    if relative:
        seconds, working = relative
        run_at = now + timedelta(seconds=seconds)
        return ParsedWhen(
            run_at=run_at.replace(second=0) if seconds >= 60 else run_at,
            recurrence=recurrence,
            interval_secs=interval_secs,
            subject=_clean_subject(working),
        )

    if recurrence == "interval" and interval_secs:
        return ParsedWhen(
            run_at=(now + timedelta(seconds=interval_secs)).replace(second=0),
            recurrence="interval",
            interval_secs=interval_secs,
            subject=_clean_subject(working),
        )

    day_result = _parse_day(working, now.date())
    target_day, working = day_result if day_result else (None, working)

    clock = _parse_clock(working)
    hour = minute = None
    meridiem_known = False
    is_vague = False

    if clock:
        hour, minute, meridiem_known, working = clock
    else:
        daypart = _parse_daypart(working)
        if daypart:
            hour, working = daypart
            minute, meridiem_known, is_vague = 0, True, True

    if hour is None:
        if target_day is None:
            # "every hour" carries a cadence but no clock time: start one step
            # from now rather than refusing to schedule.
            if recurrence in ("hourly", "minutely"):
                step = timedelta(hours=1) if recurrence == "hourly" else timedelta(minutes=1)
                return ParsedWhen(
                    run_at=(now + step).replace(second=0),
                    recurrence=recurrence,
                    subject=_clean_subject(working),
                )
            # No day and no cadence means there is no time here at all.
            if recurrence == "none":
                return None
        # A day (or a daily/weekly rule) with no stated time: assume morning and
        # flag it so the caller can read the assumption back.
        hour, minute, meridiem_known, is_vague = 9, 0, True, True

    run_at = datetime(
        target_day.year if target_day else now.year,
        target_day.month if target_day else now.month,
        target_day.day if target_day else now.day,
        hour,
        minute or 0,
    )

    if target_day is None and run_at <= now:
        # No explicit day: pick the nearest sensible future slot. A bare "at 5"
        # in the afternoon means 5 PM today, not 5 AM tomorrow.
        if not meridiem_known and hour < 12:
            bumped = run_at + timedelta(hours=12)
            run_at = bumped if bumped > now else run_at + timedelta(days=1)
        else:
            run_at += timedelta(days=1)

    return ParsedWhen(
        run_at=run_at,
        recurrence=recurrence,
        interval_secs=interval_secs,
        subject=_clean_subject(working),
        is_vague=is_vague,
    )


def describe(when: datetime, now: datetime | None = None, recurrence: str = "none",
             interval_secs: int | None = None) -> str:
    """Render a datetime the way JARVIS should say it out loud."""
    now = now or datetime.now()
    clock = when.strftime("%I:%M %p").lstrip("0")

    if recurrence == "interval" and interval_secs:
        if interval_secs % 3600 == 0:
            every = f"every {interval_secs // 3600} hour(s)"
        elif interval_secs % 60 == 0:
            every = f"every {interval_secs // 60} minute(s)"
        else:
            every = f"every {interval_secs} seconds"
        return f"{every}, starting at {clock}"

    repeat = {
        "minutely": "every minute",
        "hourly": "every hour",
        "daily": "every day",
        "weekly": f"every {when.strftime('%A')}",
        "monthly": f"every month on the {when.day}",
        "yearly": f"every year on {when.strftime('%d %B')}",
    }.get(recurrence)
    if repeat:
        return f"{repeat} at {clock}"

    delta_days = (when.date() - now.date()).days
    if delta_days == 0:
        return f"today at {clock}"
    if delta_days == 1:
        return f"tomorrow at {clock}"
    if 1 < delta_days < 7:
        return f"{when.strftime('%A')} at {clock}"
    return f"{when.strftime('%d %B')} at {clock}"
