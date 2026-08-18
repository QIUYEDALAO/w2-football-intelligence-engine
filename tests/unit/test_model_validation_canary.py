from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from w2.api.repository import ReadModelRepository
from w2.api.schemas import WorkspaceModelForecastLedgerFact
from w2.domain.canonical_serialization import canonical_sha256
from w2.infrastructure.persistence.dynamic_prematch_models import (
    DynamicPrematchEvaluationModel,
    DynamicPrematchSupersessionModel,
)
from w2.infrastructure.persistence.future_refresh_models import (
    RawPayloadModel,
    RawStatisticsRetentionModel,
    TeamXgMatchModel,
)
from w2.infrastructure.persistence.matchday_intake_models import MatchdayFixtureIdentityModel
from w2.infrastructure.persistence.model_forecast_models import (
    ModelForecastCaptureDataVersionModel,
    ModelForecastCaptureModel,
    ModelForecastOutcomeModel,
)
from w2.infrastructure.persistence.models import ResultModel
from w2.infrastructure.persistence.outcome_ledger_models import OutcomeLedgerModel
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
    assert (
        report["probability_metrics_by_data_version_and_lead_time"]
        ["TEAM_XG_MATCH_ROWS_2"]["lead_time_buckets"]["LT_6H"]["sample_count"]
        == 1
    )
    packet = tmp_path / "PRO_REOPEN_OWNER_DECISION_PACKET.md"
    write_pro_reopen_owner_decision_packet(packet, report)
    assert "OWNER_DECISION_REQUIRED" in packet.read_text(encoding="utf-8")


def test_dashboard_reads_capture_and_outcome_as_ledger_facts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = _engine(tmp_path)
    _seed_valid_capture_and_outcome(engine)
    _seed_current_flow_candidate_and_outcome(engine)
    _seed_xg_ready_future_fixture(engine)
    repository = ReadModelRepository()
    monkeypatch.setattr(repository, "_database_engine", lambda: engine)

    facts = repository.dashboard_model_forecasts_for_fixtures(["fixture-1", "fixture-not-captured"])
    progress = repository.dashboard_model_forecast_validation_progress()

    assert facts["fixture-1"] == {
        "state": "SETTLED",
        "capture_identity_hash": facts["fixture-1"]["capture_identity_hash"],
        "captured_at": "2026-08-14T00:00:00Z",
        "lead_time_seconds": 3600,
        "lead_time_bucket": "LT_6H",
        "capture_policy": "FIRST_ELIGIBLE_FREEZE_IMMUTABLE",
        "data_version": "TEAM_XG_MATCH_ROWS_2",
        "team_xg_match_count": 2,
        "model_family": "EXACT_DC_POISSON",
        "model_version": "model-v1",
        "calibration_version": "cal-v1",
        "calibration_status": "AVAILABLE",
        "four_field_xg": {
            "status": "READY",
            "identity_hash": "6" * 64,
            "home_snapshot_identity": "home-snapshot",
            "away_snapshot_identity": "away-snapshot",
            "home_match_count": 3,
            "away_match_count": 3,
        },
        "settled_at": "2026-08-14T03:00:00Z",
        "brier": 0.38,
        "log_loss": 0.69314718056,
        "rps": 0.17,
    }
    assert facts["fixture-not-captured"] == {"state": "NOT_CAPTURED"}
    assert progress == {
        "capture_count": 1,
        "settled_count": 1,
        "pending_count": 0,
        "sample_target": 200,
        "current_flow_candidate_count": 1,
        "current_flow_settled_count": 1,
        "min_xg_matches": 3,
        "xg_ready_team_count": 2,
        "next_7d_xg_ready_fixture_count": 1,
        "capture_policy": "FIRST_ELIGIBLE_FREEZE_IMMUTABLE",
        # No opportunity writer runs yet, so the honest answer is that nothing
        # is measurable -- not that every gate failed on a fixture whose
        # checkpoints have not come due.
        "market_evaluation_funnel": {
            "scope": "CHECKPOINT_EVALUATION_OPPORTUNITY_V2",
            "denominator_unit": "CHECKPOINT_EVALUATION_OPPORTUNITY_SLOT_X_MARKET",
            "measurement_status": "NOT_MEASURABLE",
            "invalid_opportunity_row_count": 0,
            "invalid_opportunity_reasons": {},
            "opportunity_count": 0,
            "capture_count": 1,
            "fixture_count": 0,
            "market_unit_count": 0,
            "persisted_market_unit_count": 0,
            "recorded_at_count": 0,
            "gate_counts": {},
            "gate_rates": None,
            "first_failed_gate_counts": {},
        },
        "lead_time_buckets": {
            "LT_6H": {"capture_count": 1, "settled_count": 1, "pending_count": 0},
            "H6_TO_LT_24H": {"capture_count": 0, "settled_count": 0, "pending_count": 0},
            "D1_TO_D3": {"capture_count": 0, "settled_count": 0, "pending_count": 0},
            "GT_3D": {"capture_count": 0, "settled_count": 0, "pending_count": 0},
        },
        "data_versions": {
            "TEAM_XG_MATCH_ROWS_2": {
                "team_xg_match_count": 2,
                "capture_count": 1,
                "settled_count": 1,
                "pending_count": 0,
                "lead_time_buckets": {
                    "LT_6H": {"capture_count": 1, "settled_count": 1, "pending_count": 0},
                    "H6_TO_LT_24H": {
                        "capture_count": 0,
                        "settled_count": 0,
                        "pending_count": 0,
                    },
                    "D1_TO_D3": {
                        "capture_count": 0,
                        "settled_count": 0,
                        "pending_count": 0,
                    },
                    "GT_3D": {
                        "capture_count": 0,
                        "settled_count": 0,
                        "pending_count": 0,
                    },
                },
            }
        },
    }
    captured_fact = WorkspaceModelForecastLedgerFact.model_validate(facts["fixture-1"])
    assert captured_fact.lead_time_seconds == 3600
    assert (
        WorkspaceModelForecastLedgerFact.model_validate(facts["fixture-not-captured"]).state
        == "NOT_CAPTURED"
    )


