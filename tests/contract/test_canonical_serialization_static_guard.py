from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from scripts.check_canonical_serialization_authority import legacy_writer_sites

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
    assert report["production_roots"] == ["src/w2", "apps", "scripts", "migrations"]
    assert report["unauthorized_serializer_writers"] == 0
    assert report["unversioned_hash_writers"] == 0
    assert report["stale_legacy_exceptions"] == []
    assert report["migrated_implementations_remaining"] == []


def test_legacy_exceptions_are_exact_and_versioned() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))

    assert registry["legacy_profile_id"] == "w2.legacy-implicit-json.v1"
    assert "serializer_version" not in registry
    assert registry["owner"]
    assert registry["reason"]
    assert registry["test"] == "tests/contract/test_canonical_serialization_static_guard.py"
    sites = registry["sites"]
    assert sites
    assert len({(row["path"], row["symbol"]) for row in sites}) == len(sites)
    assert len({row["hash_domain"] for row in sites}) == len(sites)


@pytest.mark.parametrize(
    "relative, source, symbol",
    [
        (
            "src/w2/alias_writer.py",
            "import json as codec\n"
            "def serialize(value):\n"
            " return codec.dumps(value, sort_keys=True)\n",
            "serialize",
        ),
        (
            "src/w2/dump_writer.py",
            "from json import dump as emit\n"
            "def serialize(value, stream):\n"
            " return emit(value, stream)\n",
            "serialize",
        ),
        (
            "apps/alternate_writer.py",
            "import orjson as codec\ndef serialize_payload(value):\n return codec.dumps(value)\n",
            "serialize_payload",
        ),
        (
            "scripts/module_writer.py",
            "import json\nPAYLOAD = json.dumps({'value': 1})\n",
            "<module>",
        ),
        (
            "migrations/hash_alias.py",
            "from hashlib import sha256 as digest\n"
            "from json import dumps as encode\n"
            "def build(value):\n"
            " return digest(encode(value).encode()).hexdigest()\n",
            "build",
        ),
        (
            "src/w2/encoder_helper.py",
            "import json\n"
            "encoder = json.JSONEncoder(sort_keys=True)\n"
            "def serialize(value):\n"
            " return encoder.encode(value)\n",
            "serialize",
        ),
        (
            "src/w2/cross_function_writer.py",
            "import hashlib\n"
            "import json\n"
            "def emit(value):\n"
            " return json.dumps(value, sort_keys=True, separators=(',', ':'))\n"
            "def digest(value):\n"
            " return hashlib.sha256(emit(value).encode()).hexdigest()\n",
            "emit",
        ),
        (
            "src/w2/class_body_writer.py",
            "import json\nclass Serializer:\n payload = json.dumps({'value': 1}, sort_keys=True)\n",
            "Serializer.<class>",
        ),
    ],
)
def test_guard_detects_synthetic_serializer_bypasses(
    tmp_path: Path, relative: str, source: str, symbol: str
) -> None:
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")

    assert (relative, symbol) in legacy_writer_sites(tmp_path)
