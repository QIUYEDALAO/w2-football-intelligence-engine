from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "config/canonical_serialization_legacy_exceptions.v1.json"
MIGRATED_IMPLEMENTATIONS = {
    ("src/w2/ingestion/future_refresh.py", "canonical_json"),
    ("src/w2/tracking/outcome_ledger_repository.py", "canonical_json"),
    ("src/w2/monitoring/stage7i_lifecycle.py", "canonical_json"),
    ("src/w2/monitoring/stage7i_supervision.py", "canonical_json"),
    ("src/w2/prematch/read_model_projection.py", "canonical_json_bytes"),
    ("src/w2/prematch/repository.py", "_pair_sha256"),
}


def _call_name(node: ast.Call) -> str:
    try:
        return ast.unparse(node.func)
    except ValueError:
        return ""


def legacy_writer_sites(root: Path = ROOT) -> set[tuple[str, str]]:
    sites: set[tuple[str, str]] = set()
    authority = "src/w2/domain/canonical_serialization.py"
    for path in sorted((root / "src/w2").rglob("*.py")):
        relative = path.relative_to(root).as_posix()
        if relative == authority:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            calls = {
                _call_name(child)
                for child in ast.walk(node)
                if isinstance(child, ast.Call)
            }
            is_writer = "json.dumps" in calls and (
                "hashlib.sha256" in calls
                or "canonical" in node.name.lower()
                or "hash" in node.name.lower()
            )
            if is_writer:
                sites.add((relative, node.name))
    return sites


def authority_report(root: Path = ROOT) -> dict[str, Any]:
    registry = json.loads((root / REGISTRY.relative_to(ROOT)).read_text(encoding="utf-8"))
    registered_rows = registry["sites"]
    registered = {(row["path"], row["symbol"]) for row in registered_rows}
    discovered = legacy_writer_sites(root)
    authority_path = root / registry["authority_path"]
    authority_tree = ast.parse(authority_path.read_text(encoding="utf-8"))
    authority_functions = {
        node.name for node in ast.walk(authority_tree) if isinstance(node, ast.FunctionDef)
    }
    required_metadata = ("serializer_version", "owner", "reason", "test")
    invalid_metadata = [field for field in required_metadata if not registry.get(field)]
    domains = [str(row.get("hash_domain") or "") for row in registered_rows]
    invalid_domains = [domain for domain in domains if not domain.startswith("legacy.")]
    return {
        "canonical_serializer_authority_count": int(
            {"canonical_bytes", "canonical_sha256"} <= authority_functions
        ),
        "unversioned_hash_writers": len(discovered - registered),
        "stale_legacy_exceptions": sorted(registered - discovered),
        "unexpected_legacy_writers": sorted(discovered - registered),
        "duplicate_legacy_sites": len(registered_rows) - len(registered),
        "duplicate_hash_domains": len(domains) - len(set(domains)),
        "invalid_hash_domains": invalid_domains,
        "invalid_registry_metadata": invalid_metadata,
        "migrated_implementations_remaining": sorted(MIGRATED_IMPLEMENTATIONS & discovered),
        "legacy_exception_count": len(registered),
    }


def main() -> int:
    report = authority_report()
    print(json.dumps(report, indent=2, sort_keys=True))
    failed = any(
        (
            report["canonical_serializer_authority_count"] != 1,
            report["unversioned_hash_writers"] != 0,
            bool(report["stale_legacy_exceptions"]),
            report["duplicate_legacy_sites"] != 0,
            report["duplicate_hash_domains"] != 0,
            bool(report["invalid_hash_domains"]),
            bool(report["invalid_registry_metadata"]),
            bool(report["migrated_implementations_remaining"]),
        )
    )
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
