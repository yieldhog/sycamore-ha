"""Sensor platform for the Sycamore integration."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

from . import SycamoreConfigEntry
from .const import (
    DATA_ATTENDANCE,
    DATA_GRADES,
    DATA_HOMEWORK,
    DATA_MISSING,
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
        entities.append(SycamoreUpcomingTestsSensor(coordinator, sid, name))
        entities.append(SycamoreAverageSensor(coordinator, sid, name))
        entities.append(SycamoreLowestClassSensor(coordinator, sid, name))
        entities.append(SycamoreNextAssignmentSensor(coordinator, sid, name))
        entities.append(SycamoreNextTestSensor(coordinator, sid, name))
        if coordinator.attendance_enabled:
            entities.append(SycamoreAttendanceSensor(coordinator, sid, name))
    if coordinator.school_id and coordinator.lunch_enabled:
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
                {
                    "title": i["title"],
                    "subject": i["subject"],
                    "due": i["due"].isoformat(),
                    "is_test": i["is_test"],
                    "kind": i["kind"],
                }
                for i in items
            ]
        }


class SycamoreUpcomingTestsSensor(_StudentCountSensor):
    """Number of tests/quizzes due within the focus window.

    Complements the fixed 24-hour ``test_within_24h`` binary sensor with the
    configurable "next N days" horizon, and lists each item by class so it can
    drive a calendar.
    """

    _slug = "upcoming_tests"
    _attr_translation_key = "upcoming_tests"
    _attr_icon = "mdi:clipboard-alert-outline"

    def _tests(self) -> list[dict[str, Any]]:
        return [
            hw
            for hw in self.student_data.get(DATA_HOMEWORK, [])
            if hw["in_focus"] and hw["is_test"]
        ]

    @property
    def native_value(self) -> int:
        return len(self._tests())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "tests": [
                {
                    "title": i["title"],
                    "subject": i["subject"],
                    "due": i["due"].isoformat(),
                    "kind": i["kind"],
                }
                for i in self._tests()
            ]
        }


class SycamoreAverageSensor(SycamoreStudentEntity, SensorEntity):
    """Overall grade average across the student's classes (mean of percents)."""

    _attr_translation_key = "grade_average"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1
    _attr_icon = "mdi:school"

    def __init__(self, coordinator, student_id, student_name) -> None:
        """Initialize the average sensor."""
        super().__init__(coordinator, student_id, student_name)
        self._attr_unique_id = (
            f"{coordinator.entry.entry_id}_{student_id}_grade_average"
        )

    def _numbers(self) -> list[float]:
        return [
            g["number"]
            for g in self.student_data.get(DATA_GRADES, [])
            if g["number"] is not None
        ]

    @property
    def native_value(self) -> float | None:
        nums = self._numbers()
        return round(sum(nums) / len(nums), 2) if nums else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"class_count": len(self._numbers())}


class SycamoreLowestClassSensor(SycamoreStudentEntity, SensorEntity):
    """The class with the lowest current percentage (early warning)."""

    _attr_translation_key = "lowest_class"

    def __init__(self, coordinator, student_id, student_name) -> None:
        """Initialize the lowest-class sensor."""
        super().__init__(coordinator, student_id, student_name)
        self._attr_unique_id = (
            f"{coordinator.entry.entry_id}_{student_id}_lowest_class"
        )

    def _lowest(self) -> dict[str, Any] | None:
        graded = [
            g
            for g in self.student_data.get(DATA_GRADES, [])
            if g["number"] is not None
        ]
        return min(graded, key=lambda g: g["number"]) if graded else None

    @property
    def native_value(self) -> str | None:
        grade = self._lowest()
        return grade["subject"] if grade else None

    @property
    def icon(self) -> str:
        grade = self._lowest()
        return grade["icon"] if grade else "mdi:trending-down"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        grade = self._lowest() or {}
        return {
            "percent": grade.get("number"),
            "letter": grade.get("letter"),
            "trend": grade.get("trend"),
        }


class _SycamoreNextBase(SycamoreStudentEntity, SensorEntity):
    """Due date of the soonest upcoming homework item (optionally tests only)."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _slug: str
    _test_only: bool = False

    def __init__(self, coordinator, student_id, student_name) -> None:
        super().__init__(coordinator, student_id, student_name)
        self._attr_unique_id = (
            f"{coordinator.entry.entry_id}_{student_id}_{self._slug}"
        )

    def _next(self) -> dict[str, Any] | None:
        today = datetime.now().date()
        items = [
            hw
            for hw in self.student_data.get(DATA_HOMEWORK, [])
            if hw["due"] >= today and (hw["is_test"] or not self._test_only)
        ]
        return min(items, key=lambda hw: hw["due"]) if items else None

    @property
    def native_value(self) -> datetime | None:
        item = self._next()
        return dt_util.start_of_local_day(item["due"]) if item else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        item = self._next()
        if not item:
            return {}
        return {
            "title": item["title"],
            "subject": item["subject"],
            "is_test": item["is_test"],
            "kind": item["kind"],
        }


class SycamoreNextAssignmentSensor(_SycamoreNextBase):
    """Due date of the soonest upcoming assignment."""

    _slug = "next_assignment"
    _attr_translation_key = "next_assignment"
    _attr_icon = "mdi:calendar-arrow-right"


class SycamoreNextTestSensor(_SycamoreNextBase):
    """Due date of the soonest upcoming test/quiz."""

    _slug = "next_test"
    _attr_translation_key = "next_test"
    _attr_icon = "mdi:clipboard-text-clock"
    _test_only = True


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

    def _days(self) -> list[dict[str, Any]]:
        return (self.coordinator.data or {}).get("cafeteria") or []

    def _today_meals(self) -> list[dict[str, Any]]:
        today = datetime.now().date()
        for day in self._days():
            if day["date"] == today:
                return day["meals"]
        return []

    @property
    def native_value(self) -> str | None:
        meals = self._today_meals()
        if meals:
            return ", ".join(m["name"] for m in meals)[:255]
        return "No menu" if self._days() else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "meals": [
                {"name": m["name"], "description": m["description"]}
                for m in self._today_meals()
            ],
            "menu": [
                {
                    "date": day["date"].isoformat(),
                    "meals": [
                        {"name": m["name"], "description": m["description"]}
                        for m in day["meals"]
                    ],
                }
                for day in self._days()
            ],
        }
