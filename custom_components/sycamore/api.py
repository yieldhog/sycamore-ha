"""Async client for the Sycamore School API.

Thin wrapper over the shared Home Assistant httpx client. Endpoints and the
Bearer-token auth model are per the official Sycamore API docs
(github.com/SycamoreEducation/SycamoreSchoolAPI).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from homeassistant.core import HomeAssistant
from homeassistant.helpers.httpx_client import get_async_client

from .const import API_BASE

_LOGGER = logging.getLogger(__name__)

_TIMEOUT = 15.0

# Sycamore's API intermittently 500s a single endpoint — especially under the
# burst of concurrent requests one refresh makes (grades + homework + missing +
# details at once). These are transient: the same request retried a moment later
# usually succeeds (we've watched an endpoint flip 500 -> 204). Retry a handful
# of server-side statuses with a short exponential backoff before giving up.
_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
_MAX_ATTEMPTS = 3
_RETRY_BACKOFF = 0.5  # seconds; doubled each retry (0.5s, 1.0s)

# Root cause of the transient 500s above: a single refresh fans out to every
# endpoint for every student at once, and Sycamore's API drops requests under
# that burst. Cap how many requests are in flight at any moment (across all
# students and endpoints) so we never trigger it in the first place. Refreshes
# are hourly, so the small serialization cost is invisible; the retry above is
# just the backstop for the occasional blip that slips through.
_MAX_CONCURRENCY = 2


class SycamoreError(Exception):
    """Base error for the Sycamore client."""


class SycamoreAuthError(SycamoreError):
    """Raised when the token is rejected (401/403)."""


class SycamoreConnectionError(SycamoreError):
    """Raised when Sycamore can't be reached (transport / network error)."""


class SycamoreApiError(SycamoreConnectionError):
    """Sycamore was reached but the response was an error or unusable.

    Distinct from a transport failure: the request got through but came back
    with a non-auth error status or an unparseable body — which is what a
    missing endpoint scope (e.g. no ``Families`` access) looks like. Subclasses
    ``SycamoreConnectionError`` so existing handlers (the coordinator's
    ``UpdateFailed`` path) still catch it; the config flow can catch it first
    to give a scope-aware message. Carries the HTTP status code when known.
    """

    def __init__(self, message: str, status_code: int | None = None) -> None:
        """Store the human message and the originating HTTP status (if any)."""
        super().__init__(message)
        self.status_code = status_code


