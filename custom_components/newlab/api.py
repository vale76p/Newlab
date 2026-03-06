"""Public facade for the Newlab API layer.

All imports used by the rest of the integration (coordinator, entities,
config_flow) go through this module so internal refactors don't break callers.
"""

from .client import NewlabAPI
from .models import (
    NewlabAuthError,
    NewlabConnectionError,
    NewlabGroup,
    NewlabParseError,
    NewlabSystemInfo,
)
from .parsers import parse_groups, parse_system_info

__all__ = [
    "NewlabAPI",
    "NewlabAuthError",
    "NewlabConnectionError",
    "NewlabGroup",
    "NewlabParseError",
    "NewlabSystemInfo",
    "parse_groups",
    "parse_system_info",
]
