"""Tests for the Sycamore config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

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
        # New per-child calendar step; leaving it blank keeps dedicated calendars.
        assert result["step_id"] == "calendars"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["data"]["students"] == [{"id": "111", "name": "Jane"}]
        assert result["data"]["school_id"] == "1002"
        # Nothing chosen -> no sync options (each child gets its own calendar).
        assert result["options"] == {}


async def test_discovery_flow_with_calendar_target(hass: HomeAssistant):
    """Choosing an existing calendar for a child stores it as a sync target."""
    with patch(
        "custom_components.sycamore.config_flow.SycamoreClient"
    ) as mock_cls, patch(
        "custom_components.sycamore.async_setup_entry", return_value=True
    ):
        mock_cls.return_value.async_get_family_students = AsyncMock(
            return_value=[
                {"ID": "111", "FirstName": "Jane", "LastName": "Doe", "Grade": "5th"},
            ]
        )
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"token": "tok", "family_id": "647150"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"students": ["111"]}
        )
        assert result["step_id"] == "calendars"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"Jane": "calendar.family"}
        )
        assert result["type"] == FlowResultType.CREATE_ENTRY
        # Target stored under the student id, auto-sync enabled.
        assert result["options"]["calendar_targets"] == {"111": "calendar.family"}
        assert result["options"]["calendar_autosync"] is True


async def test_manual_flow(hass: HomeAssistant):
    """No family id -> manual student entry -> entry."""
    with patch(
        "custom_components.sycamore.config_flow.SycamoreClient"
    ) as mock_cls, patch(
        "custom_components.sycamore.async_setup_entry", return_value=True
    ):
        mock_cls.return_value.async_get_student_details = AsyncMock(return_value={})
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
        assert result["step_id"] == "calendars"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
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


async def test_already_configured(hass: HomeAssistant):
    """Re-adding the same family aborts as already_configured."""
    existing = MockConfigEntry(
        domain=DOMAIN,
        unique_id="family-647150",
        data={"token": "tok", "family_id": "647150", "school_id": None, "students": []},
    )
    existing.add_to_hass(hass)
    with patch("custom_components.sycamore.config_flow.SycamoreClient") as mock_cls:
        mock_cls.return_value.async_get_family_students = AsyncMock(
            return_value=[{"ID": "111", "FirstName": "Jane", "LastName": "Doe"}]
        )
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"token": "tok", "family_id": "647150"}
        )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_manual_add_another(hass: HomeAssistant):
    """The manual step loops with add_another, then makes a multi-student entry."""
    with patch(
        "custom_components.sycamore.config_flow.SycamoreClient"
    ) as mock_cls, patch(
        "custom_components.sycamore.async_setup_entry", return_value=True
    ):
        mock_cls.return_value.async_get_student_details = AsyncMock(return_value={})
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"token": "tok"}
        )
        assert result["step_id"] == "manual"
        # First student, ask for another -> back to the manual form.
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"id": "1", "name": "Ann", "add_another": True}
        )
        assert result["step_id"] == "manual"
        # Second student, finish.
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"id": "2", "name": "Bob", "add_another": False}
        )
        assert result["step_id"] == "calendars"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["students"] == [
        {"id": "1", "name": "Ann"},
        {"id": "2", "name": "Bob"},
    ]


async def test_manual_invalid_token(hass: HomeAssistant):
    """A bad token is caught on the manual path (test-before-configure)."""
    with patch("custom_components.sycamore.config_flow.SycamoreClient") as mock_cls:
        mock_cls.return_value.async_get_student_details = AsyncMock(
            side_effect=SycamoreAuthError("nope")
        )
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"token": "bad"}
        )
        assert result["step_id"] == "manual"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"id": "999", "name": "Alex", "add_another": False}
        )
    # Stays on the manual step with the auth error, no entry created.
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "manual"
    assert result["errors"] == {"base": "invalid_auth"}


async def test_reconfigure_success(hass: HomeAssistant):
    """Reconfigure updates the token + School ID without removing the entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="family-647150",
        data={
            "token": "old",
            "family_id": "647150",
            "school_id": None,
            "students": [{"id": "111", "name": "Jane"}],
        },
    )
    entry.add_to_hass(hass)
    with patch(
        "custom_components.sycamore.config_flow.SycamoreClient"
    ) as mock_cls, patch(
        "custom_components.sycamore.async_setup_entry", return_value=True
    ):
        mock_cls.return_value.async_get_family_students = AsyncMock(
            return_value=[{"ID": "111"}]
        )
        result = await entry.start_reconfigure_flow(hass)
        assert result["step_id"] == "reconfigure"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"token": "newtok", "school_id": "1002"}
        )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["token"] == "newtok"
    assert entry.data["school_id"] == "1002"


async def test_reconfigure_invalid_auth(hass: HomeAssistant):
    """A rejected token on reconfigure surfaces invalid_auth and doesn't save."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="family-647150",
        data={
            "token": "old",
            "family_id": "647150",
            "school_id": None,
            "students": [{"id": "111", "name": "Jane"}],
        },
    )
    entry.add_to_hass(hass)
    with patch("custom_components.sycamore.config_flow.SycamoreClient") as mock_cls:
        mock_cls.return_value.async_get_family_students = AsyncMock(
            side_effect=SycamoreAuthError("nope")
        )
        result = await entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"token": "bad"}
        )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    assert entry.data["token"] == "old"


async def test_reauth_success(hass: HomeAssistant):
    """Reauth with a valid token updates the entry and aborts successfully."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="family-647150",
        data={
            "token": "old",
            "family_id": "647150",
            "school_id": None,
            "students": [{"id": "111", "name": "Jane"}],
        },
    )
    entry.add_to_hass(hass)
    with patch(
        "custom_components.sycamore.config_flow.SycamoreClient"
    ) as mock_cls, patch(
        "custom_components.sycamore.async_setup_entry", return_value=True
    ):
        mock_cls.return_value.async_validate = AsyncMock(return_value=None)
        result = await entry.start_reauth_flow(hass)
        assert result["step_id"] == "reauth_confirm"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"token": "newtok"}
        )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["token"] == "newtok"


async def test_options_flow(hass: HomeAssistant):
    """The options flow saves interval, focus window, and the toggles."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "token": "tok",
            "family_id": "647150",
            "school_id": None,
            "students": [{"id": "111", "name": "Jane"}],
        },
        options={},
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "scan_interval_minutes": 90,
            "focus_window_days": 14,
            "attendance_enabled": False,
            "lunch_enabled": True,
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["focus_window_days"] == 14
    assert result["data"]["attendance_enabled"] is False
    assert result["data"]["lunch_enabled"] is True


async def test_options_flow_calendar_mapping(hass: HomeAssistant):
    """Per-student calendar picker (labelled by name) maps back to the id."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "token": "tok",
            "family_id": "647150",
            "school_id": None,
            "students": [{"id": "111", "name": "Jane"}],
        },
        options={},
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "scan_interval_minutes": 60,
            "focus_window_days": 7,
            "attendance_enabled": True,
            "lunch_enabled": True,
            "calendar_autosync": True,
            "calendar_days": 21,
            "Jane": "calendar.school",  # field is labelled by the child's name
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["calendar_autosync"] is True
    assert result["data"]["calendar_days"] == 21
    # The name-labelled picker is stored keyed by student id.
    assert result["data"]["calendar_targets"] == {"111": "calendar.school"}
