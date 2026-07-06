from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from w2.competitions.league_whitelist_audit import EVIDENCE_ONLY_AUDIT_MODE_OUTPUT
from w2.competitions.league_whitelist_scope import (
    ALL_WHITELIST_COMPETITIONS,
    IN_SEASON_NATIONAL_LEAGUES,
)

REPORT_PREFIX = "W2_WHITELIST_AUDIT_"
REPORT_SUFFIX = ".json"
SOURCE = "scripts.summarize_w2_league_audit_diagnosis.v1"
TERMINAL_STATUSES = {"PASS", "FAIL", "CANNOT_VERIFY", EVIDENCE_ONLY_AUDIT_MODE_OUTPUT}
RAW_PAYLOAD_KEYS = {
    "raw_payload",
    "payload",
    "response",
    "request_headers",
    "headers",
    "body",
}
NEXT_ACTIONS = (
    "Verify API-Football league_id/season per profile offline using provider docs/source notes.",
    "Add/repair squad_value mapping source.",
    "Review odds bookmaker market mapping for AH/OU.",
    "Do not enable any league until 7-item audit PASS.",
    "Do not rerun provider today; daily cap already reached.",
)
MISSING_EVIDENCE_ACTIONS = (
    "Next provider audit should record sanitized observed provider mapping fields: "
    "league_id, name, country, season, team_count.",
    "Next provider audit should record sanitized fixture query params and response_count.",
    "Next provider audit should record sanitized bookmaker market names and bookmaker_count.",
    "Do not guess profile changes from category-level blockers only.",
)
SUFFICIENT_EVIDENCE_ACTIONS = (
    "Observed evidence is present; update profile mapping from observed values only after "
    "reviewer approval.",
)
MAPPING_OBSERVED_FIELDS = (
    "observed_provider_league_id",
    "observed_provider_league_name",
    "observed_provider_country",
    "observed_provider_season",
    "observed_provider_team_count",
)
FIXTURE_OBSERVED_FIELDS = (
    "observed_fixture_query_params",
    "observed_fixture_response_count",
)
BOOKMAKER_OBSERVED_FIELDS = (
    "observed_bookmaker_count",
    "observed_ah_ou_market_names",
    "observed_has_ah",
    "observed_has_ou",
    "observed_has_line",
)
OBSERVED_FIELDS = (
    *MAPPING_OBSERVED_FIELDS,
    *FIXTURE_OBSERVED_FIELDS,
    *BOOKMAKER_OBSERVED_FIELDS,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Summarize W2 league whitelist audit diagnosis from sanitized local reports.",
    )
    parser.add_argument("--audit-dir", action="append", default=[])
    parser.add_argument("--out-file")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    payload = build_diagnosis(
        audit_dirs=[Path(item) for item in args.audit_dir],
        out_file=Path(args.out_file) if args.out_file else None,
    )
    text = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        indent=None if args.json_output else 2,
    )
    print(text)
    return 0


def build_diagnosis(
    *,
    audit_dirs: list[Path],
    out_file: Path | None = None,
) -> dict[str, Any]:
    if not audit_dirs:
        raise SystemExit("BLOCKER: AUDIT_DIR_REQUIRED")
    for audit_dir in audit_dirs:
        if not audit_dir.exists() or not audit_dir.is_dir():
            raise SystemExit(f"BLOCKER: AUDIT_OUTPUT_DIR_MISSING:{audit_dir}")
    if out_file is not None and not _is_tmp_path(out_file):
        raise SystemExit("BLOCKER: OUT_FILE_MUST_BE_UNDER_TMP")

    reports = _combined_reports(audit_dirs)
    expected_leagues = _expected_leagues(reports)
    completed_leagues = [
        league_id
        for league_id in expected_leagues
        if league_id in reports and _status(reports[league_id]) in TERMINAL_STATUSES
    ]
    missing_leagues = [league_id for league_id in expected_leagues if league_id not in reports]
    diagnosis = _diagnosis(reports)
    payload = {
        "status": "PASS" if not missing_leagues else "INCOMPLETE",
        "source": SOURCE,
        "audit_dirs": [str(path) for path in audit_dirs],
        "competition_count": len(reports),
        "completed_leagues": completed_leagues,
        "missing_leagues": missing_leagues,
        "can_enable_by_league": {
            league_id: bool(report.get("can_enable")) for league_id, report in reports.items()
        },
        "blockers_by_league": {
            league_id: _strings(report.get("blockers")) for league_id, report in reports.items()
        },
        "audit_items_by_league": {
            league_id: _item_statuses(report) for league_id, report in reports.items()
        },
        "warnings_by_league": {
            league_id: _strings(report.get("warnings")) for league_id, report in reports.items()
        },
        "provider_calls_total": _provider_calls_total(audit_dirs),
        "diagnosis": diagnosis,
        "recommended_next_actions": _recommended_next_actions(diagnosis),
        "provider_calls": 0,
        "db_reads": 0,
        "db_writes": 0,
    }
    if out_file is not None:
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        payload["out_file"] = str(out_file)
    return payload


def _combined_reports(audit_dirs: list[Path]) -> dict[str, dict[str, Any]]:
    reports: dict[str, dict[str, Any]] = {}
    for audit_dir in audit_dirs:
        for path in sorted(audit_dir.glob(f"{REPORT_PREFIX}*{REPORT_SUFFIX}")):
            report = _read_report(path)
            league_id = _text(report.get("competition_id")) or _league_id_from_path(path)
            if league_id not in ALL_WHITELIST_COMPETITIONS:
                continue
            existing = reports.get(league_id)
            if existing is None or _prefer_report(report, existing):
                reports[league_id] = report
    return reports


