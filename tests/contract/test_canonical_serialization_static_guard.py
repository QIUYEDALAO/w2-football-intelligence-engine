from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "config/canonical_serialization_legacy_exceptions.v1.json"


def test_canonical_serialization_authority_guard() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_canonical_serialization_authority.py"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["canonical_serializer_authority_count"] == 1
    assert report["unversioned_hash_writers"] == 0
    assert report["migrated_implementations_remaining"] == []


def test_legacy_exceptions_are_exact_and_versioned() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))

    assert registry["serializer_version"] == "w2.legacy-implicit-json.v1"
    assert registry["owner"]
    assert registry["reason"]
    assert registry["test"] == "tests/contract/test_canonical_serialization_static_guard.py"
    sites = registry["sites"]
    assert sites
    assert len({(row["path"], row["symbol"]) for row in sites}) == len(sites)
    assert len({row["hash_domain"] for row in sites}) == len(sites)
