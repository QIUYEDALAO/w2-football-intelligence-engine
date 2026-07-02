#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from sqlalchemy.orm import Session

from w2.audit_export import build_audit_export
from w2.infrastructure.database import create_engine
from w2.operations.production_readiness import build_production_readiness_report
from w2.reporting.report_generator import render_report
from w2.reporting.report_runner import run_report_job
from w2.settlement.history import run_settlement_history


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run W2 production readiness / full-football-day rehearsal gate."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path, help="Dashboard JSON payload file.")
    source.add_argument("--public-url", help="Public staging base URL.")
    parser.add_argument("--window", default="today")
    parser.add_argument("--expected-sha")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--skip-db", action="store_true", help="Skip DB read-only rehearsal.")
    parser.add_argument("--min-rows", type=int, default=1)
    parser.add_argument("--fail-on-blocked", action="store_true")
    args = parser.parse_args()

    try:
        if args.public_url:
            base_url = args.public_url.rstrip("/")
            report_result = run_report_job(
                base_url=base_url,
                window=args.window,
                report_type="final",
                output_format="markdown",
                sink="stdout",
                timeout_seconds=args.timeout,
            )
            dashboard = _fetch_dashboard(base_url, window=args.window, timeout=args.timeout)
            report_text = report_result.report
            report_summary = report_result.summary()
        else:
            dashboard = _load_dashboard(args.input)
            report_text = render_report(dashboard, report_type="final", output_format="markdown")
            report_summary = {
                "status": "PASS",
                "health": {"version_sha": args.expected_sha},
                "quota_summary": {
                    "provider_calls": 0,
                    "network_quota_required": False,
                    "status": "NOT_REQUIRED_READ_ONLY_REPORT",
                },
            }

        if args.skip_db:
            audit = build_audit_export(dashboard)
            settlement_summary: dict[str, Any] = {
                "status": "SKIPPED",
                "reason": "DB_REHEARSAL_SKIPPED",
                "provider_calls": 0,
                "db_writes": 0,
            }
        else:
            engine = create_engine()
            with Session(engine) as session:
                audit = build_audit_export(dashboard, session=session)
                settlement_summary = run_settlement_history(
                    session=session,
                    dry_run=True,
                    write_db=False,
                )

        payload = build_production_readiness_report(
            dashboard=dashboard,
            report_text=report_text,
            report_summary=report_summary,
            audit_manifest=audit.manifest,
            settlement_summary=settlement_summary,
            expected_sha=args.expected_sha,
            min_rows=args.min_rows,
            require_db_rehearsal=True,
        )
    except Exception as exc:
        print(
            json.dumps({"status": "FAILED", "error": str(exc)}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 1

    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
    if args.fail_on_blocked and payload["status"] == "BLOCKED":
        return 2
    return 0


def _fetch_dashboard(base_url: str, *, window: str, timeout: float) -> dict[str, Any]:
    query = urlencode({"window": window, "include_debug": "true"})
    request = Request(f"{base_url}/v1/dashboard?{query}", headers={"Accept": "application/json"})  # noqa: S310
    with urlopen(request, timeout=timeout) as response:  # noqa: S310
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("dashboard endpoint did not return a JSON object")
    return payload


def _load_dashboard(path: Path | None) -> dict[str, Any]:
    if path is None:
        raise ValueError("--input is required")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("dashboard payload must be a JSON object")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
