from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from w2.config import get_settings
from w2.infrastructure.database import Base
from w2.infrastructure.persistence.future_refresh_models import RawPayloadModel
from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayMarketObservationModel,
)
from w2.ingestion.future_refresh import deterministic_task_key, run_future_refresh_task
from w2.ingestion.future_refresh_repository import (
    FutureRefreshDbRepository,
    FutureRefreshPersistenceError,
)
from w2.providers.api_football import LiveApiFootballResponse

NOW = datetime(2026, 6, 23, 10, 0, tzinfo=UTC)


class C9FakeApiFootballClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str]]] = []

    def request_live(self, endpoint: str, params: dict[str, str]) -> LiveApiFootballResponse:
        self.calls.append((endpoint, params))
        return LiveApiFootballResponse(
            endpoint=endpoint,
            params=params,
            status_code=200,
            elapsed_ms=7,
            payload=self.payload(endpoint, params),
            headers={"x-ratelimit-requests-remaining": "7000"},
            captured_at=NOW,
        )

    def payload(self, endpoint: str, params: dict[str, str]) -> dict[str, Any]:
        if endpoint == "status":
            return {"response": {"requests": {"remaining": 7000}}}
        if endpoint == "fixtures":
            return {
                "response": [
                    {
                        "fixture": {
                            "id": 1489404,
                            "date": "2026-06-23T17:00:00+00:00",
                            "status": {"short": "NS"},
                            "venue": {"name": "C9 Test Venue"},
                        },
                        "league": {
                            "id": 1,
                            "name": "World Cup",
                            "season": 2026,
                            "round": "Group K",
                        },
                        "teams": {
                            "home": {"id": 10, "name": "Team A"},
                            "away": {"id": 20, "name": "Team B"},
                        },
                    }
                ]
            }
        if endpoint == "odds":
            return {
                "response": [
                    {
                        "fixture": {"id": int(params["fixture"])},
                        "bookmakers": [
                            {
                                "id": 1,
                                "name": "Book A",
                                "bets": [
                                    {
                                        "id": 4,
                                        "name": "Asian Handicap",
                                        "values": [
                                            {"value": "Home -0.5", "odd": "1.91"},
                                            {"value": "Away +0.5", "odd": "1.93"},
                                        ],
                                    },
                                    {
                                        "id": 5,
                                        "name": "Goals Over/Under",
                                        "values": [
                                            {"value": "Over 2.5", "odd": "2.01"},
                                            {"value": "Under 2.5", "odd": "1.82"},
                                        ],
                                    },
                                ],
                            }
                        ],
                    }
                ]
            }
        if endpoint == "statistics":
            return {
                "response": [
                    {
                        "team": {"id": 10},
                        "statistics": [{"type": "expected_goals", "value": "1.4"}],
                    },
                    {
                        "team": {"id": 20},
                        "statistics": [{"type": "expected_goals", "value": "0.7"}],
                    },
                ]
            }
        if endpoint == "lineups":
            def team_lineup(team_id: int, offset: int) -> dict[str, Any]:
                return {
                    "team": {"id": team_id, "name": f"Team {team_id}"},
                    "formation": "4-3-3",
                    "startXI": [
                        {
                            "player": {
                                "id": offset + index,
                                "name": f"Player {offset + index}",
                                "number": index + 1,
                                "pos": "G" if index == 0 else "M",
                                "grid": f"{index // 4 + 1}:{index % 4 + 1}",
                            }
                        }
                        for index in range(11)
                    ],
                    "substitutes": [],
                }

            return {"response": [team_lineup(10, 100), team_lineup(20, 200)]}
        if endpoint == "injuries":
            return {"response": []}
        raise AssertionError(endpoint)


def configure_sqlite_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'future-refresh-c9.db'}"
    monkeypatch.setenv("W2_ENVIRONMENT", "test")
    monkeypatch.setenv("W2_DATABASE_URL", database_url)
    monkeypatch.setenv("W2_FUTURE_REFRESH_PERSISTENCE", "db")
    get_settings.cache_clear()
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)


def materialized_fixture_ids(events: list[Any]) -> list[str]:
    return list(dict.fromkeys(str(event.fixture_id) for event in events))


def _run_completed_refresh(
    *,
    tmp_path: Path,
    task_id: str,
    materializer: Any = materialized_fixture_ids,
) -> Any:
    key = deterministic_task_key(
        competition_id="world_cup_2026",
        season="2026",
        now=NOW,
        interval_seconds=900,
    )
    return run_future_refresh_task(
        task_id=task_id,
        key=key,
        queued_at=NOW,
        runtime_root=tmp_path / "runtime",
        client=C9FakeApiFootballClient(),
        now=NOW,
        persistence="db",
        materialize_public_artifacts=materializer,
    )


