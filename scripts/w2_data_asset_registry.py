#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from w2.data_assets.registry import build_football_data_registry, write_registry


def main() -> int:
    parser = argparse.ArgumentParser(description="Build W2 data asset registry entries.")
    parser.add_argument("--asset", choices=["football-data"], default="football-data")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    registry = build_football_data_registry()
    payload = registry.as_dict()
    if args.output:
        write_registry(args.output, registry)
    if args.json or not args.output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
