"""Calendar platform: homework and tests as due-date events."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SycamoreConfigEntry
from .const import DATA_CAFETERIA, DATA_HOMEWORK
from .entity import SycamoreSchoolEntity, SycamoreStudentEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SycamoreConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up a homework calendar per student, plus a school lunch calendar."""
    coordinator = entry.runtime_data
    entities: list[CalendarEntity] = [
        SycamoreHomeworkCalendar(coordinator, s["id"], s["name"])
        for s in coordinator.students
    ]
    if coordinator.school_id and coordinator.lunch_enabled:
        entities.append(SycamoreLunchCalendar(coordinator))
    async_add_entities(entities)


def _summary(hw: dict) -> str:
    """Prefix tests/quizzes so they stand out in calendar views."""
    if hw["is_test"] and hw["kind"]:
        return f"[{hw['kind'].upper()}] {hw['title']}"
    return hw["title"]


class SycamoreHomeworkCalendar(SycamoreStudentEntity, CalendarEntity):
    """A read-only calendar of a student's homework and tests."""

    _attr_translation_key = "homework"
    _attr_icon = "mdi:calendar-text"

    def __init__(self, coordinator, student_id, student_name) -> None:  # noqa: D107
        super().__init__(coordinator, student_id, student_name)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{student_id}_homework"

    def _events(self) -> list[CalendarEvent]:
        events: list[CalendarEvent] = []
        for hw in self.student_data.get(DATA_HOMEWORK, []):
            due: date = hw["due"]
            events.append(
                CalendarEvent(
                    start=due,
                    end=due + timedelta(days=1),
                    summary=_summary(hw),
                    description=hw["description"] or None,
                    location=hw["subject"] or None,
                )
            )
        return events

    @property
    def event(self) -> CalendarEvent | None:
        """The next upcoming assignment."""
        today = datetime.now().date()
        upcoming = sorted(
            (e for e in self._events() if e.end > today), key=lambda e: e.start
        )
        return upcoming[0] if upcoming else None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Return events intersecting the requested range."""
        start = start_date.date()
        end = end_date.date()
        return [e for e in self._events() if e.start < end and e.end > start]


class SycamoreLunchCalendar(SycamoreSchoolEntity, CalendarEntity):
    """A read-only calendar of the cafeteria menu — one all-day event per day."""

    _attr_translation_key = "lunch"
    _attr_icon = "mdi:food"

    def __init__(self, coordinator) -> None:
        """Initialize the school lunch calendar."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_lunch_calendar"

    def _events(self) -> list[CalendarEvent]:
        events: list[CalendarEvent] = []
        for day in (self.coordinator.data or {}).get(DATA_CAFETERIA) or []:
            due: date = day["date"]
            meals = day["meals"]
            summary = ", ".join(m["name"] for m in meals)
            description = "\n".join(
                f"{m['name']}: {m['description']}" if m["description"] else m["name"]
                for m in meals
            )
            events.append(
                CalendarEvent(
                    start=due,
                    end=due + timedelta(days=1),
                    summary=summary[:255] or "Lunch",
                    description=description or None,
                )
            )
        return events

    @property
    def event(self) -> CalendarEvent | None:
        """The next lunch day."""
        today = datetime.now().date()
        upcoming = sorted(
            (e for e in self._events() if e.end > today), key=lambda e: e.start
        )
        return upcoming[0] if upcoming else None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Return lunch events intersecting the requested range."""
        start = start_date.date()
        end = end_date.date()
        return [e for e in self._events() if e.start < end and e.end > start]
