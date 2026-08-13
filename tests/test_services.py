"""Tests for the sycamore.sync_calendar service, mapping, and auto-sync."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

import pytest
from homeassistant.components.calendar import CalendarEntityFeature, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sycamore.const import CONF_CALENDAR_TARGETS, DOMAIN
from custom_components.sycamore.services import _item_hash, async_run_autosync


class _Client:
    """Fake client with a single upcoming quiz for any student."""

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def async_get_grades(self, student_id):
        return []

    async def async_get_homework(self, student_id):
        tomorrow = (dt_util.now().date() + timedelta(days=1)).strftime("%m/%d/%Y")
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

    async def async_get_student_details(self, student_id):
        return {}

    async def async_get_cafeteria(self, school_id):
        return {}


async def _setup(hass: HomeAssistant, students=None, options=None):
    opts = {"focus_window_days": 7}
    if options:
        opts.update(options)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "token": "t",
            "family_id": "1",
            "school_id": None,
            "students": students or [{"id": "111", "name": "Jane"}],
        },
        options=opts,
    )
    entry.add_to_hass(hass)
    with patch("custom_components.sycamore.SycamoreClient", _Client):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


class _FakeCalendar:
    """Calendar that returns fixed events and records deletes."""

    supported_features = (
        CalendarEntityFeature.CREATE_EVENT | CalendarEntityFeature.DELETE_EVENT
    )

    def __init__(self, events) -> None:
        self._events = list(events)
        self.deleted: list[str] = []

    async def async_get_events(self, hass, start, end):
        return list(self._events)

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


def _tagged_event(sid: str, item_hash: str, event_uid: str, day: date):
    return CalendarEvent(
        start=day,
        end=day + timedelta(days=1),
        summary="whatever",
        description=f"[sycamore-sync:{sid}:{item_hash}]",
        uid=event_uid,
    )


async def _sync(hass: HomeAssistant, **data):
    payload = {"days": 14, **data}
    await hass.services.async_call(
        DOMAIN, "sync_calendar", payload, blocking=True
    )
    await hass.async_block_till_done()


async def test_service_registered_without_config_entry(hass: HomeAssistant):
    """The action registers at component setup, even with no config entry.

    (action-setup) With no loaded entry there's nothing to sync, so the call
    raises a clean ServiceValidationError instead of the service being missing.
    """
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    assert hass.services.has_service(DOMAIN, "sync_calendar")

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "sync_calendar",
            {"target_calendar": "calendar.school"},
            blocking=True,
        )


async def test_sync_creates_event(hass: HomeAssistant):
    """An upcoming item not on the calendar is created, with the description."""
    await _setup(hass)
    fake, created = _install_fake_calendar(hass, events=[])
    await _sync(hass, target_calendar="calendar.school")

    assert len(created) == 1
    event = created[0]
    assert event["entity_id"] == "calendar.school"
    assert "Chapter 3 Quiz" in event["summary"]
    assert "Study ch 3" in event["description"]
    assert "[sycamore-sync:111:" in event["description"]  # student-scoped tag
    assert fake.deleted == []


async def test_sync_deletes_stale(hass: HomeAssistant):
    """An event we created that no longer matches any item is deleted."""
    await _setup(hass)
    stale = _tagged_event(
        "111", "deadbeef0000", "g-stale", dt_util.now().date() + timedelta(days=2)
    )
    fake, created = _install_fake_calendar(hass, events=[stale])
    await _sync(hass, target_calendar="calendar.school")

    assert len(created) == 1
    assert fake.deleted == ["g-stale"]


async def test_sync_dedupes_unchanged(hass: HomeAssistant):
    """An already-synced item is neither re-created nor deleted."""
    await _setup(hass)
    tomorrow = dt_util.now().date() + timedelta(days=1)
    item_hash = _item_hash(
        "111", {"subject": "Mathematics", "title": "Chapter 3 Quiz", "due": tomorrow}
    )
    present = _tagged_event("111", item_hash, "g-keep", tomorrow)
    fake, created = _install_fake_calendar(hass, events=[present])
    await _sync(hass, target_calendar="calendar.school")

    assert created == []
    assert fake.deleted == []


async def test_sync_uses_per_student_options_mapping(hass: HomeAssistant):
    """With no target_calendar, each student's mapped calendar is used."""
    await _setup(hass, options={CONF_CALENDAR_TARGETS: {"111": "calendar.school"}})
    fake, created = _install_fake_calendar(hass, events=[])
    await _sync(hass)  # note: no target_calendar passed

    assert len(created) == 1
    assert created[0]["entity_id"] == "calendar.school"


