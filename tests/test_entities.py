from __future__ import annotations

import asyncio
import importlib
from datetime import timedelta
from types import SimpleNamespace


api_module = importlib.import_module("custom_components.newlab.api")
button_module = importlib.import_module("custom_components.newlab.button")
light_module = importlib.import_module("custom_components.newlab.light")
number_module = importlib.import_module("custom_components.newlab.number")
sensor_module = importlib.import_module("custom_components.newlab.sensor")


class _FakeAPI:
    def __init__(self) -> None:
        self.calls: list[tuple[int, int]] = []
        self.refresh_ok = True

    async def set_light(self, id_group: int, pwm: int) -> bool:
        self.calls.append((id_group, pwm))
        return True

    async def async_refresh_plant(self) -> bool:
        return self.refresh_ok


def _coordinator_with_group() -> SimpleNamespace:
    group = api_module.NewlabGroup(id_group=1, name="Cucina", pwm=20)
    return SimpleNamespace(
        data={1: group},
        api=_FakeAPI(),
        plant_code="plant-1",
        cloud_version="3.47",
        cloud_last_sync="Feb 16, 2026",
        last_sync_formatted="Lunedì 16 Febbraio 2026 19:01",
        update_interval=timedelta(seconds=10),
        async_request_refresh=lambda: None,
        async_add_listener=lambda _listener: None,
    )


def test_light_turn_on_and_off_updates_state() -> None:
    coordinator = _coordinator_with_group()
    entity = light_module.NewlabLight(coordinator, coordinator.data[1])

    asyncio.run(entity.async_turn_on(brightness=123))
    assert coordinator.api.calls[-1] == (1, 123)
    assert coordinator.data[1].pwm == 123
    assert entity.is_on is True
    assert entity.brightness == 123

    asyncio.run(entity.async_turn_off())
    assert coordinator.api.calls[-1] == (1, 0)
    assert coordinator.data[1].pwm == 0
    assert entity.is_on is False


def test_light_available_and_extra_attrs() -> None:
    coordinator = _coordinator_with_group()
    entity = light_module.NewlabLight(coordinator, coordinator.data[1])
    attrs = entity.extra_state_attributes
    assert attrs["id_group"] == 1
    assert attrs["codice_impianto"] == "plant-1"
    assert attrs["polling_interval_s"] == 10

    coordinator.data[1].is_offline = True
    assert entity.available is False


def test_number_set_pwm_updates_state() -> None:
    coordinator = _coordinator_with_group()
    entity = number_module.NewlabPWMNumber(coordinator, coordinator.data[1])

    asyncio.run(entity.async_set_native_value(77))
    assert coordinator.api.calls[-1] == (1, 77)
    assert coordinator.data[1].pwm == 77
    assert entity.native_value == 77.0


def test_sensor_values() -> None:
    coordinator = _coordinator_with_group()
    plant = sensor_module.NewlabPlantCodeSensor(coordinator)
    ver = sensor_module.NewlabCloudVersionSensor(coordinator)
    sync = sensor_module.NewlabCloudSyncSensor(coordinator)

    assert plant.native_value == "plant-1"
    assert ver.native_value == "3.47"
    assert sync.native_value == "Feb 16, 2026"


def test_refresh_button_requests_refresh(monkeypatch) -> None:
    coordinator = _coordinator_with_group()
    called = {"refresh": 0}

    async def _request_refresh() -> None:
        called["refresh"] += 1

    async def _sleep(_seconds: int) -> None:
        return None

    coordinator.async_request_refresh = _request_refresh
    button = button_module.NewlabRefreshButton(coordinator)
    monkeypatch.setattr(button_module.asyncio, "sleep", _sleep)

    asyncio.run(button.async_press())
    assert called["refresh"] == 1


def test_platform_setup_entry_registers_entities() -> None:
    coordinator = _coordinator_with_group()
    hass = SimpleNamespace(data={"newlab": {"entry-1": coordinator}})
    entry = SimpleNamespace(entry_id="entry-1")
    added: list[object] = []

    def _add_entities(entities: list[object]) -> None:
        added.extend(entities)

    asyncio.run(light_module.async_setup_entry(hass, entry, _add_entities))
    asyncio.run(number_module.async_setup_entry(hass, entry, _add_entities))
    asyncio.run(sensor_module.async_setup_entry(hass, entry, _add_entities))
    asyncio.run(button_module.async_setup_entry(hass, entry, _add_entities))

    assert len(added) == 6
