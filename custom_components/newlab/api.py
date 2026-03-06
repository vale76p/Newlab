"""Compatibility facade for the Newlab API package.

Public imports are kept stable for the rest of the integration and tests.
"""

from .client import NewlabAPI
from .models import (
    NewlabAuthError,
    NewlabConnectionError,
    NewlabGroup,
    NewlabParseError,
    NewlabSystemInfo,
)
from .parsers import _parse_groups, _parse_system_info

__all__ = [
    "NewlabAPI",
    "NewlabAuthError",
    "NewlabConnectionError",
    "NewlabGroup",
    "NewlabParseError",
    "NewlabSystemInfo",
    "_parse_groups",
    "_parse_system_info",
]
