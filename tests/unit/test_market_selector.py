from __future__ import annotations

from w2.strategy.market_selector import (
    apply_market_selection,
    enrich_secondary_evidence,
    select_analysis_markets,
)


def market(name: str, score: float, **extra: object) -> dict[str, object]:
    return {
        "market": name,
        "decision": "PICK",
        "line_status": "READY",
        "signal_strength": score,
        "bookmaker_count": 4,
        **extra,
    }


def test_ou_can_be_primary_even_when_ah_appears_first() -> None:
    result = select_analysis_markets([market("ASIAN_HANDICAP", 0.60), market("TOTALS", 0.78)])
    assert result.primary_market == "TOTALS"


def test_tie_breaks_by_calibration_then_quote_age_then_bookmakers() -> None:
    result = select_analysis_markets(
        [
            market("ASIAN_HANDICAP", 0.7, calibration_error=0.08, quote_age_seconds=5),
            market("TOTALS", 0.7, calibration_error=0.05, quote_age_seconds=20),
        ]
    )
    assert result.primary_market == "TOTALS"


def test_secondary_fails_closed_without_correlation_and_scoreline_support() -> None:
    result = select_analysis_markets([market("ASIAN_HANDICAP", 0.80), market("TOTALS", 0.75)])
    assert result.secondary_markets == ()


def test_secondary_requires_strict_score_correlation_contract() -> None:
    result = select_analysis_markets(
        [
            market("ASIAN_HANDICAP", 0.80),
            market(
                "TOTALS",
                0.75,
                settlement_correlation=0.20,
                scoreline_support_intersection=["2-1"],
            ),
        ]
    )
    assert result.secondary_markets == ("TOTALS",)


def test_apply_selection_exposes_backward_compatible_primary_and_audit() -> None:
    payload: dict[str, object] = {
        "markets": [market("ASIAN_HANDICAP", 0.56), market("TOTALS", 0.72)]
    }
    apply_market_selection(payload)
    assert payload["primary_market"] == "TOTALS"
    assert payload["secondary_picks"] == []
    assert len(payload["market_selection_audit"]) == 2  # type: ignore[arg-type]


def test_secondary_evidence_is_derived_from_the_same_score_matrix() -> None:
    payload: dict[str, object] = {
        "markets": [
            market("ASIAN_HANDICAP", 0.8, tendency="HOME", line=-0.5),
            market("TOTALS", 0.7, tendency="OVER", line=2.5),
        ],
        "simulation": {"lambda_home": 1.8, "lambda_away": 1.0},
    }
    enrich_secondary_evidence(payload)
    rows = payload["markets"]
    assert isinstance(rows, list)
    assert isinstance(rows[0].get("settlement_correlation"), float)
    assert rows[0].get("scoreline_support_intersection")
