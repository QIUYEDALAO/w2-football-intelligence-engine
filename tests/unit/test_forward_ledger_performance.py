from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from w2.tracking.forward_ledger_performance import forward_ledger_performance


def test_forward_ledger_performance_accumulates_without_fake_hit_rate(tmp_path: Path) -> None:
    root = tmp_path / "forward_outcome_ledger"
    root.mkdir()
    _write_jsonl(
        root / "2026-07-07_staging.jsonl",
        [
            _record("2026-07-07T00:00:00Z", fixture_id="fixture-1"),
            _record("2026-07-07T01:00:00Z", fixture_id="fixture-2"),
        ],
    )

    payload = forward_ledger_performance(tmp_path)

    assert payload["provider_calls"] == 0
    assert payload["db_reads"] == 0
    assert payload["db_writes"] == 0
    assert payload["record_count"] == 2
    assert payload["fixture_count"] == 2
    assert payload["settled_sample_count"] == 0
    assert payload["hit_rate"] is None
    assert payload["accumulation_label"] == "积累中 2/200"
    assert payload["mock_data"] is False
    for key in (
        "entry_window_met_count",
        "median_decimal_window_met",
        "excluded_no_prematch_closing",
        "entry_line_mismatch_count",
    ):
        assert key in payload["clv"]
        assert key in payload["clv_shadow"]


def test_forward_ledger_performance_counts_only_real_outcomes(tmp_path: Path) -> None:
    root = tmp_path / "forward_outcome_ledger"
    root.mkdir()
    _write_jsonl(
        root / "2026-07-07_staging.jsonl",
        [
            _outcome_record("fixture-1", "WIN", side="pick"),
            _outcome_record("fixture-2", "LOSS", side="pick"),
            _outcome_record("fixture-3", "PUSH", side="pick"),
            _record("2026-07-07T03:00:00Z", fixture_id="fixture-4"),
        ],
    )

    payload = forward_ledger_performance(tmp_path)

    assert payload["settled_sample_count"] == 3
    assert payload["hit_count"] == 1
    assert payload["miss_count"] == 1
    assert payload["push_count"] == 1
    assert payload["hit_rate"] == 0.5
    assert payload["outcomes"]["settled_sample_count"] == 3
    assert payload["outcomes_shadow"]["settled_sample_count"] == 0


def test_forward_ledger_performance_excludes_outcomes_without_settled_side(
    tmp_path: Path,
) -> None:
    root = tmp_path / "forward_outcome_ledger"
    root.mkdir()
    outcome = _outcome_record("fixture-1", "WIN", side="pick")
    outcome.pop("settled_side")
    _write_jsonl(root / "2026-07-07_staging.jsonl", [outcome])

    payload = forward_ledger_performance(tmp_path)

    assert payload["settled_sample_count"] == 0
    assert payload["outcomes"]["settled_sample_count"] == 0
    assert payload["outcomes_shadow"]["settled_sample_count"] == 0


def test_forward_ledger_performance_splits_shadow_outcomes_from_real_hit_rate(
    tmp_path: Path,
) -> None:
    root = tmp_path / "forward_outcome_ledger"
    root.mkdir()
    _write_jsonl(
        root / "2026-07-07_staging.jsonl",
        [
            _outcome_record("fixture-1", "WIN", side="shadow_pick"),
            _outcome_record("fixture-2", "LOSS", side="shadow_pick"),
            _record("2026-07-07T03:00:00Z", fixture_id="fixture-3"),
        ],
    )

    payload = forward_ledger_performance(tmp_path)

    assert payload["settled_sample_count"] == 0
    assert payload["hit_rate"] is None
    assert payload["outcomes"]["settled_sample_count"] == 0
    assert payload["outcomes_shadow"]["settled_sample_count"] == 2
    assert payload["outcomes_shadow"]["hit_count"] == 1
    assert payload["outcomes_shadow"]["miss_count"] == 1
    assert payload["outcomes_shadow"]["hit_rate"] == 0.5
    assert payload["by_league"][0]["shadow_settled_sample_count"] == 2


