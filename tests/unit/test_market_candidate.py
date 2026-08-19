from __future__ import annotations

from w2.markets import analysis_evidence
from w2.markets.analysis_evidence import build_analysis_market_evidence
from w2.markets.market_candidate import (
    _best_evaluated_side,
    _market_mainline_contract,
    build_market_candidates,
    candidate_is_executable,
    select_authoritative_market_candidate,
)
from w2.strategy.formal_recommendation import _candidate_executable_odds


def _audit(*, identity: str = "COMPLETE", freshness: str = "COMPLETE") -> dict[str, object]:
    return {
        "schema_version": "w2.quote_identity.v1",
        "market": "ASIAN_HANDICAP",
        "selected_line": "-0.5",
        "fixture_id": "fixture-1",
        "identity_status": identity,
        "freshness_status": freshness,
        "observation_ids": {"home": "h", "away": "a"},
        "provider": "provider",
        "bookmaker_id": "book",
        "capture_id": "capture-1",
        "captured_at": "2026-07-19T00:00:00Z",
        "source_revision": "a" * 40,
        "raw_payload_sha256": "b" * 64,
        "quote_identity_hash": "c" * 64,
        "quotes": {
            "home": {"capture_id": "capture-1", "line": "-0.5", "decimal_odds": "1.9"},
            "away": {"capture_id": "capture-1", "line": "0.5", "decimal_odds": "1.9"},
            "over": {"capture_id": "capture-1", "line": "-0.5", "decimal_odds": "1.9"},
            "under": {"capture_id": "capture-1", "line": "-0.5", "decimal_odds": "1.9"},
        },
    }


def _market(name: str) -> dict[str, object]:
    tendency = "OVER" if name == "TOTALS" else "HOME"
    return {"market": name, "decision": "PICK", "tendency": tendency, "line": "-0.5"}


def _ready_simulation() -> dict[str, object]:
    return {
        "status": "READY",
        "model_version": "model",
        "calibration_version": "calibration",
        "lambda_home": 1.4,
        "lambda_away": 0.9,
        "lambda_sigma_home": 0.08,
        "lambda_sigma_away": 0.07,
        "calibration": {
            "lambda_uncertainty_method": "deterministic_three_point",
            "params": {"dixon_coles_rho": 0.0},
        },
    }


def _evaluated_candidate(
    *, market: str, selection: str, expected_value: float, uncertainty: float, edge: float
) -> dict[str, object]:
    return {
        "market": market,
        "selection": selection,
        "line": "2.5" if market == "TOTALS" else "-0.5",
        "candidate_role": "MARKET_MAINLINE",
        "quote_status": "COMPLETE",
        "quote_usage": "EXECUTABLE",
        "quotes": {"executable": {"decimal_odds": "1.9"}},
        "analysis_evidence": {
            "status": "COMPLETE",
            "model_probability": {
                "status": "READY",
                "expected_value": expected_value,
                "ev_se": uncertainty,
            },
            "comparison": {"cashflow_price_edge": edge},
        },
    }


def test_admission_eligible_ou_beats_higher_robust_but_ineligible_ah() -> None:
    ah = _evaluated_candidate(
        market="ASIAN_HANDICAP",
        selection="HOME",
        expected_value=0.20,
        uncertainty=0.01,
        edge=0.04,
    )
    totals = _evaluated_candidate(
        market="TOTALS",
        selection="OVER",
        expected_value=0.10,
        uncertainty=0.02,
        edge=0.06,
    )

    assert select_authoritative_market_candidate({"ah": ah, "ou": totals}) == totals


