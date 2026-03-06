"""Light platform for the Newlab LED integration.

Each discovered Newlab group (zone) is exposed as a LightEntity with:
  - on/off control
  - brightness (maps directly to PWM 0–255, same scale)

State is read from coordinator.data — no direct API calls on update.
Commands go through coordinator.api.set_light() with optimistic local update.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import NewlabGroup
from .const import DOMAIN
from .coordinator import NewlabCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Newlab lights from a config entry.

    Creates one NewlabLight per group discovered in the first coordinator refresh.
    Registers a coordinator listener to detect new groups added later on the
    cloud side (picked up without restarting HA).
    """
    coordinator: NewlabCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        NewlabLight(coordinator, group)
        for group in coordinator.data.values()
    ]
    _LOGGER.debug(
        "[light] async_setup_entry: registering %d entity/ies: %s",
        len(entities),
        [e.name for e in entities],
    )
    async_add_entities(entities)

    # Track registered group IDs to detect new groups dynamically
    known_ids: set[int] = {g.id_group for g in coordinator.data.values()}

    def _handle_coordinator_update() -> None:
        """Register entities for any new groups discovered after startup."""
        new_entities = []
        for gid, group in coordinator.data.items():
            if gid not in known_ids:
                known_ids.add(gid)
                new_entities.append(NewlabLight(coordinator, group))
                _LOGGER.info(
                    "[light] new group discovered: id=%d name=%r strategy=%r",
                    gid, group.name, group.parser_strategy,
                )
        if new_entities:
            _LOGGER.info(
                "[light] adding %d new entity/ies dynamically: %s",
                len(new_entities),
                [e.name for e in new_entities],
            )
            async_add_entities(new_entities)

    coordinator.async_add_listener(_handle_coordinator_update)


class NewlabLight(CoordinatorEntity[NewlabCoordinator], LightEntity):
    """A single Newlab LED light group exposed as a HA LightEntity.

    unique_id  = "newlab_group_{id_group}" — stable across renames
    name       = label from HTML (or "Group {N}" if unavailable)
    brightness = PWM value 0–255 (1:1 mapping, no conversion needed)
    """

    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_should_poll = False  # coordinator drives all updates

    def __init__(
        self,
        coordinator: NewlabCoordinator,
        group: NewlabGroup,
    ) -> None:
        super().__init__(coordinator)
        self._id_group = group.id_group

        # unique_id is id_group only — stable even if the cloud name changes
        self._attr_unique_id = f"newlab_group_{group.id_group}"
        self._attr_name = group.name

        # DeviceInfo is defined as a @property below (dynamic serial_number)

        _LOGGER.debug(
            "[light] entity created: unique_id=%r  name=%r  id_group=%d  "
            "name_source=%r  parser_strategy=%r  initial_pwm=%d",
            self._attr_unique_id,
            self._attr_name,
            group.id_group,
            group.name_source,
            group.parser_strategy,
            group.pwm,
        )

    # ── Device info (shared via coordinator) ─────────────────────────────

    @property
    def device_info(self):
        """Delegate to coordinator.hub_device_info (single source of truth)."""
        return self.coordinator.hub_device_info

    # ── Internal helper ────────────────────────────────────────────────────

    @property
    def _current_group(self) -> NewlabGroup | None:
        """Return the latest group state from the coordinator cache."""
        return self.coordinator.data.get(self._id_group)

    # ── LightEntity properties ─────────────────────────────────────────────

    @property
    def is_on(self) -> bool | None:
        g = self._current_group
        return g.is_on if g is not None else None

    @property
    def brightness(self) -> int | None:
        g = self._current_group
        return g.brightness if g is not None else None

    @property
    def available(self) -> bool:
        """Mark unavailable if coordinator failed, group vanished, or device is offline."""
        g = self._current_group
        return super().available and g is not None and not g.is_offline

    # ── Control ────────────────────────────────────────────────────────────

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on at the requested brightness (default: 255)."""
        pwm: int = kwargs.get(ATTR_BRIGHTNESS, 255)
        pwm = max(1, min(255, int(pwm)))  # clamp; minimum 1 so it registers as "on"

        _LOGGER.debug(
            "[light] turn_on: name=%r  id_group=%d  pwm=%d  kwargs=%s",
            self.name, self._id_group, pwm, kwargs,
        )

        success = await self.coordinator.api.set_light(self._id_group, pwm)
        if success:
            # Optimistic update — patch coordinator cache immediately for snappy UI
            if g := self.coordinator.data.get(self._id_group):
                _LOGGER.debug(
                    "[light] turn_on optimistic: group=%d  pwm %d → %d",
                    self._id_group, g.pwm, pwm,
                )
                g.pwm = pwm
            self.async_write_ha_state()
        else:
            _LOGGER.warning(
                "[light] turn_on FAILED: name=%r  id_group=%d  pwm=%d",
                self.name, self._id_group, pwm,
            )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off (PWM = 0)."""
        _LOGGER.debug(
            "[light] turn_off: name=%r  id_group=%d",
            self.name, self._id_group,
        )

        success = await self.coordinator.api.set_light(self._id_group, 0)
        if success:
            if g := self.coordinator.data.get(self._id_group):
                _LOGGER.debug(
                    "[light] turn_off optimistic: group=%d  pwm %d → 0",
                    self._id_group, g.pwm,
                )
                g.pwm = 0
            self.async_write_ha_state()
        else:
            _LOGGER.warning(
                "[light] turn_off FAILED: name=%r  id_group=%d",
                self.name, self._id_group,
            )

    # ── Extra state attributes ─────────────────────────────────────────────

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose cloud info and discovery metadata in the entity state."""
        g = self._current_group
        attrs: dict[str, Any] = {"id_group": self._id_group}

        # ── Cloud / system info ────────────────────────────────────────────
        if self.coordinator.plant_code:
            attrs["codice_impianto"] = self.coordinator.plant_code
        if self.coordinator.cloud_last_sync:
            attrs["cloud_ultima_sincronizzazione"] = self.coordinator.cloud_last_sync
        attrs["ultima_sincronizzazione_ha"] = self.coordinator.last_sync_formatted
        attrs["polling_interval_s"] = int(
            self.coordinator.update_interval.total_seconds()
        )

        # ── Device status ──────────────────────────────────────────────────
        if g is not None and g.is_offline:
            attrs["stato_dispositivo"] = "offline"

        # ── Discovery debug metadata ───────────────────────────────────────
        if g is not None:
            attrs["name_source"] = g.name_source
            attrs["parser_strategy"] = g.parser_strategy

        return attrs
