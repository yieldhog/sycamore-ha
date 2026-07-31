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

# Defaults
DEFAULT_SCAN_INTERVAL_MINUTES = 30
DEFAULT_FOCUS_WINDOW_DAYS = 7
MIN_SCAN_INTERVAL_MINUTES = 5

MANUFACTURER = "Sycamore"

# Keys used in the coordinator's per-student data bundle.
DATA_NAME = "name"
DATA_GRADES = "grades"
DATA_HOMEWORK = "homework"
DATA_MISSING = "missing"
DATA_ATTENDANCE = "attendance"

# Top-level (school) key in coordinator data.
DATA_CAFETERIA = "cafeteria"
