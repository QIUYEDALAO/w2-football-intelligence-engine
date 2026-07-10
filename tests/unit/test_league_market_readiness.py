from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from w2.readiness.league_market import build_league_market_readiness

NOW = datetime(2026, 7, 11, tzinfo=UTC)


def test_empty_evidence_reports_thirteen_active_leagues_without_guessing() -> None:
    payload = build_league_market_readiness(now=NOW)

    assert payload["active_competition_count"] == 13
    assert payload["market_count"] == 26
    assert payload["status_counts"] == {"BLOCKED": 26}
    assert "world_cup_2026" not in {row["competition_id"] for row in payload["rows"]}
    assert payload["provider_calls"] == 0
    assert payload["db_reads"] == 0
    assert payload["db_writes"] == 0
    assert payload["direction_allowed_changes"] == []


def test_statistics_success_does_not_count_as_numeric_xg(tmp_path: Path) -> None:
    evidence = _evidence(shadow_pairs=0)
    evidence["leagues"]["chinese_super_league"]["statistics_response_count"] = 100
    evidence["leagues"]["chinese_super_league"]["xg_numeric_match_count"] = 0
    path = _write(tmp_path, evidence)

    row = _row(
        build_league_market_readiness(evidence_path=path, now=NOW),
        "chinese_super_league",
        "ASIAN_HANDICAP",
    )

    assert row["statistics_response_count"] == 100
    assert row["xg_numeric_match_count"] == 0


def test_status_moves_from_technical_ready_to_accumulating_to_review(
    tmp_path: Path,
) -> None:
    statuses = []
    for name, count in (("technical", 0), ("accumulating", 40), ("eligible", 100)):
        path = _write(tmp_path / name, _evidence(shadow_pairs=count))
        statuses.append(
            _row(
                build_league_market_readiness(evidence_path=path, now=NOW),
                "chinese_super_league",
                "ASIAN_HANDICAP",
            )["status"]
        )

    assert statuses == ["TECHNICALLY_READY", "ACCUMULATING", "ELIGIBLE_FOR_REVIEW"]


def test_ah_and_totals_are_evaluated_independently(tmp_path: Path) -> None:
    evidence = _evidence(shadow_pairs=100)
    totals = evidence["leagues"]["chinese_super_league"]["markets"]["TOTALS"]
    totals["pinnacle_line_count"] = 0
    path = _write(tmp_path, evidence)

    payload = build_league_market_readiness(evidence_path=path, now=NOW)

    assert _row(payload, "chinese_super_league", "ASIAN_HANDICAP")["status"] == (
        "ELIGIBLE_FOR_REVIEW"
    )
    totals_row = _row(payload, "chinese_super_league", "TOTALS")
    assert totals_row["status"] == "BLOCKED"
    assert "PINNACLE_MARKET_MISSING" in totals_row["blockers"]


def _evidence(*, shadow_pairs: int) -> dict[str, Any]:
    market = {
        "pinnacle_line_count": 20,
        "model_market_gap": 0.03,
        "shadow_closing_pair_count": shadow_pairs,
        "entry_window_rate": 0.9,
        "closing_pair_coverage_rate": 0.9,
        "outcome_coverage_rate": 0.95,
        "median_same_line_decimal_clv": 0.01,
    }
    return {
        "generated_at_utc": "2026-07-11T00:00:00Z",
        "source_sha": "sanitized-sha",
        "leagues": {
            "chinese_super_league": {
                "fixture_coverage": True,
                "statistics_response_count": 12,
                "xg_numeric_match_count": 10,
                "rolling_feature_team_count": 16,
                "elo_team_count": 16,
                "squad_value_team_count": 16,
                "rest_days_team_count": 16,
                "lineup_status": "PARTIAL",
                "validated_model": True,
                "artifact_hash": "artifact-hash",
                "artifact_version": "v1",
                "train_cutoff": "2025-12-31T00:00:00Z",
                "feature_parity": "PASS",
                "markets": {
                    "ASIAN_HANDICAP": dict(market),
                    "TOTALS": dict(market),
                },
            }
        },
    }


def _write(root: Path, payload: dict[str, Any]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / "evidence.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _row(payload: dict[str, Any], competition_id: str, market: str) -> dict[str, Any]:
    return next(
        row
        for row in payload["rows"]
        if row["competition_id"] == competition_id and row["market"] == market
    )
