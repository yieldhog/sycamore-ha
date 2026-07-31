"""Tests for the Sycamore config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.sycamore.api import (
    SycamoreApiError,
    SycamoreAuthError,
    SycamoreConnectionError,
)
from custom_components.sycamore.const import DOMAIN


def _patch_client(students=None, side_effect=None):
    """Patch the config-flow client; returns the patch context manager."""
    patcher = patch("custom_components.sycamore.config_flow.SycamoreClient")
    return patcher, students, side_effect


async def test_discovery_flow(hass: HomeAssistant):
    """Full happy path: token + family id -> pick students -> entry."""
    with patch(
        "custom_components.sycamore.config_flow.SycamoreClient"
    ) as mock_cls, patch(
        "custom_components.sycamore.async_setup_entry", return_value=True
    ):
        mock_cls.return_value.async_get_family_students = AsyncMock(
            return_value=[
                {"ID": "111", "FirstName": "Jane", "LastName": "Doe", "Grade": "5th Grade"},
                {"ID": "222", "FirstName": "Sam", "LastName": "Doe", "Grade": "3rd Grade"},
            ]
        )
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "user"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"token": "tok", "family_id": "647150", "school_id": "1002"},
        )
        assert result["step_id"] == "select"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"students": ["111"]}
        )
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["data"]["students"] == [{"id": "111", "name": "Jane"}]
        assert result["data"]["school_id"] == "1002"


async def test_manual_flow(hass: HomeAssistant):
    """No family id -> manual student entry -> entry."""
    with patch("custom_components.sycamore.config_flow.SycamoreClient"), patch(
        "custom_components.sycamore.async_setup_entry", return_value=True
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"token": "tok"}
        )
        assert result["step_id"] == "manual"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"id": "999", "name": "Alex", "add_another": False},
        )
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["data"]["students"] == [{"id": "999", "name": "Alex"}]


async def test_invalid_auth(hass: HomeAssistant):
    """A rejected token surfaces an invalid_auth error on the user step."""
    with patch("custom_components.sycamore.config_flow.SycamoreClient") as mock_cls:
        mock_cls.return_value.async_get_family_students = AsyncMock(
            side_effect=SycamoreAuthError("nope")
        )
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"token": "bad", "family_id": "647150"}
        )
        assert result["type"] == FlowResultType.FORM
        assert result["errors"] == {"base": "invalid_auth"}


async def test_cannot_connect(hass: HomeAssistant):
    """A transport failure surfaces cannot_connect."""
    with patch("custom_components.sycamore.config_flow.SycamoreClient") as mock_cls:
        mock_cls.return_value.async_get_family_students = AsyncMock(
            side_effect=SycamoreConnectionError("down")
        )
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"token": "tok", "family_id": "647150"}
        )
        assert result["errors"] == {"base": "cannot_connect"}


async def test_no_students(hass: HomeAssistant):
    """An empty family surfaces no_students."""
    with patch("custom_components.sycamore.config_flow.SycamoreClient") as mock_cls:
        mock_cls.return_value.async_get_family_students = AsyncMock(return_value=[])
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"token": "tok", "family_id": "000"}
        )
        assert result["errors"] == {"base": "no_students"}


async def test_family_access_denied(hass: HomeAssistant):
    """A non-auth API error during discovery maps to the scope-aware message.

    This is the missing-Families-scope case: Sycamore is reachable but the
    family list comes back unusable, which used to surface as cannot_connect.
    """
    with patch("custom_components.sycamore.config_flow.SycamoreClient") as mock_cls:
        mock_cls.return_value.async_get_family_students = AsyncMock(
            side_effect=SycamoreApiError("HTTP 404", status_code=404)
        )
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"token": "tok", "family_id": "647150"}
        )
        assert result["type"] == FlowResultType.FORM
        assert result["errors"] == {"base": "family_access_denied"}


def test_api_error_is_connection_error():
    """SycamoreApiError must stay a ConnectionError subclass.

    The coordinator only catches SycamoreConnectionError to raise UpdateFailed;
    keeping the subclass relationship means an API/response error there still
    degrades gracefully instead of crashing the refresh.
    """
    assert issubclass(SycamoreApiError, SycamoreConnectionError)
