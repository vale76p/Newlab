"""Unit tests for the NewlabAPI HTTP client."""

from __future__ import annotations

import asyncio
import importlib
from types import SimpleNamespace

import pytest

client_module = importlib.import_module("custom_components.newlab.client")
models_module = importlib.import_module("custom_components.newlab.models")


class _Response:
    def __init__(self, *, status: int = 200, text: str = "", url: str = "https://x/home") -> None:
        self.status = status
        self._text = text
        self.url = url

    async def text(self) -> str:
        return self._text


class _RequestCtx:
    def __init__(self, response: _Response) -> None:
        self._response = response

    async def __aenter__(self) -> _Response:
        return self._response

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class _RuntimeSession:
    def __init__(self, get_resp: _Response, post_resp: _Response) -> None:
        self._get_resp = get_resp
        self._post_resp = post_resp

    def get(self, _url: str, headers=None):
        return _RequestCtx(self._get_resp)

    def post(self, _url: str, data=None, headers=None):
        return _RequestCtx(self._post_resp)


class _Cookie:
    def __init__(self, key: str, value: str) -> None:
        self.key = key
        self.value = value


class _LoginSession:
    def __init__(self, cookie_jar=None, **kwargs) -> None:
        self._jar = cookie_jar

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    def get(self, _url: str):
        html = '<input name="csrfmiddlewaretoken" value="csrf123" />'
        return _RequestCtx(_Response(
            status=200, text=html,
            url="https://smarthome.newlablight.com/registrationwelcome",
        ))

    def post(self, _url: str, data=None, headers=None, allow_redirects=True):
        self._jar.extend([_Cookie("csrftoken", "csrf-cookie"), _Cookie("sessionid", "sid-1")])
        return _RequestCtx(_Response(
            status=200, text="",
            url="https://smarthome.newlablight.com/registrationhome",
        ))


def test_login_success_sets_cookies(monkeypatch) -> None:
    monkeypatch.setattr(client_module.aiohttp, "CookieJar", lambda unsafe: [])
    monkeypatch.setattr(client_module.aiohttp, "ClientSession", _LoginSession)

    api = client_module.NewlabAPI("user", "pw", session=SimpleNamespace())
    asyncio.run(api.login())

    assert api.is_authenticated is True
    assert "sessionid" in api.cookie_header


def test_get_groups_requires_authentication() -> None:
    api = client_module.NewlabAPI("user", "pw", session=SimpleNamespace())
    with pytest.raises(models_module.NewlabAuthError):
        asyncio.run(api.get_groups())


def test_get_groups_success_parses_data() -> None:
    html = """
    <title>Newlab Smart Home - Ver. 3.47</title>
    <p>Plant Id: <b>plant_code_example_003</b></p>
    <p>Last syncronization: <b>Feb. 16, 2026, 7:01 p.m.</b></p>
    <label for="range_2">Soggiorno</label>
    <input id="range_2" value="80" />
    """
    session = _RuntimeSession(
        get_resp=_Response(
            status=200, text=html,
            url="https://smarthome.newlablight.com/registrationhome",
        ),
        post_resp=_Response(status=200, text="OK"),
    )
    api = client_module.NewlabAPI("user", "pw", session=session)
    api._csrf_token = "a"
    api._session_id = "b"

    groups = asyncio.run(api.get_groups())

    assert groups[2].name == "Soggiorno"
    assert groups[2].pwm == 80
    assert api.system_info.plant_code == "plant_code_example_003"


def test_set_light_and_refresh() -> None:
    session = _RuntimeSession(
        get_resp=_Response(
            status=200, text="",
            url="https://smarthome.newlablight.com/registrationhome",
        ),
        post_resp=_Response(status=200, text="OK"),
    )
    api = client_module.NewlabAPI("user", "pw", session=session)
    api._csrf_token = "a"
    api._session_id = "b"

    assert asyncio.run(api.set_light(1, 99)) is True
    assert asyncio.run(api.async_refresh_plant()) is True


# ── Edge-case tests ───────────────────────────────────────────────────────────


class _FailWelcomeSession:
    """Welcome page returns non-200."""
    def __init__(self, cookie_jar=None, **kwargs):
        self._jar = cookie_jar or []

    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass

    def get(self, _url: str):
        return _RequestCtx(_Response(status=500, text="", url=_url))

    def post(self, _url: str, data=None, headers=None, allow_redirects=True):
        return _RequestCtx(_Response(status=200, text="", url=_url))


class _NoCsrfSession:
    """Welcome page HTML has no csrfmiddlewaretoken."""
    def __init__(self, cookie_jar=None, **kwargs):
        self._jar = cookie_jar or []

    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass

    def get(self, _url: str):
        return _RequestCtx(_Response(status=200, text="<html>no csrf here</html>", url=_url))

    def post(self, _url: str, data=None, headers=None, allow_redirects=True):
        return _RequestCtx(_Response(status=200, text="", url=_url))


class _RedirectToLoginSession:
    """POST login redirects to the login URL (bad credentials)."""
    def __init__(self, cookie_jar=None, **kwargs):
        self._jar = cookie_jar or []

    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass

    def get(self, _url: str):
        html = '<input name="csrfmiddlewaretoken" value="csrf123" />'
        return _RequestCtx(_Response(status=200, text=html, url=_url))

    def post(self, _url: str, data=None, headers=None, allow_redirects=True):
        return _RequestCtx(_Response(
            status=200, text="",
            url="https://smarthome.newlablight.com/registrationlogin",
        ))


