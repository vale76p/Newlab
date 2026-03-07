"""Newlab LED — Home Assistant custom integration.

Architecture
------------
  config_flow  → stores username / password / poll_interval
  __init__     → creates NewlabAPI + NewlabCoordinator per config entry
  coordinator  → polls /registrationhome every N seconds
  light        → one NewlabLight entity per discovered group (on/off + brightness)
  number       → one NewlabPWMNumber entity per group (raw PWM 0–255 slider)
  sensor       → hub-level diagnostic sensors (plant code, version, cloud sync)
  button       → hub-level refresh button (POST /smarthome/plantrefresh)

Re-authentication is handled transparently by the coordinator.

Debug
-----
Enable verbose logging in HA configuration.yaml:
  logger:
    logs:
      custom_components.newlab: debug
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry, ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import NewlabAPI, NewlabAuthError, NewlabConnectionError
from .const import CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL, DOMAIN
from .coordinator import NewlabCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.LIGHT, Platform.NUMBER, Platform.SENSOR, Platform.BUTTON]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Newlab LED from a config entry.

    Steps:
      1. Create NewlabAPI and authenticate.
      2. Create NewlabCoordinator and run first refresh (discovers groups).
      3. Forward entry setup to the light platform.
    """
    username = entry.data[CONF_USERNAME]
    poll_interval = entry.data.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
    # Options flow can override poll interval without full reconfiguration
    poll_interval = entry.options.get(CONF_POLL_INTERVAL, poll_interval)

    _LOGGER.debug(
        "[setup] entry_id=%s  user=%r  poll_interval=%ds",
        entry.entry_id, username, poll_interval,
    )

    session = async_get_clientsession(hass)
    api = NewlabAPI(username, entry.data[CONF_PASSWORD], session)

    try:
        await api.login()
    except NewlabAuthError as exc:
        _LOGGER.error(
            "[setup] authentication failed for user=%r: %s — check credentials",
            username, exc,
        )
        raise ConfigEntryAuthFailed(str(exc)) from exc
    except NewlabConnectionError as exc:
        _LOGGER.error(
            "[setup] cannot reach Newlab cloud: %s — check internet connection",
            exc,
        )
        raise ConfigEntryNotReady(str(exc)) from exc

    coordinator = NewlabCoordinator(hass, api, poll_interval)

    # First refresh — discovers all light groups and populates coordinator.data
    _LOGGER.debug("[setup] running first coordinator refresh (entity discovery)…")
    await coordinator.async_config_entry_first_refresh()

    _LOGGER.info(
        "[setup] discovery complete — %d group(s): %s",
        len(coordinator.data),
        {gid: g.name for gid, g in sorted(coordinator.data.items())},
    )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Reload entry if options are changed (e.g. new poll interval)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry and release resources."""
    _LOGGER.debug("[setup] unloading entry_id=%s", entry.entry_id)
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        _LOGGER.debug("[setup] entry_id=%s unloaded OK", entry.entry_id)
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options change (e.g. poll interval update)."""
    _LOGGER.debug("[setup] options changed, reloading entry_id=%s", entry.entry_id)
    await hass.config_entries.async_reload(entry.entry_id)
