from __future__ import annotations

import json
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
    assert payload["accumulation_label"] == "积累中 2/200"
    assert payload["mock_data"] is False


def test_forward_ledger_performance_counts_only_real_outcomes(tmp_path: Path) -> None:
    root = tmp_path / "forward_outcome_ledger"
    root.mkdir()
    _write_jsonl(
        root / "2026-07-07_staging.jsonl",
        [
            {**_record("2026-07-07T00:00:00Z", fixture_id="fixture-1"), "outcome": "WIN"},
            {**_record("2026-07-07T01:00:00Z", fixture_id="fixture-2"), "outcome": "LOSS"},
            {**_record("2026-07-07T02:00:00Z", fixture_id="fixture-3"), "outcome": "PUSH"},
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
    assert payload["settled_sample_count"] == 2
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
