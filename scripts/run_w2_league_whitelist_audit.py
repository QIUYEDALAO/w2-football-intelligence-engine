from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from w2.competitions.league_whitelist_audit import (
    AUDIT_ENDPOINT_ALLOWLIST,
    build_hard_cap_blocked_result,
    build_not_audited_result,
    build_provider_execution_not_implemented_result,
    build_provider_key_missing_result,
    build_skipped_provider_not_approved_result,
    planned_provider_calls_by_endpoint,
    planned_provider_calls_for_audit,
    write_audit_report,
)
from w2.competitions.registry import CompetitionRegistry, CompetitionRegistryEntry

ROOT = Path(__file__).resolve().parents[1]
NATIONAL_LEAGUES_DIR = ROOT / "config/competitions/national_leagues"
SOURCE = "scripts.run_w2_league_whitelist_audit.v1"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build W2 national league whitelist audit plans without provider calls "
            "by default."
        ),
    )
    parser.add_argument("--group", default="")
    parser.add_argument("--competition-id", default="")
    parser.add_argument("--env", default="staging", dest="environment")
    parser.add_argument("--dry-run", action="store_true", default=False)
    parser.add_argument("--execute-provider-audit", action="store_true", default=False)
    parser.add_argument("--approved-provider-calls", action="store_true", default=False)
    parser.add_argument("--max-provider-calls", type=int, default=20)
    parser.add_argument("--out-dir")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    payload = build_cli_payload(
        group=args.group,
        competition_id=args.competition_id,
        environment=args.environment,
        execute_provider_audit=args.execute_provider_audit,
        approved_provider_calls=args.approved_provider_calls,
        max_provider_calls=args.max_provider_calls,
        out_dir=Path(args.out_dir) if args.out_dir else None,
    )
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def build_cli_payload(
    *,
    group: str = "",
    competition_id: str = "",
    environment: str = "staging",
    execute_provider_audit: bool = False,
    approved_provider_calls: bool = False,
    max_provider_calls: int = 20,
    out_dir: Path | None = None,
) -> dict[str, Any]:
    registry = CompetitionRegistry()
    entries = _selected_entries(registry, group=group, competition_id=competition_id)
    single_league_planned_calls = planned_provider_calls_by_endpoint()
    planned_calls = planned_provider_calls_for_audit() * len(entries)
    planned_calls_by_endpoint = {
        endpoint: calls * len(entries)
        for endpoint, calls in single_league_planned_calls.items()
    }
    if execute_provider_audit and planned_calls > max_provider_calls:
        results = [
            build_hard_cap_blocked_result(
                entry,
                environment=environment,
                hard_cap=max_provider_calls,
                planned_provider_calls=planned_calls,
            )
            for entry in entries
        ]
        status = "BLOCKED_BY_HARD_CAP"
    elif execute_provider_audit and not approved_provider_calls:
        results = [
            build_skipped_provider_not_approved_result(
                entry,
                environment=environment,
                hard_cap=max_provider_calls,
            )
            for entry in entries
        ]
        status = "NEED_USER_APPROVAL"
    elif execute_provider_audit and "W2_API_FOOTBALL_API_KEY" not in os.environ:
        results = [
            build_provider_key_missing_result(
                entry,
                environment=environment,
                hard_cap=max_provider_calls,
            )
            for entry in entries
        ]
        status = "PROVIDER_KEY_MISSING"
    elif execute_provider_audit:
        results = [
            build_provider_execution_not_implemented_result(
                entry,
                environment=environment,
                hard_cap=max_provider_calls,
            )
            for entry in entries
        ]
        status = "PROVIDER_EXECUTION_NOT_IMPLEMENTED_IN_OFFLINE_HARNESS"
    else:
        results = [
            build_not_audited_result(
                entry,
                environment=environment,
                hard_cap=max_provider_calls,
            )
            for entry in entries
        ]
        status = "DRY_RUN_READY"
    result_payloads = [result.as_dict() for result in results]
    report_paths: list[str] = []
    if out_dir is not None:
        for result in results:
            path = out_dir / f"W2_WHITELIST_AUDIT_{result.competition_id}.json"
            write_audit_report(path, result)
            report_paths.append(str(path))
    return {
        "status": status,
        "group": group or None,
        "competition_id": competition_id or None,
        "environment": environment,
        "source": SOURCE,
        "endpoint_allowlist": list(AUDIT_ENDPOINT_ALLOWLIST),
        "competition_count": len(entries),
        "results": result_payloads,
        "planned_provider_calls": planned_calls,
        "planned_provider_calls_by_endpoint": planned_calls_by_endpoint,
        "actual_provider_calls": 0,
        "provider_calls": 0,
        "db_reads": 0,
        "db_writes": 0,
        "checkpoint_write": False,
        "provider_call_approval_required": status in {
            "NEED_USER_APPROVAL",
            "PROVIDER_KEY_MISSING",
            "BLOCKED_BY_HARD_CAP",
            "DRY_RUN_READY",
            "PROVIDER_EXECUTION_NOT_IMPLEMENTED_IN_OFFLINE_HARNESS",
        },
        "message": _message(status),
        "report_paths": report_paths,
    }


def _selected_entries(
    registry: CompetitionRegistry,
    *,
    group: str,
    competition_id: str,
) -> list[CompetitionRegistryEntry]:
    entries = registry.entries()
    if competition_id:
        entry = entries.get(competition_id)
        if entry is None:
            raise SystemExit(f"COMPETITION_NOT_REGISTERED:{competition_id}")
        return [entry]
    if group and group != "national_leagues":
        raise SystemExit(f"UNSUPPORTED_GROUP:{group}")
    return [
        entry
        for entry in entries.values()
        if _is_under(entry.config_path, NATIONAL_LEAGUES_DIR)
    ]


def _is_under(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _message(status: str) -> str:
    if status == "NEED_USER_APPROVAL":
        return "NEED_USER_APPROVAL: LEAGUE_WHITELIST_PROVIDER_AUDIT"
    if status == "PROVIDER_KEY_MISSING":
        return "PROVIDER_KEY_MISSING"
    if status == "BLOCKED_BY_HARD_CAP":
        return "BLOCKED_BY_HARD_CAP"
    if status == "PROVIDER_EXECUTION_NOT_IMPLEMENTED_IN_OFFLINE_HARNESS":
        return "PROVIDER_EXECUTION_NOT_IMPLEMENTED_IN_OFFLINE_HARNESS"
    return "offline dry-run; provider audit not executed"


if __name__ == "__main__":
    sys.exit(main())
