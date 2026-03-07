# Newlab LED — Home Assistant Integration

[![HACS Default](https://img.shields.io/badge/HACS-Default-41BDF5.svg)](https://hacs.xyz)
[![HA Version](https://img.shields.io/badge/HA-2024.1%2B-blue.svg)](https://www.home-assistant.io)
[![Latest Release](https://img.shields.io/github/v/release/vale76p/Newlab?display_name=tag&sort=semver)](https://github.com/vale76p/Newlab/releases/latest)
[![Validate](https://github.com/vale76p/Newlab/actions/workflows/validate.yml/badge.svg)](https://github.com/vale76p/Newlab/actions/workflows/validate.yml)
[![Coverage](https://img.shields.io/badge/coverage-90%25-brightgreen)](https://github.com/vale76p/Newlab/actions/workflows/validate.yml)

Custom integration for controlling **Newlab LED** lighting zones via the
`smarthome.newlablight.com` cloud platform.

---

## Features

- **Full brightness control** for all light zones (PWM 0–255 mapped to HA brightness)
- **Raw PWM slider** (0–255) per zone as a separate Number entity
- **Automatic zone discovery** — no hardcoded configuration, zones are read from the cloud
- **Single HTTP poll** shared across all entities (efficient, configurable interval 5–60 s)
- **Automatic re-authentication** when the session expires — no manual intervention needed
- **Offline detection** — zones reported as offline by the cloud are shown as unavailable in HA
- **Diagnostic sensors** — plant code, firmware version, last cloud sync timestamp
- **Plant refresh button** — force-sync the physical controller with the cloud on demand
- **Options flow** — change poll interval at any time without removing the integration
- Compatible with HA automations, dashboards, Alexa, Google Home

---

## What Gets Created

For each discovered lighting zone (e.g. Cucina, Soggiorno, Bagno …):

| Entity | Type | Description |
|--------|------|-------------|
| `light.<zone>` | Light | On/Off + brightness control |
| `number.<zone>_pwm` | Number | Raw PWM slider 0–255 |

For the hub (one per integration instance):

| Entity | Type | Description |
|--------|------|-------------|
| `sensor.codice_impianto` | Sensor (diagnostic) | Plant/installation identifier |
| `sensor.versione_cloud` | Sensor (diagnostic) | Cloud firmware version (e.g. `3.47`) |
| `sensor.ultima_sincronizzazione_cloud` | Sensor (diagnostic) | Last sync timestamp from Newlab cloud |
| `button.aggiorna_impianto` | Button (diagnostic) | Force plant refresh (POST to cloud) |

All entities are grouped under a single **Newlab LED Controller** device card in HA.

---

## Zone Discovery

Zones are discovered dynamically from the cloud HTML — no hardcoded list.
If a zone has no label, the fallback name is `Group <N>`.
You can rename entities in HA at any time — the unique ID is always stable.

---

## Installation

### Via HACS (recommended)

Newlab LED is available in [HACS](https://hacs.xyz) (Home Assistant Community Store).

Use this link to directly go to the repository in HACS:

[![Open HACS Repository on my](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=vale76p&repository=Newlab&category=integration)

1. Open **HACS → Integrations**
2. Search for **Newlab LED** and click **Install**
3. Restart Home Assistant

### Manual

1. Copy the `custom_components/newlab/` folder into your HA `custom_components/` directory
2. Restart Home Assistant

---

## Setup

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **Newlab LED**
3. Enter your `smarthome.newlablight.com` credentials (username + password)
4. Set the **poll interval** (default: 10 s, min: 5 s, max: 60 s) using the slider

That's it — all zones are discovered automatically.

---

## Options

Click **Configure** on the integration card to change the **poll interval** without
reconfiguring the integration.

---

## Device Card

All entities appear under a single device called **Newlab LED Controller**:

- **Controls** — one light + one PWM number per zone
- **Diagnostics** section:
  - Codice Impianto (serial number)
  - Versione Cloud (firmware)
  - Ultima Sincronizzazione Cloud (last sync from Newlab)
  - Aggiorna Impianto button

The firmware version (e.g. `3.47`) is also shown in the device info header.

---

## Usage in Automations

```yaml
# Turn on Cucina at 50% brightness
service: light.turn_on
target:
  entity_id: light.led_cucina
data:
  brightness_pct: 50

# Turn off all Newlab lights
service: light.turn_off
target:
  entity_id:
    - light.led_cucina
    - light.led_soggiorno
    - light.led_bagno


# Set raw PWM value
service: number.set_value
target:
  entity_id: number.led_cucina_pwm
data:
  value: 128

# Force cloud sync
service: button.press
target:
  entity_id: button.newlab_led_controller_aggiorna_impianto
```

---

## Troubleshooting

### Light shows "unavailable"

- The physical controller may be offline (check the Newlab cloud app)
- HA logs: enable debug logging (see below) and look for `[coordinator]` or `[api]` entries
- Try the **Aggiorna Impianto** button to force a cloud sync
- Verify credentials at `smarthome.newlablight.com`
- Click **Reload** on the integration card

### State not updating

- Reduce poll interval via **Configure** on the integration card
- Check internet connectivity from the HA host

### A new zone is not appearing

Zones are discovered at startup. After adding a new zone to the Newlab cloud app,
click **Reload** on the integration card.

### Enable debug logging

Add to `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.newlab: debug
```

Then check **Settings → System → Logs** and filter by `newlab`.

---

## Requirements

- Home Assistant 2024.1 or newer
- Active account on `smarthome.newlablight.com`
- Internet access from the HA host

---

## Sviluppo Locale (Test + Lint + Mypy)

Questa repo include:
- **Lint** con `ruff` (E, F, I, B, UP, SIM, C4, PIE, RET, TC)
- **Type check** con `mypy` (configurazione graduale)
- **Test** con `pytest` — 33 unit test, coverage ≥ 85% gate in CI
- **CI GitHub Actions** — matrice Python 3.11/3.12, job separato per mypy

Comandi locali:

```bash
# Installa tool di sviluppo (una volta)
python3 -m pip install --user ruff pytest pytest-cov aiohttp mypy

# Lint
ruff check .

# Type check
mypy custom_components/newlab

# Test
pytest -q

# Coverage report (console + coverage.xml + htmlcov/) con gate
pytest -q --cov=custom_components/newlab --cov-report=term-missing --cov-report=xml --cov-report=html --cov-fail-under=85
```

Se i tool non sono nel `PATH`, usa il prefisso `python3 -m` (es. `python3 -m ruff check .`).

---

## Changelog

Vedi [CHANGELOG.md](CHANGELOG.md) nella root del repository.

---

## License

MIT
