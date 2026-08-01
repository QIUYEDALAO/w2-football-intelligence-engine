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

from w2.operations.gate_a_evidence import (  # noqa: E402
    GateAEvidenceError,
    validate_gate_a_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    args = parser.parse_args()
    try:
        payload = json.loads(args.evidence.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise GateAEvidenceError("GATE_A_EVIDENCE_SCHEMA_INVALID")
        validate_gate_a_evidence(payload)
    except (OSError, json.JSONDecodeError, GateAEvidenceError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print("GATE_A_OFFLINE_EVIDENCE_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
