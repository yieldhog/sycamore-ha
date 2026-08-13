"""Setup / entity tests using a fake Sycamore client."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
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
        tomorrow = (dt_util.now().date() + timedelta(days=1)).strftime("%m/%d/%Y")
        return [
            {"Title": "Chapter 3 Quiz", "ClassName": "6H Mathematics",
             "DueDate": tomorrow, "Description": "<p>Study</p>"},
        ]

    async def async_get_missing(self, student_id):
        return [{"Title": "Worksheet 5", "ClassName": "6H Mathematics"}]

    async def async_get_attendance(self, student_id):
        return [{"Date": "01/12/2026", "Type": "Tardy"}]

    async def async_get_discipline(self, student_id):
        return [{"Date": "01/15/2026", "Type": "Detention", "Description": "Late"}]

    async def async_get_student_details(self, student_id):
        return {
            "FirstName": "Jane",
            "Grade": "7th",
            "HomeroomTeacher": "Doug Hager",
            "Advisor": " ",
            "LockerNum": "",
        }

    async def async_get_events(self, school_id):
        return [
            {"ID": 1, "Title": "First Day", "Datetime": "2026-08-17 06:00:00",
             "Day": "08/17/26", "Start": "06:00", "Duration": "00:00", "AllDay": 1},
            {"ID": 2, "Title": "Orientation", "Datetime": "2026-08-14 16:00:00",
             "Day": "08/14/26", "Start": "16:00", "Duration": "00:45", "AllDay": 0},
        ]

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

    # The one upcoming item is a quiz, so it counts as upcoming work AND as an
    # upcoming test, and is labelled as a test in the upcoming-work list.
    upcoming = hass.states.get("sensor.jane_upcoming_work")
    assert upcoming.attributes["assignments"][0]["is_test"] is True
    assert upcoming.attributes["assignments"][0]["kind"] == "Quiz"
    assert upcoming.attributes["assignments"][0]["subject"] == "Mathematics"

    tests = hass.states.get("sensor.jane_upcoming_tests")
    assert tests.state == "1"
    assert tests.attributes["tests"][0]["kind"] == "Quiz"
    assert tests.attributes["tests"][0]["subject"] == "Mathematics"

    assert hass.states.get("binary_sensor.jane_has_missing_work").state == "on"
    assert hass.states.get("binary_sensor.jane_test_within_24_hours").state == "on"


async def test_analytics_sensors(hass: HomeAssistant):
    """Average, lowest class, and next assignment/test are computed from data."""
    await _setup(hass)

    # Mean of 92.5 (Mathematics) and 85 (Science).
    assert float(hass.states.get("sensor.jane_grade_average").state) == 88.75

    lowest = hass.states.get("sensor.jane_lowest_class")
    assert lowest.state == "Science"
    assert lowest.attributes["percent"] == 85.0

    # The one upcoming item (a quiz due tomorrow) is both next assignment + test.
    nxt = hass.states.get("sensor.jane_next_assignment")
    assert nxt.attributes["device_class"] == "timestamp"
    assert nxt.attributes["title"] == "Chapter 3 Quiz"
    assert nxt.attributes["subject"] == "Mathematics"
    assert nxt.state not in (None, "unknown", "unavailable")

    nxt_test = hass.states.get("sensor.jane_next_test")
    assert nxt_test.attributes["title"] == "Chapter 3 Quiz"
    assert nxt_test.attributes["is_test"] is True


async def test_calendar_and_todo_present(hass: HomeAssistant):
    await _setup(hass)
    assert hass.states.get("calendar.jane_homework") is not None
    assert hass.states.get("todo.jane_missing_work") is not None


async def test_calendar_target_skips_dedicated_calendar(hass: HomeAssistant):
    """A student mapped to an existing calendar gets no dedicated calendar entity.

    The unmapped sibling still gets one, and the mapped child's other homework
    sensors are unaffected (only the dedicated calendar is skipped).
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "token": "tok",
            "family_id": "647150",
            "school_id": None,
            "students": [
                {"id": "111", "name": "Jane"},
                {"id": "222", "name": "Sam"},
            ],
        },
        options={"calendar_targets": {"111": "calendar.family"}},
    )
    entry.add_to_hass(hass)
    with patch("custom_components.sycamore.SycamoreClient", FakeClient):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    reg = er.async_get(hass)
    # Jane is routed to an existing calendar -> no dedicated calendar entity.
    assert (
        reg.async_get_entity_id("calendar", DOMAIN, f"{entry.entry_id}_111_homework")
        is None
    )
    # Sam is unmapped -> still gets a dedicated calendar.
    assert (
        reg.async_get_entity_id("calendar", DOMAIN, f"{entry.entry_id}_222_homework")
        is not None
    )
    # Jane's homework-derived sensors are unaffected.
    assert hass.states.get("sensor.jane_upcoming_work") is not None


