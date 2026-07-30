"""
Simple API key authentication for endpoints that accept external input
(webhook ingestion, feedback submission). Read-only/internal endpoints
(dashboard, /api/incidents, /docs) stay open, since they're for viewing
during a demo or by a trusted on-call dashboard, not for external systems
pushing data in.

Accepts the key two ways, so it works for both manual testing and
Alertmanager:
  - `X-API-Key: <key>` header (simplest for curl/Postman/manual testing)
  - `Authorization: Bearer <key>` header (what Alertmanager's
    `http_config.authorization` sends - see the Alertmanager config
    snippet in the README for wiring this up there)

The key itself comes from `config.API_KEY`, loaded from `.env` - same
pattern as SLACK_WEBHOOK_URL, so it never ends up committed to git.

If API_KEY is unset (e.g. fresh local clone with no .env configured yet),
authentication is skipped entirely so the app still runs out of the box -
but this is logged clearly, since running with no key configured beyond
local dev is not safe.
"""

import logging
from fastapi import Request, HTTPException, status
from app import config

logger = logging.getLogger(__name__)

_warned_no_key = False


def require_api_key(request: Request) -> None:
    global _warned_no_key

    if not config.API_KEY:
        if not _warned_no_key:
            logger.warning(
                "API_KEY is not set - webhook/feedback endpoints are running "
                "WITHOUT authentication. Set API_KEY in .env before exposing "
                "this beyond local development."
            )
            _warned_no_key = True
        return

    provided = request.headers.get("X-API-Key")
    if not provided:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            provided = auth_header[len("Bearer "):]

    if provided != config.API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key. Provide it via the "
                   "'X-API-Key' header or 'Authorization: Bearer <key>'.",
        )