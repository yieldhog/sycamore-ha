"""Base entities for the Sycamore integration."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DATA_DETAILS, DOMAIN, MANUFACTURER
from .coordinator import SycamoreDataUpdateCoordinator


class SycamoreStudentEntity(CoordinatorEntity[SycamoreDataUpdateCoordinator]):
    """Base entity tied to a single student (one HA device per student)."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SycamoreDataUpdateCoordinator,
        student_id: str,
        student_name: str,
    ) -> None:
        """Initialize the student entity and its device info."""
        super().__init__(coordinator)
        self._student_id = student_id
        self._student_name = student_name
        # Enrich the device with the student's grade level when we have it
        # (details are fetched in the first refresh before entities are added).
        details = (
            (coordinator.data or {})
            .get("students", {})
            .get(student_id, {})
            .get(DATA_DETAILS, {})
        )
        grade = details.get("grade")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.entry.entry_id}_{student_id}")},
            name=student_name,
            manufacturer=MANUFACTURER,
            model=f"{grade} Grade" if grade else "Student",
        )

    @property
    def student_data(self) -> dict[str, Any]:
        """This student's shaped data bundle from the coordinator."""
        students = (self.coordinator.data or {}).get("students", {})
        return students.get(self._student_id, {})

    @property
    def available(self) -> bool:
        """Available when the coordinator succeeded and this student is present."""
        return super().available and bool(self.student_data)


class SycamoreSchoolEntity(CoordinatorEntity[SycamoreDataUpdateCoordinator]):
    """Base entity for school-level data (e.g. the cafeteria menu)."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SycamoreDataUpdateCoordinator) -> None:
        """Initialize the school entity and its device info."""
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.entry.entry_id}_school")},
            name="School",
            manufacturer=MANUFACTURER,
            model="School",
        )
