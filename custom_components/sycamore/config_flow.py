"""Config and options flow for the Sycamore integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import (
    SycamoreApiError,
    SycamoreAuthError,
    SycamoreClient,
    SycamoreConnectionError,
)
from .const import (
    CONF_CALENDAR_AUTOSYNC,
    CONF_CALENDAR_DAYS,
    CONF_CALENDAR_TARGETS,
    CONF_ENABLE_ATTENDANCE,
    CONF_ENABLE_DISCIPLINE,
    CONF_ENABLE_LUNCH,
    CONF_FAMILY_ID,
    CONF_FOCUS_WINDOW_DAYS,
    CONF_SCAN_INTERVAL_MINUTES,
    CONF_SCHOOL_ID,
    CONF_STUDENT_ID,
    CONF_STUDENT_NAME,
    CONF_STUDENTS,
    CONF_TOKEN,
    DEFAULT_CALENDAR_AUTOSYNC,
    DEFAULT_CALENDAR_DAYS,
    DEFAULT_ENABLE_ATTENDANCE,
    DEFAULT_ENABLE_DISCIPLINE,
    DEFAULT_ENABLE_LUNCH,
    DEFAULT_FOCUS_WINDOW_DAYS,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
    MIN_SCAN_INTERVAL_MINUTES,
)


def _student_label(student: dict[str, Any]) -> str:
    """Human label for a discovered student, e.g. 'Jane Doe (5th Grade)'."""
    name = f"{student.get('FirstName', '')} {student.get('LastName', '')}".strip()
    grade = (student.get("Grade") or "").strip()
    return f"{name} ({grade})" if grade else name or str(student.get("ID", "?"))


def _calendar_target_fields(
    students: list[dict[str, Any]],
) -> list[tuple[str, str]]:
    """Return (student_id, option-field key) pairs for the calendar pickers.

    The field key is the child's name so the form shows a meaningful label;
    it's disambiguated with the id only when two students share a name.
    """
    counts: dict[str, int] = {}
    for student in students:
        counts[student[CONF_STUDENT_NAME]] = counts.get(student[CONF_STUDENT_NAME], 0) + 1
    fields: list[tuple[str, str]] = []
    for student in students:
        sid = student[CONF_STUDENT_ID]
        name = student[CONF_STUDENT_NAME]
        key = name if counts[name] == 1 else f"{name} ({sid})"
        fields.append((sid, key))
    return fields


class SycamoreConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the UI setup flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize transient flow state."""
        self._token: str | None = None
        self._family_id: str | None = None
        self._school_id: str | None = None
        self._discovered: list[dict[str, Any]] = []
        self._students: list[dict[str, str]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect the token and (optionally) family/school IDs."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._token = user_input[CONF_TOKEN].strip()
            self._family_id = (user_input.get(CONF_FAMILY_ID) or "").strip() or None
            self._school_id = (user_input.get(CONF_SCHOOL_ID) or "").strip() or None
            client = SycamoreClient(self.hass, self._token)

            if self._family_id:
                try:
                    self._discovered = await client.async_get_family_students(
                        self._family_id
                    )
                except SycamoreAuthError:
                    errors["base"] = "invalid_auth"
                except SycamoreApiError:
                    # Reached Sycamore but the family list came back unusable —
                    # usually the token lacks the Families scope. Must precede
                    # SycamoreConnectionError since it is a subclass.
                    errors["base"] = "family_access_denied"
                except SycamoreConnectionError:
                    errors["base"] = "cannot_connect"
                else:
                    if self._discovered:
                        await self.async_set_unique_id(f"family-{self._family_id}")
                        self._abort_if_unique_id_configured()
                        return await self.async_step_select()
                    errors["base"] = "no_students"
            else:
                # No family id: skip discovery, add students by hand.
                return await self.async_step_manual()

        schema = vol.Schema(
            {
                vol.Required(CONF_TOKEN, default=(user_input or {}).get(CONF_TOKEN, "")): str,
                vol.Optional(CONF_FAMILY_ID): str,
                vol.Optional(CONF_SCHOOL_ID): str,
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )

    async def async_step_select(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick which discovered students to add."""
        if user_input is not None:
            by_id = {str(s.get("ID")): s for s in self._discovered}
            self._students = [
                {
                    CONF_STUDENT_ID: sid,
                    CONF_STUDENT_NAME: (
                        by_id[sid].get("FirstName") or _student_label(by_id[sid])
                    ).strip(),
                }
                for sid in user_input[CONF_STUDENTS]
            ]
            return self._create_entry()

        options = [
            SelectOptionDict(value=str(s.get("ID")), label=_student_label(s))
            for s in self._discovered
        ]
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_STUDENTS,
                    default=[o["value"] for o in options],
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=options,
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                    )
                )
            }
        )
        return self.async_show_form(step_id="select", data_schema=schema)

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add students by hand (fallback when no family id is given)."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._students.append(
                {
                    CONF_STUDENT_ID: user_input[CONF_STUDENT_ID].strip(),
                    CONF_STUDENT_NAME: user_input[CONF_STUDENT_NAME].strip(),
                }
            )
            if user_input.get("add_another"):
                return await self.async_step_manual()
            if not self.unique_id:
                await self.async_set_unique_id(f"token-{self._token[:12]}")
                self._abort_if_unique_id_configured()
            return self._create_entry()

        schema = vol.Schema(
            {
                vol.Required(CONF_STUDENT_ID): str,
                vol.Required(CONF_STUDENT_NAME): str,
                vol.Optional("add_another", default=False): bool,
            }
        )
        return self.async_show_form(
            step_id="manual", data_schema=schema, errors=errors
        )

    @callback
    def _create_entry(self) -> ConfigFlowResult:
        """Persist the collected config into a new entry."""
        return self.async_create_entry(
            title="Sycamore",
            data={
                CONF_TOKEN: self._token,
                CONF_FAMILY_ID: self._family_id,
                CONF_SCHOOL_ID: self._school_id,
                CONF_STUDENTS: self._students,
            },
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Start reauth when the stored token is rejected."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a fresh token and update the entry."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            token = user_input[CONF_TOKEN].strip()
            client = SycamoreClient(self.hass, token)
            family_id = entry.data.get(CONF_FAMILY_ID)
            try:
                await client.async_validate(family_id)
            except SycamoreAuthError:
                errors["base"] = "invalid_auth"
            except SycamoreConnectionError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_TOKEN: token}
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_TOKEN): str}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlow:
        """Return the options flow handler."""
        return SycamoreOptionsFlow()


class SycamoreOptionsFlow(OptionsFlow):
    """Handle scan interval and focus window options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the integration options."""
        students = self.config_entry.data.get(CONF_STUDENTS, [])
        # Per-student calendar pickers are labelled by the child's name; map the
        # (unique) label back to the student id when saving.
        target_fields = _calendar_target_fields(students)

        if user_input is not None:
            targets: dict[str, str] = {}
            for sid, field_key in target_fields:
                value = user_input.pop(field_key, None)
                if value:
                    targets[sid] = value
            user_input[CONF_CALENDAR_TARGETS] = targets
            return self.async_create_entry(data=user_input)

        current = self.config_entry.options
        current_targets: dict[str, str] = current.get(CONF_CALENDAR_TARGETS, {})
        schema_dict: dict[Any, Any] = {
            vol.Optional(
                CONF_SCAN_INTERVAL_MINUTES,
                default=current.get(
                    CONF_SCAN_INTERVAL_MINUTES, DEFAULT_SCAN_INTERVAL_MINUTES
                ),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=MIN_SCAN_INTERVAL_MINUTES,
                    max=720,
                    step=5,
                    unit_of_measurement="min",
                    mode=NumberSelectorMode.BOX,
                )
            ),
            vol.Optional(
                CONF_FOCUS_WINDOW_DAYS,
                default=current.get(
                    CONF_FOCUS_WINDOW_DAYS, DEFAULT_FOCUS_WINDOW_DAYS
                ),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=1, max=31, step=1, mode=NumberSelectorMode.BOX
                )
            ),
            vol.Optional(
                CONF_ENABLE_ATTENDANCE,
                default=current.get(
                    CONF_ENABLE_ATTENDANCE, DEFAULT_ENABLE_ATTENDANCE
                ),
            ): bool,
            vol.Optional(
                CONF_ENABLE_LUNCH,
                default=current.get(CONF_ENABLE_LUNCH, DEFAULT_ENABLE_LUNCH),
            ): bool,
            vol.Optional(
                CONF_ENABLE_DISCIPLINE,
                default=current.get(
                    CONF_ENABLE_DISCIPLINE, DEFAULT_ENABLE_DISCIPLINE
                ),
            ): bool,
            vol.Optional(
                CONF_CALENDAR_AUTOSYNC,
                default=current.get(
                    CONF_CALENDAR_AUTOSYNC, DEFAULT_CALENDAR_AUTOSYNC
                ),
            ): bool,
            vol.Optional(
                CONF_CALENDAR_DAYS,
                default=current.get(CONF_CALENDAR_DAYS, DEFAULT_CALENDAR_DAYS),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=1,
                    max=90,
                    step=1,
                    unit_of_measurement="days",
                    mode=NumberSelectorMode.BOX,
                )
            ),
        }
        # One optional calendar picker per student (blank = don't sync).
        for sid, field_key in target_fields:
            schema_dict[
                vol.Optional(
                    field_key,
                    description={"suggested_value": current_targets.get(sid)},
                )
            ] = EntitySelector(EntitySelectorConfig(domain="calendar"))

        return self.async_show_form(
            step_id="init", data_schema=vol.Schema(schema_dict)
        )
