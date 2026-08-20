"""Tests for the natural-language time parser.

A fixed `now` is passed everywhere so results never depend on when the suite
runs. Reminders firing at the wrong time is the failure mode that matters most
here, so the ambiguity rules get the most coverage.
"""

from datetime import datetime

import pytest

from jarvis.services.timeparse import describe, parse_when

# Wednesday, 15 May 2024, 14:30 local.
NOW = datetime(2024, 5, 15, 14, 30)


# -- relative offsets ----------------------------------------------------


@pytest.mark.parametrize(
    "text,expected_minutes",
    [
        ("remind me to call mom in 10 minutes", 10),
        ("remind me in ten minutes to call mom", 10),
        ("in 1 hour remind me to stretch", 60),
        ("remind me to drink water in half an hour", 30),
        ("mujhe 20 minute baad yaad dila do paani peene ke liye", 20),
        ("remind me in 2 days to pay rent", 2 * 24 * 60),
        ("remind me to submit the form in a week", 7 * 24 * 60),
    ],
)
def test_relative_offsets(text, expected_minutes):
    parsed = parse_when(text, now=NOW)
    assert parsed is not None
    assert (parsed.run_at - NOW).total_seconds() == pytest.approx(expected_minutes * 60)
    assert parsed.recurrence == "none"


def test_relative_offset_keeps_subject():
    parsed = parse_when("remind me to call mom in 10 minutes", now=NOW)
    assert parsed.subject == "call mom"


def test_seconds_are_not_rounded_away():
    parsed = parse_when("remind me in 30 seconds", now=NOW)
    assert (parsed.run_at - NOW).total_seconds() == 30


# -- explicit clock times ------------------------------------------------


def test_explicit_pm_today():
    parsed = parse_when("remind me to call the bank at 5 pm", now=NOW)
    assert parsed.run_at == datetime(2024, 5, 15, 17, 0)
    assert parsed.subject == "call the bank"


def test_explicit_am_rolls_to_tomorrow():
    # 6 AM has already passed at 14:30, so the next 6 AM is tomorrow.
    parsed = parse_when("wake me up at 6 am", now=NOW)
    assert parsed.run_at == datetime(2024, 5, 16, 6, 0)


def test_bare_hour_prefers_the_nearest_future_slot():
    # "at 5" at half past two means 5 PM today, not 5 AM tomorrow.
    parsed = parse_when("remind me to leave at 5", now=NOW)
    assert parsed.run_at == datetime(2024, 5, 15, 17, 0)


def test_bare_hour_already_passed_moves_to_tomorrow():
    # At 20:00, "at 7" cannot mean 7 PM today or 7 AM today.
    parsed = parse_when("remind me at 7", now=datetime(2024, 5, 15, 20, 0))
    assert parsed.run_at == datetime(2024, 5, 16, 7, 0)


def test_minutes_are_parsed():
    parsed = parse_when("set a reminder at 9:45 pm to lock up", now=NOW)
    assert parsed.run_at == datetime(2024, 5, 15, 21, 45)


def test_noon_and_midnight():
    assert parse_when("remind me at noon", now=NOW).run_at == datetime(2024, 5, 16, 12, 0)
    assert parse_when("remind me at midnight", now=NOW).run_at == datetime(2024, 5, 16, 0, 0)


def test_a_bare_number_is_not_a_time():
    # Without at/am/pm there is no time here, so the caller can fall back.
    assert parse_when("remind me to buy 3 apples") is None


def test_no_time_expression_returns_none():
    assert parse_when("remind me to call mom") is None
    assert parse_when("") is None
    assert parse_when(None) is None


def test_invalid_clock_is_rejected():
    assert parse_when("remind me at 99", now=NOW) is None


# -- day references ------------------------------------------------------


def test_tomorrow_with_time():
    parsed = parse_when("remind me to email the report tomorrow at 9 am", now=NOW)
    assert parsed.run_at == datetime(2024, 5, 16, 9, 0)
    assert parsed.subject == "email the report"


def test_kal_is_tomorrow():
    parsed = parse_when("kal subah 9 baje meeting ka reminder", now=NOW)
    assert parsed.run_at == datetime(2024, 5, 16, 9, 0)


def test_day_after_tomorrow():
    parsed = parse_when("remind me parson at 11 am", now=NOW)
    assert parsed.run_at == datetime(2024, 5, 17, 11, 0)


