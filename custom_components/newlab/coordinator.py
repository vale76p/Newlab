"""DataUpdateCoordinator for the Newlab LED integration.

A single coordinator instance per config entry polls the Newlab cloud and
distributes the result to all NewlabLight entities via coordinator.data.

Re-authentication
-----------------
If get_groups() raises NewlabAuthError (session expired), the coordinator
calls api.login() once and retries. A second failure raises UpdateFailed
so HA marks all entities unavailable and retries on the next interval.

Debug
-----
Enable verbose logging in HA configuration.yaml:
  logger:
    logs:
      custom_components.newlab: debug
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import NewlabAPI, NewlabAuthError, NewlabConnectionError, NewlabGroup, NewlabParseError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# ── Italian datetime formatter ─────────────────────────────────────────────────

_ITALIAN_MONTHS = [
    "", "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
    "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre",
]
_ITALIAN_WEEKDAYS = [
    "Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica",
]


def _format_italian_datetime(dt: datetime) -> str:
    """Format a datetime as Italian long form.

    Example: 'Lunedì 16 Febbraio 2026 19:01'
    Uses the HA-aware datetime (already in the configured local timezone).
    """
    return (
        f"{_ITALIAN_WEEKDAYS[dt.weekday()]} "
        f"{dt.day} "
        f"{_ITALIAN_MONTHS[dt.month]} "
        f"{dt.year} "
        f"{dt.hour:02d}:{dt.minute:02d}"
    )


# ── Coordinator ────────────────────────────────────────────────────────────────

class NewlabCoordinator(DataUpdateCoordinator[dict[int, NewlabGroup]]):
    """Coordinator that polls /registrationhome every N seconds.

    Public attributes (readable by entities):
        coordinator.data              — dict[int, NewlabGroup] keyed by id_group
        coordinator.plant_code        — Codice Impianto (empty string if unknown)
        coordinator.cloud_last_sync   — Last sync timestamp from Newlab cloud HTML
        coordinator.cloud_version     — Firmware/app version from Newlab cloud (e.g. "3.47")
        coordinator.last_sync_formatted — Italian-formatted HA polling timestamp
    """

    def __init__(
        self,
        hass: HomeAssistant,
        api: NewlabAPI,
        poll_interval: int,
    ) -> None:
        self.api = api
        self._poll_count = 0
        self.plant_code: str = ""
        self.cloud_last_sync: str = ""
        self.cloud_version: str = ""
        self.last_sync_time: datetime | None = None
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=poll_interval),
        )
        _LOGGER.debug(
            "[coordinator] initialized — poll_interval=%ds",
            poll_interval,
        )

    @property
    def last_sync_formatted(self) -> str:
        """Last successful sync in Italian long format, or '—' if never synced."""
        if self.last_sync_time is None:
            return "—"
        return _format_italian_datetime(self.last_sync_time)

    async def _async_update_data(self) -> dict[int, NewlabGroup]:
        """Fetch latest light state from the Newlab cloud.

        Handles session expiry transparently with a single re-login attempt.
        Updates last_sync_time on every successful poll.
        System info (plant_code, cloud_version, cloud_last_sync) is fetched only once.
        """
        self._poll_count += 1
        t0 = time.monotonic()
        _LOGGER.debug("[coordinator] poll #%d starting", self._poll_count)

        try:
            groups = await self.api.get_groups()
            self._on_success(groups)
            elapsed = time.monotonic() - t0
            _LOGGER.debug(
                "[coordinator] poll #%d OK — %d group(s) in %.2fs — states: %s",
                self._poll_count,
                len(groups),
                elapsed,
                {gid: ("on" if g.is_on else "off") + f"/{g.pwm}" for gid, g in sorted(groups.items())},
            )
            return groups

        except NewlabAuthError as exc:
            elapsed = time.monotonic() - t0
            _LOGGER.info(
                "[coordinator] poll #%d — session expired after %.2fs (%s), re-authenticating…",
                self._poll_count, elapsed, exc,
            )
            try:
                await self.api.login()
                groups = await self.api.get_groups()
                self._on_success(groups)
                elapsed = time.monotonic() - t0
                _LOGGER.info(
                    "[coordinator] poll #%d — re-auth + retry OK — %d group(s) in %.2fs total",
                    self._poll_count, len(groups), elapsed,
                )
                return groups
            except (NewlabAuthError, NewlabConnectionError, NewlabParseError) as exc2:
                elapsed = time.monotonic() - t0
                _LOGGER.error(
                    "[coordinator] poll #%d — re-auth FAILED after %.2fs: %s",
                    self._poll_count, elapsed, exc2,
                )
                raise UpdateFailed(f"Re-authentication failed: {exc2}") from exc2

        except NewlabConnectionError as exc:
            elapsed = time.monotonic() - t0
            _LOGGER.warning(
                "[coordinator] poll #%d — connection error after %.2fs: %s",
                self._poll_count, elapsed, exc,
            )
            raise UpdateFailed(f"Connection error: {exc}") from exc

        except NewlabParseError as exc:
            elapsed = time.monotonic() - t0
            _LOGGER.error(
                "[coordinator] poll #%d — HTML parse error after %.2fs: %s",
                self._poll_count, elapsed, exc,
            )
            raise UpdateFailed(f"HTML parse error: {exc}") from exc

    def _on_success(self, groups: dict[int, NewlabGroup]) -> None:
        """Update cached metadata after a successful poll.

        System info (plant_code, cloud_version, cloud_last_sync) is extracted
        only once by the API client; here we just copy whatever was found.
        """
        self.last_sync_time = dt_util.now()  # HA local timezone
        info = self.api.system_info

        # Copy system info from API (only changes on first successful extraction)
        if info.plant_code and not self.plant_code:
            self.plant_code = info.plant_code
            _LOGGER.info("[coordinator] codice_impianto: %r", self.plant_code)
        if info.cloud_version and not self.cloud_version:
            self.cloud_version = info.cloud_version
            _LOGGER.info("[coordinator] cloud_version: %r", self.cloud_version)
        if info.cloud_last_sync and not self.cloud_last_sync:
            self.cloud_last_sync = info.cloud_last_sync
            _LOGGER.info("[coordinator] cloud_last_sync: %r", self.cloud_last_sync)