def _expected_leagues(reports: dict[str, dict[str, Any]]) -> tuple[str, ...]:
    if any(league_id not in IN_SEASON_NATIONAL_LEAGUES for league_id in reports):
        return tuple(
            league_id for league_id in ALL_WHITELIST_COMPETITIONS if league_id in reports
        )
    return IN_SEASON_NATIONAL_LEAGUES


def _read_report(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"BLOCKER: AUDIT_REPORT_INVALID:{path}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"BLOCKER: AUDIT_REPORT_INVALID:{path}")
    raw_field = _raw_payload_field(payload)
    if raw_field:
        raise SystemExit(f"BLOCKER: RAW_PAYLOAD_FIELD_NOT_ALLOWED:{raw_field}")
    return payload


def _prefer_report(candidate: dict[str, Any], existing: dict[str, Any]) -> bool:
    candidate_status = _status(candidate)
    existing_status = _status(existing)
    if candidate_status in TERMINAL_STATUSES and existing_status not in TERMINAL_STATUSES:
        return True
    if candidate_status not in TERMINAL_STATUSES and existing_status in TERMINAL_STATUSES:
        return False
    return _int(candidate.get("actual_provider_calls")) >= _int(
        existing.get("actual_provider_calls")
    )


def _diagnosis(reports: dict[str, dict[str, Any]]) -> dict[str, Any]:
    warnings = [item for report in reports.values() for item in _strings(report.get("warnings"))]
    blockers = [item for report in reports.values() for item in _strings(report.get("blockers"))]
    item_statuses = [
        statuses
        for report in reports.values()
        for statuses in _item_statuses(report).items()
    ]
    result: dict[str, Any] = {
        "provider_mapping_review_required": _has_blocker(blockers, "provider_mapping:FAIL"),
        "season_review_required": any("AUDIT_SEASON_FALLBACK" in item for item in warnings),
        "bookmaker_coverage_review_required": _has_item_status(
            item_statuses,
            "bookmaker_depth",
            "FAIL",
        ),
        "squad_value_mapping_required": _has_item_status(
            item_statuses,
            "squad_value",
            "CANNOT_VERIFY",
        ),
        "fixture_query_review_required": _has_item_status(item_statuses, "fixtures", "FAIL"),
    }
    missing_observed_fields = _missing_observed_fields(reports, result)
    result["insufficient_diagnostic_evidence"] = bool(missing_observed_fields)
    result["missing_observed_fields"] = missing_observed_fields
    return result


def _missing_observed_fields(
    reports: dict[str, dict[str, Any]],
    diagnosis: dict[str, bool],
) -> list[str]:
    required: list[str] = []
    if diagnosis["provider_mapping_review_required"] or diagnosis["season_review_required"]:
        required.extend(MAPPING_OBSERVED_FIELDS)
    if diagnosis["fixture_query_review_required"]:
        required.extend(FIXTURE_OBSERVED_FIELDS)
    if diagnosis["bookmaker_coverage_review_required"]:
        required.extend(BOOKMAKER_OBSERVED_FIELDS)
    return [
        field
        for field in _dedupe(required)
        if not all(_has_observed_field(report, field) for report in reports.values())
    ]


def _has_observed_field(report: dict[str, Any], field: str) -> bool:
    values = _observed_values(report, field)
    if not values:
        return False
    for value in values:
        if value not in (None, "", [], {}):
            return True
    return False


def _observed_values(report: dict[str, Any], field: str) -> list[Any]:
    values = [report.get(field)] if field in report else []
    items = report.get("items") or report.get("audit_items") or []
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            observed = item.get("observed_evidence")
            if isinstance(observed, dict) and field in observed:
                values.append(observed.get(field))
    return values


def _provider_calls_total(audit_dirs: list[Path]) -> int:
    total = 0
    for audit_dir in audit_dirs:
        summary = _read_json(audit_dir / "summary.json")
        if isinstance(summary, dict):
            total += _int(summary.get("actual_provider_calls_total"))
    return total


def _recommended_next_actions(diagnosis: dict[str, Any]) -> list[str]:
    actions = list(NEXT_ACTIONS)
    if diagnosis["insufficient_diagnostic_evidence"]:
        actions.extend(MISSING_EVIDENCE_ACTIONS)
    else:
        actions.extend(SUFFICIENT_EVIDENCE_ACTIONS)
    return actions


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


def _raw_payload_field(value: Any) -> str:
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            if key_text in RAW_PAYLOAD_KEYS:
                return key_text
            nested = _raw_payload_field(child)
            if nested:
                return nested
    if isinstance(value, list):
        for child in value:
            nested = _raw_payload_field(child)
            if nested:
                return nested
    return ""


def _league_id_from_path(path: Path) -> str:
    name = path.name
    if name.startswith(REPORT_PREFIX) and name.endswith(REPORT_SUFFIX):
        return name[len(REPORT_PREFIX) : -len(REPORT_SUFFIX)]
    return ""


def _status(report: dict[str, Any]) -> str:
    return _text(report.get("overall_status") or report.get("status"))


def _has_blocker(blockers: list[str], value: str) -> bool:
    return any(item == value for item in blockers)


def _has_item_status(item_statuses: list[tuple[str, str]], name: str, status: str) -> bool:
    return any(
        item_name == name and item_status == status
        for item_name, item_status in item_statuses
    )


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _strings(value: Any) -> list[str]:
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


def _is_tmp_path(path: Path) -> bool:
    return _is_under(path, Path("/tmp")) or _is_under(path, Path(tempfile.gettempdir()))  # noqa: S108


def _is_under(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return "" if value is None else str(value)


if __name__ == "__main__":
    sys.exit(main())
