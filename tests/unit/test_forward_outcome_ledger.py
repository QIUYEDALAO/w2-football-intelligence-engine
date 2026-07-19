from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from w2.tracking.forward_outcome_ledger import (
    backfill_outcomes,
    build_forward_outcome_records,
    pending_outcome_entries,
    run_forward_outcome_ledger,
)


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


def test_forward_capture_identity_preserves_at_most_one_strict_secondary() -> None:
    day_view = _day_view()
    card = day_view["cards"][0]  # type: ignore[index]
    card["secondary_picks"] = [  # type: ignore[index]
        {"market": "TOTALS", "selection": "UNDER", "line": "2.5"},
        {"market": "ASIAN_HANDICAP", "selection": "HOME_AH", "line": "-0.5"},
    ]
    records = build_forward_outcome_records(
        day_view,
        captured_at=datetime(2026, 7, 7, 12, 0, tzinfo=UTC),
    )
    assert records[0]["secondary_picks"] == [
        {"market": "TOTALS", "selection": "UNDER", "line": "2.5"}
    ]


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
    assert rows[0]["schema_version"] == "w2.forward_outcome_ledger.v3"
    assert rows[0]["recommendation_scope"] == "SHADOW"
    assert rows[0]["fixture_identity"] == {
        "fixture_id": "fixture-1",
        "kickoff_utc": "2026-07-07T16:00:00Z",
        "competition_id": "world_cup_2026",
        "competition_name": "World Cup",
        "home_team_id": None,
        "home_team_name": "Argentina",
        "away_team_id": None,
        "away_team_name": "Egypt",
    }
    assert len(rows[0]["capture_identity_hash"]) == 64
    assert rows[0]["quote_provenance"]["schema_version"] == "w2.quote_provenance.v1"
    assert rows[0]["artifact_provenance"]["artifact_hash"] == "hash-1"
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
    }
    assert rows[0]["current_odds"]["ah"]["bookmaker_count"] == 4


