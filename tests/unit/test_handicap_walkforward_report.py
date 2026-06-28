from __future__ import annotations

from datetime import UTC, datetime

from w2.backtest.handicap_walkforward import (
    EXCLUSION_MISSING_AS_OF,
    EXCLUSION_MISSING_FAIR_AH,
    EXCLUSION_MISSING_RESULT,
    EXCLUSION_POST_KICKOFF_ODDS,
    WalkForwardInputs,
    build_handicap_walkforward_report,
    dry_run_report,
)

NOW = datetime(2026, 6, 28, tzinfo=UTC)


def valid_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "fixture_id": "fixture-1",
        "kickoff_utc": "2026-06-27T20:00:00Z",
        "as_of": "2026-06-27T18:00:00Z",
        "home_team": "Home",
        "away_team": "Away",
        "model_version": "s1-shadow",
        "fair_ah": -0.75,
        "market_ah": -0.25,
        "edge_ah": 0.5,
        "market_odds_home": 1.91,
        "market_odds_away": 1.97,
        "locked_market_snapshot_id": "snap-1",
        "final_score": "1-0",
        "result_status": "FINAL",
        "data_source": "read-model-db",
    }
    row.update(overrides)
    return row


def report(rows: list[dict[str, object]]) -> dict[str, object]:
    return build_handicap_walkforward_report(
        WalkForwardInputs(
            mode="real",
            rows=rows,
            data_source="read-model-db",
            generated_at=NOW,
        )
    )


def test_dry_run_report_is_non_authoritative_and_locked_down() -> None:
    payload = dry_run_report()

    assert payload["schema_version"] == "w2.handicap_walkforward_report.v1"
    assert payload["authoritative"] is False
    assert payload["s2_gate"]["beats_market"] is False
    assert payload["s2_gate"]["formal_enabled"] is False
    assert payload["s2_gate"]["candidate_enabled"] is False
    assert payload["calibration"]["calibration_version"] == "UNVALIDATED"


def test_real_report_includes_strict_valid_sample() -> None:
    payload = report([valid_row()])

    assert payload["authoritative"] is True
    assert payload["sample"]["included"] == 1
    assert payload["sample"]["excluded"] == 0
    row = payload["rows"][0]
    assert row["settlement_outcome"] == "WIN"
    assert row["sample_included"] is True
    assert row["devig_method"] == "PROPORTIONAL"
    assert payload["metrics"]["win_rate"] == 1.0
    assert payload["calibration"]["calibration_version"] == "UNVALIDATED"


def test_missing_asof_post_kickoff_missing_fair_and_missing_result_are_excluded() -> None:
    payload = report(
        [
            valid_row(fixture_id="a", as_of=None),
            valid_row(fixture_id="b", as_of="2026-06-27T21:00:00Z"),
            valid_row(fixture_id="c", fair_ah=None),
            valid_row(fixture_id="d", final_score=None),
        ]
    )

    reasons = payload["sample"]["exclusion_reasons"]
    assert reasons[EXCLUSION_MISSING_AS_OF] == 1
    assert reasons[EXCLUSION_POST_KICKOFF_ODDS] == 1
    assert reasons[EXCLUSION_MISSING_FAIR_AH] == 1
    assert reasons[EXCLUSION_MISSING_RESULT] == 1
    assert payload["sample"]["included"] == 0


def test_no_samples_never_fabricates_hit_rate_or_calibration() -> None:
    payload = report([])

    assert payload["authoritative"] is False
    assert payload["metrics"]["win_rate"] is None
    assert payload["metrics"]["avg_edge"] is None
    assert payload["calibration"]["status"] == "INSUFFICIENT_SAMPLE"
    assert payload["s2_gate"]["beats_market"] is False
