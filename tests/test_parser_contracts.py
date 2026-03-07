"""Contract tests for parsers.py using versioned HTML fixtures.

These tests use real-world HTML fixture files to validate that the parser
strategies work correctly and remain stable against HTML structure changes.
Fixtures are stored in tests/fixtures/ and versioned with the repository.
"""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest

parsers_module = importlib.import_module("custom_components.newlab.parsers")
models_module = importlib.import_module("custom_components.newlab.models")

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load(filename: str) -> str:
    return (FIXTURES_DIR / filename).read_text(encoding="utf-8")


# ── Strategy A — English ──────────────────────────────────────────────────────

class TestStrategyAEnglish:
    def test_discovers_three_groups(self):
        groups = parsers_module.parse_groups(_load("home_strategy_a_en.html"))
        assert len(groups) == 3

    def test_group_1_name_and_pwm(self):
        groups = parsers_module.parse_groups(_load("home_strategy_a_en.html"))
        assert groups[1].name == "Living Room"
        assert groups[1].pwm == 200
        assert groups[1].is_on is True

    def test_group_2_is_off(self):
        groups = parsers_module.parse_groups(_load("home_strategy_a_en.html"))
        assert groups[2].name == "Kitchen"
        assert groups[2].pwm == 0
        assert groups[2].is_on is False

    def test_group_3_is_offline(self):
        groups = parsers_module.parse_groups(_load("home_strategy_a_en.html"))
        assert groups[3].name == "Bedroom"
        assert groups[3].is_offline is True
        assert groups[3].pwm == 100

    def test_parser_strategy_is_A(self):
        groups = parsers_module.parse_groups(_load("home_strategy_a_en.html"))
        assert groups[1].parser_strategy == "A_input_id"

    def test_name_source_is_html_label(self):
        groups = parsers_module.parse_groups(_load("home_strategy_a_en.html"))
        assert groups[1].name_source == "html_label"

    def test_system_info_plant_code_en(self):
        info = parsers_module.parse_system_info(_load("home_strategy_a_en.html"))
        assert info.plant_code == "PLANT-EN-001"

    def test_system_info_last_sync_en(self):
        info = parsers_module.parse_system_info(_load("home_strategy_a_en.html"))
        assert "2026" in info.cloud_last_sync
        assert "7:01" in info.cloud_last_sync

    def test_system_info_cloud_version(self):
        info = parsers_module.parse_system_info(_load("home_strategy_a_en.html"))
        assert info.cloud_version == "3.47"


# ── Strategy A — Italian ──────────────────────────────────────────────────────

class TestStrategyAItalian:
    def test_discovers_two_groups(self):
        groups = parsers_module.parse_groups(_load("home_strategy_a_it.html"))
        assert len(groups) == 2

    def test_italian_group_names(self):
        groups = parsers_module.parse_groups(_load("home_strategy_a_it.html"))
        assert groups[1].name == "Soggiorno"
        assert groups[2].name == "Cucina"

    def test_group_1_pwm(self):
        groups = parsers_module.parse_groups(_load("home_strategy_a_it.html"))
        assert groups[1].pwm == 150

    def test_system_info_plant_code_it(self):
        info = parsers_module.parse_system_info(_load("home_strategy_a_it.html"))
        assert info.plant_code == "IMPIANTO-IT-002"

    def test_system_info_last_sync_it(self):
        info = parsers_module.parse_system_info(_load("home_strategy_a_it.html"))
        assert info.cloud_last_sync != ""
        assert "2026" in info.cloud_last_sync


# ── Strategy B ────────────────────────────────────────────────────────────────

class TestStrategyB:
    def test_discovers_two_groups(self):
        groups = parsers_module.parse_groups(_load("home_strategy_b.html"))
        assert len(groups) == 2

    def test_parser_strategy_is_B(self):
        groups = parsers_module.parse_groups(_load("home_strategy_b.html"))
        assert groups[5].parser_strategy == "B_input_name"
        assert groups[6].parser_strategy == "B_input_name"

    def test_group_names_from_labels(self):
        groups = parsers_module.parse_groups(_load("home_strategy_b.html"))
        assert groups[5].name == "Hallway"
        assert groups[6].name == "Bathroom"

    def test_pwm_values(self):
        groups = parsers_module.parse_groups(_load("home_strategy_b.html"))
        assert groups[5].pwm == 128
        assert groups[6].pwm == 255

    def test_system_info_plant_code(self):
        info = parsers_module.parse_system_info(_load("home_strategy_b.html"))
        assert info.plant_code == "PLANT-B-003"


# ── Strategy C ────────────────────────────────────────────────────────────────

