"""Sensor platform for the Sycamore integration."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

from . import SycamoreConfigEntry
from .const import (
    DATA_ACCOUNTS,
    DATA_ATTENDANCE,
    DATA_DETAILS,
    DATA_DISCIPLINE,
    DATA_GRADES,
    DATA_HOMEWORK,
    DATA_MISSING,
    DATA_NEWS,
    DATA_SCHOOL_EVENTS,
)
from .coordinator import SycamoreDataUpdateCoordinator
from .entity import (
    SycamoreSchoolEntity,
    SycamoreServiceEntity,
    SycamoreStudentEntity,
)
from .helpers import parse_due_date

# Read-only, coordinator-driven entities: no per-entity polling to serialize.
PARALLEL_UPDATES = 0


def _due_iso(raw: object) -> str | None:
    """Normalize a missing item's raw Sycamore ``DueDate`` to an ISO date.

    Missing items keep the raw ``MM/DD/YYYY`` string (or ``None``); this matches
    the Upcoming sensor's ISO ``due`` so both attributes share one format.
    """
    parsed = parse_due_date(raw if isinstance(raw, str) else None)
    return parsed.isoformat() if parsed else None


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
        if coordinator.discipline_enabled:
            entities.append(SycamoreDisciplineSensor(coordinator, sid, name))
    if coordinator.school_id and coordinator.lunch_enabled:
        entities.append(SycamoreLunchSensor(coordinator))
    if coordinator.school_id and coordinator.events_enabled:
        entities.append(SycamoreNextEventSensor(coordinator))
    if coordinator.school_id and coordinator.news_enabled:
        entities.append(SycamoreNewsSensor(coordinator))
    entities.append(SycamoreLastUpdatedSensor(coordinator))
    async_add_entities(entities)

    # Per-class grade sensors and the profile-detail sensors are both added
    # dynamically. Classes appear as grades post; the detail sensors wait for
    # the profile endpoint to return — which may be a *later* refresh if it
    # failed/500'd at setup — so they must not be gated on the first refresh.
    known_grades: set[str] = set()
    known_details: set[str] = set()
    known_accounts: set[str] = set()

    @callback
    def _add_dynamic_entities() -> None:
        new: list[SensorEntity] = []
        students = (coordinator.data or {}).get("students", {})
        for student in coordinator.students:
            sid = student["id"]
            name = student["name"]
            sdata = students.get(sid, {})
            for grade in sdata.get(DATA_GRADES, []):
                subject = grade["subject"]
                key = f"{sid}:{subject}"
                if key in known_grades:
                    continue
                known_grades.add(key)
                new.append(SycamoreGradeSensor(coordinator, sid, name, subject))
                new.append(SycamoreGradePercentSensor(coordinator, sid, name, subject))
            if sid not in known_details and sdata.get(DATA_DETAILS):
                known_details.add(sid)
                new.append(SycamoreGradeLevelSensor(coordinator, sid, name))
                new.append(SycamoreHomeroomTeacherSensor(coordinator, sid, name))
        # Family account balances (e.g. cafeteria) arrive family-level and are
        # added as they appear, like grade sensors — the endpoint may only
        # succeed on a later refresh (or not at all, for schools without it).
        if coordinator.accounts_enabled:
            for account in (coordinator.data or {}).get(DATA_ACCOUNTS) or []:
                acct_id = account["id"]
                if acct_id in known_accounts:
                    continue
                known_accounts.add(acct_id)
                new.append(
                    SycamoreAccountSensor(coordinator, acct_id, account["name"])
                )
        if new:
            async_add_entities(new)

    _add_dynamic_entities()
    entry.async_on_unload(coordinator.async_add_listener(_add_dynamic_entities))


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

    @property
    def native_value(self) -> int:
        return len(self.student_data.get(DATA_MISSING, []))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        items = self.student_data.get(DATA_MISSING, [])
        return {
            # `assignments` stays a bare title list for backward compatibility;
            # `items` adds subject/due/description for richer cards & dashboards.
            "assignments": [i["title"] for i in items],
            "items": [
                {
                    "title": i["title"],
                    "subject": i["subject"],
                    "due": _due_iso(i.get("due")),
                    "description": i["description"],
                }
                for i in items
            ],
        }


class SycamoreUpcomingCountSensor(_StudentCountSensor):
    """Number of upcoming assignments within the focus window."""

    _slug = "upcoming_work"
    _attr_translation_key = "upcoming_work"

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
                    "description": i["description"],
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
        today = dt_util.now().date()
        items = [
            hw
            for hw in self.student_data.get(DATA_HOMEWORK, [])
            if hw["due"] >= today and (hw["is_test"] or not self._test_only)
        ]
        return min(items, key=lambda hw: hw["due"]) if items else None

    @property
    def native_value(self) -> datetime | None:
        item = self._next()
        if not item:
            return None
        due = item["due"]
        # Sycamore assignments carry a due *date*, not a time. Anchoring to
        # local midnight makes anything due *today* read as "this morning" (a
        # past relative time). Land the timestamp on the configured due-time if
        # the user set one (the same option the calendar uses), else the end of
        # the due day — so a due-today item stays in the future until the day is
        # actually over.
        event_time = self.coordinator.event_time
        if event_time is not None:
            return datetime.combine(
                due, event_time, tzinfo=dt_util.DEFAULT_TIME_ZONE
            )
        return (
            dt_util.start_of_local_day(due)
            + timedelta(days=1)
            - timedelta(seconds=1)
        )

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


class SycamoreNextTestSensor(_SycamoreNextBase):
    """Due date of the soonest upcoming test/quiz."""

    _slug = "next_test"
    _attr_translation_key = "next_test"
    _test_only = True


class SycamoreAttendanceSensor(_StudentCountSensor):
    """Attendance events count (absences/tardies as reported by the school)."""

    _slug = "attendance"
    _attr_translation_key = "attendance"

    @property
    def native_value(self) -> int:
        return self.student_data.get(DATA_ATTENDANCE, {}).get("count", 0)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"records": self.student_data.get(DATA_ATTENDANCE, {}).get("records", [])}


class SycamoreDisciplineSensor(_StudentCountSensor):
    """Discipline events count (as reported by the school's discipline log)."""

    _slug = "discipline"
    _attr_translation_key = "discipline"

    @property
    def native_value(self) -> int:
        return self.student_data.get(DATA_DISCIPLINE, {}).get("count", 0)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"records": self.student_data.get(DATA_DISCIPLINE, {}).get("records", [])}


