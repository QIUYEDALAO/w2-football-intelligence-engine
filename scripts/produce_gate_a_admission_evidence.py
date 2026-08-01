#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from w2.infrastructure.database import create_engine  # noqa: E402
from w2.operations.gate_a_evidence_producer import produce_gate_a_evidence  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Produce Gate-A evidence from DB authorities.")
    parser.add_argument("--authorization-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    evidence = produce_gate_a_evidence(
        engine=create_engine(),
        authorization_source=args.authorization_file,
    )
    args.output.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
