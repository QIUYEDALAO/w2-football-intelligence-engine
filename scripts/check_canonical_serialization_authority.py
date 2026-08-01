from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "config/canonical_serialization_legacy_exceptions.v1.json"
PRODUCTION_ROOTS = ("src/w2", "apps", "scripts", "migrations")
AUTHORITY = "src/w2/domain/canonical_serialization.py"
JSON_MODULES = frozenset({"json", "orjson", "rapidjson", "simplejson", "ujson"})
SERIALIZER_NAME_MARKERS = ("canonical", "digest", "hash", "serializ")
MIGRATED_IMPLEMENTATIONS = {
    ("src/w2/ingestion/future_refresh.py", "canonical_json"),
    ("src/w2/tracking/outcome_ledger_repository.py", "canonical_json"),
    ("src/w2/monitoring/stage7i_lifecycle.py", "canonical_json"),
    ("src/w2/monitoring/stage7i_supervision.py", "canonical_json"),
    ("src/w2/prematch/read_model_projection.py", "canonical_json_bytes"),
    ("src/w2/prematch/repository.py", "_pair_sha256"),
}


def _qualified_name(node: ast.expr, bindings: dict[str, str]) -> str:
    if isinstance(node, ast.Name):
        return bindings.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        base = _qualified_name(node.value, bindings)
        return f"{base}.{node.attr}" if base else node.attr
    if isinstance(node, ast.Call):
        return f"{_qualified_name(node.func, bindings)}()"
    return ""


def _bindings(scope: ast.AST, inherited: dict[str, str] | None = None) -> dict[str, str]:
    bindings = dict(inherited or {})
    for node in ast.walk(scope):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in JSON_MODULES | {"hashlib"}:
                    bindings[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in JSON_MODULES | {"hashlib"}:
                for alias in node.names:
                    bindings[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    for _ in range(2):
        for node in ast.walk(scope):
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                if isinstance(target, ast.Name):
                    resolved = _qualified_name(node.value, bindings)
                    if resolved:
                        bindings[target.id] = resolved
    return bindings


def _is_json_writer(name: str) -> bool:
    if any(name in {f"{module}.dump", f"{module}.dumps"} for module in JSON_MODULES):
        return True
    return name.endswith((".encode", ".iterencode")) and any(
        name.startswith(f"{module}.JSONEncoder()") for module in JSON_MODULES
    )


def _is_hash_call(name: str) -> bool:
    return name in {
        "hashlib.blake2b",
        "hashlib.blake2s",
        "hashlib.md5",
        "hashlib.sha1",
        "hashlib.sha224",
        "hashlib.sha256",
        "hashlib.sha384",
        "hashlib.sha3_224",
        "hashlib.sha3_256",
        "hashlib.sha3_384",
        "hashlib.sha3_512",
        "hashlib.sha512",
    }


def _contains_json_writer(node: ast.AST, bindings: dict[str, str]) -> bool:
    return any(
        isinstance(child, ast.Call)
        and _is_json_writer(_qualified_name(child.func, bindings))
        for child in ast.walk(node)
    )


def _contains_name(node: ast.AST, names: set[str]) -> bool:
    return any(isinstance(child, ast.Name) and child.id in names for child in ast.walk(node))


def _hashes_json(scope: ast.AST, bindings: dict[str, str]) -> bool:
    tainted: set[str] = set()
    for _ in range(2):
        for node in ast.walk(scope):
            if not isinstance(node, ast.Assign):
                continue
            if _contains_json_writer(node.value, bindings) or _contains_name(node.value, tainted):
                tainted.update(
                    target.id for target in node.targets if isinstance(target, ast.Name)
                )
    return any(
        isinstance(node, ast.Call)
        and _is_hash_call(_qualified_name(node.func, bindings))
        and any(
            _contains_json_writer(argument, bindings) or _contains_name(argument, tainted)
            for argument in node.args
        )
        for node in ast.walk(scope)
    )


def _scope_is_writer(scope: ast.AST, symbol: str, bindings: dict[str, str]) -> bool:
    calls = [node for node in ast.walk(scope) if isinstance(node, ast.Call)]
    json_calls = [
        call for call in calls if _is_json_writer(_qualified_name(call.func, bindings))
    ]
    if not json_calls:
        return False
    if symbol == "<module>":
        return True
    lowered = symbol.lower()
    return (
        any(marker in lowered for marker in SERIALIZER_NAME_MARKERS)
        or _hashes_json(scope, bindings)
    )


class _ModuleCalls(ast.NodeVisitor):
    def __init__(self) -> None:
        self.calls: list[ast.Call] = []

    def visit_Call(self, node: ast.Call) -> None:
        self.calls.append(node)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        return

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        return

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        return


def _module_is_writer(tree: ast.Module, bindings: dict[str, str]) -> bool:
    visitor = _ModuleCalls()
    visitor.visit(tree)
    return any(_is_json_writer(_qualified_name(call.func, bindings)) for call in visitor.calls)


def legacy_writer_sites(root: Path = ROOT) -> set[tuple[str, str]]:
    sites: set[tuple[str, str]] = set()
    for production_root in PRODUCTION_ROOTS:
        directory = root / production_root
        if not directory.exists():
            continue
        for path in sorted(directory.rglob("*.py")):
            relative = path.relative_to(root).as_posix()
            if relative == AUTHORITY:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
            module_bindings = _bindings(tree)
            if _module_is_writer(tree, module_bindings):
                sites.add((relative, "<module>"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                    continue
                if _scope_is_writer(node, node.name, _bindings(node, module_bindings)):
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
    required_metadata = ("legacy_profile_id", "owner", "reason", "test")
    invalid_metadata = [field for field in required_metadata if not registry.get(field)]
    domains = [str(row.get("hash_domain") or "") for row in registered_rows]
    invalid_domains = [domain for domain in domains if not domain.startswith("legacy.")]
    unauthorized = discovered - registered
    return {
        "production_roots": list(PRODUCTION_ROOTS),
        "canonical_serializer_authority_count": int(
            {"canonical_bytes", "canonical_sha256"} <= authority_functions
        ),
        "unauthorized_serializer_writers": len(unauthorized),
        "unversioned_hash_writers": len(unauthorized),
        "stale_legacy_exceptions": sorted(registered - discovered),
        "unexpected_legacy_writers": sorted(unauthorized),
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
            report["unauthorized_serializer_writers"] != 0,
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