class _SycamoreDetailSensor(SycamoreStudentEntity, SensorEntity):
    """Base for the static profile-detail sensors (grade level, homeroom)."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _detail_key: str
    _slug: str

    def __init__(self, coordinator, student_id, student_name) -> None:  # noqa: D107
        super().__init__(coordinator, student_id, student_name)
        self._attr_unique_id = (
            f"{coordinator.entry.entry_id}_{student_id}_{self._slug}"
        )

    @property
    def native_value(self) -> str | None:
        return self.student_data.get(DATA_DETAILS, {}).get(self._detail_key)


class SycamoreGradeLevelSensor(_SycamoreDetailSensor):
    """The student's grade level (e.g. '7th')."""

    _detail_key = "grade"
    _slug = "grade_level"
    _attr_translation_key = "grade_level"


class SycamoreHomeroomTeacherSensor(_SycamoreDetailSensor):
    """The student's homeroom teacher."""

    _detail_key = "homeroom_teacher"
    _slug = "homeroom_teacher"
    _attr_translation_key = "homeroom_teacher"


class SycamoreLunchSensor(SycamoreSchoolEntity, SensorEntity):
    """Today's cafeteria menu (school-level)."""

    _attr_translation_key = "todays_lunch"

    def __init__(self, coordinator: SycamoreDataUpdateCoordinator) -> None:
        """Initialize the lunch sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_todays_lunch"

    def _days(self) -> list[dict[str, Any]]:
        return (self.coordinator.data or {}).get("cafeteria") or []

    def _today_meals(self) -> list[dict[str, Any]]:
        today = dt_util.now().date()
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
        today_meals = self._today_meals()
        return {
            # Plain list of today's option names, for easy templating.
            "options": [m["name"] for m in today_meals],
            "meals": [
                {"name": m["name"], "description": m["description"]}
                for m in today_meals
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


class SycamoreAccountSensor(SycamoreSchoolEntity, SensorEntity):
    """Balance of one Sycamore family account (e.g. cafeteria)."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "USD"
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:cash"

    def __init__(
        self,
        coordinator: SycamoreDataUpdateCoordinator,
        account_id: str,
        account_name: str,
    ) -> None:
        """Track one account by its stable Sycamore id."""
        super().__init__(coordinator)
        self._account_id = account_id
        self._attr_name = f"{account_name} balance"
        self._attr_unique_id = (
            f"{coordinator.entry.entry_id}_account_{slugify(account_id)}"
        )

    def _account(self) -> dict[str, Any] | None:
        for account in (self.coordinator.data or {}).get(DATA_ACCOUNTS) or []:
            if account["id"] == self._account_id:
                return account
        return None

    @property
    def native_value(self) -> float | None:
        account = self._account()
        return account["amount"] if account else None

    @property
    def available(self) -> bool:
        """Available while the coordinator has this account in its last data."""
        return super().available and self._account() is not None


