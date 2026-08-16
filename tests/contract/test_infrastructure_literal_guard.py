from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "config/security/infrastructure_literal_exceptions.v1.json"
IPV4 = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
SKIP_PARTS = {".git", ".local", ".venv", "node_modules", "runtime"}


def _load_manifest() -> dict[str, Any]:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _text_files(root: Path) -> Iterator[Path]:
    for path in root.rglob("*"):
        if not path.is_file() or any(part in SKIP_PARTS for part in path.parts):
            continue
        try:
            path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        yield path


def _global_addresses(text: str) -> Iterator[str]:
    for candidate in IPV4.findall(text):
        try:
            address = ipaddress.ip_address(candidate)
        except ValueError:
            continue
        if address.is_global:
            yield candidate


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def test_active_scripts_and_runbooks_have_no_public_ipv4_literals() -> None:
    manifest = _load_manifest()
    findings: list[str] = []

    for relative_root in manifest["active_roots"]:
        for path in _text_files(ROOT / relative_root):
            for address in _global_addresses(path.read_text(encoding="utf-8")):
                findings.append(f"{path.relative_to(ROOT)}:{_digest(address)[:12]}")

    assert findings == []


def test_forbidden_infrastructure_addresses_are_absent_outside_archive() -> None:
    forbidden = set(_load_manifest()["forbidden_address_sha256"])
    findings: list[str] = []

    for path in _text_files(ROOT):
        relative = path.relative_to(ROOT)
        if relative.parts[:2] == ("docs", "archive"):
            continue
        for address in IPV4.findall(path.read_text(encoding="utf-8")):
            digest = _digest(address)
            if digest in forbidden:
                findings.append(f"{relative}:{digest[:12]}")

    assert findings == []


def test_archive_infrastructure_literals_have_exact_scoped_exceptions() -> None:
    manifest = _load_manifest()
    exceptions = manifest["archive_exceptions"]
    expected = {(item["path"], item["address_sha256"]) for item in exceptions}
    observed: set[tuple[str, str]] = set()

    for path in _text_files(ROOT / "docs/archive"):
        relative = str(path.relative_to(ROOT))
        for address in _global_addresses(path.read_text(encoding="utf-8")):
            observed.add((relative, _digest(address)))

    assert observed == expected
    assert len(expected) == len(exceptions)
    for item in exceptions:
        assert item["path"].startswith("docs/archive/")
        assert (ROOT / item["path"]).is_file()
        assert item["owner"].strip()
        assert item["reason"].strip()
        assert item["scope"].startswith("Exact archived file only")


def test_exception_manifest_contains_hashes_not_plaintext_addresses() -> None:
    raw = MANIFEST.read_text(encoding="utf-8")
    manifest = json.loads(raw)

    assert IPV4.search(raw) is None
    assert manifest["forbidden_address_sha256"]
    assert all(
        re.fullmatch(r"[0-9a-f]{64}", digest)
        for digest in manifest["forbidden_address_sha256"]
    )
