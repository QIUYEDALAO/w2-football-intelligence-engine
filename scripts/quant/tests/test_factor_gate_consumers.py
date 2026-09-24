"""Test matrix 6, 7 and 8: what the real consumers do with a blocked AH pick.

These do not assert on the state enum. They persist through the production
writer and then call the three functions that actually decide whether a pick
reaches the record: the official funnel projection, the candidate notification
outbox, and the profit-and-loss column that projection produces. Each test is a
pair -- the same evaluation with and without the factor veto -- so a test that
stopped exercising the consumer would fail on the control, not pass silently.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from w2.api import repository as repository_module
from w2.domain.recommendation_decision_v4 import build_recommendation_decision_v4
from w2.infrastructure.database import Base
from w2.infrastructure.persistence.dynamic_prematch_models import (
    CandidateNotificationOutboxModel,
    DynamicPrematchEvaluationModel,
    DynamicPrematchOpportunityModel,
)
from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayFixtureIdentityModel,
)
from w2.prematch.lifecycle import (
    CHECKPOINT_OPPORTUNITY_SCOPE,
    DynamicEvaluationInput,
    DynamicEvaluationState,
    EvaluationOpportunityContext,
    OpportunityState,
    bind_evaluation_opportunity,
    classify_evaluation,
)
from w2.prematch.repository import DynamicPrematchRepository

NOW = datetime(2026, 8, 20, 8, 0, tzinfo=UTC)
ADMITTED = {
    "factor_decision_status": "ADMITTED",
    "factor_direction": "HOME",
    "factor_input_identity": "f" * 64,
    "factor_input_identity_hash": "f" * 64,
}
VETOED = {
    "factor_decision_status": "VETOED",
    "factor_direction": "AWAY",
    "ev_direction": "HOME",
    "factor_veto_code": "FACTOR_EV_DIRECTION_CONFLICT",
    "factor_input_identity": "e" * 64,
    "factor_input_identity_hash": "e" * 64,
}


def _engine():  # type: ignore[no-untyped-def]
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _attempt(fixture_id: str, suffix: str, verdict: dict[str, str]):  # type: ignore[no-untyped-def]
    version = classify_evaluation(
        DynamicEvaluationInput(
            fixture_id=fixture_id,
            market="ASIAN_HANDICAP",
            selection="HOME",
            exact_line=-0.25,
            bookmaker_id="book-1",
            capture_id=f"capture-{suffix}",
            quote_identity_hash=(suffix * 64)[:64],
            model_input_hash="2" * 64,
            evaluated_at=NOW + timedelta(minutes=len(suffix)),
            checkpoint="T15_ODDS",
            capture_at=NOW,
            model_probability=0.60,
            market_probability=0.50,
            expected_value=0.06,
            ev_se=0.01,
            cashflow_price_edge=0.10,
            decimal_odds=1.91,
            bookmaker_count=7,
            mainline_parsed=True,
            calibration_status="PRODUCTION_VALIDATED",
            denominator_scope=CHECKPOINT_OPPORTUNITY_SCOPE,
            **verdict,
        )
    )
    return bind_evaluation_opportunity(
        version,
        EvaluationOpportunityContext(
            model_forecast_capture_identity_hash=(suffix * 64)[:64],
            model_input_hash="2" * 64,
            evaluation_policy_version="candidate-eval.v1",
            evaluation_slot_id="T15_ODDS",
            scheduled_checkpoint_at=NOW + timedelta(minutes=len(suffix)),
            checkpoint_plan_identity=f"plan-{suffix}",
            source_event_identity=f"event-{suffix}",
        ),
    )


def _v4(version):  # type: ignore[no-untyped-def]
    if version.opportunity_state is not OpportunityState.EVALUATED_CANDIDATE:
        return build_recommendation_decision_v4(
            {
                "fixture_id": version.fixture_id,
                "competition_id": "chinese_super_league",
                "kickoff_utc": "2026-08-21T12:00:00Z",
            }
        ).as_dict()
    odds = Decimal(str(version.decimal_odds))
    return build_recommendation_decision_v4(
        {
            "fixture_id": version.fixture_id,
            "competition_id": "chinese_super_league",
            "season": "2026",
            "kickoff_utc": "2026-08-21T12:00:00Z",
            "kickoff_revision_or_fixture_identity_hash": "d" * 64,
            "provider": "api-football",
            "bookmaker_id": version.bookmaker_id,
            "market": version.market,
            "selection": str(version.selection),
            "exact_line": str(version.exact_line),
            "capture_id": version.capture_id,
            "captured_at": version.capture_at.isoformat(),
            "decision_evaluated_at": version.evaluated_at.isoformat(),
            "quote_observation_ids": {"home": "obs-home", "away": "obs-away"},
            "raw_payload_sha256": "a" * 64,
            "source_revision": "e" * 40,
            "model_version": "model-v1",
            "calibration_version": "calibration-v1",
            "serializer_version": "w2.canonical-json.v2",
            "recommendation_schema_version": "w2.recommendation_decision.v4",
            "quote_schema_version": "w2.quote_identity.v1",
            "model_input_manifest_hash": "b" * 64,
            "decimal_odds": str(odds),
            "canonical_mainline_identity": {
                "market": version.market,
                "line": str(version.exact_line),
                "selected_side_line": str(version.exact_line),
                "candidate_role": "MARKET_MAINLINE",
                "quote_identity_hash": version.quote_identity_hash,
            },
            "settlement_distribution": {
                "WIN": "0.6",
                "HALF_WIN": "0",
                "PUSH": "0",
                "HALF_LOSS": "0",
                "LOSS": "0.4",
            },
            "fair_odds": "1.6666666667",
            "expected_value": str(odds * Decimal("0.6") - 1),
            "uncertainty": "0.01",
            "readiness": {
                "status": "READY",
                "quote_identity_status": "COMPLETE",
                "quote_freshness_status": "COMPLETE",
                "quote_freshness_policy_version": "w2.quote_freshness.v1",
                "quote_age_seconds": 60,
                "quote_max_age_seconds": 1800,
                "model_status": "READY",
            },
            "capability_status": "ANALYSIS_ONLY",
            "formal_admission": {
                "status": "DISABLED",
                "readiness_hash": None,
                "approval_hash": None,
                "candidate_identity_hash": None,
            },
            "model_probability": "0.6",
            "market_probability": "0.5",
        }
    ).as_dict()


def _persisted():  # type: ignore[no-untyped-def]
    """Persist one admitted and one vetoed AH pick through the production writer."""
    engine = _engine()
    repository = DynamicPrematchRepository(engine)
    admitted = _attempt("1490401", "a", ADMITTED)
    vetoed = _attempt("1490402", "b", VETOED)
    assert admitted.state is DynamicEvaluationState.ANALYSIS_PICK_ACTIVE
    assert vetoed.state is DynamicEvaluationState.BLOCKED_BY_FACTOR
    for version in (admitted, vetoed):
        repository.append_evaluation(version, recommendation_decision_v4=_v4(version))
    return engine, admitted, vetoed


def _funnel(engine, *, results):  # type: ignore[no-untyped-def]
    with Session(engine) as session:
        evaluations = list(session.scalars(select(DynamicPrematchEvaluationModel)))
        opportunities = list(session.scalars(select(DynamicPrematchOpportunityModel)))
        fixtures = {
            fixture_id: MatchdayFixtureIdentityModel(
                fixture_id=f"api_football:{fixture_id}",
                provider="api_football",
                provider_fixture_id=fixture_id,
                competition_id="chinese_super_league",
                provider_league_id="169",
                season="2026",
                kickoff_utc=NOW + timedelta(days=1),
                fixture_status="NS",
                home_provider_team_id="home",
                away_provider_team_id="away",
                home_w2_team_id=None,
                away_w2_team_id=None,
                team_identity_status="UNRESOLVED",
                raw_payload_sha256="c" * 64,
                captured_at=NOW,
                identity_hash=(fixture_id * 16)[:64],
                payload={
                    "teams": {"home": {"name": "Home"}, "away": {"name": "Away"}},
                },
            )
            for fixture_id in ("1490401", "1490402")
        }
        return repository_module._official_funnel_recommendations(
            evaluations, opportunities, fixtures, results, {}
        )


# --- matrix 6: a blocked AH never reaches the official recommendation list ---
def test_matrix_6_blocked_ah_is_absent_from_official_recommendations() -> None:
    engine, _admitted, _vetoed = _persisted()

    rows = _funnel(engine, results={})

    picks = {(row["fixture_id"], row["market"]) for row in rows}
    assert ("1490401", "ASIAN_HANDICAP") in picks
    assert ("1490402", "ASIAN_HANDICAP") not in picks
    assert len(rows) == 1


# --- matrix 7: a blocked AH raises no candidate notification ----------------
def test_matrix_7_blocked_ah_emits_no_candidate_notification() -> None:
    engine, admitted, vetoed = _persisted()

    with Session(engine) as session:
        events = list(session.scalars(select(CandidateNotificationOutboxModel)))

    assert admitted.opportunity_identity_hash != vetoed.opportunity_identity_hash
    assert [event.event_type for event in events] == ["VALIDATION_SAMPLE_CONFIRMED"]
    assert events[0].payload["fixture_id"] == admitted.fixture_id
    assert events[0].attempt_identity_hash is None


# --- matrix 8: a blocked AH contributes no profit-and-loss row --------------
def test_matrix_8_blocked_ah_contributes_no_profit_and_loss_row() -> None:
    engine, _admitted, _vetoed = _persisted()
    # both picks are HOME -0.25 and both fixtures lost 0-1, so were the blocked
    # one on the record it would add a further -1.0
    results = {
        f"api_football:{fixture_id}": SimpleNamespace(home_goals=0, away_goals=1)
        for fixture_id in ("1490401", "1490402")
    }

    rows = _funnel(engine, results=results)

    settled = {(row["fixture_id"], row["market"]): row for row in rows}
    assert set(settled) == {("1490401", "ASIAN_HANDICAP")}
    assert settled[("1490401", "ASIAN_HANDICAP")]["settlement"] == "LOSS"
    total = sum(Decimal(str(row["profit_units"])) for row in rows)
    assert total == Decimal("-1.0")
