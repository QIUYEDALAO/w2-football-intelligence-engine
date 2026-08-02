#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
import tempfile
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from w2.domain.canonical_serialization import HashDomain, canonical_bytes  # noqa: E402
from w2.infrastructure.database import create_engine  # noqa: E402
from w2.operations.gate_a import GateAError, GateARuntimeAuthorization  # noqa: E402
from w2.operations.gate_a_evidence import (  # noqa: E402
    GateAEvidenceError,
    validate_gate_a_evidence,
)
from w2.operations.gate_a_evidence_producer import produce_gate_a_evidence  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authorization-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--compare-evidence", type=Path)
    args = parser.parse_args()
    try:
        authorization = GateARuntimeAuthorization.load(args.authorization_file)
        payload = produce_gate_a_evidence(
            engine=create_engine(),
            authorization_source=args.authorization_file,
        )
        validate_gate_a_evidence(
            payload,
            authorization=authorization,
            authorization_source_sha256=_file_sha256(args.authorization_file),
        )
        if args.compare_evidence is not None:
            archived = json.loads(args.compare_evidence.read_text(encoding="utf-8"))
            if not isinstance(archived, dict) or not hmac.compare_digest(
                _canonical_evidence(archived), _canonical_evidence(payload)
            ):
                raise GateAEvidenceError("CALLER_EVIDENCE_DB_RECOMPUTE_MISMATCH")
        _write_atomic(args.output, payload)
    except (
        OSError,
        json.JSONDecodeError,
        SQLAlchemyError,
        GateAError,
        GateAEvidenceError,
    ) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print("GATE_A_ADMISSION_EVIDENCE_VALID")
    return 0


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_evidence(payload: dict[str, object]) -> bytes:
    return canonical_bytes(payload, domain=HashDomain.FUTURE_REFRESH_EVIDENCE)


def _write_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False).encode() + b"\n"
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as output:
            temporary = output.name
            output.write(encoded)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and os.path.exists(temporary):
            os.unlink(temporary)


if __name__ == "__main__":
    raise SystemExit(main())
