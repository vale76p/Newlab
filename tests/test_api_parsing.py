"""Unit tests for HTML parsing logic in custom_components.newlab.api."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType


def _load_api_module():
    """Load api.py without importing custom_components.newlab.__init__."""
    repo_root = Path(__file__).resolve().parents[1]
    custom_components_dir = repo_root / "custom_components"
    newlab_dir = custom_components_dir / "newlab"

    custom_components_pkg = ModuleType("custom_components")
    custom_components_pkg.__path__ = [str(custom_components_dir)]
    sys.modules.setdefault("custom_components", custom_components_pkg)

    newlab_pkg = ModuleType("custom_components.newlab")
    newlab_pkg.__path__ = [str(newlab_dir)]
    sys.modules.setdefault("custom_components.newlab", newlab_pkg)

    return importlib.import_module("custom_components.newlab.api")


api = _load_api_module()


def test_parse_groups_strategy_a_and_l1_label() -> None:
    html = """
    <html>
      <body>
        <label for="range_3">Cucina</label>
        <input id="range_3" type="range" value="255" />
      </body>
    </html>
    """

    groups = api._parse_groups(html)

    assert set(groups) == {3}
    assert groups[3].name == "Cucina"
    assert groups[3].pwm == 255
    assert groups[3].parser_strategy == "A_input_id"
    assert groups[3].name_source == "html_label"
    assert groups[3].is_offline is False


def test_parse_groups_strategy_b_name_and_aria_label() -> None:
    html = """
    <html>
      <body>
        <input name="range_7" aria-label="Soggiorno" value="120" />
      </body>
    </html>
    """

    groups = api._parse_groups(html)

    assert set(groups) == {7}
    assert groups[7].name == "Soggiorno"
    assert groups[7].pwm == 120
    assert groups[7].parser_strategy == "B_input_name"
    assert groups[7].name_source == "aria_label"


def test_parse_groups_offline_detection() -> None:
    html = """
    <html>
      <body>
        <label for="range_2">Bagno</label>
        <input id="range_2" class="slider offline" value="33" />
      </body>
    </html>
    """

    groups = api._parse_groups(html)

    assert groups[2].is_offline is True


def test_parse_groups_fallback_name_without_label() -> None:
    html = """
    <html>
      <body>
        <input id="range_9" value="1" />
      </body>
    </html>
    """

    groups = api._parse_groups(html)

    assert groups[9].name == "Group 9"
    assert groups[9].name_source == "fallback"


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

    info = api._parse_system_info(html)

    assert info.plant_code == "plant_code_example_001"
    assert info.cloud_last_sync == "Feb. 16, 2026, 7:01 p.m."
    assert info.cloud_version == "3.47"


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

    info = api._parse_system_info(html)

    assert info.plant_code == "plant_code_example_002"
    assert info.cloud_last_sync == "Lunedì 16 Febbraio 2026 19:01"
    assert info.cloud_version == "3.48"
