# Roadmap

Outstanding work for `sycamore-ha`, roughly in priority order. See `CLAUDE.md`
for architecture and conventions. **Convention reminder:** add a config toggle
only for features that cost an extra API call; otherwise ship the entity normally
or `entity_registry_enabled_default = False`.

## 1. Analytics sensors (no new endpoint — computed from data already fetched)

Cheap and high-value. Ship enabled, or disabled-by-default if they feel niche.
No config toggles.

- [ ] **Overall grade average (%)** per student — mean of class percents;
      `state_class = measurement`. The best single addition.
- [ ] **Next assignment** — soonest homework; `device_class = timestamp` (or a
      date), title/subject as attributes.
- [ ] **Next test** — next `detect_kind`-flagged item; complements the
      `test_within_24h` binary sensor over a longer horizon.
- [ ] **Lowest class** — subject with the lowest current %; early warning.

Add unit tests mirroring `tests/test_init.py` (fake client → assert states).

## 2. Endpoint-backed sensors (new fetch → add an options toggle, like Attendance/Lunch)

- [ ] **GPA / statistics** — `Student/{id}/Statistics`. Official GPA/averages.
- [ ] **Last graded assignment** — `Student/{id}/Assignment_Grades`; state = most
      recent score, attrs = name/subject/date. Enables "just got an 88" automations.
- [ ] **Discipline events** — `Student/{id}/Discipline_Log`; count + records.
- [ ] **School events calendar** + "days until next day off" — school-level
      calendar endpoint (better as a `calendar` entity than a sensor).
- [ ] **Lunch as a week calendar** — upgrade the single `todays_lunch` sensor.

For each: add the fetch to `api.py`, wire into the coordinator behind the toggle,
gate the entity in its platform, add strings/translations, and a skip-fetch test.

## 3. Quality / polish

- [ ] Expand config-flow tests: reauth success, options flow, "add another"
      manual loop, `already_configured` abort.
- [ ] Confirm the `School/{id}/Cafeteria` response shape against a real account and
      tighten `SycamoreLunchSensor._todays_items` / `_entry_text` accordingly.
- [ ] Consider discovering School ID (avoid asking the user) if an endpoint exposes it.
- [ ] Add `ruff`/lint to CI.

## 4. HACS default-store submission (so users don't need a custom repo URL)

- [ ] Repo **description** + **topics** (`home-assistant`, `hacs`, `integration`).
- [ ] Add a brand icon/logo via a PR to `home-assistant/brands` (domain `sycamore`).
- [ ] Ensure a tagged **release** exists (HACS installs from releases/tags).
- [ ] Green `hassfest` + `hacs/action` (already in CI).
- [ ] Open the PR to add `yieldhog/sycamore-ha` to the HACS default integration list.
