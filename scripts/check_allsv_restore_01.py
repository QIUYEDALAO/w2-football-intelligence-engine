from __future__ import annotations

import argparse
import json
from pathlib import Path

from w2.competitions.seed import _hash as stable_hash

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "docs/review_packages/ALLSV_RESTORE_01"
DEFAULT_EVIDENCE = PACKAGE / "ALLSV_RESTORE_01_EVIDENCE_20260824.json"


def check(evidence_path: Path) -> None:
    evidence = json.loads(evidence_path.read_text())
    claimed_hash = evidence.pop("evidence_sha256")
    assert claimed_hash == stable_hash(evidence), "EVIDENCE_SHA256_MISMATCH"
    assert evidence["task_id"] == "ALLSV-RESTORE-01"
    assert evidence["scope"]["approved_restore"] == "allsvenskan"
    assert evidence["scope"]["must_remain_disabled"] == "chinese_super_league"
    assert evidence["constraints_observed"] == {
        "provider_calls": 0,
        "production_database_writes": 0,
        "deployments": 0,
        "outcome_reads": 0,
    }
    health = evidence["current_30d_health"]
    assert health["finished_fixtures"] == 16
    assert health["covered_fixtures"] == 2
    assert health["coverage_percent"] == 12.5
    assert health["required_coverage_percent"] == 70.0
    assert health["gate"] == "FAIL_BACKFILL_REQUIRED"
    plans = evidence["checkpoint_plans"]
    assert plans["unexpired_exact_blocker"] == 1296
    assert plans["expired_exact_blocker"] == 28
    assert plans["unexpired_plan_set_sha256"] == (
        "8998f5e00892a178ff29e3bbc9926267a616a5adaea1d73ce38c22f210bfd7de"
    )
    assert evidence["ordered_gates"]["sched_dedup_01_capacity_evidence"] == "PENDING"
    assert evidence["ordered_gates"]["decision_c_enable_and_exact_reopen"] == "BLOCKED"
    assert evidence["performance_scope"]["ev_gap_retest_status"] == (
        "REQUIRED_AFTER_RESTORE_NOT_YET_RUN"
    )

    recovery_source = (ROOT / "scripts/reenable_competition_after_xg_recovery.py").read_text()
    for required in (
        'APPROVED_COMPETITION_ID = "allsvenskan"',
        'PROTECTED_DISABLED_COMPETITION_ID = "chinese_super_league"',
        "list(row.blockers or []) == [DISABLED_BLOCKER]",
        'raise ValueError("REOPEN_PLAN_SET_DRIFT")',
        '"reopened_plan_ids": plan_ids',
    ):
        assert required in recovery_source, f"RECOVERY_CONTRACT_MISSING:{required}"

    refresh_source = (ROOT / "ops/host/w2-xg-refresh").read_text()
    assert "FROM league_season s" in refresh_source
    assert "JOIN league_profile p" in refresh_source
    assert "(s.payload->>'enabled')::boolean IS TRUE" in refresh_source
    assert "s.season = p.payload->>'current_season'" in refresh_source
    assert "chinese_super_league allsvenskan" not in refresh_source

    for filename in (
        "ALLSV_RESTORE_01_GATE.md",
        "DECISION_A_DEPLOY_FOUNDATION.md",
        "DECISION_B_CONTROLLED_BACKFILL.md",
        "DECISION_C_ENABLE_AND_REOPEN.md",
    ):
        assert (PACKAGE / filename).is_file(), f"MISSING_PACKAGE_FILE:{filename}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--check", action="store_true", required=True)
    args = parser.parse_args()
    check(args.evidence)
    print(json.dumps({"status": "PASS", "evidence": str(args.evidence)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