def test_production_shaped_ah_side_admission_prefers_eligible_side(
    monkeypatch,
) -> None:
    def side_evidence(*, selection: str, line, **_kwargs):
        eligible = selection == "AWAY"
        return {
            "line": str(line),
            "model_probability": {
                "status": "READY",
                "expected_value": 0.10 if eligible else 0.20,
                "ev_se": 0.02 if eligible else 0.01,
                "effective_probability": 0.60 if eligible else 0.65,
                "settlement_distribution": {
                    "WIN": 0.5,
                    "HALF_WIN": 0.0,
                    "PUSH": 0.0,
                    "HALF_LOSS": 0.2,
                    "LOSS": 0.3,
                },
                "fair_decimal_odds": 1.8,
            },
            "comparison": {
                "analysis_direction_allowed": eligible,
                "status": "READY" if eligible else "NO_EDGE",
                "cashflow_price_edge": 0.06 if eligible else 0.04,
            },
        }

    monkeypatch.setattr(analysis_evidence, "_side_evidence", side_evidence)
    evidence = build_analysis_market_evidence(
        fixture_id="fixture-1",
        competition_id="allsvenskan",
        market="ASIAN_HANDICAP",
        selection=None,
        line="-0.5",
        quote_identity_audit={"ah": _audit()},
        simulation=_ready_simulation(),
    )
    assert evidence["status"] == "NO_EDGE"
    assert _best_evaluated_side(
        evidence,
        market="ASIAN_HANDICAP",
        odds={"home_line": "-0.5", "away_line": "0.5"},
        quote_complete=True,
    ) == "AWAY"

    candidate = build_market_candidates(
        markets=[_market("ASIAN_HANDICAP")],
        quote_identity_audit={"ah": _audit()},
        current_odds={"ah": {"home_line": "-0.5", "away_line": "0.5"}},
        pricing_shadow={},
        simulation=_ready_simulation(),
        fixture_id="fixture-1",
        competition_id="allsvenskan",
    )["ah"]

    assert candidate["selection"] == "AWAY"
    assert candidate["analysis_direction_allowed"] is True


def test_fresh_ah_and_stale_ou_are_independent_candidates() -> None:
    candidates = build_market_candidates(
        markets=[_market("ASIAN_HANDICAP"), _market("TOTALS")],
        quote_identity_audit={"ah": _audit(), "ou": _audit(freshness="STALE")},
        current_odds={"ah": {"home_price": 1.9}, "ou": {"over_price": 1.9}},
        pricing_shadow={},
    )

    assert candidates["ah"]["quote_status"] == "COMPLETE"
    assert not candidate_is_executable(candidates["ah"])
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
    assert candidates["ou"]["quote_status"] == "COMPLETE"
    assert not candidate_is_executable(candidates["ou"])


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
        current_odds={"ah": {"home_line": "-0.5", "away_line": "0.5"}},
        pricing_shadow={},
        fixture_id="fixture-1",
        competition_id="allsvenskan",
        simulation=_ready_simulation(),
    )
    candidate = candidates["ah"]
    selected = str(candidate["selection"]).lower()
    expected_quote = _audit()["quotes"][selected]  # type: ignore[index]
    assert _candidate_executable_odds(candidate) == {
        "line": expected_quote["line"],  # type: ignore[index]
        "decimal_odds": "1.9",
        "provider": None,
        "bookmaker_id": None,
        "bookmaker_name": None,
        "capture_id": "capture-1",
        "captured_at": None,
        "observation_id": None,
    }

    candidate["quote_status"] = "STALE"
    assert _candidate_executable_odds(candidate) is None


def test_same_line_evidence_uses_only_authoritative_quote_pair() -> None:
    candidates = build_market_candidates(
        markets=[_market("ASIAN_HANDICAP")],
        quote_identity_audit={"ah": _audit()},
        current_odds={},
        pricing_shadow={},
        fixture_id="fixture-1",
        competition_id="allsvenskan",
        simulation=_ready_simulation(),
    )

    evidence = candidates["ah"]["analysis_evidence"]
    assert candidates["ah"]["formal_capability"] == "CODE_PRESENT_BUT_DISABLED"
    assert candidates["ou"]["formal_capability"] == "NOT_IMPLEMENTED"
    assert evidence["status"] == "COMPLETE"
    assert evidence["evidence_contract_version"] == "w2.analysis-market-evidence.v2"
    assert evidence["quote_identity"]["bookmaker_id"] == "book"
    assert evidence["quote_identity"]["capture_id"] == "capture-1"
    assert evidence["quote_identity"]["source_revision"] == "a" * 40
    assert evidence["quote_identity"]["raw_payload_sha256"] == "b" * 64
    assert evidence["quote_identity"]["quote_identity_hash"] == "c" * 64
    assert evidence["quote_observation_ids"] == {"home": "h", "away": "a"}
    assert evidence["market_probability"]["overround"] == 0.052632
    assert evidence["model_probability"]["settlement_distribution"]
    assert evidence["model_probability"]["calibration_status"] == "UNKNOWN"
    assert evidence["evidence_hash"]