def _engine(tmp_path: Path):  # type: ignore[no-untyped-def]
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'canary.db'}")
    RawPayloadModel.__table__.create(engine)
    RawStatisticsRetentionModel.__table__.create(engine)
    TeamXgMatchModel.__table__.create(engine)
    DynamicPrematchEvaluationModel.__table__.create(engine)
    DynamicPrematchSupersessionModel.__table__.create(engine)
    MatchdayFixtureIdentityModel.__table__.create(engine)
    ModelForecastCaptureModel.__table__.create(engine)
    ModelForecastCaptureDataVersionModel.__table__.create(engine)
    ModelForecastOutcomeModel.__table__.create(engine)
    OutcomeLedgerModel.__table__.create(engine)
    ResultModel.__table__.create(engine)
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


def _seed_current_flow_candidate_and_outcome(engine) -> None:  # type: ignore[no-untyped-def]
    capture_hash = "7" * 64
    with Session(engine) as session:
        session.add_all(
            [
                OutcomeLedgerModel(
                    business_key="current-flow-capture",
                    record_type="capture",
                    fixture_id="fixture-current-flow",
                    occurred_at=NOW,
                    captured_at=NOW,
                    settled_at=None,
                    schema_version="w2.outcome_ledger.capture.v1",
                    recommendation_scope="SHADOW",
                    capture_identity_hash=capture_hash,
                    decision_hash="8" * 64,
                    payload={"checkpoint": "T-30m_VALIDATION_LOCK"},
                    payload_sha256="9" * 64,
                    source_artifact="db:forward_outcome_ledger",
                    source_line_number=None,
                    imported_at=NOW,
                ),
                OutcomeLedgerModel(
                    business_key="current-flow-outcome",
                    record_type="outcome",
                    fixture_id="fixture-current-flow",
                    occurred_at=NOW,
                    captured_at=NOW,
                    settled_at=NOW,
                    schema_version="w2.outcome_ledger.outcome.v1",
                    recommendation_scope="SHADOW",
                    capture_identity_hash=capture_hash,
                    decision_hash="8" * 64,
                    payload={"result": "WIN"},
                    payload_sha256="a" * 64,
                    source_artifact="db:forward_outcome_ledger",
                    source_line_number=None,
                    imported_at=NOW,
                ),
            ]
        )
        session.commit()


