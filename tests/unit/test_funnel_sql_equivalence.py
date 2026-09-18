from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from w2.api.repository import (
    _model_forecast_market_evaluation_funnel,
    _model_forecast_market_evaluation_funnel_sql,
)
from w2.infrastructure.database import Base
from w2.infrastructure.persistence.dynamic_prematch_models import (
    DynamicPrematchEvaluationModel,
    DynamicPrematchOpportunityModel,
    DynamicPrematchSupersessionModel,
)
from w2.infrastructure.persistence.model_forecast_models import ModelForecastCaptureModel

NOW = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _capture(fixture_id: str = "fix1") -> ModelForecastCaptureModel:
    return ModelForecastCaptureModel(
        capture_identity_hash="c1",
        fixture_id=f"api_football:{fixture_id}",
        competition_id="league1",
        kickoff_utc=NOW,
        captured_at=NOW - timedelta(hours=1),
        lead_time_seconds=3600,
        lead_time_bucket="LT_6H",
        model_family="test",
        model_version="v1",
        capture_policy="FIRST_ELIGIBLE_FREEZE_IMMUTABLE",
        horizon_id="NONE",
        model_input_manifest_hash="a" * 64,
        four_field_xg_identity_hash="b" * 64,
        score_matrix_hash="c" * 64,
        payload={},
        payload_sha256="d" * 64,
        inserted_at=NOW - timedelta(hours=1),
    )


def _eval(
    evaluation_id: str,
    *,
    fixture_id: str = "fix1",
    market: str = "ASIAN_HANDICAP",
    slot: str = "T3_ODDS",
    policy: str = "candidate-eval.v2",
    capture: str = "c1",
    gate_results: dict | None = None,
    first_failed_gate: str | None = None,
    denominator_scope: str = "CHECKPOINT_EVALUATION_OPPORTUNITY_V2",
    semantics: str = "CHECKPOINT_EVALUATION_OPPORTUNITY",
    eligible: bool = True,
    evaluated_at: datetime | None = None,
    opp_hash: str | None = None,
) -> DynamicPrematchEvaluationModel:
    return DynamicPrematchEvaluationModel(
        evaluation_id=evaluation_id,
        identity_hash=hashlib.sha256(evaluation_id.encode()).hexdigest(),
        fixture_id=fixture_id,
        market=market,
        selection="HOME",
        checkpoint=slot,
        evaluated_at=evaluated_at or NOW,
        capture_at=NOW,
        original_state="EVALUATED_CANDIDATE",
        official_funnel_eligible=eligible,
        denominator_scope=denominator_scope,
        measurement_semantics=semantics,
        evaluation_policy_version=policy,
        evaluation_slot_id=slot,
        model_forecast_capture_identity_hash=capture,
        opportunity_identity_hash=opp_hash or f"opp-{evaluation_id}",
        attempt_identity_hash=f"att-{evaluation_id}",
        recorded_at=NOW,
        first_failed_gate=first_failed_gate,
        gate_results=gate_results,
        payload={"state": "ANALYSIS_PICK_ACTIVE"},
    )


def _opportunity(
    opp_hash: str,
    *,
    fixture_id: str = "fix1",
    market: str = "ASIAN_HANDICAP",
    slot: str = "T3_ODDS",
    state: str = "EVALUATED_CANDIDATE",
) -> DynamicPrematchOpportunityModel:
    return DynamicPrematchOpportunityModel(
        opportunity_identity_hash=opp_hash,
        fixture_id=fixture_id,
        market=market,
        model_forecast_capture_identity_hash="c1",
        evaluation_policy_version="candidate-eval.v2",
        evaluation_slot_id=slot,
        scheduled_checkpoint_at=NOW,
        checkpoint_plan_identity=f"plan-{opp_hash}",
        state=state,
        recorded_at=NOW,
        payload={},
    )


def _run(session: Session, captures, evaluations, opportunities, superseded):
    old = _model_forecast_market_evaluation_funnel(
        captures, evaluations, set(superseded), opportunities
    )
    new = _model_forecast_market_evaluation_funnel_sql(session, captures)
    return old, new


def _assert_equal(old, new):
    assert old == new, (
        f"funnel 结果不相等\n"
        f"gate_counts old={old['gate_counts']} new={new['gate_counts']}\n"
        f"first_failed old={old['first_failed_gate_counts']} new={new['first_failed_gate_counts']}\n"
        f"invalid old={old['invalid_opportunity_reasons']} new={new['invalid_opportunity_reasons']}\n"
        f"status old={old['measurement_status']} new={new['measurement_status']}"
    )


def test_funnel_sql_equals_python_basic():
    engine = _engine()
    gate = {
        "model_ready": True,
        "mainline_parsed": True,
        "bookmaker_depth": True,
        "quote_fresh": True,
        "evaluated": True,
        "no_edge": False,
        "candidate": True,
    }
    with Session(engine) as session:
        captures = [_capture()]
        evaluations = [
            _eval("e1", gate_results=dict(gate)),
            _eval("e2", market="TOTALS", slot="T60_ODDS_LINEUPS", gate_results=dict(gate)),
        ]
        opportunities = [
            _opportunity("opp-e1"),
            _opportunity("opp-e2", market="TOTALS", slot="T60_ODDS_LINEUPS"),
        ]
        session.add_all(captures + evaluations + opportunities)
        session.commit()
        old, new = _run(session, captures, evaluations, opportunities, [])
    _assert_equal(old, new)
    assert old["opportunity_count"] == 2
    assert old["gate_counts"]["candidate"] == 2
    assert old["gate_counts"]["no_edge"] == 0


