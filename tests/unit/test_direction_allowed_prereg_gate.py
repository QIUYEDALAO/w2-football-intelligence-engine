from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.check_w2_direction_allowed_prereg import (
    CANDIDATE_ORDER,
    build_prereg_report,
)


def test_prereg_gate_missing_conditions_returns_blocker(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.md"
    ledger.write_text("direction_allowed review exists but no prereg conditions", encoding="utf-8")

    payload = build_prereg_report(ledger_path=ledger, runtime_root=tmp_path)

    assert "BLOCKER_DIRECTION_ALLOWED_PREREG_CONDITIONS_NOT_FOUND" in payload["blockers"]
    assert payload["release_decision"] == "REVIEW_ONLY"
    assert payload["direction_allowed_changes"] == []


def test_prereg_gate_no_samples_accumulates(tmp_path: Path) -> None:
    payload = build_prereg_report(ledger_path=_ledger(tmp_path), runtime_root=tmp_path)

    candidate_statuses = {
        row["competition_id"]: row["status"]
        for row in payload["per_league_status"]
        if row["competition_id"] in CANDIDATE_ORDER
    }
    assert payload["release_decision"] == "REVIEW_ONLY"
    assert set(candidate_statuses.values()) == {"ACCUMULATING"}
    assert payload["evidence_summary"]["clv_shadow_median"] == "ACCUMULATING"
    assert payload["provider_calls"] == 0
    assert payload["db_writes"] == 0


def test_prereg_gate_sample_insufficient_is_not_enough_sample(tmp_path: Path) -> None:
    root = tmp_path / "forward_outcome_ledger"
    root.mkdir()
    _write_jsonl(
        root / "2026-07-07_staging.jsonl",
        [
            _capture("fixture-1", "2026-07-07T00:00:00Z", "eliteserien", "1.90"),
            _capture("fixture-1", "2026-07-07T23:00:00Z", "eliteserien", "1.80"),
            _outcome("fixture-1"),
        ],
    )

    payload = build_prereg_report(
        ledger_path=_ledger(tmp_path),
        runtime_root=tmp_path,
        min_double_snapshot_cards=2,
    )
    eliteserien = payload["per_league_status"][0]

    assert payload["release_decision"] == "NOT_ELIGIBLE"
    assert eliteserien["competition_id"] == "eliteserien"
    assert eliteserien["status"] == "NOT_ENOUGH_SAMPLE"
    assert eliteserien["condition_results"]["latest_market_gap"] is True
    assert eliteserien["condition_results"]["approval"] is False


def test_prereg_gate_candidate_order_and_brazil_disabled(tmp_path: Path) -> None:
    payload = build_prereg_report(ledger_path=_ledger(tmp_path), runtime_root=tmp_path)

    assert payload["candidate_order"] == [
        "eliteserien",
        "allsvenskan",
        "chinese_super_league",
    ]
    assert [row["competition_id"] for row in payload["per_league_status"][:3]] == [
        "eliteserien",
        "allsvenskan",
        "chinese_super_league",
    ]
    assert payload["disabled_leagues"] == ["brasileirao_serie_a"]
    assert payload["per_league_status"][-1]["competition_id"] == "brasileirao_serie_a"
    assert payload["per_league_status"][-1]["status"] == "DISABLED"


def test_prereg_gate_never_changes_direction_allowed(tmp_path: Path) -> None:
    payload = build_prereg_report(ledger_path=_ledger(tmp_path), runtime_root=tmp_path)

    assert payload["direction_allowed_changes"] == []
    assert payload["direction_allowed_changed"] is False
    assert all(row["direction_allowed_change"] is False for row in payload["per_league_status"])


def test_prereg_gate_cli_json_has_zero_side_effect_flags(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/check_w2_direction_allowed_prereg.py",
            "--ledger-path",
            str(_ledger(tmp_path)),
            "--runtime-root",
            str(tmp_path),
            "--json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload["provider_calls"] == 0
    assert payload["db_writes"] == 0
    assert payload["staging_deploy"] is False
    assert payload["production_deploy"] is False
    assert payload["scheduler_restart"] is False


def test_prereg_gate_has_no_stage16_surface(tmp_path: Path) -> None:
    payload = build_prereg_report(ledger_path=_ledger(tmp_path), runtime_root=tmp_path)

    serialized = json.dumps(payload, ensure_ascii=False)
    assert "Stage 16" not in serialized
    assert "stage16" not in serialized.lower()


def _ledger(tmp_path: Path) -> Path:
    path = tmp_path / "ledger.md"
    path.write_text(
        (
            "预注册规则日期:2026-07-08。未来按联赛放行 `direction_allowed` "
            "必须单独批准 PR,且满足 shadow CLV 样本 `>=100`、shadow CLV "
            "中位数 `>0`、最新 market gap `<=0.04`;离线数字和 shadow 方向"
            "不得直接开 EV/RECOMMEND 腿。"
        ),
        encoding="utf-8",
    )
    return path


def _capture(
    fixture_id: str,
    captured_at: str,
    competition_id: str,
    home_price: str,
) -> dict[str, object]:
    return {
        "schema_version": "w2.forward_outcome_ledger.v2",
        "record_type": "capture",
        "captured_at": captured_at,
        "football_day": "2026-07-07",
        "environment": "staging",
        "fixture_id": fixture_id,
        "kickoff_utc": "2026-07-08T02:00:00Z",
        "competition_id": competition_id,
        "card_hash": fixture_id,
        "shadow_pick": {
            "market": "ASIAN_HANDICAP",
            "selection": "HOME_AH",
            "market_line_at_capture": "-1",
            "not_a_recommendation": True,
            "not_displayed": True,
        },
        "current_odds": {
            "ah": {
                "home_line": "-1",
                "home_price": home_price,
                "away_line": "+1",
                "away_price": "1.88",
            }
        },
    }


def _outcome(fixture_id: str) -> dict[str, object]:
    return {
        "schema_version": "w2.forward_outcome_ledger.v2",
        "record_type": "outcome",
        "football_day": "2026-07-07",
        "environment": "staging",
        "fixture_id": fixture_id,
        "settled_side": "shadow_pick",
        "settlement_outcome": "WIN",
        "final_score": {"home": 1, "away": 0, "status": "FT"},
    }


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows),
        encoding="utf-8",
    )
