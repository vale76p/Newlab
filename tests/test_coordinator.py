"""Unit tests for the NewlabCoordinator."""

from __future__ import annotations

import asyncio
import importlib
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

coordinator_module = importlib.import_module("custom_components.newlab.coordinator")
api_module = importlib.import_module("custom_components.newlab.api")
update_module = importlib.import_module("homeassistant.helpers.update_coordinator")


class _APIAlwaysOK:
    def __init__(self) -> None:
        self.system_info = api_module.NewlabSystemInfo(
            plant_code="impianto-xyz",
            cloud_last_sync="Feb. 16, 2026, 7:01 p.m.",
            cloud_version="3.47",
        )

    async def get_groups(self):
        return {1: api_module.NewlabGroup(id_group=1, name="Cucina", pwm=90)}

    async def login(self) -> None:
        return None


class _APIRetryAuth:
    def __init__(self) -> None:
        self.calls = 0
        self.login_calls = 0
        self.system_info = api_module.NewlabSystemInfo(
            plant_code="impianto-abc",
            cloud_last_sync="Lunedì 16 Febbraio 2026 19:01",
            cloud_version="3.48",
        )

    async def get_groups(self):
        self.calls += 1
        if self.calls == 1:
            raise api_module.NewlabAuthError("expired")
        return {2: api_module.NewlabGroup(id_group=2, name="Soggiorno", pwm=120)}

    async def login(self) -> None:
        self.login_calls += 1


class _APIAuthFailsTwice:
    def __init__(self) -> None:
        self.login_calls = 0
        self.system_info = api_module.NewlabSystemInfo()

    async def get_groups(self):
        raise api_module.NewlabAuthError("expired")

    async def login(self) -> None:
        self.login_calls += 1
        raise api_module.NewlabAuthError("still expired")


def test_coordinator_update_success(monkeypatch) -> None:
    fixed_now = datetime(2026, 3, 6, 10, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(coordinator_module.dt_util, "now", lambda: fixed_now)

    coordinator = coordinator_module.NewlabCoordinator(
        hass=SimpleNamespace(),
        api=_APIAlwaysOK(),
        poll_interval=10,
    )

    data = asyncio.run(coordinator._async_update_data())

    assert 1 in data
    assert coordinator.last_sync_time == fixed_now
    assert coordinator.plant_code == "impianto-xyz"
    assert coordinator.cloud_version == "3.47"
    assert coordinator.cloud_last_sync == "Feb. 16, 2026, 7:01 p.m."


def test_coordinator_reauth_then_success(monkeypatch) -> None:
    fixed_now = datetime(2026, 3, 6, 10, 30, tzinfo=timezone.utc)
    monkeypatch.setattr(coordinator_module.dt_util, "now", lambda: fixed_now)
    api = _APIRetryAuth()

    coordinator = coordinator_module.NewlabCoordinator(
        hass=SimpleNamespace(),
        api=api,
        poll_interval=10,
    )

    data = asyncio.run(coordinator._async_update_data())

    assert api.login_calls == 1
    assert set(data) == {2}
    assert coordinator.last_sync_time == fixed_now
    assert coordinator.plant_code == "impianto-abc"


def test_coordinator_reauth_failure_raises_update_failed() -> None:
    api = _APIAuthFailsTwice()
    coordinator = coordinator_module.NewlabCoordinator(
        hass=SimpleNamespace(),
        api=api,
        poll_interval=10,
    )

    with pytest.raises(update_module.UpdateFailed, match="Re-authentication failed"):
        asyncio.run(coordinator._async_update_data())
