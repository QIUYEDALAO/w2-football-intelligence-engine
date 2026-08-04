#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine as sqlalchemy_create_engine
from sqlalchemy.engine import Engine, make_url

from w2.config import get_settings
from w2.domain.canonical_serialization import HashDomain, canonical_bytes
from w2.infrastructure.database import create_engine
from w2.replay.real_fixture import export_real_fixture_bundle, sanitized_manifest

ROOT = Path(__file__).resolve().parents[1]


def _git_sha() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def _migration_head() -> str:
    config = Config(str(ROOT / "alembic.ini"))
    heads = ScriptDirectory.from_config(config).get_heads()
    if len(heads) != 1:
        raise SystemExit(f"exactly one migration head required; found {heads}")
    return heads[0]


def _export_engine(*, database_url_stdin: bool, host: str | None, port: int | None) -> Engine:
    if not database_url_stdin:
        if host is not None or port is not None:
            raise SystemExit("--database-host/--database-port require --database-url-stdin")
        return create_engine(get_settings())
    raw_url = sys.stdin.read().strip()
    if not raw_url or "\n" in raw_url:
        raise SystemExit("exactly one database URL is required on stdin")
    url = make_url(raw_url)
    if host is not None or port is not None:
        url = url.set(host=host or url.host, port=port or url.port)
    return sqlalchemy_create_engine(url, pool_pre_ping=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export one complete private real-fixture bundle from a read-only transaction."
    )
    parser.add_argument("--bundle-root", type=Path, required=True)
    parser.add_argument("--fixture-id")
    parser.add_argument("--database-url-stdin", action="store_true")
    parser.add_argument("--database-host")
    parser.add_argument("--database-port", type=int)
    args = parser.parse_args()
    manifest = export_real_fixture_bundle(
        engine=_export_engine(
            database_url_stdin=args.database_url_stdin,
            host=args.database_host,
            port=args.database_port,
        ),
        bundle_root=args.bundle_root,
        source_git_sha=_git_sha(),
        migration_head=_migration_head(),
        fixture_id=args.fixture_id,
    )
    # Stdout is safe to retain: no raw fixture id, team/player name, DB URL or
    # private filesystem path is present in this manifest.
    print(
        canonical_bytes(
            sanitized_manifest(manifest),
            domain=HashDomain.FUTURE_REFRESH_EVIDENCE,
        ).decode("utf-8")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
