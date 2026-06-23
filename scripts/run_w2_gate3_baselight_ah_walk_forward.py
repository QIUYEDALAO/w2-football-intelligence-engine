#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from w2.markets.baselight_limited_ah import (
    DATE_ONLY_LIMITATIONS,
    build_manifest,
    build_walk_forward,
    normalize_observations,
    rows_from_sample,
)

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
DEFAULT_SAMPLE_DIR = Path(
    "/Users/liudehua/.openclaw/workspace/w2_external_data/baselight_gate3_limited_ah"
)
MANIFEST_PATH = REPORTS / "W2_GATE3_BASELIGHT_LIMITED_AH_EXTRACT_MANIFEST.json"
WALK_FORWARD_PATH = REPORTS / "W2_GATE3_BASELIGHT_AH_WALK_FORWARD.json"
RESULT_PATH = REPORTS / "W2_GATE3_BASELIGHT_AH_WALK_FORWARD_RESULT.md"
PRESERVED_MANIFEST_FIELDS = {
    "async_job_recovery_status",
    "extraction_attempt_status",
    "get_results_status",
    "mcp_effective_page_size",
    "mcp_probe_path",
    "mcp_sql_tool_name",
    "micro_batch_enabled",
    "micro_batch_status",
    "sample_file_exists",
    "sample_path_external",
}


def discover_sample(sample_path: str | None) -> Path | None:
    if sample_path:
        path = Path(sample_path)
        return path if path.is_file() else None
    candidate_names = (
        "baselight_limited_ah.csv",
        "baselight_limited_ah.jsonl",
        "sample.csv",
        "sample.jsonl",
    )
    for name in candidate_names:
        path = DEFAULT_SAMPLE_DIR / name
        if path.is_file():
            return path
    return None


def write_reports(sample_path: Path | None) -> tuple[dict, dict]:
    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    previous_manifest = {}
    if MANIFEST_PATH.is_file():
        previous_manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    observations = []
    errors = {}
    if sample_path is not None:
        rows = rows_from_sample(sample_path)
        observations, error_counter = normalize_observations(rows)
        errors = dict(sorted(error_counter.items()))
    manifest = build_manifest(sample_path, observations)
    manifest.update(
        {
            "generated_at_utc": generated_at,
            "source_tables": {
                "odds": "@blt.ultimate_soccer_dataset.match_betting_odds",
                "matches": "@blt.ultimate_soccer_dataset.matches",
            },
            "sample_required_path": str(DEFAULT_SAMPLE_DIR),
            "normalization_errors": errors,
        }
    )
    for field in PRESERVED_MANIFEST_FIELDS:
        if field in previous_manifest and field not in manifest:
            manifest[field] = previous_manifest[field]
    walk_forward = build_walk_forward(observations)
    micro_batch_status = manifest.get("micro_batch_status")
    if (
        micro_batch_status == "PARTIAL_SAMPLE_INSUFFICIENT"
        or manifest.get("extraction_attempt_status") == "MICRO_BATCH_PARTIAL_SAMPLE_INSUFFICIENT"
    ):
        manifest["micro_batch_enabled"] = manifest.get("micro_batch_enabled", True)
        manifest["micro_batch_status"] = "PARTIAL_SAMPLE_INSUFFICIENT"
        walk_forward["limited_extract_status"] = manifest.get("extraction_attempt_status")
        walk_forward["mcp_probe_status"] = "PASS"
        walk_forward["sample_path_external"] = manifest.get("sample_path_external")
        blocker = "BASELIGHT_MICRO_BATCH_PARTIAL_SAMPLE_INSUFFICIENT"
        if blocker not in walk_forward["blockers"]:
            walk_forward["blockers"].append(blocker)
    if manifest.get("extraction_attempt_status") == "BASELIGHT_LIMITED_AH_EXTRACT_QUERY_PENDING":
        walk_forward["limited_extract_status"] = manifest["extraction_attempt_status"]
        walk_forward["mcp_probe_status"] = "PASS"
        walk_forward["sample_path_external"] = manifest.get("sample_path_external")
        if "BASELIGHT_LIMITED_AH_EXTRACT_QUERY_PENDING" not in walk_forward["blockers"]:
            walk_forward["blockers"].append("BASELIGHT_LIMITED_AH_EXTRACT_QUERY_PENDING")
    walk_forward["generated_at_utc"] = generated_at
    walk_forward["sample_path"] = str(sample_path) if sample_path else None
    walk_forward["collected_at_precision"] = "DATE_ONLY"
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    WALK_FORWARD_PATH.write_text(json.dumps(walk_forward, indent=2, sort_keys=True) + "\n")
    RESULT_PATH.write_text(
        "\n".join(
            [
                "# W2 Gate3 Baselight AH Walk-Forward Result",
                "",
                f"Generated at: `{generated_at}`",
                "",
                f"STATUS={walk_forward['status']}",
                f"SAMPLE_PATH={sample_path if sample_path else 'MISSING'}",
                f"ROW_COUNT={manifest['row_count']}",
                f"FIXTURE_COUNT={manifest['fixture_count']}",
                f"BOOKMAKER_COUNT={manifest['bookmaker_count']}",
                f"LINE_BUCKET_COUNT={manifest['line_bucket_count']}",
                f"COMPETITION_COUNT={manifest['competition_count']}",
                f"FOLD_COUNT={walk_forward['fold_count']}",
                "candidate=false",
                "formal_recommendation=false",
                "",
                "## Boundary",
                "",
                "- No full Baselight data is committed.",
                "- No provider/network call is performed.",
                "- DATE-only collected_at cannot support T-1h, T-30m, T-10m, "
                "intraday movement, or exact closing timestamp.",
                "- Gate3 remains PARTIAL unless closure checkers pass without blockers.",
                "",
                "## Remaining Limitations",
                "",
                *[f"- `{item}`" for item in DATE_ONLY_LIMITATIONS],
            ]
        )
        + "\n"
    )
    return manifest, walk_forward


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample-path")
    args = parser.parse_args()
    sample_path = discover_sample(args.sample_path)
    manifest, walk_forward = write_reports(sample_path)
    print(
        "W2 Gate3 Baselight AH walk-forward "
        f"{walk_forward['status']} rows={manifest['row_count']} "
        f"fixtures={manifest['fixture_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
