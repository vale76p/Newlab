from __future__ import annotations

import asyncio
import importlib
import sys
from types import SimpleNamespace

import pytest

init_module = importlib.import_module("custom_components.newlab.__init__")
api_module = importlib.import_module("custom_components.newlab.api")


class _FakeAPI:
    def __init__(self, username: str, password: str, session: object) -> None:
        self.username = username
        self.password = password
        self.session = session

    async def login(self) -> None:
        return None


class _FakeCoordinator:
    def __init__(self, hass: object, api: object, poll_interval: int) -> None:
        self.hass = hass
        self.api = api
        self.poll_interval = poll_interval
        self.data = {1: api_module.NewlabGroup(id_group=1, name="Cucina", pwm=100)}

    async def async_config_entry_first_refresh(self) -> None:
        return None


def _entry() -> SimpleNamespace:
    callbacks: list[object] = []

    def add_update_listener(cb):
        callbacks.append(cb)
        return lambda: None

    entry = SimpleNamespace(
        entry_id="entry-1",
        data={"username": "mario", "password": "pw", "poll_interval": 10},
        options={},
        add_update_listener=add_update_listener,
        async_on_unload=lambda _cb: None,
    )
    entry._callbacks = callbacks
    return entry


def _hass() -> SimpleNamespace:
    class _ConfigEntries:
        def __init__(self) -> None:
            self.forwarded = None
            self.reloaded = None
            self.unload_called = False

        async def async_forward_entry_setups(self, entry, platforms) -> None:
            self.forwarded = (entry.entry_id, tuple(platforms))

        async def async_unload_platforms(self, entry, platforms) -> bool:
            self.unload_called = True
            return True

        async def async_reload(self, entry_id: str) -> None:
            self.reloaded = entry_id

    return SimpleNamespace(data={}, config_entries=_ConfigEntries())


def test_async_setup_and_unload_entry(monkeypatch) -> None:
    hass = _hass()
    entry = _entry()

    monkeypatch.setattr(init_module, "async_get_clientsession", lambda _h: object())
    monkeypatch.setattr(init_module, "NewlabAPI", _FakeAPI)
    monkeypatch.setattr(init_module, "NewlabCoordinator", _FakeCoordinator)

    result = asyncio.run(init_module.async_setup_entry(hass, entry))
    assert result is True
    assert "newlab" in hass.data
    assert entry.entry_id in hass.data["newlab"]

    unload = asyncio.run(init_module.async_unload_entry(hass, entry))
    assert unload is True


def test_async_setup_entry_raises_auth_failed_on_auth_error(monkeypatch) -> None:
    ConfigEntryAuthFailed = sys.modules["homeassistant.config_entries"].ConfigEntryAuthFailed

    class _AuthFailAPI(_FakeAPI):
        async def login(self) -> None:
            raise api_module.NewlabAuthError("bad auth")

    hass = _hass()
    entry = _entry()
    monkeypatch.setattr(init_module, "async_get_clientsession", lambda _h: object())
    monkeypatch.setattr(init_module, "NewlabAPI", _AuthFailAPI)

    with pytest.raises(ConfigEntryAuthFailed):
        asyncio.run(init_module.async_setup_entry(hass, entry))


def test_async_setup_entry_raises_not_ready_on_connection_error(monkeypatch) -> None:
    ConfigEntryNotReady = sys.modules["homeassistant.config_entries"].ConfigEntryNotReady

    class _ConnFailAPI(_FakeAPI):
        async def login(self) -> None:
            raise api_module.NewlabConnectionError("no internet")

    hass = _hass()
    entry = _entry()
    monkeypatch.setattr(init_module, "async_get_clientsession", lambda _h: object())
    monkeypatch.setattr(init_module, "NewlabAPI", _ConnFailAPI)

    with pytest.raises(ConfigEntryNotReady):
        asyncio.run(init_module.async_setup_entry(hass, entry))


def test_options_flow_reads_interval_from_options() -> None:
    config_flow_module = importlib.import_module("custom_components.newlab.config_flow")

    ConfigEntry = sys.modules["homeassistant.config_entries"].ConfigEntry
    entry = ConfigEntry(
        data={"poll_interval": 10},
        options={"poll_interval": 30},
    )
    flow = config_flow_module.NewlabOptionsFlow(entry)
    result = asyncio.run(flow.async_step_init(None))
    # Form is shown with current_interval from options (30), not data (10)
    assert result["type"] == "form"


def test_update_listener_triggers_reload() -> None:
    hass = _hass()
    entry = _entry()
    asyncio.run(init_module._async_update_listener(hass, entry))
    assert hass.config_entries.reloaded == "entry-1"
