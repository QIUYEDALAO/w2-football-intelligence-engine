"""Immutable scheduler identities for automatic Provider work."""

from __future__ import annotations

import re
from datetime import UTC, datetime

XG_CLAIM_PROTOCOL = "w2.xg-history-backfill.window.v1"


def xg_backfill_claim_key(
    *,
    competition_id: str,
    queued_at: datetime,
    interval_seconds: int,
) -> tuple[str, datetime]:
    """Return the planned UTC window and its stable business claim key.

    A redelivered message carries these original values. The worker must never
    derive another key from its consumption time or Celery delivery id.
    """
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", competition_id):
        raise ValueError("XG_CLAIM_COMPETITION_INVALID")
    if queued_at.tzinfo is None or not 60 <= interval_seconds <= 86400:
        raise ValueError("XG_CLAIM_WINDOW_INVALID")
    seconds = int(queued_at.astimezone(UTC).timestamp())
    start = datetime.fromtimestamp(seconds // interval_seconds * interval_seconds, UTC)
    return (
        f"xg-history-backfill:v1:{competition_id}:{interval_seconds}:{int(start.timestamp())}",
        start,
    )
