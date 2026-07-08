from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.run_w2_monthly_eval_rerun_dry_run import build_monthly_eval_rerun_report


def test_monthly_eval_no_samples_accumulates(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    payload = build_monthly_eval_rerun_report(repo_root=repo, runtime_root=Path("runtime"))

    assert payload["readiness_status"] == "ACCUMULATING"
    assert payload["sample_status"]["status"] == "ACCUMULATING"
    assert payload["shadow_clv_status"]["median"] == "ACCUMULATING"
    assert payload["direction_allowed_gate_status"]["release_decision"] == "REVIEW_ONLY"
    assert payload["provider_calls"] == 0
    assert payload["db_writes"] == 0


def test_monthly_eval_insufficient_sample_is_not_enough_sample(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    ledger = repo / "runtime" / "forward_outcome_ledger"
    ledger.mkdir(parents=True)
    _write_jsonl(
        ledger / "2026-07-07_staging.jsonl",
        [
            _capture("fixture-1", "2026-07-07T00:00:00Z", "1.90"),
            _capture("fixture-1", "2026-07-07T23:00:00Z", "1.80"),
            _outcome("fixture-1"),
        ],
    )

    payload = build_monthly_eval_rerun_report(
        repo_root=repo,
        runtime_root=Path("runtime"),
        min_double_snapshot_cards=2,
    )

    assert payload["readiness_status"] == "NOT_ENOUGH_SAMPLE"
    assert payload["sample_status"]["double_snapshot_card_count"] == 1
    assert payload["shadow_clv_status"]["sample_count"] == 1


def test_monthly_eval_missing_required_input_blocks(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "scripts" / "run_w2_market_baseline_eval.py").unlink()

    payload = build_monthly_eval_rerun_report(repo_root=repo, runtime_root=Path("runtime"))

    assert payload["readiness_status"] == "BLOCKED"
    assert "MISSING_REQUIRED_INPUT:market_baseline_eval_script" in payload["blockers"]
    assert payload["runnable_evals"] == []


def test_monthly_eval_output_includes_r1_1_and_gate_status(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    payload = build_monthly_eval_rerun_report(repo_root=repo, runtime_root=Path("runtime"))

    assert "double_snapshot_card_count" in payload["sample_status"]
    assert "direction_allowed_gate_status" in payload
    assert payload["direction_allowed_changes"] == []
    assert payload["direction_allowed_gate_status"]["candidate_order"] == [
        "eliteserien",
        "allsvenskan",
        "chinese_super_league",
    ]


def test_monthly_eval_cli_json_has_zero_side_effect_flags(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_w2_monthly_eval_rerun_dry_run.py",
            "--repo-root",
            str(repo),
            "--runtime-root",
            "runtime",
            "--json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload["provider_calls"] == 0
    assert payload["db_reads"] == 0
    assert payload["db_writes"] == 0
    assert payload["staging_deploy"] is False
    assert payload["production_deploy"] is False
    assert payload["scheduler_restart"] is False


def test_monthly_eval_has_no_stage16_surface(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    payload = build_monthly_eval_rerun_report(repo_root=repo, runtime_root=Path("runtime"))

    serialized = json.dumps(payload, ensure_ascii=False)
    assert "Stage 16" not in serialized
    assert "stage16" not in serialized.lower()


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    for directory in (
        "scripts",
        "docs/consolidation",
        "runtime/market_baseline_eval/football_data",
        "runtime/model_artifacts/r4_1",
    ):
        (repo / directory).mkdir(parents=True, exist_ok=True)
    for path in (
        "scripts/run_w2_market_baseline_eval.py",
        "scripts/run_w2_r1_1_checkpoint_dry_run.py",
        "scripts/check_w2_direction_allowed_prereg.py",
        "docs/consolidation/W2_MARKET_BASELINE_EVAL_2026_07.md",
        "docs/consolidation/W2_R4_1_MODEL_GAP_REDUCTION_EVAL_20260708.md",
    ):
        (repo / path).write_text("placeholder", encoding="utf-8")
    (repo / "docs/consolidation/W2_TASK_ACCEPTANCE_LEDGER.md").write_text(
        (
            "预注册规则日期:2026-07-08。未来按联赛放行 `direction_allowed` "
            "必须单独批准 PR,且满足 shadow CLV 样本 `>=100`、shadow CLV "
            "中位数 `>0`、最新 market gap `<=0.04`;离线数字和 shadow 方向"
            "不得直接开 EV/RECOMMEND 腿。"
        ),
        encoding="utf-8",
    )
    for filename in (
        "allsvenskan.v1.json",
        "bundesliga.v1.json",
        "chinese_super_league.v1.json",
    ):
        (repo / "runtime/model_artifacts/r4_1" / filename).write_text(
            "{}",
            encoding="utf-8",
        )
    return repo


def _capture(fixture_id: str, captured_at: str, home_price: str) -> dict[str, object]:
    return {
        "schema_version": "w2.forward_outcome_ledger.v2",
        "record_type": "capture",
        "captured_at": captured_at,
        "football_day": "2026-07-07",
        "environment": "staging",
        "fixture_id": fixture_id,
        "kickoff_utc": "2026-07-08T02:00:00Z",
        "competition_id": "eliteserien",
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
