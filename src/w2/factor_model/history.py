from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol


class HistoricalFixtureRepository(Protocol):
    def fixture_payloads(
        self, *, provider_league_id: str | None = None
    ) -> list[dict[str, Any]]: ...


@dataclass(frozen=True)
class HistoricalFixtureBatch:
    fixture_payloads: tuple[dict[str, Any], ...]
    provider_calls: int = 0
    source_scope: str = "KICKOFF_BEFORE_AS_OF"


def _fixture_kickoff(item: dict[str, Any]) -> datetime | None:
    fixture = item.get("fixture")
    value = fixture.get("date") if isinstance(fixture, dict) else None
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def materialize_factor_history_from_persisted_raw(
    repository: HistoricalFixtureRepository,
    *,
    kickoff_from: datetime,
    kickoff_to: datetime,
    as_of: datetime,
    provider_league_id: str | None = None,
) -> HistoricalFixtureBatch:
    """Return the DB-only input batch; this contract has no Provider capability."""
    lower = kickoff_from.astimezone(UTC)
    upper = min(kickoff_to.astimezone(UTC), as_of.astimezone(UTC))
    rows = [
        item
        for item in repository.fixture_payloads(provider_league_id=provider_league_id)
        if (kickoff := _fixture_kickoff(item)) is not None and lower <= kickoff < upper
    ]
    return HistoricalFixtureBatch(fixture_payloads=tuple(rows))
