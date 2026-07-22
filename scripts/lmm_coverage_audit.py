#!/usr/bin/env python3
"""Build a deterministic LMM0 coverage report from local exported facts.

The command is deliberately provider-free and read-only. It accepts already
exported, redacted JSON rows so staging evidence collection can remain a
separate read-only operation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from w2.lineups.intelligence import LineupCoverage, grade_coverage


def build_report(rows: list[dict[str, Any]], *, source_sha256: str) -> dict[str, Any]:
    grouped: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("competition_code") or "UNKNOWN")].append(row)
    competitions: dict[str, Any] = {}
    for competition, items in sorted(grouped.items()):
        coverage = LineupCoverage(
            registered_total=_sum(items, "registered_total"),
            registered_mapped=_sum(items, "registered_mapped"),
            regular_starter_total=_sum(items, "regular_starter_total"),
            regular_starter_mapped=_sum(items, "regular_starter_mapped"),
            matchday_starter_total=_sum(items, "matchday_starter_total"),
            matchday_starter_mapped=_sum(items, "matchday_starter_mapped"),
            valuation_total=_sum(items, "valuation_total"),
            valuation_covered=_sum(items, "valuation_covered"),
            position_total=_sum(items, "position_total"),
            position_covered=_sum(items, "position_covered"),
            formation_total=_sum(items, "formation_total"),
            formation_covered=_sum(items, "formation_covered"),
            conflicts=_sum(items, "conflicts"),
        )
        payload = coverage.as_dict()
        rate = float(payload["matchday_starter_mapping_rate"])
        competitions[competition] = {**payload, "grade": grade_coverage(rate).value}
    report = {
        "schema_version": "w2.lmm0.coverage.v1",
        "source_sha256": source_sha256,
        "provider_calls": 0,
        "competition_count": len(competitions),
        "competitions": competitions,
    }
    report["report_sha256"] = _hash(report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    raw = args.input.read_bytes()
    rows = json.loads(raw)
    if not isinstance(rows, list):
        raise SystemExit("input must be a JSON array")
    report = build_report(rows, source_sha256=hashlib.sha256(raw).hexdigest())
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


def _sum(rows: list[dict[str, Any]], key: str) -> int:
    return sum(int(row.get(key) or 0) for row in rows)


def _hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