class TestStrategyC:
    def test_discovers_two_groups(self):
        groups = parsers_module.parse_groups(_load("home_strategy_c.html"))
        assert len(groups) == 2

    def test_parser_strategy_is_C(self):
        groups = parsers_module.parse_groups(_load("home_strategy_c.html"))
        assert groups[10].parser_strategy == "C_data_attr"
        assert groups[11].parser_strategy == "C_data_attr"

    def test_names_from_td_cells(self):
        groups = parsers_module.parse_groups(_load("home_strategy_c.html"))
        assert groups[10].name == "Studio"
        assert groups[11].name == "Garage"

    def test_pwm_values(self):
        groups = parsers_module.parse_groups(_load("home_strategy_c.html"))
        assert groups[10].pwm == 80
        assert groups[11].pwm == 0

    def test_system_info_plant_code(self):
        info = parsers_module.parse_system_info(_load("home_strategy_c.html"))
        assert info.plant_code == "PLANT-C-004"


# ── Strategy D ────────────────────────────────────────────────────────────────

class TestStrategyD:
    def test_discovers_two_groups(self):
        groups = parsers_module.parse_groups(_load("home_strategy_d.html"))
        assert len(groups) == 2

    def test_parser_strategy_is_D(self):
        groups = parsers_module.parse_groups(_load("home_strategy_d.html"))
        assert groups[7].parser_strategy == "D_broad"
        assert groups[8].parser_strategy == "D_broad"

    def test_fallback_names(self):
        groups = parsers_module.parse_groups(_load("home_strategy_d.html"))
        assert groups[7].name == "Group 7"
        assert groups[8].name == "Group 8"
        assert groups[7].name_source == "fallback"

    def test_pwm_values(self):
        groups = parsers_module.parse_groups(_load("home_strategy_d.html"))
        assert groups[7].pwm == 60
        assert groups[8].pwm == 0


# ── Offline detection ─────────────────────────────────────────────────────────

class TestOfflineDetection:
    def test_offline_groups_marked(self):
        groups = parsers_module.parse_groups(_load("home_all_offline.html"))
        assert groups[1].is_offline is True
        assert groups[2].is_offline is True

    def test_online_group_not_marked(self):
        groups = parsers_module.parse_groups(_load("home_strategy_a_en.html"))
        assert groups[1].is_offline is False
        assert groups[2].is_offline is False

    def test_offline_pwm_preserved(self):
        groups = parsers_module.parse_groups(_load("home_all_offline.html"))
        assert groups[1].pwm == 200
        assert groups[2].pwm == 100


# ── Parse error ───────────────────────────────────────────────────────────────

class TestParseError:
    def test_raises_on_no_groups(self):
        with pytest.raises(models_module.NewlabParseError):
            parsers_module.parse_groups(_load("home_no_groups.html"))

    def test_raises_with_informative_message(self):
        with pytest.raises(models_module.NewlabParseError, match="No light groups found"):
            parsers_module.parse_groups(_load("home_no_groups.html"))


# ── Partial system info ───────────────────────────────────────────────────────

class TestPartialSystemInfo:
    def test_version_only(self):
        info = parsers_module.parse_system_info(_load("home_partial_sysinfo.html"))
        assert info.cloud_version == "5.00"
        assert info.plant_code == ""
        assert info.cloud_last_sync == ""

    def test_groups_still_parsed_with_partial_sysinfo(self):
        groups = parsers_module.parse_groups(_load("home_partial_sysinfo.html"))
        assert len(groups) == 1
        assert groups[1].name == "Light"


# ── Label resolution fallbacks ────────────────────────────────────────────────

class TestLabelFallbacks:
    def test_L2_aria_label(self):
        groups = parsers_module.parse_groups(_load("home_label_fallbacks.html"))
        assert groups[1].name == "Aria Light"
        assert groups[1].name_source == "aria_label"

    def test_L3_title(self):
        groups = parsers_module.parse_groups(_load("home_label_fallbacks.html"))
        assert groups[2].name == "Title Light"
        assert groups[2].name_source == "title"

    def test_L4_td_text(self):
        groups = parsers_module.parse_groups(_load("home_label_fallbacks.html"))
        assert groups[3].name == "Cell Light"
        assert groups[3].name_source == "td_text"

    def test_fallback_name(self):
        groups = parsers_module.parse_groups(_load("home_label_fallbacks.html"))
        assert groups[4].name == "Group 4"
        assert groups[4].name_source == "fallback"

    def test_all_four_groups_discovered(self):
        groups = parsers_module.parse_groups(_load("home_label_fallbacks.html"))
        assert len(groups) == 4
