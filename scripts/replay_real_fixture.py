#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from w2.domain.canonical_serialization import HashDomain, canonical_bytes
from w2.replay.real_fixture import replay_real_fixture_bundle

ROOT = Path(__file__).resolve().parents[1]


def _git_sha() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def _migration_head() -> str:
    config = Config(str(ROOT / "alembic.ini"))
    heads = ScriptDirectory.from_config(config).get_heads()
    if len(heads) != 1:
        raise SystemExit(f"exactly one migration head required; found {heads}")
    return heads[0]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Recompute one private real fixture twice without any network access."
    )
    parser.add_argument("--bundle-root", type=Path, required=True)
    parser.add_argument("--network-disabled", action="store_true", required=True)
    parser.add_argument("--receipt-output", type=Path)
    args = parser.parse_args()
    receipt = replay_real_fixture_bundle(
        bundle_root=args.bundle_root,
        current_git_sha=_git_sha(),
        current_migration_head=_migration_head(),
    )
    data = canonical_bytes(receipt, domain=HashDomain.FUTURE_REFRESH_EVIDENCE) + b"\n"
    if args.receipt_output is not None:
        args.receipt_output.parent.mkdir(parents=True, exist_ok=True)
        args.receipt_output.write_bytes(data)
    print(data.decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
