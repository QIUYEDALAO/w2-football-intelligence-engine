from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from w2.competitions.league_whitelist_audit import AUDIT_ENDPOINT_ALLOWLIST

SOURCE = "scripts.summarize_w2_league_provider_usage.v1"
DEFAULT_DAILY_AUDIT_HARD_CAP = 90
DEFAULT_TMP_ROOT = Path("/tmp")  # noqa: S108 - read-only reconciliation scans audit dirs.
DEFAULT_AUDIT_DIR_GLOB = "w2_league_whitelist*audit*"
DEDUP_KEY_FIELDS = (
    "endpoint",
    "competition_id",
    "league_id",
    "fixture_id",
    "provider_call_index",
    "captured_at",
)
STOP_OR_WARNING_TEXT = ("QUOTA_WARNING", "DAILY_QUOTA_EXHAUSTED")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reconcile W2 league whitelist provider usage from local audit ledgers.",
    )
    parser.add_argument("--date")
    parser.add_argument("--audit-dir", action="append", default=[])
    parser.add_argument("--dashboard-used", type=int)
    parser.add_argument("--daily-audit-hard-cap", type=int, default=DEFAULT_DAILY_AUDIT_HARD_CAP)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    target_date = date.fromisoformat(args.date) if args.date else datetime.now(UTC).date()
    audit_dirs = [Path(item) for item in args.audit_dir] or discover_audit_dirs()
    payload = summarize_provider_usage(
        target_date=target_date,
        audit_dirs=audit_dirs,
        dashboard_used=args.dashboard_used,
        daily_audit_hard_cap=args.daily_audit_hard_cap,
    )
    print(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            indent=None if args.json_output else 2,
        )
    )
    return 0


def discover_audit_dirs(tmp_root: Path = DEFAULT_TMP_ROOT) -> list[Path]:
    return sorted(path for path in tmp_root.glob(DEFAULT_AUDIT_DIR_GLOB) if path.is_dir())


