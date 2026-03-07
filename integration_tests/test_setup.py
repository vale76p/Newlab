"""Integration tests for the Newlab LED custom component.

These tests use pytest-homeassistant-custom-component (PHAC) to run against
a real Home Assistant core instance. The HTTP layer is always mocked so no
real cloud calls are made.

Run with:
    pytest integration_tests/ -v
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from custom_components.newlab.api import NewlabAuthError, NewlabConnectionError, NewlabGroup
from custom_components.newlab.const import CONF_POLL_INTERVAL, DOMAIN
from homeassistant.config_entries import ConfigEntryAuthFailed, ConfigEntryNotReady

# ---------------------------------------------------------------------------
# Helpers (import _make_api from conftest indirectly — conftest fixtures inject it)
# ---------------------------------------------------------------------------


def _patch_api(api_instance: MagicMock):
    """Return a context manager that patches NewlabAPI with api_instance."""
    return patch(
        "custom_components.newlab.__init__.NewlabAPI",
        return_value=api_instance,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_setup_entry_success(hass, mock_config_entry, mock_api):
    """Full setup succeeds: coordinator is stored and groups are discovered."""
    with _patch_api(mock_api):
        result = await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert result is True
    assert DOMAIN in hass.data
    assert mock_config_entry.entry_id in hass.data[DOMAIN]

    coordinator = hass.data[DOMAIN][mock_config_entry.entry_id]
    assert len(coordinator.data) == 2
    assert coordinator.data[2].name == "Cucina"
    assert coordinator.data[3].name == "Soggiorno"


@pytest.mark.asyncio
async def test_setup_entry_auth_failed(hass, mock_config_entry):
    """NewlabAuthError during login raises ConfigEntryAuthFailed."""
    bad_api = MagicMock()
    bad_api.login = AsyncMock(side_effect=NewlabAuthError("bad credentials"))

    with _patch_api(bad_api), pytest.raises(ConfigEntryAuthFailed):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)


@pytest.mark.asyncio
async def test_setup_entry_not_ready(hass, mock_config_entry):
    """NewlabConnectionError during login raises ConfigEntryNotReady."""
    bad_api = MagicMock()
    bad_api.login = AsyncMock(side_effect=NewlabConnectionError("no network"))

    with _patch_api(bad_api), pytest.raises(ConfigEntryNotReady):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)


@pytest.mark.asyncio
async def test_unload_entry_removes_coordinator(hass, mock_config_entry, mock_api):
    """After unload, coordinator is removed from hass.data."""
    with _patch_api(mock_api):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.entry_id in hass.data[DOMAIN]

    unloaded = await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert unloaded is True
    assert mock_config_entry.entry_id not in hass.data.get(DOMAIN, {})


@pytest.mark.asyncio
async def test_light_entities_created(hass, mock_config_entry, mock_api):
    """One light entity per discovered group is registered in hass."""
    with _patch_api(mock_api):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    light_states = hass.states.async_all("light")
    assert len(light_states) >= 2  # Cucina + Soggiorno


@pytest.mark.asyncio
async def test_options_update_triggers_reload(hass, mock_config_entry, mock_api):
    """Updating poll_interval via options flow triggers an entry reload."""
    with _patch_api(mock_api):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    original_coordinator = hass.data[DOMAIN][mock_config_entry.entry_id]

    # Simulate options update (changes poll_interval)
    with _patch_api(mock_api):
        hass.config_entries.async_update_entry(
            mock_config_entry,
            options={CONF_POLL_INTERVAL: 30},
        )
        await hass.async_block_till_done()

    # Entry should still be healthy after options update; reload may recreate coordinator.
    assert mock_config_entry.entry_id in hass.data.get(DOMAIN, {})
    new_coordinator = hass.data[DOMAIN][mock_config_entry.entry_id]
    assert hasattr(new_coordinator, "update_interval")
    assert int(new_coordinator.update_interval.total_seconds()) == 30
    assert isinstance(new_coordinator.data, dict)
    if new_coordinator.data:
        assert isinstance(next(iter(new_coordinator.data.values())), NewlabGroup)
    _ = original_coordinator
