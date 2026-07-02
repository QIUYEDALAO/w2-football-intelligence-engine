#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "src/w2/migration/foundation.py",
    "src/w2/migration/shadow.py",
    "src/w2/infrastructure/persistence/migration_models.py",
    "migrations/versions/0013_create_stage12a_migration_shadow.py",
    "docs/adr/ADR-0015-w1-migration-shadow-foundation.md",
    "docs/migration/W1_TO_W2_MAPPING_V1.md",
    "docs/migration/W1_MIGRATION_VALIDATION_POLICY_V1.md",
    "docs/shadow/W2_SHADOW_COMPARISON_V1.md",
    "docs/runbooks/W1_MIGRATION_APPROVAL_CHECKPOINT.md",
    "scripts/run_stage12a_migration_dry_run.py",
    "scripts/run_stage12a_shadow_dry_run.py",
    "scripts/check_w2_stage12a.py",
]
REPORT_ARTIFACTS = [
    "reports/W2_STAGE12A_SOURCE_INVENTORY.json",
    "reports/W2_STAGE12A_MIGRATION_DRY_RUN.json",
    "reports/W2_STAGE12A_QUARANTINE.json",
    "reports/W2_STAGE12A_SHADOW_COMPARISON.json",
    "reports/W2_STAGE12A_W1_READONLY_AUDIT.txt",
    "reports/W2_STAGE12A_RESULT.md",
]


def fail(message: str) -> None:
    print(f"W2 Stage12A check FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def load(path: str) -> object:
    return json.loads(read(path))


def main() -> int:
    for path in REQUIRED:
        if not (ROOT / path).is_file():
            fail(f"missing {path}")
    combined = "\n".join(read(path) for path in REQUIRED if path.endswith((".py", ".md")))
    for token in [
        "MigrationDecision",
        "READY_FOR_TRANSFORM",
        "AUDIT_ONLY",
        "QUARANTINE",
        "MANUAL_REVIEW_REQUIRED",
        "TransformContract",
        "MigrationDryRunEngine",
        "ShadowComparisonEngine",
        "W1SnapshotAdapter",
        "W2SnapshotAdapter",
        "migration_source_asset",
        "migration_dry_run",
        "shadow_comparison_record",
        "NOT_AVAILABLE_GATE4",
    ]:
        if token not in combined:
            fail(f"missing token {token}")
    if all((ROOT / path).is_file() for path in REPORT_ARTIFACTS):
        inventory = load("reports/W2_STAGE12A_SOURCE_INVENTORY.json")
        dry_run = load("reports/W2_STAGE12A_MIGRATION_DRY_RUN.json")
        quarantine = load("reports/W2_STAGE12A_QUARANTINE.json")
        shadow = load("reports/W2_STAGE12A_SHADOW_COMPARISON.json")
        result = read("reports/W2_STAGE12A_RESULT.md")
        domains = {item["domain"] for item in inventory["assets"]}  # type: ignore[index]
        required_domains = {
            "competition_season_fixture",
            "team_player_provider_mapping",
            "raw_odds_payload",
            "bookmaker_odds_snapshots",
            "match_cards",
            "lineups_injuries",
            "weather_venue",
            "results",
            "forward_ledger",
            "w1_model_outputs",
            "w1_ai_scout_outputs",
            "recommendation_audit_records",
        }
        if domains != required_domains:
            fail("source inventory domain coverage mismatch")
        if inventory["full_dataset_copied"] or inventory["w1_runtime_imported"]:  # type: ignore[index]
            fail("inventory must not copy full data or import W1 runtime")
        if dry_run["temporary_load_touched_w2_database"]:  # type: ignore[index]
            fail("dry-run must not touch W2 production database")
        if dry_run["w1_writes"] or dry_run["business_data_copy_retained"]:  # type: ignore[index]
            fail("dry-run must not write W1 or retain business copies")
        if len(dry_run["results"]) != len(required_domains):  # type: ignore[index]
            fail("dry-run must include every domain")
        if quarantine["silent_drop_allowed"]:  # type: ignore[index]
            fail("silent drops must be forbidden")
        if shadow["manifest"]["strategy_comparison_status"] != "NOT_AVAILABLE_GATE4":  # type: ignore[index]
            fail("strategy comparison must be blocked by Gate 4")
        if shadow["network_used"] or shadow["real_prediction_run"]:  # type: ignore[index]
            fail("shadow dry-run must stay offline and non-runtime")
        for token in [
            "STAGE_12A=COMPLETED",
            "STAGE_12=PROVISIONAL",
            "W1_DATA_MIGRATION_EXECUTION=DISABLED_PENDING_APPROVAL",
            "SHADOW_FOUNDATION=READY",
            "SHADOW_RUNTIME=DISABLED_PENDING_GATE4",
            "PRODUCTION_SWITCH=DISABLED",
            "GATE_4_NATIONAL_1X2=PROVISIONAL_FORWARD_HOLDOUT_PENDING",
            "STAGE_9=BLOCKED",
            "PUSH_BLOCKED_NO_ORIGIN",
        ]:
            if token not in result:
                fail(f"missing status {token}")
    print("W2 Stage12A check PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
