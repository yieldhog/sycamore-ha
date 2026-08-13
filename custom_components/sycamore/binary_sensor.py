"""Binary sensor platform for the Sycamore integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import SycamoreConfigEntry
from .const import DATA_HOMEWORK, DATA_MISSING
from .coordinator import SycamoreDataUpdateCoordinator
from .entity import SycamoreServiceEntity, SycamoreStudentEntity

# Read-only, coordinator-driven entities: no per-entity polling to serialize.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SycamoreConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Sycamore binary sensors."""
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = []
    for student in coordinator.students:
        entities.append(
            SycamoreMissingWorkBinarySensor(coordinator, student["id"], student["name"])
        )
        entities.append(
            SycamoreTestSoonBinarySensor(coordinator, student["id"], student["name"])
        )
    entities.append(SycamoreStatusBinarySensor(coordinator))
    async_add_entities(entities)


class SycamoreMissingWorkBinarySensor(SycamoreStudentEntity, BinarySensorEntity):
    """On when the student has any missing work."""

    _attr_translation_key = "has_missing_work"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator, student_id, student_name) -> None:  # noqa: D107
        super().__init__(coordinator, student_id, student_name)
        self._attr_unique_id = (
            f"{coordinator.entry.entry_id}_{student_id}_has_missing_work"
        )

    @property
    def is_on(self) -> bool:
        return bool(self.student_data.get(DATA_MISSING))


class SycamoreTestSoonBinarySensor(SycamoreStudentEntity, BinarySensorEntity):
    """On when a test/quiz is due within the next day."""

    _attr_translation_key = "test_within_24h"

    def __init__(self, coordinator, student_id, student_name) -> None:  # noqa: D107
        super().__init__(coordinator, student_id, student_name)
        self._attr_unique_id = (
            f"{coordinator.entry.entry_id}_{student_id}_test_within_24h"
        )

    def _tests_soon(self) -> list[dict[str, Any]]:
        today = dt_util.now().date()
        out = []
        for hw in self.student_data.get(DATA_HOMEWORK, []):
            if hw["is_test"] and 0 <= (hw["due"] - today).days <= 1:
                out.append(hw)
        return out

    @property
    def is_on(self) -> bool:
        return bool(self._tests_soon())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "tests": [
                {"title": t["title"], "subject": t["subject"], "due": t["due"].isoformat()}
                for t in self._tests_soon()
            ]
        }


class SycamoreStatusBinarySensor(SycamoreServiceEntity, BinarySensorEntity):
    """On when the last Sycamore refresh failed (integration health).

    Stays available even during a failure (see SycamoreServiceEntity) so it can
    actually report the problem, with the error surfaced as an attribute.
    """

    _attr_translation_key = "status"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: SycamoreDataUpdateCoordinator) -> None:
        """Initialize the status binary sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_status"

    @property
    def is_on(self) -> bool:
        return not self.coordinator.last_update_success

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        error = self.coordinator.last_exception
        degraded = [
            f"{d['section']} ({d['student']}): {d['error']}"
            for d in self.coordinator.degraded
        ]
        return {
            "error": str(error) if error else None,
            "last_success": (
                self.coordinator.last_success.isoformat()
                if self.coordinator.last_success
                else None
            ),
            # Sections that errored but were tolerated this refresh (empty when
            # all data loaded). Lets you tell "endpoint erroring" from "no data".
            "degraded": degraded or None,
        }
