"""A-R5: one real chain -- synthetic source rows -> real producer/materializer ->
real frozen writer/reader -> real run_model_forecast_capture -> real opportunity
binding -> real forward writer -- the same source identity through every stage,
ending PROVABLE. This is the positive sample every R5 counter-example mutates.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from w2.domain.canonical_serialization import _canonical_hash, canonical_sha256
from w2.infrastructure.persistence.api_models import ReadModelCheckpointModel
from w2.infrastructure.persistence.dynamic_prematch_models import (
    CandidateNotificationOutboxModel,
    DynamicPrematchEvaluationModel,
    DynamicPrematchOpportunityModel,
    DynamicPrematchSupersessionModel,
    LineupConfirmedEventModel,
)
from w2.infrastructure.persistence.forward_evidence_models import (
    ForwardClockModel,
    RecommendationReviewLedgerModel,
)
from w2.infrastructure.persistence.future_refresh_models import (
    TeamXgMatchModel,
    TeamXgRollingSnapshotModel,
)
from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayCheckpointPlanModel,
    MatchdayMarketObservationModel,
)
from w2.infrastructure.persistence.model_forecast_models import (
    ModelForecastCaptureDataVersionModel,
    ModelForecastCaptureModel,
)
from w2.infrastructure.persistence.models import ResultModel
from w2.prematch.analysis_calculator import ReadModelService
from w2.prematch.evaluation_slots import CURRENT_EVALUATION_POLICY
from w2.prematch.lifecycle import (
    DynamicEvaluationState,
    EvaluationOpportunityContext,
)
from w2.prematch.read_model_projection import (
    AnalysisCardCanaryMaterializer,
    ProjectionSourceEvent,
    read_frozen_analysis_artifact,
    write_frozen_analysis_artifacts,
)
from w2.prematch.repository import DynamicPrematchRepository
from w2.tracking.forward_evidence import (
    T0,
    append_forward_evidence_in_session,
    register_forward_clock,
)
from w2.tracking.model_forecast_ledger import (
    MODEL_FORECAST_CAPTURE_HASH_DOMAIN,
    MODEL_FORECAST_INPUT_MANIFEST_HASH_DOMAIN,
    ModelForecastLedgerRepository,
    _capture_model,
    run_model_forecast_capture,
)

FIXTURE_ID = "1576804"
# Everything after T0 so the forward clock accepts the evaluation time.
KICKOFF = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
XG_AS_OF = datetime(2026, 9, 25, 8, 0, tzinfo=UTC)
QUOTE_AT = datetime(2026, 9, 25, 7, 30, tzinfo=UTC)
CAPTURED_AT = datetime(2026, 9, 25, 8, 10, tzinfo=UTC)
EVALUATED_AT = datetime(2026, 9, 25, 9, 0, tzinfo=UTC)


def _z(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


class ScopedRepository:
    """Materializer-scoped source rows (synthetic upstream IO)."""

    fixture_id: str = FIXTURE_ID

    def __init__(self) -> None:
        self.fixture = {
            "fixture": {
                "id": FIXTURE_ID,
                "date": _z(KICKOFF),
                "status": {"short": "NS"},
            },
            "league": {"id": "allsvenskan", "name": "Allsvenskan"},
            "teams": {
                "home": {"id": "home", "name": "Home"},
                "away": {"id": "away", "name": "Away"},
            },
        }
        self.observations = [
            {
                "observation_id": "observation-1",
                "fixture_id": FIXTURE_ID,
                "canonical_market": "TOTALS",
                "captured_at": _z(QUOTE_AT),
                "selection": "Over",
                "line": "2.5",
                "decimal_odds": "1.91",
            }
        ]

    def fixture_payload(self, fixture_id: str) -> dict[str, Any] | None:
        return self.fixture if fixture_id == self.fixture_id else None

    def future_market_observations_for_fixtures(
        self, fixture_ids: list[str]
    ) -> list[dict[str, Any]]:
        return [dict(row) for row in self.observations]

    def canonical_lineup_confirmed_event(self, fixture_id: str) -> Any:
        return None

    def matchday_fixture_identity(self, fixture_id: str) -> dict[str, Any] | None:
        if fixture_id != self.fixture_id:
            return None
        return {
            "status": "READY",
            "fixture_id": fixture_id,
            "provider": "api_football",
            "provider_fixture_id": fixture_id,
            "competition_id": "allsvenskan",
            "season": "2026",
        }


class FrozenReaderRepository:
    """Read-only repository that serves the frozen checkpoint from the local DB."""

    def __init__(self, engine: Any) -> None:
        self.engine = engine

    def analysis_card_canary_artifact(self, fixture_id: str) -> Any:
        return read_frozen_analysis_artifact(self.engine, fixture_id)

    def dynamic_prematch_lifecycle(self, fixture_id: str) -> dict[str, Any]:
        return DynamicPrematchRepository(self.engine).lifecycle(fixture_id)


def _simulation() -> dict[str, Any]:
    distribution = [
        {"home_goals": 0, "away_goals": 0, "probability": 0.25},
        {"home_goals": 2, "away_goals": 1, "probability": 0.5},
        {"home_goals": 3, "away_goals": 0, "probability": 0.25},
    ]
    return {
        "status": "READY",
        "model_version": "w2.formal.exact_dc_poisson.v1",
        "calibration_version": "w2.calibration.v1",
        "calibration_status": "PRODUCTION_VALIDATED",
        "calibration_identity": "c" * 64,
        "lambda_home": 1.4,
        "lambda_away": 0.9,
        "lambda_sigma_home": 0.5,
        "lambda_sigma_away": 0.4,
        "calibration": {
            "simulation_input_hash": "f" * 64,
            "params": {"dixon_coles_rho": -0.08},
            "lambda_uncertainty_method": "empirical_xg_standard_error.v2_latest_five",
            "lambda_uncertainty_status": "ANALYSIS_READY",
        },
        "input_readiness": {
            "neutral_site": False,
            "lambda_uncertainty_input_hash": "g" * 64,
        },
        "score_matrix_summary": {
            "home_win": 0.75,
            "draw": 0.0,
            "away_win": 0.25,
            "score_matrix_hash": _canonical_hash(distribution),
            "distribution": distribution,
        },
        "ah_probabilities": {
            "ladder": [
                {
                    "home_line": -0.5,
                    "home_settlement_distribution": {
                        "WIN": 0.5, "HALF_WIN": 0.0, "PUSH": 0.0,
                        "HALF_LOSS": 0.0, "LOSS": 0.5,
                    },
                    "away_settlement_distribution": {
                        "WIN": 0.5, "HALF_WIN": 0.0, "PUSH": 0.0,
                        "HALF_LOSS": 0.0, "LOSS": 0.5,
                    },
                }
            ]
        },
        "ou_probabilities": {"ladder": [{"line": 2.5}]},
    }


def _flat_card() -> dict[str, Any]:
    return {
        "fixture_id": FIXTURE_ID,
        "competition_id": "allsvenskan",
        "kickoff_utc": _z(KICKOFF),
        "data_readiness": {"xg_observed_at": _z(XG_AS_OF)},
        "simulation": _simulation(),
        "neutral_site_resolution": {
            "neutral_site": False,
            "neutral_site_resolution_source": "DEFAULT_NON_NEUTRAL_POLICY",
            "neutral_site_policy_version": "w2.neutral_site_policy.v1",
            "neutral_site_as_of": _z(QUOTE_AT),
            "neutral_site_status": "READY",
        },
        "market_candidates": {
            "ou": {
                "market": "TOTALS",
                "selection": "OVER",
                "line": "2.5",
                "market_mainline": {
                    "bookmaker_count": 3,
                    "complete_pair_bookmaker_count": 3,
                },
                "analysis_evidence": {
                    "side_evidence": {
                        "OVER": {
                            "model_probability": {
                                "status": "READY",
                                "settlement_distribution": {
                                    "WIN": 0.75, "HALF_WIN": 0.0, "PUSH": 0.0,
                                    "HALF_LOSS": 0.0, "LOSS": 0.25,
                                },
                                "effective_probability": 0.75,
                                "expected_value": 0.08,
                                "ev_se": 0.01,
                            },
                            "comparison": {"cashflow_price_edge": 0.10},
                        }
                    },
                    "quote_identity": {
                        "identity_status": "COMPLETE",
                        "freshness_status": "COMPLETE",
                        "quotes": {
                            "over": {
                                "line": "2.5",
                                "provider": "api_football",
                                "bookmaker_id": "4",
                                "capture_id": "capture-1",
                                "captured_at": _z(QUOTE_AT),
                                "decimal_odds": "1.91",
                            }
                        },
                    },
                    "market_probability": {"devig": {"OVER": 0.52, "UNDER": 0.48}},
                },
            }
        },
        "quote_identity_audit": {},
        "lineup_provenance": {},
    }


def _engine() -> Any:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    ReadModelCheckpointModel.__table__.create(engine)
    DynamicPrematchEvaluationModel.__table__.create(engine)
    DynamicPrematchOpportunityModel.__table__.create(engine)
    CandidateNotificationOutboxModel.__table__.create(engine)
    DynamicPrematchSupersessionModel.__table__.create(engine)
    LineupConfirmedEventModel.__table__.create(engine)
    MatchdayCheckpointPlanModel.__table__.create(engine)
    ModelForecastCaptureModel.__table__.create(engine)
    ModelForecastCaptureDataVersionModel.__table__.create(engine)
    TeamXgMatchModel.__table__.create(engine)
    TeamXgRollingSnapshotModel.__table__.create(engine)
    MatchdayMarketObservationModel.__table__.create(engine)
    ForwardClockModel.__table__.create(engine)
    RecommendationReviewLedgerModel.__table__.create(engine)
    ResultModel.__table__.create(engine)
    return engine


def _seed_xg(engine: Any) -> None:
    with Session(engine) as session:
        for team_id, xg_for, xg_against in (
            ("home", 1.2, 0.8),
            ("away", 0.8, 1.2),
        ):
            for index in range(3):
                session.add(
                    TeamXgMatchModel(
                        id=f"history-{index}:{team_id}",
                        fixture_id=f"history-{index}",
                        team_id=team_id,
                        opponent_team_id="away" if team_id == "home" else "home",
                        kickoff_at=KICKOFF - timedelta(days=4 - index),
                        captured_at=KICKOFF - timedelta(days=3 - index),
                        xg_for=xg_for,
                        xg_against=xg_against,
                        goals_for=1,
                        goals_against=0,
                        raw_payload_sha256=f"{index + 1}" * 64,
                        source_system="api_football_statistics",
                        candidate=False,
                        formal_recommendation=False,
                    )
                )
            session.add(
                TeamXgRollingSnapshotModel(
                    snapshot_id=f"{team_id}:{FIXTURE_ID}",
                    team_id=team_id,
                    as_of_fixture_id=FIXTURE_ID,
                    as_of_time=XG_AS_OF,
                    match_count=3,
                    rolling_xg_for=xg_for,
                    rolling_xg_against=xg_against,
                    rolling_goals_for=1.0,
                    rolling_goals_against=0.0,
                    regression_index=0.0,
                    source_system="team_xg_match",
                    candidate=False,
                    formal_recommendation=False,
                )
            )
        session.commit()


def _seed_quote_pair(engine: Any) -> None:
    with Session(engine) as session:
        for selection, odds in (("OVER", "1.91"), ("UNDER", "1.85")):
            session.add(
                MatchdayMarketObservationModel(
                    observation_id=f"obs-{selection}",
                    fixture_id=f"api_football:{FIXTURE_ID}",
                    provider_fixture_id=FIXTURE_ID,
                    competition_id="allsvenskan",
                    provider="api_football",
                    bookmaker_id="4",
                    bookmaker_name="Bookmaker",
                    capture_id="capture-1",
                    provider_bet_id="4",
                    raw_market_label="Over/Under",
                    canonical_market="TOTALS",
                    canonical_selection=selection,
                    provider_selection=selection,
                    line="2.5",
                    decimal_odds=odds,
                    suspended=False,
                    live=False,
                    provider_updated_at=QUOTE_AT,
                    captured_at=QUOTE_AT,
                    ingested_at=QUOTE_AT,
                    raw_payload_sha256="a" * 64,
                    source_revision="s" * 64,
                )
            )
        session.commit()


def _materializer() -> AnalysisCardCanaryMaterializer:
    def calculate(repository: Any, fixture_id: str, evaluated_at: datetime) -> dict[str, Any] | None:
        del repository, evaluated_at
        if fixture_id != FIXTURE_ID:
            return None
        return deepcopy(_flat_card())

    return AnalysisCardCanaryMaterializer(
        ScopedRepository(),
        calculate_analysis_card=calculate,
        build_scoreline_reference=lambda card, version, quote_identity: {
            "source": "formal_simulation",
            "scoreline_projection": {
                "status": "READY",
                "decision_hash": version.identity_hash,
                "top3": [{"scoreline": "1-0"}],
            },
        },
        clock=lambda: EVALUATED_AT,
    )


def _event(opportunity_contexts: tuple[EvaluationOpportunityContext, ...] = ()) -> ProjectionSourceEvent:
    event = ProjectionSourceEvent.create(
        fixture_id=FIXTURE_ID,
        event_type="ODDS_CHANGED",
        event_id="odds-changed:capture-1",
        event_at=EVALUATED_AT,
        payload={"capture_id": "capture-1"},
    )
    return replace(event, opportunity_contexts=opportunity_contexts)


def _run_chain(
    engine: Any,
    materializer: AnalysisCardCanaryMaterializer,
    mutate_capture_payload: Any | None = None,
) -> Any:
    """Run the real chain once, optionally mutating the capture payload (resealing
    its outer hashes) before the opportunity is bound, and return the TOTALS
    evaluation plus the bound capture hash."""
    artifact = materializer.build(FIXTURE_ID, evaluated_at=EVALUATED_AT, source_event=None)
    write_frozen_analysis_artifacts(engine, [artifact])

    reader = ReadModelService(repository=FrozenReaderRepository(engine))
    card = reader.public_analysis_card_bounded(FIXTURE_ID, use_frozen_canary=True)
    assert isinstance(card, dict)
    simulation = card.get("simulation") or {}
    model_forecast_card = {
        **card,
        "simulation": {"status": simulation.get("status"), "simulation": simulation},
    }
    result = run_model_forecast_capture(
        {"cards": [model_forecast_card]},
        repository=ModelForecastLedgerRepository(engine),
        captured_at=CAPTURED_AT,
        dry_run=True,
        write_db=False,
    )
    assert result["model_forecast_capture_count"] == 1
    capture = dict(result["captures"][0])

    if mutate_capture_payload is not None:
        mutate_capture_payload(capture)
        identity = {
            key: value for key, value in capture.items() if key != "capture_identity_hash"
        }
        capture["capture_identity_hash"] = canonical_sha256(
            identity, domain=MODEL_FORECAST_CAPTURE_HASH_DOMAIN
        )
        capture["payload_sha256"] = canonical_sha256(
            capture, domain=MODEL_FORECAST_CAPTURE_HASH_DOMAIN
        )
        capture["model_input_manifest_hash"] = canonical_sha256(
            capture["model_input_manifest"],
            domain=MODEL_FORECAST_INPUT_MANIFEST_HASH_DOMAIN,
        )

    with Session(engine) as session:
        session.add(_capture_model(capture, inserted_at=CAPTURED_AT))
        session.commit()

    capture_hash = capture["capture_identity_hash"]
    model_input_hash = capture["model_input_manifest_hash"]

    context = EvaluationOpportunityContext(
        model_forecast_capture_identity_hash=capture_hash,
        model_input_hash=model_input_hash,
        evaluation_policy_version=CURRENT_EVALUATION_POLICY,
        evaluation_slot_id="T3_ODDS",
        scheduled_checkpoint_at=EVALUATED_AT,
        checkpoint_plan_identity="plan-1",
        source_event_identity="event-1",
    )
    bound = materializer.build(
        FIXTURE_ID, evaluated_at=EVALUATED_AT, source_event=_event((context,))
    )
    write_frozen_analysis_artifacts(engine, [bound])
    return next(item for item in bound.evaluations if item.market == "TOTALS")


def _forward(engine: Any, evaluation: Any) -> Any:
    with Session(engine) as session:
        register_forward_clock(session, started_at=T0, code_revision="a" * 40)
        session.commit()
        return append_forward_evidence_in_session(session, evaluation)


def test_real_chain_provable() -> None:
    engine = _engine()
    _seed_xg(engine)
    _seed_quote_pair(engine)
    materializer = _materializer()
    evaluation = _run_chain(engine, materializer)
    assert evaluation.state in (
        DynamicEvaluationState.NO_EDGE_CURRENT,
        DynamicEvaluationState.ANALYSIS_PICK_ACTIVE,
    ), (evaluation.state, evaluation.blockers)
    row = _forward(engine, evaluation)
    assert row is not None
    assert row.pit_status == "PROVABLE", row.payload["exclusion_reasons"]
    assert row.payload["exclusion_reasons"] == []


def test_real_chain_rejects_missing_away_xg_source() -> None:
    engine = _engine()
    _seed_xg(engine)
    _seed_quote_pair(engine)
    materializer = _materializer()

    def mutate(payload: dict) -> None:
        payload["four_field_xg_identity"].pop("away")

    evaluation = _run_chain(engine, materializer, mutate)
    row = _forward(engine, evaluation)
    assert row is not None
    assert row.pit_status == "PIT_UNPROVABLE"
    assert "PRODUCER_INPUT_SOURCE_MISMATCH" in row.payload["exclusion_reasons"]


def test_real_chain_rejects_invalid_away_xg_time() -> None:
    engine = _engine()
    _seed_xg(engine)
    _seed_quote_pair(engine)
    materializer = _materializer()

    def mutate(payload: dict) -> None:
        payload["four_field_xg_identity"]["away"]["as_of"] = "not-a-time"

    evaluation = _run_chain(engine, materializer, mutate)
    row = _forward(engine, evaluation)
    assert row is not None
    assert row.pit_status == "PIT_UNPROVABLE"
    assert "PRODUCER_INPUT_SOURCE_MISMATCH" in row.payload["exclusion_reasons"]
