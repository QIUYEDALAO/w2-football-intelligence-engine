from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from w2.providers.api_football import ApiFootballClient  # noqa: E402
from w2.tracking.outcome_result_refresh import (  # noqa: E402
    run_outcome_result_refresh,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Refresh terminal fixture results and settle pending validation ledger rows."
    )
    parser.add_argument("--runtime-root", type=Path, default=Path("runtime"))
    parser.add_argument("--max-fixtures", type=int, default=20)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--write-artifacts", action="store_true")
    args = parser.parse_args()
    if not args.live:
        parser.error("--live is required because current fixture status must be verified")
    if args.write_artifacts and args.dry_run:
        parser.error("--write-artifacts requires --no-dry-run")
    payload = run_outcome_result_refresh(
        runtime_root=args.runtime_root,
        client=ApiFootballClient(
            allow_live=True,
            allowed_live_endpoints=frozenset({"fixtures"}),
        ),
        dry_run=args.dry_run,
        write_artifacts=args.write_artifacts,
        max_fixtures=args.max_fixtures,
    )
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if payload["status"] in {"PASS", "PARTIAL", "NO_DUE_WORK"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
