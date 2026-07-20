from __future__ import annotations

from w2.markets.market_candidate import build_market_candidates, candidate_is_executable
from w2.strategy.formal_recommendation import _candidate_executable_odds


def _audit(*, identity: str = "COMPLETE", freshness: str = "COMPLETE") -> dict[str, object]:
    return {
        "identity_status": identity,
        "freshness_status": freshness,
        "observation_ids": {"home": "h", "away": "a"},
        "provider": "provider",
        "bookmaker_id": "book",
        "captured_at": "2026-07-19T00:00:00Z",
        "quotes": {"home": {"decimal_odds": "1.9"}, "away": {"decimal_odds": "1.9"}},
    }


def _market(name: str) -> dict[str, object]:
    return {"market": name, "decision": "PICK", "tendency": "HOME", "line": "-0.5"}


def test_fresh_ah_and_stale_ou_are_independent_candidates() -> None:
    candidates = build_market_candidates(
        markets=[_market("ASIAN_HANDICAP"), _market("TOTALS")],
        quote_identity_audit={"ah": _audit(), "ou": _audit(freshness="STALE")},
        current_odds={"ah": {"home_price": 1.9}, "ou": {"over_price": 1.9}},
        pricing_shadow={},
    )

    assert candidate_is_executable(candidates["ah"])
    assert not candidate_is_executable(candidates["ou"])
    assert candidates["ou"]["quote_status"] == "STALE"
    assert candidates["ou"]["quotes"]["executable"] is None


def test_fresh_ou_is_not_blocked_by_stale_ah() -> None:
    candidates = build_market_candidates(
        markets=[_market("ASIAN_HANDICAP"), _market("TOTALS")],
        quote_identity_audit={"ah": _audit(freshness="STALE"), "ou": _audit()},
        current_odds={"ah": {"home_price": 1.9}, "ou": {"over_price": 1.9}},
        pricing_shadow={},
    )

    assert not candidate_is_executable(candidates["ah"])
    assert candidate_is_executable(candidates["ou"])


def test_conflict_is_reference_only_and_never_ev_eligible() -> None:
    candidates = build_market_candidates(
        markets=[_market("ASIAN_HANDICAP")],
        quote_identity_audit={"ah": _audit(identity="CONFLICT")},
        current_odds={"ah": {"home_price": 1.9}},
        pricing_shadow={},
    )

    candidate = candidates["ah"]
    assert candidate["quote_status"] == "CONFLICT"
    assert candidate["quote_usage"] == "REFERENCE_ONLY"
    assert candidate["ev_eligible"] is False
    assert candidate["quotes"]["last_known_reference"] is not None


def test_generated_at_or_legacy_ready_cannot_synthesize_candidate_identity() -> None:
    candidates = build_market_candidates(
        markets=[_market("TOTALS")],
        quote_identity_audit={"ou": {"readiness_status": "READY", "generated_at": "now"}},
        current_odds={"ou": {"over_price": 1.9}},
        pricing_shadow={},
    )

    candidate = candidates["ou"]
    assert candidate["quote_status"] == "INCOMPLETE"
    assert candidate["quotes"]["executable"] is None
    assert candidate["ev_eligible"] is False


def test_formal_ah_can_only_consume_executable_candidate_quote() -> None:
    candidates = build_market_candidates(
        markets=[_market("ASIAN_HANDICAP")],
        quote_identity_audit={"ah": _audit()},
        current_odds={"ah": {"home_price": 1.9}},
        pricing_shadow={},
    )
    assert _candidate_executable_odds(candidates["ah"]) == {"home_price": 1.9}

    candidates["ah"]["quote_status"] = "STALE"
    assert _candidate_executable_odds(candidates["ah"]) is None


def test_same_line_evidence_uses_only_authoritative_quote_pair() -> None:
    candidates = build_market_candidates(
        markets=[_market("ASIAN_HANDICAP")],
        quote_identity_audit={"ah": _audit()},
        current_odds={},
        pricing_shadow={},
        fixture_id="fixture-1",
        competition_id="allsvenskan",
        simulation={
            "status": "READY",
            "model_version": "model",
            "calibration_version": "calibration",
            "lambda_home": 1.4,
            "lambda_away": 0.9,
            "calibration": {"params": {"dixon_coles_rho": 0.0}},
        },
    )

    evidence = candidates["ah"]["analysis_evidence"]
    assert candidates["ah"]["formal_capability"] == "CODE_PRESENT_BUT_DISABLED"
    assert candidates["ou"]["formal_capability"] == "NOT_IMPLEMENTED"
    assert evidence["status"] == "COMPLETE"
    assert evidence["evidence_contract_version"] == "w2.analysis-market-evidence.v2"
    assert evidence["quote_identity"]["bookmaker_id"] == "book"
    assert evidence["quote_observation_ids"] == {"home": "h", "away": "a"}
    assert evidence["market_probability"]["overround"] == 0.052632
    assert evidence["model_probability"]["settlement_distribution"]
    assert evidence["model_probability"]["calibration_status"] == "UNKNOWN"
    assert evidence["evidence_hash"]


def test_no_pick_retains_complete_quote_and_side_evidence() -> None:
    candidates = build_market_candidates(
        markets=[{"market": "ASIAN_HANDICAP", "line": "-0.5"}],
        quote_identity_audit={"ah": _audit()},
        current_odds={},
        pricing_shadow={},
        fixture_id="fixture-1",
        competition_id="allsvenskan",
        simulation={
            "status": "READY",
            "model_version": "model",
            "calibration_version": "calibration",
            "lambda_home": 1.4,
            "lambda_away": 0.9,
            "calibration": {"params": {"dixon_coles_rho": 0.0}},
        },
    )

    candidate = candidates["ah"]
    assert candidate["selection"] is None
    assert candidate["quote_status"] == "COMPLETE"
    assert candidate["quote_usage"] == "COMPARISON_ONLY"
    assert candidate["analysis_evidence_status"] == "NO_EDGE"
    assert candidate["analysis_evidence"]["comparison"]["status"] == "NO_EDGE"
    assert set(candidate["side_evidence"]) == {"HOME", "AWAY"}
    assert all(
        row["model_probability"]["status"] == "READY"
        for row in candidate["side_evidence"].values()
    )
    assert candidate_is_executable(candidate) is False
