"""Data models and domain exceptions for the Newlab integration."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class NewlabGroup:
    """Represents a single Newlab light group (zone)."""

    id_group: int
    name: str
    pwm: int = 0
    is_offline: bool = False
    name_source: str = "fallback"
    parser_strategy: str = "unknown"

    @property
    def is_on(self) -> bool:
        return self.pwm > 0

    @property
    def brightness(self) -> int:
        return self.pwm


@dataclass
class NewlabSystemInfo:
    """System-level information extracted from the cloud home page."""

    plant_code: str = ""
    cloud_last_sync: str = ""
    cloud_version: str = ""


class NewlabAuthError(Exception):
    """Raised when credentials are invalid or session expired."""


class NewlabConnectionError(Exception):
    """Raised on network / HTTP-level errors."""


class NewlabParseError(Exception):
    """Raised when HTML parsing fails."""
