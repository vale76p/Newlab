"""Button platform for the Newlab LED integration.

Exposes a single hub-level button on the Newlab LED Controller device:

  NewlabRefreshButton — Aggiorna Impianto
      Calls POST /smarthome/plantrefresh, waits 5 s (as the web app does),
      then triggers a coordinator refresh to update all entity states.
"""

from __future__ import annotations

import asyncio
import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import NewlabCoordinator

_LOGGER = logging.getLogger(__name__)

# Seconds to wait after plantrefresh before requesting a coordinator update.
# The Newlab web app uses 5 s; we use the same value.
_REFRESH_SETTLE_DELAY = 5


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Newlab refresh button from a config entry."""
    coordinator: NewlabCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([NewlabRefreshButton(coordinator)])
    _LOGGER.debug("[button] async_setup_entry: registered NewlabRefreshButton")


class NewlabRefreshButton(CoordinatorEntity[NewlabCoordinator], ButtonEntity):
    """Button that triggers a plant refresh on the Newlab cloud.

    When pressed:
      1. POST /smarthome/plantrefresh  → cloud re-syncs with physical controller
      2. Wait _REFRESH_SETTLE_DELAY s  → give the cloud time to update state
      3. Coordinator refresh           → HA pulls fresh state for all entities

    This is the same sequence the Newlab web UI performs when the user clicks
    the "Aggiorna" button on the plant page.
    """

    _attr_unique_id = "newlab_hub_plant_refresh"
    _attr_name = "Aggiorna Impianto"
    _attr_icon = "mdi:refresh"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_should_poll = False

    def __init__(self, coordinator: NewlabCoordinator) -> None:
        super().__init__(coordinator)

    @property
    def device_info(self):
        """Delegate to coordinator.hub_device_info (single source of truth)."""
        return self.coordinator.hub_device_info

    async def async_press(self) -> None:
        """Handle button press: refresh plant then update coordinator."""
        _LOGGER.debug("[button] Aggiorna Impianto pressed")

        success = await self.coordinator.api.async_refresh_plant()

        if success:
            _LOGGER.info(
                "[button] plantrefresh OK — waiting %ds for cloud to settle…",
                _REFRESH_SETTLE_DELAY,
            )
            await asyncio.sleep(_REFRESH_SETTLE_DELAY)
            await self.coordinator.async_request_refresh()
            _LOGGER.info("[button] coordinator refresh requested after plantrefresh")
        else:
            _LOGGER.warning(
                "[button] plantrefresh failed — coordinator refresh skipped"
            )
