#!/usr/bin/env python3
"""Append-only reconciliation of the PR #370 mainline validation ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from w2.tracking.forward_ledger_performance import forward_ledger_performance
from w2.tracking.forward_outcome_ledger import (
    _ledger_rows_by_file,
    append_capture_supersessions,
    run_forward_outcome_ledger,
)

OLD_FIXTURE_IDS = ("1494217", "1494218", "1494220", "1494222", "1494223")
SOLE_PICK_FIXTURE_ID = "1494222"
SUPERSESSION_REASON = "TOTALS_MAINLINE_POLICY_SUPERSEDED"


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--day-view-json", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--captured-at", required=True)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--output-json", type=Path, required=True)
    return parser.parse_args()


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("captured_at must include a timezone")
    return parsed.astimezone(UTC)


def _ledger_hash(runtime_root: Path) -> str:
    ledger = runtime_root / "forward_outcome_ledger"
    digest = hashlib.sha256()
    for path in sorted(ledger.glob("*.jsonl")):
        digest.update(path.name.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _pick(card: dict[str, Any]) -> dict[str, Any]:
    v3 = card.get("recommendation_decision_v3") or {}
    return v3.get("selected_candidate") or {}


def _assert_sole_pick(card: dict[str, Any]) -> None:
    v3 = card.get("recommendation_decision_v3") or {}
    pick = _pick(card)
    if (
        str(card.get("fixture_id")) != SOLE_PICK_FIXTURE_ID
        or v3.get("outcome") != "ANALYSIS_PICK"
        or pick.get("market") != "TOTALS"
        or pick.get("selection") != "OVER"
        or str(pick.get("line")) != "2.75"
        or abs(float(pick.get("odds")) - 1.86) > 0.000001
        or card.get("outcome_tracked") is not True
    ):
        raise ValueError("SOLE_PICK_CONTRACT_MISMATCH")


def _pending_audit(performance: dict[str, Any]) -> list[dict[str, Any]]:
    details = performance.get("validation_pending_status", {}).get("details", [])
    result: list[dict[str, Any]] = []
    for detail in details:
        if not isinstance(detail, dict):
            continue
        result.append(
            {
                "fixture_id": detail.get("fixture_id"),
                "capture_identity_hash": detail.get("capture_identity_hash"),
                "decision_hash": detail.get("decision_hash"),
                "card_hash": detail.get("card_hash"),
                "status": detail.get("category"),
                "superseded_by": None,
            }
        )
    return result


def _ledger_records(runtime_root: Path) -> list[dict[str, Any]]:
    """Read the append-only ledger without making it a second authority."""
    rows_by_file = _ledger_rows_by_file(runtime_root / "forward_outcome_ledger")
    return [row for rows in rows_by_file.values() for row in rows]


def main() -> int:
    args = _args()
    captured_at = _parse_utc(args.captured_at)
    day_view = json.loads(args.day_view_json.read_text(encoding="utf-8"))
    cards = [card for card in day_view.get("cards", []) if isinstance(card, dict)]
    sole_pick = next(
        (card for card in cards if str(card.get("fixture_id")) == SOLE_PICK_FIXTURE_ID),
        None,
    )
    if sole_pick is None:
        raise ValueError("SOLE_PICK_FIXTURE_MISSING")
    _assert_sole_pick(sole_pick)

    ledger_hash_before = _ledger_hash(args.runtime_root)
    before = forward_ledger_performance(args.runtime_root, now=captured_at)
    before_pending = _pending_audit(before)
    # Supersede every historical validation capture for the five fixtures.
    # Otherwise an older duplicate could become active after the latest row is
    # superseded, silently restoring the stale decision.
    targets = [
        {
            "fixture_id": row.get("fixture_id"),
            "capture_identity_hash": row.get("capture_identity_hash"),
            "decision_hash": row.get("decision_hash"),
        }
        for row in _ledger_records(args.runtime_root)
        if row.get("record_type") == "capture"
        and row.get("recommendation_scope") == "VALIDATION"
        and str(row.get("fixture_id")) in OLD_FIXTURE_IDS
        and isinstance(row.get("capture_identity_hash"), str)
    ]
    target_ids = {str(row["fixture_id"]) for row in targets}
    if target_ids not in {set(OLD_FIXTURE_IDS), {SOLE_PICK_FIXTURE_ID}}:
        raise ValueError("UNEXPECTED_ACTIVE_PENDING_VALIDATION_SET")

    supersession = append_capture_supersessions(
        args.runtime_root,
        targets,
        reason_code=SUPERSESSION_REASON,
        superseded_at=captured_at,
        dry_run=not args.write,
        write_artifacts=args.write,
    )
    new_capture = run_forward_outcome_ledger(
        {
            "football_day": day_view.get("football_day") or day_view.get("date"),
            "environment": day_view.get("environment") or "staging",
            "cards": [sole_pick],
        },
        captured_at=captured_at,
        dry_run=not args.write,
        write_artifacts=args.write,
        runtime_root=args.runtime_root / "forward_outcome_ledger",
    )
    after = forward_ledger_performance(args.runtime_root, now=captured_at)
    cohort = after.get("performance_cohort", {})
    expected = {
        "validation_count": 24,
        "processed_count": 23,
        "pending_count": 1,
        "eligible_count": 16,
        "excluded_count": 7,
    }
    observed = {key: cohort.get(key) for key in expected}
    if args.write and observed != expected:
        raise ValueError(f"LEDGER_RECONCILIATION_COUNT_MISMATCH:{observed}")
    payload = {
        "schema_version": "w2.pr370.validation_ledger_reconciliation.v1",
        "status": "PASS",
        "write": bool(args.write),
        "reason_code": SUPERSESSION_REASON,
        "captured_at": captured_at.isoformat().replace("+00:00", "Z"),
        "ledger_hash_before": ledger_hash_before,
        "active_pending_before": before_pending,
        "supersessions": supersession,
        "new_validation_capture": new_capture,
        "active_pending_after": _pending_audit(after),
        "public_accounting": observed,
        "expected_public_accounting": expected,
        "safety": {
            "provider_calls": 0,
            "recommendations": 0,
            "locks": 0,
            "official": 0,
            "formal_settlements": 0,
        },
    }
    payload["ledger_hash_after"] = _ledger_hash(args.runtime_root)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
