"""Todo platform: missing work as a read-only checklist."""

from __future__ import annotations

from homeassistant.components.todo import TodoItem, TodoItemStatus, TodoListEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify

from . import SycamoreConfigEntry
from .const import DATA_MISSING
from .entity import SycamoreStudentEntity

# Read-only, coordinator-driven entities: no per-entity polling to serialize.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SycamoreConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one missing-work todo list per student."""
    coordinator = entry.runtime_data
    async_add_entities(
        SycamoreMissingTodoList(coordinator, s["id"], s["name"])
        for s in coordinator.students
    )


class SycamoreMissingTodoList(SycamoreStudentEntity, TodoListEntity):
    """Read-only list of the student's missing assignments.

    Sycamore is the source of truth (items can't be completed from HA), so no
    write features are advertised; the list refreshes with the coordinator.
    """

    _attr_translation_key = "missing_work"
    _attr_icon = "mdi:format-list-checks"

    def __init__(self, coordinator, student_id, student_name) -> None:  # noqa: D107
        super().__init__(coordinator, student_id, student_name)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{student_id}_missing_todo"

    @property
    def todo_items(self) -> list[TodoItem]:
        """Current missing assignments as needs-action todo items."""
        items: list[TodoItem] = []
        for idx, m in enumerate(self.student_data.get(DATA_MISSING, [])):
            subject = m.get("subject") or ""
            summary = f"{subject}: {m['title']}" if subject else m["title"]
            items.append(
                TodoItem(
                    uid=f"{slugify(subject)}-{slugify(m['title'])}-{idx}",
                    summary=summary[:255],
                    status=TodoItemStatus.NEEDS_ACTION,
                )
            )
        return items