def test_forward_ledger_performance_isolates_validation_from_official_outcomes(
    tmp_path: Path,
) -> None:
    root = tmp_path / "forward_outcome_ledger"
    root.mkdir()
    official = _outcome_record("fixture-official", "WIN", side="pick")
    official["recommendation_scope"] = "OFFICIAL"
    validation_win = _outcome_record("fixture-validation-win", "WIN", side="pick")
    validation_win["recommendation_scope"] = "VALIDATION"
    validation_loss = _outcome_record("fixture-validation-loss", "LOSS", side="pick")
    validation_loss["recommendation_scope"] = "VALIDATION"
    _write_jsonl(
        root / "2026-07-07_staging.jsonl",
        [official, validation_win, validation_loss],
    )

    payload = forward_ledger_performance(tmp_path)

    assert payload["settled_sample_count"] == 1
    assert payload["hit_rate"] == 1.0
    assert payload["outcomes"]["settled_sample_count"] == 1
    assert payload["outcomes_validation"]["settled_sample_count"] == 2
    assert payload["outcomes_validation"]["hit_rate"] == 0.5
    league = payload["by_league"][0]
    assert league["settled_sample_count"] == 1
    assert league["validation_settled_sample_count"] == 2
    assert league["validation_hit_rate"] == 0.5


def test_forward_ledger_performance_reports_validation_fixture_denominator(
    tmp_path: Path,
) -> None:
    root = tmp_path / "forward_outcome_ledger"
    root.mkdir()
    settled_capture = _record(
        "2026-07-07T01:00:00Z", fixture_id="validation-settled", pick=True
    )
    settled_capture["decision_tier"] = "ANALYSIS_PICK"
    pending_capture = _record(
        "2026-07-07T02:00:00Z", fixture_id="validation-pending", pick=True
    )
    pending_capture["decision_tier"] = "ANALYSIS_PICK"
    outcome = _outcome_record("validation-settled", "WIN", side="pick")
    outcome["recommendation_scope"] = "VALIDATION"
    _write_jsonl(
        root / "2026-07-07_staging.jsonl",
        [settled_capture, pending_capture, outcome],
    )

    payload = forward_ledger_performance(tmp_path)

    assert payload["validation_fixture_count"] == 2
    assert payload["validation_settled_fixture_count"] == 1
    assert payload["validation_pending_fixture_count"] == 1


def test_validation_pending_status_distinguishes_waiting_from_unsettled_result(
    tmp_path: Path,
) -> None:
    root = tmp_path / "forward_outcome_ledger"
    root.mkdir()
    now = datetime(2026, 7, 11, 12, 0, tzinfo=UTC)
    captures = []
    for fixture_id, kickoff in (
        ("validation-settled", "2026-07-11T06:00:00Z"),
        ("before-window", "2026-07-11T13:00:00Z"),
        ("in-window", "2026-07-11T10:00:00Z"),
        ("awaiting-result", "2026-07-11T06:00:00Z"),
        ("result-unsettled", "2026-07-11T06:00:00Z"),
    ):
        capture = _record("2026-07-10T12:00:00Z", fixture_id=fixture_id, kickoff=kickoff, pick=True)
        capture["decision_tier"] = "ANALYSIS_PICK"
        captures.append(capture)
    outcome = _outcome_record("validation-settled", "WIN", side="pick")
    outcome["recommendation_scope"] = "VALIDATION"
    _write_jsonl(root / "2026-07-10_staging.jsonl", [*captures, outcome])

    payload = forward_ledger_performance(
        tmp_path,
        now=now,
        result_events=[
            {
                "fixture_id": "result-unsettled",
                "status": "FT",
                "score": {"fulltime": {"home": 2, "away": 1}},
            }
        ],
    )

    assert payload["validation_fixture_count"] == 5
    assert payload["validation_settled_fixture_count"] == 1
    assert payload["validation_pending_fixture_count"] == 4
    assert payload["validation_pending_status"] == {
        "pre_settlement_window_fixture_count": 2,
        "awaiting_official_result_fixture_count": 1,
        "result_available_unsettled_fixture_count": 1,
        "result_source_unavailable_fixture_count": 0,
        "result_source_available": True,
        "pending_fixture_count": 4,
    }


