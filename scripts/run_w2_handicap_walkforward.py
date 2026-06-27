from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from w2.backtest.s2_gate import S2_MIN_COVERED_SETTLED_SAMPLE  # noqa: E402


def dry_run_payload() -> dict[str, Any]:
    return {
        "samples": 0,
        "n_min": S2_MIN_COVERED_SETTLED_SAMPLE,
        "beats_market": False,
        "reason": "INSUFFICIENT_VALIDATED_SAMPLES",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run W2 handicap walk-forward audit.")
    parser.add_argument("--dry-run", action="store_true", help="Emit the Wave-1 skeleton payload.")
    args = parser.parse_args()
    if not args.dry_run:
        parser.error("only --dry-run is supported in Wave-1")
    print(json.dumps(dry_run_payload(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
