from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from w2.models.fair_market_estimate import FairMarketEstimate, FairMarketEstimateSnapshot
from w2.tracking.forward_outcome_ledger import backfill_outcomes, run_forward_outcome_ledger


def _day_view() -> dict[str, object]:
    return {
        "football_day": "2026-07-07",
        "environment": "staging",
        "cards": [
            {
                "fixture_id": "fixture-1",
                "kickoff_utc": "2026-07-07T16:00:00Z",
                "competition_id": "world_cup_2026",
                "competition_name": "World Cup",
                "home_team_name": "Argentina",
                "away_team_name": "Egypt",
                "decision_tier": "WATCH",
                "data_status": "READY",
                "reason_code": "EDGE_INSUFFICIENT",
                "action": "盯价格变动",
                "probability_source": "MARKET_DEVIG",
                "model_market_divergence": {
                    "status": "READY",
                    "magnitude": 0.03,
                    "direction_allowed": False,
                    "model_fair_line": "-1.5",
                    "market_line": "-1.25",
                    "model_family": "R4_1_CALIBRATED",
                },
                "current_odds": {
                    "ah": {
                        "home_line": "-1.25",
                        "away_line": "+1.25",
                        "home_price": "1.91",
                        "away_price": "1.93",
                        "bookmaker_count": 4,
                    }
                },
                "card_hash": "hash-1",
                "outcome_tracked": False,
                "source": "decision_contract",
            }
        ],
    }


def test_forward_outcome_ledger_dry_run_does_not_write(tmp_path: Path) -> None:
    payload = run_forward_outcome_ledger(
        _day_view(),
        dry_run=True,
        write_artifacts=True,
        runtime_root=tmp_path,
        captured_at=datetime(2026, 7, 7, 12, 0, tzinfo=UTC),
    )

    assert payload["provider_calls"] == 0
    assert payload["db_writes"] == 0
    assert payload["lock_capture_write"] is False
    assert payload["settlement_write"] is False
    assert payload["record_count"] == 1
    assert payload["written"] == 0
    assert list(tmp_path.glob("*.jsonl")) == []


def test_forward_outcome_ledger_write_is_idempotent(tmp_path: Path) -> None:
    first = run_forward_outcome_ledger(
        _day_view(),
        dry_run=False,
        write_artifacts=True,
        runtime_root=tmp_path,
        captured_at=datetime(2026, 7, 7, 12, 0, tzinfo=UTC),
    )
    second = run_forward_outcome_ledger(
        _day_view(),
        dry_run=False,
        write_artifacts=True,
        runtime_root=tmp_path,
        captured_at=datetime(2026, 7, 7, 12, 5, tzinfo=UTC),
    )

    output = tmp_path / "2026-07-07_staging.jsonl"
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert first["written"] == 1
    assert second["written"] == 0
    assert second["skipped_existing"] == 1
    assert len(rows) == 1
    assert rows[0]["not_a_lock"] is True
    assert rows[0]["posthoc_only"] is True
    assert rows[0]["record_type"] == "capture"
    assert rows[0]["shadow_pick"] == {
        "market": "ASIAN_HANDICAP",
        "selection": "HOME_AH",
        "model_fair_line": -1.5,
        "market_line_at_capture": -1.25,
        "divergence_line_units": -0.25,
        "derived_from": "model_market_divergence",
        "display_tier_at_capture": "WATCH",
        "shadow": True,
        "not_a_recommendation": True,
        "not_displayed": True,
        "raw_shadow_capture": True,
        "diagnostic_only": True,
        "evidence_eligible": False,
        "semantic_status": "LEGACY_DISTRIBUTION_CONTEXT_UNVERIFIED",
    }
    assert rows[0]["current_odds"]["ah"]["bookmaker_count"] == 4
    assert rows[0]["model_market_divergence"]["model_family"] == "R4_1_CALIBRATED"
    assert rows[0]["capture_checkpoint"] == "EVIDENCE_CHANGE"
    assert len(rows[0]["evidence_hash"]) == 64