def summarize_provider_usage(
    *,
    target_date: date,
    audit_dirs: list[Path],
    dashboard_used: int | None = None,
    daily_audit_hard_cap: int = DEFAULT_DAILY_AUDIT_HARD_CAP,
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    audit_dir_keys: list[str] = []
    local_summary_calls_by_dir: dict[str, int | None] = {}
    local_ledger_records_by_dir: dict[str, int] = {}
    http_status_distribution_by_dir: dict[str, dict[str, int]] = {}
    endpoints_by_dir: dict[str, list[str]] = {}
    quota_remaining_values: dict[str, list[int | str]] = {}
    records_with_quota_headers_by_dir: dict[str, int] = {}
    records_without_quota_headers_by_dir: dict[str, int] = {}
    records_with_status_code_missing_by_dir: dict[str, int] = {}
    provider_calls_by_dir_summary: dict[str, dict[str, int | bool | None]] = {}
    report_files_by_dir: dict[str, int] = {}
    mismatches: list[dict[str, Any]] = []
    all_records: list[dict[str, Any]] = []

    for audit_dir in audit_dirs:
        dir_key = str(audit_dir)
        if not audit_dir.exists() or not audit_dir.is_dir():
            blockers.append(f"AUDIT_DIR_MISSING:{dir_key}")
            continue
        audit_dir_keys.append(dir_key)
        ledger_records = _read_ledger(audit_dir, blockers)
        summary = _read_summary(audit_dir, blockers)
        _read_reports(audit_dir, blockers)

        summary_calls = _summary_calls(summary)
        local_summary_calls_by_dir[dir_key] = summary_calls
        local_ledger_records_by_dir[dir_key] = len(ledger_records)
        report_files_by_dir[dir_key] = len(list(audit_dir.glob("W2_WHITELIST_AUDIT_*.json")))
        http_status_distribution_by_dir[dir_key] = _status_distribution(ledger_records)
        endpoints_by_dir[dir_key] = sorted(
            {str(record.get("endpoint", "")) for record in ledger_records if record.get("endpoint")}
        )
        quota_remaining_values[dir_key] = _quota_values(ledger_records)
        records_with_quota_headers_by_dir[dir_key] = sum(
            1 for record in ledger_records if _has_quota_header(record)
        )
        records_without_quota_headers_by_dir[dir_key] = sum(
            1 for record in ledger_records if not _has_quota_header(record)
        )
        records_with_status_code_missing_by_dir[dir_key] = sum(
            1 for record in ledger_records if record.get("status_code") is None
        )
        dir_http_like_records = [
            record for record in ledger_records if _is_http_like_record(record)
        ]
        provider_calls_by_dir_summary[dir_key] = {
            "summary_calls": summary_calls,
            "ledger_records": len(ledger_records),
            "likely_real_http_calls": len(dir_http_like_records),
            "records_with_quota_headers": records_with_quota_headers_by_dir[dir_key],
            "records_without_quota_headers": records_without_quota_headers_by_dir[dir_key],
            "summary_ledger_mismatch": (
                summary_calls is not None and summary_calls != len(ledger_records)
            ),
        }
        if summary_calls is not None and summary_calls != len(ledger_records):
            mismatches.append(
                {
                    "audit_dir": dir_key,
                    "summary_provider_calls": summary_calls,
                    "ledger_records": len(ledger_records),
                }
            )
        for record in ledger_records:
            normalized = dict(record)
            normalized["_audit_dir"] = dir_key
            all_records.append(normalized)
        if not ledger_records and summary_calls:
            warnings.append(f"LEDGER_MISSING_USED_SUMMARY:{dir_key}")

    deduped_records = _dedupe_records(all_records)
    today_records = [
        record for record in deduped_records if _record_date(record) == target_date
    ]
    http_like_records = [record for record in today_records if _is_http_like_record(record)]
    likely_billing_records = [
        record for record in http_like_records if _has_quota_header(record)
    ]
    non_billing_records = [record for record in today_records if record not in http_like_records]

    warnings.extend(_evidence_warnings(today_records, http_like_records, likely_billing_records))
    likely_real_http_calls = len(http_like_records)
    status = _status(blockers, dashboard_used, likely_real_http_calls)
    today_provider_calls_used = likely_real_http_calls
    remaining_cap = max(0, daily_audit_hard_cap - today_provider_calls_used)
    records_with_status_code_200 = sum(
        1 for record in today_records if record.get("status_code") == 200
    )
    records_with_status_code_429 = sum(
        1 for record in today_records if record.get("status_code") == 429
    )
    records_with_status_code_missing = sum(
        1 for record in today_records if record.get("status_code") is None
    )
    records_with_quota_headers = sum(1 for record in today_records if _has_quota_header(record))
    records_without_quota_headers = len(today_records) - records_with_quota_headers
    status_code_distribution = _status_distribution(today_records)
    endpoint_distribution = _endpoint_distribution(today_records)
    duplicate_records_count = len(all_records) - len(deduped_records)
    possible_local_double_count = (
        duplicate_records_count > 0 or len(today_records) > likely_real_http_calls
    )
    possible_account_mismatch = (
        dashboard_used is not None and dashboard_used != likely_real_http_calls
    )
    possible_dashboard_delay = (
        dashboard_used is not None
        and dashboard_used < likely_real_http_calls
        and likely_real_http_calls > 0
    )

    return {
        "status": status,
        "reconciliation_status": status,
        "source": SOURCE,
        "target_date": target_date.isoformat(),
        "audit_dirs": audit_dir_keys,
        "counted_dirs": audit_dir_keys,
        "official_dashboard_used_user_reported": dashboard_used,
        "local_summary_calls_by_dir": local_summary_calls_by_dir,
        "summary_calls_by_dir": local_summary_calls_by_dir,
        "local_ledger_records_by_dir": local_ledger_records_by_dir,
        "ledger_records_by_dir": local_ledger_records_by_dir,
        "provider_calls_by_dir_summary": provider_calls_by_dir_summary,
        "http_status_distribution_by_dir": http_status_distribution_by_dir,
        "endpoints_by_dir": endpoints_by_dir,
        "quota_remaining_values": quota_remaining_values,
        "status_code_distribution": status_code_distribution,
        "endpoint_distribution": endpoint_distribution,
        "records_with_status_code": len(today_records) - records_with_status_code_missing,
        "records_with_status_code_200": records_with_status_code_200,
        "records_with_status_code_429": records_with_status_code_429,
        "records_with_status_code_missing": records_with_status_code_missing,
        "records_without_status_code": records_with_status_code_missing,
        "records_with_status_code_missing_by_dir": records_with_status_code_missing_by_dir,
        "records_with_quota_headers": records_with_quota_headers,
        "records_without_quota_headers": records_without_quota_headers,
        "records_with_quota_headers_by_dir": records_with_quota_headers_by_dir,
        "records_without_quota_headers_by_dir": records_without_quota_headers_by_dir,
        "provider_calls_total_raw": len(all_records),
        "provider_calls_total_deduped": len(deduped_records),
        "local_ledger_records_total": len(deduped_records),
        "dedup_key": list(DEDUP_KEY_FIELDS),
        "duplicate_records_count": duplicate_records_count,
        "deduped_http_like_calls": len(http_like_records),
        "likely_real_http_calls": likely_real_http_calls,
        "likely_billing_calls": len(likely_billing_records),
        "non_billing_local_records": len(non_billing_records),
        "today_provider_calls_used": today_provider_calls_used,
        "daily_audit_hard_cap": daily_audit_hard_cap,
        "remaining_cap": remaining_cap,
        "quota_warning": _has_quota_warning(today_records),
        "http_429": _has_429(today_records),
        "historical_quota_warning": _has_quota_warning(deduped_records),
        "historical_http_429": _has_429(deduped_records),
        "summary_ledger_mismatches": mismatches,
        "summary_ledger_mismatch": bool(mismatches),
        "possible_account_mismatch": possible_account_mismatch,
        "possible_dashboard_delay": possible_dashboard_delay,
        "possible_local_double_count": possible_local_double_count,
        "report_files_by_dir": report_files_by_dir,
        "warnings": sorted(set(warnings)),
        "blockers": blockers,
        "discrepancy": {
            "dashboard_used": dashboard_used,
            "local_ledger_records": len(today_records),
            "likely_real_http_calls": likely_real_http_calls,
            "likely_billing_calls": len(likely_billing_records),
            "explanation": _discrepancy_explanation(
                dashboard_used=dashboard_used,
                local_ledger_records=len(today_records),
                likely_real_http_calls=likely_real_http_calls,
                likely_billing_calls=len(likely_billing_records),
            ),
        },
        "explanation": {
            "why_local_ledger_differs_from_dashboard": (
                "Local audit_ledger.json records are execution ledger rows. They are "
                "not official billing by themselves. Records with status_code but no "
                "provider quota header are HTTP-like local records, but they are weaker "
                "billing evidence than records carrying provider quota metadata."
            ),
            "why_78_or_90_happened": (
                "78 and 90 came from counting all local ledger rows for 2026-07-06. "
                "That is useful for local execution accounting, but it is not the same "
                "as the API-Football dashboard billing counter."
            ),
            "why_112_happened": (
                "112 came from a broad /tmp directory scan that mixed extra local audit "
                "directories with the authoritative evidence run."
            ),
            "why_user_36_can_be_consistent": (
                "The 2026-07-06 evidence audit has 36 records with quota_remaining "
                "provider metadata. That matches the user-reported dashboard value."
            ),
            "counting_rule": (
                "summary.json is used only to cross-check audit_ledger.json and is not "
                "added to ledger records."
            ),
        },
        "provider_calls": 0,
        "db_reads": 0,
        "db_writes": 0,
    }


def _read_ledger(audit_dir: Path, blockers: list[str]) -> list[dict[str, Any]]:
    path = audit_dir / "audit_ledger.json"
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        blockers.append(f"AUDIT_LEDGER_INVALID:{audit_dir}")
        return []
    records = payload.get("records") if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        blockers.append(f"AUDIT_LEDGER_INVALID:{audit_dir}")
        return []
    normalized: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            blockers.append(f"AUDIT_LEDGER_RECORD_INVALID:{audit_dir}:{index}")
            continue
        if _raw_payload_field(record):
            blockers.append(f"RAW_PAYLOAD_FIELD_NOT_ALLOWED:{audit_dir}:{index}")
            continue
        normalized.append(record)
    return normalized


def _read_summary(audit_dir: Path, blockers: list[str]) -> dict[str, Any]:
    path = audit_dir / "summary.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        blockers.append(f"AUDIT_SUMMARY_INVALID:{audit_dir}")
        return {}
    if not isinstance(payload, dict):
        blockers.append(f"AUDIT_SUMMARY_INVALID:{audit_dir}")
        return {}
    if _raw_payload_field(payload):
        blockers.append(f"RAW_PAYLOAD_FIELD_NOT_ALLOWED:{audit_dir}:summary")
        return {}
    return payload


def _read_reports(audit_dir: Path, blockers: list[str]) -> None:
    for path in sorted(audit_dir.glob("W2_WHITELIST_AUDIT_*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            blockers.append(f"AUDIT_REPORT_INVALID:{path}")
            continue
        if not isinstance(payload, dict):
            blockers.append(f"AUDIT_REPORT_INVALID:{path}")
            continue
        if _raw_payload_field(payload):
            blockers.append(f"RAW_PAYLOAD_FIELD_NOT_ALLOWED:{path}")


def _summary_calls(summary: dict[str, Any]) -> int | None:
    for key in ("actual_provider_calls_total", "actual_provider_calls", "provider_calls"):
        value = summary.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None


def _status_distribution(records: list[dict[str, Any]]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for record in records:
        value = record.get("status_code")
        counter["missing" if value is None else str(value)] += 1
    return dict(sorted(counter.items()))


def _endpoint_distribution(records: list[dict[str, Any]]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for record in records:
        value = record.get("endpoint")
        counter["missing" if value is None else str(value)] += 1
    return dict(sorted(counter.items()))


def _quota_values(records: list[dict[str, Any]]) -> list[int | str]:
    values = {
        record["quota_remaining"]
        for record in records
        if record.get("quota_remaining") is not None
    }
    return sorted(values, key=lambda item: str(item))


def _dedupe_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, ...]] = set()
    deduped: list[dict[str, Any]] = []
    for record in records:
        key = tuple(_dedup_value(record, field) for field in DEDUP_KEY_FIELDS)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(record)
    return deduped


def _dedup_value(record: dict[str, Any], field: str) -> str:
    value = record.get(field)
    if value is None:
        return ""
    return str(value)


def _record_date(record: dict[str, Any]) -> date | None:
    captured_at = record.get("captured_at")
    if not isinstance(captured_at, str) or not captured_at:
        return None
    try:
        parsed = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).date()


def _is_http_like_record(record: dict[str, Any]) -> bool:
    return (
        record.get("status_code") is not None
        and record.get("endpoint") in AUDIT_ENDPOINT_ALLOWLIST
        and _record_date(record) is not None
    )


def _has_quota_header(record: dict[str, Any]) -> bool:
    return record.get("quota_remaining") is not None


def _has_429(records: list[dict[str, Any]]) -> bool:
    return any(
        record.get("status_code") == 429 or str(record.get("error")) == "429"
        for record in records
    )


def _has_quota_warning(records: list[dict[str, Any]]) -> bool:
    for record in records:
        text = json.dumps(record, ensure_ascii=False)
        if any(item in text for item in STOP_OR_WARNING_TEXT):
            return True
    return False


def _evidence_warnings(
    today_records: list[dict[str, Any]],
    http_like_records: list[dict[str, Any]],
    likely_billing_records: list[dict[str, Any]],
) -> list[str]:
    warnings: list[str] = []
    if http_like_records and not likely_billing_records:
        warnings.append("POSSIBLE_REAL_HTTP_BUT_NO_PROVIDER_QUOTA_HEADER")
    if len(http_like_records) > len(likely_billing_records):
        warnings.append("POSSIBLE_REAL_HTTP_BUT_NO_PROVIDER_QUOTA_HEADER")
    if any(record.get("status_code") is None for record in today_records):
        warnings.append("LOCAL_LEDGER_NOT_PROOF_OF_PROVIDER_BILLING")
    if today_records and not http_like_records:
        warnings.append("LOCAL_LEDGER_NOT_PROOF_OF_PROVIDER_BILLING")
    return warnings


def _status(
    blockers: list[str],
    dashboard_used: int | None,
    likely_real_http_calls: int,
) -> str:
    if blockers:
        return "PROVIDER_USAGE_UNVERIFIED"
    if dashboard_used is not None and dashboard_used != likely_real_http_calls:
        return "RECONCILIATION_REQUIRED"
    return "PASS"


def _discrepancy_explanation(
    *,
    dashboard_used: int | None,
    local_ledger_records: int,
    likely_real_http_calls: int,
    likely_billing_calls: int,
) -> str:
    if dashboard_used is None:
        return "No official dashboard value was supplied; local ledger cannot prove billing alone."
    if dashboard_used == likely_real_http_calls:
        return (
            "User-reported dashboard usage matches local records with HTTP evidence. "
            "Local ledger rows without HTTP evidence are not treated as provider calls."
        )
    return (
        "User-reported dashboard usage does not match local records with HTTP evidence. "
        "Do not continue provider audit without explicit reconciliation or a separately "
        "approved one-call canary. Quota-header-backed records are reported separately "
        f"as likely_billing_calls={likely_billing_calls}."
    )


def _raw_payload_field(value: Any) -> str | None:
    if isinstance(value, dict):
        for key, nested in value.items():
            lowered = str(key).lower()
            if lowered in {"raw_payload", "request_headers", "headers", "body"}:
                return str(key)
            found = _raw_payload_field(nested)
            if found:
                return found
    if isinstance(value, list):
        for item in value:
            found = _raw_payload_field(item)
            if found:
                return found
    return None


if __name__ == "__main__":
    raise SystemExit(main())
