"""Setup / entity tests using a fake Sycamore client."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sycamore.const import DOMAIN


class FakeClient:
    """Stand-in for SycamoreClient returning fixed sample payloads."""

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def async_get_grades(self, student_id):
        return [
            {"ClassName": "6H Mathematics", "Number": "92.5", "Letter": "A-",
             "PDate": "01/10/2026"},
            {"ClassName": "Science", "Number": "85", "Letter": "B"},
        ]

    async def async_get_homework(self, student_id):
        tomorrow = (date.today() + timedelta(days=1)).strftime("%m/%d/%Y")
        return [
            {"Title": "Chapter 3 Quiz", "ClassName": "6H Mathematics",
             "DueDate": tomorrow, "Description": "<p>Study</p>"},
        ]

    async def async_get_missing(self, student_id):
        return [{"Title": "Worksheet 5", "ClassName": "6H Mathematics"}]

    async def async_get_attendance(self, student_id):
        return [{"Date": "01/12/2026", "Type": "Tardy"}]

    async def async_get_cafeteria(self, school_id):
        return []


def _entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        data={
            "token": "tok",
            "family_id": "647150",
            "school_id": None,
            "students": [{"id": "111", "name": "Jane"}],
        },
        options={"scan_interval_minutes": 30, "focus_window_days": 7},
    )


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = _entry()
    entry.add_to_hass(hass)
    with patch("custom_components.sycamore.SycamoreClient", FakeClient):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_setup_and_grade_sensors(hass: HomeAssistant):
    entry = await _setup(hass)
    assert entry.state is ConfigEntryState.LOADED

    letter = hass.states.get("sensor.jane_mathematics")
    assert letter is not None
    assert letter.state == "A-"
    assert letter.attributes["percent"] == 92.5
    assert letter.attributes["trend"] == "stable"

    percent = hass.states.get("sensor.jane_mathematics_percent")
    assert percent is not None
    assert percent.state == "92.5"
    assert percent.attributes["unit_of_measurement"] == "%"
    assert percent.attributes["state_class"] == "measurement"


async def test_count_and_binary_entities(hass: HomeAssistant):
    await _setup(hass)

    assert hass.states.get("sensor.jane_missing_work").state == "1"
    assert hass.states.get("sensor.jane_upcoming_work").state == "1"
    assert hass.states.get("sensor.jane_attendance_events").state == "1"

    assert hass.states.get("binary_sensor.jane_has_missing_work").state == "on"
    assert hass.states.get("binary_sensor.jane_test_within_24_hours").state == "on"


async def test_calendar_and_todo_present(hass: HomeAssistant):
    await _setup(hass)
    assert hass.states.get("calendar.jane_homework") is not None
    assert hass.states.get("todo.jane_missing_work") is not None


async def test_unload(hass: HomeAssistant):
    entry = await _setup(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


class NoAttendanceClient(FakeClient):
    """Fails if attendance is fetched, proving the toggle skips the call."""

    async def async_get_attendance(self, student_id):
        raise AssertionError("attendance must not be fetched when disabled")


async def test_attendance_disabled(hass: HomeAssistant):
    """With attendance off, the endpoint isn't polled and no sensor is made."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "token": "tok",
            "family_id": "647150",
            "school_id": None,
            "students": [{"id": "111", "name": "Jane"}],
        },
        options={"attendance_enabled": False},
    )
    entry.add_to_hass(hass)
    with patch("custom_components.sycamore.SycamoreClient", NoAttendanceClient):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.jane_attendance_events") is None
    # Core sensors are unaffected.
    assert hass.states.get("sensor.jane_missing_work") is not None