class SycamoreClient:
    """Minimal async client for the endpoints this integration uses."""

    def __init__(self, hass: HomeAssistant, token: str) -> None:
        """Store the shared httpx client and the account token."""
        self._client = get_async_client(hass)
        self._token = token
        # Bounds concurrent in-flight requests for this account (see
        # _MAX_CONCURRENCY) so a refresh doesn't hammer Sycamore all at once.
        self._semaphore = asyncio.Semaphore(_MAX_CONCURRENCY)

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    async def _get(self, path: str) -> Any:
        """GET a Sycamore endpoint, returning parsed JSON (or [] for empty).

        Sycamore returns 204 / an empty body when a section has no rows (e.g.
        no missing work, or between terms). Treat those as an empty list so one
        empty section never blanks out the others (ported from _json_list).
        """
        url = f"{API_BASE}/{path.lstrip('/')}"
        for attempt in range(_MAX_ATTEMPTS):
            # Hold the concurrency slot only for the network call, not the
            # backoff sleep below, so a retrying request doesn't idle a slot.
            async with self._semaphore:
                try:
                    resp = await self._client.get(
                        url, headers=self._headers, timeout=_TIMEOUT
                    )
                except httpx.HTTPError as err:
                    raise SycamoreConnectionError(
                        f"Request to {path} failed: {err}"
                    ) from err

            if resp.status_code in (401, 403):
                raise SycamoreAuthError(
                    f"Token rejected for {path} ({resp.status_code})"
                )
            if resp.status_code == 204 or not resp.content:
                return []
            # Retry transient server-side errors, but only while attempts
            # remain: the retry guard requires attempt < _MAX_ATTEMPTS - 1, so
            # on the final attempt a retryable status falls through to the
            # HTTP-error raise below. The loop therefore always returns or
            # raises within its last iteration — it never exits normally.
            if resp.status_code in _RETRY_STATUSES and attempt < _MAX_ATTEMPTS - 1:
                delay = _RETRY_BACKOFF * (2**attempt)
                _LOGGER.debug(
                    "Sycamore %s returned HTTP %s; retrying in %.1fs (attempt %d/%d)",
                    path,
                    resp.status_code,
                    delay,
                    attempt + 1,
                    _MAX_ATTEMPTS,
                )
                await asyncio.sleep(delay)
                continue
            if resp.status_code >= 300:
                _LOGGER.debug(
                    "Sycamore %s returned HTTP %s: %s",
                    path,
                    resp.status_code,
                    resp.text[:200],
                )
                raise SycamoreApiError(
                    f"{path} returned HTTP {resp.status_code}",
                    status_code=resp.status_code,
                )
            try:
                return resp.json()
            except ValueError as err:
                _LOGGER.debug(
                    "Sycamore %s returned an unparseable body: %s",
                    path,
                    resp.text[:200],
                )
                raise SycamoreApiError(
                    f"Bad JSON from {path}: {err}", status_code=resp.status_code
                ) from err

    @staticmethod
    def _as_list(data: Any) -> list[dict[str, Any]]:
        return data if isinstance(data, list) else []

    # --- Discovery ---------------------------------------------------------
    async def async_get_family_students(self, family_id: str) -> list[dict[str, Any]]:
        """List the students in a family: GET /Family/{id}/Students."""
        return self._as_list(await self._get(f"Family/{family_id}/Students"))

    async def async_validate(self, family_id: str | None = None) -> None:
        """Raise SycamoreAuthError/ConnectionError if the token can't be used.

        Prefer validating against the family students list (also confirms the
        family id); callers without a family id can pass None to skip it.
        """
        if family_id:
            await self.async_get_family_students(family_id)

    # --- Per-student data --------------------------------------------------
    async def async_get_grades(self, student_id: str) -> list[dict[str, Any]]:
        """GET /Student/{id}/Grades."""
        return self._as_list(await self._get(f"Student/{student_id}/Grades"))

    async def async_get_homework(self, student_id: str) -> list[dict[str, Any]]:
        """GET /Student/{id}/Homework."""
        return self._as_list(await self._get(f"Student/{student_id}/Homework"))

    async def async_get_missing(self, student_id: str) -> list[dict[str, Any]]:
        """GET /Student/{id}/Missing."""
        return self._as_list(await self._get(f"Student/{student_id}/Missing"))

    async def async_get_attendance(self, student_id: str) -> list[dict[str, Any]]:
        """GET /Student/{id}/Attendance."""
        return self._as_list(await self._get(f"Student/{student_id}/Attendance"))

    async def async_get_discipline(self, student_id: str) -> list[dict[str, Any]]:
        """GET /Student/{id}/Discipline (the discipline log)."""
        return self._as_list(await self._get(f"Student/{student_id}/Discipline"))

    async def async_get_student_details(self, student_id: str) -> dict[str, Any]:
        """GET /Student/{id} — profile details (grade, homeroom, etc.)."""
        data = await self._get(f"Student/{student_id}")
        return data if isinstance(data, dict) else {}

    # --- School-level ------------------------------------------------------
    async def async_get_events(self, school_id: str) -> list[dict[str, Any]]:
        """GET /School/{id}/Events (school calendar)."""
        return self._as_list(await self._get(f"School/{school_id}/Events"))

    async def async_get_cafeteria(self, school_id: str) -> dict[str, Any]:
        """GET /School/{id}/Cafeteria (lunch menu).

        The payload is an object keyed by ``MM/DD/YYYY`` date, each value a list
        of meal options — not a flat list — so return the dict as-is (an empty
        or non-object body becomes ``{}``).
        """
        data = await self._get(f"School/{school_id}/Cafeteria")
        return data if isinstance(data, dict) else {}
