"""Diagnostics support for the Sycamore integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import SycamoreConfigEntry
from .const import (
    CONF_FAMILY_ID,
    CONF_SCHOOL_ID,
    CONF_STUDENTS,
    CONF_TOKEN,
    DATA_NAME,
)

# Redact credentials and anything that identifies a child or a staff member: the
# token/ids, the student's display name (DATA_NAME), and the teacher/advisor
# names from the profile. Academic values (grades, homework) are kept but
# de-identified, so diagnostics stay useful for debugging without naming anyone.
TO_REDACT = {
    CONF_TOKEN,
    CONF_FAMILY_ID,
    CONF_SCHOOL_ID,
    CONF_STUDENTS,
    "id",
    DATA_NAME,
    "homeroom_teacher",
    "advisor",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: SycamoreConfigEntry
) -> dict[str, Any]:
    """Return redacted diagnostics for a config entry."""
    coordinator = entry.runtime_data
    data = coordinator.data or {}
    # Re-key students by index so the raw Sycamore student IDs (the dict keys)
    # aren't disclosed, and redact each bundle's identifying fields.
    students = data.get("students", {})
    redacted_students = {
        f"student_{index}": async_redact_data(bundle, TO_REDACT)
        for index, bundle in enumerate(students.values())
    }
    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "data": {**data, "students": redacted_students},
    }
