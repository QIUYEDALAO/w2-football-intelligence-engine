#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from w2.readiness.league_market import build_league_market_readiness


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the read-only 13-league AH/OU readiness truth matrix.",
    )
    parser.add_argument("--evidence-json", type=Path)
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=Path("runtime/model_artifacts/r4_1"),
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()
    payload = build_league_market_readiness(
        evidence_path=args.evidence_json,
        artifact_dir=args.artifact_dir,
    )
    print(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            indent=None if args.json_output else 2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
