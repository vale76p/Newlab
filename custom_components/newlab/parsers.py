"""HTML parsing utilities for Newlab cloud pages.

All parsing is done with regex on raw HTML (no BeautifulSoup dependency).
Functions are stateless and never perform I/O.
"""

from __future__ import annotations

import logging
import re

from .const import DEBUG_HTML_MAX_CHARS, GROUP_NAME_FALLBACK
from .models import NewlabGroup, NewlabParseError, NewlabSystemInfo

_LOGGER = logging.getLogger(__name__)

# ── Input discovery strategies ────────────────────────────────────────────────
# A — id="range_N"
_RE_A = re.compile(r'<input[^>]+id=["\']range_(\d+)["\'][^>]*>', re.IGNORECASE)
# B — name="range_N"
_RE_B = re.compile(r'<input[^>]+name=["\']range_(\d+)["\'][^>]*>', re.IGNORECASE)
# C — data-group="N" or data-id="N"
_RE_C = re.compile(r'<input[^>]+data-(?:group|id)=["\'](\d+)["\'][^>]*>', re.IGNORECASE)
# D — broad: "range_N" ... value="V" anywhere in proximity
_RE_D = re.compile(r'range_(\d+)[^"\'<]{0,100}value=["\'](\d+)["\']', re.IGNORECASE)

# value="N" extractor (applied to tag text from strategies A/B/C)
_RE_VALUE = re.compile(r'value=["\'](\d+)["\']', re.IGNORECASE)

# ── Label strategies ──────────────────────────────────────────────────────────
# L1 — <label for="range_N">text</label>
_RE_L1 = re.compile(
    r'<label[^>]+for=["\']range_(\d+)["\'][^>]*>\s*([^<]{1,80}?)\s*</label>',
    re.IGNORECASE,
)
# L2 — aria-label="text" on the input tag itself
_RE_L2_ARIA = re.compile(r'aria-label=["\']([^"\']{1,80})["\']', re.IGNORECASE)
# L3 — title="text" on the input tag itself
_RE_L3_TITLE = re.compile(r'\btitle=["\']([^"\']{1,80})["\']', re.IGNORECASE)
# L4 — text in a <td>, <th>, or <span> preceding range_N (400-char window)
_RE_L4_CELL = re.compile(
    r'<(?:td|th|span)[^>]*>\s*([^<]{1,80}?)\s*</(?:td|th|span)>',
    re.IGNORECASE,
)

# Offline device detection
_RE_OFFLINE_CLASS = re.compile(r'class=["\'][^"\']*\boffline\b', re.IGNORECASE)

# ── Cloud metadata ────────────────────────────────────────────────────────────
# Supports both EN and IT labels (Django i18n)
_RE_CLOUD_LAST_SYNC = re.compile(
    r'(?:Last\s+sync(?:h?ronization)|Ultima\s+sincronizzazione)\b'
    r'.{0,60}?<(?:b|strong)[^>]*>\s*([^<]{4,80}?)\s*</(?:b|strong)>',
    re.IGNORECASE | re.DOTALL,
)
_RE_CLOUD_VERSION = re.compile(r'Ver\.\s*([\d.]+)', re.IGNORECASE)

_RE_PLANT_CODE_PATTERNS: list[re.Pattern] = [
    # Pattern 1 — EN: "Plant Id: <b>...</b>"  IT: "Codice Impianto: <b>...</b>"
    re.compile(
        r'(?:Plant\s+Id|Codice\s+Impianto)\b'
        r'.{0,60}?<(?:b|strong)[^>]*>\s*([^<]{3,80}?)\s*</(?:b|strong)>',
        re.IGNORECASE | re.DOTALL,
    ),
    # Pattern 2 — JavaScript variable: var plant_id = "12345";
    re.compile(
        r'var\s+(?:plant|impianto)(?:_?(?:id|code|Id|Code))?\s*=\s*["\']([A-Za-z0-9_\-]{3,})["\']',
        re.IGNORECASE,
    ),
    # Pattern 3 — Hidden input: name/id contains "plant" or "impianto"
    re.compile(
        r'<input[^>]+(?:name|id)=["\'][A-Za-z_]*(?:plant|impianto)[A-Za-z_]*["\'][^>]*value=["\']([A-Za-z0-9_\-]{3,})["\']',
        re.IGNORECASE,
    ),
    # Pattern 4 — data-attribute: data-plant-id="..." / data-impianto="..."
    re.compile(
        r'data-(?:plant[-_]?(?:id|code)|impianto[-_]?(?:id|codice))=["\']([A-Za-z0-9_\-]{3,})["\']',
        re.IGNORECASE,
    ),
]


# ── Internal helpers ──────────────────────────────────────────────────────────


def _extract_labels(html: str) -> dict[int, tuple[str, str]]:
    """Return {id_group: (label_text, source)} from L1 label tags."""
    labels: dict[int, tuple[str, str]] = {}
    for m in _RE_L1.finditer(html):
        gid = int(m.group(1))
        text = m.group(2).strip()
        if text:
            labels[gid] = (text, "html_label")
            _LOGGER.debug("[discovery] L1 label: group=%d name=%r", gid, text)
    _LOGGER.debug("[discovery] L1 pass — %d label(s): %s", len(labels), list(labels.keys()))
    return labels


