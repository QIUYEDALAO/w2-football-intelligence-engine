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
    parser.add_argument(
        "--target-fixture-file",
        type=Path,
        help="Sanitized target fixtures exported separately from the history cache",
    )
    output = parser.add_mutually_exclusive_group(required=True)
    output.add_argument("--out-file", type=Path)
    output.add_argument(
        "--out-dir",
        type=Path,
        help="Write one content-addressed materialization file per target fixture",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    output_path = (args.out_file or args.out_dir).resolve()
    if not output_path.is_relative_to(TMP_ROOT):
        raise SystemExit("OUTPUT_MUST_BE_UNDER_TMP")
    if args.out_dir is not None:
        output_path.mkdir(parents=True, exist_ok=True)
        summaries = []
        blocked = False
        for fixture_id in sorted(set(str(value) for value in args.fixture_id)):
            result = materialize_from_pro_cache(
                raw_root=args.raw_root,
                target_fixture_ids=(fixture_id,),
                target_fixture_file=args.target_fixture_file,
            )
            payload = result.payload()
            materialization_id = payload["integrity"]["materialization_id"]
            out_file = output_path / f"{fixture_id}.{materialization_id}.json"
            out_file.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            summaries.append({**result.summary(), "out_file": str(out_file)})
            blocked = blocked or bool(result.blockers)
        print(json.dumps(summaries, ensure_ascii=False, sort_keys=True))
        return 2 if blocked else 0
    result = materialize_from_pro_cache(
        raw_root=args.raw_root,
        target_fixture_ids=tuple(str(value) for value in args.fixture_id),
        target_fixture_file=args.target_fixture_file,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result.payload(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary = {**result.summary(), "out_file": str(output_path)}
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    else:
        print(f"status {'PASS' if not result.blockers else 'BLOCKED'}")
        print(f"rolling_snapshot_count {len(result.snapshots)}")
        print(f"out_file {output_path}")
    return 0 if not result.blockers else 2


if __name__ == "__main__":
    raise SystemExit(main())
