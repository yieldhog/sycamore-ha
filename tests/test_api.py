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
