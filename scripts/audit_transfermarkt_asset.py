#!/usr/bin/env python3
"""Audit a pinned Transfermarkt dataset export without database writes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from w2.lineups.value_identity import audit_transfermarkt_asset, write_json_and_md


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a source-backed Allsvenskan Transfermarkt asset manifest."
    )
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument(
        "--asset-descriptor",
        type=Path,
        required=True,
        help="Private JSON descriptor for one pinned DuckDB/CSV asset; never commit the asset.",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--competition-name", default="Allsvenskan")
    args = parser.parse_args()

    descriptor: Any = json.loads(args.asset_descriptor.read_text(encoding="utf-8"))
    if not isinstance(descriptor, dict):
        parser.error("--asset-descriptor must contain a JSON object")
    result = audit_transfermarkt_asset(
        source_root=args.source_root,
        asset_descriptor=descriptor,
        competition_name=args.competition_name,
    )
    write_json_and_md(result, args.output)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
