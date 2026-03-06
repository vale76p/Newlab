# Newlab LED Cloud — API Research

Reverse engineering notes for `smarthome.newlablight.com`, aligned with current code in:
- `custom_components/newlab/client.py`
- `custom_components/newlab/parsers.py`

---

## Authentication

Django session-based auth with CSRF protection.

### Login Flow

```
1. GET  https://smarthome.newlablight.com/registrationwelcome
   ← HTTP 200
   ← Set-Cookie: csrftoken=<value>; Path=/; SameSite=Lax
   ← HTML: <input name="csrfmiddlewaretoken" value="<token>">

2. POST https://smarthome.newlablight.com/registrationlogin
   Headers:
     Content-Type: application/x-www-form-urlencoded
     X-CSRFToken: <csrfmiddlewaretoken>
     Referer: https://smarthome.newlablight.com/registrationwelcome
   Body:
     csrfmiddlewaretoken=<token>&username=<user>&password=<pass>&next=

   ← typically redirect chain ending on HTTP 200 /registrationhome
   ← Set-Cookie: sessionid=<value>; Path=/; HttpOnly; SameSite=Lax
```

All subsequent requests include both cookies:
```
Cookie: csrftoken=<value>; sessionid=<value>
```

Control requests also need:
```
X-CSRFToken: <csrftoken>
X-Requested-With: XMLHttpRequest
```

### Session Expiry

Session expiry is detected when poll returns:
1. HTTP 302 redirect
2. or final URL pointing back to login page

The coordinator re-authenticates automatically and retries once.

---

## State Endpoint — Zone Discovery

```
GET https://smarthome.newlablight.com/registrationhome
Headers:
  Cookie: csrftoken=<value>; sessionid=<value>

← HTTP 200  (HTML page with zone sliders + hub info)
← HTTP 302  (session expired → redirect to login)
```

### Zone HTML Structure

Zones are rendered as `<input type="range">` controls with group index.
Parser supports multiple variants:
1. `id="range_N"` (Strategy A)
2. `name="range_N"` (Strategy B)
3. `data-group="N"` or `data-id="N"` (Strategy C)
4. broad fallback regex (Strategy D)

Name resolution order:
1. `<label for="range_N">...`
2. `aria-label` on input
3. `title` on input
4. nearest preceding `<td>/<th>/<span>` text
5. fallback `Group N`

```html
<tr>
    <td>3</td>
    <td>Led Cucina</td>
    <td style="min-width:150px;" class="ranges">
        <input id="range_3" class="" type="range" style="width:100%;"
               min="0" max="255" step="1" value="0" >
    </td>
    <td class="noacapo"> <span class="valore pwmvalue" id="val_3">OFF</span></td>
    <td><button type="button" class="btn btn-sm btlight min150 btn-warning"
                id="bt_3">Turn On</button></td>
</tr>
```

`value` = current PWM (0 = off, 1–255 = on at that level).

### Offline Zone

When a zone is offline (physical controller not reachable), the `<input>` carries an
`offline` CSS class:

```html
<input id="range_3" class="offline" type="range" value="0" min="0" max="255">
```

### Parsing Rules (implemented in `parsers.py`)

```python
_parse_groups(html) -> dict[int, NewlabGroup]
  - reads PWM from input `value`
  - marks group offline if input class contains `offline`
  - assigns parser strategy + name source for diagnostics
```

---

## Hub Diagnostic Data (same HTML response)

Important: cloud labels can be English or Italian (Django i18n).
Regexes in parser support both.

### Plant Id / Codice Impianto

```html
<!-- EN (production, Accept-Language: en) -->
<p>Plant Id: <b>y8gd189un32851ykg82z6ksl71g4lz</b></p>

<!-- IT (Accept-Language: it) -->
<p>Codice Impianto: <b>y8gd189un32851ykg82z6ksl71g4lz</b></p>
```

```python
r'(?:Plant\s+Id|Codice\s+Impianto)\b.{0,60}?<(?:b|strong)[^>]*>\s*([^<]{3,80}?)\s*</(?:b|strong)>'
```

### Cloud Version (Firmware)

Appears in the `<title>` tag:

```html
<title>Newlab Smart Home - Ver. 3.47</title>
```

```python
r'Ver\.\s*([\d.]+)'
```

### Last Syncronization / Ultima Sincronizzazione

Timestamp of the last time the physical controller synced with the cloud.
Note: "syncronization" is a typo in the Newlab cloud HTML (missing 'h').

```html
<!-- EN (production) -->
<p>Last syncronization: <b>Feb. 16, 2026, 7:01 p.m.</b></p>

<!-- IT -->
<p>Ultima sincronizzazione: <b>Lunedì 16 Febbraio 2026 19:01</b></p>
```

```python
r'(?:Last\s+sync(?:h?ronization)|Ultima\s+sincronizzazione)\b.{0,60}?<(?:b|strong)[^>]*>\s*([^<]{4,80}?)\s*</(?:b|strong)>'
```

---

## Control Endpoint

```
POST https://smarthome.newlablight.com/smarthome/newplantsendcommand
Headers:
  Cookie: csrftoken=<value>; sessionid=<value>
  X-CSRFToken: <csrftoken>
  Content-Type: application/x-www-form-urlencoded
  X-Requested-With: XMLHttpRequest
  Referer: https://smarthome.newlablight.com/registrationhome

Body (URL-encoded):
  pwm=<0-255>&status=0&id_group=<N>

`client.py` considers `200` or `204` as success.
```

| Parameter | Type | Values | Notes |
|-----------|------|--------|-------|
| `id_group` | int | 3, 4, 5, 6, 7, … | Zone identifier |
| `pwm` | int | 0–255 | 0 = off, 255 = max brightness |
| `status` | int | 0 | Fixed value, purpose unknown |

PWM → HA brightness mapping is 1:1 (both use 0–255).

---

## Plant Refresh Endpoint

Forces the cloud to re-sync state from the physical controller.
Mirrors the behavior of the "Refresh" button in the Newlab web app.

```
POST https://smarthome.newlablight.com/smarthome/plantrefresh
Headers:
  Cookie: csrftoken=<value>; sessionid=<value>
  X-CSRFToken: <csrftoken>
  Content-Type: application/x-www-form-urlencoded
  X-Requested-With: XMLHttpRequest
  Referer: https://smarthome.newlablight.com/registrationhome

Body: (empty or minimal form data)

← HTTP 200, body: "OK"
```

Integration behavior:
1. call endpoint
2. wait 5 seconds
3. force coordinator refresh

---

## Polling Settings

| Parameter | Value |
|-----------|-------|
| Default interval | 10 s |
| Minimum | 5 s |
| Maximum | 60 s |
| Connect timeout | 10 s |
| Read timeout | 15 s |

`config_flow` enforces 5-60 seconds with slider.

---

## Known Limitations

1. **No public JSON API** — the cloud exposes HTML only
2. **No WebSocket / push** — state can only be retrieved via polling
3. **HTML structure undocumented** — may change without notice
4. **PWM is continuous but the mobile app may use on/off only** — HA exposes full 0–255 brightness

---

## Implementation Note

Since refactor, API layer is modular:
1. HTTP transport: `client.py`
2. Parsing: `parsers.py`
3. Models/errors: `models.py`
4. Compatibility facade: `api.py`
