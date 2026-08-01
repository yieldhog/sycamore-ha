# CLAUDE.md — context for AI sessions working on this repo

This file orients a fresh Claude Code session. Read it first.

## What this is

A **native Home Assistant custom integration** (HACS-installable) for the
[Sycamore School](https://sycamoreleaf.com/products/sycamore-school/) platform.
HA domain: **`sycamore`**. It polls the Sycamore API and exposes each child's
grades, homework/tests, missing work, attendance, and the school lunch menu as
first-class HA entities (device per student).

It was extracted from **`sycamore-dash`** (a self-hosted FastAPI dashboard +
e-ink display). That project keeps the PWA/e-ink rendering; this repo is only
the data layer, done the HA-native way (no MQTT bridge, no SQLite).

## Architecture (`custom_components/sycamore/`)

| File | Role |
| --- | --- |
| `__init__.py` | Setup/unload; creates the coordinator; `type SycamoreConfigEntry = ConfigEntry[...]`, stored in `entry.runtime_data`. Reloads on options change. |
| `const.py` | `DOMAIN`, config/option keys, defaults, data-bundle keys. |
| `helpers.py` | Pure functions (no HA import): `clean_subject_name`, `detect_kind`, `strip_html`, `subject_icon`, `parse_due_date`, `to_float`. Ported from sycamore-dash. |
| `api.py` | `SycamoreClient` over HA's shared httpx client. Raises `SycamoreAuthError` (401/403) and `SycamoreConnectionError`. Treats 204/empty as `[]`. |
| `coordinator.py` | `SycamoreDataUpdateCoordinator`: fetches all students concurrently, shapes data, computes grade trend in memory (no DB). Auth → `ConfigEntryAuthFailed`; other → `UpdateFailed`. |
| `config_flow.py` | Token → Family ID discovery (`/Family/{id}/Students`) → pick students; manual fallback; reauth; options (interval, focus window, Attendance/Lunch toggles). |
| `entity.py` | `SycamoreStudentEntity` (device per student) + `SycamoreSchoolEntity`. |
| `sensor.py` | Per-class letter grade + numeric `%` sensor; missing/upcoming/attendance counts; school-level lunch sensor. Grade sensors added dynamically as classes appear. |
| `binary_sensor.py` | `has_missing_work`, `test_within_24h`. |
| `calendar.py` | Homework/tests as due-date events. |
| `todo.py` | Missing work as a read-only to-do list. |
| `diagnostics.py` | Redacted entry + coordinator dump. |

Coordinator data shape: `{"students": {sid: {name, grades, homework, missing,
attendance}}, "cafeteria": [...] | None}`.

## Key design decisions (and why)

- **Native entities, not MQTT.** The integration *is* the HA data source; the old
  MQTT publish + SQLite trend store are gone (HA's recorder gives history).
- **Trend without a DB.** Coordinator keeps the previous poll's per-class number;
  each refresh tags `up`/`down`/`stable`.
- **Numeric `%` sensor per class** (state_class `measurement`) so grade
  percentage is graphable / kept in long-term statistics; the letter grade is a
  separate text sensor.
- **Config options only when they save work.** Attendance and Lunch each hit
  their own endpoint, so they get options toggles that *gate the fetch*. Purely
  cosmetic on/off should instead use `entity_registry_enabled_default = False`
  (HA-native per-entity disable) — do NOT add config toggles for those.
- **No hardcoded student names.** Everything is discovered or user-entered.

## Sycamore API notes

- Base: `https://app.sycamoreschool.com/api/v1` (docs also cite
  `app.sycamoreeducation.com`; the school host above is what works).
- Auth: personal access token (My Organizer → Applications), `Authorization:
  Bearer <token>`. No OAuth redirect flow.
- Endpoints used: `Student/{id}` (details) `|Grades|Homework|Missing|Attendance|
  Discipline`, `Family/{id}/Students` (discovery), `School/{id}/Cafeteria|Events`.
- Endpoint names are per the live sandbox (app.sycamoreschool.com/oauth/sandbox),
  which is authoritative — the GitHub docs list some that don't exist. E.g. it's
  `Student/{id}/Discipline` (**not** `Discipline_Log`), and there's no
  `Assignment_Grades`; assignment-level grades are `Student/{id}/Classes/{cid}/
  Grades` (needs the class list first; response is keyed by class-type unless
  `format=1`, and `quarter=0` returns all terms). `Statistics` exists but likely
  needs a higher token scope. Official docs: github.com/SycamoreEducation/SycamoreSchoolAPI.

## Dev & testing

```bash
python3.13 -m venv .venv
.venv/bin/pip install -r requirements_test.txt   # pulls HA + test harness
.venv/bin/python -m pytest -q                     # 27 tests
```

- Tests use `pytest-homeassistant-custom-component`; `pyproject.toml` sets
  `asyncio_mode = auto`. Patch `custom_components.sycamore.SycamoreClient` (setup)
  or `...config_flow.SycamoreClient` (flow) with a fake/AsyncMock.
- CI (`.github/workflows/validate.yml`) runs **hassfest**, **HACS**, and pytest.
- Requires Python 3.12+ (uses the `type X = ...` alias). `python` may be 3.11
  locally — compile/run with `python3.12`/`python3.13`.

## Gotchas

- `clean_subject_name` alternation is ordered `Grade-` before the `6H ` rule on
  purpose (so "2nd Grade-Science" → "Science"); don't revert it.
- Grade sensors are created dynamically via a coordinator listener; new classes
  appear on the next refresh without a reload.

## Pushing changes

GitHub tool/proxy access is **per-session scoped**. To push here, the session
must have `yieldhog/sycamore-ha` in its allowed repositories (set in the Claude
Code web environment settings) — it can't be added mid-session. Otherwise, hand
off changes as an archive.
