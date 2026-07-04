from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from w2.infrastructure.database import create_engine  # noqa: E402
from w2.infrastructure.persistence.future_refresh_models import (  # noqa: E402
    FutureMarketObservationModel,
)
from w2.markets.asian_handicap_scope import (  # noqa: E402
    is_full_time_asian_handicap_label,
    normalize_market_label,
)


def classify_legacy_ah_label(raw_label: Any) -> str:
    label = normalize_market_label(raw_label)
    if not label:
        return "LEGACY_UNSCOPED_ASIAN_HANDICAP"
    if is_full_time_asian_handicap_label(label):
        return "ASIAN_HANDICAP"
    if "corner" in label:
        return "CORNERS_ASIAN_HANDICAP"
    if "card" in label or "booking" in label or "yellow" in label:
        return "CARDS_ASIAN_HANDICAP"
    if "half" in label or "1st" in label or "first" in label:
        return "FIRST_HALF_ASIAN_HANDICAP"
    if "asian handicap" in label or "handicap" in label:
        return "LEGACY_SCOPED_NON_FULL_TIME_AH"
    return "LEGACY_UNSCOPED_ASIAN_HANDICAP"


def run(*, write: bool = False) -> dict[str, Any]:
    engine = create_engine()
    scanned = 0
    updates: list[tuple[str, str, str]] = []
    counts: dict[str, int] = {}
    with Session(engine) as session:
        rows = list(
            session.scalars(
                select(FutureMarketObservationModel)
                .where(FutureMarketObservationModel.canonical_market == "ASIAN_HANDICAP")
                .order_by(
                    FutureMarketObservationModel.fixture_id,
                    FutureMarketObservationModel.captured_at,
                )
            )
        )
        for row in rows:
            scanned += 1
            target = classify_legacy_ah_label(row.raw_market_label)
            counts[target] = counts.get(target, 0) + 1
            if target != "ASIAN_HANDICAP":
                updates.append((row.observation_id, row.raw_market_label, target))
                if write:
                    row.canonical_market = target
        if write:
            session.commit()
    return {
        "status": "PASS",
        "dry_run": not write,
        "scanned": scanned,
        "would_update": len(updates),
        "updated": len(updates) if write else 0,
        "counts": counts,
        "sample_updates": [
            {"observation_id": item[0], "raw_market_label": item[1], "target": item[2]}
            for item in updates[:20]
        ],
        "provider_calls": 0,
        "lock_capture_write": False,
        "settlement_write": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Dry-run or apply legacy AH pool cleanup for full-time AH materialization.",
    )
    parser.add_argument("--write", action="store_true", help="Apply canonical_market updates.")
    args = parser.parse_args()
    print(json.dumps(run(write=bool(args.write)), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