def test_model_selects_direction_without_bookmaker_intent() -> None:
    candidates = build_market_candidates(
        markets=[{"market": "ASIAN_HANDICAP", "line": "-0.5"}],
        quote_identity_audit={"ah": _audit()},
        current_odds={"ah": {"home_line": "-0.5", "away_line": "0.5"}},
        pricing_shadow={},
        fixture_id="fixture-1",
        competition_id="allsvenskan",
        simulation=_ready_simulation(),
    )

    candidate = candidates["ah"]
    assert candidate["selection"] in {"HOME", "AWAY"}
    assert candidate["bookmaker_intent_selection"] is None
    assert candidate["quote_status"] == "COMPLETE"
    assert candidate["quote_usage"] == "EXECUTABLE"
    assert candidate["analysis_evidence_status"] == "COMPLETE"
    assert set(candidate["side_evidence"]) == {"HOME", "AWAY"}
    assert all(
        row["model_probability"]["status"] == "READY"
        for row in candidate["side_evidence"].values()
    )
    assert candidate_is_executable(candidate) is True
    assert select_authoritative_market_candidate(candidates) == candidate


def test_bookmaker_intent_cannot_change_authoritative_direction() -> None:
    inputs = {
        "quote_identity_audit": {"ah": _audit()},
        "current_odds": {"ah": {"home_line": "-0.5", "away_line": "0.5"}},
        "pricing_shadow": {},
        "fixture_id": "fixture-1",
        "competition_id": "allsvenskan",
        "simulation": _ready_simulation(),
    }
    home_intent = build_market_candidates(
        markets=[{"market": "ASIAN_HANDICAP", "tendency": "HOME", "line": "-0.5"}],
        **inputs,
    )["ah"]
    away_intent = build_market_candidates(
        markets=[{"market": "ASIAN_HANDICAP", "tendency": "AWAY", "line": "-0.5"}],
        **inputs,
    )["ah"]

    assert home_intent["bookmaker_intent_selection"] == "HOME"
    assert away_intent["bookmaker_intent_selection"] == "AWAY"
    assert home_intent["selection"] == away_intent["selection"]
    assert home_intent["analysis_evidence"] == away_intent["analysis_evidence"]


def test_no_pick_with_current_odds_is_comparison_only() -> None:
    candidates = build_market_candidates(
        markets=[{"market": "ASIAN_HANDICAP", "line": "-0.5"}],
        quote_identity_audit={"ah": _audit()},
        current_odds={"ah": {"home_price": 1.9, "away_price": 1.9}},
        pricing_shadow={},
    )

    candidate = candidates["ah"]
    assert candidate["selection"] is None
    assert candidate["quote_usage"] == "COMPARISON_ONLY"
    assert candidate["quotes"]["executable"] is None
    assert candidate["ev_eligible"] is False
    assert candidate["formal_eligible"] is False
    assert candidate["lock_eligible"] is False
    assert candidate_is_executable(candidate) is False


def test_best_side_evidence_uses_away_quote_line_for_away_candidate() -> None:
    simulation = {
        "status": "READY",
        "model_version": "model",
        "calibration_version": "calibration",
        "lambda_home": 1.0,
        "lambda_away": 1.9,
        "lambda_sigma_home": 0.08,
        "lambda_sigma_away": 0.07,
        "calibration": {
            "lambda_uncertainty_method": "deterministic_three_point",
            "params": {"dixon_coles_rho": 0.0},
        },
    }
    candidates = build_market_candidates(
        markets=[{"market": "ASIAN_HANDICAP", "line": "-0.5"}],
        quote_identity_audit={"ah": _audit()},
        current_odds={"ah": {"home_price": 1.9, "away_price": 1.9}},
        pricing_shadow={},
        fixture_id="fixture-1",
        competition_id="allsvenskan",
        simulation=simulation,
    )

    candidate = candidates["ah"]
    assert candidate["selection"] == "AWAY"
    assert candidate["line"] == "0.5"
    assert candidate["analysis_evidence"]["canonical_home_line"] == "-0.5"
    assert candidate["analysis_evidence"]["selected_side_line"] == "0.5"
    assert candidate["side_evidence"]["HOME"]["line"] == "-0.5"
    assert candidate["side_evidence"]["AWAY"]["line"] == "0.5"
    assert candidate["analysis_evidence_status"] == "COMPLETE"
    assert candidate["analysis_direction_allowed"] is True
    assert candidate["analysis_evidence"]["comparison"]["reason_code"] == "MODEL_MARKET_EDGE_READY"
    assert candidate["quotes"]["executable"]["line"] == "0.5"
    assert candidate["quotes"]["executable"]["decimal_odds"] == "1.9"
    assert candidate["quote_identity"]["capture_id"] == "capture-1"
    assert candidate["quote_identity"]["source_revision"] == "a" * 40
    assert candidate["quote_identity"]["raw_payload_sha256"] == "b" * 64
    assert candidate["quote_identity"]["quote_identity_hash"] == "c" * 64
    assert candidate["ev_eligible"] is True
    assert candidate_is_executable(candidate)


