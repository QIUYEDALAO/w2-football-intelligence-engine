from __future__ import annotations

import csv
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from w2.markets.baselight_limited_ah import (
    build_walk_forward,
    normalize_observations,
    rows_from_sample,
)

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "reports/W2_GATE3_BASELIGHT_LIMITED_AH_EXTRACT_MANIFEST.json"
WALK_FORWARD = ROOT / "reports/W2_GATE3_BASELIGHT_AH_WALK_FORWARD.json"
RESULT = ROOT / "reports/W2_GATE3_BASELIGHT_AH_WALK_FORWARD_RESULT.md"
HANDOFF = ROOT / "reports/W2_CURRENT_HANDOFF.md"


def _write_sample(path: Path, fixture_count: int = 25) -> None:
    rows: list[dict[str, object]] = []
    competitions = [
        "Synthetic League Alpha",
        "Synthetic League Bravo",
        "Synthetic League Charlie",
        "Synthetic League Delta",
        "Synthetic Cup Echo",
    ]
    bookmakers = ["Pinnacle", "SBO", "Dafabet", "Bet365", "BookE"]
    lines = ["-0.25", "+0.25", "-0.5", "+0.5", "-0.75", "+0.75", "-1.0", "+1.0"]
    start = datetime(2024, 1, 1, tzinfo=UTC)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "match_id",
                "competition",
                "season",
                "kickoff_utc",
                "home_team_name",
                "away_team_name",
                "status",
                "home_score",
                "away_score",
                "bookmaker",
                "market",
                "outcome",
                "odds",
                "odds_type",
                "collected_at",
            ],
        )
        writer.writeheader()
        for fixture_index in range(fixture_count):
            kickoff = start + timedelta(days=fixture_index)
            home_score = fixture_index % 4
            away_score = (fixture_index + 1) % 3
            for book_index, bookmaker in enumerate(bookmakers):
                line = lines[(fixture_index + book_index) % len(lines)]
                writer.writerow(
                    {
                        "match_id": f"fx-{fixture_index:03d}",
                        "competition": competitions[fixture_index % len(competitions)],
                        "season": "2024",
                        "kickoff_utc": kickoff.isoformat().replace("+00:00", "Z"),
                        "home_team_name": f"Home {fixture_index}",
                        "away_team_name": f"Away {fixture_index}",
                        "status": "finished",
                        "home_score": home_score,
                        "away_score": away_score,
                        "bookmaker": bookmaker,
                        "market": "Asian Handicap",
                        "outcome": f"Home {fixture_index} {line}",
                        "odds": "1.91",
                        "odds_type": "pre_match",
                        "collected_at": (kickoff - timedelta(days=1)).date().isoformat(),
                    }
                )
                rows.append({})


def test_limited_ah_parser_settles_and_keeps_fixture_level_folds(tmp_path: Path) -> None:
    sample = tmp_path / "sample.csv"
    _write_sample(sample)
    observations, errors = normalize_observations(rows_from_sample(sample))
    walk_forward = build_walk_forward(observations)

    assert errors == {}
    assert len(observations) == 125
    assert walk_forward["fold_count"] == 5
    assert walk_forward["status"] == "INSUFFICIENT_SAMPLE"
    assert "BASELIGHT_LIMITED_AH_SAMPLE_TOO_SMALL" in walk_forward["blockers"]
    assert walk_forward["candidate"] is False
    assert walk_forward["formal_recommendation"] is False
    assert sum(fold["fixture_count"] for fold in walk_forward["folds"]) == 25


def test_limited_ah_cli_does_not_fake_backtest_pass(tmp_path: Path) -> None:
    previous_manifest = MANIFEST.read_text(encoding="utf-8")
    previous_walk_forward = WALK_FORWARD.read_text(encoding="utf-8")
    previous_result = RESULT.read_text(encoding="utf-8")
    try:
        result = subprocess.run(
            [
                sys.executable,
                "scripts/run_w2_gate3_baselight_ah_walk_forward.py",
                "--sample-path",
                str(tmp_path / "w2-baselight-contract-sample-does-not-exist.jsonl"),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        walk_forward = json.loads(WALK_FORWARD.read_text(encoding="utf-8"))
        handoff = HANDOFF.read_text(encoding="utf-8")
    finally:
        MANIFEST.write_text(previous_manifest, encoding="utf-8")
        WALK_FORWARD.write_text(previous_walk_forward, encoding="utf-8")
        RESULT.write_text(previous_result, encoding="utf-8")

    assert result.returncode == 0, result.stderr
    assert manifest["status"] == "INSUFFICIENT_SAMPLE"
    assert manifest["large_sample_committed"] is False
    assert walk_forward["status"] == "INSUFFICIENT_SAMPLE"
    assert walk_forward["fixture_count"] == 0
    assert "BASELIGHT_LIMITED_AH_SAMPLE_TOO_SMALL" in walk_forward["blockers"]
    assert "handoff_version: 35" in handoff
    assert "candidate: false" in handoff
    assert "formal_recommendation: false" in handoff
