"""Services for the Sycamore integration.

`sycamore.sync_calendar` mirrors upcoming assignments, tests, and quizzes into a
writable calendar (e.g. a Google calendar). It only ever touches events it
created — identified by a hidden tag in the description — so the user's own
events are never affected.

Home Assistant exposes only `create_event`/`get_events` as calendar *services*
(delete/update are frontend-websocket only), so this reads events and deletes
stale ones via the target calendar entity's own methods — the same calls the
dashboard uses — and creates via the public `create_event` service.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import timedelta
from typing import Any

import voluptuous as vol
from homeassistant.components.calendar import CalendarEntityFeature
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from .const import DATA_HOMEWORK, DOMAIN

_LOGGER = logging.getLogger(__name__)

SERVICE_SYNC_CALENDAR = "sync_calendar"
ATTR_TARGET = "target_calendar"
ATTR_DAYS = "days"
ATTR_PREFIX_NAME = "prefix_student_name"

_TAG = "sycamore-sync:"

SYNC_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_TARGET): cv.entity_id,
        vol.Optional(ATTR_DAYS, default=14): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=90)
        ),
        vol.Optional(ATTR_PREFIX_NAME, default=True): cv.boolean,
    }
)


def _sync_uid(student_id: str, hw: dict[str, Any]) -> str:
    """Stable id for a homework item (changes if title/subject/due changes).

    Because a changed due date yields a new id, the old event falls out of the
    desired set and is deleted while the new one is created — no update needed.
    """
    raw = f"{student_id}|{hw['subject']}|{hw['title']}|{hw['due'].isoformat()}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _summary(name: str, hw: dict[str, Any], prefix_name: bool) -> str:
    kind = f"[{hw['kind'].upper()}] " if hw["is_test"] and hw["kind"] else ""
    label = f"{kind}{hw['title']}"
    return (f"{name}: {label}" if prefix_name else label)[:255]


def _description(hw: dict[str, Any], uid: str) -> str:
    parts: list[str] = []
    if hw.get("subject"):
        parts.append(hw["subject"])
    if hw.get("description"):
        parts.append(hw["description"])
    parts.append(f"[{_TAG}{uid}]")
    return "\n\n".join(parts)


def _extract_uid(description: str | None) -> str | None:
    marker = f"[{_TAG}"
    if not description or marker not in description:
        return None
    return description.split(marker, 1)[1].split("]", 1)[0] or None


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register the Sycamore services (once)."""
    if hass.services.has_service(DOMAIN, SERVICE_SYNC_CALENDAR):
        return

    async def _sync_calendar(call: ServiceCall) -> ServiceResponse:
        target: str = call.data[ATTR_TARGET]
        days: int = call.data[ATTR_DAYS]
        prefix: bool = call.data[ATTR_PREFIX_NAME]

        component = hass.data.get("calendar")
        entity = component.get_entity(target) if component else None
        if entity is None:
            raise ServiceValidationError(f"Calendar entity {target} not found")
        if not entity.supported_features & CalendarEntityFeature.CREATE_EVENT:
            raise ServiceValidationError(f"{target} cannot have events added")
        can_delete = bool(
            entity.supported_features & CalendarEntityFeature.DELETE_EVENT
        )

        today = dt_util.now().date()
        horizon = today + timedelta(days=days)

        # Desired set: every homework item in the window, across all entries.
        desired: dict[str, tuple[str, dict[str, Any]]] = {}
        for entry in hass.config_entries.async_entries(DOMAIN):
            coordinator = getattr(entry, "runtime_data", None)
            if coordinator is None or not coordinator.data:
                continue
            students = coordinator.data.get("students", {})
            for student in coordinator.students:
                sid = student["id"]
                name = student["name"]
                for hw in students.get(sid, {}).get(DATA_HOMEWORK, []):
                    if today <= hw["due"] <= horizon:
                        desired[_sync_uid(sid, hw)] = (name, hw)

        # Events we previously created on the target: (our tag uid, event uid).
        start = dt_util.start_of_local_day(today)
        end = dt_util.start_of_local_day(horizon) + timedelta(days=1)
        existing: list[tuple[str, str]] = []
        for event in await entity.async_get_events(hass, start, end):
            uid = _extract_uid(event.description)
            if uid and event.uid:
                existing.append((uid, event.uid))
        existing_uids = {uid for uid, _ in existing}

        created = 0
        for uid, (name, hw) in desired.items():
            if uid in existing_uids:
                continue
            await hass.services.async_call(
                "calendar",
                "create_event",
                {
                    "entity_id": target,
                    "summary": _summary(name, hw, prefix),
                    "description": _description(hw, uid),
                    "start_date": hw["due"].isoformat(),
                    "end_date": (hw["due"] + timedelta(days=1)).isoformat(),
                },
                blocking=True,
            )
            created += 1

        stale = [event_uid for uid, event_uid in existing if uid not in desired]
        deleted = 0
        if stale and not can_delete:
            _LOGGER.warning(
                "sycamore.sync_calendar: %s stale event(s) on %s can't be "
                "removed (calendar has no delete support)",
                len(stale),
                target,
            )
        elif can_delete:
            for event_uid in stale:
                await entity.async_delete_event(event_uid)
                deleted += 1

        _LOGGER.info(
            "sycamore.sync_calendar: %s created, %s deleted on %s",
            created,
            deleted,
            target,
        )
        return {
            "created": created,
            "deleted": deleted,
            "unchanged": sum(1 for uid, _ in existing if uid in desired),
        }

    hass.services.async_register(
        DOMAIN,
        SERVICE_SYNC_CALENDAR,
        _sync_calendar,
        schema=SYNC_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
