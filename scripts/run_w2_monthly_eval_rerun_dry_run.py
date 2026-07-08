from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_w2_direction_allowed_prereg import build_prereg_report  # noqa: E402
from run_w2_r1_1_checkpoint_dry_run import (  # noqa: E402
    DEFAULT_ENVIRONMENT,
    DEFAULT_MIN_DOUBLE_SNAPSHOT_CARDS,
    DEFAULT_RUNTIME_ROOT,
    build_checkpoint_report,
)

REQUIRED_INPUTS = {
    "market_baseline_eval_script": Path("scripts/run_w2_market_baseline_eval.py"),
    "r1_1_checkpoint_script": Path("scripts/run_w2_r1_1_checkpoint_dry_run.py"),
    "direction_allowed_gate_script": Path("scripts/check_w2_direction_allowed_prereg.py"),
    "task_acceptance_ledger": Path("docs/consolidation/W2_TASK_ACCEPTANCE_LEDGER.md"),
    "market_baseline_eval_report": Path(
        "docs/consolidation/W2_MARKET_BASELINE_EVAL_2026_07.md"
    ),
    "r4_1_gap_reduction_report": Path(
        "docs/consolidation/W2_R4_1_MODEL_GAP_REDUCTION_EVAL_20260708.md"
    ),
}

OPTIONAL_INPUTS = {
    "runtime_forward_ledger": Path("runtime/forward_outcome_ledger"),
    "runtime_market_baseline_model_report": Path(
        "runtime/market_baseline_eval/model_phase_report.json"
    ),
    "runtime_market_baseline_market_report": Path(
        "runtime/market_baseline_eval/market_phase_report.json"
    ),
    "runtime_market_baseline_summary": Path(
        "runtime/market_baseline_eval/W2_MARKET_BASELINE_SUMMARY.md"
    ),
    "runtime_football_data_dir": Path("runtime/market_baseline_eval/football_data"),
    "runtime_r4_1_artifact_dir": Path("runtime/model_artifacts/r4_1"),
}


def build_monthly_eval_rerun_report(
    *,
    repo_root: Path = ROOT,
    runtime_root: Path = DEFAULT_RUNTIME_ROOT,
    eval_month: str | None = None,
    environment: str = DEFAULT_ENVIRONMENT,
    min_double_snapshot_cards: int = DEFAULT_MIN_DOUBLE_SNAPSHOT_CARDS,
) -> dict[str, Any]:
    resolved_month = eval_month or datetime.now(UTC).strftime("%Y-%m")
    available_inputs, missing_inputs = _input_status(repo_root)
    missing_required = [
        item["name"] for item in missing_inputs if item.get("required") is True
    ]
    checkpoint = build_checkpoint_report(
        repo_root / runtime_root,
        environment=environment,
        min_double_snapshot_cards=min_double_snapshot_cards,
    )
    prereg = build_prereg_report(
        ledger_path=repo_root / REQUIRED_INPUTS["task_acceptance_ledger"],
        runtime_root=repo_root / runtime_root,
        environment=environment,
        min_double_snapshot_cards=min_double_snapshot_cards,
    )
    readiness_status, blockers = _readiness_status(
        missing_required=missing_required,
        checkpoint_status=str(checkpoint.get("readiness_status") or ""),
        checkpoint_blockers=checkpoint.get("blockers"),
        prereg_blockers=prereg.get("blockers"),
    )
    sample_status = _sample_status(checkpoint)
    return {
        "eval_month": resolved_month,
        "environment": environment,
        "available_inputs": available_inputs,
        "missing_inputs": missing_inputs,
        "runnable_evals": _runnable_evals(missing_required, repo_root),
        "skipped_evals": _skipped_evals(),
        "sample_status": sample_status,
        "shadow_clv_status": {
            "status": sample_status["status"],
            "sample_count": checkpoint.get("clv_shadow_sample_count"),
            "median": checkpoint.get("clv_shadow_median"),
            "entry_window_met_rate": checkpoint.get("entry_window_met_rate"),
        },
        "market_gap_status": _market_gap_status(repo_root),
        "r4_1_artifact_status": _r4_1_artifact_status(repo_root),
        "direction_allowed_gate_status": {
            "release_decision": prereg.get("release_decision"),
            "candidate_order": prereg.get("candidate_order"),
            "disabled_leagues": prereg.get("disabled_leagues"),
            "blockers": prereg.get("blockers"),
            "direction_allowed_changes": prereg.get("direction_allowed_changes"),
        },
        "readiness_status": readiness_status,
        "blockers": blockers,
        "provider_calls": 0,
        "db_reads": 0,
        "db_writes": 0,
        "staging_deploy": False,
        "production_deploy": False,
        "scheduler_restart": False,
        "direction_allowed_changes": [],
        "formal_decision": "NOT_EVALUATED",
        "runtime_writes": 0,
    }


