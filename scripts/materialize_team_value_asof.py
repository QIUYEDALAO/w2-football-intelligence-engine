#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from w2.lineups.value_identity import (
    identity_value_audit,
    import_team_crosswalk_file,
    materialize_team_value_asof,
    write_json_and_md,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build offline TeamValueAsOf artifacts.")
    parser.add_argument("--fixture-as-of-file", type=Path, required=True)
    parser.add_argument("--crosswalk-file", type=Path)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--database-url")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    fixtures = json.loads(args.fixture_as_of_file.read_text(encoding="utf-8"))
    if isinstance(fixtures, dict):
        fixtures = fixtures.get("fixtures", [])
    crosswalks = import_team_crosswalk_file(args.crosswalk_file) if args.crosswalk_file else []
    artifacts = [
        materialize_team_value_asof(
            fixture=fixture,
            crosswalks=crosswalks,
            source_root=args.source_root,
        )
        for fixture in fixtures
        if isinstance(fixture, dict)
    ]
    args.output_root.mkdir(parents=True, exist_ok=True)
    (args.output_root / "team_value_asof_artifacts.json").write_text(
        json.dumps(artifacts, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    audit = identity_value_audit(
        crosswalks=crosswalks,
        artifacts=artifacts,
        source_root=args.source_root,
    )
    write_json_and_md(audit, args.output_root / "FAH04_IDENTITY_VALUE_AUDIT.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
