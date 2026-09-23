from datetime import UTC, datetime

FORWARD_START_UTC = datetime(2026, 9, 26, 16, tzinfo=UTC)
FAST_CRITERIA_MINIMUM_KEPT = 300


def is_forward(evaluated_at: datetime | None) -> bool:
    if evaluated_at is None:
        return False
    value = (
        evaluated_at.replace(tzinfo=UTC)
        if evaluated_at.tzinfo is None
        else evaluated_at.astimezone(UTC)
    )
    return value >= FORWARD_START_UTC
