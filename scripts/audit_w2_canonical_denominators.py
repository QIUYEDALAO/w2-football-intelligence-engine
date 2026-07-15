#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from w2.infrastructure.atomic_files import read_jsonl
from w2.tracking.canonical_identity import canonical_capture_candidates
from w2.tracking.canonical_outcomes import project_canonical_outcomes


def audit_denominators(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    candidates = canonical_capture_candidates(records)
    projection = project_canonical_outcomes(records, candidates)
    raw_scope = Counter(_raw_scope(row) for row in projection.raw_outcomes)
    canonical_scope = Counter(
        str(row.get("recommendation_scope") or "UNKNOWN")
        for row in projection.canonical_outcomes
    )
    audit_scope = Counter(
        str(row.get("recommendation_scope") or _raw_scope(row))
        for row in projection.audit_only_outcomes
    )
    by_strategy = Counter(
        (
            str(row.get("recommendation_scope") or "UNKNOWN"),
            str(row.get("strategy_version") or "LEGACY_UNVERSIONED"),
        )
        for row in projection.canonical_outcomes
    )
    by_market = Counter(
        str(row.get("market") or "UNKNOWN") for row in projection.canonical_outcomes
    )
    fixture_keys = Counter(
        tuple(row.get("canonical_performance_key") or ())
        for row in projection.canonical_outcomes
    )
    return {
        "schema_version": "w2.canonical_denominator_audit.v1",
        "raw_row_count": len(records),
        "raw_outcome_row_count": len(projection.raw_outcomes),
        "canonical_outcome_count": len(projection.canonical_outcomes),
        "audit_only_outcome_count": len(projection.audit_only_outcomes),
        "performance_integrity": dict(projection.metrics),
        "by_scope": {
            scope: {
                "raw_outcome_row_count": raw_scope[scope],
                "canonical_outcome_count": canonical_scope[scope],
                "audit_only_outcome_count": audit_scope[scope],
            }
            for scope in sorted(set(raw_scope) | set(canonical_scope) | set(audit_scope))
        },
        "by_strategy": [
            {
                "recommendation_scope": scope,
                "strategy_version": strategy,
                "canonical_outcome_count": count,
            }
            for (scope, strategy), count in sorted(by_strategy.items())
        ],
        "by_market": dict(sorted(by_market.items())),
        "by_fixture_key": [
            {"key": list(key), "canonical_outcome_count": count}
            for key, count in sorted(fixture_keys.items())
        ],
        "provider_calls": 0,
        "db_writes": 0,
        "ledger_writes": 0,
    }


def load_records(
    *, runtime_root: Path | None = None, baseline_manifest: Path | None = None
) -> list[dict[str, Any]]:
    if (runtime_root is None) == (baseline_manifest is None):
        raise ValueError("provide exactly one of runtime_root or baseline_manifest")
    paths: list[Path]
    if baseline_manifest is not None:
        manifest = json.loads(baseline_manifest.read_text(encoding="utf-8"))
        paths = []
        for item in manifest.get("files", []):
            declared = Path(str(item.get("frozen_path") or ""))
            candidate = declared if declared.exists() else baseline_manifest.parent / declared.name
            paths.append(candidate)
    else:
        assert runtime_root is not None
        root = runtime_root / "forward_outcome_ledger"
        paths = sorted(root.glob("*.jsonl"))
    records: list[dict[str, Any]] = []
    for path in paths:
        result = read_jsonl(path)
        records.extend(
            dict(row) for row in result.records if isinstance(row, Mapping)
        )
    return records


def _raw_scope(row: Mapping[str, Any]) -> str:
    explicit = str(row.get("recommendation_scope") or "").upper()
    if explicit in {"VALIDATION", "OFFICIAL", "SHADOW"}:
        return explicit
    return "SHADOW" if str(row.get("settled_side") or "") == "shadow_pick" else "VALIDATION"


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only W2 canonical denominator audit")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--runtime-root", type=Path)
    source.add_argument("--baseline-manifest", type=Path)
    args = parser.parse_args()
    payload = audit_denominators(
        load_records(
            runtime_root=args.runtime_root,
            baseline_manifest=args.baseline_manifest,
        )
    )
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
    return 2 if payload["performance_integrity"]["status"] == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
