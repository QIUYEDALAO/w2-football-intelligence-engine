from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


class HistoricalFixtureRepository(Protocol):
    def historical_fixture_payloads(
        self,
        *,
        kickoff_from: datetime,
        kickoff_to: datetime,
        provider_league_id: str | None = None,
    ) -> list[dict[str, Any]]: ...


@dataclass(frozen=True)
class HistoricalFixtureBatch:
    fixture_payloads: tuple[dict[str, Any], ...]
    provider_calls: int = 0
    source_scope: str = "HISTORICAL_TRAINING"


def materialize_factor_history_from_persisted_raw(
    repository: HistoricalFixtureRepository,
    *,
    kickoff_from: datetime,
    kickoff_to: datetime,
    provider_league_id: str | None = None,
) -> HistoricalFixtureBatch:
    """Return the DB-only input batch; this contract has no Provider capability."""
    rows = repository.historical_fixture_payloads(
        provider_league_id=provider_league_id,
        kickoff_from=kickoff_from,
        kickoff_to=kickoff_to,
    )
    return HistoricalFixtureBatch(fixture_payloads=tuple(rows))
