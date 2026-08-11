# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.7] - 2026-08-11

### Fixed

- **Transient HTTP 500s no longer break setup.** Sycamore's API intermittently
  500s a single endpoint — most often under the burst of concurrent requests one
  refresh makes (grades + homework + missing + details at once) — which caused
  *"Failed setup, will retry: Student/{id}/Homework returned HTTP 500"* (and the
  same on Grades). Three layers now handle this:
  - **Concurrency cap (root-cause fix).** A refresh no longer fires every
    endpoint for every student at once — in-flight requests per account are
    capped (currently 2), so the burst that triggers Sycamore's 500s never
    happens. Refreshes are hourly, so the small serialization cost is invisible.
  - **Retry with backoff.** Any retryable server-side status
    (429/500/502/503/504) that still slips through is retried a few times with a
    short exponential backoff, so a momentary blip resolves itself and the data
    actually loads.
  - **Graceful degradation.** If a section *still* errors after retries, only
    that section degrades to empty (with a logged warning) instead of failing the
    whole integration. A genuine connectivity failure still fails the refresh so
    it retries, and auth errors still trigger reauth — so an outage isn't
    silently masked as "no data."

## [0.1.6] - 2026-08-11

### Changed

- **README renders correctly on the HACS info page.** The brand image used a
  relative path (`assets/brand/logo.png`), which HACS resolved against the Home
  Assistant host (e.g. `https://<your-ha>/hacs/…`) and 404'd; it now uses an
  absolute `raw.githubusercontent.com` URL so it loads wherever the README is
  shown. Install steps lead with the HACS **default store** (custom-repository
  steps kept as a collapsible fallback), the HACS badge reads **Default**, and
  **Release** / **minimum-HA-version** badges were added.

  *Docs-only — no functional change. Cut as a release because HACS renders the
  README from the latest published release, not the default branch, so the image
  fix only reaches users once it ships in a release.*

## [0.1.5] - 2026-08-01

### Fixed

- **Discipline endpoint** — the discipline log is fetched from
  `Student/{id}/Discipline`, not `Discipline_Log` (which 404s). The old path
  would have failed the refresh for anyone who enabled the (off-by-default)
  discipline toggle. Verified against the live API sandbox.

## [0.1.4] - 2026-08-01

### Added

- **Integration health entities** on a new **Sycamore** service device:
  - **Last updated** — a timestamp sensor showing the last *successful* poll, so
    you can tell fresh data from stale (and automate `if last update > Nh → notify`).
  - **Status** — a problem binary sensor that turns **on** when a refresh fails,
    with the error as an attribute.
  Both are diagnostic and stay **available even during a failure** (a normal
  coordinator entity would go unavailable exactly when you'd want the signal),
  so an off-season *Unknown* on the grade sensors reads as "no data yet," not
  "broken."

## [0.1.3] - 2026-08-01

### Added

- **School events calendar** — `School/{id}/Events` as a **School events** calendar
  entity (all-day and timed events) plus a **Next school event** timestamp sensor.
  Gated by a *School events calendar* options toggle and needs a School ID (like lunch).
- **Student profile details** — the device now shows the student's **grade level** as
  its model, plus **Grade level** and **Homeroom teacher** diagnostic sensors. Fetched
  with the normal refresh and degrades quietly if the token can't read the profile.

## [0.1.2] - 2026-08-01

### Added

- **Discipline events sensor** — a per-student sensor backed by
  `Student/{id}/Discipline_Log`, showing a count with the raw records as a
  `records` attribute. It's **off by default** (niche and sensitive); enable it
  with the *Discipline log sensor* toggle in the integration options, which also
  gates the extra API call.

### Internal

- Added a pinned `ruff` lint job to CI, and expanded the config-flow test suite
  (reauth success, options flow, manual "add another" loop, already-configured
  abort).

## [0.1.1] - 2026-07-31

Packaging release so the Sycamore brand renders in Home Assistant. No changes to
grades/homework/calendar behaviour.

### Added

- **Brand icon and logo** shipped in-repo at `custom_components/sycamore/brand/`
  (`icon.png` 256×256, `logo.png` 512×248). Home Assistant 2026.3+ and HACS read the
  brand from the integration's own folder; `home-assistant/brands` no longer accepts
  custom-integration submissions (Feb 2026 Brands Proxy API).

### Changed

- Enabled the HACS action's brand validation (dropped the temporary `ignore: brands`).
- Added this changelog and corrected the reported manifest version.

## [0.1.0] - 2026-07-31

First stable release. A native Home Assistant integration for the Sycamore School
platform: it polls the Sycamore API and exposes each child's grades, homework/tests,
missing work, attendance, and the school lunch menu as first-class Home Assistant
entities, with one device per student. HACS-installable; configured entirely in the UI.

### Added

- **Setup & config** — UI config flow with automatic student discovery (via Family
  ID), manual student entry fallback, a reauthentication flow, and per-integration
  options (poll interval, focus window, Attendance/Lunch toggles). Redacted
  diagnostics. One device per student.
- **Grades** — per-class sensor with the letter grade as state, a companion numeric
  `%` sensor (`measurement` state class for long-term statistics/graphs), and an
  `up`/`down`/`stable` trend computed in memory (no database).
- **Analytics** (computed from data already fetched) — grade average, lowest class,
  next assignment, and next test (timestamp sensors).
- **Work** — Homework calendar (assignments/tests by due date, `[TEST]`/`[QUIZ]`
  labelled), a read-only Missing work to-do list, *Has missing work* and *Test within
  24 hours* binary sensors, and *Upcoming work* / *Upcoming tests* count sensors over
  a configurable focus window.
- **Attendance & lunch** — an Attendance sensor, and an optional Today's lunch sensor
  plus a Lunch calendar (requires a School ID).
- **Calendar sync** — the `sycamore.sync_calendar` service mirrors upcoming
  assignments, tests, and quizzes into a writable calendar (e.g. Google): it adds new
  work and removes cancelled or changed items, only ever touching events it created
  (identified by a hidden `[sycamore-sync:<student>:<hash>]` tag). A per-student
  target calendar can be set in the options, with opt-in auto-sync after each refresh;
  student-scoped tags let two children safely share one calendar.

### Notes

- Requires Home Assistant **2024.12.0** or newer.
- Polling is capped at a **60-minute minimum** (Sycamore data changes at most daily).
- Calendar deletion works on any target that supports it (Google does); calendars
  without delete support still receive new events, and stale ones are logged.

## [0.1.0b1] - 2026-07-31

Initial beta: core integration (setup/discovery/reauth, per-class grades and trend,
homework calendar, missing-work to-do, binary sensors, attendance, and the optional
lunch sensor/calendar).

[0.1.7]: https://github.com/yieldhog/sycamore-ha/releases/tag/v0.1.7
[0.1.6]: https://github.com/yieldhog/sycamore-ha/releases/tag/v0.1.6
[0.1.5]: https://github.com/yieldhog/sycamore-ha/releases/tag/v0.1.5
[0.1.4]: https://github.com/yieldhog/sycamore-ha/releases/tag/v0.1.4
[0.1.3]: https://github.com/yieldhog/sycamore-ha/releases/tag/v0.1.3
[0.1.2]: https://github.com/yieldhog/sycamore-ha/releases/tag/v0.1.2
[0.1.1]: https://github.com/yieldhog/sycamore-ha/releases/tag/v0.1.1
[0.1.0]: https://github.com/yieldhog/sycamore-ha/releases/tag/v0.1.0
[0.1.0b1]: https://github.com/yieldhog/sycamore-ha/releases/tag/v0.1.0b1
