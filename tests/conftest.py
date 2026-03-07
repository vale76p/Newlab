from __future__ import annotations

import sys
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any


def _install_custom_components_package() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    custom_components_dir = repo_root / "custom_components"
    newlab_dir = custom_components_dir / "newlab"

    custom_components_pkg = ModuleType("custom_components")
    custom_components_pkg.__path__ = [str(custom_components_dir)]
    sys.modules.setdefault("custom_components", custom_components_pkg)

    newlab_pkg = ModuleType("custom_components.newlab")
    newlab_pkg.__path__ = [str(newlab_dir)]
    sys.modules.setdefault("custom_components.newlab", newlab_pkg)


def _install_homeassistant_stubs() -> None:
    if "homeassistant" in sys.modules:
        return

    homeassistant = ModuleType("homeassistant")
    sys.modules["homeassistant"] = homeassistant

    config_entries = ModuleType("homeassistant.config_entries")
    sys.modules["homeassistant.config_entries"] = config_entries

    class ConfigEntry:
        def __init__(
            self,
            *,
            data: dict[str, Any] | None = None,
            options: dict[str, Any] | None = None,
            entry_id: str = "entry-1",
        ) -> None:
            self.data = data or {}
            self.options = options or {}
            self.entry_id = entry_id

    class ConfigFlow:
        def __init_subclass__(cls, **kwargs: Any) -> None:
            super().__init_subclass__()

        async def async_set_unique_id(self, unique_id: str) -> None:
            self._unique_id = unique_id

        def _abort_if_unique_id_configured(self) -> None:
            return None

        def async_show_form(self, *, step_id: str, data_schema: Any, errors: dict[str, str]) -> dict[str, Any]:
            return {
                "type": "form",
                "step_id": step_id,
                "data_schema": data_schema,
                "errors": errors,
            }

        def async_create_entry(self, *, title: str, data: dict[str, Any]) -> dict[str, Any]:
            return {"type": "create_entry", "title": title, "data": data}

    class OptionsFlow:
        def async_show_form(self, *, step_id: str, data_schema: Any) -> dict[str, Any]:
            return {"type": "form", "step_id": step_id, "data_schema": data_schema}

        def async_create_entry(self, *, title: str, data: dict[str, Any]) -> dict[str, Any]:
            return {"type": "create_entry", "title": title, "data": data}

    class ConfigEntryAuthFailed(Exception):
        pass

    class ConfigEntryNotReady(Exception):
        pass

    config_entries.ConfigEntry = ConfigEntry
    config_entries.ConfigFlow = ConfigFlow
    config_entries.OptionsFlow = OptionsFlow
    config_entries.FlowResult = dict
    config_entries.ConfigEntryAuthFailed = ConfigEntryAuthFailed
    config_entries.ConfigEntryNotReady = ConfigEntryNotReady
    homeassistant.config_entries = config_entries

    const = ModuleType("homeassistant.const")
    const.CONF_USERNAME = "username"
    const.CONF_PASSWORD = "password"
    const.ATTR_IDENTIFIERS = "identifiers"
    const.EntityCategory = SimpleNamespace(DIAGNOSTIC="diagnostic")

    class Platform(Enum):
        LIGHT = "light"
        NUMBER = "number"
        SENSOR = "sensor"
        BUTTON = "button"

    const.Platform = Platform
    sys.modules["homeassistant.const"] = const

    core = ModuleType("homeassistant.core")
    class HomeAssistant:
        pass
    core.HomeAssistant = HomeAssistant
    sys.modules["homeassistant.core"] = core

    helpers = ModuleType("homeassistant.helpers")
    sys.modules["homeassistant.helpers"] = helpers

    selector = ModuleType("homeassistant.helpers.selector")
    class NumberSelectorMode:
        SLIDER = "slider"
    class NumberSelectorConfig:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs
    class NumberSelector:
        def __init__(self, config: NumberSelectorConfig) -> None:
            self.config = config
    selector.NumberSelectorMode = NumberSelectorMode
    selector.NumberSelectorConfig = NumberSelectorConfig
    selector.NumberSelector = NumberSelector
    sys.modules["homeassistant.helpers.selector"] = selector

    entity = ModuleType("homeassistant.helpers.entity")
    class DeviceInfo(dict):
        pass
    entity.DeviceInfo = DeviceInfo
    sys.modules["homeassistant.helpers.entity"] = entity

    entity_platform = ModuleType("homeassistant.helpers.entity_platform")
    class AddEntitiesCallback:
        pass
    entity_platform.AddEntitiesCallback = AddEntitiesCallback
    sys.modules["homeassistant.helpers.entity_platform"] = entity_platform

    aiohttp_client = ModuleType("homeassistant.helpers.aiohttp_client")
    def async_get_clientsession(_hass: Any) -> object:
        return object()
    aiohttp_client.async_get_clientsession = async_get_clientsession
    sys.modules["homeassistant.helpers.aiohttp_client"] = aiohttp_client

    update_coordinator = ModuleType("homeassistant.helpers.update_coordinator")

    class UpdateFailed(Exception):
        pass

    class DataUpdateCoordinator:
        @classmethod
        def __class_getitem__(cls, _item: Any) -> Any:
            return cls

        def __init__(self, hass: Any, logger: Any, *, name: str, update_interval: Any) -> None:
            self.hass = hass
            self.logger = logger
            self.name = name
            self.update_interval = update_interval
            self.data = {}
            self._listeners: list[Any] = []

        async def async_request_refresh(self) -> None:
            self.data = await self._async_update_data()
            for listener in list(self._listeners):
                listener()

        def async_add_listener(self, listener: Any) -> Any:
            self._listeners.append(listener)

            def _unsub() -> None:
                if listener in self._listeners:
                    self._listeners.remove(listener)

            return _unsub

    update_coordinator.UpdateFailed = UpdateFailed
    update_coordinator.DataUpdateCoordinator = DataUpdateCoordinator
    sys.modules["homeassistant.helpers.update_coordinator"] = update_coordinator

    util = ModuleType("homeassistant.util")
    dt = ModuleType("homeassistant.util.dt")
    def now() -> datetime:
        return datetime.now(timezone.utc)
    dt.now = now
    util.dt = dt
    sys.modules["homeassistant.util"] = util
    sys.modules["homeassistant.util.dt"] = dt

    light = ModuleType("homeassistant.components.light")
    light.ATTR_BRIGHTNESS = "brightness"

    class ColorMode:
        BRIGHTNESS = "brightness"

    class LightEntity:
        def __init__(self) -> None:
            self._attr_name = None

        @property
        def name(self) -> str | None:
            return getattr(self, "_attr_name", None)

        def async_write_ha_state(self) -> None:
            return None

    light.ColorMode = ColorMode
    light.LightEntity = LightEntity
    sys.modules["homeassistant.components.light"] = light

    number = ModuleType("homeassistant.components.number")
    class NumberMode:
        SLIDER = "slider"

    class NumberEntity:
        def __init__(self) -> None:
            self._attr_name = None

        @property
        def name(self) -> str | None:
            return getattr(self, "_attr_name", None)

        def async_write_ha_state(self) -> None:
            return None

    number.NumberMode = NumberMode
    number.NumberEntity = NumberEntity
    sys.modules["homeassistant.components.number"] = number

    sensor = ModuleType("homeassistant.components.sensor")
    class SensorEntity:
        pass
    sensor.SensorEntity = SensorEntity
    sys.modules["homeassistant.components.sensor"] = sensor

    button = ModuleType("homeassistant.components.button")
    class ButtonEntity:
        pass
    button.ButtonEntity = ButtonEntity
    sys.modules["homeassistant.components.button"] = button

    class CoordinatorEntity:
        @classmethod
        def __class_getitem__(cls, _item: Any) -> Any:
            return cls

        def __init__(self, coordinator: Any) -> None:
            self.coordinator = coordinator

        @property
        def available(self) -> bool:
            return True

        def async_write_ha_state(self) -> None:
            return None

    update_coordinator.CoordinatorEntity = CoordinatorEntity


_install_custom_components_package()
_install_homeassistant_stubs()


def _install_voluptuous_stub() -> None:
    if "voluptuous" in sys.modules:
        return

    voluptuous = ModuleType("voluptuous")

    class _Marker:
        def __init__(self, key: str, default: Any = None) -> None:
            self.key = key
            self.default = default

        def __hash__(self) -> int:
            return hash((self.key, self.default))

        def __eq__(self, other: Any) -> bool:
            return isinstance(other, _Marker) and (self.key, self.default) == (
                other.key,
                other.default,
            )

    def Required(key: str, default: Any = None) -> _Marker:
        return _Marker(key, default)

    def Optional(key: str, default: Any = None) -> _Marker:
        return _Marker(key, default)

    class Schema:
        def __init__(self, schema: Any) -> None:
            self.schema = schema

        def __call__(self, value: Any) -> Any:
            return value

    voluptuous.Required = Required
    voluptuous.Optional = Optional
    voluptuous.Schema = Schema
    sys.modules["voluptuous"] = voluptuous


_install_voluptuous_stub()
