# Changelog

All notable changes to the Newlab LED integration are documented here.

---

## [Unreleased]

No changes yet.

---

## [1.1.1] — 2026-03-06

### Fixed

- Minor bug fixing and documentation/test consistency updates.

---

## [1.1.0] — 2026-03-06

### Changed

- **API layer refactor to modular architecture**
  - `api.py` is now a compatibility facade.
  - HTTP/session logic moved to `client.py`.
  - HTML parsing moved to `parsers.py`.
  - dataclasses/exceptions moved to `models.py`.
  - Goal: improve maintainability and testability without changing external behavior.

### Added

- **Automated quality baseline**
  - Added `pyproject.toml` with lint/test configuration.
  - Added `ruff` linting and `pytest` execution in CI.
  - Added coverage reports in CI (`coverage.xml`, `htmlcov` artifacts).

- **Comprehensive unit tests**
  - Parsing tests (`test_api_parsing.py`)
  - Client tests (`test_client.py`)
  - Config flow tests (`test_config_flow.py`)
  - Coordinator tests (`test_coordinator.py`)
  - Entity tests (`test_entities.py`)
  - Setup/unload tests (`test_init_module.py`)

### Quality

- Coverage increased from initial ~35% baseline to **84%** total.

---

## [1.0.2] — 2026-03-06

### Fixed

- **Diagnostic sensors "Codice Impianto" and "Ultima Sincronizzazione Cloud"
  always showing "Sconosciuto"** — The Newlab cloud is a Django app with i18n.
  Our `Accept-Language: en` header caused the server to respond in English, but
  the regexes were hard-coded for the Italian labels (`Codice Impianto`,
  `Ultima sincronizzazione`). The actual HTML uses:
  - `<p>Plant Id: <b>…</b></p>` (not "Codice Impianto")
  - `<p>Last syncronization: <b>Feb. 16, 2026, 7:01 p.m.</b></p>`
    (not "Ultima sincronizzazione"; NB: "syncronization" is a typo in the
    Newlab cloud source, missing the 'h')

  **Fix:** All metadata regexes now match both EN and IT labels:
  ```python
  r'(?:Plant\s+Id|Codice\s+Impianto)\b.{0,60}?<(?:b|strong)…>'
  r'(?:Last\s+sync(?:h?ronization)|Ultima\s+sincronizzazione)\b.{0,60}?…'
  ```
  `.{0,60}?` with `re.DOTALL` tolerates any separator between label and `<b>` tag
  (spaces, `&nbsp;`, `<br/>`). Both `<b>` and `<strong>` are accepted.

### Added

- **HACS brand assets** — `custom_components/newlab/brand/icon.png` (256×256)
  and `logo.png` (640×256), compatible with HA 2026.3+ local brand proxy.

### Changed

- Removed Pattern 5 (URL segment fallback) from plant code regexes — unreliable
  and unnecessary now that the correct label is matched.
- `DEBUG_HTML_MAX_CHARS` remains at 4000 (temporarily increased to 25000 during
  debugging, reverted).

---

## [1.0.1] — 2026-03-05

### Fixed

- **Diagnostic sensors showing "unavailable"** — `NewlabPlantCodeSensor`,
  `NewlabCloudVersionSensor`, and `NewlabCloudSyncSensor` had a custom `available`
  property that returned `False` whenever the parsed value was an empty string
  (e.g. regex not matching or first poll not yet complete). Removed the custom
  `available` check; sensors now follow the coordinator's availability and show
  `unknown` instead of `unavailable` when the value cannot be extracted from the
  cloud HTML.

---

## [1.0.0] — 2026-03-05

First stable release as a proper HACS custom integration, replacing the previous
`pyscript` + `rest:` + `template switch` approach.

### Platforms

- **`light`** — On/Off + brightness (PWM 0–255) per zone, `ColorMode.BRIGHTNESS`
- **`number`** — Raw PWM slider (0–255) per zone for precise control
- **`sensor`** — Three hub-level diagnostic sensors (plant code, cloud version, last sync)
- **`button`** — Plant refresh button (force cloud sync of the physical controller)

### Entities

| Entity | Description |
|--------|-------------|
| `light.<zone>` | One per discovered zone — on/off + brightness |
| `number.<zone>_pwm` | Raw PWM 0–255 slider per zone |
| `sensor.codice_impianto` | Plant/installation serial code |
| `sensor.versione_cloud` | Cloud firmware version (e.g. `3.47`) |
| `sensor.ultima_sincronizzazione_cloud` | Last sync timestamp from Newlab cloud |
| `button.aggiorna_impianto` | Force plant refresh via POST to cloud |

### Device Card

All entities are grouped under a single **Newlab LED Controller** device.
Firmware version appears in the device info header. Plant code is shown as serial number.
Diagnostic entities are in the **Diagnostics** section of the device card.

### Core Features

- Dynamic zone discovery from cloud HTML — no hardcoded zone list
- Single HTTP poll per interval shared by all entities (`DataUpdateCoordinator`)
- Configurable poll interval 5–60 s (slider in setup + options flow)
- Automatic session re-authentication on cookie expiry
- Offline detection: zones with `class="offline"` in the cloud HTML are marked unavailable
- Optimistic state updates on control commands for instant UI feedback
- Plant refresh: POST `/smarthome/plantrefresh` + 5 s wait + coordinator refresh

### Diagnostic Data (extracted from cloud HTML)

- **Plant Id / Codice Impianto** — `<p>Plant Id: <b>…</b></p>` (EN) / `<p>Codice Impianto: <b>…</b></p>` (IT)
- **Cloud Version** — `Ver. X.XX` in `<title>` tag
- **Last syncronization / Ultima sincronizzazione** — `<p>Last syncronization: <b>…</b></p>` (EN)

### Security

- Credentials stored in HA encrypted config entry storage only
- Session cookies held in RAM, never written to disk or exposed as HA helpers
- No hardcoded passwords, no `input_text` cookie helpers required

### Migration from Previous Setup

| Before | After |
|--------|-------|
| `pyscript/newlab_login.py` (hourly login) | `api.py` with on-demand re-auth |
| `rest:` sensors (scraping every 5 s each) | `NewlabCoordinator` (one poll, configurable) |
| `template switch` | `LightEntity` with brightness support |
| `rest_command: newlab_set_light` | `api.set_light()` internal |
| `input_text.newlab_cookie` | Cookie in RAM only |
