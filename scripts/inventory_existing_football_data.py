#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from w2.historical.existing_data_inventory import (
    build_existing_football_data_inventory,
    write_inventory_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Inventory existing W2 football data.")
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--database-url")
    args = parser.parse_args()
    payload = build_existing_football_data_inventory(
        repo_root=Path("."),
        database_url=args.database_url,
    )
    write_inventory_outputs(
        payload,
        json_path=args.artifact_root / "EXISTING_FOOTBALL_DATA_INVENTORY.json",
        md_path=args.artifact_root / "EXISTING_FOOTBALL_DATA_INVENTORY.md",
    )
    print(payload["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
