"""
Central configuration. Swap DB_PATH for a real Postgres DSN in production
by changing storage/db.py's connection logic.
"""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DB_PATH = BASE_DIR / "alert_intelligence.db"
RUNBOOKS_PATH = BASE_DIR / "data" / "runbooks.yaml"

# Alerts within this many seconds of each other, on the same/related service,
# are considered candidates for the same incident.
CORRELATION_WINDOW_SECONDS = 300

# Minimum confidence score (0-100) required before remediation is even
# suggested. Below this, we just notify with context and no suggestion.
MIN_CONFIDENCE_FOR_SUGGESTION = 40

# Minimum confidence AND the action must be marked safe_to_automate
# before we auto-run remediation instead of merely suggesting it.
MIN_CONFIDENCE_FOR_AUTOMATION = 85