def test_validation_pending_status_reports_unavailable_result_source(
    tmp_path: Path,
) -> None:
    root = tmp_path / "forward_outcome_ledger"
    root.mkdir()
    capture = _record(
        "2026-07-10T12:00:00Z",
        fixture_id="pending",
        kickoff="2026-07-11T06:00:00Z",
        pick=True,
    )
    capture["decision_tier"] = "ANALYSIS_PICK"
    _write_jsonl(root / "2026-07-10_staging.jsonl", [capture])

    payload = forward_ledger_performance(
        tmp_path,
        now=datetime(2026, 7, 11, 12, 0, tzinfo=UTC),
        result_events=None,
    )

    assert payload["validation_pending_status"]["result_source_available"] is False
    assert payload["validation_pending_status"]["result_source_unavailable_fixture_count"] == 1


def test_legacy_unscoped_outcome_inherits_validation_capture_and_deduplicates(
    tmp_path: Path,
) -> None:
    root = tmp_path / "forward_outcome_ledger"
    root.mkdir()
    capture = _record(
        "2026-07-07T01:00:00Z",
        fixture_id="fixture-validation",
        pick=True,
    )
    capture["decision_tier"] = "ANALYSIS_PICK"
    capture["card_hash"] = "hash-fixture-validation"
    legacy = _outcome_record("fixture-validation", "WIN", side="pick")
    canonical = dict(legacy)
    canonical["recommendation_scope"] = "VALIDATION"
    canonical["source_capture_hash"] = capture["card_hash"]
    _write_jsonl(root / "2026-07-07_staging.jsonl", [capture, legacy, canonical])

    payload = forward_ledger_performance(tmp_path)

    assert payload["settled_sample_count"] == 0
    assert payload["outcomes_validation"]["settled_sample_count"] == 1


def test_forward_ledger_performance_reads_mixed_v1_v2_and_outcome_records(
    tmp_path: Path,
) -> None:
    root = tmp_path / "forward_outcome_ledger"
    root.mkdir()
    legacy = _record(
        "2026-07-07T00:00:00Z",
        fixture_id="fixture-legacy",
        record_type=None,
    )
    legacy["outcome"] = "WIN"
    _write_jsonl(
        root / "2026-07-07_staging.jsonl",
        [
            legacy,
            _record("2026-07-07T01:00:00Z", fixture_id="fixture-v2"),
            _outcome_record("fixture-outcome", "PUSH", side="pick"),
            _outcome_record("fixture-shadow", "VOID", side="shadow_pick"),
        ],
    )

    payload = forward_ledger_performance(tmp_path)

    assert payload["record_count"] == 4
    assert payload["settled_sample_count"] == 1
    assert payload["push_count"] == 1
    assert payload["outcomes_shadow"]["void_count"] == 1


def test_forward_ledger_performance_clv_uses_same_line_entry_minus_closing(tmp_path: Path) -> None:
    root = tmp_path / "forward_outcome_ledger"
    root.mkdir()
    _write_jsonl(
        root / "2026-07-07_staging.jsonl",
        [
            _record(
                "2026-07-07T00:00:00Z",
                fixture_id="fixture-1",
                kickoff="2026-07-08T01:00:00Z",
                home_price=2.05,
                pick=True,
            ),
            _record(
                "2026-07-08T00:30:00Z",
                fixture_id="fixture-1",
                kickoff="2026-07-08T01:00:00Z",
                home_price=1.90,
                pick=True,
            ),
        ],
    )

    payload = forward_ledger_performance(tmp_path)

    assert payload["clv"]["sample_count"] == 1
    assert payload["clv"]["median_decimal"] == 0.15
    assert payload["clv"]["entry_window_met_count"] == 1
    assert payload["clv"]["median_decimal_window_met"] == 0.15
    assert payload["clv_shadow"]["sample_count"] == 0
    assert payload["clv"]["positive_count"] == 1
    assert payload["by_league"][0]["clv_median_decimal"] == 0.15


