# Home Assistant Integration Quality Scale — gap checklist

Tracks this integration against Home Assistant's [Integration Quality
Scale](https://developers.home-assistant.io/docs/core/integration-quality-scale/).
Tiers are cumulative: **Bronze** is the minimum bar for acceptance into
`home-assistant/core`; **Silver → Gold → Platinum** add polish.

Legend: ✅ done · 🟡 partial · ❌ to do · ➖ not applicable

> We are **not** currently pursuing core inclusion — this is a running checklist
> so the integration stays "core-ready" and keeps improving on HACS. Rule names
> are the official slugs.

## 🥉 Bronze — required for core acceptance

| Rule | Status | Note |
| --- | --- | --- |
| `config-flow` | ✅ | UI setup |
| `test-before-configure` | ✅ | Discovery validates the family list; the manual path validates the token against a student endpoint |
| `unique-config-entry` | ✅ | `async_set_unique_id` + abort |
| `config-flow-test-coverage` | ✅ | `config_flow.py` at 100% line coverage, enforced in CI |
| `runtime-data` | ✅ | `entry.runtime_data` |
| `test-before-setup` | ✅ | first refresh → `ConfigEntryNotReady`/`ConfigEntryAuthFailed` |
| `appropriate-polling` | ✅ | 60-minute minimum |
| `entity-unique-id` | ✅ | |
| `has-entity-name` | ✅ | |
| `entity-event-setup` | ✅ | coordinator + `async_on_unload` listeners |
| `common-modules` | ✅ | `coordinator.py` / `entity.py` |
| `action-setup` | ✅ | `sync_calendar` registers in `async_setup`; the handler validates a usable entry at call time |
| `dependency-transparency` | ❌ | needs the API client as a versioned PyPI library (`pysycamore`) |
| `docs-*` (install / remove / actions / description) | ❌ | needs a page on home-assistant.io |
| `brands` | 🟡 | shipped in-repo under `brand/`; core needs assets in `home-assistant/brands` |

## 🥈 Silver

| Rule | Status | Note |
| --- | --- | --- |
| `config-entry-unloading` | ✅ | |
| `reauthentication-flow` | ✅ | |
| `test-coverage` (>95%) | 🟡 | measure |
| `entity-unavailable` | ✅ | |
| `integration-owner` | ✅ | `@yieldhog` |
| `action-exceptions` | 🟡 | `sync_calendar` raises `ServiceValidationError`; audit all failure modes |
| `log-when-unavailable` | ✅ | coordinator logs once |
| `parallel-updates` | ✅ | `PARALLEL_UPDATES = 0` on every platform (coordinator-driven, read-only) |
| `stale-devices` | ✅ | `async_remove_config_entry_device` removes devices no longer configured |

## 🥇 Gold

| Rule | Status | Note |
| --- | --- | --- |
| `entity-translations` | ✅ | |
| `entity-device-class` | ✅ | timestamp / problem / measurement |
| `devices` | ✅ | per student + school + service device |
| `entity-category` | ✅ | diagnostics set |
| `dynamic-devices` | ➖ | no runtime device discovery — students are fixed at config time (a cloud service, not a hub); entities like grade sensors still appear dynamically |
| `entity-disabled-by-default` | ✅ | nothing niche is default-on: attendance/discipline are gated by fetch toggles, and health/detail sensors are `diagnostic` |
| `diagnostics` | ✅ | redacts token, student ids/names, and teacher names; academic data kept de-identified |
| `discovery` | ➖ | cloud service — no local discovery |
| `reconfiguration-flow` | ✅ | reconfigure step updates token + School ID without re-adding |
| `exception-translations` | ✅ | the `sync_calendar` action error uses a translated exception (`exceptions` in `strings.json`) |
| `repair-issues` | ✅ | a section failing for 3 refreshes in a row raises an auto-clearing Repairs card (`section_degraded`), built on the `degraded` tracking |
| `icon-translations` | ✅ | static entity icons defined in `icons.json` |
| `docs-*` (data-update / limitations / troubleshooting / examples) | ❌ | needs a home-assistant.io page (core-only; the README serves HACS users) |

## 💎 Platinum

| Rule | Status | Note |
| --- | --- | --- |
| `inject-websession` | ✅ | uses HA's shared httpx client |
| `async-dependency` | ❌ | needs the async PyPI library |
| `strict-typing` | ❌ | enforce full type hints under core's strict mypy |

## Where we stand

Bronze and Silver are complete except the three core-only levers below; **Gold is
complete except `docs-*`** (which needs a home-assistant.io page — a core concern,
not a HACS one). Platinum needs the library extraction + strict typing.

## Biggest remaining levers

1. **Extract `pysycamore`** — a versioned, CI-built, PyPI-published async library
   holding the API client + errors. Unlocks `dependency-transparency` (Bronze),
   `async-dependency` + `strict-typing` (Platinum), and makes the API reusable
   outside HA.
2. **Docs on home-assistant.io** — the `docs-*` rules across every tier.
3. **Move brand assets** to `home-assistant/brands` (core does not read the
   in-repo `brand/` folder).

Everything else is small, mechanical work that improves the integration on HACS
regardless of whether core inclusion is ever pursued.
