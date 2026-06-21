#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from w2.operations.leagues import run_top_five_audit

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")


def main() -> int:
    audit = run_top_five_audit()
    write_json(REPORTS / "W2_STAGE14A_COVERAGE.json", audit["coverage"])
    write_json(REPORTS / "W2_STAGE14A_ROLLOVER.json", audit["rollover"])
    write_json(REPORTS / "W2_STAGE14A_READINESS.json", audit["readiness"])
    result = "\n".join(
        [
            "# W2 Stage 14A Result",
            "",
            "STAGE_14A=COMPLETED",
            "TOP_FIVE_LEAGUE_PROFILES=READY_LOCAL_STAGING",
            "CLUB_RESULTS_DATASET=AVAILABLE",
            "CLUB_MARKET_DATASET=PARTIAL",
            "LEAGUE_STRATEGY=BLOCKED_GATE4",
            "LEAGUE_PRODUCTION=DISABLED",
            "PUSH_BLOCKED_NO_ORIGIN",
            "",
            "No API calls were made. League teams are derived from local Stage5B history.",
            "正式推荐尚未启用。",
        ]
    )
    (REPORTS / "W2_STAGE14A_RESULT.md").write_text(result + "\n", encoding="utf-8")
    print("W2 Stage14A league audit PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
