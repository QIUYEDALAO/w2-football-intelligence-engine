from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from w2.features.offline_materialization import (
    materialize_from_pro_cache,
    sanitized_target_fixture_payload,
    verify_materialization_payload,
)
from w2.features.staging_materialization_injection import (
    MaterializationInjectionError,
    inject_staging_materialization,
)
from w2.infrastructure.database import Base
from w2.infrastructure.persistence.future_refresh_models import TeamXgMatchModel

KICKOFF = datetime(2026, 7, 20, 12, tzinfo=UTC)


def test_materializes_target_snapshots_from_cached_history(tmp_path: Path) -> None:
    raw_root = tmp_path / "raw"
    fixtures = [
        _fixture(str(index), KICKOFF - timedelta(days=10 - index), "FT")
        for index in range(5)
    ]
    fixtures.append(_fixture("target", KICKOFF, "NS"))
    _write(raw_root / "fixtures" / "fixtures.json", _wrapper({}, fixtures))
    for index in range(5):
        _write(
            raw_root / "statistics" / f"statistics-{index}.json",
            _wrapper(
                {"fixture": str(index)},
                [
                    _stats("home", 1.4 + index * 0.1),
                    _stats("away", 1.0 + index * 0.1),
                ],
            ),
        )

    result = materialize_from_pro_cache(
        raw_root=raw_root,
        target_fixture_ids=("target",),
    )

    assert result.blockers == ()
    assert len(result.matches) == 10
    assert len(result.snapshots) == 2
    assert {row.team_id for row in result.snapshots} == {"home", "away"}
    assert all(row.match_count == 5 for row in result.snapshots)
    assert all(row.as_of_time == KICKOFF for row in result.snapshots)
    assert result.summary()["provider_calls"] == 0
    assert result.summary()["db_writes"] == 0


def test_missing_history_fails_closed(tmp_path: Path) -> None:
    raw_root = tmp_path / "raw"
    _write(
        raw_root / "fixtures" / "fixtures.json",
        _wrapper({}, [_fixture("target", KICKOFF, "NS")]),
    )

    result = materialize_from_pro_cache(
        raw_root=raw_root,
        target_fixture_ids=("target",),
    )

    assert len(result.snapshots) == 0
    assert result.blockers == (
        "FEATURE_HISTORY_INSUFFICIENT:target:away",
        "FEATURE_HISTORY_INSUFFICIENT:target:home",
    )


def test_target_fixtures_can_be_separate_from_history_cache(tmp_path: Path) -> None:
    raw_root = tmp_path / "raw"
    history = [
        _fixture(str(index), KICKOFF - timedelta(days=10 - index), "FT")
        for index in range(5)
    ]
    _write(raw_root / "fixtures" / "fixtures.json", _wrapper({}, history))
    for index in range(5):
        _write(
            raw_root / "statistics" / f"statistics-{index}.json",
            _wrapper(
                {"fixture": str(index)},
                [_stats("home", 1.4), _stats("away", 1.0)],
            ),
        )
    target_file = tmp_path / "sanitized-targets.json"
    _write(target_file, {"fixtures": [_fixture("today", KICKOFF, "NS")]})

    first = materialize_from_pro_cache(
        raw_root=raw_root,
        target_fixture_ids=("today",),
        target_fixture_file=target_file,
    ).payload()
    second = materialize_from_pro_cache(
        raw_root=raw_root,
        target_fixture_ids=("today",),
        target_fixture_file=target_file,
    ).payload()

    assert first == second
    assert verify_materialization_payload(first)
    assert first["summary"]["target_team_coverage"] == {"today": ["away", "home"]}  # type: ignore[index]
    assert first["integrity"]["materialization_id"].startswith("w2mat_")  # type: ignore[index,union-attr]


