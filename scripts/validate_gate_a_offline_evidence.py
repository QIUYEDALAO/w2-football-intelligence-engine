#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from w2.operations.gate_a import GateAError, GateARuntimeAuthorization  # noqa: E402
from w2.operations.gate_a_evidence import (  # noqa: E402
    GateAEvidenceError,
    validate_gate_a_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--authorization-file", type=Path, required=True)
    args = parser.parse_args()
    try:
        authorization = GateARuntimeAuthorization.load(args.authorization_file)
        payload = json.loads(args.evidence.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise GateAEvidenceError("GATE_A_EVIDENCE_SCHEMA_INVALID")
        validate_gate_a_evidence(
            payload,
            authorization=authorization,
            authorization_source_sha256=_file_sha256(args.authorization_file),
        )
    except (OSError, json.JSONDecodeError, GateAError, GateAEvidenceError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print("GATE_A_ADMISSION_EVIDENCE_VALID")
    return 0


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
