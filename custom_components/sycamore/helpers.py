"""Pure data-shaping helpers, ported from the original sycamore-dash app.

These have no Home Assistant dependencies so they can be unit-tested in
isolation and reused across platforms (sensor/calendar/todo).
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from datetime import time as dtime

# --- Subject name cleanup (ported from app/main.py: clean_subject_name) ---
# Ordered so the "<Nth> Grade-" prefix is tried before the "6H " section prefix:
# the original app's ordering let "2nd Grade-Science" match the section rule and
# leave "Grade-Science", which its own docstring said it meant to strip whole.
_PREFIX_RE = re.compile(r"^(.*?Grade-|\d+[a-zA-Z]+\s)")


def clean_subject_name(raw_name: str | None) -> str:
    """Strip '6H ' or '2nd Grade-' style prefixes without swallowing labels."""
    if not raw_name:
        return ""
    return _PREFIX_RE.sub("", raw_name).strip()


# --- HTML stripping (ported from app/main.py: strip_html_for_mqtt) ---
_BREAKS_RE = re.compile(r"<(br|/div|/p)>")
_TAGS_RE = re.compile(r"<.*?>")


def strip_html(text: str | None) -> str:
    """Remove HTML while keeping readability (breaks -> spaces, entities decoded)."""
    if not text:
        return ""
    text = _BREAKS_RE.sub(" ", text)
    clean = _TAGS_RE.sub("", text)
    return clean.replace("&nbsp;", " ").replace("&amp;", "&").strip()


_WS_RE = re.compile(r"\s+")


def collapse_ws(text: str | None) -> str:
    """Collapse runs of whitespace (incl. the CR/LF in meal descriptions)."""
    if not text:
        return ""
    return _WS_RE.sub(" ", text).strip()


# --- Test/quiz inference (ported from app/trmnl.py: detect_kind) ---
# Whole-word cues matched on boundaries so "final draft"/"contest" don't trip.
# Strong cues classify unconditionally; the weak cue ("assessment") only counts
# when the item doesn't otherwise read as ordinary work — teachers routinely
# assign "assessment questions" for homework, which should not become a test.
_STRONG_TEST_KINDS: list[tuple[str, str]] = [
    (r"midterm", "Test"),
    (r"final exam", "Test"),
    (r"finals", "Test"),
    (r"exam", "Test"),
    (r"test", "Test"),
    (r"quiz(?:zes)?", "Quiz"),
]
_WEAK_TEST_KINDS: list[tuple[str, str]] = [
    (r"assessment", "Test"),
]
# Presence of any of these (in the title or description) marks an item as
# ordinary work, vetoing a weak cue like "assessment".
_HOMEWORK_INDICATORS = re.compile(
    r"\b(questions?|worksheets?|packets?|reviews?|study guide|notes?|reading|read|homework)\b",
    re.IGNORECASE,
)


def detect_kind(
    title: str | None, description: str | None = None
) -> tuple[bool, str]:
    """Return (is_test, label) inferring test/quiz from an assignment.

    Strong cues (test/exam/quiz/midterm/finals) always classify.  The weaker
    ``assessment`` cue is suppressed when the title or description shows the
    item is ordinary work (e.g. "assessment *questions* due for homework").
    """
    low = (title or "").lower()
    for pattern, label in _STRONG_TEST_KINDS:
        if re.search(rf"\b{pattern}\b", low):
            return True, label
    if _HOMEWORK_INDICATORS.search(f"{title or ''} {description or ''}"):
        return False, ""
    for pattern, label in _WEAK_TEST_KINDS:
        if re.search(rf"\b{pattern}\b", low):
            return True, label
    return False, ""


# --- Subject icons/abbreviations (ported from app/trmnl.py) ---
_SUBJECT_ICONS: list[tuple[str, str]] = [
    ("math", "mdi:calculator-variant"),
    ("algebra", "mdi:calculator-variant"),
    ("geometry", "mdi:calculator-variant"),
    ("calc", "mdi:calculator-variant"),
    ("read", "mdi:book-open-variant"),
    ("literature", "mdi:book-open-variant"),
    ("english", "mdi:book-open-variant"),
    ("lang", "mdi:book-open-variant"),
    ("spell", "mdi:book-open-variant"),
    ("lit", "mdi:book-open-variant"),
    ("writ", "mdi:pencil"),
    ("essay", "mdi:pencil"),
    ("scien", "mdi:flask"),
    ("bio", "mdi:flask"),
    ("chem", "mdi:flask"),
    ("physic", "mdi:flask"),
    ("span", "mdi:earth"),
    ("french", "mdi:earth"),
    ("world", "mdi:earth"),
    ("geog", "mdi:earth"),
    ("hist", "mdi:script-text"),
    ("social", "mdi:script-text"),
    ("relig", "mdi:cross"),
    ("theo", "mdi:cross"),
    ("bible", "mdi:cross"),
    ("cathol", "mdi:cross"),
    ("art", "mdi:palette"),
    ("music", "mdi:music"),
    ("pe", "mdi:basketball"),
    ("physical", "mdi:basketball"),
]


def subject_icon(name: str | None) -> str:
    """Return an mdi icon id for a subject name (first substring match wins)."""
    low = (name or "").lower()
    for key, icon in _SUBJECT_ICONS:
        if key in low:
            return icon
    return "mdi:notebook"


def parse_due_date(raw: str | None) -> date | None:
    """Parse Sycamore's 'MM/DD/YYYY' due date, tolerating bad/empty values."""
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%m/%d/%Y").date()
    except (ValueError, TypeError):
        return None


def to_float(value: object) -> float | None:
    """Best-effort float parse (Sycamore 'Number' fields), else None."""
    try:
        return float(value)  # type: ignore[arg-type]
    except (ValueError, TypeError):
        return None


def parse_clock_time(raw: str | None) -> dtime | None:
    """Parse an 'HH:MM' or 'HH:MM:SS' time-of-day option, else None.

    Used for the optional due-time that turns all-day homework/test events into
    timed ones. An empty/absent/malformed value returns None (= keep all-day).
    """
    if not raw:
        return None
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(raw, fmt).time()
        except (ValueError, TypeError):
            continue
    return None


def parse_event_time(
    event: dict,
) -> tuple[datetime, timedelta, bool] | None:
    """Parse a School Events row into (naive start, duration, all_day).

    Sycamore events carry ``Datetime`` ('YYYY-MM-DD HH:MM:SS', school-local),
    a ``Duration`` ('HH:MM'), and an ``AllDay`` 0/1 flag. The start is returned
    naive (the caller attaches the local timezone); an unparseable row is None.
    """
    raw = event.get("Datetime")
    if not raw:
        return None
    try:
        start = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return None
    all_day = str(event.get("AllDay", "0")).strip() in ("1", "true", "True")
    duration = timedelta()
    parts = (event.get("Duration") or "").split(":")
    if len(parts) == 2:
        try:
            duration = timedelta(hours=int(parts[0]), minutes=int(parts[1]))
        except (ValueError, TypeError):
            duration = timedelta()
    return start, duration, all_day
