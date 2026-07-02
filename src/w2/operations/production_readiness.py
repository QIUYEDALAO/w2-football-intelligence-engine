from __future__ import annotations

from typing import Any

FORBIDDEN_REPORT_TERMS = (
    "方向未识别",
    "正式推荐字段不完整",
    "正式推荐EV字段不完整",
    "推荐：全场让球，看 方向未识别",
    "AH_MAINLINE_AMBIGUOUS",
    "MISSING_AH_MARKET",
    "DATA_INSUFFICIENT",
    "MARKET_NOT_READY",
    "命中率",
    "胜率",
    "ROI",
    "必中",
    "可买",
    "庄家开错",
    "照这个买",
    "跟庄",
)


def build_production_readiness_report(
    *,
    dashboard: dict[str, Any],
    report_text: str,
    report_summary: dict[str, Any],
    audit_manifest: dict[str, Any],
    settlement_summary: dict[str, Any],
    expected_sha: str | None = None,
    min_rows: int = 1,
    require_db_rehearsal: bool = True,
) -> dict[str, Any]:
    matches = [item for item in _list(dashboard.get("all")) if isinstance(item, dict)]
    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []

    _check(
        checks,
        blockers,
        bool(dashboard.get("generated_at") or dashboard.get("as_of") or dashboard.get("asof")),
        "PAYLOAD_AS_OF_PRESENT",
        "dashboard payload has generated_at/as_of",
    )
    _check(
        checks,
        blockers,
        bool(dashboard.get("selected_football_day") or dashboard.get("selected_date")),
        "FOOTBALL_DAY_PRESENT",
        "dashboard payload has selected football day",
    )
    _check(
        checks,
        blockers,
        len(matches) >= min_rows,
        "FOOTBALL_DAY_HAS_ROWS",
        f"football-day rows >= {min_rows}",
        observed=len(matches),
    )

    if expected_sha:
        _check(
            checks,
            blockers,
            report_summary.get("health", {}).get("version_sha") == expected_sha,
            "API_SHA_MATCH",
            "report runner health version matches expected SHA",
            observed=report_summary.get("health", {}).get("version_sha"),
        )

    invalid_formals = [_formal_id(match) for match in matches if _invalid_formal(match)]
    _check(
        checks,
        blockers,
        not invalid_formals,
        "VALID_FORMAL_PAYLOADS",
        "formal rows carry valid recommendation payload and positive EV",
        observed=invalid_formals,
    )
    _check(
        checks,
        blockers,
        report_summary.get("status") == "PASS",
        "REPORT_RUNNER_PASS",
        "report runner completed successfully",
        observed=report_summary.get("status"),
    )
    quota = _dict(report_summary.get("quota_summary"))
    _check(
        checks,
        blockers,
        quota.get("provider_calls") == 0 and quota.get("network_quota_required") is False,
        "REPORT_RUNNER_READ_ONLY",
        "report runner is read-only and does not require provider quota",
        observed=quota,
    )
    found_terms = [term for term in FORBIDDEN_REPORT_TERMS if term in report_text]
    _check(
        checks,
        blockers,
        not found_terms and "as-of：未知" not in report_text,
        "REPORT_COPY_SAFE",
        "report has no forbidden terms and no unknown as-of",
        observed=found_terms,
    )
    _check(
        checks,
        blockers,
        audit_manifest.get("status") == "PASS"
        and audit_manifest.get("read_only") is True
        and audit_manifest.get("provider_calls") == 0
        and audit_manifest.get("db_writes") == 0,
        "AUDIT_EXPORT_READ_ONLY_PASS",
        "audit export completed read-only",
        observed={
            "status": audit_manifest.get("status"),
            "read_only": audit_manifest.get("read_only"),
            "provider_calls": audit_manifest.get("provider_calls"),
            "db_writes": audit_manifest.get("db_writes"),
        },
    )
    if settlement_summary.get("status") == "SKIPPED":
        target = blockers if require_db_rehearsal else warnings
        target.append(
            {
                "code": "SETTLEMENT_DRY_RUN_NOT_EXECUTED",
                "message": "settlement history dry-run did not run",
                "observed": settlement_summary.get("reason"),
            }
        )
        checks.append(
            {
                "code": "SETTLEMENT_DRY_RUN_READ_ONLY_PASS",
                "status": "BLOCKED" if require_db_rehearsal else "WARN",
                "message": "settlement dry-run skipped",
            }
        )
    else:
        _check(
            checks,
            blockers,
            settlement_summary.get("status") == "PASS"
            and settlement_summary.get("dry_run") is True
            and settlement_summary.get("write_db") is False
            and settlement_summary.get("provider_calls") == 0
            and settlement_summary.get("db_writes") == 0,
            "SETTLEMENT_DRY_RUN_READ_ONLY_PASS",
            "settlement history dry-run completed without writes",
            observed={
                "status": settlement_summary.get("status"),
                "dry_run": settlement_summary.get("dry_run"),
                "write_db": settlement_summary.get("write_db"),
                "provider_calls": settlement_summary.get("provider_calls"),
                "db_writes": settlement_summary.get("db_writes"),
            },
        )
        counts = _dict(settlement_summary.get("counts"))
        if int(counts.get("inspected_locks") or 0) == 0:
            warnings.append(
                {
                    "code": "NO_DB_LOCK_SNAPSHOTS_FOR_REHEARSAL",
                    "message": "no DB recommendation locks were available for settlement rehearsal",
                }
            )
        if int(counts.get("candidate_settlements") or 0) == 0:
            warnings.append(
                {
                    "code": "NO_SETTLEMENT_CANDIDATES_FOR_REHEARSAL",
                    "message": (
                        "no lock/result pair was available for settlement "
                        "candidate rehearsal"
                    ),
                }
            )

    status = "BLOCKED" if blockers else ("WARN_ONLY" if warnings else "PASS")
    return {
        "status": status,
        "schema_version": "w2.production_readiness_rehearsal.v1",
        "selected_football_day": dashboard.get("selected_football_day")
        or dashboard.get("selected_date"),
        "rows": len(matches),
        "formal_payload_count": sum(1 for match in matches if match.get("formal_recommendation")),
        "invalid_formal_payload_count": len(invalid_formals),
        "provider_calls": 0,
        "db_writes": 0,
        "read_only": True,
        "production_deploy": False,
        "checks": checks,
        "blockers": blockers,
        "warnings": warnings,
        "report_summary": report_summary,
        "audit_manifest": audit_manifest,
        "settlement_summary": settlement_summary,
    }


