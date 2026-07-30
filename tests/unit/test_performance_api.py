from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any

import pytest
from apps.api.main import app
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from w2.api import routers
from w2.api.repository import (
    Checkpoint,
    ReadModelRepository,
    ReadModelService,
)
from w2.infrastructure.persistence.api_models import ReadModelCheckpointModel

NOW = datetime(2026, 7, 30, tzinfo=UTC)


class PerformanceRepository:
    def __init__(self, rows: list[Checkpoint]) -> None:
        self.rows = rows
        self.read_prefixes: list[str] = []
        self.db_writes = 0

    def checkpoints(self, prefix: str) -> list[Checkpoint]:
        self.read_prefixes.append(prefix)
        return [row for row in self.rows if row.key.startswith(prefix)]


def test_performance_api_uses_projection_values_and_exact_filters() -> None:
    repository = PerformanceRepository(_rows())
    service = ReadModelService(repository=repository)  # type: ignore[arg-type]

    payload = service.performance(
        window="7d",
        league="premier_league",
        tier="STRICT",
    )

    assert payload["selected_window"] == "7d"
    assert payload["selected_league"] == "premier_league"
    assert payload["selected_tier"] == "STRICT"
    assert (
        payload["clv"]["clv_population"]
        == "SCORABLE_FINISHED_WITH_CANONICAL_CLV"
    )
    assert payload["clv"]["mean"] == 0.1
    assert payload["calibration"]["model_log_loss"] == 0.55
    assert payload["sample_progress"] == {
        "current": 8,
        "target": 200,
        "ratio": 0.04,
        "status": "ACCUMULATING",
    }
    assert payload["clv"]["points"] == [
        {
            "fixture_id": "fixture-strict-clv",
            "kickoff_utc": NOW,
            "league": "premier_league",
            "evaluation_tier": "STRICT",
            "clv_decimal": 0.1,
        }
    ]
    assert repository.read_prefixes == [
        "performance:cohort:",
        "performance:fixture:",
    ]
    assert repository.db_writes == 0


def test_clv_points_exclude_non_scorable_blocked_and_unavailable_rows() -> None:
    payload = ReadModelService(
        repository=PerformanceRepository(_rows()),  # type: ignore[arg-type]
    ).performance(window="30d", league=None, tier="ALL")

    assert payload["clv"]["sample_count"] == 2
    assert {
        point["fixture_id"] for point in payload["clv"]["points"]
    } == {"fixture-strict-clv", "fixture-advisory-clv"}
    assert sorted(
        point["clv_decimal"] for point in payload["clv"]["points"]
    ) == [-0.2, 0.1]
    assert payload["clv"]["mean"] == -0.05
    assert payload["clv"]["median"] == -0.05
    assert payload["clv"]["positive_count"] == 1
    assert payload["clv"]["positive_share"] == 0.5


@pytest.mark.parametrize("window", ["7d", "30d", "90d"])
@pytest.mark.parametrize("tier", ["ALL", "STRICT", "ADVISORY"])
@pytest.mark.parametrize("league", [None, "premier_league"])
def test_clv_points_match_projected_sample_count_for_every_filter(
    window: str,
    tier: str,
    league: str | None,
) -> None:
    payload = ReadModelService(
        repository=PerformanceRepository(_rows()),  # type: ignore[arg-type]
    ).performance(
        window=window,  # type: ignore[arg-type]
        league=league,
        tier=tier,  # type: ignore[arg-type]
    )
    expected = {
        "ALL": [0.1, -0.2],
        "STRICT": [0.1],
        "ADVISORY": [-0.2],
    }[tier]

    assert len(payload["clv"]["points"]) == payload["clv"]["sample_count"]
    assert sorted(
        point["clv_decimal"] for point in payload["clv"]["points"]
    ) == sorted(expected)


def test_clv_population_mismatch_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = _rows()
    payload = deepcopy(rows[0].payload)
    payload["windows"]["30d"]["clv_sample_count"] = 3
    rows[0] = Checkpoint(
        key=rows[0].key,
        source_hash=rows[0].source_hash,
        created_at=rows[0].created_at,
        payload=payload,
    )
    monkeypatch.setattr(
        routers,
        "service",
        ReadModelService(
            repository=PerformanceRepository(rows),  # type: ignore[arg-type]
        ),
    )

    response = TestClient(app, raise_server_exceptions=False).get(
        "/v1/performance"
    )

    assert response.status_code == 503
    assert response.json() == {
        "request_id": response.json()["request_id"],
        "code": "SYSTEM_DEGRADED",
        "message": "PERFORMANCE_CLV_POPULATION_MISMATCH",
    }


