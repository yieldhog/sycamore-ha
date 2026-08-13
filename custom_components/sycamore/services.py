"""Services for the Sycamore integration.

`sycamore.sync_calendar` mirrors upcoming assignments, tests, and quizzes into a
writable calendar (e.g. a Google calendar). It only ever touches events it
created — identified by a hidden ``[sycamore-sync:<student>:<hash>]`` tag in the
description — so the user's own events are never affected, and because the tag
carries the student id, two children can safely share one calendar (each sync
only reconciles its own students' events).

Home Assistant exposes only `create_event`/`get_events` as calendar *services*
(delete/update are frontend-websocket only), so this reads events and deletes
stale ones via the target calendar entity's own methods — the same calls the
dashboard uses — and creates via the public `create_event` service.

Targets are resolved per student: the service's `target_calendar` (if given)
overrides everything; otherwise each student's calendar comes from the entry
options mapping (`CONF_CALENDAR_TARGETS`). The same reconcile powers the opt-in
auto-sync (`async_run_autosync`), run from a coordinator listener.
"""

from __future__ import annotations

import hashlib
import logging
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

import voluptuous as vol
from homeassistant.components.calendar import CalendarEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from .const import (
    CONF_CALENDAR_DAYS,
    CONF_CALENDAR_TARGETS,
    DATA_HOMEWORK,
    DEFAULT_CALENDAR_DAYS,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

SERVICE_SYNC_CALENDAR = "sync_calendar"
ATTR_TARGET = "target_calendar"
ATTR_DAYS = "days"
ATTR_PREFIX_NAME = "prefix_student_name"
ATTR_STUDENT = "student"

_TAG = "sycamore-sync:"

SYNC_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_TARGET): cv.entity_id,
        vol.Optional(ATTR_STUDENT): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(ATTR_DAYS, default=DEFAULT_CALENDAR_DAYS): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=90)
        ),
        vol.Optional(ATTR_PREFIX_NAME, default=True): cv.boolean,
    }
)


def _item_hash(student_id: str, hw: dict[str, Any]) -> str:
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


def _description(hw: dict[str, Any], student_id: str, item_hash: str) -> str:
    parts: list[str] = []
    if hw.get("subject"):
        parts.append(hw["subject"])
    if hw.get("description"):
        parts.append(hw["description"])
    parts.append(f"[{_TAG}{student_id}:{item_hash}]")
    return "\n\n".join(parts)


def _parse_tag(description: str | None) -> tuple[str, str] | None:
    """Return (student_id, item_hash) from one of our events, else None."""
    marker = f"[{_TAG}"
    if not description or marker not in description:
        return None
    inner = description.split(marker, 1)[1].split("]", 1)[0]
    student_id, _, item_hash = inner.partition(":")
    if not student_id or not item_hash:
        return None
    return student_id, item_hash


def _get_calendar_entity(hass: HomeAssistant, entity_id: str):
    component = hass.data.get("calendar")
    return component.get_entity(entity_id) if component else None


def _student_matches(student: dict[str, str], wanted: list[str]) -> bool:
    ident = {student["id"].lower(), student["name"].lower()}
    return any(w.strip().lower() in ident for w in wanted)


async def _reconcile_calendar(
    hass: HomeAssistant,
    target: str,
    pairs: list[tuple[Any, dict[str, str]]],
    today: date,
    horizon: date,
    prefix: bool,
) -> dict[str, int] | None:
    """Reconcile one calendar against the homework of the students mapped to it.

    `pairs` is a list of (coordinator, student) that all sync into `target`.
    Only events tagged for those students are considered, so other students'
    events on a shared calendar are never touched.
    """
    entity = _get_calendar_entity(hass, target)
    if entity is None:
        _LOGGER.warning("sycamore.sync_calendar: calendar %s not found", target)
        return None
    if not entity.supported_features & CalendarEntityFeature.CREATE_EVENT:
        _LOGGER.warning("sycamore.sync_calendar: %s cannot have events added", target)
        return None
    can_delete = bool(entity.supported_features & CalendarEntityFeature.DELETE_EVENT)

    # Desired: {(student_id, item_hash): (student_name, homework)} in the window.
    desired: dict[tuple[str, str], tuple[str, dict[str, Any]]] = {}
    sids: set[str] = set()
    for coordinator, student in pairs:
        sid = student["id"]
        sids.add(sid)
        if coordinator is None or not coordinator.data:
            continue
        students = coordinator.data.get("students", {})
        for hw in students.get(sid, {}).get(DATA_HOMEWORK, []):
            if today <= hw["due"] <= horizon:
                desired[(sid, _item_hash(sid, hw))] = (student["name"], hw)

    # Existing events we created for *these* students (ignore everyone else's).
    start = dt_util.start_of_local_day(today)
    end = dt_util.start_of_local_day(horizon) + timedelta(days=1)
    existing: list[tuple[str, str, str]] = []  # (student_id, item_hash, event_uid)
    for event in await entity.async_get_events(hass, start, end):
        tag = _parse_tag(event.description)
        if tag and tag[0] in sids and event.uid:
            existing.append((tag[0], tag[1], event.uid))
    existing_keys = {(sid, h) for sid, h, _ in existing}

    created = 0
    for (sid, item_hash), (name, hw) in desired.items():
        if (sid, item_hash) in existing_keys:
            continue
        await hass.services.async_call(
            "calendar",
            "create_event",
            {
                "entity_id": target,
                "summary": _summary(name, hw, prefix),
                "description": _description(hw, sid, item_hash),
                "start_date": hw["due"].isoformat(),
                "end_date": (hw["due"] + timedelta(days=1)).isoformat(),
            },
            blocking=True,
        )
        created += 1

    stale = [uid for sid, h, uid in existing if (sid, h) not in desired]
    deleted = 0
    if stale and not can_delete:
        _LOGGER.warning(
            "sycamore.sync_calendar: %s stale event(s) on %s can't be removed "
            "(calendar has no delete support)",
            len(stale),
            target,
        )
    elif can_delete:
        for uid in stale:
            await entity.async_delete_event(uid)
            deleted += 1

    return {"created": created, "deleted": deleted, "unchanged": len(existing) - deleted}


