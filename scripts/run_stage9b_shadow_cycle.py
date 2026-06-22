from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from w2.strategy.operations import run_shadow_replay
from w2.strategy.shadow import write_json

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
sys.path.insert(0, str(ROOT))

from scripts.run_stage9a_shadow_replay import demo_inputs  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Stage9B shadow-only local cycle.")
    parser.add_argument("--request-budget", type=int, default=100)
    parser.add_argument("--quota-reserve", type=int, default=1500)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.request_budget > 100:
        raise SystemExit("request budget exceeds Stage9B limit")
    if args.quota_reserve < 1500:
        raise SystemExit("quota reserve below Stage9B minimum")

    replay = run_shadow_replay(
        inputs=demo_inputs(),
        root=ROOT,
        mode="LOCAL_DRY_RUN" if args.dry_run else "LOCAL_CONTROLLED_SHADOW",
    )
    replay["server_shadow_cycle"] = {
        "status": "NO_ELIGIBLE_FORWARD_FIXTURE",
        "reason": "STAGING_DEPLOYMENT_FREEZE_ACTIVE_AND_NO_DEPLOYED_STAGE9B_CLI",
        "api_request_count": 0,
        "quota_reserve": args.quota_reserve,
        "allowed_actions": ["SHADOW_WATCH", "SHADOW_SKIP"],
    }
    write_json(REPORTS / "W2_STAGE9B_SHADOW_OPERATIONS.json", replay)
    print(json.dumps({"status": "PASS", "forward": "NO_ELIGIBLE_FORWARD_FIXTURE"}, sort_keys=True))


if __name__ == "__main__":
    main()