async def test_sync_shared_calendar_is_student_scoped(hass: HomeAssistant):
    """Two kids share a calendar: syncing one never touches the other's events."""
    entry = await _setup(
        hass,
        students=[{"id": "111", "name": "Jane"}, {"id": "222", "name": "John"}],
    )
    coordinator = entry.runtime_data
    due = dt_util.now().date() + timedelta(days=3)
    jane_hw = {
        "title": "Math HW", "subject": "Mathematics", "due": due,
        "is_test": False, "kind": "assignment", "description": "",
    }
    john_hw = {
        "title": "Sci HW", "subject": "Science", "due": due,
        "is_test": False, "kind": "assignment", "description": "",
    }
    coordinator.data = {
        "students": {
            "111": {"name": "Jane", "homework": [jane_hw]},
            "222": {"name": "John", "homework": [john_hw]},
        },
        "cafeteria": None,
    }
    events = [
        _tagged_event("111", _item_hash("111", jane_hw), "jane-current", due),
        _tagged_event("111", "oldhash0000", "jane-stale", due),
        _tagged_event("222", _item_hash("222", john_hw), "john-current", due),
    ]
    fake, created = _install_fake_calendar(hass, events)

    # Sync only Jane onto the shared calendar.
    await _sync(hass, target_calendar="calendar.school", student=["Jane"])

    assert created == []  # Jane's current item already present
    assert fake.deleted == ["jane-stale"]  # only Jane's stale event removed
    assert "john-current" not in fake.deleted  # John's event untouched


async def test_autosync_reconciles_mapping(hass: HomeAssistant):
    """async_run_autosync syncs each mapped student without a service call."""
    entry = await _setup(
        hass, options={CONF_CALENDAR_TARGETS: {"111": "calendar.school"}}
    )
    fake, created = _install_fake_calendar(hass, events=[])
    await async_run_autosync(hass, entry)
    await hass.async_block_till_done()

    assert len(created) == 1
    assert created[0]["entity_id"] == "calendar.school"


class _StatefulCalendar:
    """A faithful calendar: stores events, and creates/deletes like a real one."""

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
        "title": title, "subject": subject, "due": due,
        "is_test": is_test, "kind": kind, "description": description,
    }


async def test_sync_full_lifecycle(hass: HomeAssistant):
    """End-to-end: add -> idempotent re-run -> due-date change -> cancellation."""
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

    d2 = dt_util.now().date() + timedelta(days=2)
    d5 = dt_util.now().date() + timedelta(days=5)
    d9 = dt_util.now().date() + timedelta(days=9)

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
    assert res["created"] == 2 and res["deleted"] == 0
    assert len(cal.events) == 2
    english = next(e for e in cal.events.values() if "Read Ch 4" in e.summary)
    assert "pp. 40-55" in english.description
    assert english.summary == "Jane: Read Ch 4"
    quiz = next(e for e in cal.events.values() if "Ch 3 Quiz" in e.summary)
    assert quiz.summary == "Jane: [QUIZ] Ch 3 Quiz"

    # Idempotent re-run.
    res = await run()
    assert res["created"] == 0 and res["deleted"] == 0
    assert len(cal.events) == 2

    # Due date slips d2 -> d9: old event removed, new created.
    coordinator.data["students"]["111"]["homework"] = [
        _hw("Ch 3 Quiz", "Mathematics", d9, is_test=True, kind="quiz"),
        _hw("Read Ch 4", "English", d5, description="pp. 40-55"),
    ]
    res = await run()
    assert res["created"] == 1 and res["deleted"] == 1
    assert len(cal.events) == 2
    moved = next(e for e in cal.events.values() if "Ch 3 Quiz" in e.summary)
    assert moved.start == d9

    # Quiz cancelled -> its event is deleted.
    coordinator.data["students"]["111"]["homework"] = [
        _hw("Read Ch 4", "English", d5, description="pp. 40-55"),
    ]
    res = await run()
    assert res["created"] == 0 and res["deleted"] == 1
    assert len(cal.events) == 1
    assert all("Ch 3 Quiz" not in e.summary for e in cal.events.values())