def test_forward_outcome_ledger_records_distinct_t24_and_t1_checkpoints(
    tmp_path: Path,
) -> None:
    day_view = _day_view()
    card = day_view["cards"][0]  # type: ignore[index]
    card["kickoff_utc"] = "2026-07-08T12:00:00Z"  # type: ignore[index]

    first = run_forward_outcome_ledger(
        day_view,
        dry_run=False,
        write_artifacts=True,
        runtime_root=tmp_path,
        captured_at=datetime(2026, 7, 7, 12, 0, tzinfo=UTC),
    )
    second = run_forward_outcome_ledger(
        day_view,
        dry_run=False,
        write_artifacts=True,
        runtime_root=tmp_path,
        captured_at=datetime(2026, 7, 8, 11, 0, tzinfo=UTC),
    )

    assert first["written"] == 1
    assert second["written"] == 1
    rows = [
        json.loads(line)
        for line in (tmp_path / "2026-07-07_staging.jsonl").read_text().splitlines()
    ]
    assert {row["capture_checkpoint"] for row in rows} == {
        "T_MINUS_24H",
        "T_MINUS_1H",
    }


def test_forward_outcome_ledger_shadow_pick_is_null_without_lines(
    tmp_path: Path,
) -> None:
    day_view = _day_view()
    card = day_view["cards"][0]  # type: ignore[index]
    divergence = card["model_market_divergence"]  # type: ignore[index]
    divergence.pop("model_fair_line")  # type: ignore[union-attr]

    payload = run_forward_outcome_ledger(
        day_view,
        dry_run=True,
        write_artifacts=False,
        runtime_root=tmp_path,
        captured_at=datetime(2026, 7, 7, 12, 0, tzinfo=UTC),
    )

    assert payload["records"][0]["shadow_pick"] is None


def test_forward_outcome_ledger_records_ah_and_totals_shadow_picks(tmp_path: Path) -> None:
    day_view = _day_view()
    card = day_view["cards"][0]  # type: ignore[index]
    card["current_odds"]["ou"] = {  # type: ignore[index]
        "line": "2.5",
        "over_price": "1.95",
        "under_price": "1.91",
    }
    card["fair_market_estimates"] = [  # type: ignore[index]
        {
            "market": "ASIAN_HANDICAP",
            "status": "READY",
            "fair_line": -1.5,
            "model_family": "R4_1_CALIBRATED",
        },
        {
            "market": "TOTALS",
            "status": "READY",
            "fair_line": 3.0,
            "model_family": "R4_1_CALIBRATED",
        },
    ]

    payload = run_forward_outcome_ledger(
        day_view,
        dry_run=True,
        runtime_root=tmp_path,
        captured_at=datetime(2026, 7, 7, 12, 0, tzinfo=UTC),
    )

    assert [item["market"] for item in payload["records"][0]["shadow_picks"]] == [
        "ASIAN_HANDICAP",
        "TOTALS",
    ]
    assert payload["records"][0]["shadow_picks"][1]["selection"] == "OVER"


def test_watch_ah_keeps_raw_shadow_capture(tmp_path: Path) -> None:
    payload = run_forward_outcome_ledger(
        _day_view(),
        dry_run=True,
        runtime_root=tmp_path,
        captured_at=datetime(2026, 7, 7, 12, 0, tzinfo=UTC),
    )

    record = payload["records"][0]
    assert record["decision_tier"] == "WATCH"
    assert record["recommendation_scope"] is None
    assert record["shadow_pick"]["raw_shadow_capture"] is True
    assert record["shadow_pick"]["diagnostic_only"] is True
    assert record["shadow_pick"]["evidence_eligible"] is False