async def test_student_details_enrich_device_and_sensors(hass: HomeAssistant):
    """Profile details set the device model + grade/homeroom diagnostic sensors."""
    entry = await _setup(hass)

    assert hass.states.get("sensor.jane_grade_level").state == "7th"
    assert hass.states.get("sensor.jane_homeroom_teacher").state == "Doug Hager"

    device = dr.async_get(hass).async_get_device(
        identifiers={(DOMAIN, f"{entry.entry_id}_111")}
    )
    assert device is not None
    assert device.model == "7th Grade"


class LateDetailsClient(FakeClient):
    """Profile endpoint returns nothing at first, then data on a later refresh."""

    details_ready = False

    async def async_get_student_details(self, student_id):
        if not LateDetailsClient.details_ready:
            return {}
        return {"Grade": "7th", "HomeroomTeacher": "Doug Hager"}


async def test_detail_sensors_appear_on_later_refresh(hass: HomeAssistant):
    """Detail sensors are added when the profile endpoint first returns data.

    Regression: previously they were created only if details were present on the
    very first refresh, so a transient failure (e.g. a 500) permanently hid them
    until a reload. They should now appear on whichever refresh first succeeds.
    """
    LateDetailsClient.details_ready = False
    entry = _entry()
    entry.add_to_hass(hass)
    with patch("custom_components.sycamore.SycamoreClient", LateDetailsClient):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        # Profile empty at setup -> detail sensors not created yet.
        assert hass.states.get("sensor.jane_grade_level") is None
        assert hass.states.get("sensor.jane_homeroom_teacher") is None

        # Profile becomes available on a later refresh -> sensors appear.
        LateDetailsClient.details_ready = True
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()

    assert hass.states.get("sensor.jane_grade_level").state == "7th"
    assert hass.states.get("sensor.jane_homeroom_teacher").state == "Doug Hager"