def test_ah_candidate_role_uses_signed_line_for_each_side() -> None:
    cases = (
        ("HOME", "+0.75", "+0.75", "-0.75"),
        ("AWAY", "-0.75", "+0.75", "-0.75"),
        ("HOME", "-1.25", "-1.25", "+1.25"),
        ("AWAY", "+1.25", "-1.25", "+1.25"),
    )
    for selection, selected_line, home_line, away_line in cases:
        audit = _audit()
        audit["selected_line"] = home_line
        quotes = audit["quotes"]
        assert isinstance(quotes, dict)
        assert isinstance(quotes["home"], dict)
        assert isinstance(quotes["away"], dict)
        quotes["home"]["line"] = home_line
        quotes["away"]["line"] = away_line
        candidate = build_market_candidates(
            markets=[{"market": "ASIAN_HANDICAP", "tendency": selection, "line": selected_line}],
            quote_identity_audit={"ah": audit},
            current_odds={
                "ah": {
                    "line": home_line.lstrip("+-"),
                    "home_line": home_line,
                    "away_line": away_line,
                }
            },
            pricing_shadow={},
            fixture_id="fixture-1",
            competition_id="allsvenskan",
            simulation=_ready_simulation(),
        )["ah"]
        assert candidate["candidate_role"] == "MARKET_MAINLINE"


def test_ah_candidate_role_marks_different_signed_line_as_alternate() -> None:
    audit = _audit()
    candidate = build_market_candidates(
        markets=[{"market": "ASIAN_HANDICAP", "tendency": "AWAY", "line": "+0.5"}],
        quote_identity_audit={"ah": audit},
        current_odds={"ah": {"line": "0.5", "home_line": "-0.5", "away_line": "+0.75"}},
        pricing_shadow={},
        fixture_id="fixture-1",
        competition_id="allsvenskan",
        simulation=_ready_simulation(),
    )["ah"]
    assert candidate["candidate_role"] == "ALTERNATE_LINE"


def test_ah_side_line_sign_conflict_fails_closed() -> None:
    audit = _audit()
    audit["selected_line"] = "0.5"
    candidates = build_market_candidates(
        markets=[{"market": "ASIAN_HANDICAP", "tendency": "AWAY", "line": "0.5"}],
        quote_identity_audit={"ah": audit},
        current_odds={"ah": {"home_price": 1.9, "away_price": 1.9}},
        pricing_shadow={},
        fixture_id="fixture-1",
        competition_id="allsvenskan",
        simulation=_ready_simulation(),
    )

    candidate = candidates["ah"]
    assert candidate["analysis_evidence_status"] == "AH_SIDE_LINE_IDENTITY_CONFLICT"
    assert candidate["quote_usage"] == "COMPARISON_ONLY"
    assert candidate["ev_eligible"] is False
    assert candidate_is_executable(candidate) is False
    assert "AH_SIDE_LINE_IDENTITY_CONFLICT" in candidate["blockers"]


