#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from w2.migration import (
    ShadowComparisonEngine,
    ShadowRunManifest,
    W1SnapshotAdapter,
    W2SnapshotAdapter,
)

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"


def main() -> int:
    manifest = ShadowRunManifest(
        run_id="stage12a-shadow-dry-run-v1",
        created_at=datetime(2026, 6, 22, tzinfo=UTC),
        w1_source="W1_FROZEN_HISTORICAL_OUTPUT_SAMPLE",
        w2_source="W2_ARCHIVED_MARKET_MODEL_OUTPUT_SAMPLE",
        strategy_comparison_status="NOT_AVAILABLE_GATE4",
    )
    payload = ShadowComparisonEngine().compare(
        manifest=manifest,
        w1_snapshot=W1SnapshotAdapter().load_sample(),
        w2_snapshot=W2SnapshotAdapter().load_sample(),
    )
    (REPORTS / "W2_STAGE12A_SHADOW_COMPARISON.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    print("W2 Stage12A shadow dry-run PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