def _name_from_tag(
    tag_html: str,
    gid: int,
    html: str,
    match_pos: int,
    label_map: dict[int, tuple[str, str]],
) -> tuple[str, str]:
    """Resolve best available name for a group, returning (name, source)."""
    if gid in label_map:
        return label_map[gid]

    m = _RE_L2_ARIA.search(tag_html)
    if m:
        name = m.group(1).strip()
        _LOGGER.debug("[discovery] L2 aria-label: group=%d name=%r", gid, name)
        return name, "aria_label"

    m = _RE_L3_TITLE.search(tag_html)
    if m:
        name = m.group(1).strip()
        _LOGGER.debug("[discovery] L3 title: group=%d name=%r", gid, name)
        return name, "title"

    window_start = max(0, match_pos - 400)
    cells = _RE_L4_CELL.findall(html[window_start:match_pos])
    if cells:
        name = cells[-1].strip()
        _LOGGER.debug("[discovery] L4 cell text: group=%d name=%r", gid, name)
        return name, "td_text"

    name = GROUP_NAME_FALLBACK.format(gid=gid)
    _LOGGER.debug("[discovery] fallback name: group=%d name=%r", gid, name)
    return name, "fallback"


def _run_strategy(
    label: str,
    strategy: str,
    regex: re.Pattern,
    html: str,
    label_map: dict[int, tuple[str, str]],
    *,
    broad: bool = False,
) -> dict[int, NewlabGroup]:
    """Run a single parser strategy and return discovered groups."""
    _LOGGER.debug("[discovery] Strategy %s: searching…", label)
    groups: dict[int, NewlabGroup] = {}

    for m in regex.finditer(html):
        gid = int(m.group(1))
        if broad:
            pwm = int(m.group(2))
            tag_html = ""
            is_offline = False
        else:
            tag_html = m.group(0)
            val_m = _RE_VALUE.search(tag_html)
            pwm = int(val_m.group(1)) if val_m else 0
            is_offline = bool(_RE_OFFLINE_CLASS.search(tag_html))

        name, src = _name_from_tag(tag_html, gid, html, m.start(), label_map)
        groups[gid] = NewlabGroup(
            id_group=gid,
            name=name,
            pwm=pwm,
            is_offline=is_offline,
            name_source=src,
            parser_strategy=strategy,
        )
        _LOGGER.debug(
            "[discovery] %s: group=%d pwm=%d offline=%s name=%r (source=%s)",
            label, gid, pwm, is_offline, name, src,
        )

    if groups:
        _LOGGER.info(
            "[discovery] Strategy %s succeeded: %d group(s) — %s",
            label, len(groups), {gid: g.name for gid, g in sorted(groups.items())},
        )
    else:
        _LOGGER.debug("[discovery] Strategy %s: 0 matches", label)

    return groups


# ── Public API ────────────────────────────────────────────────────────────────


def parse_groups(html: str) -> dict[int, NewlabGroup]:
    """Parse the /registrationhome HTML and return all discovered light groups.

    Tries four parser strategies in order (A → B → C → D). Stops at the first
    one that finds at least one group. All attempts are logged at DEBUG level.

    Raises:
        NewlabParseError: if all strategies fail to find any group.
    """
    _LOGGER.debug("[discovery] HTML response: %d chars total", len(html))
    _LOGGER.debug(
        "[discovery] HTML excerpt (first %d chars):\n%s",
        DEBUG_HTML_MAX_CHARS,
        html[:DEBUG_HTML_MAX_CHARS],
    )

    label_map = _extract_labels(html)

    # Strategy A — id="range_N"
    groups = _run_strategy("A", "A_input_id", _RE_A, html, label_map)
    if groups:
        return groups

    # Strategy B — name="range_N"
    groups = _run_strategy("B", "B_input_name", _RE_B, html, label_map)
    if groups:
        return groups

    # Strategy C — data-group / data-id
    groups = _run_strategy("C", "C_data_attr", _RE_C, html, label_map)
    if groups:
        return groups

    # Strategy D — broad fallback
    groups = _run_strategy("D", "D_broad", _RE_D, html, label_map, broad=True)
    if groups:
        return groups

    # All strategies failed
    _LOGGER.error(
        "[discovery] ALL strategies failed. HTML length=%d. Excerpt:\n%s\n"
        "Please open a GitHub issue and attach this log excerpt.",
        len(html),
        html[:DEBUG_HTML_MAX_CHARS],
    )
    raise NewlabParseError(
        f"No light groups found in HTML ({len(html)} chars). "
        "All four parser strategies (A/B/C/D) returned 0 results."
    )


def parse_system_info(html: str) -> NewlabSystemInfo:
    """Extract system-level info from the /registrationhome HTML.

    Extracts (best-effort, never raises):
      - plant_code      via _RE_PLANT_CODE_PATTERNS (first match wins)
      - cloud_last_sync via _RE_CLOUD_LAST_SYNC
      - cloud_version   via _RE_CLOUD_VERSION
    """
    info = NewlabSystemInfo()

    # Plant code
    for i, pattern in enumerate(_RE_PLANT_CODE_PATTERNS, 1):
        m = pattern.search(html)
        if m:
            info.plant_code = m.group(1).strip()
            _LOGGER.debug("[discovery] plant_code: pattern %d matched → %r", i, info.plant_code)
            break
    if not info.plant_code:
        _LOGGER.warning(
            "[discovery] plant_code: all %d patterns found nothing",
            len(_RE_PLANT_CODE_PATTERNS),
        )

    # Cloud last sync
    m = _RE_CLOUD_LAST_SYNC.search(html)
    if m:
        info.cloud_last_sync = m.group(1).strip()
        _LOGGER.debug("[discovery] cloud_last_sync: %r", info.cloud_last_sync)
    else:
        _LOGGER.warning("[discovery] cloud_last_sync: not found in HTML")

    # Cloud version
    m = _RE_CLOUD_VERSION.search(html)
    if m:
        info.cloud_version = m.group(1).strip()
        _LOGGER.debug("[discovery] cloud_version: %r", info.cloud_version)
    else:
        _LOGGER.debug("[discovery] cloud_version: not found in HTML")

    return info
