from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

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
    assert payload["accumulation_label"] == "积累中 0/200"
    assert payload["validation_fixture_count"] == 0
    assert payload["validation_market_pick_count"] == 0
    assert payload["mock_data"] is False


def test_forward_ledger_performance_counts_only_real_outcomes(tmp_path: Path) -> None:
    root = tmp_path / "forward_outcome_ledger"
    root.mkdir()
    _write_jsonl(
        root / "2026-07-07_staging.jsonl",
        [
            _outcome_record("fixture-1", "WIN", side="pick", scope="OFFICIAL"),
            _outcome_record("fixture-2", "LOSS", side="pick", scope="OFFICIAL"),
            _outcome_record("fixture-3", "PUSH", side="pick", scope="OFFICIAL"),
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
    assert payload["settled_sample_count"] == 0
    assert payload["push_count"] == 0
    assert payload["outcomes_shadow"]["void_count"] == 1
    assert payload["validation_excluded_count"] == 0


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


def test_validation_counts_unique_fixtures_and_keeps_scopes_separate(tmp_path: Path) -> None:
    root = tmp_path / "forward_outcome_ledger"
    root.mkdir()
    first = _validation_capture("fixture-1", "2026-07-07T00:00:00Z")
    duplicate = _validation_capture("fixture-1", "2026-07-07T01:00:00Z")
    _write_jsonl(
        root / "2026-07-07_staging.jsonl",
        [
            first,
            duplicate,
            _outcome_record("fixture-1", "PUSH", side="pick", scope="VALIDATION"),
            _outcome_record("official-1", "WIN", side="pick", scope="OFFICIAL"),
            _outcome_record("shadow-1", "LOSS", side="shadow_pick", scope="SHADOW"),
        ],
    )

    payload = forward_ledger_performance(tmp_path)

    assert payload["record_count"] == 5
    assert payload["validation_fixture_count"] == 1
    assert payload["validation_settled_fixture_count"] == 1
    assert payload["validation_pending_fixture_count"] == 0
    assert payload["outcomes_validation"]["push_count"] == 1
    assert payload["outcomes_validation"]["hit_rate"] is None
    assert payload["outcomes"]["hit_count"] == 1
    assert payload["outcomes_shadow"]["miss_count"] == 1


def test_validation_pending_status_explains_missing_result(tmp_path: Path) -> None:
    root = tmp_path / "forward_outcome_ledger"
    root.mkdir()
    capture = _validation_capture("fixture-1", "2026-07-07T00:00:00Z")
    _write_jsonl(root / "2026-07-07_staging.jsonl", [capture])
    (tmp_path / "forward_outcome_result_refresh_state.json").write_text(
        json.dumps(
            {
                "schema_version": "w2.outcome_result_refresh.v1",
                "fixtures": {
                    "fixture-1": {
                        "status": "RESULT_MISSING",
                        "checked_at_utc": "2026-07-08T04:00:00Z",
                        "next_check_at_utc": "2026-07-08T05:00:00Z",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    payload = forward_ledger_performance(
        tmp_path,
        now=datetime(2026, 7, 8, 6, 0, tzinfo=UTC),
    )

    status = payload["validation_pending_status"]
    assert status["result_missing_count"] == 1
    assert status["settlement_error_count"] == 0
    assert status["details"][0]["category"] == "RESULT_MISSING"


def test_validation_identity_conflict_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "forward_outcome_ledger"
    root.mkdir()
    first = _validation_capture("fixture-1", "2026-07-07T00:00:00Z")
    conflict = _validation_capture("fixture-1", "2026-07-07T01:00:00Z")
    conflict["pick"] = {"market": "ASIAN_HANDICAP", "selection": "AWAY_AH"}
    _write_jsonl(root / "2026-07-07_staging.jsonl", [first, conflict])

    payload = forward_ledger_performance(tmp_path)

    assert payload["validation_fixture_count"] == 0
    assert payload["validation_excluded_by_reason"] == {"RECOMMENDATION_IDENTITY_CONFLICT": 1}


def test_complete_v3_capture_counts_as_canonical_and_reports_calibration(tmp_path: Path) -> None:
    root = tmp_path / "forward_outcome_ledger"
    root.mkdir()
    capture = _validation_capture("fixture-1", "2026-07-07T00:00:00Z")
    capture.update(
        {
            "schema_version": "w2.forward_outcome_ledger.v3",
            "capture_identity_hash": "capture-hash-1",
            "artifact_provenance": {"artifact_hash": "artifact-hash-1"},
            "quote_provenance": {
                "markets": {
                    "ah": {
                        "identity_status": "COMPLETE",
                        "freshness_status": "COMPLETE",
                        "captured_at": "2026-07-07T00:00:00Z",
                    }
                }
            },
            "probability_identity": {
                "market_probabilities": {
                    "one_x_two": {"probabilities": {"HOME": 0.5, "DRAW": 0.3, "AWAY": 0.2}}
                }
            },
        }
    )
    outcome = _outcome_record("fixture-1", "WIN", side="pick", scope="VALIDATION")
    outcome.update(
        {
            "capture_identity_hash": "capture-hash-1",
            "final_score": {"home": 2, "away": 0, "status": "FT"},
            "entry_price": 1.9,
        }
    )
    _write_jsonl(root / "2026-07-07_staging.jsonl", [capture, outcome])

    payload = forward_ledger_performance(tmp_path)

    assert payload["canonical_settled_fixture_count"] == 1
    assert payload["canonical_excluded_count"] == 0
    assert payload["calibration"]["sample_count"] == 1
    assert payload["calibration"]["log_loss"] > 0
    assert payload["calibration"]["research_roi"] == 0.9


def test_validation_league_rows_merge_rounds_and_use_canonical_outcomes(tmp_path: Path) -> None:
    root = tmp_path / "forward_outcome_ledger"
    root.mkdir()
    captures = []
    outcomes = []
    for fixture_id, round_number, outcome_value in (
        ("fixture-18", 18, "WIN"),
        ("fixture-19", 19, "LOSS"),
    ):
        capture = _validation_capture(fixture_id, f"2026-07-{round_number:02d}T00:00:00Z")
        capture["competition_id"] = "169"
        capture["competition_name"] = f"中超 · 常规赛第{round_number}轮"
        outcome = _outcome_record(fixture_id, outcome_value, side="pick", scope="VALIDATION")
        outcome.update(
            {
                "source_capture_hash": capture["card_hash"],
                "source_captured_at": capture["captured_at"],
                "final_score": {"home": 2, "away": 1, "status": "FT"},
            }
        )
        captures.append(capture)
        outcomes.append(outcome)
    _write_jsonl(root / "2026-07-18_staging.jsonl", [*captures, *outcomes])

    payload = forward_ledger_performance(tmp_path)

    assert payload["outcomes_canonical"]["settled_sample_count"] == 2
    assert payload["outcomes_canonical"]["hit_rate"] == 0.5
    assert payload["by_league_validation"] == [
        {
            "competition_id": "169",
            "league": "中超",
            "validation_fixture_count": 2,
            "validation_settled_fixture_count": 2,
            "canonical_settled_fixture_count": 2,
            "canonical_excluded_count": 0,
            "hit_count": 1,
            "miss_count": 1,
            "push_count": 0,
            "void_count": 0,
            "hit_rate": 0.5,
            "clv_sample_count": 0,
            "clv_median_decimal": None,
        }
    ]


def test_legacy_capture_with_unique_outcome_link_is_inherited_without_calibration(
    tmp_path: Path,
) -> None:
    root = tmp_path / "forward_outcome_ledger"
    root.mkdir()
    capture = _validation_capture("fixture-legacy", "2026-07-07T00:00:00Z")
    capture["schema_version"] = "w2.forward_outcome_ledger.v2"
    outcome = _outcome_record("fixture-legacy", "WIN", side="pick", scope="VALIDATION")
    outcome.update(
        {
            "source_capture_hash": capture["card_hash"],
            "source_captured_at": capture["captured_at"],
            "final_score": {"home": 2, "away": 0, "status": "FT"},
        }
    )
    _write_jsonl(root / "2026-07-07_staging.jsonl", [capture, outcome])

    payload = forward_ledger_performance(tmp_path)

    assert payload["canonical_settled_fixture_count"] == 1
    assert payload["canonical_excluded_count"] == 0
    assert payload["calibration"]["sample_count"] == 0


def test_v3_missing_probability_remains_canonical_but_skips_calibration(
    tmp_path: Path,
) -> None:
    root = tmp_path / "forward_outcome_ledger"
    root.mkdir()
    capture = _validation_capture("fixture-v3", "2026-07-07T00:00:00Z")
    capture.update(
        {
            "schema_version": "w2.forward_outcome_ledger.v3",
            "capture_identity_hash": "capture-hash-v3",
            "artifact_provenance": {"artifact_hash": "artifact-hash-v3"},
            "quote_provenance": {
                "markets": {
                    "ah": {
                        "identity_status": "COMPLETE",
                        "freshness_status": "COMPLETE",
                        "captured_at": "2026-07-07T00:00:00Z",
                    }
                }
            },
        }
    )
    outcome = _outcome_record("fixture-v3", "WIN", side="pick", scope="VALIDATION")
    outcome.update(
        {
            "capture_identity_hash": "capture-hash-v3",
            "final_score": {"home": 2, "away": 0, "status": "FT"},
        }
    )
    _write_jsonl(root / "2026-07-07_staging.jsonl", [capture, outcome])

    payload = forward_ledger_performance(tmp_path)

    assert payload["canonical_settled_fixture_count"] == 1
    assert payload["calibration"]["sample_count"] == 0


def test_performance_cohort_partitions_samples_and_filters_clv(tmp_path: Path) -> None:
    root = tmp_path / "forward_outcome_ledger"
    root.mkdir()
    eligible_entry = _validation_capture("eligible", "2026-07-07T00:00:00Z")
    eligible_close = _validation_capture("eligible", "2026-07-08T00:30:00Z")
    eligible_close["current_odds"] = {
        "ah": {
            "home_line": "-1",
            "away_line": "+1",
            "home_price": 1.8,
            "away_price": 2.0,
        }
    }
    eligible_outcome = _outcome_record("eligible", "WIN", side="pick", scope="VALIDATION")
    eligible_outcome.update(
        {
            "source_capture_hash": eligible_entry["card_hash"],
            "source_captured_at": eligible_entry["captured_at"],
            "final_score": {"home": 2, "away": 0, "status": "FT"},
        }
    )
    excluded = _validation_capture("excluded", "2026-07-07T00:05:00Z")
    excluded["competition_id"] = "169"
    excluded["competition_name"] = "中超 · 常规赛第19轮"
    excluded_outcome = _outcome_record("excluded", "LOSS", side="pick", scope="VALIDATION")
    excluded_outcome.update({"final_score": {"home": 0, "away": 1, "status": "FT"}})
    pending = _validation_capture("pending", "2026-07-07T00:10:00Z")
    _write_jsonl(
        root / "2026-07-07_staging.jsonl",
        [eligible_entry, eligible_close, eligible_outcome, excluded, excluded_outcome, pending],
    )

    payload = forward_ledger_performance(tmp_path)
    cohort = payload["performance_cohort"]

    assert payload["schema_version"] == "w2.forward_ledger_performance.v3"
    assert cohort["validation_count"] == 3
    assert cohort["processed_count"] == 2
    assert cohort["eligible_count"] == 1
    assert cohort["excluded_count"] == 1
    assert cohort["pending_count"] == 1
    assert cohort["outcomes"]["decisive_count"] == 1
    assert cohort["outcomes"]["hit_rate"] == 1.0
    assert cohort["clv"]["sample_count"] == 1
    assert cohort["clv"]["median_decimal"] == 0.2
    assert cohort["invariants"]["status"] == "PASS"
    assert cohort["exclusions"] == [
        {
            "fixture_id": "excluded",
            "competition_id": "169",
            "league": "中超",
            "home_team_name": "Home",
            "away_team_name": "Away",
            "kickoff_utc": "2026-07-08T01:00:00Z",
            "settlement_outcome": "LOSS",
            "reason_code": "LEGACY_CAPTURE_LINK_MISSING",
            "reason_label": "历史推荐与赛果身份链缺失",
        }
    ]
    csl = next(row for row in cohort["by_league"] if row["competition_id"] == "169")
    assert csl["processed_count"] == 1
    assert csl["eligible_count"] == 0
    assert csl["excluded_count"] == 1
    assert csl["rate_status"] == "INSUFFICIENT"


def _validation_capture(fixture_id: str, captured_at: str) -> dict[str, object]:
    return {
        **_record(captured_at, fixture_id=fixture_id, pick=True),
        "schema_version": "w2.forward_outcome_ledger.v2",
        "recommendation_scope": "VALIDATION",
        "competition_id": "league-1",
        "home_team_name": "Home",
        "away_team_name": "Away",
        "card_hash": f"card-{fixture_id}",
        "decision_tier": "ANALYSIS_PICK",
        "outcome_tracked": True,
    }


def _record(
    captured_at: str,
    *,
    fixture_id: str,
    kickoff: str = "2026-07-08T01:00:00Z",
    home_price: float = 2.0,
    pick: bool = False,
    shadow_pick: bool = False,
    record_type: str | None = "capture",
) -> dict[str, object]:
    row: dict[str, object] = {
        "record_type": record_type,
        "captured_at": captured_at,
        "football_day": "2026-07-07",
        "environment": "staging",
        "fixture_id": fixture_id,
        "kickoff_utc": kickoff,
        "competition_name": "World Cup",
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
    if pick:
        row["pick"] = {"market": "ASIAN_HANDICAP", "selection": "HOME_AH"}
    if shadow_pick:
        row["shadow_pick"] = {
            "market": "ASIAN_HANDICAP",
            "selection": "HOME_AH",
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
    scope: str | None = None,
) -> dict[str, object]:
    row: dict[str, object] = {
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
    if scope is not None:
        row["recommendation_scope"] = scope
    return row


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows),
        encoding="utf-8",
    )
