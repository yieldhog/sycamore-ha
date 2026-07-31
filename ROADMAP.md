# Roadmap

Outstanding work for `sycamore-ha`, roughly in priority order. See `CLAUDE.md`
for architecture and conventions. **Convention reminder:** add a config toggle
only for features that cost an extra API call; otherwise ship the entity normally
or `entity_registry_enabled_default = False`.

## Recently shipped (merged)

- **CI** — `validate.yml` runs hassfest, the HACS action, and pytest (Python 3.13);
  green on `main`.
- **Lunch week calendar** — real `{MM/DD/YYYY: [meals]}` cafeteria shape parsed; a
  `Lunch` calendar (one all-day event per day) plus a richer `todays_lunch` sensor.
- **Upcoming tests sensor** + `is_test`/`kind` on the *Upcoming work* attribute, so
  the focus-window data separates tests from assignments, by class.
- **Token-scope error handling** — a missing Families scope (HTTP 404) now shows a
  clear message + manual-entry hint instead of "cannot connect."
- **Poll interval** default and minimum raised to 60 minutes.
- **Missing-work resilience** — items without a `Title` are no longer dropped.
- **Field shapes verified** against a live account and the sycamore-dash source
  (Homework `Title`/`ClassName`/`DueDate`/`Description` confirmed).

## 1. Analytics sensors (no new endpoint — computed from data already fetched)

Cheap and high-value. Ship enabled, or disabled-by-default if niche. No toggles.

- [x] **Overall grade average (%)** per student — mean of class percents;
      `state_class = measurement`.
- [x] **Lowest class** — subject with the lowest current %; early warning.
- [x] **Next assignment** — soonest homework; `device_class = timestamp`,
      title/subject/kind as attributes.
- [x] **Next test** — soonest test/quiz; `device_class = timestamp` (plus the
      *Upcoming tests* count/list sensor over the focus window).

All four are computed from grades/homework already fetched (fields confirmed
against the dash source) and unit-tested in `tests/test_init.py`.

## 2. Endpoint-backed sensors (new fetch → add an options toggle, like Attendance/Lunch)

- [ ] **GPA / statistics** — `Student/{id}/Statistics`. Blocked: returns
      `401 insufficient_scope` (needs the `families` scope the family-portal token
      lacks). Needs a higher-privilege token; also, its 401 would trip our auth
      handler, so it needs isolated error handling if added.
- [ ] **Last graded assignment** — `Student/{id}/Assignment_Grades`; state = most
      recent score, attrs = name/subject/date. Enables "just got an 88" automations.
- [ ] **Discipline events** — `Student/{id}/Discipline_Log`; count + records.
- [ ] **School events calendar** + "days until next day off" — school-level
      calendar endpoint (better as a `calendar` entity than a sensor).
- [x] **Lunch as a week calendar** — shipped.

For each: add the fetch to `api.py`, wire into the coordinator behind the toggle,
gate the entity in its platform, add strings/translations, and a skip-fetch test.

## 3. Calendar sync — write Sycamore items into a writable calendar

Designed earlier this session; not yet built. A `sycamore.sync_calendar` service
that reconciles (create / update / delete) upcoming assignments & tests into a
target calendar. Full CRUD works into HA's **Local Calendar**; Google via HA is
create-only (no update/delete), so a true mirror there needs a direct Google API.

- [ ] Build the reconciliation service (Local Calendar target first; capability-gate
      update/delete; tag our events so user events are never touched).
- [ ] Optional auto-sync on each coordinator refresh (target stored on the entry).

## 4. Quality / polish

- [ ] Expand config-flow tests: reauth success, options flow, "add another"
      manual loop, `already_configured` abort.
- [x] Confirm the `School/{id}/Cafeteria` response shape against a real account —
      it's `{MM/DD/YYYY: [{MealID, MealName, MealDesc}]}` (a dict, not a list).
- [ ] Verify Homework/Missing item shape against a live term (summer = empty now);
      adopt an explicit test/quiz field if the payload exposes one, instead of the
      title heuristic.
- [ ] Consider discovering School ID (avoid asking the user) if an endpoint exposes it.
- [ ] Add `ruff`/lint to CI (dead imports already cleaned, so it should start green).

## 5. HACS default-store submission (so users don't need a custom repo URL)

- [x] Repo **description** + **topics**.
- [x] Green `hassfest` + `hacs/action` + pytest (`validate.yml`).
- [ ] Add a brand icon/logo via a PR to `home-assistant/brands` (domain `sycamore`).
- [ ] Ensure a tagged **release** exists (HACS installs from releases/tags).
- [ ] Open the PR to add `yieldhog/sycamore-ha` to the HACS default integration list.
