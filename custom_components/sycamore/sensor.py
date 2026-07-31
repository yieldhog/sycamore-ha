"""Sensor platform for the Sycamore integration."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify

from . import SycamoreConfigEntry
from .const import (
    DATA_ATTENDANCE,
    DATA_GRADES,
    DATA_HOMEWORK,
    DATA_MISSING,
    DOMAIN,
)
from .coordinator import SycamoreDataUpdateCoordinator
from .entity import SycamoreSchoolEntity, SycamoreStudentEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SycamoreConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Sycamore sensors, adding grade sensors as classes appear."""
    coordinator = entry.runtime_data

    entities: list[SensorEntity] = []
    for student in coordinator.students:
        sid = student["id"]
        name = student["name"]
        entities.append(SycamoreMissingCountSensor(coordinator, sid, name))
        entities.append(SycamoreUpcomingCountSensor(coordinator, sid, name))
        entities.append(SycamoreAttendanceSensor(coordinator, sid, name))
    if coordinator.school_id:
        entities.append(SycamoreLunchSensor(coordinator))
    async_add_entities(entities)

    known: set[str] = set()

    @callback
    def _add_grade_sensors() -> None:
        new: list[SensorEntity] = []
        students = (coordinator.data or {}).get("students", {})
        for student in coordinator.students:
            sid = student["id"]
            for grade in students.get(sid, {}).get(DATA_GRADES, []):
                subject = grade["subject"]
                key = f"{sid}:{subject}"
                if key in known:
                    continue
                known.add(key)
                new.append(
                    SycamoreGradeSensor(coordinator, sid, student["name"], subject)
                )
                new.append(
                    SycamoreGradePercentSensor(
                        coordinator, sid, student["name"], subject
                    )
                )
        if new:
            async_add_entities(new)

    _add_grade_sensors()
    entry.async_on_unload(coordinator.async_add_listener(_add_grade_sensors))


class _SycamoreGradeBase(SycamoreStudentEntity, SensorEntity):
    """Shared lookup for the per-class grade sensors."""

    def __init__(
        self,
        coordinator: SycamoreDataUpdateCoordinator,
        student_id: str,
        student_name: str,
        subject: str,
    ) -> None:
        """Store the subject this sensor tracks."""
        super().__init__(coordinator, student_id, student_name)
        self._subject = subject

    def _grade(self) -> dict[str, Any] | None:
        for grade in self.student_data.get(DATA_GRADES, []):
            if grade["subject"] == self._subject:
                return grade
        return None

    @property
    def icon(self) -> str | None:
        grade = self._grade()
        return grade["icon"] if grade else "mdi:notebook"


class SycamoreGradeSensor(_SycamoreGradeBase):
    """Current letter grade for one class (percent + trend as attributes)."""

    def __init__(self, coordinator, student_id, student_name, subject) -> None:  # noqa: D107
        super().__init__(coordinator, student_id, student_name, subject)
        self._attr_name = subject
        self._attr_unique_id = (
            f"{coordinator.entry.entry_id}_{student_id}_grade_{slugify(subject)}"
        )

    @property
    def native_value(self) -> str | None:
        grade = self._grade()
        if grade is None:
            return None
        if grade["letter"]:
            return grade["letter"]
        if grade["number"] is not None:
            return str(round(grade["number"]))
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        grade = self._grade() or {}
        return {
            "percent": grade.get("number"),
            "trend": grade.get("trend"),
            "updated": grade.get("pdate"),
            "subject": self._subject,
        }


class SycamoreGradePercentSensor(_SycamoreGradeBase):
    """Numeric percentage for one class, recorded for long-term history."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator, student_id, student_name, subject) -> None:  # noqa: D107
        super().__init__(coordinator, student_id, student_name, subject)
        self._attr_name = f"{subject} percent"
        self._attr_unique_id = (
            f"{coordinator.entry.entry_id}_{student_id}_grade_pct_{slugify(subject)}"
        )

    @property
    def native_value(self) -> float | None:
        grade = self._grade()
        return grade["number"] if grade else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        grade = self._grade() or {}
        return {
            "letter": grade.get("letter"),
            "trend": grade.get("trend"),
            "subject": self._subject,
        }


class _StudentCountSensor(SycamoreStudentEntity, SensorEntity):
    """Shared base for the simple per-student count sensors."""

    _data_key: str
    _slug: str

    def __init__(
        self,
        coordinator: SycamoreDataUpdateCoordinator,
        student_id: str,
        student_name: str,
    ) -> None:
        super().__init__(coordinator, student_id, student_name)
        self._attr_unique_id = (
            f"{coordinator.entry.entry_id}_{student_id}_{self._slug}"
        )


class SycamoreMissingCountSensor(_StudentCountSensor):
    """Number of missing assignments."""

    _data_key = DATA_MISSING
    _slug = "missing_work"
    _attr_translation_key = "missing_work"
    _attr_icon = "mdi:alert-circle"

    @property
    def native_value(self) -> int:
        return len(self.student_data.get(DATA_MISSING, []))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        items = self.student_data.get(DATA_MISSING, [])
        return {"assignments": [i["title"] for i in items]}


class SycamoreUpcomingCountSensor(_StudentCountSensor):
    """Number of upcoming assignments within the focus window."""

    _slug = "upcoming_work"
    _attr_translation_key = "upcoming_work"
    _attr_icon = "mdi:calendar-clock"

    @property
    def native_value(self) -> int:
        return sum(
            1 for hw in self.student_data.get(DATA_HOMEWORK, []) if hw["in_focus"]
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        items = [
            hw for hw in self.student_data.get(DATA_HOMEWORK, []) if hw["in_focus"]
        ]
        return {
            "assignments": [
                {"title": i["title"], "subject": i["subject"], "due": i["due"].isoformat()}
                for i in items
            ]
        }


class SycamoreAttendanceSensor(_StudentCountSensor):
    """Attendance events count (absences/tardies as reported by the school)."""

    _slug = "attendance"
    _attr_translation_key = "attendance"
    _attr_icon = "mdi:clipboard-check"

    @property
    def native_value(self) -> int:
        return self.student_data.get(DATA_ATTENDANCE, {}).get("count", 0)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"records": self.student_data.get(DATA_ATTENDANCE, {}).get("records", [])}


class SycamoreLunchSensor(SycamoreSchoolEntity, SensorEntity):
    """Today's cafeteria menu (school-level)."""

    _attr_translation_key = "todays_lunch"
    _attr_icon = "mdi:food-apple"

    def __init__(self, coordinator: SycamoreDataUpdateCoordinator) -> None:
        """Initialize the lunch sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_todays_lunch"

    def _cafeteria(self) -> list[dict[str, Any]]:
        data = self.coordinator.data or {}
        return data.get("cafeteria") or []

    @staticmethod
    def _entry_text(item: dict[str, Any]) -> str:
        for field in ("Title", "Name", "Menu", "Description", "Item"):
            if item.get(field):
                return str(item[field]).strip()
        return ""

    def _todays_items(self) -> list[dict[str, Any]]:
        today = datetime.now().strftime("%m/%d/%Y")
        today_iso = datetime.now().strftime("%Y-%m-%d")
        out = []
        for item in self._cafeteria():
            raw = str(item.get("Date") or item.get("MenuDate") or "")
            if raw.startswith(today) or raw.startswith(today_iso):
                out.append(item)
        return out

    @property
    def native_value(self) -> str | None:
        items = self._todays_items()
        texts = [t for t in (self._entry_text(i) for i in items) if t]
        if texts:
            return ", ".join(texts)[:255]
        return "No menu" if self._cafeteria() else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"menu": self._cafeteria()}
