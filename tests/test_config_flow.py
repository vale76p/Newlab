from __future__ import annotations

import asyncio
import importlib
from types import SimpleNamespace

config_flow = importlib.import_module("custom_components.newlab.config_flow")
api_module = importlib.import_module("custom_components.newlab.api")


class _FakeAPI:
    def __init__(self, username: str, password: str, session: object) -> None:
        self.username = username
        self.password = password
        self.session = session

    async def login(self) -> None:
        return None

    async def get_groups(self):
        group = api_module.NewlabGroup(id_group=1, name="Cucina", pwm=100)
        return {1: group}


def test_config_flow_user_success(monkeypatch) -> None:
    monkeypatch.setattr(config_flow, "NewlabAPI", _FakeAPI)
    monkeypatch.setattr(config_flow, "async_get_clientsession", lambda _hass: object())

    flow = config_flow.NewlabConfigFlow()
    flow.hass = SimpleNamespace()

    result = asyncio.run(
        flow.async_step_user(
            {
                "username": "  mario.rossi  ",
                "password": "secret",
                "poll_interval": 12,
            }
        )
    )

    assert result["type"] == "create_entry"
    assert result["title"] == "Newlab (mario.rossi)"
    assert result["data"]["username"] == "mario.rossi"
    assert result["data"]["password"] == "secret"
    assert result["data"]["poll_interval"] == 12


class _AuthFailAPI(_FakeAPI):
    async def login(self) -> None:
        raise api_module.NewlabAuthError("bad credentials")


def test_config_flow_user_invalid_auth(monkeypatch) -> None:
    monkeypatch.setattr(config_flow, "NewlabAPI", _AuthFailAPI)
    monkeypatch.setattr(config_flow, "async_get_clientsession", lambda _hass: object())

    flow = config_flow.NewlabConfigFlow()
    flow.hass = SimpleNamespace()

    result = asyncio.run(
        flow.async_step_user(
            {
                "username": "mario.rossi",
                "password": "wrong",
                "poll_interval": 10,
            }
        )
    )

    assert result["type"] == "form"
    assert result["step_id"] == "user"
    assert result["errors"]["base"] == "invalid_auth"


def test_options_flow_saves_new_interval() -> None:
    entry = config_flow.config_entries.ConfigEntry(
        data={"poll_interval": 10},
        options={},
        entry_id="entry-1",
    )
    flow = config_flow.NewlabOptionsFlow(entry)

    result = asyncio.run(flow.async_step_init({"poll_interval": 25}))

    assert result["type"] == "create_entry"
    assert result["data"] == {"poll_interval": 25}
