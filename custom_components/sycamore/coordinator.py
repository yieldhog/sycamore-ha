"""DataUpdateCoordinator for the Sycamore integration."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import SycamoreAuthError, SycamoreClient, SycamoreConnectionError
from .const import (
    CONF_FOCUS_WINDOW_DAYS,
    CONF_SCAN_INTERVAL_MINUTES,
    CONF_SCHOOL_ID,
    CONF_STUDENT_ID,
    CONF_STUDENT_NAME,
    CONF_STUDENTS,
    DATA_ATTENDANCE,
    DATA_CAFETERIA,
    DATA_GRADES,
    DATA_HOMEWORK,
    DATA_MISSING,
    DATA_NAME,
    DEFAULT_FOCUS_WINDOW_DAYS,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
)
from .helpers import (
    clean_subject_name,
    detect_kind,
    parse_due_date,
    strip_html,
    subject_icon,
    to_float,
)

_LOGGER = logging.getLogger(__name__)


class SycamoreDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch and shape all configured students' data in one refresh."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: SycamoreClient,
    ) -> None:
        """Initialize the coordinator from the config entry + options."""
        self.entry = entry
        self.client = client
        options = entry.options
        self._students: list[dict[str, str]] = entry.data.get(CONF_STUDENTS, [])
        self._school_id: str | None = entry.data.get(CONF_SCHOOL_ID) or None
        self._focus_window: int = int(
            options.get(CONF_FOCUS_WINDOW_DAYS, DEFAULT_FOCUS_WINDOW_DAYS)
        )
        interval = int(
            options.get(CONF_SCAN_INTERVAL_MINUTES, DEFAULT_SCAN_INTERVAL_MINUTES)
        )
        # (student_id, class_name) -> last seen numeric score, for trend arrows.
        self._prev_scores: dict[tuple[str, str], float] = {}

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=interval),
        )

    @property
    def students(self) -> list[dict[str, str]]:
        """Configured students: list of {id, name}."""
        return self._students

    @property
    def school_id(self) -> str | None:
        """School id used for the cafeteria menu, if configured."""
        return self._school_id

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch every student concurrently and reshape into entity-ready data."""
        today = datetime.now().date()
        try:
            results = await asyncio.gather(
                *(self._fetch_student(s, today) for s in self._students)
            )
            cafeteria: list[dict[str, Any]] | None = None
            if self._school_id:
                cafeteria = await self.client.async_get_cafeteria(self._school_id)
        except SycamoreAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except SycamoreConnectionError as err:
            raise UpdateFailed(str(err)) from err

        return {
            "students": {sid: data for sid, data in results},
            DATA_CAFETERIA: cafeteria,
        }

    async def _fetch_student(
        self, student: dict[str, str], today: date
    ) -> tuple[str, dict[str, Any]]:
        """Fetch one student's endpoints and shape the payload."""
        sid = student[CONF_STUDENT_ID]
        grades_raw, homework_raw, missing_raw, attendance_raw = await asyncio.gather(
            self.client.async_get_grades(sid),
            self.client.async_get_homework(sid),
            self.client.async_get_missing(sid),
            self.client.async_get_attendance(sid),
        )

        data: dict[str, Any] = {
            DATA_NAME: student[CONF_STUDENT_NAME],
            DATA_GRADES: self._shape_grades(sid, grades_raw),
            DATA_HOMEWORK: self._shape_homework(homework_raw, today),
            DATA_MISSING: self._shape_missing(missing_raw),
            DATA_ATTENDANCE: self._shape_attendance(attendance_raw),
        }
        return sid, data

    def _shape_grades(
        self, sid: str, raw: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for g in raw:
            name = clean_subject_name(g.get("ClassName", ""))
            if not name:
                continue
            number = to_float(g.get("Number"))
            prev = self._prev_scores.get((sid, name))
            if number is None or prev is None or number == prev:
                trend = "stable"
            elif number > prev:
                trend = "up"
            else:
                trend = "down"
            if number is not None:
                self._prev_scores[(sid, name)] = number
            out.append(
                {
                    "subject": name,
                    "letter": (g.get("Letter") or "").strip(),
                    "number": number,
                    "pdate": g.get("PDate"),
                    "trend": trend,
                    "icon": subject_icon(name),
                }
            )
        return out

    def _shape_homework(
        self, raw: list[dict[str, Any]], today: date
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        horizon = today + timedelta(days=self._focus_window)
        for hw in raw:
            due = parse_due_date(hw.get("DueDate"))
            if due is None:
                continue
            title = (hw.get("Title") or "").strip()
            subject = clean_subject_name(hw.get("ClassName", ""))
            is_test, kind = detect_kind(title)
            out.append(
                {
                    "title": title,
                    "subject": subject,
                    "due": due,
                    "is_test": is_test,
                    "kind": kind,
                    "description": strip_html(hw.get("Description")),
                    "in_focus": today <= due <= horizon,
                    "icon": subject_icon(subject),
                }
            )
        out.sort(key=lambda e: (e["due"], e["title"]))
        return out

    def _shape_missing(self, raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in raw:
            title = (m.get("Title") or "").strip()
            if not title:
                continue
            out.append(
                {
                    "title": title,
                    "subject": clean_subject_name(m.get("ClassName", "")),
                    "due": m.get("DueDate"),
                    "description": strip_html(m.get("Description")),
                }
            )
        return out

    def _shape_attendance(self, raw: list[dict[str, Any]]) -> dict[str, Any]:
        # Records vary by school config; keep a count plus the raw rows as an
        # attribute so users can template whatever their school reports.
        return {"count": len(raw), "records": raw}
