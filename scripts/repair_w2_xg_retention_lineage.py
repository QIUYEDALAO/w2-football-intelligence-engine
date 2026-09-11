from __future__ import annotations

import argparse
import json
from pathlib import Path

from w2.ingestion.xg_retention import XgRetentionHardeningService


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup", type=Path)
    args = parser.parse_args()
    result = XgRetentionHardeningService().repair_derived_lineage(
        dry_run=not args.apply,
        write_db=args.apply,
        backup_path=args.backup,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
