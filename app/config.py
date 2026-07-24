"""
Central configuration. Swap DB_PATH for a real Postgres DSN in production
by changing storage/db.py's connection logic.
"""

from pathlib import Path
from dotenv import load_dotenv
import os

BASE_DIR = Path(__file__).resolve().parent.parent

# Loads variables from a .env file in the project root (e.g. SLACK_WEBHOOK_URL)
# into the environment. Safe to call even if .env doesn't exist.
load_dotenv(BASE_DIR / ".env")

# If unset, the notifier falls back to printing to console instead of
# sending to Slack - so the app still runs fine without Slack configured.
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

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
