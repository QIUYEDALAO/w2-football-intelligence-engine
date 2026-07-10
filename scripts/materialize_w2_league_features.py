from __future__ import annotations

import argparse
import json
from pathlib import Path

from w2.features.offline_materialization import materialize_from_pro_cache

TMP_ROOT = Path("/tmp").resolve()  # noqa: S108 - approved non-repository output boundary


def main() -> int:
    parser = argparse.ArgumentParser(description="Materialize W2 league features offline")
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--fixture-id", action="append", required=True)
    parser.add_argument("--out-file", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    out_file = args.out_file.resolve()
    if not out_file.is_relative_to(TMP_ROOT):
        raise SystemExit("OUT_FILE_MUST_BE_UNDER_TMP")
    result = materialize_from_pro_cache(
        raw_root=args.raw_root,
        target_fixture_ids=tuple(str(value) for value in args.fixture_id),
    )
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(
        json.dumps(result.payload(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary = {**result.summary(), "out_file": str(out_file)}
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    else:
        print(f"status {'PASS' if not result.blockers else 'BLOCKED'}")
        print(f"rolling_snapshot_count {len(result.snapshots)}")
        print(f"out_file {out_file}")
    return 0 if not result.blockers else 2


if __name__ == "__main__":
    raise SystemExit(main())