def _seed_valid_capture_and_outcome(engine) -> None:  # type: ignore[no-untyped-def]
    kickoff = NOW + timedelta(hours=1)
    capture_core = {
        "schema_version": "w2.model_forecast_capture.v1",
        "fixture_identity": {"fixture_id": "fixture-1"},
        "competition_identity": {"competition_id": "allsvenskan"},
        "kickoff_utc": kickoff.isoformat().replace("+00:00", "Z"),
        "captured_at": NOW.isoformat().replace("+00:00", "Z"),
        "calibration_version": "cal-v1",
        "calibration_status": "AVAILABLE",
        "four_field_xg_identity": {
            "identity_hash": "6" * 64,
            "home": {"snapshot_identity": "home-snapshot", "match_count": 3},
            "away": {"snapshot_identity": "away-snapshot", "match_count": 3},
        },
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
                lead_time_seconds=3600,
                lead_time_bucket="LT_6H",
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
            ModelForecastCaptureDataVersionModel(
                capture_identity_hash=capture_identity,
                data_version="TEAM_XG_MATCH_ROWS_2",
                team_xg_match_count=2,
                evidence_source="RECORDED_AT_CAPTURE",
                recorded_at=NOW,
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
                lead_time_seconds=3600,
                lead_time_bucket="LT_6H",
                settled_at=kickoff + timedelta(hours=2),
                payload=outcome_payload,
                payload_sha256=canonical_sha256(
                    outcome_payload, domain=MODEL_FORECAST_OUTCOME_HASH_DOMAIN
                ),
                inserted_at=NOW,
            )
        )
        session.add(
            ResultModel(
                fixture_id="fixture-1",
                home_goals=1,
                away_goals=0,
                result_status="FT",
                confirmed_at=kickoff + timedelta(hours=2),
                source_payload_sha256="3" * 64,
                result_hash="4" * 64,
            )
        )
        session.commit()


def _seed_xg_ready_future_fixture(engine) -> None:  # type: ignore[no-untyped-def]
    with Session(engine) as session:
        for team_id, opponent_id in (("10", "20"), ("20", "10")):
            for index in range(3):
                session.add(
                    TeamXgMatchModel(
                        id=f"history-{index}:{team_id}",
                        fixture_id=f"history-{index}",
                        team_id=team_id,
                        opponent_team_id=opponent_id,
                        kickoff_at=NOW - timedelta(days=4 - index),
                        captured_at=NOW,
                        xg_for=1.0,
                        xg_against=0.8,
                        goals_for=1,
                        goals_against=0,
                        raw_payload_sha256=f"{index + 1}" * 64,
                        source_system="api_football.statistics",
                        candidate=False,
                        formal_recommendation=False,
                    )
                )
        session.add(
            MatchdayFixtureIdentityModel(
                fixture_id="w2:fixture:future-ready",
                provider="api_football",
                provider_fixture_id="future-ready",
                competition_id="allsvenskan",
                provider_league_id="113",
                season="2026",
                kickoff_utc=datetime.now(UTC) + timedelta(days=1),
                fixture_status="NS",
                home_provider_team_id="10",
                away_provider_team_id="20",
                home_w2_team_id="w2:team:10",
                away_w2_team_id="w2:team:20",
                team_identity_status="READY",
                raw_payload_sha256="f" * 64,
                captured_at=NOW,
                identity_hash="e" * 64,
                payload={},
            )
        )
        session.commit()
