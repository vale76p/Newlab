"""Config flow for the Newlab LED integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import NewlabAPI, NewlabAuthError, NewlabConnectionError, NewlabParseError
from .const import (
    CONF_POLL_INTERVAL,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    MAX_POLL_INTERVAL,
    MIN_POLL_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_POLL_INTERVAL, default=DEFAULT_POLL_INTERVAL): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=MIN_POLL_INTERVAL,
                max=MAX_POLL_INTERVAL,
                step=1,
                unit_of_measurement="s",
                mode=selector.NumberSelectorMode.SLIDER,
            )
        ),
    }
)


class NewlabConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the UI config flow for Newlab LED."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Initial step: collect username, password, and poll interval."""
        errors: dict[str, str] = {}

        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            poll_interval = int(user_input.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL))

            _LOGGER.debug(
                "[config_flow] user submitted: username=%r  poll_interval=%d",
                username, poll_interval,
            )

            # Prevent duplicate entries for the same account
            await self.async_set_unique_id(username.lower())
            self._abort_if_unique_id_configured()

            session = async_get_clientsession(self.hass)
            api = NewlabAPI(username, user_input[CONF_PASSWORD], session)

            # Validate by performing a real login + discovery pass
            try:
                _LOGGER.debug("[config_flow] attempting login for user=%r", username)
                await api.login()

                _LOGGER.debug("[config_flow] login OK, running discovery pass…")
                groups = await api.get_groups()

                _LOGGER.info(
                    "[config_flow] validation SUCCESS — user=%r  groups_found=%d  names=%s",
                    username,
                    len(groups),
                    {gid: g.name for gid, g in sorted(groups.items())},
                )

            except NewlabAuthError as exc:
                _LOGGER.warning("[config_flow] auth error for user=%r: %s", username, exc)
                errors["base"] = "invalid_auth"
            except NewlabConnectionError as exc:
                _LOGGER.warning("[config_flow] connection error: %s", exc)
                errors["base"] = "cannot_connect"
            except NewlabParseError as exc:
                _LOGGER.warning("[config_flow] parse error: %s", exc)
                errors["base"] = "cannot_parse"
            except Exception:
                _LOGGER.exception("[config_flow] unexpected error for user=%r", username)
                errors["base"] = "unknown"

            if not errors:
                _LOGGER.debug(
                    "[config_flow] creating entry for user=%r  poll_interval=%d",
                    username, poll_interval,
                )
                return self.async_create_entry(
                    title=f"Newlab ({username})",
                    data={
                        CONF_USERNAME: username,
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_POLL_INTERVAL: poll_interval,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "NewlabOptionsFlow":
        return NewlabOptionsFlow(config_entry)


class NewlabOptionsFlow(config_entries.OptionsFlow):
    """Options flow — change poll interval without removing the integration."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        current_interval = self._config_entry.data.get(
            CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL
        )

        if user_input is not None:
            new_interval = int(user_input[CONF_POLL_INTERVAL])
            _LOGGER.debug(
                "[options_flow] poll_interval changed: %d → %d",
                current_interval, new_interval,
            )
            return self.async_create_entry(
                title="",
                data={CONF_POLL_INTERVAL: new_interval},
            )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_POLL_INTERVAL,
                        default=current_interval,
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=MIN_POLL_INTERVAL,
                            max=MAX_POLL_INTERVAL,
                            step=1,
                            unit_of_measurement="s",
                            mode=selector.NumberSelectorMode.SLIDER,
                        )
                    ),
                }
            ),
        )
