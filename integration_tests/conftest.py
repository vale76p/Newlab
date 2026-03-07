"""Fixtures for integration tests (pytest-homeassistant-custom-component)."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

# Make custom_components importable without installing the package.
# tests/conftest.py is NOT loaded here because this directory is outside tests/.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from custom_components.newlab.api import NewlabGroup
from custom_components.newlab.const import CONF_POLL_INTERVAL, DOMAIN

# ---------------------------------------------------------------------------
# Shared mock data
# ---------------------------------------------------------------------------

MOCK_GROUPS: dict[int, NewlabGroup] = {
    2: NewlabGroup(id_group=2, name="Cucina", pwm=200),
    3: NewlabGroup(id_group=3, name="Soggiorno", pwm=0),
}


def _make_api(login_raises: Exception | None = None) -> MagicMock:
    """Return a mock NewlabAPI instance."""
    api = MagicMock()
    if login_raises is not None:
        api.login = AsyncMock(side_effect=login_raises)
    else:
        api.login = AsyncMock(return_value=None)
    api.get_groups = AsyncMock(return_value=MOCK_GROUPS)
    api.system_info = SimpleNamespace(
        plant_code="plant_001",
        version="3.47",
        last_sync="Feb. 16, 2026, 7:01 p.m.",
    )
    api.async_refresh_plant = AsyncMock(return_value=True)
    api.is_authenticated = True
    return api


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_api() -> MagicMock:
    """Mock API that succeeds for login + get_groups."""
    return _make_api()


@pytest.fixture
def entry_data() -> dict:
    """Minimal config entry data."""
    return {
        "username": "testuser",
        "password": "testpass",
        CONF_POLL_INTERVAL: 10,
    }


@pytest.fixture
def mock_config_entry(hass, entry_data):
    """Add a MockConfigEntry for the Newlab domain to hass."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(
        domain=DOMAIN,
        data=entry_data,
        unique_id="testuser",
    )
    entry.add_to_hass(hass)
    return entry
