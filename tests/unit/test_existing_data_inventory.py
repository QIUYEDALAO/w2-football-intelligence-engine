from __future__ import annotations

import json
from pathlib import Path

from w2.historical.existing_data_inventory import build_existing_football_data_inventory


def test_inventory_no_runtime_does_not_request_new_data_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("W2_RUNTIME_ROOT", raising=False)

    inventory = build_existing_football_data_inventory(repo_root=tmp_path)

    assert inventory["status"] == "NO_EXISTING_DATA_FOUND"
    assert inventory["summary"]["top_five_existing_download_detected"] is False
    assert inventory["classification"]["requires_user_extra_data"] is False
    assert inventory["privacy"]["provider_calls"] == 0
    assert inventory["privacy"]["home_directory_full_scan"] is False
    assert inventory["database"]["status"] == "LOCAL_DATABASE_NOT_FOUND"


def test_inventory_counts_allowed_runtime_top_five_odds(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("W2_RUNTIME_ROOT", raising=False)
    runtime = tmp_path / "runtime" / "future_refresh"
    runtime.mkdir(parents=True)
    payload = {
        "endpoint": "odds",
        "fixture": {"id": "fixture-1", "date": "2026-08-01T14:00:00Z"},
        "league": {"id": 39, "season": 2026},
        "captured_at": "2026-08-01T12:00:00Z",
        "bookmaker": {"id": "book-1"},
        "canonical_market": "ASIAN_HANDICAP",
        "selection": "Home",
        "line": "-0.25",
        "decimal_odds": "1.91",
    }
    (runtime / "odds.jsonl").write_text(json.dumps(payload) + "\n", encoding="utf-8")

    inventory = build_existing_football_data_inventory(repo_root=tmp_path)

    assert inventory["status"] == "EXISTING_DATA_INSUFFICIENT"
    assert inventory["summary"]["top_five_existing_download_detected"] is True
    assert inventory["summary"]["historical_odds_found"] is True
    assert inventory["summary"]["bookmaker_found"] is True
    assert inventory["summary"]["ah_line_found"] is True
    assert inventory["summary"]["final_result_found"] is False
