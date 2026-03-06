from __future__ import annotations

import asyncio
import importlib
from types import SimpleNamespace


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
        return _RequestCtx(_Response(status=200, text=html, url="https://smarthome.newlablight.com/registrationwelcome"))

    def post(self, _url: str, data=None, headers=None, allow_redirects=True):
        self._jar.extend([_Cookie("csrftoken", "csrf-cookie"), _Cookie("sessionid", "sid-1")])
        return _RequestCtx(_Response(status=200, text="", url="https://smarthome.newlablight.com/registrationhome"))


def test_login_success_sets_cookies(monkeypatch) -> None:
    monkeypatch.setattr(client_module.aiohttp, "CookieJar", lambda unsafe: [])
    monkeypatch.setattr(client_module.aiohttp, "ClientSession", _LoginSession)

    api = client_module.NewlabAPI("user", "pw", session=SimpleNamespace())
    asyncio.run(api.login())

    assert api.is_authenticated is True
    assert "sessionid" in api.cookie_header


def test_get_groups_requires_authentication() -> None:
    api = client_module.NewlabAPI("user", "pw", session=SimpleNamespace())
    try:
        asyncio.run(api.get_groups())
    except models_module.NewlabAuthError:
        pass
    else:
        raise AssertionError("Expected NewlabAuthError")


def test_get_groups_success_parses_data() -> None:
    html = """
    <title>Newlab Smart Home - Ver. 3.47</title>
    <p>Plant Id: <b>plant_code_example_003</b></p>
    <p>Last syncronization: <b>Feb. 16, 2026, 7:01 p.m.</b></p>
    <label for="range_2">Soggiorno</label>
    <input id="range_2" value="80" />
    """
    session = _RuntimeSession(
        get_resp=_Response(status=200, text=html, url="https://smarthome.newlablight.com/registrationhome"),
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
        get_resp=_Response(status=200, text="", url="https://smarthome.newlablight.com/registrationhome"),
        post_resp=_Response(status=200, text="OK"),
    )
    api = client_module.NewlabAPI("user", "pw", session=session)
    api._csrf_token = "a"
    api._session_id = "b"

    assert asyncio.run(api.set_light(1, 99)) is True
    assert asyncio.run(api.async_refresh_plant()) is True
