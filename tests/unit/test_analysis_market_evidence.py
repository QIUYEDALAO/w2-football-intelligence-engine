from __future__ import annotations

from w2.markets.analysis_evidence import build_analysis_market_evidence


def _quote_audit() -> dict[str, object]:
    return {
        "ah": {
            "identity_status": "COMPLETE",
            "freshness_status": "COMPLETE",
            "provider": "api-football",
            "bookmaker_id": "book-1",
            "captured_at": "2026-07-20T10:00:00Z",
            "observation_ids": {"home": "h1", "away": "a1"},
            "quotes": {
                "home": {"decimal_odds": "1.95"},
                "away": {"decimal_odds": "1.91"},
            },
        }
    }


def _ready_simulation() -> dict[str, object]:
    return {
        "status": "READY",
        "lambda_home": 1.7,
        "lambda_away": 1.0,
        "calibration_status": "OFFLINE_ONLY",
        "model_version": "unit-model",
        "calibration_version": "unit-calibration",
        "input_manifest": {"fixture": "fixture-1"},
        "lambda_sigma_home": 0.08,
        "lambda_sigma_away": 0.07,
        "calibration": {
            "lambda_uncertainty_method": "deterministic_three_point",
            "params": {"dixon_coles_rho": 0.0},
        },
    }


def test_no_selection_with_ready_sides_is_no_edge_not_not_ready() -> None:
    evidence = build_analysis_market_evidence(
        fixture_id="fixture-1",
        competition_id="allsvenskan",
        market="ASIAN_HANDICAP",
        selection=None,
        line="-0.25",
        quote_identity_audit=_quote_audit(),
        simulation=_ready_simulation(),
    )

    assert evidence["status"] == "NO_EDGE"
    assert evidence["quote_evidence_status"] == "READY"
    assert evidence["model_evidence_status"] == "READY"
    assert evidence["direction_status"] == "NO_DIRECTION_SELECTED"
    assert evidence["quote_usage"] == "COMPARISON_ONLY"
    assert evidence["ev_eligible"] is False
    assert evidence["formal_eligible"] is False
    assert evidence["lock_eligible"] is False
    assert evidence["comparison"]["reason_code"] == "NO_DIRECTION_SELECTED"


def test_no_selection_with_unready_model_is_not_ready() -> None:
    evidence = build_analysis_market_evidence(
        fixture_id="fixture-1",
        competition_id="allsvenskan",
        market="ASIAN_HANDICAP",
        selection=None,
        line="-0.25",
        quote_identity_audit=_quote_audit(),
        simulation={"status": "NOT_READY"},
    )

    assert evidence["status"] == "NOT_READY"
    assert evidence["quote_evidence_status"] == "READY"
    assert evidence["model_evidence_status"] == "NOT_READY"
    assert evidence["direction_status"] == "NOT_READY"
    assert evidence["comparison"]["reason_code"] == "NO_DIRECTION_SELECTED"


def test_selected_side_requires_ready_model_before_executable_quote_usage() -> None:
    unready = build_analysis_market_evidence(
        fixture_id="fixture-1",
        competition_id="allsvenskan",
        market="ASIAN_HANDICAP",
        selection="HOME",
        line="-0.25",
        quote_identity_audit=_quote_audit(),
        simulation={"status": "NOT_READY"},
    )
    ready = build_analysis_market_evidence(
        fixture_id="fixture-1",
        competition_id="allsvenskan",
        market="ASIAN_HANDICAP",
        selection="HOME",
        line="-0.25",
        quote_identity_audit=_quote_audit(),
        simulation=_ready_simulation(),
    )

    assert unready["status"] == "NOT_READY"
    assert unready["quote_usage"] == "NONE"
    assert unready["comparison"]["reason_code"] == "MODEL_EVIDENCE_NOT_READY"
    assert ready["status"] == "COMPLETE"
    assert ready["quote_usage"] == "EXECUTABLE"
    assert ready["quote_evidence_status"] == "READY"
    assert ready["model_evidence_status"] == "READY"
    assert ready["model_probability"]["ev_se"] is not None
    assert ready["model_probability"]["ev_se"] > 0


def test_selected_side_blocks_when_uncertainty_is_not_validated() -> None:
    simulation = _ready_simulation()
    simulation.pop("lambda_sigma_home")
    simulation.pop("lambda_sigma_away")
    simulation["calibration"] = {"lambda_uncertainty_method": "none"}

    evidence = build_analysis_market_evidence(
        fixture_id="fixture-1",
        competition_id="allsvenskan",
        market="ASIAN_HANDICAP",
        selection="HOME",
        line="-0.25",
        quote_identity_audit=_quote_audit(),
        simulation=simulation,
    )

    assert evidence["status"] == "NOT_READY"
    assert evidence["model_evidence_status"] == "NOT_READY"
    assert evidence["comparison"]["reason_code"] == "MODEL_UNCERTAINTY_NOT_READY"
    assert evidence["model_probability"]["reason_code"] == "MODEL_UNCERTAINTY_NOT_READY"
