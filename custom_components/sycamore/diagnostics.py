"""Diagnostics support for the Sycamore integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import SycamoreConfigEntry
from .const import CONF_FAMILY_ID, CONF_SCHOOL_ID, CONF_STUDENTS, CONF_TOKEN

TO_REDACT = {CONF_TOKEN, CONF_FAMILY_ID, CONF_SCHOOL_ID, "id", CONF_STUDENTS}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: SycamoreConfigEntry
) -> dict[str, Any]:
    """Return redacted diagnostics for a config entry."""
    coordinator = entry.runtime_data
    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "data": async_redact_data(coordinator.data or {}, TO_REDACT),
    }
