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
| `action-setup` | 🟡 | services register from `async_setup_entry`; core prefers `async_setup` with entry validated inside |
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
| `dynamic-devices` | 🟡 | entities added dynamically; devices are per configured student |
| `entity-disabled-by-default` | 🟡 | consider disabling niche entities by default |
| `diagnostics` | ✅ | redacts token, student ids/names, and teacher names; academic data kept de-identified |
| `discovery` | ➖ | cloud service — no local discovery |
| `reconfiguration-flow` | ✅ | reconfigure step updates token + School ID without re-adding |
| `repair-issues` | ❌ | surface e.g. missing-scope via the repairs/issue registry |
| `icon-translations` | ❌ | move inline `_attr_icon` → `icons.json` |
| `exception-translations` | ❌ | translated exception messages |
| `docs-*` (data-update / limitations / troubleshooting / examples) | ❌ | |

## 💎 Platinum

| Rule | Status | Note |
| --- | --- | --- |
| `inject-websession` | ✅ | uses HA's shared httpx client |
| `async-dependency` | ❌ | needs the async PyPI library |
| `strict-typing` | ❌ | enforce full type hints under core's strict mypy |

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
