from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from collections.abc import Callable
from datetime import UTC, datetime
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
from w2.competitions.league_whitelist_provider_audit import (
    IN_SEASON_NATIONAL_LEAGUES,
    LEAGUE_PROVIDER_HARD_CAPS,
    STOP_STATUSES,
    ApiFootballLeagueAuditProvider,
    ApiFootballRequester,
    LocalProviderAuditLedger,
    ProviderAuditBudget,
    evaluate_controlled_provider_league_audit,
    write_provider_audit_outputs,
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
    parser.add_argument("--real-provider-audit", action="store_true", default=False)
    parser.add_argument("--approved-provider-calls", action="store_true", default=False)
    parser.add_argument("--max-provider-calls", type=int, default=20)
    parser.add_argument("--daily-hard-cap", type=int, default=90)
    parser.add_argument("--league-hard-cap", type=int)
    parser.add_argument("--request-interval-seconds", type=float, default=10.0)
    parser.add_argument("--out-dir")
    parser.add_argument("--audit-ledger-json")
    parser.add_argument("--resume-from-out-dir")
    parser.add_argument("--summarize-output-dir")
    parser.add_argument("--stop-on-first-quota-warning", action="store_true", default=True)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    if args.summarize_output_dir:
        payload = summarize_output_dir(Path(args.summarize_output_dir))
    else:
        payload = build_cli_payload(
            group=args.group,
            competition_id=args.competition_id,
            environment=args.environment,
            execute_provider_audit=args.execute_provider_audit,
            real_provider_audit=args.real_provider_audit,
            approved_provider_calls=args.approved_provider_calls,
            max_provider_calls=args.max_provider_calls,
            daily_hard_cap=args.daily_hard_cap,
            league_hard_cap=args.league_hard_cap,
            request_interval_seconds=args.request_interval_seconds,
            out_dir=Path(args.out_dir) if args.out_dir else None,
            audit_ledger_json=Path(args.audit_ledger_json) if args.audit_ledger_json else None,
            resume_from_out_dir=(
                Path(args.resume_from_out_dir) if args.resume_from_out_dir else None
            ),
            stop_on_first_quota_warning=args.stop_on_first_quota_warning,
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
    real_provider_audit: bool = False,
    approved_provider_calls: bool = False,
    max_provider_calls: int = 20,
    daily_hard_cap: int = 90,
    league_hard_cap: int | None = None,
    request_interval_seconds: float = 10.0,
    out_dir: Path | None = None,
    audit_ledger_json: Path | None = None,
    resume_from_out_dir: Path | None = None,
    stop_on_first_quota_warning: bool = True,
    requester_factory: Callable[[str], ApiFootballRequester] | None = None,
    sleeper: Callable[[float], None] | None = None,
) -> dict[str, Any]:
    registry = CompetitionRegistry()
    entries = _selected_entries(registry, group=group, competition_id=competition_id)
    single_league_planned_calls = planned_provider_calls_by_endpoint()
    planned_calls = planned_provider_calls_for_audit() * len(entries)
    planned_calls_by_endpoint = {
        endpoint: calls * len(entries)
        for endpoint, calls in single_league_planned_calls.items()
    }
    if real_provider_audit:
        return _build_real_provider_payload(
            entries=entries,
            group=group,
            competition_id=competition_id,
            environment=environment,
            approved_provider_calls=approved_provider_calls,
            max_provider_calls=max_provider_calls,
            daily_hard_cap=daily_hard_cap,
            league_hard_cap=league_hard_cap,
            request_interval_seconds=request_interval_seconds,
            out_dir=out_dir,
            audit_ledger_json=audit_ledger_json,
            resume_from_out_dir=resume_from_out_dir,
            stop_on_first_quota_warning=stop_on_first_quota_warning,
            planned_calls=planned_calls,
            planned_calls_by_endpoint=planned_calls_by_endpoint,
            requester_factory=requester_factory,
            sleeper=sleeper,
        )
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
    if group == "national_leagues_in_season":
        return [entries[item] for item in IN_SEASON_NATIONAL_LEAGUES]
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


def _build_real_provider_payload(
    *,
    entries: list[CompetitionRegistryEntry],
    group: str,
    competition_id: str,
    environment: str,
    approved_provider_calls: bool,
    max_provider_calls: int,
    daily_hard_cap: int,
    league_hard_cap: int | None,
    request_interval_seconds: float,
    out_dir: Path | None,
    audit_ledger_json: Path | None,
    resume_from_out_dir: Path | None,
    stop_on_first_quota_warning: bool,
    planned_calls: int,
    planned_calls_by_endpoint: dict[str, int],
    requester_factory: Callable[[str], ApiFootballRequester] | None,
    sleeper: Callable[[float], None] | None,
) -> dict[str, Any]:
    if not approved_provider_calls:
        results = [
            build_skipped_provider_not_approved_result(
                entry,
                environment=environment,
                hard_cap=_league_cap(entry, max_provider_calls, league_hard_cap),
            )
            for entry in entries
        ]
        return _payload(
            status="NEED_USER_APPROVAL",
            group=group,
            competition_id=competition_id,
            environment=environment,
            results=results,
            planned_calls=planned_calls,
            planned_calls_by_endpoint=planned_calls_by_endpoint,
            message="NEED_USER_APPROVAL: LEAGUE_WHITELIST_PROVIDER_AUDIT",
        )
    if "W2_API_FOOTBALL_API_KEY" not in os.environ:
        results = [
            build_provider_key_missing_result(
                entry,
                environment=environment,
                hard_cap=_league_cap(entry, max_provider_calls, league_hard_cap),
            )
            for entry in entries
        ]
        return _payload(
            status="PROVIDER_KEY_MISSING",
            group=group,
            competition_id=competition_id,
            environment=environment,
            results=results,
            planned_calls=planned_calls,
            planned_calls_by_endpoint=planned_calls_by_endpoint,
            message="PROVIDER_KEY_MISSING",
        )
    if planned_calls > daily_hard_cap:
        results = [
            build_hard_cap_blocked_result(
                entry,
                environment=environment,
                hard_cap=daily_hard_cap,
                planned_provider_calls=planned_calls,
            )
            for entry in entries
        ]
        return _payload(
            status="BLOCKED_BY_HARD_CAP",
            group=group,
            competition_id=competition_id,
            environment=environment,
            results=results,
            planned_calls=planned_calls,
            planned_calls_by_endpoint=planned_calls_by_endpoint,
            message="BLOCKED_BY_HARD_CAP",
        )
    resolved_out_dir = out_dir or _default_out_dir()
    if not _is_tmp_path(resolved_out_dir):
        raise SystemExit("BLOCKER: OUTPUT_DIR_MUST_BE_UNDER_TMP")
    if resume_from_out_dir is not None and not _is_tmp_path(resume_from_out_dir):
        raise SystemExit("BLOCKER: RESUME_FROM_OUT_DIR_MUST_BE_UNDER_TMP")
    resume_reports = _resume_reports(resume_from_out_dir)
    skipped_existing_reports: list[str] = []
    resolved_sleeper = _resolve_sleeper(
        requester_factory=requester_factory,
        sleeper=sleeper,
    )
    ledger = LocalProviderAuditLedger()
    budget = ProviderAuditBudget(daily_hard_cap=daily_hard_cap)
    results = []
    stopped_early = False
    stopped_reason: str | None = None
    for entry in entries:
        existing_report = resume_reports.get(entry.competition_id)
        if existing_report is not None and _is_completed_report(existing_report):
            skipped_existing_reports.append(str(existing_report["_path"]))
            continue
        cap = _league_cap(entry, max_provider_calls, league_hard_cap)
        provider = ApiFootballLeagueAuditProvider(
            competition_id=entry.competition_id,
            league_hard_cap=cap,
            budget=budget,
            ledger=ledger,
            requester=requester_factory(entry.competition_id) if requester_factory else None,
            request_interval_seconds=request_interval_seconds,
            sleeper=resolved_sleeper,
        )
        result = evaluate_controlled_provider_league_audit(
            entry,
            environment=environment,
            provider=provider,
        )
        results.append(result)
        if result.overall_status in STOP_STATUSES:
            stopped_early = True
            stopped_reason = result.overall_status
            if stop_on_first_quota_warning:
                break
        if budget.actual_provider_calls >= daily_hard_cap:
            stopped_early = True
            stopped_reason = "GLOBAL_PROVIDER_HARD_CAP_REACHED"
            break
    summary = write_provider_audit_outputs(
        out_dir=resolved_out_dir,
        results=results,
        ledger=ledger,
        status="PROVIDER_AUDIT_STOPPED_EARLY" if stopped_early else "PROVIDER_AUDIT_COMPLETED",
        stopped_early=stopped_early,
        stopped_reason=stopped_reason,
        skipped_existing_reports=skipped_existing_reports,
    )
    if audit_ledger_json is not None:
        if not _is_tmp_path(audit_ledger_json):
            raise SystemExit("BLOCKER: AUDIT_LEDGER_JSON_MUST_BE_UNDER_TMP")
        ledger.write_json(audit_ledger_json)
        summary["audit_ledger_json"] = str(audit_ledger_json)
    return _payload(
        status=summary["status"],
        group=group,
        competition_id=competition_id,
        environment=environment,
        results=results,
        planned_calls=planned_calls,
        planned_calls_by_endpoint=planned_calls_by_endpoint,
        message=summary["status"],
        actual_provider_calls=budget.actual_provider_calls,
        report_paths=summary["reports"],
        output_dir=summary["output_dir"],
        audit_ledger_json=summary["audit_ledger_json"],
        summary_json=summary["summary_json"],
        stopped_early=stopped_early,
        stopped_reason=stopped_reason,
        cooldown_recommended=stopped_reason == "PROVIDER_HTTP_429",
        local_ledger_records=len(ledger.records),
        skipped_existing_reports=skipped_existing_reports,
    )


def _payload(
    *,
    status: str,
    group: str,
    competition_id: str,
    environment: str,
    results: list[Any],
    planned_calls: int,
    planned_calls_by_endpoint: dict[str, int],
    message: str,
    actual_provider_calls: int = 0,
    report_paths: list[str] | None = None,
    output_dir: str | None = None,
    audit_ledger_json: str | None = None,
    summary_json: str | None = None,
    stopped_early: bool = False,
    stopped_reason: str | None = None,
    cooldown_recommended: bool = False,
    local_ledger_records: int = 0,
    skipped_existing_reports: list[str] | None = None,
) -> dict[str, Any]:
    result_payloads = [result.as_dict() for result in results]
    return {
        "status": status,
        "group": group or None,
        "competition_id": competition_id or None,
        "environment": environment,
        "source": SOURCE,
        "endpoint_allowlist": list(AUDIT_ENDPOINT_ALLOWLIST),
        "competition_count": len(results),
        "results": result_payloads,
        "planned_provider_calls": planned_calls,
        "planned_provider_calls_by_endpoint": planned_calls_by_endpoint,
        "actual_provider_calls": actual_provider_calls,
        "provider_calls": actual_provider_calls,
        "db_reads": 0,
        "db_writes": 0,
        "checkpoint_write": False,
        "provider_call_approval_required": status in {
            "NEED_USER_APPROVAL",
            "PROVIDER_KEY_MISSING",
            "BLOCKED_BY_HARD_CAP",
        },
        "message": message,
        "report_paths": report_paths or [],
        "output_dir": output_dir,
        "audit_ledger_json": audit_ledger_json,
        "summary_json": summary_json,
        "stopped_early": stopped_early,
        "stopped_reason": stopped_reason,
        "cooldown_recommended": cooldown_recommended,
        "local_ledger_records": local_ledger_records,
        "skipped_existing_reports": skipped_existing_reports or [],
    }


def _league_cap(
    entry: CompetitionRegistryEntry,
    max_provider_calls: int,
    league_hard_cap: int | None,
) -> int:
    if league_hard_cap is not None:
        return league_hard_cap
    if len(IN_SEASON_NATIONAL_LEAGUES) == 1:
        return max_provider_calls
    return LEAGUE_PROVIDER_HARD_CAPS.get(entry.competition_id, max_provider_calls)


def summarize_output_dir(out_dir: Path) -> dict[str, Any]:
    if not _is_tmp_path(out_dir):
        raise SystemExit("BLOCKER: SUMMARY_OUTPUT_DIR_MUST_BE_UNDER_TMP")
    reports = _resume_reports(out_dir)
    summary = _read_json(out_dir / "summary.json")
    ledger = _read_json(out_dir / "audit_ledger.json")
    ledger_records = ledger if isinstance(ledger, list) else []
    completed_leagues: list[str] = []
    partial_leagues: list[str] = []
    per_league: dict[str, dict[str, Any]] = {}
    blockers: list[str] = []
    warnings: list[str] = []
    season_review_required = False
    for competition_id in IN_SEASON_NATIONAL_LEAGUES:
        report = reports.get(competition_id)
        if report is None:
            continue
        status = _report_status(report)
        report_blockers = _list_of_strings(report.get("blockers"))
        report_warnings = _list_of_strings(report.get("warnings"))
        review_required = any("AUDIT_SEASON_FALLBACK" in item for item in report_warnings)
        season_review_required = season_review_required or review_required
        if _is_completed_report(report):
            completed_leagues.append(competition_id)
        else:
            partial_leagues.append(competition_id)
        blockers.extend(report_blockers)
        warnings.extend(report_warnings)
        per_league[competition_id] = {
            "overall_status": status,
            "can_enable": bool(report.get("can_enable")),
            "actual_provider_calls": _int(report.get("actual_provider_calls")),
            "items": _item_statuses(report),
            "blockers": report_blockers,
            "warnings": report_warnings,
            "provider_mapping_or_season_review_required": review_required,
        }
    unstarted_leagues = [
        competition_id
        for competition_id in IN_SEASON_NATIONAL_LEAGUES
        if competition_id not in reports
    ]
    stopped_reason = _text(summary.get("stopped_reason")) if isinstance(summary, dict) else ""
    actual_provider_calls_total = (
        _int(summary.get("actual_provider_calls_total"))
        if isinstance(summary, dict)
        else len(ledger_records)
    )
    if not actual_provider_calls_total:
        actual_provider_calls_total = len(ledger_records)
    if stopped_reason != "PROVIDER_HTTP_429" and (
        "PROVIDER_HTTP_429" in blockers
        or any(
            per_league_item["overall_status"] == "PROVIDER_HTTP_429"
            for per_league_item in per_league.values()
        )
    ):
        stopped_reason = "PROVIDER_HTTP_429"
    return {
        "status": "OUTPUT_DIR_SUMMARY",
        "source": SOURCE,
        "output_dir": str(out_dir),
        "completed_leagues": completed_leagues,
        "partial_leagues": partial_leagues,
        "unstarted_leagues": unstarted_leagues,
        "per_league": per_league,
        "blockers": _dedupe(blockers),
        "warnings": _dedupe(warnings),
        "actual_provider_calls_total": actual_provider_calls_total,
        "provider_calls": 0,
        "db_reads": 0,
        "db_writes": 0,
        "checkpoint_write": False,
        "provider_mapping_or_season_review_required": season_review_required,
        "recommended_next_action": _recommended_next_action(
            stopped_reason=stopped_reason,
            partial_leagues=partial_leagues,
            unstarted_leagues=unstarted_leagues,
            season_review_required=season_review_required,
            completed_leagues=completed_leagues,
        ),
    }


def _resume_reports(out_dir: Path | None) -> dict[str, dict[str, Any]]:
    if out_dir is None or not out_dir.exists():
        return {}
    reports: dict[str, dict[str, Any]] = {}
    for path in sorted(out_dir.glob("W2_WHITELIST_AUDIT_*.json")):
        report = _read_json(path)
        if not isinstance(report, dict):
            continue
        competition_id = _text(report.get("competition_id")) or path.stem.removeprefix(
            "W2_WHITELIST_AUDIT_"
        )
        if competition_id:
            report["_path"] = str(path)
            reports[competition_id] = report
    return reports


def _is_completed_report(report: dict[str, Any]) -> bool:
    return _report_status(report) in {"PASS", "FAIL", "CANNOT_VERIFY"}


def _report_status(report: dict[str, Any]) -> str:
    return _text(report.get("overall_status") or report.get("status"))


def _resolve_sleeper(
    *,
    requester_factory: Callable[[str], ApiFootballRequester] | None,
    sleeper: Callable[[float], None] | None,
) -> Callable[[float], None]:
    if sleeper is not None:
        return sleeper
    if requester_factory is not None:
        return lambda _seconds: None
    return time.sleep


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _item_statuses(report: dict[str, Any]) -> dict[str, str]:
    items = report.get("items") or report.get("audit_items") or []
    if not isinstance(items, list):
        return {}
    statuses: dict[str, str] = {}
    for item in items:
        if isinstance(item, dict):
            name = _text(item.get("name"))
            status = _text(item.get("status"))
            if name:
                statuses[name] = status
    return statuses


def _recommended_next_action(
    *,
    stopped_reason: str,
    partial_leagues: list[str],
    unstarted_leagues: list[str],
    season_review_required: bool,
    completed_leagues: list[str],
) -> str:
    if stopped_reason == "PROVIDER_HTTP_429":
        return "WAIT_FOR_PROVIDER_COOLDOWN_THEN_RESUME"
    if partial_leagues or unstarted_leagues:
        return "RESUME_AUDIT"
    if season_review_required:
        return "REVIEW_PROVIDER_MAPPING_OR_SEASON"
    if completed_leagues:
        return "REVIEW_COMPLETED_REPORTS"
    return "NO_REPORTS_FOUND"


def _list_of_strings(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_text(item) for item in value if _text(item)]
    return []


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _default_out_dir() -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return Path("/tmp") / f"w2_league_whitelist_audit_{stamp}"  # noqa: S108


def _is_tmp_path(path: Path) -> bool:
    return _is_under(path, Path("/tmp")) or _is_under(  # noqa: S108
        path,
        Path(tempfile.gettempdir()),
    )


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
