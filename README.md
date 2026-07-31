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

1. In HACS, open the three-dot menu → **Custom repositories**.
2. Add `https://github.com/yieldhog/sycamore-ha` with category **Integration**.
3. Install **Sycamore School**, then restart Home Assistant.

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
- **Attendance** and **Lunch** toggles — turning one off stops the coordinator from
  polling that endpoint and removes its entities.

Every other sensor can be enabled or disabled individually from its own entity settings
in Home Assistant.

## Entities

Per student (device):

| Entity | Platform | State |
| --- | --- | --- |
| `<Class>` | sensor | Letter grade; attrs: `percent`, `trend`, `updated` |
| `<Class> percent` | sensor | Numeric grade `%` (`measurement` state class → long-term history/graphs) |
| Missing work | sensor | Count of missing assignments |
| Upcoming work | sensor | Count of assignments due within the focus window (next 7 days by default) |
| Attendance events | sensor | Count of attendance records |
| Has missing work | binary_sensor | `on` when anything is missing |
| Test within 24 hours | binary_sensor | `on` when a test/quiz is due within a day |
| Homework | calendar | Assignments and tests by due date |
| Missing work | todo | Read-only checklist of missing assignments |

School-level (only with a School ID): **Today's lunch** sensor.

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

## Roadmap

Additional Sycamore endpoints that could become entities: per-assignment scores
(`Assignment_Grades`), GPA/statistics, and the discipline log, plus a full lunch-menu
calendar.

See [`ROADMAP.md`](ROADMAP.md) for the full, prioritized list.

## Credits

Grew out of [`sycamore-dash`][dash], a self-hosted family grades dashboard and e-ink
display. This integration extracts its data layer into native Home Assistant.

[sycamore]: https://sycamoreleaf.com/products/sycamore-school/
[sycamore-api]: https://github.com/SycamoreEducation/SycamoreSchoolAPI
[dash]: https://github.com/yieldhog/sycamore-dash
[hacs]: https://hacs.xyz
[hacs-badge]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg
[validate]: https://github.com/yieldhog/sycamore-ha/actions/workflows/validate.yml
[validate-badge]: https://github.com/yieldhog/sycamore-ha/actions/workflows/validate.yml/badge.svg
