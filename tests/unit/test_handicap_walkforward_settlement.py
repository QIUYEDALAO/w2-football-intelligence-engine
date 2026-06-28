from __future__ import annotations

from datetime import UTC, datetime

from tests.unit.test_handicap_walkforward_report import valid_row

from w2.backtest.handicap_walkforward import (
    EXCLUSION_VOID_SETTLEMENT,
    WalkForwardInputs,
    build_handicap_walkforward_report,
)

NOW = datetime(2026, 6, 28, tzinfo=UTC)


def outcomes(*rows: dict[str, object]) -> list[dict[str, object]]:
    payload = build_handicap_walkforward_report(
        WalkForwardInputs(
            mode="real",
            rows=list(rows),
            data_source="read-model-db",
            generated_at=NOW,
        )
    )
    return list(payload["rows"])


def test_ah_quarter_line_outcomes_and_sample_semantics() -> None:
    rows = outcomes(
        valid_row(fixture_id="home025", fair_ah=-0.5, market_ah=-0.25, final_score="1-0"),
        valid_row(fixture_id="home075", fair_ah=-1.0, market_ah=-0.75, final_score="1-0"),
        valid_row(fixture_id="away025", fair_ah=0.5, market_ah=0.25, final_score="0-0"),
        valid_row(fixture_id="away075", fair_ah=1.0, market_ah=0.75, final_score="1-0"),
        valid_row(fixture_id="push", fair_ah=-1.25, market_ah=-1.0, final_score="1-0"),
        valid_row(fixture_id="loss", fair_ah=-0.75, market_ah=-0.5, final_score="0-1"),
    )
    by_id = {str(row["fixture_id"]): row for row in rows}

    assert by_id["home025"]["settlement_outcome"] == "WIN"
    assert by_id["home075"]["settlement_outcome"] == "HALF_WIN"
    assert by_id["away025"]["settlement_outcome"] == "HALF_WIN"
    assert by_id["away075"]["settlement_outcome"] == "HALF_LOSS"
    assert by_id["push"]["settlement_outcome"] == "PUSH"
    assert by_id["push"]["win_included"] is False
    assert by_id["loss"]["settlement_outcome"] == "LOSS"
    assert by_id["loss"]["win_included"] is False


def test_void_settlement_is_excluded_from_sample() -> None:
    payload = build_handicap_walkforward_report(
        WalkForwardInputs(
            mode="real",
            rows=[valid_row(result_status="CANCELLED")],
            data_source="read-model-db",
            generated_at=NOW,
        )
    )

    assert payload["sample"]["included"] == 0
    assert payload["sample"]["exclusion_reasons"][EXCLUSION_VOID_SETTLEMENT] == 1
    assert payload["rows"][0]["settlement_outcome"] == "VOID"
