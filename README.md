<p align="center">
  <img src="https://raw.githubusercontent.com/yieldhog/sycamore-ha/main/assets/brand/logo.png" alt="Sycamore School" width="320">
</p>

# Sycamore School — Home Assistant integration

[![hacs][hacs-badge]][hacs]
[![Validate][validate-badge]][validate]

A native Home Assistant integration for the [Sycamore School][sycamore] platform.
It pulls your children's **grades, homework, tests, missing work, attendance**, and the
school **lunch menu** into first-class Home Assistant entities — a device per student,
with sensors, a homework **calendar**, and a missing-work **to-do list**.

Everything is polled directly from Sycamore's official API and exposed locally in HA, so
you can build dashboards and automations ("Nicholas has a test tomorrow", "someone has
missing work") without any MQTT bridge or external service.

> **Unofficial.** This project is not affiliated with or endorsed by Sycamore Education.
> It uses the public [Sycamore School API][sycamore-api].

---

## Features

- **One device per student**, so entities group cleanly.
- **Per-class grade sensors** — letter grade as state, percent + `up`/`down`/`stable`
  trend as attributes (trend is computed live from the previous poll; no database).
- **Homework calendar** — every assignment on its due date, with `[TEST]`/`[QUIZ]`
  prefixes inferred from the title, ready for the calendar card and automations.
- **Missing-work to-do list** + a **Has missing work** binary sensor.
- **Test within 24 hours** binary sensor for "study tonight" automations.
- **Upcoming work** and **Missing work** count sensors.
- **Attendance** sensor (absences/tardies as your school reports them).
- **Today's lunch** sensor (optional, needs a School ID).
- **UI configuration** with automatic student discovery, a reauthentication flow, and
  options for poll interval and focus window.

## Installation

Requires Home Assistant **2024.12** or newer.

### HACS (recommended)

**Sycamore School** is in the default HACS store:

1. Open **HACS** in Home Assistant.
2. Search for **Sycamore School** and click **Download**.
3. Restart Home Assistant.

<details>
<summary>Not showing up yet? Add it as a custom repository</summary>

If the default-store listing hasn't reached your instance yet, you can add the
repo directly:

1. In HACS, open the three-dot menu → **Custom repositories**.
2. Add `https://github.com/yieldhog/sycamore-ha` with category **Integration**.
3. Install **Sycamore School**, then restart Home Assistant.

</details>

### Manual

Copy `custom_components/sycamore` into your Home Assistant `config/custom_components/`
directory and restart.

## Configuration

Add the integration under **Settings → Devices & Services → Add Integration → Sycamore
School**. You'll be asked for:

| Field | Required | Notes |
| --- | --- | --- |
| **Access token** | Yes | Create one in Sycamore under **My Organizer → Applications**. |
| **Family ID** | No | When provided, students are **discovered automatically** and you just pick which to add. Find it in your family portal. Needs the token's **Families** scope — if discovery fails, leave this blank and add students manually (per-student data uses different endpoints that don't need that scope). |
| **School ID** | No | Only needed to enable the **Today's lunch** sensor. |

If you leave Family ID blank, you can add students by hand (Student ID + display name).

**Options** (gear icon on the integration):

- **Update interval** — how often to poll Sycamore, in minutes (minimum 60, default 60). Sycamore data changes at most daily, so there's no benefit to polling more often.
- **Focus window** — how many days ahead to look, `1`–`31`, **default 7**. This is the
  "next N days" horizon: the *Upcoming work* sensor reports the assignments due within
  this window (its count is the state; the assignments are listed in its attributes).
  Set it to `14` for a two-week view, and so on.
- **Attendance**, **Lunch**, **Discipline**, and **School events** toggles — each gates
  its own endpoint, so turning one off stops the coordinator polling it and removes its
  entities. Discipline is **off by default** (niche and sensitive); School events needs a
  School ID and adds a *School events* calendar + *Next school event* sensor.

Every other sensor can be enabled or disabled individually from its own entity settings
in Home Assistant.

## Entities

Per student (device):

| Entity | Platform | State |
| --- | --- | --- |
| `<Class>` | sensor | Letter grade; attrs: `percent`, `trend`, `updated` |
| `<Class> percent` | sensor | Numeric grade `%` (`measurement` state class → long-term history/graphs) |
| Grade average | sensor | Mean of the class percents (`measurement` → long-term history) |
| Lowest class | sensor | Subject with the lowest current %; `percent`/`letter`/`trend` as attributes |
| Next assignment | sensor | Due date of the soonest assignment (`timestamp`); title/subject/kind as attributes |
| Next test | sensor | Due date of the soonest test/quiz (`timestamp`); title/subject/kind as attributes |
| Missing work | sensor | Count of missing assignments |
| Upcoming work | sensor | Count of assignments due within the focus window (next 7 days by default); `assignments` attr lists them by class with an `is_test`/`kind` flag |
| Upcoming tests | sensor | Count of tests/quizzes due within the focus window; `tests` attr lists them by class (title, subject, due, kind) |
| Attendance events | sensor | Count of attendance records |
| Discipline events | sensor | Count of discipline-log records (`records` attr); **off by default** — enable in options |
| Grade level | sensor | The student's grade (e.g. `7th`); diagnostic |
| Homeroom teacher | sensor | Homeroom teacher name; diagnostic |
| Has missing work | binary_sensor | `on` when anything is missing |
| Test within 24 hours | binary_sensor | `on` when a test/quiz is due within a day |
| Homework | calendar | Assignments and tests by due date |
| Missing work | todo | Read-only checklist of missing assignments |

