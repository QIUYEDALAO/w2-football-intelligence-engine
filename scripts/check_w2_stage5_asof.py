#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED = [
    "src/w2/historical/registry.py",
    "src/w2/historical/dataset.py",
    "src/w2/historical/adapters.py",
    "src/w2/historical/builder.py",
    "src/w2/historical/leakage.py",
    "src/w2/historical/quality.py",
    "src/w2/historical/splitters.py",
    "src/w2/infrastructure/persistence/historical_models.py",
    "migrations/versions/0004_create_stage5_asof_foundation.py",
    "docs/adr/ADR-0005-historical-asof-dataset.md",
    "docs/data/W2_ASOF_DATASET_V1.md",
    "docs/data/W2_HISTORICAL_SOURCE_REGISTRY_V1.md",
    "docs/data/W2_LEAKAGE_POLICY_V1.md",
    "docs/runbooks/HISTORICAL_DATA_IMPORT_CHECKPOINT.md",
]
REPORT_ARTIFACTS = [
    "reports/W2_STAGE5_SOURCE_COVERAGE_AUDIT.json",
    "reports/W2_STAGE5A_RESULT.md",
    "reports/W2_STAGE5A_DEMO_DATASETS.json",
]


def fail(message: str) -> None:
    print(f"W2 Stage5 as-of check FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> int:
    for path in REQUIRED:
        if not (ROOT / path).is_file():
            fail(f"missing {path}")
    combined = "\n".join(read(path) for path in REQUIRED if path.endswith((".py", ".md")))
    for token in [
        "HistoricalSourceRegistry",
        "DatasetSource",
        "DatasetVersion",
        "DatasetArtifact",
        "AsOfSample",
        "DataQualityRun",
        "CsvAdapter",
        "JsonAdapter",
        "ParquetAdapter",
        "AsOfDatasetBuilder",
        "DatasetManifestBuilder",
        "future_result",
        "closing_odds_used_before_closing",
        "chronological_split",
        "rolling_split",
        "expanding_split",
        "walk_forward_split",
    ]:
        if token not in combined:
            fail(f"missing Stage5 token {token}")
    if all((ROOT / path).is_file() for path in REPORT_ARTIFACTS):
        demo = json.loads(read("reports/W2_STAGE5A_DEMO_DATASETS.json"))
        datasets = demo.get("datasets", {})
        if set(datasets) != {"international", "club_league"}:
            fail("demo must include international and club_league datasets")
        for dataset_id, payload in datasets.items():
            manifest = payload["manifest"]
            if manifest["fixture_count"] < 2 or manifest["sample_count"] < 4:
                fail(f"{dataset_id} demo dataset is too small")
            if payload["quality_status"] != "PASS":
                fail(f"{dataset_id} quality must pass")
            if payload["leakage_findings"]:
                fail(f"{dataset_id} clean demo should have no leakage findings")
            if manifest.get("manifest_sha256") is None:
                fail(f"{dataset_id} missing manifest sha")
        audit = json.loads(read("reports/W2_STAGE5_SOURCE_COVERAGE_AUDIT.json"))
        if audit.get("audit_mode") != "read_only_inventory_no_copy":
            fail("W1 audit must be read-only no-copy")
        result = read("reports/W2_STAGE5A_RESULT.md")
        for token in [
            "STAGE_5A=COMPLETED",
            "STAGE_5=PROVISIONAL",
            "REAL_HISTORICAL_IMPORT_CHECKPOINT_REQUIRED",
            "GATE_2=CLOSED",
            "GATE_3=NOT_STARTED",
        ]:
            if token not in result:
                fail(f"missing final status {token}")
    print("W2 Stage5 as-of check PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