def test_funnel_sql_equals_python_dedup_latest():
    engine = _engine()
    gate_win = {"model_ready": True, "mainline_parsed": True, "bookmaker_depth": True, "quote_fresh": True, "evaluated": True, "no_edge": False, "candidate": True}
    gate_noedge = {"model_ready": True, "mainline_parsed": True, "bookmaker_depth": True, "quote_fresh": True, "evaluated": True, "no_edge": True, "candidate": False}
    with Session(engine) as session:
        captures = [_capture()]
        # 同一 (capture, policy, slot, market) 两次评估，latest 是 no_edge
        evaluations = [
            _eval("e1-old", gate_results=dict(gate_win), evaluated_at=NOW - timedelta(minutes=5), opp_hash="opp-e1-new"),
            _eval("e1-new", gate_results=dict(gate_noedge), evaluated_at=NOW),
        ]
        opportunities = [_opportunity("opp-e1-new")]
        session.add_all(captures + evaluations + opportunities)
        session.commit()
        old, new = _run(session, captures, evaluations, opportunities, [])
    _assert_equal(old, new)
    assert old["gate_counts"]["candidate"] == 0
    assert old["gate_counts"]["no_edge"] == 1


def test_funnel_sql_equals_python_superseded():
    engine = _engine()
    gate = {"model_ready": True, "mainline_parsed": True, "bookmaker_depth": True, "quote_fresh": True, "evaluated": True, "no_edge": False, "candidate": True}
    with Session(engine) as session:
        captures = [_capture()]
        evaluations = [
            _eval("e1", gate_results=dict(gate)),
            _eval("e2", gate_results=dict(gate)),
        ]
        opportunities = [_opportunity("opp-e1"), _opportunity("opp-e2")]
        superseded = [DynamicPrematchSupersessionModel(superseded_evaluation_id="e2", superseded_by_evaluation_id="e1", fixture_id="fix1", market="ASIAN_HANDICAP", reason="retry", created_at=NOW)]
        session.add_all(captures + evaluations + opportunities + superseded)
        session.commit()
        old, new = _run(session, captures, evaluations, opportunities, ["e2"])
    _assert_equal(old, new)
    assert old["gate_counts"]["candidate"] == 1


def test_funnel_sql_equals_python_defects():
    engine = _engine()
    gate = {"model_ready": True, "mainline_parsed": True, "bookmaker_depth": True, "quote_fresh": True, "evaluated": True, "no_edge": False, "candidate": True}
    with Session(engine) as session:
        captures = [_capture()]
        evaluations = [
            _eval("good", gate_results=dict(gate)),
            # scope mismatch -> SCOPE_MISMATCH
            _eval("bad-scope", gate_results=dict(gate), denominator_scope="WRONG"),
            # market not registered -> MARKET_NOT_REGISTERED
            _eval("bad-market", market="WRONG_MARKET", gate_results=dict(gate)),
            # opportunity missing -> OPPORTUNITY_ROW_MISSING
            _eval("bad-no-opp", gate_results=dict(gate)),
        ]
        opportunities = [
            _opportunity("opp-good"),
            _opportunity("opp-bad-scope"),
            _opportunity("opp-bad-market", market="WRONG_MARKET"),
        ]
        session.add_all(captures + evaluations + opportunities)
        session.commit()
        old, new = _run(session, captures, evaluations, opportunities, [])
    _assert_equal(old, new)
    assert old["invalid_opportunity_reasons"] == {
        "MARKET_NOT_REGISTERED": 1,
        "OPPORTUNITY_ROW_MISSING": 1,
        "SCOPE_MISMATCH": 1,
    }


def test_funnel_sql_equals_python_first_failed():
    engine = _engine()
    gate_ok = {"model_ready": True, "mainline_parsed": True, "bookmaker_depth": True, "quote_fresh": True, "evaluated": True, "no_edge": False, "candidate": True}
    with Session(engine) as session:
        captures = [_capture()]
        evaluations = [
            _eval("e1", gate_results=dict(gate_ok), first_failed_gate=None),
            _eval("e2", market="TOTALS", slot="T60_ODDS_LINEUPS", gate_results=dict(gate_ok), first_failed_gate="bookmaker_depth"),
        ]
        opportunities = [
            _opportunity("opp-e1"),
            _opportunity("opp-e2", market="TOTALS", slot="T60_ODDS_LINEUPS"),
            # 未评估的 opportunity -> 计入 state
            _opportunity("opp-unassessed", fixture_id="fix2", state="MISSED_CHECKPOINT"),
        ]
        session.add_all(captures + evaluations + opportunities)
        session.commit()
        old, new = _run(session, captures, evaluations, opportunities, [])
    _assert_equal(old, new)
    assert old["first_failed_gate_counts"]["bookmaker_depth"] == 1
    assert old["first_failed_gate_counts"]["MISSED_CHECKPOINT"] == 1
