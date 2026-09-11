#!/usr/bin/env python3
"""Run diff whitespace checks while preserving immutable evidence artifacts.

Five historical evidence files contain intentional trailing spaces.  Their
contents are pinned here so the allowlist cannot become a general whitespace
escape hatch.  Every other path is checked by the normal ``git diff --check``.
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

HISTORICAL_EVIDENCE_SHA256 = {
    "docs/review_packages/W2_REPLAY_EVIDENCE_20260908/changes.patch":
        "51b1f0730ed45612945a533940f195b873e2ff094367eac0e4f143a96dcd2cee",
    "docs/review_packages/W2_OFFICIAL_CANDIDATE_ACCURACY_REMEDIATION_20260909/DISPATCH.md":
        "761208c67c9215ccc45b4c4ff3d8bb98534dd87bea3f003854fcb0b2bf5dccb6",
    "docs/review_packages/W2_OFFICIAL_CANDIDATE_ACCURACY_REMEDIATION_20260909/REMEDIATION_DISPATCH_V1_1.md":
        "463c08d8b90b62c662aa3a89a5308cdd3336a54cc57d991e9adae0cdc22d9004",
    "docs/review_packages/SC21_FACTOR_INPUT_CHAIN/R17_P0_QUOTA_UNDERESTIMATE_AND_PROVIDER_LIMIT_AUDIT.md":
        "5a4eacd35106e52d46bc0815cc1c0d3cc3fba04f10f76b5450e139b85827db4a",
    "docs/review_packages/SC21_FACTOR_INPUT_CHAIN/R19_PROVIDER_DISPATCH_AND_QUOTA_DEGRADATION_CLOSURE.md":
        "c95b6615088daaed6881928f78481526414bc44c2b3d09cbf1154b40879ad815",
}


def verify_historical_evidence() -> None:
    for relative, expected in HISTORICAL_EVIDENCE_SHA256.items():
        path = ROOT / relative
        if not path.is_file():
            raise SystemExit(f"historical evidence missing: {relative}")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise SystemExit(
                f"historical evidence hash changed: {relative}: {actual} != {expected}"
            )


def check_diff(base: str, head: str) -> None:
    verify_historical_evidence()
    excludes = [f":(exclude){path}" for path in HISTORICAL_EVIDENCE_SHA256]
    command = ["git", "diff", "--check", f"{base}...{head}", "--", ".", *excludes]
    subprocess.run(command, cwd=ROOT, check=True)
    print("historical evidence allowlist and diff check PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    args = parser.parse_args()
    check_diff(args.base, args.head)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
