# Roadmap

Outstanding work for `sycamore-ha`, roughly in priority order. See `CLAUDE.md`
for architecture and conventions. **Convention reminder:** add a config toggle
only for features that cost an extra API call; otherwise ship the entity normally
or `entity_registry_enabled_default = False`.

## Recently shipped (merged)

- **Calendar sync service** — `sycamore.sync_calendar` mirrors assignments, tests,
  and quizzes into a writable calendar; it creates new items and deletes stale ones
  (changed due date or cancelled), only ever touching events it tagged. Reconciler
  and full lifecycle unit-tested, and **live-validated against a real Google
  calendar** (create → tag round-trip → delete → due-date change all confirmed).
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
- [x] **Discipline events** — `Student/{id}/Discipline_Log`; opt-in options toggle
      (off by default) gates the fetch and a per-student *Discipline events* count
      sensor (records exposed as an attribute).
- [x] **School events calendar** — `School/{id}/Events` as a `calendar` entity
      (all-day + timed) plus a *Next school event* timestamp sensor, gated by a
      toggle + School ID. ("Days until next day off" isn't derivable — the feed
      has no no-school flag — so that piece is dropped.)
- [x] **Student details** — `Student/{id}` enriches the device (grade level as the
      model) and adds *Grade level* + *Homeroom teacher* diagnostic sensors;
      fetched with the core refresh and degrades quietly if the token can't read it.
- [x] **Lunch as a week calendar** — shipped.

For each: add the fetch to `api.py`, wire into the coordinator behind the toggle,
gate the entity in its platform, add strings/translations, and a skip-fetch test.

## 3. Calendar sync — write Sycamore items into a writable calendar

Core shipped (PR #10) and live-validated against a real Google calendar. Note
learned while building: HA exposes only `create_event`/`get_events` as calendar
*services* (delete/update are frontend-websocket only), so the service reads and
deletes through the target calendar entity's own methods — which works for any
calendar that advertises `DELETE_EVENT`, Google included.

- [x] Build the reconciliation service — `sycamore.sync_calendar` mirrors
      assignments/tests/quizzes into a target calendar: creates new items and
      deletes stale ones (via the calendar entity's own methods, since HA has no
      delete *service*), only touching events it tagged. Works with Google.
- [x] **Per-student calendar mapping + opt-in auto-sync** — each child gets a
      calendar picker in Options (blank = don't sync); an "auto-sync after each
      refresh" toggle (default off) reconciles automatically. Tags are
      student-scoped (`[sycamore-sync:<student>:<hash>]`) so children can share a
      calendar safely; the service also takes an optional `student` filter and an
      optional `target_calendar` override.

## 4. Quality / polish

- [x] Expand config-flow tests: reauth success, options flow, "add another"
      manual loop, `already_configured` abort.
- [x] Confirm the `School/{id}/Cafeteria` response shape against a real account —
      it's `{MM/DD/YYYY: [{MealID, MealName, MealDesc}]}` (a dict, not a list).
- [ ] Verify Homework/Missing item shape against a live term (summer = empty now);
      adopt an explicit test/quiz field if the payload exposes one, instead of the
      title heuristic.
- [ ] Consider discovering School ID (avoid asking the user) if an endpoint exposes it.
- [x] Add `ruff`/lint to CI — a pinned `ruff check` job runs in `validate.yml`.

## 5. HACS default-store submission (so users don't need a custom repo URL)

- [x] Repo **description** + **topics**.
- [x] Green `hassfest` + `hacs/action` + pytest (`validate.yml`).
- [x] **Brand icon/logo** — shipped in-repo at `custom_components/sycamore/brand/`
      (`icon.png` 256×256, `logo.png` 512×248). `home-assistant/brands` no longer
      accepts custom-integration PRs (Feb 2026 Brands Proxy API); HA 2026.3+ and HACS
      now read a local `brand/` folder, so `ignore: brands` was dropped from CI.
- [x] Ensure a **release** exists — `v0.1.0` stable published.
- [x] Open the PR to add `yieldhog/sycamore-ha` to the HACS default integration list.
