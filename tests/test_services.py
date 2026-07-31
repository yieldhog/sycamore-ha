"""Tests for the sycamore.sync_calendar service (full mirror behaviour)."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

from homeassistant.components.calendar import CalendarEntityFeature, CalendarEvent
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sycamore.const import DOMAIN
from custom_components.sycamore.services import _sync_uid


class _Client:
    """Fake client with a single upcoming quiz."""

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def async_get_grades(self, student_id):
        return []

    async def async_get_homework(self, student_id):
        tomorrow = (date.today() + timedelta(days=1)).strftime("%m/%d/%Y")
        return [
            {
                "Title": "Chapter 3 Quiz",
                "ClassName": "6H Mathematics",
                "DueDate": tomorrow,
                "Description": "<p>Study ch 3</p>",
            }
        ]

    async def async_get_missing(self, student_id):
        return []

    async def async_get_attendance(self, student_id):
        return []

    async def async_get_cafeteria(self, school_id):
        return {}


async def _setup(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "token": "t",
            "family_id": "1",
            "school_id": None,
            "students": [{"id": "111", "name": "Jane"}],
        },
        options={"focus_window_days": 7},
    )
    entry.add_to_hass(hass)
    with patch("custom_components.sycamore.SycamoreClient", _Client):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


class _FakeCalendar:
    """Stand-in calendar entity that records deletes and returns fixed events."""

    supported_features = (
        CalendarEntityFeature.CREATE_EVENT | CalendarEntityFeature.DELETE_EVENT
    )

    def __init__(self, events: list[CalendarEvent]) -> None:
        self._events = events
        self.deleted: list[str] = []

    async def async_get_events(self, hass, start, end):
        return self._events

    async def async_delete_event(
        self, uid, recurrence_id=None, recurrence_range=None
    ):
        self.deleted.append(uid)


def _install_fake_calendar(hass: HomeAssistant, events):
    """Point the calendar component at a fake entity + record create_event."""
    fake = _FakeCalendar(events)
    hass.data["calendar"].get_entity = lambda entity_id: fake
    created: list[dict] = []

    async def _create(call):
        created.append(dict(call.data))

    hass.services.async_register("calendar", "create_event", _create)
    return fake, created


def _tagged_event(uid: str, event_uid: str, day: date) -> CalendarEvent:
    return CalendarEvent(
        start=day,
        end=day + timedelta(days=1),
        summary="whatever",
        description=f"[sycamore-sync:{uid}]",
        uid=event_uid,
    )


async def _run(hass: HomeAssistant) -> None:
    await hass.services.async_call(
        DOMAIN,
        "sync_calendar",
        {"target_calendar": "calendar.school", "days": 14},
        blocking=True,
    )
    await hass.async_block_till_done()


async def test_sync_creates_event(hass: HomeAssistant):
    """An upcoming item not on the calendar is created, with the description."""
    await _setup(hass)
    fake, created = _install_fake_calendar(hass, events=[])
    await _run(hass)

    assert len(created) == 1
    event = created[0]
    assert event["entity_id"] == "calendar.school"
    assert "Chapter 3 Quiz" in event["summary"]
    assert "Study ch 3" in event["description"]  # description carried through
    assert "sycamore-sync:" in event["description"]  # dedup tag embedded
    assert fake.deleted == []


async def test_sync_deletes_stale(hass: HomeAssistant):
    """An event we created that no longer matches any item is deleted."""
    await _setup(hass)
    stale = _tagged_event("deadbeef0000", "g-stale", date.today() + timedelta(days=2))
    fake, created = _install_fake_calendar(hass, events=[stale])
    await _run(hass)

    assert len(created) == 1  # current quiz added
    assert fake.deleted == ["g-stale"]  # stale one removed


async def test_sync_dedupes_unchanged(hass: HomeAssistant):
    """An already-synced item is neither re-created nor deleted."""
    await _setup(hass)
    tomorrow = date.today() + timedelta(days=1)
    uid = _sync_uid(
        "111", {"subject": "Mathematics", "title": "Chapter 3 Quiz", "due": tomorrow}
    )
    present = _tagged_event(uid, "g-keep", tomorrow)
    fake, created = _install_fake_calendar(hass, events=[present])
    await _run(hass)

    assert created == []
    assert fake.deleted == []


class _StatefulCalendar:
    """A faithful calendar: stores events, and creates/deletes like a real one.

    The `calendar.create_event` service writes here; the service reads back via
    `async_get_events` and removes via `async_delete_event`. This lets a test
    drive the real service through a multi-run lifecycle.
    """

    supported_features = (
        CalendarEntityFeature.CREATE_EVENT | CalendarEntityFeature.DELETE_EVENT
    )

    def __init__(self) -> None:
        self.events: dict[str, CalendarEvent] = {}
        self._seq = 0

    def add(self, data: dict) -> None:
        self._seq += 1
        uid = f"evt-{self._seq}"
        self.events[uid] = CalendarEvent(
            start=date.fromisoformat(data["start_date"]),
            end=date.fromisoformat(data["end_date"]),
            summary=data["summary"],
            description=data.get("description"),
            uid=uid,
        )

    async def async_get_events(self, hass, start, end):
        return list(self.events.values())

    async def async_delete_event(self, uid, recurrence_id=None, recurrence_range=None):
        self.events.pop(uid, None)


def _hw(title, subject, due, *, is_test=False, kind="assignment", description=""):
    return {
        "title": title,
        "subject": subject,
        "due": due,
        "is_test": is_test,
        "kind": kind,
        "description": description,
    }


async def test_sync_full_lifecycle(hass: HomeAssistant):
    """End-to-end: add -> idempotent re-run -> due-date change -> cancellation.

    Drives the real sycamore.sync_calendar service against a stateful calendar,
    mutating the coordinator's data between runs the way a real refresh would.
    """
    entry = await _setup(hass)
    coordinator = entry.runtime_data

    cal = _StatefulCalendar()
    hass.data["calendar"].get_entity = lambda entity_id: cal

    async def _create(call):
        cal.add(call.data)

    hass.services.async_register("calendar", "create_event", _create)

    async def run():
        return await hass.services.async_call(
            DOMAIN,
            "sync_calendar",
            {"target_calendar": "calendar.school", "days": 14},
            blocking=True,
            return_response=True,
        )

    d2 = date.today() + timedelta(days=2)
    d5 = date.today() + timedelta(days=5)
    d9 = date.today() + timedelta(days=9)

    # Run 1: two items on the board -> both created.
    coordinator.data = {
        "students": {
            "111": {
                "name": "Jane",
                "homework": [
                    _hw("Ch 3 Quiz", "Mathematics", d2, is_test=True, kind="quiz"),
                    _hw("Read Ch 4", "English", d5, description="pp. 40-55"),
                ],
            }
        },
        "cafeteria": None,
    }
    res = await run()
    assert res == {"created": 2, "deleted": 0, "unchanged": 0}
    assert len(cal.events) == 2
    # description carried through onto the stored event
    english = next(e for e in cal.events.values() if "Read Ch 4" in e.summary)
    assert "pp. 40-55" in english.description
    assert english.summary == "Jane: Read Ch 4"
    quiz = next(e for e in cal.events.values() if "Ch 3 Quiz" in e.summary)
    assert quiz.summary == "Jane: [QUIZ] Ch 3 Quiz"

    # Run 2: nothing changed -> no writes at all (idempotent).
    res = await run()
    assert res == {"created": 0, "deleted": 0, "unchanged": 2}
    assert len(cal.events) == 2

    # Run 3: the quiz's due date slips d2 -> d9. Old event removed, new created.
    coordinator.data["students"]["111"]["homework"] = [
        _hw("Ch 3 Quiz", "Mathematics", d9, is_test=True, kind="quiz"),
        _hw("Read Ch 4", "English", d5, description="pp. 40-55"),
    ]
    res = await run()
    assert res == {"created": 1, "deleted": 1, "unchanged": 1}
    assert len(cal.events) == 2
    moved = next(e for e in cal.events.values() if "Ch 3 Quiz" in e.summary)
    assert moved.start == d9  # calendar now reflects the new date

    # Run 4: the quiz is cancelled (drops off the board) -> its event is deleted.
    coordinator.data["students"]["111"]["homework"] = [
        _hw("Read Ch 4", "English", d5, description="pp. 40-55"),
    ]
    res = await run()
    assert res == {"created": 0, "deleted": 1, "unchanged": 1}
    assert len(cal.events) == 1
    assert all("Ch 3 Quiz" not in e.summary for e in cal.events.values())
