# Changelog

All notable changes to the Newlab LED integration are documented here.

---

## [Unreleased]

No changes yet.

---

## [1.2.0] — 2026-03-06

### Fixed

- **`NewlabParseError` missing from `client.py` imports** — login flow would crash with
  `NameError` if the welcome page HTML lacked the CSRF token. Re-added the import from `models`.
- **Silent error swallowing in `set_light()` / `async_refresh_plant()`** — restored
  `_LOGGER.warning` on non-200 responses and `_LOGGER.error` on connection exceptions;
  added `_LOGGER.error` when called without authentication.
- **Reduced observability in `parsers.py`** — restored per-strategy DEBUG logging, added
  ERROR log before raising `NewlabParseError`, and WARNING logs when system-info fields
  are not found.
- **URL comparison in `get_groups()`** — fixed login-redirect detection to use
  case-insensitive comparison (`HOME_URL.lower()`).
- **Import ordering** — fixed `ruff I001` violations across coordinator, config_flow, and
  test modules.
- **Quoted type annotation** — removed unnecessary string quotes from
  `config_flow.py:async_get_options_flow` return type (`UP037`).

### Changed

- **Shared `DeviceInfo` via coordinator** — `coordinator.hub_device_info` property replaces
  identical `DeviceInfo(…)` blocks duplicated in `light.py`, `number.py`, `sensor.py`, and
  `button.py`. Entities now delegate to `self.coordinator.hub_device_info`.
- **Public parser API** — renamed `_parse_groups` → `parse_groups` and
  `_parse_system_info` → `parse_system_info` in `parsers.py`; updated `api.py` facade
  exports and all internal callers.
- **`strings.json` in English** — HA convention requires `strings.json` in English;
  Italian translations remain in `translations/it.json`.
- **Ruff lint rules expanded** — added `I` (isort), `B` (bugbear), `UP` (pyupgrade),
  `SIM` (simplify). Suppressed `UP017` (`datetime.UTC`) for Python 3.9 test compatibility.
- **Dead constants removed** — `CONF_USERNAME`, `CONF_PASSWORD`, `DATA_COORDINATOR`,
  `DATA_API` removed from `const.py` (unused after Codex refactor).

### Added

- **6 new parser tests** — Strategy C (`data-group`), Strategy D (broad fallback),
  L4 (`td_text`), parse-error (`pytest.raises`), partial system info, empty HTML.
  Total parsing tests: 12 (was 6).
- **`pytest.raises` idiom** — replaced `try/except/raise AssertionError` anti-pattern
  in `test_client.py` and `test_coordinator.py`.

### Quality

- Ruff lint: **0 errors** (was 9).
- Test suite: **31 tests**, all passing.
- Coverage: **87%** total (was 84%). `parsers.py` and `models.py` at **100%**.

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
