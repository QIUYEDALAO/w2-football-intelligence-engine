from __future__ import annotations

from datetime import UTC, datetime, timedelta

from w2.domain.enums import DataStatus, DecisionReasonCode
from w2.readiness.data_gate import (
    DataFreshnessPolicy,
    DataReadinessInput,
    build_data_readiness_from_legacy_payload,
    evaluate_data_readiness,
)

NOW = datetime(2026, 7, 5, 0, 0, tzinfo=UTC)
KICKOFF = NOW + timedelta(hours=4)
POLICY = DataFreshnessPolicy()


def _input(**overrides: object) -> DataReadinessInput:
    base = {
        "fixture_id": "fixture-1",
        "kickoff_utc": KICKOFF,
        "as_of": NOW,
        "fixture_status": "UPCOMING",
        "market_available": True,
        "odds_available": True,
        "odds_captured_at": NOW - timedelta(minutes=5),
        "lineups_available": True,
        "lineups_captured_at": NOW - timedelta(minutes=5),
        "xg_available": True,
        "xg_captured_at": NOW - timedelta(hours=2),
        "ratings_available": True,
        "ratings_captured_at": NOW - timedelta(hours=2),
        "team_value_available": True,
        "team_value_captured_at": NOW - timedelta(hours=2),
        "provider_budget_status": "AVAILABLE",
        "provider_budget_remaining": 6000,
        "provider_budget_exhausted": False,
        "coverage_supported": True,
    }
    base.update(overrides)
    return DataReadinessInput(**base)  # type: ignore[arg-type]


def test_all_required_fields_fresh_is_ready() -> None:
    result = evaluate_data_readiness(_input(), POLICY)

    assert result.data_status is DataStatus.READY
    assert result.reason_code is None
    assert result.missing_fields == ()
    assert result.stale_fields == ()
    assert result.source == "w2.readiness.data_gate.v1"


def test_fixture_live_or_finished_blocks_prematch_readiness() -> None:
    result = evaluate_data_readiness(_input(fixture_status="FT"), POLICY)

    assert result.data_status is DataStatus.BLOCKED
    assert result.reason_code is DecisionReasonCode.FIXTURE_LIVE_OR_FINISHED
    assert result.next_eval_at is None


def test_unsupported_coverage_blocks() -> None:
    result = evaluate_data_readiness(_input(coverage_supported=False), POLICY)

    assert result.data_status is DataStatus.BLOCKED
    assert result.reason_code is DecisionReasonCode.COVERAGE_NONE


def test_provider_budget_exhausted_marks_stale_without_provider_call() -> None:
    result = evaluate_data_readiness(
        _input(provider_budget_status="EXHAUSTED", provider_budget_exhausted=True),
        POLICY,
    )

    assert result.data_status is DataStatus.STALE
    assert result.reason_code is DecisionReasonCode.PROVIDER_BUDGET_EXHAUSTED
    assert result.next_eval_at == NOW + timedelta(minutes=30)
    assert result.provider_budget_status == "EXHAUSTED"


def test_market_or_odds_missing_blocks() -> None:
    missing_market = evaluate_data_readiness(_input(market_available=False), POLICY)
    missing_odds = evaluate_data_readiness(_input(odds_available=False), POLICY)

    assert missing_market.data_status is DataStatus.BLOCKED
    assert missing_market.reason_code is DecisionReasonCode.MARKET_UNAVAILABLE
    assert missing_odds.data_status is DataStatus.BLOCKED
    assert missing_odds.reason_code is DecisionReasonCode.MARKET_UNAVAILABLE


def test_stale_odds_marks_stale() -> None:
    result = evaluate_data_readiness(
        _input(odds_captured_at=NOW - timedelta(minutes=31)),
        POLICY,
    )

    assert result.data_status is DataStatus.STALE
    assert result.reason_code is DecisionReasonCode.DATA_STALE_ODDS
    assert result.stale_fields == ("odds",)


