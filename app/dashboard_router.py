"""
Dashboard router: a small, self-contained addition that serves a visual
incident dashboard without touching any existing pipeline logic.

Wired into the app with two lines in main.py (see README/instructions) -
kept as its own router so it can be removed or extended independently.
"""

from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from app.storage import db
from app.models.schemas import Incident

router = APIRouter()

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@router.get("/api/incidents", response_model=list[Incident])
def list_incidents(limit: int = 50):
    """Returns the most recent incidents, newest first - what the
    dashboard polls to render its incident feed."""
    return db.list_incidents(limit=limit)


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    """Serves the dashboard's static HTML shell; the page itself fetches
    /api/incidents via JS and renders client-side."""
    html_path = _STATIC_DIR / "dashboard.html"
    return html_path.read_text(encoding="utf-8")