#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from w2.monitoring.stage7i_lifecycle import (  # noqa: E402
    LifecycleConfig,
    Stage7ILifecycleCollector,
    parse_utc,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture Stage7I fixture lifecycle evidence.")
    parser.add_argument("--runtime-dir", type=Path, required=True)
    parser.add_argument("--fixture-id", required=True)
    parser.add_argument("--scheduled-kickoff-utc", required=True)
    parser.add_argument("--source-revision", default="LOCAL_UNDEPLOYED")
    parser.add_argument("--quota-reserve", type=int, default=1500)
    parser.add_argument("--request-budget", type=int, default=None)
    parser.add_argument("--interval-seconds", type=int, default=300)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    kickoff = parse_utc(args.scheduled_kickoff_utc)
    if kickoff is None:
        raise SystemExit("scheduled kickoff must be timezone-aware UTC")
    config = LifecycleConfig(
        runtime_dir=args.runtime_dir,
        fixture_id=args.fixture_id,
        scheduled_kickoff_utc=kickoff.astimezone(UTC),
        quota_reserve=args.quota_reserve,
        request_budget=args.request_budget,
        interval_seconds=args.interval_seconds,
        source_revision=args.source_revision,
    )
    collector = Stage7ILifecycleCollector(config=config)
    if args.once:
        result = collector.probe_once()
        print(json.dumps(result.__dict__, sort_keys=True))
        return 0 if not result.blockers else 1
    collector.run_loop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
