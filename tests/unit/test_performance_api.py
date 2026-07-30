from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from apps.api.main import app
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from w2.api import routers
from w2.api.repository import Checkpoint, ReadModelRepository, ReadModelService
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
    assert payload["clv"]["mean"] == 0.08
    assert payload["calibration"]["model_log_loss"] == 0.55
    assert payload["sample_progress"] == {
        "current": 8,
        "target": 200,
        "ratio": 0.04,
        "status": "ACCUMULATING",
    }
    assert payload["clv"]["points"] == [
        {
            "fixture_id": "fixture-clv",
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


def _rows() -> list[Checkpoint]:
    rows = [
        _cohort("performance:cohort:all", finished=35, settled=0),
        _cohort("performance:cohort:tier:STRICT", finished=20, settled=5),
        _cohort("performance:cohort:tier:ADVISORY", finished=15, settled=0),
        _cohort(
            "performance:cohort:league:premier_league",
            finished=12,
            settled=8,
        ),
        _cohort(
            "performance:cohort:league-tier:premier_league:STRICT",
            finished=8,
            settled=8,
            model_log_loss=0.55,
            clv_mean=0.08,
        ),
        _cohort(
            "performance:cohort:league-tier:premier_league:ADVISORY",
            finished=4,
            settled=0,
        ),
    ]
    rows.extend(
        [
            _fixture("fixture-clv", clv_status="AVAILABLE", clv_decimal=0.1),
            _fixture(
                "fixture-no-clv",
                clv_status="NOT_APPLICABLE_NO_PICK",
                clv_decimal=None,
            ),
        ]
    )
    return rows


def _cohort(
    key: str,
    *,
    finished: int,
    settled: int,
    model_log_loss: float | None = None,
    clv_mean: float | None = None,
) -> Checkpoint:
    window = _window(
        finished=finished,
        settled=settled,
        model_log_loss=model_log_loss,
        clv_mean=clv_mean,
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
    clv_mean: float | None,
) -> dict[str, Any]:
    decisive = settled
    return {
        "finished_result_count": finished,
        "fixture_checkpoint_count": finished,
        "scored_count": 0,
        "not_scorable_count": finished,
        "blocked_count": 0,
        "not_scorable_by_reason": {
            "CAPTURE_IDENTITY_MISSING": finished
        },
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
        "clv_sample_count": 1 if clv_mean is not None else 0,
        "clv_mean": clv_mean,
        "clv_median": clv_mean,
        "clv_positive_count": 1 if clv_mean and clv_mean > 0 else 0,
        "clv_positive_share": 1.0 if clv_mean and clv_mean > 0 else None,
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
    clv_status: str,
    clv_decimal: float | None,
) -> Checkpoint:
    key = f"performance:fixture:{fixture_id}"
    return Checkpoint(
        key=key,
        source_hash=f"hash:{key}",
        created_at=NOW,
        payload={
            "schema_version": "w2.performance_projection.v2",
            "projection_version": "eval-01c.v2",
            "status": "NOT_SCORABLE",
            "fixture_id": fixture_id,
            "kickoff_utc": NOW.isoformat(),
            "league": "premier_league",
            "evaluation_tier": "STRICT",
            "clv_status": clv_status,
            "clv_decimal": clv_decimal,
            "canonical_pick_status": "SETTLEMENT_MISSING",
            "canonical_settlement_outcome": None,
            "canonical_decisive": None,
        },
    )