def test_shadow_capture_does_not_enter_validation(tmp_path: Path) -> None:
    day_view = _day_view()
    day_view["cards"][0]["decision_tier"] = "ANALYSIS_PICK"  # type: ignore[index]
    payload = run_forward_outcome_ledger(
        day_view,
        dry_run=False,
        write_artifacts=True,
        runtime_root=tmp_path / "forward_outcome_ledger",
        captured_at=datetime(2026, 7, 7, 12, 0, tzinfo=UTC),
    )
    outcomes = backfill_outcomes(
        tmp_path,
        {"results": [_result("fixture-1", 2, 0)]},
        dry_run=True,
    )

    assert payload["written"] == 1
    assert outcomes["record_count"] == 1
    assert outcomes["records"][0]["settled_side"] == "shadow_pick"
    assert outcomes["records"][0]["recommendation_scope"] == "SHADOW"


def test_shadow_capture_does_not_enter_official(tmp_path: Path) -> None:
    day_view = _day_view()
    day_view["cards"][0]["decision_tier"] = "RECOMMEND"  # type: ignore[index]
    payload = run_forward_outcome_ledger(
        day_view,
        dry_run=False,
        write_artifacts=True,
        runtime_root=tmp_path / "forward_outcome_ledger",
        captured_at=datetime(2026, 7, 7, 12, 0, tzinfo=UTC),
    )
    outcomes = backfill_outcomes(
        tmp_path,
        {"results": [_result("fixture-1", 2, 0)]},
        dry_run=True,
    )

    assert payload["written"] == 1
    assert outcomes["record_count"] == 1
    assert outcomes["records"][0]["settled_side"] == "shadow_pick"
    assert outcomes["records"][0]["recommendation_scope"] == "SHADOW"


