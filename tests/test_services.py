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
