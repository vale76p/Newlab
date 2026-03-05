"""Async API client for the Newlab LED cloud platform.

Authentication flow
-------------------
1. GET /registrationwelcome  → extract csrfmiddlewaretoken from HTML + csrftoken cookie
2. POST /registrationlogin   → server replies 302; Set-Cookie contains sessionid

All subsequent requests send both cookies:
  Cookie: csrftoken=<value>; sessionid=<value>

Entity discovery
----------------
GET /registrationhome returns an HTML page with one slider per light group.
The parser tries FOUR strategies in order (most to least specific) and logs
every step so failures are diagnosable from the log alone.

Strategy A — strict input[id]:
  <input ... id="range_3" ... value="255" ...>

Strategy B — input[name] (some Django forms emit name instead of id):
  <input ... name="range_3" ... value="255" ...>

Strategy C — data attribute:
  <input ... data-group="3" ... value="255" ...>

Strategy D — broad fallback (matches range_N anywhere near a value):
  range_3 ... value="255"

Label strategies (tried in order for each group):
  L1 — <label for="range_3">Zone name</label>
  L2 — aria-label="Zone name" on the input tag itself
  L3 — title="Zone name" on the input tag itself
  L4 — closest preceding <td> / <th> / <span> text node
  Fallback — "Group {N}"  (neutral, user can rename in HA)

Control
-------
POST /smarthome/newplantsendcommand
  Content-Type: application/x-www-form-urlencoded
  Body: pwm=<0-255>&status=0&id_group=<N>

Debug
-----
Enable verbose logging in HA configuration.yaml:
  logger:
    logs:
      custom_components.newlab: debug
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Optional

import aiohttp

from .const import (
    CONNECT_TIMEOUT,
    CONTROL_URL,
    DEBUG_HTML_MAX_CHARS,
    DEFAULT_HEADERS,
    GROUP_NAME_FALLBACK,
    HOME_URL,
    LOGIN_URL,
    READ_TIMEOUT,
    REFRESH_URL,
    WELCOME_URL,
)

_LOGGER = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Data model
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class NewlabGroup:
    """Represents a single Newlab light group (zone)."""

    id_group: int
    name: str
    pwm: int = 0
    is_offline: bool = False           # True when input has class="offline" in HTML
    # Discovery metadata — logged but not exposed in HA state
    name_source: str = "fallback"      # "html_label" | "aria_label" | "title" | "td_text" | "fallback"
    parser_strategy: str = "unknown"   # "A_input_id" | "B_input_name" | "C_data_attr" | "D_broad"

    @property
    def is_on(self) -> bool:
        return self.pwm > 0

    @property
    def brightness(self) -> int:
        """HA brightness (0–255), same scale as PWM."""
        return self.pwm


@dataclass
class NewlabSystemInfo:
    """System-level information extracted from the cloud home page.

    plant_code      — installation/plant identifier (e.g. "y8gd189un32851ykg82z6ksl71g4lz")
    cloud_last_sync — last sync timestamp as shown by the Newlab cloud
                      (e.g. "Lunedì 16 Febbraio 2026 19:01") — this is the cloud's own value,
                      NOT the HA polling timestamp.
    cloud_version   — firmware/app version shown in the page title (e.g. "3.47")
    """

    plant_code: str = ""
    cloud_last_sync: str = ""
    cloud_version: str = ""


# ──────────────────────────────────────────────────────────────────────────────
# Exceptions
# ──────────────────────────────────────────────────────────────────────────────

class NewlabAuthError(Exception):
    """Raised when credentials are invalid or the session has expired."""


class NewlabConnectionError(Exception):
    """Raised on network / HTTP-level errors."""


class NewlabParseError(Exception):
    """Raised when no groups can be extracted from the HTML response."""


# ──────────────────────────────────────────────────────────────────────────────
# Regex patterns — compiled once at module level
# ──────────────────────────────────────────────────────────────────────────────

# ── Input discovery strategies ────────────────────────────────────────────────
# A — id="range_N"
_RE_A = re.compile(r'<input[^>]+id=["\']range_(\d+)["\'][^>]*>', re.IGNORECASE)
# B — name="range_N"
_RE_B = re.compile(r'<input[^>]+name=["\']range_(\d+)["\'][^>]*>', re.IGNORECASE)
# C — data-group="N" or data-id="N"
_RE_C = re.compile(r'<input[^>]+data-(?:group|id)=["\'](\d+)["\'][^>]*>', re.IGNORECASE)
# D — broad: "range_N" ... value="V"  anywhere in proximity (multiline-safe)
_RE_D = re.compile(r'range_(\d+)[^"\'<]{0,100}value=["\'](\d+)["\']', re.IGNORECASE)

# value="N" extractor (applied to tag text from strategies A/B/C)
_RE_VALUE = re.compile(r'value=["\'](\d+)["\']', re.IGNORECASE)

# ── Label strategies ──────────────────────────────────────────────────────────
# L1 — <label for="range_N">text</label>
_RE_L1 = re.compile(
    r'<label[^>]+for=["\']range_(\d+)["\'][^>]*>\s*([^<]{1,80}?)\s*</label>',
    re.IGNORECASE,
)
# L2 — aria-label="text" on the input tag itself (extracted from full tag string)
_RE_L2_ARIA = re.compile(r'aria-label=["\']([^"\']{1,80})["\']', re.IGNORECASE)
# L3 — title="text" on the input tag itself
_RE_L3_TITLE = re.compile(r'\btitle=["\']([^"\']{1,80})["\']', re.IGNORECASE)
# L4 — text in a <td>, <th>, or <span> that immediately precedes range_N in HTML
#       We search a 400-char window before each match position.
_RE_L4_CELL = re.compile(r'<(?:td|th|span)[^>]*>\s*([^<]{1,80}?)\s*</(?:td|th|span)>', re.IGNORECASE)

# Login CSRF token
_RE_CSRF = re.compile(
    r'name=["\']csrfmiddlewaretoken["\'] value=["\']([^"\']+)["\']',
    re.IGNORECASE,
)

# Offline device detection: input tag has class="offline" when unreachable
_RE_OFFLINE_CLASS = re.compile(r'class=["\'][^"\']*\boffline\b', re.IGNORECASE)

# Cloud metadata — extracted from /registrationhome HTML
# Production HTML: <p>Ultima sincronizzazione: <b>Lunedì 16 Febbraio 2026 19:01</b></p>
_RE_CLOUD_LAST_SYNC = re.compile(
    r'Ultima\s+sincronizzazione:\s*<b>([^<]+)</b>',
    re.IGNORECASE,
)
# Production HTML: <title>Newlab Smart Home - Ver. 3.47</title>
_RE_CLOUD_VERSION = re.compile(r'Ver\.\s*([\d.]+)', re.IGNORECASE)

# ── Plant code / Codice Impianto — tried in order ─────────────────────────────
# Patterns are from most to least specific; first match wins.
_RE_PLANT_CODE_PATTERNS: list[re.Pattern] = [
    # Pattern 1 — EXACT production HTML (most specific, always try first):
    #   <p>Codice Impianto: <b>y8gd189un32851ykg82z6ksl71g4lz</b></p>
    re.compile(r'Codice\s+Impianto:\s*<b>([^<]+)</b>', re.IGNORECASE),
    # Pattern 2 — JavaScript variable: var plant_id = "12345";
    re.compile(
        r'var\s+(?:plant|impianto)(?:_?(?:id|code|Id|Code))?\s*=\s*["\']([A-Za-z0-9_\-]{3,})["\']',
        re.IGNORECASE,
    ),
    # Pattern 3 — Hidden input whose name/id contains "plant" or "impianto"
    re.compile(
        r'<input[^>]+(?:name|id)=["\'][A-Za-z_]*(?:plant|impianto)[A-Za-z_]*["\'][^>]*value=["\']([A-Za-z0-9_\-]{3,})["\']',
        re.IGNORECASE,
    ),
    # Pattern 4 — data-attribute: data-plant-id="..." / data-impianto="..."
    re.compile(
        r'data-(?:plant[-_]?(?:id|code)|impianto[-_]?(?:id|codice))=["\']([A-Za-z0-9_\-]{3,})["\']',
        re.IGNORECASE,
    ),
    # Pattern 5 — URL segment after /smarthome/ (not a command keyword)
    re.compile(
        r'/smarthome/(?!newplant|send|plantrefresh)([A-Za-z0-9]{4,})/',
        re.IGNORECASE,
    ),
]


# ──────────────────────────────────────────────────────────────────────────────
# HTML parser
# ──────────────────────────────────────────────────────────────────────────────

def _html_excerpt(html: str, pos: int, window: int = 200) -> str:
    """Return a window of HTML centred on pos, for log readability."""
    start = max(0, pos - window // 2)
    end = min(len(html), pos + window // 2)
    return html[start:end].replace("\n", " ").replace("\r", "")


def _extract_labels(html: str) -> dict[int, tuple[str, str]]:
    """Return {id_group: (label_text, source)} from L1 label tags."""
    labels: dict[int, tuple[str, str]] = {}
    for m in _RE_L1.finditer(html):
        gid = int(m.group(1))
        text = m.group(2).strip()
        if text:
            labels[gid] = (text, "html_label")
            _LOGGER.debug(
                "[discovery] L1 label found: group=%d name=%r at pos=%d",
                gid, text, m.start(),
            )
    _LOGGER.debug("[discovery] L1 pass complete — %d label(s) found: %s", len(labels), list(labels.keys()))
    return labels


def _name_from_tag(tag_html: str, gid: int, html: str, match_pos: int, label_map: dict) -> tuple[str, str]:
    """Resolve best available name for a group, returning (name, source)."""

    # Prefer L1 label if available
    if gid in label_map:
        return label_map[gid]

    # L2 — aria-label on the input tag
    m = _RE_L2_ARIA.search(tag_html)
    if m:
        name = m.group(1).strip()
        _LOGGER.debug("[discovery] L2 aria-label: group=%d name=%r", gid, name)
        return name, "aria_label"

    # L3 — title on the input tag
    m = _RE_L3_TITLE.search(tag_html)
    if m:
        name = m.group(1).strip()
        _LOGGER.debug("[discovery] L3 title attr: group=%d name=%r", gid, name)
        return name, "title"

    # L4 — nearest preceding <td>/<th>/<span> in a 400-char window
    window_start = max(0, match_pos - 400)
    preceding = html[window_start:match_pos]
    cells = _RE_L4_CELL.findall(preceding)
    if cells:
        name = cells[-1].strip()  # closest cell (last match in preceding window)
        _LOGGER.debug("[discovery] L4 cell text: group=%d name=%r (window before pos %d)", gid, name, match_pos)
        return name, "td_text"

    # Generic fallback
    name = GROUP_NAME_FALLBACK.format(gid=gid)
    _LOGGER.debug("[discovery] fallback name: group=%d name=%r", gid, name)
    return name, "fallback"


def _parse_groups(html: str) -> dict[int, NewlabGroup]:
    """Parse the /registrationhome HTML and return all discovered light groups.

    Tries four parser strategies in order. Stops at the first one that finds
    at least one group. All attempts are logged at DEBUG level.

    Raises:
        NewlabParseError: if all strategies fail to find any group.
    """
    _LOGGER.debug(
        "[discovery] HTML response: %d chars total",
        len(html),
    )
    _LOGGER.debug(
        "[discovery] HTML excerpt (first %d chars):\n%s",
        DEBUG_HTML_MAX_CHARS,
        html[:DEBUG_HTML_MAX_CHARS],
    )

    # ── Pre-pass: extract all L1 labels ────────────────────────────────────
    label_map = _extract_labels(html)

    groups: dict[int, NewlabGroup] = {}

    # ── Strategy A: id="range_N" ────────────────────────────────────────────
    _LOGGER.debug("[discovery] Strategy A: searching id=[\"']range_N[\"']")
    for m in _RE_A.finditer(html):
        gid = int(m.group(1))
        tag_html = m.group(0)
        val_m = _RE_VALUE.search(tag_html)
        pwm = int(val_m.group(1)) if val_m else 0
        is_offline = bool(_RE_OFFLINE_CLASS.search(tag_html))
        name, src = _name_from_tag(tag_html, gid, html, m.start(), label_map)
        groups[gid] = NewlabGroup(id_group=gid, name=name, pwm=pwm, is_offline=is_offline, name_source=src, parser_strategy="A_input_id")
        _LOGGER.debug(
            "[discovery] A: group=%d pwm=%d offline=%s name=%r (source=%s) tag=%.120s",
            gid, pwm, is_offline, name, src, tag_html,
        )

    if groups:
        _LOGGER.info(
            "[discovery] Strategy A succeeded: %d group(s) found — %s",
            len(groups),
            {gid: g.name for gid, g in sorted(groups.items())},
        )
        return groups

    _LOGGER.debug("[discovery] Strategy A: 0 matches — trying B")

    # ── Strategy B: name="range_N" ──────────────────────────────────────────
    _LOGGER.debug("[discovery] Strategy B: searching name=[\"']range_N[\"']")
    for m in _RE_B.finditer(html):
        gid = int(m.group(1))
        tag_html = m.group(0)
        val_m = _RE_VALUE.search(tag_html)
        pwm = int(val_m.group(1)) if val_m else 0
        is_offline = bool(_RE_OFFLINE_CLASS.search(tag_html))
        name, src = _name_from_tag(tag_html, gid, html, m.start(), label_map)
        groups[gid] = NewlabGroup(id_group=gid, name=name, pwm=pwm, is_offline=is_offline, name_source=src, parser_strategy="B_input_name")
        _LOGGER.debug(
            "[discovery] B: group=%d pwm=%d offline=%s name=%r (source=%s)",
            gid, pwm, is_offline, name, src,
        )

    if groups:
        _LOGGER.info(
            "[discovery] Strategy B succeeded: %d group(s) — %s",
            len(groups),
            {gid: g.name for gid, g in sorted(groups.items())},
        )
        return groups

    _LOGGER.debug("[discovery] Strategy B: 0 matches — trying C")

    # ── Strategy C: data-group / data-id ────────────────────────────────────
    _LOGGER.debug("[discovery] Strategy C: searching data-group/data-id")
    for m in _RE_C.finditer(html):
        gid = int(m.group(1))
        tag_html = m.group(0)
        val_m = _RE_VALUE.search(tag_html)
        pwm = int(val_m.group(1)) if val_m else 0
        is_offline = bool(_RE_OFFLINE_CLASS.search(tag_html))
        name, src = _name_from_tag(tag_html, gid, html, m.start(), label_map)
        groups[gid] = NewlabGroup(id_group=gid, name=name, pwm=pwm, is_offline=is_offline, name_source=src, parser_strategy="C_data_attr")
        _LOGGER.debug(
            "[discovery] C: group=%d pwm=%d offline=%s name=%r (source=%s)",
            gid, pwm, is_offline, name, src,
        )

    if groups:
        _LOGGER.info(
            "[discovery] Strategy C succeeded: %d group(s) — %s",
            len(groups),
            {gid: g.name for gid, g in sorted(groups.items())},
        )
        return groups

    _LOGGER.debug("[discovery] Strategy C: 0 matches — trying D (broad fallback)")

    # ── Strategy D: broad pattern ────────────────────────────────────────────
    _LOGGER.debug("[discovery] Strategy D: broad pattern range_N ... value=V")
    for m in _RE_D.finditer(html):
        gid = int(m.group(1))
        pwm = int(m.group(2))
        name, src = _name_from_tag("", gid, html, m.start(), label_map)
        groups[gid] = NewlabGroup(id_group=gid, name=name, pwm=pwm, name_source=src, parser_strategy="D_broad")
        _LOGGER.debug(
            "[discovery] D: group=%d pwm=%d name=%r (source=%s) match=%.80s",
            gid, pwm, name, src, m.group(0),
        )

    if groups:
        _LOGGER.info(
            "[discovery] Strategy D succeeded: %d group(s) — %s",
            len(groups),
            {gid: g.name for gid, g in sorted(groups.items())},
        )
        return groups

    # ── All strategies failed ────────────────────────────────────────────────
    _LOGGER.error(
        "[discovery] ALL strategies failed. "
        "HTML length=%d. Excerpt:\n%s\n"
        "Please open a GitHub issue and attach this log excerpt.",
        len(html),
        html[:DEBUG_HTML_MAX_CHARS],
    )
    raise NewlabParseError(
        f"No light groups found in HTML ({len(html)} chars). "
        "All four parser strategies (A/B/C/D) returned 0 results. "
        "Check the HA log at DEBUG level for the full HTML excerpt."
    )


def _parse_system_info(html: str) -> NewlabSystemInfo:
    """Extract system-level info from the /registrationhome HTML.

    Extracts (best-effort, never raises):
      - plant_code      via _RE_PLANT_CODE_PATTERNS (first match wins)
      - cloud_last_sync via _RE_CLOUD_LAST_SYNC
      - cloud_version   via _RE_CLOUD_VERSION
    """
    info = NewlabSystemInfo()

    # ── Plant code ──────────────────────────────────────────────────────────
    for i, pattern in enumerate(_RE_PLANT_CODE_PATTERNS, 1):
        m = pattern.search(html)
        if m:
            info.plant_code = m.group(1).strip()
            _LOGGER.debug(
                "[discovery] codice_impianto: pattern %d matched → %r  context=%.80r",
                i, info.plant_code,
                html[max(0, m.start() - 20): m.end() + 20],
            )
            break
    if not info.plant_code:
        _LOGGER.debug(
            "[discovery] codice_impianto: all %d patterns found nothing",
            len(_RE_PLANT_CODE_PATTERNS),
        )

    # ── Cloud last sync ──────────────────────────────────────────────────────
    m = _RE_CLOUD_LAST_SYNC.search(html)
    if m:
        info.cloud_last_sync = m.group(1).strip()
        _LOGGER.debug("[discovery] cloud_last_sync: %r", info.cloud_last_sync)
    else:
        _LOGGER.debug("[discovery] cloud_last_sync: not found in HTML")

    # ── Cloud version ────────────────────────────────────────────────────────
    m = _RE_CLOUD_VERSION.search(html)
    if m:
        info.cloud_version = m.group(1).strip()
        _LOGGER.debug("[discovery] cloud_version: %r", info.cloud_version)
    else:
        _LOGGER.debug("[discovery] cloud_version: not found in HTML")

    return info


# ──────────────────────────────────────────────────────────────────────────────
# API client
# ──────────────────────────────────────────────────────────────────────────────

class NewlabAPI:
    """Async client for the Newlab LED cloud.

    Lifecycle
    ---------
    1. Instantiate with username / password.
    2. ``await api.login()``       — obtains session cookies.
    3. ``await api.get_groups()``  — polls state of all discovered groups.
    4. ``await api.set_light(N, pwm)`` — sends control command.

    The aiohttp.ClientSession is provided by the caller and shared to enable
    connection pooling across the coordinator's poll cycles.
    """

    def __init__(
        self,
        username: str,
        password: str,
        session: aiohttp.ClientSession,
    ) -> None:
        self._username = username
        self._password = password
        self._session = session
        self._csrf_token: Optional[str] = None
        self._session_id: Optional[str] = None
        # System-level info updated on every get_groups() call
        self.system_info: NewlabSystemInfo = NewlabSystemInfo()

    # ── Public properties ──────────────────────────────────────────────────

    @property
    def is_authenticated(self) -> bool:
        return bool(self._csrf_token and self._session_id)

    @property
    def cookie_header(self) -> str:
        if self._csrf_token and self._session_id:
            return f"csrftoken={self._csrf_token}; sessionid={self._session_id}"
        return ""

    # ── Authentication ─────────────────────────────────────────────────────

    async def login(self) -> None:
        """Authenticate with the Newlab cloud (two-step CSRF + session).

        Raises:
            NewlabAuthError: credentials rejected or cookies not set.
            NewlabConnectionError: network-level failure.
            NewlabParseError: CSRF token not found in HTML.
        """
        _LOGGER.debug("[login] starting — user=%r", self._username)
        t0 = time.monotonic()

        timeout = aiohttp.ClientTimeout(connect=CONNECT_TIMEOUT, sock_read=READ_TIMEOUT)
        jar = aiohttp.CookieJar(unsafe=True)

        async with aiohttp.ClientSession(
            cookie_jar=jar,
            timeout=timeout,
            headers=DEFAULT_HEADERS,
        ) as tmp:

            # ── Step 1: GET welcome page ───────────────────────────────────
            _LOGGER.debug("[login] step 1 — GET %s", WELCOME_URL)
            try:
                async with tmp.get(WELCOME_URL) as resp:
                    status = resp.status
                    _LOGGER.debug(
                        "[login] step 1 response: HTTP %d  content-type=%s",
                        status, resp.content_type,
                    )
                    if status != 200:
                        raise NewlabConnectionError(
                            f"GET {WELCOME_URL} returned HTTP {status} (expected 200)"
                        )
                    html = await resp.text()
                    _LOGGER.debug(
                        "[login] step 1 HTML: %d chars, cookies after: %s",
                        len(html),
                        [c.key for c in jar],
                    )
            except aiohttp.ClientError as exc:
                raise NewlabConnectionError(f"GET welcome failed: {exc}") from exc

            # Extract csrfmiddlewaretoken
            m = _RE_CSRF.search(html)
            if not m:
                _LOGGER.error(
                    "[login] csrfmiddlewaretoken NOT FOUND in HTML (%d chars). "
                    "Excerpt:\n%s",
                    len(html), html[:1500],
                )
                raise NewlabParseError(
                    "csrfmiddlewaretoken not found in welcome page HTML. "
                    "The site structure may have changed."
                )
            csrf_middleware = m.group(1)
            _LOGGER.debug(
                "[login] csrfmiddlewaretoken extracted: len=%d chars (value hidden)",
                len(csrf_middleware),
            )

            # ── Step 2: POST login ─────────────────────────────────────────
            # Django returns 302 → home page. The sessionid cookie is set by
            # the redirect TARGET (the GET to home), NOT in the 302 headers.
            # Using allow_redirects=True so aiohttp follows the full chain and
            # the cookie jar captures sessionid from the final response.
            _LOGGER.debug(
                "[login] step 2 — POST %s (allow_redirects=True, follows 302→GET)",
                LOGIN_URL,
            )
            login_data = {
                "csrfmiddlewaretoken": csrf_middleware,
                "username": self._username,
                "password": "***",          # never log the real password
                "next": "",
            }
            _LOGGER.debug("[login] POST fields: %s", {k: v for k, v in login_data.items()})
            login_data["password"] = self._password  # restore before sending

            login_headers = {
                "Referer": WELCOME_URL,
                "Content-Type": "application/x-www-form-urlencoded",
                "X-CSRFToken": csrf_middleware,
            }
            try:
                async with tmp.post(
                    LOGIN_URL,
                    data=login_data,
                    headers=login_headers,
                    allow_redirects=True,   # follow 302 → GET /home to get sessionid
                ) as resp:
                    status = resp.status
                    final_url = str(resp.url)
                    _LOGGER.debug(
                        "[login] step 2 final: HTTP %d  final_url=%r  "
                        "resp.cookies=%s  jar_keys=%s",
                        status, final_url,
                        list(resp.cookies.keys()),
                        [c.key for c in jar],
                    )
                    # If Django redirected us back to the login/welcome page,
                    # the credentials were rejected.
                    _login_url_keywords = ("login", "welcome", "register")
                    if any(kw in final_url.lower() for kw in _login_url_keywords):
                        raise NewlabAuthError(
                            f"Login redirected back to authentication page "
                            f"({final_url!r}). Check your credentials."
                        )
                    if status != 200:
                        raise NewlabAuthError(
                            f"POST login + redirect returned HTTP {status} "
                            f"(expected 200). final_url={final_url!r}"
                        )
            except aiohttp.ClientError as exc:
                raise NewlabConnectionError(f"POST login failed: {exc}") from exc

            # Extract cookies
            cookies = {c.key: c.value for c in jar}
            _LOGGER.debug(
                "[login] cookie jar after login: keys=%s (values hidden)",
                list(cookies.keys()),
            )

            csrf = cookies.get("csrftoken")
            sessid = cookies.get("sessionid")

            if not csrf:
                _LOGGER.error(
                    "[login] 'csrftoken' cookie missing after login. "
                    "Cookie jar keys: %s", list(cookies.keys()),
                )
            if not sessid:
                _LOGGER.error(
                    "[login] 'sessionid' cookie missing after login. "
                    "Cookie jar keys: %s", list(cookies.keys()),
                )

            if not csrf or not sessid:
                raise NewlabAuthError(
                    "Session cookies missing after login "
                    f"(csrftoken={'OK' if csrf else 'MISSING'}, "
                    f"sessionid={'OK' if sessid else 'MISSING'}). "
                    "Wrong credentials or site structure changed."
                )

            self._csrf_token = csrf
            self._session_id = sessid

            elapsed = time.monotonic() - t0
            _LOGGER.info(
                "[login] SUCCESS — user=%r  elapsed=%.2fs  "
                "csrftoken_len=%d  sessionid_len=%d",
                self._username, elapsed, len(csrf), len(sessid),
            )

    # ── State polling ──────────────────────────────────────────────────────

    async def get_groups(self) -> dict[int, NewlabGroup]:
        """Fetch current state of all light groups via HTML discovery.

        Raises:
            NewlabAuthError: session expired (server redirected to login).
            NewlabConnectionError: network-level failure.
            NewlabParseError: HTML structure not recognised.
        """
        if not self.is_authenticated:
            raise NewlabAuthError("Not authenticated — call login() first.")

        _LOGGER.debug("[poll] GET %s", HOME_URL)
        t0 = time.monotonic()

        headers = {
            **DEFAULT_HEADERS,
            "Cookie": self.cookie_header,
        }
        try:
            async with self._session.get(HOME_URL, headers=headers) as resp:
                status = resp.status
                content_type = resp.content_type
                _LOGGER.debug(
                    "[poll] response: HTTP %d  content-type=%s  url=%s",
                    status, content_type, str(resp.url),
                )

                if status == 302:
                    location = resp.headers.get("Location", "")
                    _LOGGER.warning(
                        "[poll] HTTP 302 redirect to %r — session expired, re-auth needed",
                        location,
                    )
                    raise NewlabAuthError("Session expired (HTTP 302 redirect)")

                if status != 200:
                    raise NewlabConnectionError(
                        f"GET {HOME_URL} returned HTTP {status}"
                    )

                # Check if we were silently redirected to the login page
                final_url = str(resp.url)
                if "login" in final_url.lower() and HOME_URL not in final_url:
                    _LOGGER.warning(
                        "[poll] followed redirect to login page (%s) — session expired",
                        final_url,
                    )
                    raise NewlabAuthError("Session expired (redirected to login)")

                html = await resp.text()
                _LOGGER.debug("[poll] HTML received: %d chars", len(html))

        except aiohttp.ClientError as exc:
            raise NewlabConnectionError(f"GET home failed: {exc}") from exc

        groups = _parse_groups(html)

        # Also extract plant code (best-effort, does not raise on failure)
        self.system_info = _parse_system_info(html)
        if self.system_info.plant_code:
            _LOGGER.debug("[poll] codice_impianto=%r", self.system_info.plant_code)

        elapsed = time.monotonic() - t0
        _LOGGER.debug(
            "[poll] complete — %d group(s)  elapsed=%.2fs  states=%s",
            len(groups),
            elapsed,
            {gid: g.pwm for gid, g in sorted(groups.items())},
        )
        return groups

    # ── Control ────────────────────────────────────────────────────────────

    async def set_light(self, id_group: int, pwm: int) -> bool:
        """Send a PWM command to a light group.

        Args:
            id_group: Group ID as returned by discovery.
            pwm: 0 = off, 255 = full brightness.  Clamped to [0, 255].

        Returns:
            True on HTTP 2xx, False otherwise.
        """
        if not self.is_authenticated:
            _LOGGER.error("[control] set_light called without authentication")
            return False

        pwm = max(0, min(255, int(pwm)))
        payload = f"pwm={pwm}&status=0&id_group={id_group}"

        _LOGGER.debug(
            "[control] POST %s  payload=%r",
            CONTROL_URL, payload,
        )

        headers = {
            **DEFAULT_HEADERS,
            "Cookie": self.cookie_header,
            "X-CSRFToken": self._csrf_token or "",
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": HOME_URL,
        }
        try:
            async with self._session.post(
                CONTROL_URL,
                data=payload,
                headers=headers,
            ) as resp:
                status = resp.status
                body = (await resp.text())[:200]  # truncated for log
                success = status in (200, 204)
                if success:
                    _LOGGER.debug(
                        "[control] OK — group=%d pwm=%d HTTP %d body=%.80r",
                        id_group, pwm, status, body,
                    )
                else:
                    _LOGGER.warning(
                        "[control] FAILED — group=%d pwm=%d HTTP %d body=%.80r",
                        id_group, pwm, status, body,
                    )
                return success
        except aiohttp.ClientError as exc:
            _LOGGER.error(
                "[control] exception — group=%d pwm=%d error=%s",
                id_group, pwm, exc,
            )
            return False

    # ── Plant refresh ───────────────────────────────────────────────────────

    async def async_refresh_plant(self) -> bool:
        """POST to /smarthome/plantrefresh — asks the cloud to re-sync with physical devices.

        The cloud responds "OK" on success. The web app then waits ~5 seconds
        before reloading state; callers should do the same before requesting a
        coordinator refresh.

        Returns:
            True if the cloud responded "OK", False otherwise.
        """
        if not self.is_authenticated:
            _LOGGER.error("[refresh] async_refresh_plant called without authentication")
            return False

        headers = {
            **DEFAULT_HEADERS,
            "Cookie": self.cookie_header,
            "X-CSRFToken": self._csrf_token or "",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": HOME_URL,
        }
        _LOGGER.debug("[refresh] POST %s", REFRESH_URL)
        try:
            async with self._session.post(REFRESH_URL, headers=headers) as resp:
                text = (await resp.text()).strip()
                success = text.upper() == "OK"
                _LOGGER.debug(
                    "[refresh] response: HTTP %d  body=%r  success=%s",
                    resp.status, text[:80], success,
                )
                if not success:
                    _LOGGER.warning(
                        "[refresh] unexpected response from plantrefresh: HTTP %d  body=%r",
                        resp.status, text[:80],
                    )
                return success
        except aiohttp.ClientError as exc:
            _LOGGER.error("[refresh] plantrefresh request failed: %s", exc)
            return False

    # ── Re-auth helper ─────────────────────────────────────────────────────

    async def ensure_authenticated(self) -> None:
        """Login if not already authenticated."""
        if not self.is_authenticated:
            _LOGGER.debug("[auth] ensure_authenticated: not authenticated, calling login()")
            await self.login()