def test_forward_outcome_backfill_settles_two_shadow_markets_from_one_capture(
    tmp_path: Path,
) -> None:
    day_view = _day_view()
    card = day_view["cards"][0]  # type: ignore[index]
    card["current_odds"]["ou"] = {  # type: ignore[index]
        "line": "2.5",
        "over_price": "1.95",
        "under_price": "1.91",
    }
    card["fair_market_estimates"] = [  # type: ignore[index]
        {"market": "ASIAN_HANDICAP", "status": "READY", "fair_line": -1.5},
        {"market": "TOTALS", "status": "READY", "fair_line": 3.0},
    ]
    run_forward_outcome_ledger(
        day_view,
        dry_run=False,
        write_artifacts=True,
        runtime_root=tmp_path / "forward_outcome_ledger",
        captured_at=datetime(2026, 7, 7, 12, 0, tzinfo=UTC),
    )

    result = backfill_outcomes(
        tmp_path,
        {"results": [_result("fixture-1", 3, 0)]},
        dry_run=False,
        write_artifacts=True,
    )

    assert result["written"] == 2
    rows = [
        json.loads(line)
        for line in (tmp_path / "forward_outcome_ledger" / "2026-07-07_staging.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    outcomes = [row for row in rows if row.get("record_type") == "outcome"]
    assert {(row["market"], row["settlement_outcome"]) for row in outcomes} == {
        ("ASIAN_HANDICAP", "WIN"),
        ("TOTALS", "WIN"),
    }


def test_estimate_id_survives_capture_and_settlement(tmp_path: Path) -> None:
    snapshot = FairMarketEstimateSnapshot.create(
        fixture_id="fixture-1",
        estimate=FairMarketEstimate(
            market="TOTALS",
            status="READY",
            model_family="R4_1_CALIBRATED",
            fair_line=3.0,
            probabilities={"OVER": 0.55, "UNDER": 0.45},
            home_mu=1.8,
            away_mu=1.2,
            feature_as_of="2026-07-07T12:00:00Z",
            train_cutoff="2026-06-01T00:00:00Z",
            artifact_hash="artifact",
            artifact_version="v1",
        ),
        odds_snapshot={"ou": {"line": 2.5, "over_price": 1.95}},
        feature_snapshot={"home_xg": 1.8, "away_xg": 1.2},
        created_at="2026-07-07T12:00:00Z",
    ).as_dict()
    day_view = _day_view()
    card = day_view["cards"][0]  # type: ignore[index]
    card["decision_tier"] = "ANALYSIS_PICK"  # type: ignore[index]
    card["outcome_tracked"] = True  # type: ignore[index]
    card["current_odds"]["ou"] = {  # type: ignore[index]
        "line": "2.5",
        "over_price": "1.95",
        "under_price": "1.91",
    }
    card["pick"] = {  # type: ignore[index]
        "market": "TOTALS",
        "selection": "OVER",
        "line": "2.5",
        "odds": "1.95",
        "estimate_id": snapshot["estimate_id"],
    }
    card["fair_market_estimate_ids"] = [snapshot["estimate_id"]]  # type: ignore[index]
    card["fair_market_estimate_snapshots"] = [snapshot]  # type: ignore[index]
    card["fair_market_estimates"] = [snapshot]  # type: ignore[index]

    run_forward_outcome_ledger(
        day_view,
        dry_run=False,
        write_artifacts=True,
        runtime_root=tmp_path / "forward_outcome_ledger",
        captured_at=datetime(2026, 7, 7, 12, 0, tzinfo=UTC),
    )
    result = backfill_outcomes(
        tmp_path,
        {"results": [_result("fixture-1", 2, 1)]},
        dry_run=False,
        write_artifacts=True,
    )

    assert result["written"] >= 1
    rows = [
        json.loads(line)
        for line in (tmp_path / "forward_outcome_ledger" / "2026-07-07_staging.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    capture = next(row for row in rows if row["record_type"] == "capture")
    outcome = next(
        row
        for row in rows
        if row["record_type"] == "outcome" and row["settled_side"] == "pick"
    )
    assert capture["fair_market_estimate_ids"] == [snapshot["estimate_id"]]
    assert capture["estimate_integrity"] == [
        {"estimate_id": snapshot["estimate_id"], "valid": True}
    ]
    assert outcome["estimate_id"] == snapshot["estimate_id"]


def test_validation_settlement_uses_last_valid_prematch_snapshot(tmp_path: Path) -> None:
    day_view = _day_view()
    card = day_view["cards"][0]  # type: ignore[index]
    card["fixture_id"] = "1494699"  # type: ignore[index]
    card["kickoff_utc"] = "2026-07-11T18:00:00Z"  # type: ignore[index]
    card["decision_tier"] = "ANALYSIS_PICK"  # type: ignore[index]
    card["pick"] = {"market": "ASIAN_HANDICAP", "selection": "AWAY_AH"}  # type: ignore[index]
    card["current_odds"]["ah"].update({"away_line": "+1", "away_price": 1.60})  # type: ignore[index]
    run_forward_outcome_ledger(
        day_view,
        dry_run=False,
        write_artifacts=True,
        runtime_root=tmp_path / "forward_outcome_ledger",
        captured_at=datetime(2026, 7, 11, 12, 0, tzinfo=UTC),
    )
    card["current_odds"]["ah"].update({"away_line": "+0.75", "away_price": 1.92})  # type: ignore[index]
    run_forward_outcome_ledger(
        day_view,
        dry_run=False,
        write_artifacts=True,
        runtime_root=tmp_path / "forward_outcome_ledger",
        captured_at=datetime(2026, 7, 11, 17, 30, tzinfo=UTC),
    )

    payload = backfill_outcomes(
        tmp_path,
        {"results": [_result("1494699", 2, 1)]},
        dry_run=True,
        settled_at=datetime(2026, 7, 11, 21, 0, tzinfo=UTC),
    )

    outcome = next(row for row in payload["records"] if row["settled_side"] == "pick")
    assert outcome["recommendation_scope"] == "VALIDATION"
    assert outcome["entry_line"] == "+0.75"
    assert outcome["entry_price"] == 1.92
    assert outcome["source_captured_at"] == "2026-07-11T17:30:00Z"
    assert outcome["source_capture_hash"]


def test_forward_outcome_ledger_cli_reads_day_view_json(tmp_path: Path) -> None:
    day_view_path = tmp_path / "day_view.json"
    day_view_path.write_text(json.dumps(_day_view()), encoding="utf-8")
    output_root = tmp_path / "ledger"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_w2_forward_outcome_ledger.py",
            "--day-view-json",
            str(day_view_path),
            "--runtime-root",
            str(output_root),
            "--json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert payload["dry_run"] is True
    assert payload["provider_calls"] == 0
    assert payload["db_writes"] == 0
    assert payload["record_count"] == 1
    assert not output_root.exists()


def test_forward_outcome_backfill_writes_win_push_half_loss_and_void(
    tmp_path: Path,
) -> None:
    root = tmp_path / "forward_outcome_ledger"
    root.mkdir()
    _write_jsonl(
        root / "2026-07-07_staging.jsonl",
        [
            _capture("fixture-win", "hash-win", home_line="-1", home_price="1.9"),
            _capture("fixture-push", "hash-push", home_line="-1", home_price="1.9"),
            _capture("fixture-half-loss", "hash-half", home_line="-0.25", home_price="1.9"),
            _capture("fixture-void", "hash-void", home_line=None, home_price="1.9"),
        ],
    )

    payload = backfill_outcomes(
        tmp_path,
        {
            "results": [
                _result("fixture-win", 2, 0),
                _result("fixture-push", 1, 0),
                _result("fixture-half-loss", 0, 0),
                _result("fixture-void", 2, 0),
            ]
        },
        dry_run=False,
        write_artifacts=True,
        settled_at=datetime(2026, 7, 8, 12, 0, tzinfo=UTC),
    )

    rows = [
        json.loads(line)
        for line in (root / "2026-07-07_staging.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    outcomes = {row["fixture_id"]: row for row in rows if row.get("record_type") == "outcome"}
    assert payload["provider_calls"] == 0
    assert payload["db_writes"] == 0
    assert payload["settlement_write"] is False
    assert payload["written"] == 4
    assert outcomes["fixture-win"]["settlement_outcome"] == "WIN"
    assert outcomes["fixture-push"]["settlement_outcome"] == "PUSH"
    assert outcomes["fixture-half-loss"]["settlement_outcome"] == "HALF_LOSS"
    assert outcomes["fixture-void"]["settlement_outcome"] == "VOID"
    assert outcomes["fixture-void"]["void_reason"] == "MISSING_ENTRY_LINE_OR_PRICE"
    assert outcomes["fixture-win"]["settled_side"] == "pick"
    assert outcomes["fixture-win"]["final_score"] == {
        "home": 2,
        "away": 0,
        "status": "FT",
    }


def test_forward_outcome_backfill_is_idempotent(tmp_path: Path) -> None:
    root = tmp_path / "forward_outcome_ledger"
    root.mkdir()
    _write_jsonl(
        root / "2026-07-07_staging.jsonl",
        [_capture("fixture-1", "hash-1", home_line="-1", home_price="1.9")],
    )
    source = {"results": [_result("fixture-1", 2, 0)]}

    first = backfill_outcomes(tmp_path, source, dry_run=False, write_artifacts=True)
    second = backfill_outcomes(tmp_path, source, dry_run=False, write_artifacts=True)

    assert first["written"] == 1
    assert second["written"] == 0
    assert second["skipped_existing"] == 1


def test_forward_outcome_backfill_ignores_non_ft_results(tmp_path: Path) -> None:
    root = tmp_path / "forward_outcome_ledger"
    root.mkdir()
    _write_jsonl(
        root / "2026-07-07_staging.jsonl",
        [_capture("fixture-1", "hash-1", home_line="-1", home_price="1.9")],
    )

    payload = backfill_outcomes(
        tmp_path,
        {"results": [_result("fixture-1", 2, 0, status="1H")]},
        dry_run=False,
        write_artifacts=True,
    )

    assert payload["record_count"] == 0
    assert payload["written"] == 0


def test_forward_outcome_backfill_settles_aet_with_fulltime_score(
    tmp_path: Path,
) -> None:
    root = tmp_path / "forward_outcome_ledger"
    root.mkdir()
    _write_jsonl(
        root / "2026-07-07_staging.jsonl",
        [_capture("fixture-aet", "hash-aet", home_line="-1", home_price="1.9")],
    )

    payload = backfill_outcomes(
        tmp_path,
        {
            "results": [
                {
                    "fixture_id": "fixture-aet",
                    "status": "AET",
                    "score": {
                        "fulltime": {"home": 1, "away": 0},
                        "extratime": {"home": 2, "away": 0},
                    },
                }
            ]
        },
        dry_run=False,
        write_artifacts=True,
    )

    rows = [
        json.loads(line)
        for line in (root / "2026-07-07_staging.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    outcome = [row for row in rows if row.get("record_type") == "outcome"][0]
    assert payload["record_count"] == 1
    assert payload["unsettled_missing_fulltime"] == 0
    assert outcome["settlement_outcome"] == "PUSH"
    assert outcome["final_score"] == {"home": 1, "away": 0, "status": "AET"}


def test_forward_outcome_backfill_skips_aet_without_fulltime_score(
    tmp_path: Path,
) -> None:
    root = tmp_path / "forward_outcome_ledger"
    root.mkdir()
    _write_jsonl(
        root / "2026-07-07_staging.jsonl",
        [_capture("fixture-aet", "hash-aet", home_line="-1", home_price="1.9")],
    )

    payload = backfill_outcomes(
        tmp_path,
        {"results": [_result("fixture-aet", 2, 0, status="AET")]},
        dry_run=False,
        write_artifacts=True,
    )

    assert payload["record_count"] == 0
    assert payload["written"] == 0
    assert payload["unsettled_missing_fulltime"] == 1


def test_forward_outcome_backfill_settles_shadow_pick_separately(
    tmp_path: Path,
) -> None:
    root = tmp_path / "forward_outcome_ledger"
    root.mkdir()
    capture = _capture("fixture-1", "hash-1", home_line="-1", home_price="1.9")
    capture["shadow_pick"] = {
        "market": "ASIAN_HANDICAP",
        "selection": "AWAY_AH",
        "not_a_recommendation": True,
        "not_displayed": True,
    }
    capture["current_odds"]["ah"]["away_line"] = "+1"
    capture["current_odds"]["ah"]["away_price"] = "1.8"
    _write_jsonl(root / "2026-07-07_staging.jsonl", [capture])

    payload = backfill_outcomes(
        tmp_path,
        {"results": [_result("fixture-1", 2, 0)]},
        dry_run=False,
        write_artifacts=True,
    )

    rows = [
        json.loads(line)
        for line in (root / "2026-07-07_staging.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    outcomes = [row for row in rows if row.get("record_type") == "outcome"]
    assert payload["written"] == 2
    assert {row["settled_side"] for row in outcomes} == {"pick", "shadow_pick"}
    shadow = [row for row in outcomes if row["settled_side"] == "shadow_pick"][0]
    assert shadow["settlement_outcome"] == "LOSS"
    assert shadow["selection"] == "AWAY_AH"


def test_validation_recommendation_scope_is_frozen_and_settled_separately(
    tmp_path: Path,
) -> None:
    root = tmp_path / "forward_outcome_ledger"
    root.mkdir()
    capture = _capture("fixture-validation", "hash-validation", home_line="-1", home_price="1.9")
    capture["decision_tier"] = "ANALYSIS_PICK"
    capture["outcome_tracked"] = True
    _write_jsonl(root / "2026-07-07_staging.jsonl", [capture])

    payload = backfill_outcomes(
        tmp_path,
        {"results": [_result("fixture-validation", 2, 0)]},
        dry_run=True,
    )

    assert payload["record_count"] == 1
    outcome = payload["records"][0]
    assert outcome["settled_side"] == "pick"
    assert outcome["recommendation_scope"] == "VALIDATION"
    assert outcome["card_hash"] == "hash-validation"


def test_validation_and_official_recommendations_for_same_fixture_settle_as_two_tracks(
    tmp_path: Path,
) -> None:
    root = tmp_path / "forward_outcome_ledger"
    root.mkdir()
    validation = _capture("fixture-upgraded", "hash-validation", home_line="-1", home_price="1.9")
    validation["decision_tier"] = "ANALYSIS_PICK"
    validation["recommendation_scope"] = "VALIDATION"
    official = _capture("fixture-upgraded", "hash-official", home_line="-1", home_price="1.9")
    official["captured_at"] = "2026-07-07T01:00:00Z"
    official["decision_tier"] = "RECOMMEND"
    official["recommendation_scope"] = "OFFICIAL"
    _write_jsonl(root / "2026-07-07_staging.jsonl", [validation, official])

    payload = backfill_outcomes(
        tmp_path,
        {"results": [_result("fixture-upgraded", 2, 0)]},
        dry_run=False,
        write_artifacts=True,
    )
    rerun = backfill_outcomes(
        tmp_path,
        {"results": [_result("fixture-upgraded", 2, 0)]},
        dry_run=False,
        write_artifacts=True,
    )

    assert payload["written"] == 2
    assert rerun["written"] == 0
    assert rerun["skipped_existing"] == 2
    rows = [
        json.loads(line)
        for line in (root / "2026-07-07_staging.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    outcomes = [row for row in rows if row.get("record_type") == "outcome"]
    assert {row["recommendation_scope"] for row in outcomes} == {"VALIDATION", "OFFICIAL"}


def test_forward_outcome_backfill_settles_totals_quarter_line_from_all_window(
    tmp_path: Path,
) -> None:
    root = tmp_path / "forward_outcome_ledger"
    root.mkdir()
    capture = _capture("fixture-total", "hash-total", home_line="-1", home_price="1.9")
    capture["shadow_pick"] = {
        "market": "TOTALS",
        "selection": "OVER",
        "not_a_recommendation": True,
        "not_displayed": True,
    }
    capture["shadow_picks"] = [capture["shadow_pick"]]
    capture["current_odds"]["ou"] = {  # type: ignore[index]
        "line": "2.25",
        "over_price": "1.91",
        "under_price": "1.93",
    }
    capture["pick"] = None
    _write_jsonl(root / "2026-07-07_staging.jsonl", [capture])

    payload = backfill_outcomes(
        tmp_path,
        {"all": [_result("fixture-total", 2, 0)]},
        dry_run=False,
        write_artifacts=True,
    )

    rows = [
        json.loads(line) for line in (root / "2026-07-07_staging.jsonl").read_text().splitlines()
    ]
    outcome = [row for row in rows if row.get("record_type") == "outcome"][0]
    assert payload["written"] == 1
    assert outcome["market"] == "TOTALS"
    assert outcome["settlement_outcome"] == "HALF_LOSS"


def _capture(
    fixture_id: str,
    card_hash: str,
    *,
    home_line: str | None,
    home_price: str | None,
) -> dict[str, object]:
    ah = {
        "away_line": "+1",
        "away_price": "1.8",
    }
    if home_line is not None:
        ah["home_line"] = home_line
    if home_price is not None:
        ah["home_price"] = home_price
    return {
        "schema_version": "w2.forward_outcome_ledger.v2",
        "record_type": "capture",
        "captured_at": "2026-07-07T00:00:00Z",
        "football_day": "2026-07-07",
        "environment": "staging",
        "fixture_id": fixture_id,
        "kickoff_utc": "2026-07-08T02:00:00Z",
        "competition_id": "world_cup_2026",
        "competition_name": "World Cup",
        "card_hash": card_hash,
        "pick": {"market": "ASIAN_HANDICAP", "selection": "HOME_AH"},
        "current_odds": {"ah": ah},
    }


def _result(
    fixture_id: str,
    home: int,
    away: int,
    *,
    status: str = "FT",
) -> dict[str, object]:
    return {
        "fixture_id": fixture_id,
        "status": status,
        "home_score": home,
        "away_score": away,
    }


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows),
        encoding="utf-8",
    )
