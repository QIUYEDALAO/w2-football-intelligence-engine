from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from w2.features.staging_materialization_injection import inject_staging_materialization
from w2.infrastructure.database import create_engine


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Dry-run or transactionally inject an offline feature materialization"
    )
    parser.add_argument("--materialization-file", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    payload = json.loads(args.materialization_file.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit("MATERIALIZATION_OBJECT_REQUIRED")
    report = inject_staging_materialization(
        engine=create_engine(),
        payload=payload,
        environment=os.getenv("W2_ENVIRONMENT", ""),
        apply=args.apply,
    )
    output = report.as_dict()
    if args.json:
        print(json.dumps(output, ensure_ascii=False, sort_keys=True, default=str))
    else:
        print(f"mode {output['mode']}")
        print(f"materialization_id {output['materialization_id']}")
        print(f"ready_fixture_count {len(output['ready_fixture_ids'])}")
        print(f"match_rows_inserted {output['match_rows_inserted']}")
        print(f"snapshot_rows_inserted {output['snapshot_rows_inserted']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
