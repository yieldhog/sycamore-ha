# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[0.1.2]: https://github.com/yieldhog/sycamore-ha/releases/tag/v0.1.2
[0.1.1]: https://github.com/yieldhog/sycamore-ha/releases/tag/v0.1.1
[0.1.0]: https://github.com/yieldhog/sycamore-ha/releases/tag/v0.1.0
[0.1.0b1]: https://github.com/yieldhog/sycamore-ha/releases/tag/v0.1.0b1
