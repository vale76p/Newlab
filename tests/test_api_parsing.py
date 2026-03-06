"""Unit tests for HTML parsing logic in custom_components.newlab.parsers."""

from __future__ import annotations

import importlib

import pytest

parsers = importlib.import_module("custom_components.newlab.parsers")
models = importlib.import_module("custom_components.newlab.models")


# ── Strategy A + L1 label ────────────────────────────────────────────────────


def test_parse_groups_strategy_a_and_l1_label() -> None:
    html = """
    <html>
      <body>
        <label for="range_3">Cucina</label>
        <input id="range_3" type="range" value="255" />
      </body>
    </html>
    """
    groups = parsers.parse_groups(html)

    assert set(groups) == {3}
    assert groups[3].name == "Cucina"
    assert groups[3].pwm == 255
    assert groups[3].parser_strategy == "A_input_id"
    assert groups[3].name_source == "html_label"
    assert groups[3].is_offline is False


# ── Strategy B + L2 aria-label ───────────────────────────────────────────────


def test_parse_groups_strategy_b_name_and_aria_label() -> None:
    html = """
    <html>
      <body>
        <input name="range_7" aria-label="Soggiorno" value="120" />
      </body>
    </html>
    """
    groups = parsers.parse_groups(html)

    assert set(groups) == {7}
    assert groups[7].name == "Soggiorno"
    assert groups[7].pwm == 120
    assert groups[7].parser_strategy == "B_input_name"
    assert groups[7].name_source == "aria_label"


# ── Strategy C + L3 title ────────────────────────────────────────────────────


def test_parse_groups_strategy_c_data_group() -> None:
    html = """
    <html>
      <body>
        <input type="range" data-group="4" value="200" title="Corridoio" />
      </body>
    </html>
    """
    groups = parsers.parse_groups(html)

    assert set(groups) == {4}
    assert groups[4].name == "Corridoio"
    assert groups[4].pwm == 200
    assert groups[4].parser_strategy == "C_data_attr"
    assert groups[4].name_source == "title"


# ── Strategy D + broad pattern ───────────────────────────────────────────────


def test_parse_groups_strategy_d_broad_fallback() -> None:
    html = """
    <html>
      <body>
        <div>range_5 something value="77"</div>
      </body>
    </html>
    """
    groups = parsers.parse_groups(html)

    assert set(groups) == {5}
    assert groups[5].pwm == 77
    assert groups[5].parser_strategy == "D_broad"
    assert groups[5].name == "Group 5"
    assert groups[5].name_source == "fallback"


# ── L4 (td_text) — production layout ────────────────────────────────────────


def test_parse_groups_l4_td_text_label() -> None:
    """L4 strategy: name from the closest preceding <td> element."""
    html = """
    <html>
      <body>
        <table>
          <tr>
            <td>Led Cucina</td>
            <td><input id="range_3" value="128" /></td>
          </tr>
        </table>
      </body>
    </html>
    """
    groups = parsers.parse_groups(html)

    assert groups[3].name == "Led Cucina"
    assert groups[3].name_source == "td_text"
    assert groups[3].pwm == 128


# ── Offline detection ────────────────────────────────────────────────────────


def test_parse_groups_offline_detection() -> None:
    html = """
    <html>
      <body>
        <label for="range_2">Bagno</label>
        <input id="range_2" class="slider offline" value="33" />
      </body>
    </html>
    """
    groups = parsers.parse_groups(html)

    assert groups[2].is_offline is True


# ── Fallback name ────────────────────────────────────────────────────────────


def test_parse_groups_fallback_name_without_label() -> None:
    html = """
    <html>
      <body>
        <input id="range_9" value="1" />
      </body>
    </html>
    """
    groups = parsers.parse_groups(html)

    assert groups[9].name == "Group 9"
    assert groups[9].name_source == "fallback"


# ── All strategies fail → NewlabParseError ───────────────────────────────────


def test_parse_groups_raises_on_empty_html() -> None:
    html = "<html><body><p>No groups here</p></body></html>"
    with pytest.raises(models.NewlabParseError, match="No light groups found"):
        parsers.parse_groups(html)


# ── System info — English labels ─────────────────────────────────────────────


def test_parse_system_info_english_labels() -> None:
    html = """
    <html>
      <head><title>Newlab Smart Home - Ver. 3.47</title></head>
      <body>
        <p>Plant Id: <b>plant_code_example_001</b></p>
        <p>Last syncronization: <b>Feb. 16, 2026, 7:01 p.m.</b></p>
      </body>
    </html>
    """
    info = parsers.parse_system_info(html)

    assert info.plant_code == "plant_code_example_001"
    assert info.cloud_last_sync == "Feb. 16, 2026, 7:01 p.m."
    assert info.cloud_version == "3.47"


# ── System info — Italian labels ─────────────────────────────────────────────


def test_parse_system_info_italian_labels() -> None:
    html = """
    <html>
      <head><title>Newlab Smart Home - Ver. 3.48</title></head>
      <body>
        <p>Codice Impianto: <strong>plant_code_example_002</strong></p>
        <p>Ultima sincronizzazione: <b>Lunedì 16 Febbraio 2026 19:01</b></p>
      </body>
    </html>
    """
    info = parsers.parse_system_info(html)

    assert info.plant_code == "plant_code_example_002"
    assert info.cloud_last_sync == "Lunedì 16 Febbraio 2026 19:01"
    assert info.cloud_version == "3.48"


# ── System info — partial (only version) ─────────────────────────────────────


def test_parse_system_info_partial_data() -> None:
    html = """
    <html>
      <head><title>Newlab Smart Home - Ver. 4.00</title></head>
      <body><p>Nothing relevant here</p></body>
    </html>
    """
    info = parsers.parse_system_info(html)

    assert info.plant_code == ""
    assert info.cloud_last_sync == ""
    assert info.cloud_version == "4.00"


# ── System info — completely empty ───────────────────────────────────────────


def test_parse_system_info_empty_html() -> None:
    html = "<html><body></body></html>"
    info = parsers.parse_system_info(html)

    assert info.plant_code == ""
    assert info.cloud_last_sync == ""
    assert info.cloud_version == ""
