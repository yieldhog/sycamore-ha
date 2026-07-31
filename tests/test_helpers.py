"""Unit tests for the pure data-shaping helpers."""

from __future__ import annotations

from datetime import date

import pytest

from custom_components.sycamore.helpers import (
    clean_subject_name,
    collapse_ws,
    detect_kind,
    parse_due_date,
    strip_html,
    subject_icon,
    to_float,
)


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
    ],
)
def test_detect_kind(title, is_test, label):
    assert detect_kind(title) == (is_test, label)


def test_strip_html():
    assert strip_html("<p>Study 1-10</p>") == "Study 1-10"
    assert strip_html("line a<br>line b") == "line a line b"
    assert strip_html("Tom &amp; Jerry") == "Tom & Jerry"
    assert strip_html(None) == ""


def test_parse_due_date():
    assert parse_due_date("01/15/2026") == date(2026, 1, 15)
    assert parse_due_date("garbage") is None
    assert parse_due_date(None) is None


def test_subject_icon():
    assert subject_icon("Mathematics") == "mdi:calculator-variant"
    assert subject_icon("Science") == "mdi:flask"
    assert subject_icon("Spanish") == "mdi:earth"
    assert subject_icon("Underwater Basket Weaving") == "mdi:notebook"


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
