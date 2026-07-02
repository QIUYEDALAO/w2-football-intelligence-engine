#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED = [
    "scripts/run_stage4b_live_smoke.py",
    "docs/runbooks/LIVE_INGESTION_VERIFIED.md",
]
REPORT_ARTIFACTS = [
    "reports/W2_STAGE4B_REQUEST_AUDIT.json",
    "reports/W2_STAGE4B_DATA_QUALITY.json",
    "reports/W2_STAGE4B_RESULT.md",
]


def fail(message: str) -> None:
    print(f"W2 Stage4B live smoke check FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> int:
    for path in REQUIRED:
        if not (ROOT / path).is_file():
            fail(f"missing {path}")
    if "runtime/live_smoke" not in (ROOT / ".gitignore").read_text(encoding="utf-8"):
        fail("runtime live smoke path must be gitignored")
    if all((ROOT / path).is_file() for path in REPORT_ARTIFACTS):
        audit = json.loads((ROOT / "reports/W2_STAGE4B_REQUEST_AUDIT.json").read_text())
        quality = json.loads((ROOT / "reports/W2_STAGE4B_DATA_QUALITY.json").read_text())
        result = (ROOT / "reports/W2_STAGE4B_RESULT.md").read_text(encoding="utf-8")
        if len(audit) > 20:
            fail("request count exceeded target")
        if any("authorization" in json.dumps(item).lower() for item in audit):
            fail("authorization header leaked into audit")
        if "W2_API_FOOTBALL_API_KEY" in json.dumps(audit) + json.dumps(quality) + result:
            fail("environment variable name leaked into reports")
        if quality.get("request_count") != len(audit):
            fail("request count mismatch")
        if quality.get("discovery_request_count") is None:
            fail("missing discovery request count")
        if quality.get("data_request_count") is None:
            fail("missing data request count")
        if quality.get("auth_probe_request_count") is None:
            fail("missing auth probe request count")
        if "local_fixture_discovery" not in quality:
            fail("missing local fixture discovery diagnostic")
        local = quality["local_fixture_discovery"]
        required_local_fields = [
            "scanned_files",
            "records_read",
            "kickoff_parse_success",
            "kickoff_parse_failed",
            "future_count",
            "past_count",
            "now_utc",
            "earliest_kickoff",
            "latest_kickoff",
        ]
        if not all(field in local for field in required_local_fields):
            fail("local fixture discovery diagnostic is incomplete")
        if len(audit) == 0 and "live ingestion data-link smoke completed" in result.lower():
            fail("zero-request run cannot be reported as verified")
        if quality.get("gate2") == "CLOSED":
            required = [
                quality.get("request_count", 0) > 0,
                quality.get("data_request_count", 0) >= 2,
                quality.get("odds_observation_count", 0) > 0,
                quality.get("second_replay_new_odds") == 0,
                quality.get("second_replay_new_mappings") == 0,
                quality.get("post_kickoff_pre_match_odds_rejected") is True,
                quality.get("feature_result_leakage") is False,
                quality.get("as_of_time_before_kickoff") is True,
                quality.get("odds_ranges_ok") is True,
                quality.get("bookmaker_count", 0) > 0,
            ]
            if not all(required):
                fail("Gate 2 CLOSED conditions are inconsistent")
    print("W2 Stage4B live smoke check PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