def test_c9_lineup_event_is_emitted_after_identity_and_capture_are_available(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_sqlite_db(monkeypatch, tmp_path)
    event_types: list[str] = []

    def materialize(events: list[Any]) -> list[str]:
        event_types.extend(str(event.event_type) for event in events)
        return materialized_fixture_ids(events)

    audit = _run_completed_refresh(
        tmp_path=tmp_path,
        task_id="task-c9-ordering",
        materializer=materialize,
    )

    assert audit.status == "COMPLETED", audit
    assert set(event_types) == {"FIXTURE_CHANGED", "LINEUP_CHANGED", "ODDS_CHANGED"}


def test_generated_ready_model_distributions_satisfy_v2_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_sqlite_db(monkeypatch, tmp_path)
    audit = _run_completed_refresh(
        tmp_path=tmp_path,
        task_id="task-v2-distribution-contract",
    )
    assert audit.status == "COMPLETED", audit

    from w2.prematch.analysis_calculator import ReadModelRepository, ReadModelService

    card = ReadModelService(repository=ReadModelRepository()).public_analysis_card_bounded(
        "1489404",
        evaluation_time=NOW,
        use_frozen_canary=False,
    )
    assert isinstance(card, dict), card
    candidates = card.get("market_candidates")
    assert isinstance(candidates, dict), card
    ready_distributions: list[tuple[str, str, dict[str, Any], float]] = []
    required_states = {"WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "LOSS"}
    for market_key, candidate in candidates.items():
        if not isinstance(candidate, dict):
            continue
        evidence = candidate.get("analysis_evidence")
        sides = evidence.get("side_evidence") if isinstance(evidence, dict) else None
        if not isinstance(sides, dict):
            continue
        for selection, side in sides.items():
            model = side.get("model_probability") if isinstance(side, dict) else None
            if not isinstance(model, dict) or model.get("status") != "READY":
                continue
            distribution = model.get("settlement_distribution")
            assert isinstance(distribution, dict), (market_key, selection, model)
            values = {state: float(value) for state, value in distribution.items()}
            total = sum(values.values())
            ready_distributions.append((str(market_key), str(selection), distribution, total))
            assert set(values) == required_states, ready_distributions[-1]
            assert all(math.isfinite(value) and value >= 0 for value in values.values()), (
                ready_distributions[-1]
            )
            assert abs(total - 1.0) <= 1e-9, ready_distributions[-1]

    assert ready_distributions, card


def test_c9_lineup_failure_is_explicit_and_preserves_paid_raw_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_sqlite_db(monkeypatch, tmp_path)

    def reject_lineup(self: Any, **kwargs: Any) -> int:
        raise FutureRefreshPersistenceError("INJECTED_LINEUP_WRITE_FAILURE")

    monkeypatch.setattr(
        FutureRefreshDbRepository,
        "save_lineup_snapshots",
        reject_lineup,
    )
    key = deterministic_task_key(
        competition_id="world_cup_2026",
        season="2026",
        now=NOW,
        interval_seconds=900,
    )
    client = C9FakeApiFootballClient()

    audit = run_future_refresh_task(
        task_id="task-c9-failure",
        key=key,
        queued_at=NOW,
        runtime_root=tmp_path / "runtime",
        client=client,
        now=NOW,
        persistence="db",
        materialize_public_artifacts=materialized_fixture_ids,
    )

    assert audit.status == "BLOCKED"
    assert audit.result["error_code"] == (
        "LINEUP_MATERIALIZATION_FAILED:INJECTED_LINEUP_WRITE_FAILURE"
    )
    assert audit.result["raw_payload_written_count"] == len(client.calls)
    assert "lineups" in [endpoint for endpoint, _params in client.calls]
    engine = create_engine(get_settings().database_url.get_secret_value())
    with Session(engine) as session:
        endpoints = set(session.scalars(select(RawPayloadModel.endpoint)).all())
        assert "lineups" in endpoints
        assert session.scalar(
            select(func.count()).select_from(MatchdayMarketObservationModel)
        ) == 0


def test_c9_lineup_integrity_conflict_is_noop_only_for_exact_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_sqlite_db(monkeypatch, tmp_path)
    monkeypatch.setattr(
        FutureRefreshDbRepository,
        "materialize_player_identity_mappings",
        lambda self, **kwargs: 0,
    )
    repository = FutureRefreshDbRepository()
    payload = C9FakeApiFootballClient().payload("lineups", {"fixture": "1489404"})

    assert repository.save_lineup_snapshots(
        fixture_id="1489404",
        captured_at=NOW,
        raw_sha256="a" * 64,
        payload=payload,
        materialize_baselines=False,
    ) == 2
    assert repository.save_lineup_snapshots(
        fixture_id="1489404",
        captured_at=NOW,
        raw_sha256="a" * 64,
        payload=payload,
        materialize_baselines=False,
    ) == 0

    conflicting = json.loads(json.dumps(payload))
    conflicting["response"][0]["formation"] = "3-5-2"
    with pytest.raises(
        FutureRefreshPersistenceError,
        match="LINEUP_SNAPSHOT_IDENTITY_CONFLICT",
    ):
        repository.save_lineup_snapshots(
            fixture_id="1489404",
            captured_at=NOW,
            raw_sha256="a" * 64,
            payload=conflicting,
            materialize_baselines=False,
        )