def test_forward_outcome_ledger_captures_and_settles_independent_ou_shadow(
    tmp_path: Path,
) -> None:
    day_view = _day_view()
    card = day_view["cards"][0]  # type: ignore[index]
    card["current_odds"]["ou"] = {  # type: ignore[index]
        "line": "2.5",
        "over_price": "1.91",
        "under_price": "1.93",
    }
    card["pricing_shadow"] = {"fair_ou": 2.75, "market_ou": 2.5}  # type: ignore[index]

    capture = run_forward_outcome_ledger(
        day_view,
        dry_run=False,
        write_artifacts=True,
        runtime_root=tmp_path / "forward_outcome_ledger",
        captured_at=datetime(2026, 7, 7, 12, 0, tzinfo=UTC),
    )

    assert capture["written"] == 2
    capture_rows = [
        json.loads(line)
        for line in (tmp_path / "forward_outcome_ledger" / "2026-07-07_staging.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert {
        (row["shadow_pick"]["market"], row["shadow_pick"]["selection"])
        for row in capture_rows
    } == {("ASIAN_HANDICAP", "HOME_AH"), ("TOTALS", "OVER")}
    assert all(row["shadow_pick"]["not_a_recommendation"] is True for row in capture_rows)
    assert all(row["shadow_pick"]["not_displayed"] is True for row in capture_rows)

    settlement = backfill_outcomes(
        tmp_path,
        {"results": [_result("fixture-1", 2, 1)]},
        dry_run=False,
        write_artifacts=True,
    )

    assert settlement["written"] == 2
    rows = [
        json.loads(line)
        for line in (tmp_path / "forward_outcome_ledger" / "2026-07-07_staging.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    outcomes = [row for row in rows if row.get("record_type") == "outcome"]
    assert {(row["market"], row["selection"], row["settlement_outcome"]) for row in outcomes} == {
        ("ASIAN_HANDICAP", "HOME_AH", "HALF_LOSS"),
        ("TOTALS", "OVER", "WIN"),
    }


def test_forward_outcome_ledger_rejects_cross_line_ou_shadow(tmp_path: Path) -> None:
    day_view = _day_view()
    card = day_view["cards"][0]  # type: ignore[index]
    card["current_odds"]["ou"] = {  # type: ignore[index]
        "line": "2.75",
        "over_price": "1.91",
        "under_price": "1.93",
    }
    card["pricing_shadow"] = {"fair_ou": 2.75, "market_ou": 2.5}  # type: ignore[index]

    records = build_forward_outcome_records(
        day_view,
        captured_at=datetime(2026, 7, 7, 12, 0, tzinfo=UTC),
    )

    assert [row["shadow_pick"]["market"] for row in records] == ["ASIAN_HANDICAP"]


def test_forward_outcome_backfill_deduplicates_same_capture_across_day_files(
    tmp_path: Path,
) -> None:
    root = tmp_path / "forward_outcome_ledger"
    root.mkdir()
    capture = _capture("fixture-1", "hash-1", home_line="-1", home_price="1.9")
    next_day = dict(capture)
    next_day["football_day"] = "2026-07-08"
    _write_jsonl(root / "2026-07-07_staging.jsonl", [capture])
    _write_jsonl(root / "2026-07-08_staging.jsonl", [next_day])

    payload = backfill_outcomes(
        tmp_path,
        {"results": [_result("fixture-1", 2, 0)]},
        dry_run=False,
        write_artifacts=True,
    )

    outcomes = [
        json.loads(line)
        for path in root.glob("*.jsonl")
        for line in path.read_text(encoding="utf-8").splitlines()
        if json.loads(line).get("record_type") == "outcome"
    ]
    assert payload["written"] == 1
    assert payload["record_count"] == 1
    assert len(outcomes) == 1


def test_forward_outcome_backfill_does_not_void_shadow_without_quote(tmp_path: Path) -> None:
    root = tmp_path / "forward_outcome_ledger"
    root.mkdir()
    capture = _capture("fixture-1", "hash-1", home_line="-1", home_price="1.9")
    capture["decision_tier"] = "WATCH"
    capture["recommendation_scope"] = "SHADOW"
    capture["outcome_tracked"] = False
    capture["pick"] = None
    capture["shadow_pick"] = {
        "market": "TOTALS",
        "selection": "OVER",
        "not_a_recommendation": True,
        "not_displayed": True,
    }
    _write_jsonl(root / "2026-07-07_staging.jsonl", [capture])

    payload = backfill_outcomes(
        tmp_path,
        {"results": [_result("fixture-1", 2, 1)]},
        dry_run=False,
        write_artifacts=True,
    )

    assert payload["written"] == 0
    assert payload["record_count"] == 0
    assert payload["unresolved_count"] == 1
    assert payload["status"] == "PARTIAL"


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


def test_forward_outcome_backfill_writes_win_push_half_loss_and_fails_closed_without_quote(
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
    assert payload["written"] == 3
    assert outcomes["fixture-win"]["settlement_outcome"] == "WIN"
    assert outcomes["fixture-push"]["settlement_outcome"] == "PUSH"
    assert outcomes["fixture-half-loss"]["settlement_outcome"] == "HALF_LOSS"
    assert "fixture-void" not in outcomes
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
    assert second["skipped_existing"] == 0
    assert second["status"] == "NO_DUE_WORK"


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


def test_forward_outcome_backfill_settles_totals_and_uses_fulltime_score(
    tmp_path: Path,
) -> None:
    root = tmp_path / "forward_outcome_ledger"
    root.mkdir()
    capture = _capture("fixture-ou", "hash-ou", home_line="-1", home_price="1.9")
    capture["pick"] = {"market": "TOTALS", "selection": "OVER"}
    capture["current_odds"] = {"ou": {"line": "2.75", "over_price": "1.9", "under_price": "1.9"}}
    _write_jsonl(root / "2026-07-07_staging.jsonl", [capture])

    payload = backfill_outcomes(
        tmp_path,
        {
            "results": [
                {
                    "fixture": {"id": "fixture-ou", "status": {"short": "AET"}},
                    "goals": {"home": 3, "away": 1},
                    "score": {"fulltime": {"home": 1, "away": 1}},
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
    assert payload["status"] == "PASS"
    assert outcome["final_score"] == {"home": 1, "away": 1, "status": "AET"}
    assert outcome["settlement_outcome"] == "LOSS"


def test_pending_entries_and_zero_result_are_not_false_pass(tmp_path: Path) -> None:
    root = tmp_path / "forward_outcome_ledger"
    root.mkdir()
    capture = _capture("fixture-1", "hash-1", home_line="-1", home_price="1.9")
    _write_jsonl(root / "2026-07-07_staging.jsonl", [capture])

    pending = pending_outcome_entries(
        tmp_path,
        now=datetime(2026, 7, 8, 6, 0, tzinfo=UTC),
    )
    payload = backfill_outcomes(tmp_path, {"results": []})

    assert len(pending) == 1
    assert pending[0]["due"] is True
    assert payload["status"] == "PARTIAL"
    assert payload["pending_count"] == 1
    assert payload["unresolved_count"] == 1


def test_v3_validation_identity_conflict_is_not_settled(tmp_path: Path) -> None:
    root = tmp_path / "forward_outcome_ledger"
    root.mkdir()
    first = _capture("fixture-1", "hash-1", home_line="-1", home_price="1.9")
    first.update(
        {
            "schema_version": "w2.forward_outcome_ledger.v3",
            "recommendation_scope": "VALIDATION",
            "outcome_tracked": True,
            "capture_identity_hash": "capture-1",
            "competition_id": "league-1",
            "home_team_name": "Home",
            "away_team_name": "Away",
        }
    )
    conflict = dict(first)
    conflict["captured_at"] = "2026-07-07T01:00:00Z"
    conflict["capture_identity_hash"] = "capture-2"
    conflict["pick"] = {"market": "ASIAN_HANDICAP", "selection": "AWAY_AH"}
    _write_jsonl(root / "2026-07-07_staging.jsonl", [first, conflict])

    payload = backfill_outcomes(
        tmp_path,
        {"results": [_result("fixture-1", 2, 0)]},
    )

    assert payload["status"] == "NO_DUE_WORK"
    assert payload["record_count"] == 0


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
        "home_team_name": "Home",
        "away_team_name": "Away",
        "card_hash": card_hash,
        "decision_tier": "ANALYSIS_PICK",
        "recommendation_scope": "VALIDATION",
        "outcome_tracked": True,
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