def test_day_without_time_defaults_to_morning_and_flags_vague():
    parsed = parse_when("remind me tomorrow to renew the licence", now=NOW)
    assert parsed.run_at == datetime(2024, 5, 16, 9, 0)
    assert parsed.is_vague is True


def test_weekday_moves_forward():
    # NOW is a Wednesday; Friday is two days out.
    parsed = parse_when("remind me on friday at 4 pm", now=NOW)
    assert parsed.run_at == datetime(2024, 5, 17, 16, 0)


def test_same_weekday_means_next_week():
    # Asking for Wednesday on a Wednesday means the next one.
    parsed = parse_when("remind me on wednesday at 4 pm", now=NOW)
    assert parsed.run_at == datetime(2024, 5, 22, 16, 0)


def test_explicit_date():
    parsed = parse_when("remind me on 5 august at 10 am to file taxes", now=NOW)
    assert parsed.run_at == datetime(2024, 8, 5, 10, 0)


def test_past_date_rolls_to_next_year():
    parsed = parse_when("remind me on 3 january at 10 am", now=NOW)
    assert parsed.run_at == datetime(2025, 1, 3, 10, 0)


def test_month_first_date_order():
    parsed = parse_when("remind me on august 5 at 10 am", now=NOW)
    assert parsed.run_at == datetime(2024, 8, 5, 10, 0)


# -- vague dayparts ------------------------------------------------------


def test_tonight_infers_an_evening_hour():
    parsed = parse_when("remind me tonight to charge the phone", now=NOW)
    assert parsed.run_at == datetime(2024, 5, 15, 21, 0)
    assert parsed.is_vague is True


def test_tomorrow_evening():
    parsed = parse_when("remind me tomorrow evening to water the plants", now=NOW)
    assert parsed.run_at == datetime(2024, 5, 16, 18, 0)


def test_hinglish_daypart():
    parsed = parse_when("kal shaam yaad dila do", now=NOW)
    assert parsed.run_at == datetime(2024, 5, 16, 18, 0)


# -- recurrence ----------------------------------------------------------


def test_daily_recurrence():
    parsed = parse_when("remind me every day at 8 am to take my medicine", now=NOW)
    assert parsed.recurrence == "daily"
    assert parsed.run_at == datetime(2024, 5, 16, 8, 0)
    assert parsed.subject == "take my medicine"


def test_hinglish_daily_recurrence():
    parsed = parse_when("har roz raat 10 baje yaad dila do", now=NOW)
    assert parsed.recurrence == "daily"
    assert parsed.run_at.hour == 22


def test_weekly_on_a_named_day():
    parsed = parse_when("remind me every monday at 9 am to send the update", now=NOW)
    assert parsed.recurrence == "weekly"
    assert parsed.run_at == datetime(2024, 5, 20, 9, 0)


def test_interval_recurrence():
    parsed = parse_when("remind me every 30 minutes to stand up", now=NOW)
    assert parsed.recurrence == "interval"
    assert parsed.interval_secs == 1800
    assert parsed.run_at == NOW.replace(minute=0, hour=15)
    assert parsed.subject == "stand up"


def test_hourly_recurrence():
    parsed = parse_when("remind me every hour to check the oven", now=NOW)
    assert parsed.recurrence == "hourly"


def test_monthly_recurrence():
    parsed = parse_when("remind me every month on the 1 at 9 am to pay rent", now=NOW)
    assert parsed.recurrence == "monthly"


# -- spoken descriptions -------------------------------------------------


def test_describe_today_and_tomorrow():
    assert describe(datetime(2024, 5, 15, 17, 0), now=NOW) == "today at 5:00 PM"
    assert describe(datetime(2024, 5, 16, 6, 30), now=NOW) == "tomorrow at 6:30 AM"


def test_describe_weekday_and_far_date():
    assert describe(datetime(2024, 5, 17, 16, 0), now=NOW) == "Friday at 4:00 PM"
    assert describe(datetime(2024, 8, 5, 10, 0), now=NOW) == "05 August at 10:00 AM"


def test_describe_recurring():
    assert describe(datetime(2024, 5, 16, 8, 0), now=NOW, recurrence="daily") == (
        "every day at 8:00 AM"
    )
    assert describe(
        datetime(2024, 5, 15, 15, 0), now=NOW, recurrence="interval", interval_secs=1800
    ) == "every 30 minute(s), starting at 3:00 PM"
