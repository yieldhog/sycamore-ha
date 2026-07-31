"""Constants for the Sycamore integration."""

from __future__ import annotations

DOMAIN = "sycamore"

# The current app uses the sycamoreschool.com host successfully; the docs also
# reference sycamoreeducation.com. Keep the working host as the single source.
API_BASE = "https://app.sycamoreschool.com/api/v1"

# Config / options keys
CONF_TOKEN = "token"
CONF_FAMILY_ID = "family_id"
CONF_SCHOOL_ID = "school_id"
CONF_STUDENTS = "students"
CONF_STUDENT_ID = "id"
CONF_STUDENT_NAME = "name"
CONF_FOCUS_WINDOW_DAYS = "focus_window_days"
CONF_SCAN_INTERVAL_MINUTES = "scan_interval_minutes"
# Feature toggles (options). These gate an extra API call each, so turning one
# off also stops the coordinator from fetching that endpoint.
CONF_ENABLE_ATTENDANCE = "attendance_enabled"
CONF_ENABLE_LUNCH = "lunch_enabled"

# Calendar sync (options). Per-student target calendar entities, plus an opt-in
# auto-sync that reconciles after each refresh. Empty/unset target = no sync.
CONF_CALENDAR_TARGETS = "calendar_targets"  # {student_id: calendar_entity_id}
CONF_CALENDAR_AUTOSYNC = "calendar_autosync"
CONF_CALENDAR_DAYS = "calendar_days"

# Defaults
DEFAULT_SCAN_INTERVAL_MINUTES = 60
DEFAULT_FOCUS_WINDOW_DAYS = 7
MIN_SCAN_INTERVAL_MINUTES = 60
DEFAULT_ENABLE_ATTENDANCE = True
DEFAULT_ENABLE_LUNCH = True
DEFAULT_CALENDAR_AUTOSYNC = False
DEFAULT_CALENDAR_DAYS = 14

MANUFACTURER = "Sycamore"

# Keys used in the coordinator's per-student data bundle.
DATA_NAME = "name"
DATA_GRADES = "grades"
DATA_HOMEWORK = "homework"
DATA_MISSING = "missing"
DATA_ATTENDANCE = "attendance"

# Top-level (school) key in coordinator data.
DATA_CAFETERIA = "cafeteria"