class _NoCookiesSession:
    """POST succeeds but jar stays empty (no session cookies issued)."""
    def __init__(self, cookie_jar=None, **kwargs):
        self._jar = cookie_jar or []

    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass

    def get(self, _url: str):
        html = '<input name="csrfmiddlewaretoken" value="csrf123" />'
        return _RequestCtx(_Response(status=200, text=html, url=_url))

    def post(self, _url: str, data=None, headers=None, allow_redirects=True):
        # deliberately no cookies written to jar
        return _RequestCtx(_Response(
            status=200, text="",
            url="https://smarthome.newlablight.com/registrationhome",
        ))


def test_login_fails_on_welcome_non_200(monkeypatch) -> None:
    monkeypatch.setattr(client_module.aiohttp, "CookieJar", lambda unsafe: [])
    monkeypatch.setattr(client_module.aiohttp, "ClientSession", _FailWelcomeSession)
    api = client_module.NewlabAPI("user", "pw", session=SimpleNamespace())
    with pytest.raises(models_module.NewlabConnectionError):
        asyncio.run(api.login())


def test_login_fails_on_missing_csrf(monkeypatch) -> None:
    monkeypatch.setattr(client_module.aiohttp, "CookieJar", lambda unsafe: [])
    monkeypatch.setattr(client_module.aiohttp, "ClientSession", _NoCsrfSession)
    api = client_module.NewlabAPI("user", "pw", session=SimpleNamespace())
    with pytest.raises(models_module.NewlabParseError):
        asyncio.run(api.login())


def test_login_fails_on_redirect_to_login(monkeypatch) -> None:
    monkeypatch.setattr(client_module.aiohttp, "CookieJar", lambda unsafe: [])
    monkeypatch.setattr(client_module.aiohttp, "ClientSession", _RedirectToLoginSession)
    api = client_module.NewlabAPI("user", "pw", session=SimpleNamespace())
    with pytest.raises(models_module.NewlabAuthError):
        asyncio.run(api.login())


def test_login_fails_on_missing_cookies(monkeypatch) -> None:
    monkeypatch.setattr(client_module.aiohttp, "CookieJar", lambda unsafe: [])
    monkeypatch.setattr(client_module.aiohttp, "ClientSession", _NoCookiesSession)
    api = client_module.NewlabAPI("user", "pw", session=SimpleNamespace())
    with pytest.raises(models_module.NewlabAuthError):
        asyncio.run(api.login())


def test_get_groups_raises_auth_error_on_302() -> None:
    session = _RuntimeSession(
        get_resp=_Response(status=302, text="", url="https://smarthome.newlablight.com/registrationhome"),
        post_resp=_Response(status=200, text="OK"),
    )
    api = client_module.NewlabAPI("user", "pw", session=session)
    api._csrf_token = "a"
    api._session_id = "b"
    with pytest.raises(models_module.NewlabAuthError):
        asyncio.run(api.get_groups())


def test_get_groups_raises_connection_error_on_500() -> None:
    session = _RuntimeSession(
        get_resp=_Response(status=500, text="", url="https://smarthome.newlablight.com/registrationhome"),
        post_resp=_Response(status=200, text="OK"),
    )
    api = client_module.NewlabAPI("user", "pw", session=session)
    api._csrf_token = "a"
    api._session_id = "b"
    with pytest.raises(models_module.NewlabConnectionError):
        asyncio.run(api.get_groups())


def test_set_light_returns_false_unauthenticated() -> None:
    api = client_module.NewlabAPI("user", "pw", session=SimpleNamespace())
    assert asyncio.run(api.set_light(1, 100)) is False


def test_set_light_returns_false_on_non_200() -> None:
    session = _RuntimeSession(
        get_resp=_Response(status=200, text="", url="https://smarthome.newlablight.com/registrationhome"),
        post_resp=_Response(status=500, text="error"),
    )
    api = client_module.NewlabAPI("user", "pw", session=session)
    api._csrf_token = "a"
    api._session_id = "b"
    assert asyncio.run(api.set_light(1, 100)) is False


def test_async_refresh_plant_returns_false_unauthenticated() -> None:
    api = client_module.NewlabAPI("user", "pw", session=SimpleNamespace())
    assert asyncio.run(api.async_refresh_plant()) is False


def test_async_refresh_plant_returns_false_on_unexpected_body() -> None:
    session = _RuntimeSession(
        get_resp=_Response(status=200, text="", url="https://smarthome.newlablight.com/registrationhome"),
        post_resp=_Response(status=200, text="ERROR"),
    )
    api = client_module.NewlabAPI("user", "pw", session=session)
    api._csrf_token = "a"
    api._session_id = "b"
    assert asyncio.run(api.async_refresh_plant()) is False


def test_is_authenticated_false_when_no_cookies() -> None:
    api = client_module.NewlabAPI("user", "pw", session=SimpleNamespace())
    assert api.is_authenticated is False


def test_cookie_header_empty_when_not_authenticated() -> None:
    api = client_module.NewlabAPI("user", "pw", session=SimpleNamespace())
    assert api.cookie_header == ""


def test_ensure_authenticated_calls_login_when_not_auth(monkeypatch) -> None:
    login_called = []

    async def _mock_login() -> None:
        login_called.append(True)

    api = client_module.NewlabAPI("user", "pw", session=SimpleNamespace())
    monkeypatch.setattr(api, "login", _mock_login)
    asyncio.run(api.ensure_authenticated())
    assert len(login_called) == 1


def test_ensure_authenticated_skips_login_when_already_auth(monkeypatch) -> None:
    login_called = []

    async def _mock_login() -> None:
        login_called.append(True)

    api = client_module.NewlabAPI("user", "pw", session=SimpleNamespace())
    api._csrf_token = "a"
    api._session_id = "b"
    monkeypatch.setattr(api, "login", _mock_login)
    asyncio.run(api.ensure_authenticated())
    assert len(login_called) == 0