def _invalid_formal(match: dict[str, Any]) -> bool:
    if match.get("formal_recommendation") is not True:
        return False
    recommendation = _dict(match.get("recommendation"))
    if not _valid_formal_recommendation_payload(recommendation, match):
        return True
    expected_value = _number(recommendation.get("expected_value"))
    return expected_value is None or expected_value <= 0


def _valid_formal_recommendation_payload(
    recommendation: dict[str, Any],
    match: dict[str, Any],
) -> bool:
    if not recommendation:
        return False
    if recommendation.get("tier") != "FORMAL" and match.get("formal_recommendation") is not True:
        return False
    if recommendation.get("market") != "ASIAN_HANDICAP":
        return False
    if recommendation.get("selection") not in {"HOME_AH", "AWAY_AH"}:
        return False
    if _number(recommendation.get("line")) is None:
        return False
    odds = recommendation.get("odds")
    return odds is None or _number(odds) is not None


def _formal_id(match: dict[str, Any]) -> dict[str, Any]:
    return {
        "fixture_id": match.get("fixture_id"),
        "teams": f"{match.get('home_team_name')} vs {match.get('away_team_name')}",
    }


def _check(
    checks: list[dict[str, Any]],
    blockers: list[dict[str, Any]],
    passed: bool,
    code: str,
    message: str,
    *,
    observed: Any | None = None,
) -> None:
    row = {
        "code": code,
        "status": "PASS" if passed else "BLOCKED",
        "message": message,
    }
    if observed is not None:
        row["observed"] = observed
    checks.append(row)
    if not passed:
        blockers.append({"code": code, "message": message, "observed": observed})


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _number(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
