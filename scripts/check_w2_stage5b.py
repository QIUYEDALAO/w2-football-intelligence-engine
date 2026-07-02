#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED = [
    "scripts/import_stage5b_historical_data.py",
    "scripts/check_w2_stage5b.py",
    "docs/runbooks/STAGE5_HISTORICAL_REFRESH.md",
]
REPORT_ARTIFACTS = [
    "reports/W2_STAGE5B_SOURCE_MANIFEST.json",
    "reports/W2_STAGE5B_NATIONAL_DATA_QUALITY.json",
    "reports/W2_STAGE5B_CLUB_DATA_QUALITY.json",
    "reports/W2_STAGE5B_MARKET_COVERAGE.json",
    "reports/W2_STAGE5B_API_USAGE.json",
    "reports/W2_STAGE5B_MAPPING_REVIEW_QUEUE.json",
    "reports/W2_STAGE5B_RESULT.md",
]


def fail(message: str) -> None:
    print(f"W2 Stage5B check FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def load(path: str) -> object:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def main() -> int:
    for path in REQUIRED:
        if not (ROOT / path).is_file():
            fail(f"missing {path}")
    if all((ROOT / path).is_file() for path in REPORT_ARTIFACTS):
        source_manifest = load("reports/W2_STAGE5B_SOURCE_MANIFEST.json")
        national = load("reports/W2_STAGE5B_NATIONAL_DATA_QUALITY.json")
        club = load("reports/W2_STAGE5B_CLUB_DATA_QUALITY.json")
        market = load("reports/W2_STAGE5B_MARKET_COVERAGE.json")
        usage = load("reports/W2_STAGE5B_API_USAGE.json")
        result = (ROOT / "reports/W2_STAGE5B_RESULT.md").read_text(encoding="utf-8")
        if "W2_API_FOOTBALL_API_KEY" in json.dumps(usage) + result:
            fail("API key environment name leaked into report")
        if "x-apisports-key" in json.dumps(usage).lower():
            fail("auth header leaked into report")
        sources = {item["source_id"] for item in source_manifest["sources"]}  # type: ignore[index]
        for source in {
            "w1_international_dataset_csv",
            "w1_world_cup_odds_historical_csv",
            "w1_2026_odds_snapshots",
        }:
            if source not in sources:
                fail(f"missing source {source}")
        if national.get("status") == "BLOCKED_BEFORE_IMPORT":
            if "BLOCKER" not in result:
                fail("blocked import must be reported")
        else:
            if national.get("row_count", 0) < 1000:
                fail("national import row count too small")
            if national.get("football_data_1x2_semantics") != "UNKNOWN_PREMATCH_AGGREGATE":
                fail("Football-Data 1X2 semantics must be UNKNOWN_PREMATCH_AGGREGATE")
            if national.get("pre_match_feature_result_leakage") is not False:
                fail("pre-match feature leakage guard failed")
            if national.get("historical_ou", {}).get("matched", 0) > 128:
                fail("historical OU must not extrapolate beyond W1 source")
            low_mapping_without_blocker = (
                national.get("mapping_rate", 0) < 0.95
                and "NATIONAL_FIXTURE_MAPPING_RATE_BELOW_95_PERCENT" not in result
            )
            if low_mapping_without_blocker:
                fail("low mapping rate must be blocker")
        if club.get("CLUB_RESULTS_DATASET") not in {"AVAILABLE", "BLOCKED"}:
            fail("club results dataset status missing")
        if club.get("CLUB_MARKET_DATASET") not in {"PARTIAL_COVERAGE", "AVAILABLE"}:
            fail("club market dataset status missing")
        if market.get("historical_ah_fabricated") is not False:
            fail("historical AH must not be fabricated")
        if usage.get("requests_used", 0) > usage.get("stage5b_allowed_requests", 0):
            fail("API usage exceeded Stage5B budget")
    gitignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for path in ("runtime/stage5b/", "data/raw/", "data/processed/"):
        if path not in gitignored:
            fail(f"missing gitignore entry {path}")
    print("W2 Stage5B check PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
