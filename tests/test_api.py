"""Tests for the Sycamore API client's error mapping.

These pin the transport-vs-response split: a reachable-but-errored response
(e.g. the HTTP 404 "Endpoint Not Found" a token without the Families scope
gets back) must be a SycamoreApiError, while a genuine transport failure stays
a plain SycamoreConnectionError.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from custom_components.sycamore.api import (
    SycamoreApiError,
    SycamoreAuthError,
    SycamoreClient,
    SycamoreConnectionError,
)


def _client_returning(hass, response: httpx.Response) -> SycamoreClient:
    """Build a client whose underlying httpx GET returns a fixed response."""
    client = SycamoreClient(hass, "tok")
    client._client = AsyncMock()
    client._client.get = AsyncMock(return_value=response)
    return client


async def test_404_maps_to_api_error(hass):
    """The real missing-Families-scope response (404 + JSON) is an API error.

    It must carry the status code and remain a SycamoreConnectionError subclass
    so the coordinator's UpdateFailed path still catches it.
    """
    client = _client_returning(
        hass,
        httpx.Response(404, json={"code": 404, "message": "Endpoint Not Found"}),
    )
    with pytest.raises(SycamoreApiError) as exc:
        await client.async_get_family_students("123")
    assert exc.value.status_code == 404
    assert isinstance(exc.value, SycamoreConnectionError)


async def test_transport_error_maps_to_connection_error(hass):
    """An httpx transport failure is a plain connection error, not an API error."""
    client = SycamoreClient(hass, "tok")
    client._client = AsyncMock()
    client._client.get = AsyncMock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(SycamoreConnectionError) as exc:
        await client.async_get_family_students("123")
    assert not isinstance(exc.value, SycamoreApiError)


async def test_401_maps_to_auth_error(hass):
    """A rejected token still raises the dedicated auth error."""
    client = _client_returning(hass, httpx.Response(401))
    with pytest.raises(SycamoreAuthError):
        await client.async_get_family_students("123")


async def test_empty_body_is_empty_list(hass):
    """A 204 / empty body is treated as no rows, not an error."""
    client = _client_returning(hass, httpx.Response(204))
    assert await client.async_get_family_students("123") == []


async def test_transient_500_is_retried_then_succeeds(hass, monkeypatch):
    """A transient 5xx is retried; a good response on a later attempt wins.

    Mirrors the real Sycamore behaviour where a single endpoint 500s under the
    concurrent-request burst but succeeds a moment later.
    """
    import custom_components.sycamore.api as api_mod

    monkeypatch.setattr(api_mod, "_RETRY_BACKOFF", 0)  # no real delay in tests
    client = SycamoreClient(hass, "tok")
    client._client = AsyncMock()
    client._client.get = AsyncMock(
        side_effect=[
            httpx.Response(500, text="boom"),
            httpx.Response(200, json=[{"ClassName": "Science", "Number": "90"}]),
        ]
    )
    result = await client.async_get_grades("123")
    assert result == [{"ClassName": "Science", "Number": "90"}]
    assert client._client.get.call_count == 2


async def test_persistent_500_raises_after_retries(hass, monkeypatch):
    """A 5xx on every attempt eventually raises an API error (not forever)."""
    import custom_components.sycamore.api as api_mod

    monkeypatch.setattr(api_mod, "_RETRY_BACKOFF", 0)
    client = SycamoreClient(hass, "tok")
    client._client = AsyncMock()
    client._client.get = AsyncMock(return_value=httpx.Response(500, text="down"))
    with pytest.raises(SycamoreApiError) as exc:
        await client.async_get_grades("123")
    assert exc.value.status_code == 500
    assert client._client.get.call_count == 3  # _MAX_ATTEMPTS


async def test_404_is_not_retried(hass, monkeypatch):
    """A 404 (a real 'not found', not a transient blip) fails on the first try."""
    import custom_components.sycamore.api as api_mod

    monkeypatch.setattr(api_mod, "_RETRY_BACKOFF", 0)
    client = SycamoreClient(hass, "tok")
    client._client = AsyncMock()
    client._client.get = AsyncMock(
        return_value=httpx.Response(404, json={"message": "Endpoint Not Found"})
    )
    with pytest.raises(SycamoreApiError):
        await client.async_get_family_students("123")
    assert client._client.get.call_count == 1  # not retried


async def test_discipline_hits_correct_endpoint(hass):
    """Discipline must call /Student/{id}/Discipline, not the old Discipline_Log.

    The real Sycamore API exposes `Discipline` (confirmed in the sandbox);
    `Discipline_Log` 404s. Pin the path so it can't regress.
    """
    client = _client_returning(hass, httpx.Response(200, json=[]))
    await client.async_get_discipline("123")
    url = client._client.get.call_args.args[0]
    assert url.endswith("/Student/123/Discipline")
    assert "Discipline_Log" not in url
