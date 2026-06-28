from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from w2.ingestion.market_timeline_refresh import run_market_timeline_refresh  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Build W2 market timeline lock snapshots.")
    parser.add_argument("--window", default="next36", choices=["today", "next36", "all"])
    parser.add_argument("--checkpoint", default="auto")
    parser.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--write-artifacts", action="store_true")
    parser.add_argument("--runtime-root", type=Path)
    parser.add_argument("--remaining-quota-override")
    parser.add_argument("--max-fixtures", type=int)
    parser.add_argument("--network-quota-required", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    payload = run_market_timeline_refresh(
        window=args.window,
        checkpoint=args.checkpoint,
        dry_run=args.dry_run,
        write_artifacts=args.write_artifacts,
        max_fixtures=args.max_fixtures,
        runtime_root=args.runtime_root,
        remaining_quota_override=args.remaining_quota_override,
        network_quota_required=args.network_quota_required,
    )
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
