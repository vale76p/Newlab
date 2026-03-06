# Newlab LED Integration — Architecture

## Overview

```
Home Assistant
  ├─ config_flow.py
  │   └─ validate credentials + first discovery
  ├─ __init__.py
  │   ├─ build NewlabAPI facade
  │   ├─ build NewlabCoordinator
  │   └─ setup platforms: light, number, sensor, button
  ├─ coordinator.py (DataUpdateCoordinator)
  │   ├─ poll /registrationhome every N seconds
  │   └─ retry with re-auth on session expiry
  └─ entities
      ├─ light.py (per-zone LightEntity)
      ├─ number.py (per-zone PWM NumberEntity)
      ├─ sensor.py (hub diagnostics)
      └─ button.py (hub refresh command)

API Layer (modular)
  ├─ api.py        (public facade / compatibility exports)
  ├─ client.py     (HTTP login/poll/control/refresh)
  ├─ parsers.py    (HTML parsing for groups + system info)
  └─ models.py     (dataclasses + domain exceptions)
```

## Current File Structure

```
custom_components/newlab/
├── __init__.py
├── manifest.json
├── const.py
├── api.py
├── client.py
├── parsers.py
├── models.py
├── coordinator.py
├── config_flow.py
├── light.py
├── number.py
├── sensor.py
├── button.py
├── strings.json
├── brand/
└── translations/
```

## Module Responsibilities

### `api.py`
- Backward-compatible entrypoint for imports in the integration.
- Re-exports `NewlabAPI`, dataclasses, exceptions, and parser helpers.

### `client.py`
- Implements `NewlabAPI`.
- Handles:
1. login flow (`GET /registrationwelcome`, `POST /registrationlogin`)
2. polling (`GET /registrationhome`)
3. control (`POST /smarthome/newplantsendcommand`)
4. plant refresh (`POST /smarthome/plantrefresh`)

### `parsers.py`
- Pure parsing logic from HTML string input.
- `_parse_groups(html)` -> `dict[int, NewlabGroup]`
- `_parse_system_info(html)` -> `NewlabSystemInfo`

### `models.py`
- Data models:
1. `NewlabGroup`
2. `NewlabSystemInfo`
- Domain errors:
1. `NewlabAuthError`
2. `NewlabConnectionError`
3. `NewlabParseError`

## Runtime Data Flow

### Setup

1. `async_setup_entry` creates `NewlabAPI`.
2. `api.login()` authenticates and caches session cookies in memory.
3. `NewlabCoordinator` is created with poll interval.
4. first refresh runs discovery (`api.get_groups()`).
5. platforms are forwarded and entities are created.

### Polling

1. coordinator calls `api.get_groups()`.
2. `client.py` fetches `/registrationhome`.
3. `parsers.py` extracts groups + metadata.
4. coordinator updates `coordinator.data` and hub fields.
5. entities update state from coordinator cache.

### Session Recovery

1. if `get_groups()` raises `NewlabAuthError`, coordinator re-logins once.
2. retry poll once.
3. on failure, raises `UpdateFailed` and HA marks entities unavailable.

## Entity Model

### Per-zone entities
- `light.NewlabLight`
- `number.NewlabPWMNumber`

Both share:
1. stable ID by `id_group`
2. same hub `DeviceInfo`
3. availability tied to coordinator + offline flag
4. optimistic state update after successful command

### Hub entities
- `sensor.NewlabPlantCodeSensor`
- `sensor.NewlabCloudVersionSensor`
- `sensor.NewlabCloudSyncSensor`
- `button.NewlabRefreshButton`

## Testing and Quality

Repository quality stack:
1. `ruff` for linting
2. `pytest` for unit tests
3. `pytest-cov` for coverage

Current CI workflow (`.github/workflows/validate.yml`) runs:
1. lint
2. tests
3. coverage report generation (`coverage.xml`, `htmlcov/`)
4. artifact upload

Current measured total coverage: **84%**.
