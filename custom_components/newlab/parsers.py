"""HTML parsing utilities for Newlab cloud pages."""

from __future__ import annotations

import logging
import re

from .const import DEBUG_HTML_MAX_CHARS, GROUP_NAME_FALLBACK
from .models import NewlabGroup, NewlabParseError, NewlabSystemInfo

_LOGGER = logging.getLogger(__name__)

_RE_A = re.compile(r'<input[^>]+id=["\']range_(\d+)["\'][^>]*>', re.IGNORECASE)
_RE_B = re.compile(r'<input[^>]+name=["\']range_(\d+)["\'][^>]*>', re.IGNORECASE)
_RE_C = re.compile(r'<input[^>]+data-(?:group|id)=["\'](\d+)["\'][^>]*>', re.IGNORECASE)
_RE_D = re.compile(r'range_(\d+)[^"\'<]{0,100}value=["\'](\d+)["\']', re.IGNORECASE)
_RE_VALUE = re.compile(r'value=["\'](\d+)["\']', re.IGNORECASE)

_RE_L1 = re.compile(
    r'<label[^>]+for=["\']range_(\d+)["\'][^>]*>\s*([^<]{1,80}?)\s*</label>',
    re.IGNORECASE,
)
_RE_L2_ARIA = re.compile(r'aria-label=["\']([^"\']{1,80})["\']', re.IGNORECASE)
_RE_L3_TITLE = re.compile(r'\btitle=["\']([^"\']{1,80})["\']', re.IGNORECASE)
_RE_L4_CELL = re.compile(
    r'<(?:td|th|span)[^>]*>\s*([^<]{1,80}?)\s*</(?:td|th|span)>',
    re.IGNORECASE,
)

_RE_OFFLINE_CLASS = re.compile(r'class=["\'][^"\']*\boffline\b', re.IGNORECASE)

_RE_CLOUD_LAST_SYNC = re.compile(
    r'(?:Last\s+sync(?:h?ronization)|Ultima\s+sincronizzazione)\b'
    r'.{0,60}?<(?:b|strong)[^>]*>\s*([^<]{4,80}?)\s*</(?:b|strong)>',
    re.IGNORECASE | re.DOTALL,
)
_RE_CLOUD_VERSION = re.compile(r'Ver\.\s*([\d.]+)', re.IGNORECASE)

_RE_PLANT_CODE_PATTERNS: list[re.Pattern] = [
    re.compile(
        r'(?:Plant\s+Id|Codice\s+Impianto)\b'
        r'.{0,60}?<(?:b|strong)[^>]*>\s*([^<]{3,80}?)\s*</(?:b|strong)>',
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r'var\s+(?:plant|impianto)(?:_?(?:id|code|Id|Code))?\s*=\s*["\']([A-Za-z0-9_\-]{3,})["\']',
        re.IGNORECASE,
    ),
    re.compile(
        r'<input[^>]+(?:name|id)=["\'][A-Za-z_]*(?:plant|impianto)[A-Za-z_]*["\'][^>]*value=["\']([A-Za-z0-9_\-]{3,})["\']',
        re.IGNORECASE,
    ),
    re.compile(
        r'data-(?:plant[-_]?(?:id|code)|impianto[-_]?(?:id|codice))=["\']([A-Za-z0-9_\-]{3,})["\']',
        re.IGNORECASE,
    ),
]


def _extract_labels(html: str) -> dict[int, tuple[str, str]]:
    labels: dict[int, tuple[str, str]] = {}
    for m in _RE_L1.finditer(html):
        gid = int(m.group(1))
        text = m.group(2).strip()
        if text:
            labels[gid] = (text, "html_label")
    return labels


def _name_from_tag(
    tag_html: str,
    gid: int,
    html: str,
    match_pos: int,
    label_map: dict[int, tuple[str, str]],
) -> tuple[str, str]:
    if gid in label_map:
        return label_map[gid]

    m = _RE_L2_ARIA.search(tag_html)
    if m:
        return m.group(1).strip(), "aria_label"

    m = _RE_L3_TITLE.search(tag_html)
    if m:
        return m.group(1).strip(), "title"

    window_start = max(0, match_pos - 400)
    cells = _RE_L4_CELL.findall(html[window_start:match_pos])
    if cells:
        return cells[-1].strip(), "td_text"

    return GROUP_NAME_FALLBACK.format(gid=gid), "fallback"


def _parse_groups(html: str) -> dict[int, NewlabGroup]:
    _LOGGER.debug("[discovery] HTML response: %d chars total", len(html))
    _LOGGER.debug(
        "[discovery] HTML excerpt (first %d chars):\n%s",
        DEBUG_HTML_MAX_CHARS,
        html[:DEBUG_HTML_MAX_CHARS],
    )

    label_map = _extract_labels(html)
    groups: dict[int, NewlabGroup] = {}

    for m in _RE_A.finditer(html):
        gid = int(m.group(1))
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
            parser_strategy="A_input_id",
        )
    if groups:
        return groups

    for m in _RE_B.finditer(html):
        gid = int(m.group(1))
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
            parser_strategy="B_input_name",
        )
    if groups:
        return groups

    for m in _RE_C.finditer(html):
        gid = int(m.group(1))
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
            parser_strategy="C_data_attr",
        )
    if groups:
        return groups

    for m in _RE_D.finditer(html):
        gid = int(m.group(1))
        pwm = int(m.group(2))
        name, src = _name_from_tag("", gid, html, m.start(), label_map)
        groups[gid] = NewlabGroup(
            id_group=gid,
            name=name,
            pwm=pwm,
            name_source=src,
            parser_strategy="D_broad",
        )
    if groups:
        return groups

    raise NewlabParseError(
        f"No light groups found in HTML ({len(html)} chars). "
        "All four parser strategies (A/B/C/D) returned 0 results."
    )


def _parse_system_info(html: str) -> NewlabSystemInfo:
    info = NewlabSystemInfo()

    for pattern in _RE_PLANT_CODE_PATTERNS:
        m = pattern.search(html)
        if m:
            info.plant_code = m.group(1).strip()
            break

    m = _RE_CLOUD_LAST_SYNC.search(html)
    if m:
        info.cloud_last_sync = m.group(1).strip()

    m = _RE_CLOUD_VERSION.search(html)
    if m:
        info.cloud_version = m.group(1).strip()

    return info
