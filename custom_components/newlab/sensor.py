"""Sensor platform for the Newlab LED integration.

Exposes hub-level diagnostic sensors on the Newlab LED Controller device:

  NewlabPlantCodeSensor   — Codice Impianto (serial/plant identifier)
  NewlabCloudVersionSensor — Versione Cloud  (e.g. "3.47")
  NewlabCloudSyncSensor   — Ultima sincronizzazione cloud (as reported by Newlab)

All three are EntityCategory.DIAGNOSTIC so they appear in the "Diagnostics"
section of the device card in HA, keeping the main entity list clean.
They are hub-level (one per config entry, not one per group).
"""

from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import NewlabCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Newlab diagnostic sensors from a config entry."""
    coordinator: NewlabCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        NewlabPlantCodeSensor(coordinator),
        NewlabCloudVersionSensor(coordinator),
        NewlabCloudSyncSensor(coordinator),
    ]
    _LOGGER.debug(
        "[sensor] async_setup_entry: registering %d diagnostic sensor(s)",
        len(entities),
    )
    async_add_entities(entities)


# ── Base class ────────────────────────────────────────────────────────────────

class _NewlabHubSensor(CoordinatorEntity[NewlabCoordinator], SensorEntity):
    """Base class for hub-level diagnostic sensors."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_should_poll = False

    def __init__(self, coordinator: NewlabCoordinator) -> None:
        super().__init__(coordinator)

    @property
    def device_info(self):
        """Delegate to coordinator.hub_device_info (single source of truth)."""
        return self.coordinator.hub_device_info


# ── Codice Impianto ───────────────────────────────────────────────────────────

class NewlabPlantCodeSensor(_NewlabHubSensor):
    """Diagnostic sensor: Codice Impianto (plant/installation identifier).

    Shown in the Diagnostics section of the device card.
    Value is extracted from the cloud HTML once at integration load (first successful poll).
    State is 'unknown' (not 'unavailable') if the value cannot be parsed from HTML.
    """

    _attr_unique_id = "newlab_hub_plant_code"
    _attr_name = "Codice Impianto"
    _attr_icon = "mdi:identifier"

    @property
    def native_value(self) -> str | None:
        """Return the plant code, or None if not yet discovered."""
        return self.coordinator.plant_code or None


# ── Versione Cloud ────────────────────────────────────────────────────────────

class NewlabCloudVersionSensor(_NewlabHubSensor):
    """Diagnostic sensor: Versione Cloud (app/firmware version from page title).

    Example value: "3.47"
    State is 'unknown' (not 'unavailable') if not parseable from cloud HTML.
    """

    _attr_unique_id = "newlab_hub_cloud_version"
    _attr_name = "Versione Cloud"
    _attr_icon = "mdi:tag-outline"

    @property
    def native_value(self) -> str | None:
        return self.coordinator.cloud_version or None


# ── Ultima sincronizzazione cloud ─────────────────────────────────────────────

class NewlabCloudSyncSensor(_NewlabHubSensor):
    """Diagnostic sensor: Ultima sincronizzazione cloud.

    The timestamp shown by the Newlab cloud itself (when the physical controller
    last synchronized with the cloud). This is NOT the HA polling timestamp.

    Example value: "Lunedì 16 Febbraio 2026 19:01"
    State is 'unknown' (not 'unavailable') if not parseable from cloud HTML.
    """

    _attr_unique_id = "newlab_hub_cloud_sync"
    _attr_name = "Ultima Sincronizzazione Cloud"
    _attr_icon = "mdi:cloud-sync-outline"

    @property
    def native_value(self) -> str | None:
        return self.coordinator.cloud_last_sync or None