def test_performance_endpoint_twenty_reads_are_stable_and_zero_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = PerformanceRepository(_rows())
    monkeypatch.setattr(
        routers,
        "service",
        ReadModelService(repository=repository),  # type: ignore[arg-type]
    )
    client = TestClient(app)

    responses = [client.get("/v1/performance") for _ in range(20)]
    payloads = [
        {key: value for key, value in response.json().items() if key != "request_id"}
        for response in responses
    ]

    assert {response.status_code for response in responses} == {200}
    assert all(payload == payloads[0] for payload in payloads)
    assert set(repository.read_prefixes) == {
        "performance:cohort:",
        "performance:fixture:",
    }
    assert repository.db_writes == 0


def test_performance_endpoint_twenty_real_db_reads_issue_no_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'performance.db'}")
    ReadModelCheckpointModel.__table__.create(engine)  # type: ignore[attr-defined]
    with Session(engine) as session:
        for checkpoint in _rows():
            session.add(
                ReadModelCheckpointModel(
                    checkpoint_key=checkpoint.key,
                    source_hash=checkpoint.source_hash,
                    created_at=checkpoint.created_at,
                    payload=checkpoint.payload,
                )
            )
        session.commit()
    writes: list[str] = []

    def record_write(
        _connection: Any,
        _cursor: Any,
        statement: str,
        _parameters: Any,
        _context: Any,
        _executemany: Any,
    ) -> None:
        if statement.lstrip().upper().startswith(
            ("INSERT", "UPDATE", "DELETE")
        ):
            writes.append(statement)

    event.listen(engine, "before_cursor_execute", record_write)
    monkeypatch.setattr("w2.api.repository.create_engine", lambda: engine)
    monkeypatch.setattr(
        routers,
        "service",
        ReadModelService(repository=ReadModelRepository()),
    )
    client = TestClient(app)

    responses = [client.get("/v1/performance") for _ in range(20)]
    payloads = [
        {key: value for key, value in response.json().items() if key != "request_id"}
        for response in responses
    ]

    assert {response.status_code for response in responses} == {200}
    assert all(payload == payloads[0] for payload in payloads)
    assert writes == []


def test_performance_endpoint_invalid_projection_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = _rows()
    rows[0] = Checkpoint(
        key=rows[0].key,
        source_hash=rows[0].source_hash,
        created_at=rows[0].created_at,
        payload={**rows[0].payload, "projection_version": "stale"},
    )
    monkeypatch.setattr(
        routers,
        "service",
        ReadModelService(
            repository=PerformanceRepository(rows),  # type: ignore[arg-type]
        ),
    )

    response = TestClient(app, raise_server_exceptions=False).get(
        "/v1/performance"
    )

    assert response.status_code == 503
    assert response.json()["code"] == "SYSTEM_DEGRADED"


def test_performance_endpoint_missing_projection_field_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = _rows()
    payload = deepcopy(rows[0].payload)
    del payload["windows"]["30d"]["sample_progress"]
    rows[0] = Checkpoint(
        key=rows[0].key,
        source_hash=rows[0].source_hash,
        created_at=rows[0].created_at,
        payload=payload,
    )
    monkeypatch.setattr(
        routers,
        "service",
        ReadModelService(
            repository=PerformanceRepository(rows),  # type: ignore[arg-type]
        ),
    )

    response = TestClient(app, raise_server_exceptions=False).get(
        "/v1/performance"
    )

    assert response.status_code == 503
    assert response.json()["code"] == "SYSTEM_DEGRADED"


