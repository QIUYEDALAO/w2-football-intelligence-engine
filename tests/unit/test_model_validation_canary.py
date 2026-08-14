from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from w2.domain.canonical_serialization import canonical_sha256
from w2.infrastructure.persistence.future_refresh_models import (
    RawPayloadModel,
    RawStatisticsRetentionModel,
)
from w2.infrastructure.persistence.model_forecast_models import (
    ModelForecastCaptureModel,
    ModelForecastOutcomeModel,
)
from w2.ingestion.xg_retention import XgRetentionHardeningService
from w2.tracking.model_forecast_ledger import (
    MODEL_FORECAST_CAPTURE_HASH_DOMAIN,
    MODEL_FORECAST_OUTCOME_HASH_DOMAIN,
)
from w2.tracking.model_validation_canary import (
    CANARY_TERMINAL,
    free_mode_model_validation_canary,
    write_pro_reopen_owner_decision_packet,
)

NOW = datetime(2026, 8, 14, tzinfo=UTC)


def test_canary_requires_nonempty_capture_outcome_and_metrics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = _engine(tmp_path)
    _retention_pass(monkeypatch)

    report = free_mode_model_validation_canary(engine=engine, now=NOW)

    assert report["status"] == "BLOCKED"
    assert report["provider_calls"] == 0
    assert report["db_writes"] == 0
    assert "MODEL_FORECAST_CAPTURE_COUNT" in report["blockers"]
    with pytest.raises(ValueError, match="PRO_REOPEN_OWNER_DECISION_PACKET_REQUIRES_CANARY_PASS"):
        write_pro_reopen_owner_decision_packet(tmp_path / "packet.md", report)


def test_canary_passes_valid_independent_ledger_and_unlocks_packet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = _engine(tmp_path)
    _retention_pass(monkeypatch)
    _seed_valid_capture_and_outcome(engine)

    report = free_mode_model_validation_canary(engine=engine, now=NOW)

    assert report["status"] == CANARY_TERMINAL
    assert report["metrics"] == {
        "MODEL_ELIGIBLE_COUNT": 1,
        "MODEL_FORECAST_CAPTURE_COUNT": 1,
        "MODEL_FORECAST_SETTLED_COUNT": 1,
        "PROBABILITY_METRICS_SAMPLE_COUNT": 1,
        "SHADOW_CANDIDATE_COUNT": 0,
        "RAW_STATISTICS_RESTORE_HASH_MATCH": True,
    }
    assert report["model_forecast_ledger_integrity"]["invalid_capture_count"] == 0
    packet = tmp_path / "PRO_REOPEN_OWNER_DECISION_PACKET.md"
    write_pro_reopen_owner_decision_packet(packet, report)
    assert "OWNER_DECISION_REQUIRED" in packet.read_text(encoding="utf-8")


def _engine(tmp_path: Path):  # type: ignore[no-untyped-def]
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'canary.db'}")
    RawPayloadModel.__table__.create(engine)
    RawStatisticsRetentionModel.__table__.create(engine)
    ModelForecastCaptureModel.__table__.create(engine)
    ModelForecastOutcomeModel.__table__.create(engine)
    return engine


def _retention_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        XgRetentionHardeningService,
        "audit",
        lambda _self: {
            "status": "PASS",
            "raw_statistics_count": 1,
            "raw_statistics_aggregate_hash": "1" * 64,
            "team_xg_match_expected_count": 2,
            "team_xg_match_expected_hash": "2" * 64,
            "rolling_snapshot_expected_count": 2,
            "rolling_snapshot_expected_hash": "3" * 64,
            "raw_statistics_restore_hash_match": True,
            "blockers": [],
        },
    )


def _seed_valid_capture_and_outcome(engine) -> None:  # type: ignore[no-untyped-def]
    kickoff = NOW + timedelta(hours=1)
    capture_core = {
        "schema_version": "w2.model_forecast_capture.v1",
        "fixture_identity": {"fixture_id": "fixture-1"},
        "competition_identity": {"competition_id": "allsvenskan"},
        "kickoff_utc": kickoff.isoformat().replace("+00:00", "Z"),
        "captured_at": NOW.isoformat().replace("+00:00", "Z"),
        "candidate_required": False,
        "exact_quote_required": False,
    }
    capture_identity = canonical_sha256(capture_core, domain=MODEL_FORECAST_CAPTURE_HASH_DOMAIN)
    capture_payload = {**capture_core, "capture_identity_hash": capture_identity}
    outcome_core = {
        "schema_version": "w2.model_forecast_outcome.v1",
        "capture_identity_hash": capture_identity,
        "fixture_id": "fixture-1",
        "authoritative_result_identity": "4" * 64,
        "final_score": {"home": 1, "away": 0, "status": "FT"},
        "actual_outcome": "HOME",
        "brier": 0.38,
        "log_loss": 0.69314718056,
        "rps": 0.17,
        "ece_input": {
            "predicted_class": "HOME",
            "confidence": 0.5,
            "actual_class": "HOME",
            "correct": True,
        },
        "settled_at": (kickoff + timedelta(hours=2)).isoformat().replace("+00:00", "Z"),
    }
    outcome_identity = canonical_sha256(outcome_core, domain=MODEL_FORECAST_OUTCOME_HASH_DOMAIN)
    outcome_payload = {
        **outcome_core,
        "capture_to_outcome_identity_hash": outcome_identity,
        "outcome_identity_hash": outcome_identity,
    }
    with Session(engine) as session:
        session.add(
            ModelForecastCaptureModel(
                capture_identity_hash=capture_identity,
                fixture_id="fixture-1",
                competition_id="allsvenskan",
                kickoff_utc=kickoff,
                captured_at=NOW,
                model_family="EXACT_DC_POISSON",
                model_version="model-v1",
                model_input_manifest_hash="5" * 64,
                four_field_xg_identity_hash="6" * 64,
                score_matrix_hash="7" * 64,
                payload=capture_payload,
                payload_sha256=canonical_sha256(
                    capture_payload, domain=MODEL_FORECAST_CAPTURE_HASH_DOMAIN
                ),
                inserted_at=NOW,
            )
        )
        session.add(
            ModelForecastOutcomeModel(
                outcome_identity_hash=outcome_identity,
                capture_identity_hash=capture_identity,
                fixture_id="fixture-1",
                authoritative_result_identity="4" * 64,
                brier=0.38,
                log_loss=0.69314718056,
                rps=0.17,
                settled_at=kickoff + timedelta(hours=2),
                payload=outcome_payload,
                payload_sha256=canonical_sha256(
                    outcome_payload, domain=MODEL_FORECAST_OUTCOME_HASH_DOMAIN
                ),
                inserted_at=NOW,
            )
        )
        session.commit()