def test_forward_ledger_performance_tracks_shadow_clv_separately(
    tmp_path: Path,
) -> None:
    root = tmp_path / "forward_outcome_ledger"
    root.mkdir()
    _write_jsonl(
        root / "2026-07-07_staging.jsonl",
        [
            _record(
                "2026-07-07T00:00:00Z",
                fixture_id="fixture-1",
                kickoff="2026-07-08T01:00:00Z",
                home_price=2.05,
                shadow_pick=True,
            ),
            _record(
                "2026-07-08T00:30:00Z",
                fixture_id="fixture-1",
                kickoff="2026-07-08T01:00:00Z",
                home_price=1.90,
                shadow_pick=True,
            ),
        ],
    )

    payload = forward_ledger_performance(tmp_path)

    assert payload["clv"]["sample_count"] == 0
    assert payload["clv_shadow"]["sample_count"] == 1
    assert payload["clv_shadow"]["median_decimal"] == 0.15
    assert payload["clv_shadow"]["method"] == (
        "shadow_pick_entry_minus_closing_same_line; not_displayed_direction"
    )
    assert "shadow CLV" in payload["accrual_note"]
    assert payload["by_league"][0]["clv_shadow_median_decimal"] == 0.15
    assert payload["double_snapshot_fixture_count"] == 1
    assert payload["by_league"][0]["double_snapshot_fixture_count"] == 1


def test_forward_ledger_performance_uses_distinct_fixtures_and_stable_competition_id(
    tmp_path: Path,
) -> None:
    root = tmp_path / "forward_outcome_ledger"
    root.mkdir()
    rows = [
        _record(
            f"2026-07-07T{hour:02d}:00:00Z",
            fixture_id="fixture-1" if hour < 5 else "fixture-2",
            competition_name=f"Allsvenskan · Regular Season - {12 + hour}",
        )
        for hour in range(10)
    ]
    _write_jsonl(root / "2026-07-07_staging.jsonl", rows)

    payload = forward_ledger_performance(tmp_path)

    assert payload["record_count"] == 10
    assert payload["fixture_count"] == 2
    assert payload["accumulation_label"] == "积累中 2/200"
    assert len(payload["by_league"]) == 1
    assert payload["by_league"][0]["league"] == "allsvenskan"
    assert payload["by_league"][0]["fixture_count"] == 2


def test_forward_ledger_performance_maps_provider_ids_to_canonical_competitions(
    tmp_path: Path,
) -> None:
    root = tmp_path / "forward_outcome_ledger"
    root.mkdir()
    _write_jsonl(
        root / "2026-07-07_staging.jsonl",
        [
            _record(
                "2026-07-07T00:00:00Z",
                fixture_id="sweden",
                competition_id="113",
                competition_name="Allsvenskan · Regular Season - 12",
            ),
            _record(
                "2026-07-07T01:00:00Z",
                fixture_id="world-cup",
                competition_id="1",
                competition_name="World Cup",
            ),
        ],
    )

    payload = forward_ledger_performance(tmp_path)

    assert {row["league"] for row in payload["by_league"]} == {
        "allsvenskan",
        "world_cup_2026",
    }


def test_forward_ledger_performance_splits_totals_decimal_and_line_clv(
    tmp_path: Path,
) -> None:
    root = tmp_path / "forward_outcome_ledger"
    root.mkdir()
    entry = _record(
        "2026-07-07T00:00:00Z",
        fixture_id="fixture-ou",
        kickoff="2026-07-08T01:00:00Z",
    )
    closing = _record(
        "2026-07-08T00:30:00Z",
        fixture_id="fixture-ou",
        kickoff="2026-07-08T01:00:00Z",
    )
    for row, line, price in ((entry, "2.25", 2.05), (closing, "2.5", 1.90)):
        row["shadow_picks"] = [
            {
                "market": "TOTALS",
                "selection": "OVER",
                "market_line_at_capture": line,
                "not_a_recommendation": True,
            }
        ]
        row["current_odds"]["ou"] = {  # type: ignore[index]
            "line": line,
            "over_price": price,
            "under_price": 1.85,
        }
    _write_jsonl(root / "2026-07-07_staging.jsonl", [entry, closing])

    payload = forward_ledger_performance(tmp_path)

    assert payload["clv_shadow"]["sample_count"] == 0
    assert payload["clv_shadow"]["line_changed_count"] == 1
    assert payload["clv_shadow"]["line_clv_sample_count"] == 1
    assert payload["clv_shadow"]["median_line_clv"] == 0.25
    market = payload["by_league_market"][0]
    assert market["market"] == "TOTALS"
    assert market["median_decimal_clv"] is None
    assert market["median_line_clv"] == 0.25