@pytest.mark.parametrize(
    ("populated_tier", "empty_tier"),
    [("STRICT", "ADVISORY"), ("ADVISORY", "STRICT")],
)
def test_sparse_tier_and_league_tier_return_zero_sample_projection(
    populated_tier: str,
    empty_tier: str,
) -> None:
    repository = PerformanceRepository(
        _sparse_rows(populated_tier=populated_tier)
    )
    service = ReadModelService(repository=repository)  # type: ignore[arg-type]

    global_payload = service.performance(
        window="30d",
        league=None,
        tier=empty_tier,  # type: ignore[arg-type]
    )
    league_payload = service.performance(
        window="30d",
        league="premier_league",
        tier="ALL",
    )

    assert global_payload["coverage"]["fixture_checkpoint_count"] == 0
    assert global_payload["sample_progress"] == {
        "current": 0,
        "target": 200,
        "ratio": 0.0,
        "status": "ACCUMULATING",
    }
    assert league_payload["tier_comparison"][empty_tier][
        "finished_result_count"
    ] == 0
    assert league_payload["tier_comparison"][empty_tier][
        "canonical_hit_rate"
    ] is None


def test_unknown_league_and_missing_mandatory_tier_cohort_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = _sparse_rows(populated_tier="STRICT")
    monkeypatch.setattr(
        routers,
        "service",
        ReadModelService(
            repository=PerformanceRepository(rows),  # type: ignore[arg-type]
        ),
    )
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get(
        "/v1/performance",
        params={"league": "unknown_league"},
    )
    assert response.status_code == 503
    assert response.json()["code"] == "SYSTEM_DEGRADED"

    missing = [
        row
        for row in rows
        if row.key != "performance:cohort:tier:ADVISORY"
    ]
    monkeypatch.setattr(
        routers,
        "service",
        ReadModelService(
            repository=PerformanceRepository(missing),  # type: ignore[arg-type]
        ),
    )
    response = client.get("/v1/performance")
    assert response.status_code == 503
    assert response.json()["code"] == "SYSTEM_DEGRADED"


def _rows() -> list[Checkpoint]:
    rows = [
        _cohort(
            "performance:cohort:all",
            finished=35,
            settled=0,
            clv_values=(0.1, -0.2),
        ),
        _cohort(
            "performance:cohort:tier:STRICT",
            finished=20,
            settled=5,
            clv_values=(0.1,),
        ),
        _cohort(
            "performance:cohort:tier:ADVISORY",
            finished=15,
            settled=0,
            clv_values=(-0.2,),
        ),
        _cohort(
            "performance:cohort:league:premier_league",
            finished=12,
            settled=8,
            clv_values=(0.1, -0.2),
        ),
        _cohort(
            "performance:cohort:league-tier:premier_league:STRICT",
            finished=8,
            settled=8,
            model_log_loss=0.55,
            clv_values=(0.1,),
        ),
        _cohort(
            "performance:cohort:league-tier:premier_league:ADVISORY",
            finished=4,
            settled=0,
            clv_values=(-0.2,),
        ),
    ]
    rows.extend(
        [
            _fixture(
                "fixture-strict-clv",
                clv_status="AVAILABLE",
                clv_decimal=0.1,
            ),
            _fixture(
                "fixture-advisory-clv",
                clv_status="AVAILABLE",
                clv_decimal=-0.2,
                evaluation_tier="ADVISORY",
            ),
            _fixture(
                "fixture-not-scorable-clv",
                status="NOT_SCORABLE",
                clv_status="AVAILABLE",
                clv_decimal=0.8,
            ),
            _fixture(
                "fixture-blocked-clv",
                status="BLOCKED",
                clv_status="AVAILABLE",
                clv_decimal=0.9,
            ),
            _fixture(
                "fixture-unavailable-clv",
                clv_status="INSUFFICIENT_SNAPSHOTS",
                clv_decimal=0.7,
            ),
        ]
    )
    return rows


def _sparse_rows(*, populated_tier: str) -> list[Checkpoint]:
    empty_tier = "ADVISORY" if populated_tier == "STRICT" else "STRICT"
    return [
        _cohort("performance:cohort:all", finished=1, settled=0),
        _cohort(
            f"performance:cohort:tier:{populated_tier}",
            finished=1,
            settled=0,
        ),
        _cohort(
            f"performance:cohort:tier:{empty_tier}",
            finished=0,
            settled=0,
        ),
        _cohort(
            "performance:cohort:league:premier_league",
            finished=1,
            settled=0,
        ),
        _cohort(
            f"performance:cohort:league-tier:premier_league:{populated_tier}",
            finished=1,
            settled=0,
        ),
        _cohort(
            f"performance:cohort:league-tier:premier_league:{empty_tier}",
            finished=0,
            settled=0,
        ),
        _fixture(
            "fixture-sparse",
            status="NOT_SCORABLE",
            clv_status="NOT_APPLICABLE_NO_PICK",
            clv_decimal=None,
            evaluation_tier=populated_tier,
        ),
    ]


