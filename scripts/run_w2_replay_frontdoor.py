from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from w2.replay.front_door import build_replay_front_door


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a read-only W2 replay front-door envelope.")
    parser.add_argument("--football-day", required=True)
    parser.add_argument("--env", default="staging", dest="environment")
    parser.add_argument("--day-view-json", type=Path)
    parser.add_argument("--audit-manifest-json", type=Path)
    parser.add_argument("--audit-tables-json", type=Path)
    parser.add_argument("--outcomes-json", type=Path)
    parser.add_argument("--json", action="store_true", default=False, dest="json_output")
    args = parser.parse_args()

    payload = build_replay_front_door(
        football_day=args.football_day,
        environment=args.environment,
        day_view=_optional_mapping_file(args.day_view_json),
        audit_manifest=_optional_mapping_file(args.audit_manifest_json),
        audit_tables=_audit_tables(args.audit_tables_json),
        outcomes=_optional_sequence_file(args.outcomes_json),
    )
    indent = None if args.json_output else 2
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=indent))
    return 0


def _optional_mapping_file(path: Path | None) -> Mapping[str, Any] | None:
    if path is None:
        return None
    payload = _load_json(path)
    if not isinstance(payload, Mapping):
        raise SystemExit(f"{path} must contain a JSON object")
    return payload


def _audit_tables(path: Path | None) -> Mapping[str, Any] | None:
    payload = _optional_mapping_file(path)
    if payload is None:
        return None
    nested = payload.get("tables")
    return nested if isinstance(nested, Mapping) else payload


def _optional_sequence_file(path: Path | None) -> Sequence[Mapping[str, Any]] | None:
    if path is None:
        return None
    payload = _load_json(path)
    if isinstance(payload, Mapping):
        payload = payload.get("outcomes")
    if not isinstance(payload, Sequence) or isinstance(payload, str | bytes | bytearray):
        raise SystemExit(f"{path} must contain a JSON array or object with outcomes[]")
    rows = [item for item in payload if isinstance(item, Mapping)]
    return rows


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    sys.exit(main())
