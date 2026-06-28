from __future__ import annotations

from datetime import UTC, datetime

from tests.unit.test_handicap_walkforward_report import valid_row

from w2.backtest.handicap_walkforward import (
    EXCLUSION_DEMO_DATA,
    EXCLUSION_MISSING_DEVIG_ODDS,
    EXCLUSION_MISSING_MARKET_LINE,
    EXCLUSION_NON_AUTHORITATIVE,
    WalkForwardInputs,
    build_handicap_walkforward_report,
)

NOW = datetime(2026, 6, 28, tzinfo=UTC)


def build(mode: str, rows: list[dict[str, object]], source: str) -> dict[str, object]:
    return build_handicap_walkforward_report(
        WalkForwardInputs(mode=mode, rows=rows, data_source=source, generated_at=NOW)
    )


def test_demo_mode_authoritative_false_and_excluded() -> None:
    payload = build("demo", [valid_row(data_source="fixtures/stage5_demo")], "stage5_demo")

    assert payload["authoritative"] is False
    assert payload["authoritative_reason"] == "DEMO_DATA_NOT_AUTHORITATIVE"
    assert payload["sample"]["exclusion_reasons"][EXCLUSION_DEMO_DATA] == 1
    assert payload["s2_gate"]["beats_market"] is False


def test_real_mode_without_rows_is_non_authoritative() -> None:
    payload = build("real", [], "read-model-db")

    assert payload["authoritative"] is False
    assert payload["authoritative_reason"] == "NO_REAL_ASOF_ROWS_FOUND"
    assert payload["sample"]["total"] == 0


def test_non_authoritative_report_excludes_otherwise_valid_row() -> None:
    payload = build("dry-run", [valid_row()], "DRY_RUN_NO_ASOF_ARTIFACT")

    assert payload["sample"]["exclusion_reasons"][EXCLUSION_NON_AUTHORITATIVE] == 1
    assert payload["sample"]["included"] == 0


def test_missing_market_line_and_one_side_odds_are_separate_exclusions() -> None:
    payload = build(
        "real",
        [
            valid_row(fixture_id="line", market_ah=None),
            valid_row(fixture_id="odds", market_odds_away=None),
        ],
        "read-model-db",
    )

    assert payload["sample"]["exclusion_reasons"][EXCLUSION_MISSING_MARKET_LINE] == 1
    assert payload["sample"]["exclusion_reasons"][EXCLUSION_MISSING_DEVIG_ODDS] == 1
    assert payload["sample"]["included"] == 0
