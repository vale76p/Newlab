"""Number platform for the Newlab LED integration.

Each discovered Newlab group (zone) is exposed as a NumberEntity with:
  - raw PWM value 0–255 shown as a slider
  - setting PWM to 0 turns the light off; 1–255 turns it on at that level
  - optimistic local update on set, confirmed on next coordinator poll

This entity lives on the same device as the corresponding NewlabLight entity
(same identifiers) so they appear together in the HA device card.
"""

from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity, NumberMode
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
    """Set up Newlab PWM number entities from a config entry.

    Mirrors the same dynamic-discovery pattern used by light.py:
    registers a coordinator listener to detect groups added later on the
    cloud side without restarting HA.
    """
    coordinator: NewlabCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        NewlabPWMNumber(coordinator, group)
        for group in coordinator.data.values()
    ]
    _LOGGER.debug(
        "[number] async_setup_entry: registering %d entity/ies: %s",
        len(entities),
        [e.name for e in entities],
    )
    async_add_entities(entities)

    known_ids: set[int] = {g.id_group for g in coordinator.data.values()}

    def _handle_coordinator_update() -> None:
        """Register PWM entities for any new groups discovered after startup."""
        new_entities = []
        for gid, group in coordinator.data.items():
            if gid not in known_ids:
                known_ids.add(gid)
                new_entities.append(NewlabPWMNumber(coordinator, group))
                _LOGGER.info(
                    "[number] new group discovered: id=%d name=%r",
                    gid, group.name,
                )
        if new_entities:
            _LOGGER.info(
                "[number] adding %d new entity/ies dynamically: %s",
                len(new_entities),
                [e.name for e in new_entities],
            )
            async_add_entities(new_entities)

    coordinator.async_add_listener(_handle_coordinator_update)


class NewlabPWMNumber(CoordinatorEntity[NewlabCoordinator], NumberEntity):
    """Raw PWM slider (0–255) for a single Newlab LED group.

    unique_id  = "newlab_group_{id_group}_pwm" — stable across renames
    name       = "{group_name} PWM"
    native_value = current PWM (0 = off, 1–255 = on at that level)
    """

    _attr_native_min_value = 0.0
    _attr_native_max_value = 255.0
    _attr_native_step = 1.0
    _attr_mode = NumberMode.SLIDER
    _attr_icon = "mdi:brightness-6"
    _attr_should_poll = False  # coordinator drives all updates

    def __init__(
        self,
        coordinator: NewlabCoordinator,
        group: NewlabGroup,
    ) -> None:
        super().__init__(coordinator)
        self._id_group = group.id_group

        self._attr_unique_id = f"newlab_group_{group.id_group}_pwm"
        self._attr_name = f"{group.name} PWM"

        _LOGGER.debug(
            "[number] entity created: unique_id=%r  name=%r  id_group=%d  initial_pwm=%d",
            self._attr_unique_id,
            self._attr_name,
            group.id_group,
            group.pwm,
        )

    # ── Device info (shared via coordinator) ─────────────────────────────

    @property
    def device_info(self):
        """Delegate to coordinator.hub_device_info (single source of truth)."""
        return self.coordinator.hub_device_info

    # ── Internal helper ─────────────────────────────────────────────────────

    @property
    def _current_group(self) -> NewlabGroup | None:
        """Return the latest group state from the coordinator cache."""
        return self.coordinator.data.get(self._id_group)

    # ── NumberEntity properties ─────────────────────────────────────────────

    @property
    def native_value(self) -> float | None:
        """Current PWM value (0–255), or None if group is unavailable."""
        g = self._current_group
        return float(g.pwm) if g is not None else None

    @property
    def available(self) -> bool:
        """Mark unavailable if coordinator failed, group vanished, or device is offline."""
        g = self._current_group
        return super().available and g is not None and not g.is_offline

    # ── Control ─────────────────────────────────────────────────────────────

    async def async_set_native_value(self, value: float) -> None:
        """Send a new PWM value to the Newlab cloud.

        value=0   → light off
        value=1–255 → light on at that PWM level
        """
        pwm = max(0, min(255, int(value)))

        _LOGGER.debug(
            "[number] set_pwm: name=%r  id_group=%d  pwm=%d",
            self.name, self._id_group, pwm,
        )

        success = await self.coordinator.api.set_light(self._id_group, pwm)
        if success:
            # Optimistic update — patch coordinator cache immediately for snappy UI
            if g := self.coordinator.data.get(self._id_group):
                _LOGGER.debug(
                    "[number] set_pwm optimistic: group=%d  pwm %d → %d",
                    self._id_group, g.pwm, pwm,
                )
                g.pwm = pwm
            self.async_write_ha_state()
        else:
            _LOGGER.warning(
                "[number] set_pwm FAILED: name=%r  id_group=%d  pwm=%d",
                self.name, self._id_group, pwm,
            )