def test_full_ladder_is_evaluated_but_alternates_remain_comparison_only() -> None:
    mainline_audit = _audit()
    mainline_audit["market"] = "TOTALS"
    mainline_audit["selected_line"] = "2.75"
    quotes = mainline_audit["quotes"]
    assert isinstance(quotes, dict)
    for side in ("over", "under"):
        assert isinstance(quotes[side], dict)
        quotes[side]["line"] = "2.75"
    alternate_audit = {
        **mainline_audit,
        "selected_line": "2.5",
        "quote_identity_hash": "d" * 64,
        "quotes": {
            side: {**quotes[side], "line": "2.5"} for side in ("over", "under")
        },
    }
    candidate = build_market_candidates(
        markets=[{"market": "TOTALS", "tendency": "OVER", "line": "2.75"}],
        quote_identity_audit={"ou": mainline_audit},
        current_odds={
            "ou": {
                "line": "2.75",
                "selection_policy": "canonical_bookmaker_mainline_consensus_v1",
                "candidate_ladder_hash": "e" * 64,
                "candidate_lines": [
                    {
                        "line": 2.75,
                        "status": "SELECTED_MARKET_MAINLINE",
                        "complete_pair_bookmaker_count": 6,
                        "bookmaker_vote_count": 6,
                        "median_over_price": 1.91,
                        "median_under_price": 1.91,
                    },
                    {"line": 2.5, "status": "REJECTED", "reason": "LOWER_BOOKMAKER_CONSENSUS"},
                ],
                "ladder_quote_identity_audits": {
                    "2.75": mainline_audit,
                    "2.5": alternate_audit,
                },
            }
        },
        pricing_shadow={},
        fixture_id="fixture-1",
        competition_id="allsvenskan",
        simulation=_ready_simulation(),
    )["ou"]

    ladder = candidate["market_ladder_evaluation"]
    assert ladder["evaluated_candidate_count"] == 4
    assert len(ladder["mainline_candidates"]) == 2
    assert len(ladder["alternate_candidates"]) == 2
    assert all(row["admission"] == "COMPARISON_ONLY" for row in ladder["alternate_candidates"])
    assert candidate["candidate_role"] == "MARKET_MAINLINE"
    assert candidate["market_mainline"]["line"] == "2.75"
    assert candidate["market_mainline"]["bookmaker_vote_count"] == 6


def test_market_mainline_keeps_top_level_bookmaker_depth() -> None:
    mainline = _market_mainline_contract({"line": "1.25", "bookmaker_count": 6})

    assert mainline["bookmaker_count"] == 6


def test_away_minus_point_seven_five_keeps_negative_selected_line() -> None:
    audit = _audit()
    audit["selected_line"] = "0.75"
    quotes = audit["quotes"]
    assert isinstance(quotes, dict)
    assert isinstance(quotes["home"], dict)
    assert isinstance(quotes["away"], dict)
    quotes["home"]["line"] = "0.75"
    quotes["away"]["line"] = "-0.75"
    candidate = build_market_candidates(
        markets=[{"market": "ASIAN_HANDICAP", "tendency": "HOME", "line": "0.75"}],
        quote_identity_audit={"ah": audit},
        current_odds={"ah": {"home_price": 1.88, "away_price": 1.90}},
        pricing_shadow={},
        fixture_id="fixture-1",
        competition_id="allsvenskan",
        simulation={**_ready_simulation(), "lambda_home": 1.0, "lambda_away": 1.9},
    )["ah"]

    assert candidate["selection"] == "AWAY"
    assert candidate["bookmaker_intent_selection"] == "HOME"
    assert candidate["line"] == "-0.75"
    assert candidate["quotes"]["executable"]["line"] == "-0.75"
    assert candidate["analysis_evidence"]["selected_side_line"] == "-0.75"


def test_home_minus_one_point_two_five_keeps_negative_selected_line() -> None:
    audit = _audit()
    audit["selected_line"] = "-1.25"
    quotes = audit["quotes"]
    assert isinstance(quotes, dict)
    assert isinstance(quotes["home"], dict)
    assert isinstance(quotes["away"], dict)
    quotes["home"]["line"] = "-1.25"
    quotes["away"]["line"] = "1.25"
    candidate = build_market_candidates(
        markets=[{"market": "ASIAN_HANDICAP", "tendency": "AWAY", "line": "-1.25"}],
        quote_identity_audit={"ah": audit},
        current_odds={"ah": {"home_price": 1.90, "away_price": 1.90}},
        pricing_shadow={},
        fixture_id="fixture-1",
        competition_id="allsvenskan",
        simulation={**_ready_simulation(), "lambda_home": 2.5, "lambda_away": 0.5},
    )["ah"]

    assert candidate["selection"] == "HOME"
    assert candidate["bookmaker_intent_selection"] == "AWAY"
    assert candidate["line"] == "-1.25"
    assert candidate["quotes"]["executable"]["line"] == "-1.25"
    assert candidate["side_evidence"]["AWAY"]["line"] == "1.25"