def test_forward_ledger_performance_excludes_clv_without_prematch_closing(
    tmp_path: Path,
) -> None:
    root = tmp_path / "forward_outcome_ledger"
    root.mkdir()
    _write_jsonl(
        root / "2026-07-07_staging.jsonl",
        [
            _record(
                "2026-07-08T01:05:00Z",
                fixture_id="fixture-1",
                kickoff="2026-07-08T01:00:00Z",
                home_price=2.05,
                pick=True,
            ),
            _record(
                "2026-07-08T01:10:00Z",
                fixture_id="fixture-1",
                kickoff="2026-07-08T01:00:00Z",
                home_price=1.90,
                pick=True,
            ),
        ],
    )

    payload = forward_ledger_performance(tmp_path)

    assert payload["clv"]["sample_count"] == 0
    assert payload["clv"]["excluded_no_prematch_closing"] == 1


@pytest.mark.parametrize(
    ("settled_count", "expected_status"),
    [(34, "ACCUMULATING"), (35, "REVIEW_ELIGIBLE"), (100, "MATURE")],
)
def test_ev_shadow_challenger_uses_35_and_100_sample_evidence_levels(
    tmp_path: Path,
    settled_count: int,
    expected_status: str,
) -> None:
    root = tmp_path / "forward_outcome_ledger"
    root.mkdir()
    records: list[dict[str, object]] = []
    for index in range(settled_count):
        fixture_id = f"fixture-ev-{index}"
        shadow = {
            "market": "TOTALS",
            "candidate_pass": True,
            "evidence_eligible": True,
            "net_ev": 0.04,
            "shadow_only": True,
            "affects_decision": False,
        }
        records.extend(
            [
                {
                    "record_type": "capture",
                    "fixture_id": fixture_id,
                    "competition_id": "39",
                    "captured_at": f"2026-08-{index % 28 + 1:02d}T10:00:00Z",
                    "analysis_gate_v2_shadows": [shadow],
                },
                {
                    "record_type": "outcome",
                    "fixture_id": fixture_id,
                    "competition_id": "39",
                    "market": "TOTALS",
                    "settled_side": "shadow_pick",
                    "settlement_outcome": "WIN" if index % 2 == 0 else "LOSS",
                    "entry_price": "1.95",
                    "analysis_gate_v2_shadow": shadow,
                },
            ]
        )
    _write_jsonl(root / "2026-08-01_staging.jsonl", records)

    payload = forward_ledger_performance(tmp_path)

    row = next(
        item
        for item in payload["by_league_market"]
        if item["league"] == "premier_league" and item["market"] == "TOTALS"
    )
    challenger = row["ev_shadow_challenger"]
    assert challenger["settled_candidate_count"] == settled_count
    assert challenger["evidence_status"] == expected_status
    assert challenger["review_threshold"] == 35
    assert challenger["maturity_threshold"] == 100
    assert challenger["affects_decision"] is False


def test_forward_ledger_performance_marks_late_entry_window(
    tmp_path: Path,
) -> None:
    root = tmp_path / "forward_outcome_ledger"
    root.mkdir()
    _write_jsonl(
        root / "2026-07-07_staging.jsonl",
        [
            _record(
                "2026-07-07T12:00:00Z",
                fixture_id="fixture-1",
                kickoff="2026-07-08T01:00:00Z",
                home_price=2.05,
                pick=True,
            ),
            _record(
                "2026-07-08T00:30:00Z",
                fixture_id="fixture-1",
                kickoff="2026-07-08T01:00:00Z",
                home_price=1.90,
                pick=True,
            ),
        ],
    )

    payload = forward_ledger_performance(tmp_path)

    assert payload["clv"]["sample_count"] == 1
    assert payload["clv"]["entry_window_met_count"] == 0
    assert payload["clv"]["median_decimal_window_met"] is None


