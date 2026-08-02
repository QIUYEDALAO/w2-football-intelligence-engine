#!/usr/bin/env python3
"""JSON transport for the existing independent Oracle; contains no algorithm."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ORACLE_DIR = Path(__file__).resolve().parents[1] / "oracle"
sys.path.insert(0, str(ORACLE_DIR))

from canonical_serialization_oracle import (  # type: ignore[import-not-found]  # noqa: E402
    bootstrap_seed,
    canonical_sha256,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract-version", required=True)
    parser.add_argument("--pair", nargs=10, action="append", default=[])
    args = parser.parse_args()
    if any(name == "w2" or name.startswith("w2.") for name in sys.modules):
        raise RuntimeError("INDEPENDENT_ORACLE_IMPORTED_PRODUCTION")
    identities = [
        {
            "canonical_fixture_id": _decode(values[0]),
            "competition_id": _decode(values[1]),
            "season_id": _decode(values[2]),
            "provider_id": _decode(values[3]),
            "bookmaker_id": _decode(values[4]),
            "market": _decode(values[5]),
            "selection": _decode(values[6]),
            "exact_line": float.fromhex(_decode(values[7])),
            "pre_evaluation_id": _decode(values[8]),
            "post_evaluation_id": _decode(values[9]),
        }
        for values in args.pair
    ]
    hashes = [
        canonical_sha256(
            identity,
            version="w2.canonical-json.v2",
            domain="eval_02b.pair_identity",
        )
        for identity in identities
    ]
    seed = bootstrap_seed(args.contract_version, hashes)
    json.dump(
        {
            "pair_identity_sha256": hashes,
            "bootstrap_seed": seed.seed,
            "bootstrap_seed_hash": seed.seed_hash,
            "production_imported": False,
        },
        sys.stdout,
        sort_keys=True,
    )
    return 0


def _decode(value: str) -> str:
    return bytes.fromhex(value).decode("utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
