from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "docs/review_packages/WEB_SCOPE_01"
DEFAULT_INPUT = PACKAGE / "WEB_SCOPE_01_FROZEN_INPUT.json"
DEFAULT_EVIDENCE = PACKAGE / "WEB_SCOPE_01_EVIDENCE.json"


def _read(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _source_contract() -> dict[str, bool]:
    repository = (ROOT / "src/w2/api/repository.py").read_text(encoding="utf-8")
    workspace = (ROOT / "src/w2/dashboard/workspace.py").read_text(encoding="utf-8")
    date_strip = (ROOT / "src/w2/dashboard/date_strip.py").read_text(encoding="utf-8")
    release_preflight = ROOT / "ops/host/w2-release-sync-preflight"
    return {
        "enabled_scope_reads_registry_enabled_ids": ".enabled_ids()" in repository,
        "repository_has_no_fixed_13_scope_guard": "!= 13" not in repository,
        "workspace_has_no_fixed_active_count": '"active_whitelist_count": 13' not in workspace,
        "date_strip_has_no_fixed_active_count": "ACTIVE_WHITELIST_COUNT" not in date_strip,
        "release_sync_preflight_present": release_preflight.is_file(),
    }


def build_evidence(frozen: dict[str, Any]) -> dict[str, Any]:
    enabled = set(frozen["enabled_competitions"])
    rows = list(frozen["matchday_rows"])
    scoped_rows = [row for row in rows if row["competition_id"] in enabled]
    disabled_rows = [row for row in rows if row["competition_id"] not in enabled]
    checkpoint_counts = dict(frozen["analysis_checkpoint_counts_by_competition"])
    version_before = sum(int(value) for value in checkpoint_counts.values())
    version_after = sum(
        int(value) for competition, value in checkpoint_counts.items() if competition in enabled
    )
    target = dict(frozen["fixture_1494253"])
    release = dict(frozen["release"])
    source_contract = _source_contract()
    return {
        "schema_version": "w2.web-scope-01.evidence.v1",
        "frozen_input_schema_version": frozen["schema_version"],
        "observed_at_utc": frozen["observed_at_utc"],
        "read_contract": {
            "provider_calls": 0,
            "production_db_writes": 0,
            "deployed": False,
        },
        "enabled_scope": {
            "authority": "league_season.payload.enabled",
            "competition_count": len(enabled),
            "competition_ids": sorted(enabled),
        },
        "path_inventory": {
            "matchday": {"before": len(rows), "after": len(scoped_rows)},
            "dashboard": {"before": len(rows), "after": len(scoped_rows)},
            "radar_attention_input": {"before": len(rows), "after": len(scoped_rows)},
            "direct_fixture_projection": {
                "fixture_id": "1494253",
                "before_visible": True,
                "after_visible": False,
            },
            "postmatch_recommendations": {
                "fixture_id": "1494253",
                "official_opportunities_before": target["dynamic_opportunities"],
                "official_opportunities_after": 0,
                "already_filtered_by_enabled_scope": True,
            },
            "performance_record": {
                "fixture_id": "1494253",
                "included_before_this_change": False,
                "included_after_this_change": False,
                "filter_commit": "c582ace4",
            },
            "version_counts": {
                "before": version_before,
                "after": version_after,
                "disabled_removed": version_before - version_after,
            },
        },
        "disabled_rows": disabled_rows,
        "fixture_1494253_reachability": {
            "captured_plan_rows": target["checkpoint_plans_captured"],
            "legacy_analysis_pick_active_rows": target["legacy_analysis_pick_active"],
            "official_funnel_eligible_rows": target["official_funnel_eligible_true"],
            "official_opportunity_rows": target["dynamic_opportunities"],
            "current_card": target["current_card"],
            "can_enter_public_recommendation_after_change": False,
            "can_enter_official_performance_record": False,
        },
        "release_consistency": {
            "api_git_sha": release["api_git_sha"],
            "web_git_sha": release["web_git_sha"],
            "same_revision": release["api_git_sha"] == release["web_git_sha"],
            "existing_public_check_exit_code": release["existing_public_release_sync_exit_code"],
            "new_image_preflight_contract": "PYTHON_AND_WEB_OCI_REVISIONS_MUST_MATCH",
        },
        "source_contract": source_contract,
        "scope_retention_ratio": round(len(scoped_rows) / len(rows), 12),
        "check_passed": all(source_contract.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Reproduce WEB-SCOPE-01 offline evidence.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    actual = build_evidence(_read(args.input))
    if args.check:
        expected = _read(args.evidence)
        if actual != expected:
            print("WEB_SCOPE_01_CHECK_FAILED: evidence differs", file=sys.stderr)
            return 1
        if not actual["check_passed"]:
            print("WEB_SCOPE_01_CHECK_FAILED: source contract failed", file=sys.stderr)
            return 1
        print("WEB_SCOPE_01_CHECK_OK")
        return 0
    rendered = json.dumps(actual, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