School-level (only with a School ID):

| Entity | Platform | State |
| --- | --- | --- |
| Today's lunch | sensor | Today's meal names; `meals` attr = today's items, `menu` attr = the full pulled week (dates + meals) |
| Lunch | calendar | The pulled cafeteria menu, one all-day event per day (meal names as summary, full details in the description) |
| School events | calendar | The school calendar — all-day and timed events (title, start/end) |
| Next school event | sensor | Start time of the next school event (`timestamp`); title/all-day as attributes |

The device for each student also shows their **grade level** as the device model, pulled
from the student profile (no toggle — it's fetched with the rest and degrades quietly if
your token can't read it).

### Integration health (a "Sycamore" service device)

| Entity | Platform | State |
| --- | --- | --- |
| Last updated | sensor | Timestamp of the last **successful** poll (diagnostic) |
| Status | binary_sensor | `problem` — **on** when the last refresh failed; `error` attribute has the reason (diagnostic) |

Both stay **available even during a failure**, so you can automate on them (e.g. notify
if *Status* is on, or if *Last updated* is more than a few hours old).

> **`Unknown` is not "broken".** Between terms (or before any data posts) sensors like
> *Grade average* and *Next test* read `Unknown` — they're alive, there's just no value
> yet. That's different from `Unavailable` (which only happens on a real error). If you
> ever want to be sure, check the **Status** sensor: green there means the integration is
> fine and the `Unknown`s just mean "no school data right now."

## Automation examples

Notify when a test is due within a day:

```yaml
automation:
  - alias: Test tomorrow
    trigger:
      - platform: state
        entity_id: binary_sensor.nicholas_test_within_24_hours
        to: "on"
    action:
      - service: notify.family
        data:
          message: >-
            {{ state_attr('binary_sensor.nicholas_test_within_24_hours', 'tests')
               | map(attribute='title') | join(', ') }} — test coming up!
```

Nudge in the evening if there's missing work:

```yaml
automation:
  - alias: Missing work reminder
    trigger:
      - platform: time
        at: "18:00:00"
    condition:
      - condition: state
        entity_id: binary_sensor.nicholas_has_missing_work
        state: "on"
    action:
      - service: notify.family
        data:
          message: >-
            Nicholas has {{ states('sensor.nicholas_missing_work') }} missing assignment(s).
```

## Sync assignments to a calendar

The integration can mirror upcoming assignments, tests, and quizzes into a writable
calendar — e.g. a Google calendar you've added to Home Assistant. It only manages
events it created (each tagged with `[sycamore-sync:<student>:<hash>]` in the
description), so your own events are never touched: new work is **added**, and if an
item's due date changes or it's cancelled the stale event is **removed**. Because the
tag carries the student, **two children can safely share one calendar** — syncing one
never disturbs the other's events.

**Nothing syncs until you set it up** — you choose the calendars. The integration
never creates calendars; the writable `calendar.*` entities come from *your* Google
(or Local Calendar, CalDAV, …) integration.

### Per-child mapping (recommended)

In the integration's **Configure → Options**, each child gets a **calendar picker**
(labelled by name). Point a child at a calendar to sync them; **leave it blank to not
sync** that child. Then either:

- turn on **"Auto-sync calendars after each refresh"** and it stays updated
  automatically after every poll — no automation needed; or
- leave auto-sync off and call the service yourself (below) when you want.

Different kids can go to different calendars, or several can share one.

### The `sycamore.sync_calendar` service (manual / power use)

| Field | Required | Default | Notes |
| --- | --- | --- | --- |
| `target_calendar` | No | — | Overrides the per-child mapping for the run. If omitted, each child's mapped calendar is used. |
| `student` | No | all | Limit to specific children (by name or id). |
| `days` | No | 14 | How many days ahead to sync. |
| `prefix_student_name` | No | `true` | Prefix each event with the student's name. |

```yaml
# Only needed if you leave auto-sync off. Uses each child's mapped calendar:
automation:
  - alias: Sync school work
    trigger:
      - platform: time_pattern
        hours: "/6"
    action:
      - service: sycamore.sync_calendar
        data:
          days: 14
```

Deletion works on any calendar that supports it (Google does); on calendars without
delete support, new events are still added but stale ones are logged instead of
removed.

## Roadmap

Additional Sycamore endpoints that could become entities: per-assignment scores
(`Assignment_Grades`), GPA/statistics, and the discipline log, plus a full lunch-menu
calendar.

See [`ROADMAP.md`](ROADMAP.md) for the full, prioritized list.

[sycamore]: https://sycamoreleaf.com/products/sycamore-school/
[sycamore-api]: https://github.com/SycamoreEducation/SycamoreSchoolAPI
[dash]: https://github.com/yieldhog/sycamore-dash
[hacs]: https://hacs.xyz
[hacs-badge]: https://img.shields.io/badge/HACS-Default-41BDF5.svg
[validate]: https://github.com/yieldhog/sycamore-ha/actions/workflows/validate.yml
[validate-badge]: https://github.com/yieldhog/sycamore-ha/actions/workflows/validate.yml/badge.svg
