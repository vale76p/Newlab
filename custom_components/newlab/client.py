"""HTTP client for authentication, polling and control commands."""

from __future__ import annotations

import logging
import re
import time

import aiohttp

from .const import (
    CONNECT_TIMEOUT,
    CONTROL_URL,
    DEFAULT_HEADERS,
    HOME_URL,
    LOGIN_URL,
    READ_TIMEOUT,
    REFRESH_URL,
    WELCOME_URL,
)
from .models import (
    NewlabAuthError,
    NewlabConnectionError,
    NewlabGroup,
    NewlabParseError,
    NewlabSystemInfo,
)
from .parsers import parse_groups, parse_system_info

_LOGGER = logging.getLogger(__name__)

_RE_CSRF = re.compile(
    r'name=["\']csrfmiddlewaretoken["\'] value=["\']([^"\']+)["\']',
    re.IGNORECASE,
)


class NewlabAPI:
    """Async client for the Newlab LED cloud."""

    def __init__(
        self,
        username: str,
        password: str,
        session: aiohttp.ClientSession,
    ) -> None:
        self._username = username
        self._password = password
        self._session = session
        self._csrf_token: str | None = None
        self._session_id: str | None = None
        self.system_info: NewlabSystemInfo = NewlabSystemInfo()
        self._system_info_fetched = False

    @property
    def is_authenticated(self) -> bool:
        return bool(self._csrf_token and self._session_id)

    @property
    def cookie_header(self) -> str:
        if self._csrf_token and self._session_id:
            return f"csrftoken={self._csrf_token}; sessionid={self._session_id}"
        return ""

    async def login(self) -> None:
        timeout = aiohttp.ClientTimeout(connect=CONNECT_TIMEOUT, sock_read=READ_TIMEOUT)
        jar = aiohttp.CookieJar(unsafe=True)

        async with aiohttp.ClientSession(
            cookie_jar=jar,
            timeout=timeout,
            headers=DEFAULT_HEADERS,
        ) as tmp:
            try:
                async with tmp.get(WELCOME_URL) as resp:
                    if resp.status != 200:
                        raise NewlabConnectionError(
                            f"GET {WELCOME_URL} returned HTTP {resp.status} (expected 200)"
                        )
                    html = await resp.text()
            except aiohttp.ClientError as exc:
                raise NewlabConnectionError(f"GET welcome failed: {exc}") from exc

            m = _RE_CSRF.search(html)
            if not m:
                raise NewlabParseError("csrfmiddlewaretoken not found in welcome page HTML")
            csrf_middleware = m.group(1)

            login_data = {
                "csrfmiddlewaretoken": csrf_middleware,
                "username": self._username,
                "password": self._password,
                "next": "",
            }
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
                    allow_redirects=True,
                ) as resp:
                    final_url = str(resp.url).lower()
                    if any(kw in final_url for kw in ("login", "welcome", "register")):
                        raise NewlabAuthError("Login redirected to authentication page")
                    if resp.status != 200:
                        raise NewlabAuthError(
                            f"POST login + redirect returned HTTP {resp.status}"
                        )
            except aiohttp.ClientError as exc:
                raise NewlabConnectionError(f"POST login failed: {exc}") from exc

            cookies = {c.key: c.value for c in jar}
            csrf = cookies.get("csrftoken")
            sessionid = cookies.get("sessionid")
            if not csrf or not sessionid:
                raise NewlabAuthError("Session cookies missing after login")

            self._csrf_token = csrf
            self._session_id = sessionid

    async def get_groups(self) -> dict[int, NewlabGroup]:
        if not self.is_authenticated:
            raise NewlabAuthError("Not authenticated — call login() first.")

        t0 = time.monotonic()
        headers = {**DEFAULT_HEADERS, "Cookie": self.cookie_header}
        try:
            async with self._session.get(HOME_URL, headers=headers) as resp:
                if resp.status == 302:
                    raise NewlabAuthError("Session expired (HTTP 302 redirect)")
                if resp.status != 200:
                    raise NewlabConnectionError(f"GET {HOME_URL} returned HTTP {resp.status}")

                final_url = str(resp.url).lower()
                if "login" in final_url and HOME_URL.lower() not in final_url:
                    raise NewlabAuthError("Session expired (redirected to login)")

                html = await resp.text()
        except aiohttp.ClientError as exc:
            raise NewlabConnectionError(f"GET home failed: {exc}") from exc

        groups = parse_groups(html)

        if not self._system_info_fetched:
            self.system_info = parse_system_info(html)
            if self.system_info.plant_code or self.system_info.cloud_version or self.system_info.cloud_last_sync:
                self._system_info_fetched = True
                _LOGGER.info(
                    "[poll] system_info fetched (one-time): plant=%r version=%r sync=%r",
                    self.system_info.plant_code,
                    self.system_info.cloud_version,
                    self.system_info.cloud_last_sync,
                )
            else:
                _LOGGER.debug("[poll] system_info still empty — will retry on next poll")

        _LOGGER.debug("[poll] complete — %d group(s) in %.2fs", len(groups), time.monotonic() - t0)
        return groups

    async def set_light(self, id_group: int, pwm: int) -> bool:
        if not self.is_authenticated:
            _LOGGER.error("[control] set_light called without authentication")
            return False

        pwm = max(0, min(255, int(pwm)))
        payload = f"pwm={pwm}&status=0&id_group={id_group}"
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
                success = resp.status in (200, 204)
                if not success:
                    _LOGGER.warning(
                        "[control] FAILED — group=%d pwm=%d HTTP %d",
                        id_group, pwm, resp.status,
                    )
                return success
        except aiohttp.ClientError as exc:
            _LOGGER.error(
                "[control] exception — group=%d pwm=%d: %s", id_group, pwm, exc
            )
            return False

    async def async_refresh_plant(self) -> bool:
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
        try:
            async with self._session.post(REFRESH_URL, headers=headers) as resp:
                text = (await resp.text()).strip()
                success = text.upper() == "OK"
                if not success:
                    _LOGGER.warning(
                        "[refresh] unexpected response: HTTP %d body=%r",
                        resp.status, text[:80],
                    )
                return success
        except aiohttp.ClientError as exc:
            _LOGGER.error("[refresh] plantrefresh request failed: %s", exc)
            return False

    async def ensure_authenticated(self) -> None:
        if not self.is_authenticated:
            await self.login()