async def test_school_events_calendar_and_sensor(hass: HomeAssistant):
    """With a School ID, the events endpoint drives a calendar + next-event sensor."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "token": "tok",
            "family_id": "647150",
            "school_id": "1002",
            "students": [{"id": "111", "name": "Jane"}],
        },
        options={"scan_interval_minutes": 60, "focus_window_days": 7},
    )
    entry.add_to_hass(hass)
    with patch("custom_components.sycamore.SycamoreClient", FakeClient):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    reg = er.async_get(hass)
    cal_eid = reg.async_get_entity_id(
        "calendar", DOMAIN, f"{entry.entry_id}_school_events"
    )
    assert cal_eid
    assert hass.states.get(cal_eid) is not None

    sensor_eid = reg.async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_next_school_event"
    )
    assert sensor_eid
    assert hass.states.get(sensor_eid).attributes["device_class"] == "timestamp"


async def test_health_entities(hass: HomeAssistant):
    """Last-updated + status report success, and survive a failed refresh."""
    from custom_components.sycamore.api import SycamoreConnectionError

    entry = await _setup(hass)
    coordinator = entry.runtime_data

    last_updated = hass.states.get("sensor.sycamore_last_updated")
    assert last_updated is not None
    assert last_updated.state not in ("unknown", "unavailable")
    good_time = last_updated.state

    status = hass.states.get("binary_sensor.sycamore_status")
    assert status.state == "off"  # problem device_class -> "off" means OK

    # Force the next refresh to fail.
    with patch.object(
        FakeClient,
        "async_get_grades",
        new=AsyncMock(side_effect=SycamoreConnectionError("down")),
    ):
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    status = hass.states.get("binary_sensor.sycamore_status")
    assert status.state == "on"  # problem detected
    assert status.attributes["error"]
    # The health sensors stay available and keep the last good time.
    last_updated = hass.states.get("sensor.sycamore_last_updated")
    assert last_updated.state == good_time
    assert last_updated.state != "unavailable"


async def test_remove_stale_device(hass: HomeAssistant):
    """A live student device can't be deleted; a stale one can."""
    from custom_components.sycamore import async_remove_config_entry_device

    entry = await _setup(hass)  # one configured student, Jane (111)
    dev_reg = dr.async_get(hass)

    live = dev_reg.async_get_device(identifiers={(DOMAIN, f"{entry.entry_id}_111")})
    assert live is not None
    # A configured student's device is live -> not removable.
    assert await async_remove_config_entry_device(hass, entry, live) is False

    # A device for a student no longer in the config is stale -> removable.
    stale = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, f"{entry.entry_id}_999")},
    )
    assert await async_remove_config_entry_device(hass, entry, stale) is True


async def test_diagnostics_redacts_pii(hass: HomeAssistant):
    """Diagnostics hide the token, student ids, and student/teacher names."""
    from custom_components.sycamore.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    entry = await _setup(hass)  # Jane (id 111), homeroom "Doug Hager"
    diag = await async_get_config_entry_diagnostics(hass, entry)

    # Credentials redacted.
    assert diag["entry_data"]["token"] == "**REDACTED**"

    # Students re-keyed so the raw student id isn't a dict key.
    students = diag["data"]["students"]
    assert "111" not in students
    assert "student_0" in students

    bundle = students["student_0"]
    # Name + teacher redacted, but academic structure preserved for debugging.
    assert bundle["name"] == "**REDACTED**"
    assert bundle["details"]["homeroom_teacher"] == "**REDACTED**"
    assert bundle["grades"]  # grade data still present