def test_forward_ledger_performance_counts_entry_line_mismatch(
    tmp_path: Path,
) -> None:
    root = tmp_path / "forward_outcome_ledger"
    root.mkdir()
    _write_jsonl(
        root / "2026-07-07_staging.jsonl",
        [
            _record(
                "2026-07-07T00:00:00Z",
                fixture_id="fixture-1",
                kickoff="2026-07-08T01:00:00Z",
                home_price=2.05,
                shadow_pick=True,
                shadow_market_line="-0.75",
            ),
            _record(
                "2026-07-08T00:30:00Z",
                fixture_id="fixture-1",
                kickoff="2026-07-08T01:00:00Z",
                home_price=1.90,
                shadow_pick=True,
                shadow_market_line="-0.75",
            ),
        ],
    )

    payload = forward_ledger_performance(tmp_path)

    assert payload["clv_shadow"]["sample_count"] == 1
    assert payload["clv_shadow"]["entry_line_mismatch_count"] == 1


def test_forward_ledger_performance_reads_legacy_v1_capture_records(
    tmp_path: Path,
) -> None:
    root = tmp_path / "forward_outcome_ledger"
    root.mkdir()
    _write_jsonl(
        root / "2026-07-07_staging.jsonl",
        [
            _record(
                "2026-07-07T00:00:00Z",
                fixture_id="fixture-1",
                kickoff="2026-07-08T01:00:00Z",
                home_price=2.05,
                pick=True,
                record_type=None,
            ),
            _record(
                "2026-07-08T00:30:00Z",
                fixture_id="fixture-1",
                kickoff="2026-07-08T01:00:00Z",
                home_price=1.90,
                pick=True,
                record_type=None,
            ),
        ],
    )

    payload = forward_ledger_performance(tmp_path)

    assert payload["clv"]["sample_count"] == 1
    assert payload["clv"]["median_decimal"] == 0.15


def _record(
    captured_at: str,
    *,
    fixture_id: str,
    kickoff: str = "2026-07-08T01:00:00Z",
    home_price: float = 2.0,
    pick: bool = False,
    shadow_pick: bool = False,
    shadow_market_line: str = "-1",
    record_type: str | None = "capture",
    competition_id: str | None = None,
    competition_name: str = "World Cup",
) -> dict[str, object]:
    row: dict[str, object] = {
        "record_type": record_type,
        "captured_at": captured_at,
        "football_day": "2026-07-07",
        "environment": "staging",
        "fixture_id": fixture_id,
        "kickoff_utc": kickoff,
        "competition_name": competition_name,
        "decision_tier": "WATCH",
        "current_odds": {
            "ah": {
                "home_line": "-1",
                "away_line": "+1",
                "home_price": home_price,
                "away_price": 1.8,
            }
        },
    }
    if competition_id:
        row["competition_id"] = competition_id
    if pick:
        row["pick"] = {"market": "ASIAN_HANDICAP", "selection": "HOME_AH"}
    if shadow_pick:
        row["shadow_pick"] = {
            "market": "ASIAN_HANDICAP",
            "selection": "HOME_AH",
            "market_line_at_capture": shadow_market_line,
            "shadow": True,
            "not_a_recommendation": True,
        }
    if record_type is None:
        row.pop("record_type")
    return row


def _outcome_record(
    fixture_id: str,
    settlement_outcome: str,
    *,
    side: str,
) -> dict[str, object]:
    return {
        "schema_version": "w2.forward_outcome_ledger.v2",
        "record_type": "outcome",
        "settled_at": "2026-07-08T03:00:00Z",
        "football_day": "2026-07-07",
        "environment": "staging",
        "fixture_id": fixture_id,
        "competition_name": "World Cup",
        "card_hash": f"hash-{fixture_id}",
        "market": "ASIAN_HANDICAP",
        "selection": "HOME_AH",
        "settled_side": side,
        "settlement_outcome": settlement_outcome,
    }


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows),
        encoding="utf-8",
    )
