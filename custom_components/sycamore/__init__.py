"""The Sycamore School integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from .api import SycamoreClient
from .const import CONF_CALENDAR_AUTOSYNC, CONF_TOKEN, DOMAIN
from .coordinator import SycamoreDataUpdateCoordinator
from .services import async_run_autosync, async_setup_services

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.CALENDAR,
    Platform.TODO,
]

type SycamoreConfigEntry = ConfigEntry[SycamoreDataUpdateCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: SycamoreConfigEntry) -> bool:
    """Set up Sycamore from a config entry."""
    client = SycamoreClient(hass, entry.data[CONF_TOKEN])
    coordinator = SycamoreDataUpdateCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    await async_setup_services(hass)

    # Opt-in: reconcile the per-student calendar mapping after every refresh.
    if entry.options.get(CONF_CALENDAR_AUTOSYNC):

        def _autosync() -> None:
            hass.async_create_task(async_run_autosync(hass, entry))

        entry.async_on_unload(coordinator.async_add_listener(_autosync))
        # Run once now so enabling it doesn't wait for the next poll.
        hass.async_create_task(async_run_autosync(hass, entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: SycamoreConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_config_entry_device(
    hass: HomeAssistant,
    entry: SycamoreConfigEntry,
    device: DeviceEntry,
) -> bool:
    """Allow deleting a device only once the entry no longer provides it.

    A device is "live" if it maps to a currently-configured student, or is the
    school / service device. Anything else is stale (e.g. a student that's no
    longer configured) and the user may remove it from the UI.
    """
    coordinator = getattr(entry, "runtime_data", None)
    if coordinator is None:
        return True
    live_ids = {f"{entry.entry_id}_{s['id']}" for s in coordinator.students}
    live_ids.add(f"{entry.entry_id}_school")
    live_ids.add(f"{entry.entry_id}_service")
    return not any(
        domain == DOMAIN and ident in live_ids
        for domain, ident in device.identifiers
    )


async def _async_reload_entry(hass: HomeAssistant, entry: SycamoreConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)