def _cohort(
    key: str,
    *,
    finished: int,
    settled: int,
    model_log_loss: float | None = None,
    clv_values: tuple[float, ...] = (),
) -> Checkpoint:
    window = _window(
        finished=finished,
        settled=settled,
        model_log_loss=model_log_loss,
        clv_values=clv_values,
    )
    return Checkpoint(
        key=key,
        source_hash=f"hash:{key}",
        created_at=NOW,
        payload={
            "schema_version": "w2.performance_projection.v2",
            "projection_version": "eval-01c.v2",
            "checkpoint_key": key,
            "scoring_window_anchor": NOW.isoformat(),
            "windows": {
                "7d": deepcopy(window),
                "30d": deepcopy(window),
                "90d": deepcopy(window),
            },
            "business_projection_hash": f"business:{key}",
        },
    )


def _window(
    *,
    finished: int,
    settled: int,
    model_log_loss: float | None,
    clv_values: tuple[float, ...],
) -> dict[str, Any]:
    decisive = settled
    clv_positive_count = len([value for value in clv_values if value > 0])
    return {
        "finished_result_count": finished,
        "fixture_checkpoint_count": finished,
        "scored_count": 0,
        "not_scorable_count": finished,
        "blocked_count": 0,
        "not_scorable_by_reason": (
            {"CAPTURE_IDENTITY_MISSING": finished}
            if finished
            else {}
        ),
        "model_log_loss": model_log_loss,
        "market_log_loss": None,
        "model_minus_market_log_loss": None,
        "model_brier": None,
        "market_brier": None,
        "model_minus_market_brier": None,
        "model_rps": None,
        "market_rps": None,
        "model_minus_market_rps": None,
        "paired_log_loss_bootstrap": {
            "status": "INSUFFICIENT",
            "sample_count": 0,
        },
        "model_ece": None,
        "market_ece": None,
        "model_reliability_bins": _bins(),
        "market_reliability_bins": _bins(),
        "clv_sample_count": len(clv_values),
        "clv_population": "SCORABLE_FINISHED_WITH_CANONICAL_CLV",
        "clv_mean": (
            sum(clv_values) / len(clv_values) if clv_values else None
        ),
        "clv_median": median(clv_values) if clv_values else None,
        "clv_positive_count": clv_positive_count,
        "clv_positive_share": (
            clv_positive_count / len(clv_values) if clv_values else None
        ),
        "clv_ci95": None,
        "clv_method": "existing-canonical-method",
        "canonical_settled_count": settled,
        "canonical_hit_count": settled,
        "canonical_miss_count": 0,
        "canonical_push_count": 0,
        "canonical_void_count": 0,
        "canonical_decisive_count": decisive,
        "canonical_hit_rate": 1.0 if decisive >= 5 else None,
        "canonical_hit_rate_status": (
            "AVAILABLE" if decisive >= 5 else "INSUFFICIENT_SAMPLE"
        ),
        "sample_target": 200,
        "sample_progress": settled / 200,
        "sample_progress_status": "ACCUMULATING",
    }


def _bins() -> list[dict[str, Any]]:
    return [
        {
            "lower": 0.0,
            "upper": 0.1,
            "count": 0,
            "mean_confidence": None,
            "accuracy": None,
        }
    ]


def _fixture(
    fixture_id: str,
    *,
    status: str = "SCORED",
    clv_status: str,
    clv_decimal: float | None,
    evaluation_tier: str = "STRICT",
) -> Checkpoint:
    key = f"performance:fixture:{fixture_id}"
    return Checkpoint(
        key=key,
        source_hash=f"hash:{key}",
        created_at=NOW,
        payload={
            "schema_version": "w2.performance_projection.v2",
            "projection_version": "eval-01c.v2",
            "status": status,
            "fixture_id": fixture_id,
            "kickoff_utc": NOW.isoformat(),
            "league": "premier_league",
            "evaluation_tier": evaluation_tier,
            "clv_status": clv_status,
            "clv_decimal": clv_decimal,
            "canonical_pick_status": "SETTLEMENT_MISSING",
            "canonical_settlement_outcome": None,
            "canonical_decisive": None,
            "canonical_exclusion_reason": "SETTLEMENT_MISSING",
        },
    )