async def test_unload(hass: HomeAssistant):
    entry = await _setup(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


class LunchClient(FakeClient):
    """Returns the real cafeteria shape: {MM/DD/YYYY: [meal objects]}."""

    async def async_get_cafeteria(self, school_id):
        today = dt_util.now().date().strftime("%m/%d/%Y")
        return {
            today: [
                {
                    "MealID": 1,
                    "MealName": "Cheeseburger",
                    "MealDesc": "Cheeseburger, Chips,\r\nKetchup",
                },
                {"MealID": 2, "MealName": "Chef Salad", "MealDesc": "Lettuce, Ham"},
            ],
            "01/01/2020": [
                {"MealID": 3, "MealName": "Pizza", "MealDesc": "Cheese"},
            ],
        }


async def test_lunch_sensor_and_calendar(hass: HomeAssistant):
    """The dict cafeteria payload drives today's lunch sensor and a calendar."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "token": "tok",
            "family_id": "647150",
            "school_id": "1002",
            "students": [{"id": "111", "name": "Jane"}],
        },
        options={"scan_interval_minutes": 60, "focus_window_days": 7},
    )
    entry.add_to_hass(hass)
    with patch("custom_components.sycamore.SycamoreClient", LunchClient):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    reg = er.async_get(hass)

    lunch_eid = reg.async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_todays_lunch"
    )
    assert lunch_eid
    lunch = hass.states.get(lunch_eid)
    assert "Cheeseburger" in lunch.state
    assert "Chef Salad" in lunch.state
    # CR/LF in the description is collapsed.
    assert lunch.attributes["meals"][0]["description"] == "Cheeseburger, Chips, Ketchup"
    # The full pulled menu (both days) is exposed for calendar/week use.
    assert len(lunch.attributes["menu"]) == 2

    cal_eid = reg.async_get_entity_id(
        "calendar", DOMAIN, f"{entry.entry_id}_lunch_calendar"
    )
    assert cal_eid
    assert hass.states.get(cal_eid) is not None


class TitlelessMissingClient(FakeClient):
    """Missing item with no Title — the reference app only used ClassName/Desc."""

    async def async_get_missing(self, student_id):
        return [{"ClassName": "6H Science", "Description": "<p>Lab writeup</p>"}]


async def test_missing_without_title_still_counts(hass: HomeAssistant):
    """A missing item lacking a Title is surfaced (not silently dropped)."""
    entry = _entry()
    entry.add_to_hass(hass)
    with patch("custom_components.sycamore.SycamoreClient", TitlelessMissingClient):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert hass.states.get("sensor.jane_missing_work").state == "1"
    assert hass.states.get("binary_sensor.jane_has_missing_work").state == "on"
    # Falls back to the description text as the label.
    missing = hass.states.get("sensor.jane_missing_work")
    assert missing.attributes["assignments"] == ["Lab writeup"]


class HomeworkErrorClient(FakeClient):
    """Homework 500s (as Sycamore does between terms / during an API hiccup)."""

    async def async_get_homework(self, student_id):
        from custom_components.sycamore.api import SycamoreApiError

        raise SycamoreApiError(
            f"Student/{student_id}/Homework returned HTTP 500", status_code=500
        )


async def test_endpoint_500_degrades_not_fails(hass: HomeAssistant):
    """A 500 on one section degrades that section, not the whole setup.

    Reproduces the real-world "Failed setup, will retry: Student/…/Homework
    returned HTTP 500": the integration must still load, with the other
    sections intact and only the failed section empty.
    """
    entry = _entry()
    entry.add_to_hass(hass)
    with patch("custom_components.sycamore.SycamoreClient", HomeworkErrorClient):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    # Grades and missing work still load; only homework-derived data is empty.
    assert hass.states.get("sensor.jane_mathematics") is not None
    assert hass.states.get("sensor.jane_missing_work").state == "1"
    assert hass.states.get("sensor.jane_upcoming_work").state == "0"
    # A single-section 500 is not a failed refresh, so health stays OK...
    status = hass.states.get("binary_sensor.sycamore_status")
    assert status.state == "off"
    # ...but the failed section is surfaced so a user can tell it apart from
    # "no data yet".
    degraded = status.attributes["degraded"]
    assert degraded and any("homework" in d for d in degraded)


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


class NoDisciplineClient(FakeClient):
    """Fails if discipline is fetched, proving it's off unless enabled."""

    async def async_get_discipline(self, student_id):
        raise AssertionError("discipline must not be fetched when disabled")


async def test_discipline_off_by_default(hass: HomeAssistant):
    """Discipline is opt-in: not polled and no sensor unless the toggle is on."""
    entry = _entry()  # no discipline_enabled option -> defaults off
    entry.add_to_hass(hass)
    with patch("custom_components.sycamore.SycamoreClient", NoDisciplineClient):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.jane_discipline_events") is None


async def test_discipline_enabled(hass: HomeAssistant):
    """With the toggle on, the discipline log drives a per-student sensor."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "token": "tok",
            "family_id": "647150",
            "school_id": None,
            "students": [{"id": "111", "name": "Jane"}],
        },
        options={"discipline_enabled": True},
    )
    entry.add_to_hass(hass)
    with patch("custom_components.sycamore.SycamoreClient", FakeClient):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    disc = hass.states.get("sensor.jane_discipline_events")
    assert disc is not None
    assert disc.state == "1"
    assert disc.attributes["records"][0]["Type"] == "Detention"