def test_sanitized_target_export_contains_identity_only() -> None:
    fixture = _fixture("target", KICKOFF, "NS")
    fixture["teams"]["home"]["name"] = "Sensitive Provider Name"  # type: ignore[index]
    payload = sanitized_target_fixture_payload(
        [fixture],
        kickoff_from=KICKOFF - timedelta(minutes=1),
        kickoff_to=KICKOFF + timedelta(minutes=1),
    )

    assert payload["fixtures"] == [
        {
            "fixture_id": "target",
            "kickoff_utc": "2026-07-20T12:00:00Z",
            "competition_id": "169",
            "home_team_id": "home",
            "away_team_id": "away",
        }
    ]
    assert "Sensitive Provider Name" not in json.dumps(payload)


def test_staging_injection_is_dry_run_idempotent_and_conflict_safe(
    tmp_path: Path,
) -> None:
    payload = _ready_materialization(tmp_path)
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    dry_run = inject_staging_materialization(
        engine=engine, payload=payload, environment="staging"
    )
    assert dry_run.mode == "DRY_RUN"
    assert dry_run.match_rows_inserted == 10
    with Session(engine) as session:
        assert session.query(TeamXgMatchModel).count() == 0

    applied = inject_staging_materialization(
        engine=engine, payload=payload, environment="staging", apply=True
    )
    repeated = inject_staging_materialization(
        engine=engine, payload=payload, environment="staging", apply=True
    )
    assert applied.snapshot_rows_inserted == 2
    assert repeated.match_rows_inserted == 0
    assert repeated.match_rows_unchanged == 10
    assert repeated.snapshot_rows_unchanged == 2

    with Session(engine) as session:
        row = session.scalar(select(TeamXgMatchModel).limit(1))
        assert row is not None
        row.xg_for += 0.5
        session.commit()
    with pytest.raises(MaterializationInjectionError, match="TEAM_XG_MATCH_CONFLICT"):
        inject_staging_materialization(
            engine=engine, payload=payload, environment="staging", apply=True
        )


def test_staging_injection_rejects_production_and_tampering(tmp_path: Path) -> None:
    payload = _ready_materialization(tmp_path)
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with pytest.raises(MaterializationInjectionError, match="STAGING_ENVIRONMENT_REQUIRED"):
        inject_staging_materialization(
            engine=engine, payload=payload, environment="production", apply=True
        )
    payload["team_xg_rolling_snapshots"][0]["rolling_xg_for"] = 99  # type: ignore[index]
    with pytest.raises(MaterializationInjectionError, match="MATERIALIZATION_INTEGRITY_INVALID"):
        inject_staging_materialization(
            engine=engine, payload=payload, environment="staging", apply=True
        )


def _ready_materialization(tmp_path: Path) -> dict[str, object]:
    raw_root = tmp_path / "raw"
    fixtures = [
        _fixture(str(index), KICKOFF - timedelta(days=10 - index), "FT")
        for index in range(5)
    ]
    fixtures.append(_fixture("target", KICKOFF, "NS"))
    _write(raw_root / "fixtures" / "fixtures.json", _wrapper({}, fixtures))
    for index in range(5):
        _write(
            raw_root / "statistics" / f"statistics-{index}.json",
            _wrapper(
                {"fixture": str(index)},
                [_stats("home", 1.4), _stats("away", 1.0)],
            ),
        )
    return materialize_from_pro_cache(
        raw_root=raw_root, target_fixture_ids=("target",)
    ).payload()


def _fixture(fixture_id: str, kickoff: datetime, status: str) -> dict[str, object]:
    return {
        "fixture": {
            "id": fixture_id,
            "date": kickoff.isoformat().replace("+00:00", "Z"),
            "status": {"short": status},
        },
        "league": {"id": 169, "season": 2026},
        "teams": {"home": {"id": "home"}, "away": {"id": "away"}},
        "goals": {"home": 2, "away": 1},
    }


def _stats(team_id: str, xg: float) -> dict[str, object]:
    return {
        "team": {"id": team_id},
        "statistics": [{"type": "expected_goals", "value": xg}],
    }


def _wrapper(params: dict[str, str], response: list[dict[str, object]]) -> dict[str, object]:
    return {
        "captured_at": "2026-07-10T00:00:00Z",
        "params": params,
        "payload": {"response": response},
    }


def _write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