async def _reconcile(
    hass: HomeAssistant,
    assignments: list[tuple[str, Any, dict[str, str]]],
    days: int,
    prefix: bool,
) -> ServiceResponse:
    """Group (calendar, coordinator, student) assignments by calendar and sync."""
    today = dt_util.now().date()
    horizon = today + timedelta(days=days)
    by_calendar: dict[str, list[tuple[Any, dict[str, str]]]] = defaultdict(list)
    for target, coordinator, student in assignments:
        by_calendar[target].append((coordinator, student))

    created = deleted = 0
    per_calendar: dict[str, Any] = {}
    for target, pairs in by_calendar.items():
        result = await _reconcile_calendar(
            hass, target, pairs, today, horizon, prefix
        )
        if result is None:
            continue
        created += result["created"]
        deleted += result["deleted"]
        per_calendar[target] = result
    _LOGGER.info(
        "sycamore.sync_calendar: %s created, %s deleted across %s calendar(s)",
        created,
        deleted,
        len(per_calendar),
    )
    return {"created": created, "deleted": deleted, "calendars": per_calendar}


def _assignments_for_entry(
    entry: ConfigEntry,
    coordinator: Any,
    *,
    override_target: str | None,
    wanted: list[str] | None,
) -> list[tuple[str, Any, dict[str, str]]]:
    """Build (calendar, coordinator, student) for one entry's students.

    Target precedence: the service's `override_target` wins for every selected
    student; otherwise each student's calendar comes from the options mapping.
    Students with no resolved calendar are skipped.
    """
    targets: dict[str, str] = entry.options.get(CONF_CALENDAR_TARGETS, {})
    out: list[tuple[str, Any, dict[str, str]]] = []
    for student in coordinator.students:
        if wanted and not _student_matches(student, wanted):
            continue
        target = override_target or targets.get(student["id"])
        if target:
            out.append((target, coordinator, student))
    return out


async def async_run_autosync(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reconcile every mapped student for one entry (opt-in, from a listener)."""
    coordinator = getattr(entry, "runtime_data", None)
    if coordinator is None:
        return
    days = entry.options.get(CONF_CALENDAR_DAYS, DEFAULT_CALENDAR_DAYS)
    assignments = _assignments_for_entry(
        entry, coordinator, override_target=None, wanted=None
    )
    if not assignments:
        return
    try:
        await _reconcile(hass, assignments, days, True)
    except Exception:  # noqa: BLE001 — never let auto-sync break a refresh
        _LOGGER.exception("sycamore: calendar auto-sync failed")


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register the Sycamore services (once)."""
    if hass.services.has_service(DOMAIN, SERVICE_SYNC_CALENDAR):
        return

    async def _sync_calendar(call: ServiceCall) -> ServiceResponse:
        override_target: str | None = call.data.get(ATTR_TARGET)
        wanted: list[str] | None = call.data.get(ATTR_STUDENT)
        days: int = call.data[ATTR_DAYS]
        prefix: bool = call.data[ATTR_PREFIX_NAME]

        assignments: list[tuple[str, Any, dict[str, str]]] = []
        for entry in hass.config_entries.async_entries(DOMAIN):
            coordinator = getattr(entry, "runtime_data", None)
            if coordinator is None:
                continue
            assignments.extend(
                _assignments_for_entry(
                    entry, coordinator, override_target=override_target, wanted=wanted
                )
            )

        if not assignments:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="no_sync_targets",
            )
        return await _reconcile(hass, assignments, days, prefix)

    hass.services.async_register(
        DOMAIN,
        SERVICE_SYNC_CALENDAR,
        _sync_calendar,
        schema=SYNC_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
