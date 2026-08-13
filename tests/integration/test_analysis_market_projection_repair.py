from __future__ import annotations

from datetime import UTC, datetime

import pytest
from scripts.repair_analysis_market_projection_v4 import (
    repair_analysis_market_projection_v4,
)
from sqlalchemy import create_engine, select

from w2.competitions.seed import seed_competition_runtime_authority
from w2.infrastructure.database import Base
from w2.infrastructure.persistence.api_models import ReadModelCheckpointModel

NOW = datetime(2026, 8, 13, 5, 0, tzinfo=UTC)


def test_projection_repair_is_dry_by_default_and_exactly_guarded(tmp_path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'projection-repair.db'}")
    Base.metadata.create_all(engine)
    seed_competition_runtime_authority(engine, environment="test", now=NOW)
    with engine.begin() as connection:
        connection.execute(
            ReadModelCheckpointModel.__table__.insert(),
            [
                _checkpoint("eligible", "allsvenskan", "v3-source", "v3"),
                _checkpoint("current", "allsvenskan", "v4-source", "v4"),
                _checkpoint("world-cup", "world_cup_2026", "world-source", "v3"),
            ],
        )

    dry_run = repair_analysis_market_projection_v4(engine)

    assert (dry_run.mode, dry_run.scanned, dry_run.eligible, dry_run.updated) == (
        "DRY_RUN",
        3,
        1,
        0,
    )
    assert dry_run.provider_calls == 0
    assert dry_run.targets == (
        {
            "checkpoint_key": "analysis-card:shadow:v1:eligible",
            "fixture_id": "eligible",
            "competition_id": "allsvenskan",
            "source_hash": "v3-source",
            "source_event_type": "ODDS_CHANGED",
            "source_event_id": "capture-eligible",
            "source_event_hash": "event-eligible",
            "old_contract_version": "w2.analysis-market-evidence-projection.v3",
            "old_market_depth": {"ASIAN_HANDICAP": 1, "TOTALS": 7},
        },
    )
    with engine.connect() as connection:
        versions = list(
            connection.execute(
                select(ReadModelCheckpointModel.payload).order_by(
                    ReadModelCheckpointModel.checkpoint_key
                )
            )
        )
    assert len(versions) == 3
    assert versions[1].payload["input_manifest"][
        "analysis_evidence_contract_version"
    ] == "w2.analysis-market-evidence-projection.v3"

    with pytest.raises(ValueError, match="--apply requires"):
        repair_analysis_market_projection_v4(engine, apply=True)
    with pytest.raises(RuntimeError, match="EXPECTED_COUNT_MISMATCH"):
        repair_analysis_market_projection_v4(
            engine,
            apply=True,
            expected_count=2,
            expected_target_sha256=dry_run.target_sha256,
        )
    with pytest.raises(RuntimeError, match="EXPECTED_TARGET_MISMATCH"):
        repair_analysis_market_projection_v4(
            engine,
            apply=True,
            expected_count=1,
            expected_target_sha256="0" * 64,
        )


def _checkpoint(
    fixture_id: str,
    competition_id: str,
    source_hash: str,
    version: str,
) -> dict[str, object]:
    contract = f"w2.analysis-market-evidence-projection.{version}"
    return {
        "checkpoint_key": f"analysis-card:shadow:v1:{fixture_id}",
        "source_hash": source_hash,
        "created_at": NOW,
        "payload": {
            "checkpoint_namespace": "shadow",
            "fixture_identity": {
                "fixture_id": fixture_id,
                "competition_id": competition_id,
            },
            "input_manifest": {
                "analysis_evidence_contract_version": contract,
            },
            "source_event_type": "ODDS_CHANGED",
            "source_event_id": f"capture-{fixture_id}",
            "source_event_hash": f"event-{fixture_id}",
            "source_event_at": NOW.isoformat(),
            "analysis_card": {
                "fixture_id": fixture_id,
                "competition_id": competition_id,
                "market_radar": {
                    "markets": {
                        "ASIAN_HANDICAP": {"current": {"bookmaker_count": 1}},
                        "TOTALS": {"current": {"bookmaker_count": 7}},
                    }
                },
            },
        },
    }