def _input_status(repo_root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    available: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    for name, path in REQUIRED_INPUTS.items():
        item = {
            "name": name,
            "path": str(path),
            "required": True,
            "will_write": False,
        }
        if (repo_root / path).exists():
            available.append(item)
        else:
            missing.append({**item, "reason": "REQUIRED_INPUT_MISSING"})
    for name, path in OPTIONAL_INPUTS.items():
        item = {
            "name": name,
            "path": str(path),
            "required": False,
            "will_write": False,
        }
        if (repo_root / path).exists():
            available.append(item)
        else:
            missing.append({**item, "reason": "OPTIONAL_INPUT_MISSING"})
    return available, missing


def _readiness_status(
    *,
    missing_required: list[str],
    checkpoint_status: str,
    checkpoint_blockers: Any,
    prereg_blockers: Any,
) -> tuple[str, list[str]]:
    blockers: list[str] = []
    if missing_required:
        blockers.extend(f"MISSING_REQUIRED_INPUT:{name}" for name in missing_required)
        return ("BLOCKED", blockers)
    checkpoint_blocker_values = _string_list(checkpoint_blockers)
    prereg_blocker_values = _string_list(prereg_blockers)
    blockers.extend(checkpoint_blocker_values)
    blockers.extend(prereg_blocker_values)
    if checkpoint_status == "ACCUMULATING" or "R1_1_ACCUMULATING" in prereg_blocker_values:
        return ("ACCUMULATING", blockers)
    if (
        checkpoint_status == "NOT_ENOUGH_SAMPLE"
        or "R1_1_NOT_ENOUGH_SAMPLE" in prereg_blocker_values
    ):
        return ("NOT_ENOUGH_SAMPLE", blockers)
    if blockers:
        return ("BLOCKED", blockers)
    return ("READY", [])


def _sample_status(checkpoint: dict[str, Any]) -> dict[str, Any]:
    status = str(checkpoint.get("readiness_status") or "ACCUMULATING")
    return {
        "status": status,
        "double_snapshot_card_count": checkpoint.get("double_snapshot_card_count"),
        "shadow_nonempty_rate": checkpoint.get("shadow_nonempty_rate"),
        "clv_shadow_sample_count": checkpoint.get("clv_shadow_sample_count"),
        "clv_shadow_median": checkpoint.get("clv_shadow_median"),
        "outcome_count_ft": checkpoint.get("outcome_count_ft"),
        "outcome_count_aet": checkpoint.get("outcome_count_aet"),
        "outcome_count_pen": checkpoint.get("outcome_count_pen"),
        "note": (
            "No settlement samples are ACCUMULATING, not a numeric conclusion."
            if status == "ACCUMULATING"
            else "Sample status is read-only."
        ),
    }


def _runnable_evals(missing_required: list[str], repo_root: Path) -> list[dict[str, Any]]:
    if missing_required:
        return []
    market_phase_ready = (
        repo_root / OPTIONAL_INPUTS["runtime_football_data_dir"]
    ).exists()
    return [
        {
            "id": "r1_1_checkpoint_dry_run",
            "status": "READY",
            "will_write": False,
            "provider_calls": 0,
            "db_writes": 0,
        },
        {
            "id": "direction_allowed_prereg_gate",
            "status": "READY",
            "will_write": False,
            "provider_calls": 0,
            "db_writes": 0,
        },
        {
            "id": "market_baseline_eval_model_phase",
            "status": "READY_FOR_MANUAL_RUN"
            if (repo_root / REQUIRED_INPUTS["market_baseline_eval_script"]).exists()
            else "BLOCKED",
            "will_write": True,
            "write_target": "runtime/market_baseline_eval/",
            "provider_calls": 0,
            "db_writes": 0,
        },
        {
            "id": "market_baseline_eval_market_phase",
            "status": "READY_FOR_MANUAL_RUN" if market_phase_ready else "BLOCKED",
            "will_write": True,
            "write_target": "runtime/market_baseline_eval/",
            "provider_calls": 0,
            "db_writes": 0,
        },
    ]


def _skipped_evals() -> list[dict[str, Any]]:
    return [
        {
            "id": "formal_monthly_eval_execution",
            "status": "SKIPPED",
            "reason": "dry-run only; formal eval would write runtime outputs",
        },
        {
            "id": "r3_0_ev_recommend_decision",
            "status": "SKIPPED",
            "reason": "not enough forward evidence and no EV/RECOMMEND release in this PR",
        },
        {
            "id": "direction_allowed_release",
            "status": "SKIPPED",
            "reason": "prereg gate is review-only; release requires later approved PR",
        },
    ]


def _market_gap_status(repo_root: Path) -> dict[str, Any]:
    docs_present = [
        str(path)
        for path in (
            REQUIRED_INPUTS["market_baseline_eval_report"],
            REQUIRED_INPUTS["r4_1_gap_reduction_report"],
        )
        if (repo_root / path).exists()
    ]
    runtime_reports = [
        str(path)
        for path in (
            OPTIONAL_INPUTS["runtime_market_baseline_model_report"],
            OPTIONAL_INPUTS["runtime_market_baseline_market_report"],
            OPTIONAL_INPUTS["runtime_market_baseline_summary"],
        )
        if (repo_root / path).exists()
    ]
    return {
        "status": "AVAILABLE" if docs_present else "BLOCKED",
        "doc_reports": docs_present,
        "runtime_reports": runtime_reports,
        "candidate_gaps": {
            "eliteserien": 0.0164,
            "allsvenskan": 0.0188,
            "chinese_super_league": 0.0354,
            "brasileirao_serie_a": ">0.04_DISABLED",
        },
        "provider_calls": 0,
        "db_writes": 0,
    }


def _r4_1_artifact_status(repo_root: Path) -> dict[str, Any]:
    artifact_dir = repo_root / OPTIONAL_INPUTS["runtime_r4_1_artifact_dir"]
    expected = {
        "allsvenskan.v1.json",
        "bundesliga.v1.json",
        "chinese_super_league.v1.json",
    }
    files = {path.name for path in artifact_dir.glob("*.json")} if artifact_dir.exists() else set()
    missing = sorted(expected - files)
    return {
        "status": "AVAILABLE" if not missing else "MISSING_RUNTIME_ARTIFACTS",
        "artifact_dir": str(OPTIONAL_INPUTS["runtime_r4_1_artifact_dir"]),
        "expected_files": sorted(expected),
        "present_files": sorted(files),
        "missing_files": missing,
        "runtime_artifacts_committed": False,
    }


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only monthly W2 eval rerun readiness dry-run."
    )
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME_ROOT)
    parser.add_argument("--eval-month")
    parser.add_argument("--environment", default=DEFAULT_ENVIRONMENT)
    parser.add_argument(
        "--min-double-snapshot-cards",
        type=int,
        default=DEFAULT_MIN_DOUBLE_SNAPSHOT_CARDS,
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    payload = build_monthly_eval_rerun_report(
        repo_root=args.repo_root,
        runtime_root=args.runtime_root,
        eval_month=args.eval_month,
        environment=args.environment,
        min_double_snapshot_cards=args.min_double_snapshot_cards,
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(
            "status={status} runnable={runnable} missing={missing}".format(
                status=payload["readiness_status"],
                runnable=len(payload["runnable_evals"]),
                missing=len(payload["missing_inputs"]),
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
