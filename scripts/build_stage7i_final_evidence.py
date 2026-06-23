#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from w2.monitoring.stage7i_lifecycle import build_final_evidence  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Stage7I final evidence JSON.")
    parser.add_argument("--runtime-dir", type=Path, required=True)
    parser.add_argument("--fixture-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    payload = build_final_evidence(args.runtime_dir, expected_fixture_id=args.fixture_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": payload["status"], "blockers": payload["blockers"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