class SycamoreLastUpdatedSensor(SycamoreServiceEntity, SensorEntity):
    """When Sycamore was last polled successfully (integration health)."""

    _attr_translation_key = "last_updated"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: SycamoreDataUpdateCoordinator) -> None:
        """Initialize the last-updated sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_last_updated"

    @property
    def native_value(self) -> datetime | None:
        return self.coordinator.last_success


class SycamoreNextEventSensor(SycamoreSchoolEntity, SensorEntity):
    """Start time of the next upcoming school event (school-level)."""

    _attr_translation_key = "next_school_event"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: SycamoreDataUpdateCoordinator) -> None:
        """Initialize the next-event sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_next_school_event"

    def _next(self) -> dict[str, Any] | None:
        now = dt_util.now()
        upcoming = []
        for ev in (self.coordinator.data or {}).get(DATA_SCHOOL_EVENTS) or []:
            start = ev["start"]
            start_dt = (
                start
                if isinstance(start, datetime)
                else dt_util.start_of_local_day(start)
            )
            if start_dt >= now:
                upcoming.append((start_dt, ev))
        return min(upcoming, key=lambda t: t[0])[1] if upcoming else None

    @property
    def native_value(self) -> datetime | None:
        item = self._next()
        if item is None:
            return None
        start = item["start"]
        return start if isinstance(start, datetime) else dt_util.start_of_local_day(start)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        item = self._next()
        if item is None:
            return {}
        start = item["start"]
        return {
            "title": item["title"],
            "all_day": not isinstance(start, datetime),
        }


class SycamoreNewsSensor(SycamoreSchoolEntity, SensorEntity):
    """The school's latest news/announcement headline (school-level).

    State is the newest headline; the recent items (with their published
    timestamps) are exposed as attributes for an announcements-feed card.
    """

    _attr_translation_key = "latest_news"

    def __init__(self, coordinator: SycamoreDataUpdateCoordinator) -> None:
        """Initialize the latest-news sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_latest_news"

    def _items(self) -> list[dict[str, Any]]:
        return (self.coordinator.data or {}).get(DATA_NEWS) or []

    @property
    def native_value(self) -> str | None:
        # None = not fetched yet / degraded; [] = fetched but nothing posted (or
        # the school has no news feed); a list = real headlines.
        news = (self.coordinator.data or {}).get(DATA_NEWS)
        if news:
            return news[0]["title"][:255]
        return "No news" if news == [] else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        items = self._items()
        return {
            "count": len(items),
            "items": items,
            "latest_published": items[0]["published"] if items else None,
        }