def test_lineups_missing_before_t90_is_partial_not_blocked() -> None:
    as_of = KICKOFF - timedelta(minutes=120)
    result = evaluate_data_readiness(
        _input(lineups_available=False, as_of=as_of, odds_captured_at=as_of - timedelta(minutes=5)),
        POLICY,
    )

    assert result.data_status is DataStatus.PARTIAL
    assert result.reason_code is DecisionReasonCode.LINEUPS_PENDING
    assert result.missing_fields == ("lineups",)


def test_lineups_missing_after_t30_is_still_partial_by_default() -> None:
    as_of = KICKOFF - timedelta(minutes=20)
    result = evaluate_data_readiness(
        _input(lineups_available=False, as_of=as_of, odds_captured_at=as_of - timedelta(minutes=5)),
        POLICY,
    )

    assert result.data_status is DataStatus.PARTIAL
    assert result.reason_code is DecisionReasonCode.LINEUPS_PENDING


def test_missing_xg_is_partial() -> None:
    result = evaluate_data_readiness(_input(xg_available=False), POLICY)

    assert result.data_status is DataStatus.PARTIAL
    assert result.reason_code is DecisionReasonCode.DATA_MISSING_XG
    assert "xg" in result.missing_fields


def test_baseline_prior_and_calibration_report_are_not_readiness_blockers() -> None:
    result = build_data_readiness_from_legacy_payload(
        card={
            "source": "unit",
            "decision": "PICK",
            "calibration_report": {"n": 42, "baseline": "BASELINE_PRIOR"},
            "pricing_shadow": {
                "formal_blockers": ["AH_EV_BELOW_FORMAL_THRESHOLD"],
                "calibration_report": {"n": 42, "source": "BASELINE_PRIOR"},
            },
        },
        market={"market": "ASIAN_HANDICAP", "decision": "PICK", "line": "-0.25", "odds": "1.95"},
        recommendation=None,
        analysis_readiness={"status": "PARTIAL", "blockers": ["AH_EV_BELOW_FORMAL_THRESHOLD"]},
        provider_status={"status": "AVAILABLE", "remaining_quota": 6000},
        as_of=NOW,
        kickoff_utc=KICKOFF,
        policy=POLICY,
    )

    assert result.data_status is not DataStatus.BLOCKED
    assert result.reason_code is not DecisionReasonCode.COVERAGE_NONE


def test_legacy_gate_uses_authoritative_quote_capture_for_staleness() -> None:
    captured = NOW - timedelta(minutes=31)
    result = build_data_readiness_from_legacy_payload(
        card={
            "fixture_id": "fixture-1",
            "generated_at": NOW.isoformat(),
            "data_readiness": {"market_observations": 2, "bookmakers": 1},
            "quote_identity_audit": {
                "ou": {
                    "schema_version": "w2.quote_identity.v1",
                    "identity_status": "COMPLETE",
                    "freshness_status": "STALE",
                    "captured_at": captured.isoformat(),
                }
            },
        },
        market={"market": "TOTALS"},
        recommendation=None,
        analysis_readiness={
            "status": "PARTIAL",
            "blockers": ["MARKET_UNAVAILABLE"],
            "available_inputs": {"market_observations": 2, "odds_snapshots": 1},
        },
        provider_status=None,
        as_of=NOW,
        kickoff_utc=KICKOFF,
        policy=POLICY,
    )

    assert result.data_status is DataStatus.STALE
    assert result.reason_code is DecisionReasonCode.DATA_STALE_ODDS
    odds = next(field for field in result.field_statuses if field.field == "odds")
    assert odds.captured_at == captured


def test_generated_at_does_not_fill_missing_authoritative_quote_time() -> None:
    result = build_data_readiness_from_legacy_payload(
        card={
            "fixture_id": "fixture-1",
            "generated_at": NOW.isoformat(),
            "data_readiness": {"market_observations": 2, "bookmakers": 1},
        },
        market={"market": "TOTALS"},
        recommendation=None,
        analysis_readiness={
            "status": "PARTIAL",
            "available_inputs": {"market_observations": 2, "odds_snapshots": 1},
        },
        provider_status=None,
        as_of=NOW,
        kickoff_utc=KICKOFF,
        policy=POLICY,
    )

    odds = next(field for field in result.field_statuses if field.field == "odds")
    assert odds.captured_at is None
