from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from scripts.summarize_w2_league_provider_usage import summarize_provider_usage


def test_summary_and_ledger_are_not_double_counted(tmp_path: Path) -> None:
    run = tmp_path / "run"
    run.mkdir()
    _write_usage_run(
        run,
        [
            _ledger_record("2026-07-06T00:00:00+00:00", provider_call_index=1),
            _ledger_record("2026-07-06T00:00:01+00:00", provider_call_index=2),
        ],
        summary_calls=2,
    )

    payload = summarize_provider_usage(
        target_date=date(2026, 7, 6),
        audit_dirs=[run],
        dashboard_used=2,
    )

    assert payload["status"] == "PASS"
    assert payload["local_summary_calls_by_dir"][str(run)] == 2
    assert payload["local_ledger_records_by_dir"][str(run)] == 2
    assert payload["provider_calls_total_raw"] == 2
    assert payload["provider_calls_total_deduped"] == 2
    assert payload["likely_real_http_calls"] == 2
    assert payload["likely_billing_calls"] == 2
    assert payload["reconciliation_status"] == "PASS"
    assert payload["provider_calls"] == 0
    assert payload["db_reads"] == 0
    assert payload["db_writes"] == 0


def test_duplicate_records_are_deduped(tmp_path: Path) -> None:
    run = tmp_path / "run"
    run.mkdir()
    record = _ledger_record("2026-07-06T00:00:00+00:00", provider_call_index=1)
    _write_usage_run(run, [record, dict(record)], summary_calls=2)

    payload = summarize_provider_usage(
        target_date=date(2026, 7, 6),
        audit_dirs=[run],
        dashboard_used=1,
    )

    assert payload["provider_calls_total_raw"] == 2
    assert payload["provider_calls_total_deduped"] == 1
    assert payload["duplicate_records_count"] == 1
    assert payload["likely_real_http_calls"] == 1
    assert payload["likely_billing_calls"] == 1


def test_records_without_status_code_are_not_billing_proof(tmp_path: Path) -> None:
    run = tmp_path / "run"
    run.mkdir()
    record = _ledger_record("2026-07-06T00:00:00+00:00", provider_call_index=1)
    record.pop("status_code")
    _write_usage_run(run, [record], summary_calls=1)

    payload = summarize_provider_usage(
        target_date=date(2026, 7, 6),
        audit_dirs=[run],
        dashboard_used=0,
    )

    assert payload["records_with_status_code_missing"] == 1
    assert payload["deduped_http_like_calls"] == 0
    assert payload["likely_real_http_calls"] == 0
    assert payload["likely_billing_calls"] == 0
    assert payload["non_billing_local_records"] == 1
    assert "LOCAL_LEDGER_NOT_PROOF_OF_PROVIDER_BILLING" in payload["warnings"]


def test_status_code_without_quota_header_is_warning_not_likely_billing(
    tmp_path: Path,
) -> None:
    run = tmp_path / "run"
    run.mkdir()
    record = _ledger_record("2026-07-06T00:00:00+00:00", provider_call_index=1)
    record["quota_remaining"] = None
    _write_usage_run(run, [record], summary_calls=1)

    payload = summarize_provider_usage(
        target_date=date(2026, 7, 6),
        audit_dirs=[run],
        dashboard_used=0,
    )

    assert payload["deduped_http_like_calls"] == 1
    assert payload["likely_real_http_calls"] == 1
    assert payload["likely_billing_calls"] == 0
    assert payload["non_billing_local_records"] == 0
    assert payload["status"] == "RECONCILIATION_REQUIRED"
    assert "POSSIBLE_REAL_HTTP_BUT_NO_PROVIDER_QUOTA_HEADER" in payload["warnings"]


def test_dashboard_used_mismatch_requires_reconciliation(tmp_path: Path) -> None:
    run = tmp_path / "run"
    run.mkdir()
    _write_usage_run(
        run,
        [_ledger_record("2026-07-06T00:00:00+00:00", provider_call_index=1)],
        summary_calls=1,
    )

    payload = summarize_provider_usage(
        target_date=date(2026, 7, 6),
        audit_dirs=[run],
        dashboard_used=36,
    )

    assert payload["status"] == "RECONCILIATION_REQUIRED"
    assert payload["reconciliation_status"] == "RECONCILIATION_REQUIRED"
    assert payload["discrepancy"]["dashboard_used"] == 36
    assert payload["discrepancy"]["likely_real_http_calls"] == 1
    assert payload["discrepancy"]["likely_billing_calls"] == 1


def test_raw_payload_or_key_like_fields_are_blocked(tmp_path: Path) -> None:
    run = tmp_path / "run"
    run.mkdir()
    record = _ledger_record("2026-07-06T00:00:00+00:00", provider_call_index=1)
    record["raw_payload"] = {"redacted_value": "not-written"}
    _write_usage_run(run, [record], summary_calls=1)

    payload = summarize_provider_usage(
        target_date=date(2026, 7, 6),
        audit_dirs=[run],
        dashboard_used=0,
    )

    assert payload["status"] == "PROVIDER_USAGE_UNVERIFIED"
    assert payload["likely_billing_calls"] == 0
    assert payload["blockers"]


def test_summary_ledger_mismatch_is_reported(tmp_path: Path) -> None:
    run = tmp_path / "run"
    run.mkdir()
    _write_usage_run(
        run,
        [_ledger_record("2026-07-06T00:00:00+00:00", provider_call_index=1)],
        summary_calls=3,
    )

    payload = summarize_provider_usage(
        target_date=date(2026, 7, 6),
        audit_dirs=[run],
        dashboard_used=1,
    )

    assert payload["summary_ledger_mismatch"] is True
    assert payload["summary_ledger_mismatches"] == [
        {
            "audit_dir": str(run),
            "summary_provider_calls": 3,
            "ledger_records": 1,
        }
    ]


def _write_usage_run(
    path: Path,
    records: list[dict[str, Any]],
    *,
    summary_calls: int,
) -> None:
    (path / "audit_ledger.json").write_text(
        json.dumps(records),
        encoding="utf-8",
    )
    (path / "summary.json").write_text(
        json.dumps({"actual_provider_calls_total": summary_calls}),
        encoding="utf-8",
    )


def _ledger_record(captured_at: str, *, provider_call_index: int) -> dict[str, Any]:
    return {
        "captured_at": captured_at,
        "competition_id": "premier_league",
        "endpoint": "fixtures",
        "league_id": "39",
        "fixture_id": "",
        "provider_call_index": provider_call_index,
        "quota_remaining": 90 - provider_call_index,
        "status_code": 200,
    }
