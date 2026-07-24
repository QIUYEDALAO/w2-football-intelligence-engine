from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from w2.ingestion.independent_signal_backfill import (
    IndependentSignalBackfillConfig,
    IndependentSignalBackfillService,
)
from w2.prematch.analysis_calculator import ReadModelRepository


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run guarded W2 independent signal backfill.")
    parser.add_argument(
        "--task",
        choices=[
            "team_fixture_history_backfill",
            "h2h_backfill",
            "squad_value_mapping",
            "ratings_backfill",
            "all",
        ],
        required=True,
    )
    parser.add_argument("--competition-id", required=True)
    parser.add_argument("--season", required=True)
    parser.add_argument("--fixture-id")
    parser.add_argument("--window", choices=["today", "next36", "all"], default="next36")
    parser.add_argument("--dry-run", dest="dry_run", action="store_true", default=True)
    parser.add_argument("--no-dry-run", dest="dry_run", action="store_false")
    parser.add_argument("--write-artifacts", action="store_true")
    parser.add_argument("--max-fixtures", type=int, default=20)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--runtime-root",
        type=Path,
        default=Path("runtime/independent_signal_backfill"),
    )
    parser.add_argument("--remaining-quota-override")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    remaining_quota: Any = args.remaining_quota_override
    config = IndependentSignalBackfillConfig(
        task=args.task,
        competition_id=args.competition_id,
        season=args.season,
        window=args.window,
        fixture_id=args.fixture_id,
        dry_run=args.dry_run,
        write_artifacts=args.write_artifacts,
        max_fixtures=args.max_fixtures,
        remaining_quota_override=remaining_quota,
        runtime_root=args.runtime_root,
    )
    service = IndependentSignalBackfillService(fixture_provider=ReadModelRepository())
    result = service.run(config)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] in {"ok", "blocked"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
