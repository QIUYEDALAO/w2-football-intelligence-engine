from __future__ import annotations

import ast
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "config/legacy_decision_allowlist.json"
ALLOWED_CATEGORIES = {"compatibility_shim", "historical_reader", "migration"}
SOURCE_ROOTS = (ROOT / "src", ROOT / "apps")


def main() -> int:
    manifest = _mapping(json.loads(MANIFEST_PATH.read_text(encoding="utf-8")))
    legacy_fields = {str(item) for item in manifest.get("legacy_fields", [])}
    allowed = _mapping(manifest.get("allowed_readers"))
    authoritative = {str(item) for item in manifest.get("authoritative_paths", [])}
    failures: list[str] = []

    for path, metadata in allowed.items():
        relative = str(path)
        details = _mapping(metadata)
        if details.get("category") not in ALLOWED_CATEGORIES:
            failures.append(f"{relative}: invalid allowlist category")
        if not str(details.get("reason") or "").strip():
            failures.append(f"{relative}: missing allowlist reason")
        if relative in authoritative:
            failures.append(f"{relative}: authoritative paths cannot be allowlisted")
        if not (ROOT / relative).is_file():
            failures.append(f"{relative}: allowlisted file does not exist")

    readers: dict[str, set[str]] = {}
    for root in SOURCE_ROOTS:
        for path in root.rglob("*"):
            if "node_modules" in path.parts or "dist" in path.parts:
                continue
            if path.suffix == ".py":
                fields = _python_reads(path, legacy_fields)
            elif path.suffix in {".ts", ".tsx"}:
                fields = _typescript_reads(path, legacy_fields)
            else:
                continue
            if fields:
                readers[str(path.relative_to(ROOT))] = fields

    for relative, fields in sorted(readers.items()):
        if relative in authoritative:
            failures.append(
                f"{relative}: authoritative path reads legacy fields {sorted(fields)}"
            )
        elif relative not in allowed:
            failures.append(
                f"{relative}: unallowlisted legacy field read {sorted(fields)}"
            )

    stale = sorted(set(allowed) - set(readers))
    for relative in stale:
        failures.append(f"{relative}: stale allowlist entry has no legacy reads")

    if failures:
        for failure in failures:
            print(f"legacy decision governance FAIL: {failure}")
        return 1
    print(f"legacy decision governance PASS: {len(readers)} explicit readers")
    return 0


def _python_reads(path: Path, legacy_fields: set[str]) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return set()
    fields: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "get" and node.args:
                field = _string_constant(node.args[0])
                if field in legacy_fields:
                    fields.add(field)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            for argument in node.args:
                field = _string_constant(argument)
                if field in legacy_fields:
                    fields.add(field)
        if isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load):
            field = _string_constant(node.slice)
            if field in legacy_fields:
                fields.add(field)
    return fields


def _typescript_reads(path: Path, legacy_fields: set[str]) -> set[str]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    fields: set[str] = set()
    for field in legacy_fields:
        escaped = re.escape(field)
        if re.search(rf"(?:\.|\[['\"]){escaped}(?:\b|['\"]\])", text):
            fields.add(field)
    return fields


def _string_constant(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


if __name__ == "__main__":
    raise SystemExit(main())
