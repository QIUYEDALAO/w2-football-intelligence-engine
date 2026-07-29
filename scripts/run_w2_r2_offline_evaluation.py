#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from w2.models.correction_evaluation import (
    evaluate_r2_corrections,
    load_fixed_snapshot,
    stable_evaluation_hash,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "tests/fixtures/gate4/dixon_coles_matches.json"
DEFAULT_OUTPUT = ROOT / "docs/operations/W2_R2_OFFLINE_CORRECTION_EVALUATION_20260718.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate W2 R2 corrections on a fixed snapshot")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    input_bytes = args.input.read_bytes()
    raw = json.loads(input_bytes)
    if not isinstance(raw, list):
        raise ValueError("evaluation input must be a JSON array")
    report = evaluate_r2_corrections(load_fixed_snapshot(raw))
    report["input"] = {
        "path": str(args.input.relative_to(ROOT)),
        "sha256": hashlib.sha256(input_bytes).hexdigest(),
    }
    report["artifact_sha256"] = stable_evaluation_hash(report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
