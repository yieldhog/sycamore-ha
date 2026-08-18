"""Unit tests for the pure data-shaping helpers."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from custom_components.sycamore.helpers import (
    clean_subject_name,
    collapse_ws,
    detect_kind,
    humanize_title,
    parse_due_date,
    parse_event_time,
    strip_html,
    subject_emoji,
    subject_icon,
    to_float,
)


def test_parse_event_time_all_day():
    result = parse_event_time(
        {"Datetime": "2026-08-17 06:00:00", "Duration": "00:00", "AllDay": 1}
    )
    assert result == (datetime(2026, 8, 17, 6, 0, 0), timedelta(), True)


def test_parse_event_time_timed_with_duration():
    start, duration, all_day = parse_event_time(
        {"Datetime": "2026-08-14 16:00:00", "Duration": "00:45", "AllDay": 0}
    )
    assert start == datetime(2026, 8, 14, 16, 0, 0)
    assert duration == timedelta(minutes=45)
    assert all_day is False


@pytest.mark.parametrize("bad", [{}, {"Datetime": ""}, {"Datetime": "nope"}])
def test_parse_event_time_bad_rows(bad):
    assert parse_event_time(bad) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("6H Mathematics", "Mathematics"),
        ("2nd Grade-Science", "Science"),  # regression: prefix fully stripped
        ("2nd Grade- Science", "Science"),
        ("Mathematics", "Mathematics"),
        ("", ""),
        (None, ""),
    ],
)
def test_clean_subject_name(raw, expected):
    assert clean_subject_name(raw) == expected


@pytest.mark.parametrize(
    ("title", "is_test", "label"),
    [
        ("Chapter 3 Quiz", True, "Quiz"),
        ("Unit Test", True, "Test"),
        ("Midterm Exam", True, "Test"),
        ("Final Exam", True, "Test"),
        ("final draft", False, ""),  # "final" alone is not a cue
        ("contest entry", False, ""),  # "test" must be a whole word
        ("Reading log", False, ""),
        ("Unit 3 Assessment", True, "Test"),  # bare assessment => test
        # "assessment" downgraded when a homework word is present.
        ("HIS Chap 11 Lesson 1 Assessment questions 1-4", False, ""),
        ("Chapter 2 Assessment worksheet", False, ""),
        ("Exam review questions", True, "Test"),  # strong cue still wins
    ],
)
def test_detect_kind(title, is_test, label):
    assert detect_kind(title) == (is_test, label)


def test_parse_clock_time():
    from datetime import time

    from custom_components.sycamore.helpers import parse_clock_time

    assert parse_clock_time("08:00:00") == time(8, 0)
    assert parse_clock_time("08:00") == time(8, 0)
    assert parse_clock_time(None) is None
    assert parse_clock_time("") is None
    assert parse_clock_time("not-a-time") is None


def test_detect_kind_description_suppresses_assessment():
    """A homework word in the description also vetoes the weak 'assessment' cue."""
    assert detect_kind("Unit 3 Assessment", "These questions are due for homework") == (
        False,
        "",
    )
    # Without the homework context, the same title is a test.
    assert detect_kind("Unit 3 Assessment", "Bring a pencil") == (True, "Test")


def test_strip_html():
    assert strip_html("<p>Study 1-10</p>") == "Study 1-10"
    assert strip_html("line a<br>line b") == "line a line b"
    assert strip_html("Tom &amp; Jerry") == "Tom & Jerry"
    assert strip_html(None) == ""


def test_parse_due_date():
    assert parse_due_date("01/15/2026") == date(2026, 1, 15)
    # Official homework/missing examples use two-digit years (MM/DD/YY).
    assert parse_due_date("01/31/13") == date(2013, 1, 31)
    assert parse_due_date("garbage") is None
    assert parse_due_date(None) is None


def test_subject_icon():
    assert subject_icon("Mathematics") == "mdi:calculator-variant"
    assert subject_icon("Science") == "mdi:flask"
    assert subject_icon("Spanish") == "mdi:earth"
    assert subject_icon("Underwater Basket Weaving") == "mdi:notebook"


def test_subject_emoji():
    assert subject_emoji("Mathematics") == "📐"
    assert subject_emoji("Science") == "🧪"
    assert subject_emoji("History") == "📜"
    assert subject_emoji("English") == "📚"
    assert subject_emoji("Spanish") == "🌍"
    # Unknown subjects fall back to a generic assignment emoji.
    assert subject_emoji("Underwater Basket Weaving") == "📝"
    assert subject_emoji("") == "📝"
    assert subject_emoji(None) == "📝"


@pytest.mark.parametrize(
    ("title", "subject", "expected"),
    [
        # The class code is translated to the real class name.
        ("HIS Introduction.", "History", "History: Introduction."),
        (
            "HIS Chap 11 Lesson 1 Assessment questions 1-4",
            "History",
            "History: Chap 11 Lesson 1 Assessment questions 1-4",
        ),
        # A caps word that is NOT an acronym of the subject is left alone.
        ("READ pages 1-10", "History", "READ pages 1-10"),
        # No leading code at all — unchanged.
        ("Science Notebook Check Week", "Science", "Science Notebook Check Week"),
        # Mid-title caps ("READ") must not be touched — only the leading code.
        ("HIS Chap 11 READ Lesson 1", "History", "History: Chap 11 READ Lesson 1"),
        # Code-only title collapses to the class name.
        ("MAT", "Mathematics", "Mathematics"),
        # Missing subject or title is a safe no-op.
        ("HIS Introduction.", "", "HIS Introduction."),
        ("", "History", ""),
        (None, "History", ""),
    ],
)
def test_humanize_title(title, subject, expected):
    assert humanize_title(title, subject) == expected


def test_to_float():
    assert to_float("92.5") == 92.5
    assert to_float(88) == 88.0
    assert to_float(None) is None
    assert to_float("not a number") is None


def test_collapse_ws():
    # The CR/LF that Sycamore embeds in MealDesc collapses to single spaces.
    assert collapse_ws("Cheeseburger, Chips, \r\nKetchup") == "Cheeseburger, Chips, Ketchup"
    assert collapse_ws("  x   y  ") == "x y"
    assert collapse_ws("") == ""
    assert collapse_ws(None) == ""
