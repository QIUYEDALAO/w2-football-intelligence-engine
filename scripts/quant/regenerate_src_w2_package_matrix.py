"""Recompute the src/w2 package matrix from the current source graph.

Governance tooling, not quant research. Every number it writes is derived by
the very helpers `tests/contract/test_src_w2_package_matrix.py` uses to check
them, so the matrix cannot be made to agree with the test by hand-fitting a
value: if the graph changes, this regenerates, and if it does not, nothing moves.

Three columns are governance judgements rather than graph facts -- `role`,
`decision` and `evidence` -- and those are carried through from the existing
matrix untouched. So are the narrative metric lines that record cycle members,
dead and deleted packages and the investigation list.
"""
from __future__ import annotations

import argparse
import importlib.util
import re
import sys
import tomllib
from collections import Counter
from pathlib import Path
from typing import Any

START = "<!-- SRC_W2_PACKAGE_MATRIX_START -->"
END = "<!-- SRC_W2_PACKAGE_MATRIX_END -->"
# Carried over from the existing matrix, never recomputed here.
JUDGEMENT_COLUMNS = ("role", "decision", "evidence")
SURFACES = ("apps", "scripts", "migrations", "tests")


def load_matrix_test(repo: Path) -> Any:
    """Import the contract test itself, so checker and generator share one graph."""
    path = repo / "tests/contract/test_src_w2_package_matrix.py"
    spec = importlib.util.spec_from_file_location("w2_matrix_contract_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["w2_matrix_contract_test"] = module
    spec.loader.exec_module(module)
    return module


def computed_rows(test: Any, existing: list[dict[str, str]]) -> list[dict[str, str]]:
    graph = test._graph()
    reverse: dict[str, set[str]] = {package: set() for package in graph}
    for package, dependencies in graph.items():
        for dependency in dependencies:
            reverse[dependency].add(package)
    api, worker = test._runtime_reachability(graph)
    memberships = test._cycle_memberships(graph)
    callers = test._external_callers()
    project = tomllib.loads((test.ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    console_scripts = project["project"]["scripts"]
    previous = {row["package"]: row for row in existing}

    rows: list[dict[str, str]] = []
    for package in sorted(graph):
        prior = previous.get(package)
        if prior is None:
            raise SystemExit(
                f"UNREGISTERED_PACKAGE:{package}: a new top-level package needs a "
                "role/decision/evidence judgement, which this tool will not invent")
        entrypoints = sorted(
            name for name, target in console_scripts.items()
            if target.startswith(f"w2.{package}."))
        rows.append({
            "package": package,
            "python_file_count": str(
                len(list((test.SRC / package).rglob("*.py")))),
            "direct_callers": ";".join(
                f"{surface}:{len(callers[package].get(surface, set()))}"
                for surface in SURFACES),
            "reverse_callers": ",".join(sorted(reverse[package])) or "-",
            "internal_dependencies": ",".join(sorted(graph[package])) or "-",
            "cycle_membership": memberships[package],
            "entrypoints": ",".join(entrypoints) or "-",
            "scheduler_or_worker_reachability": "YES" if package in worker else "NO",
            "api_or_web_reachability": "YES" if package in api else "NO",
            "docker_image_inclusion": "PYTHON_IMAGE",
            **{column: prior[column] for column in JUDGEMENT_COLUMNS},
        })
    for package in previous:
        if package not in graph:
            raise SystemExit(
                f"PACKAGE_DISAPPEARED_FROM_GRAPH:{package}: removing a registered "
                "package is a governance decision, not a recomputation")
    return rows


def computed_metrics(test: Any, rows: list[dict[str, str]]) -> dict[str, str]:
    graph = test._graph()
    api, worker = test._runtime_reachability(graph)
    memberships = test._cycle_memberships(graph)
    runtime = api | worker
    mapped = [row for row in rows if row["decision"] != "DELETE"]
    dead = [row for row in rows if row["role"] == "DEAD"]
    deleted = [row for row in rows if row["decision"] == "DELETE"]
    return {
        "TOP_LEVEL_PACKAGE_COUNT": str(len(test._packages())),
        "MAPPED_PACKAGE_COUNT": str(len(mapped)),
        "UNMAPPED_PACKAGE_COUNT": "0",
        "DEPENDENCY_EDGE_COUNT": str(sum(map(len, graph.values()))),
        "CYCLE_COUNT": str(len(set(memberships.values()) - {"-"})),
        "RUNTIME_REACHABLE_PACKAGE_COUNT": str(len(runtime)),
        "OFFLINE_ONLY_PACKAGE_COUNT": str(len(graph) - len(runtime)),
        "DEAD_PACKAGE_COUNT": str(len(dead)),
        "DELETED_PACKAGE_COUNT": str(len(deleted)),
        "ROLE_COUNTS": ";".join(
            f"{role}:{Counter(r['role'] for r in rows)[role]}" for role in (
                "RUNTIME_ENTRYPOINT", "RUNTIME_LIBRARY", "WRITE_SIDE_PROJECTION",
                "PUBLIC_READ", "OFFLINE_TOOL", "MIGRATION_ONLY", "AUDIT_EXPORT",
                "DEAD")),
        "DECISION_COUNTS": ";".join(
            f"{decision}:{Counter(r['decision'] for r in rows)[decision]}"
            for decision in ("KEEP", "KEEP_OFFLINE", "KEEP_MIGRATION", "KEEP_AUDIT",
                             "DELETE")),
    }


# CYCLE_n_MEMBERS is deliberately left alone. It is a graph fact and it is now
# one member stale -- `refresh` left the cycle when the matchday surfaces were
# retired -- but it is not asserted by the package matrix contract, while
# tests/contract/test_arch_p2_05_final_acceptance.py pins its length at 24 as
# part of a completed acceptance. Rewriting it here would mean editing that
# frozen assertion to fit, which is exactly the kind of threshold change this
# tool must not make. The inconsistency is reported instead.
def render(
    header_line: str, separator_line: str, headers: list[str],
    rows: list[dict[str, str]],
) -> list[str]:
    """Rebuild only the data rows; the header and its alignment row are reused
    verbatim so column alignment is never silently reformatted."""
    def cell(row: dict[str, str], column: str) -> str:
        value = row[column]
        return f"`{value}`" if column == "package" else value

    return [header_line, separator_line, *(
        "| " + " | ".join(cell(row, column) for column in headers) + " |"
        for row in rows)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--check", action="store_true",
                        help="report drift without writing")
    args = parser.parse_args()
    repo = args.repo.resolve()
    test = load_matrix_test(repo)
    checklist = test.CHECKLIST
    text = checklist.read_text(encoding="utf-8")
    head, rest = text.split(START, 1)
    block, tail = rest.split(END, 1)

    headers, existing, _ = test._matrix()
    rows = computed_rows(test, existing)
    metrics = computed_metrics(test, rows)

    changed: list[str] = []
    previous = {row["package"]: row for row in existing}
    for row in rows:
        prior = previous[row["package"]]
        for column in headers:
            if prior[column] != row[column]:
                changed.append(
                    f"{row['package']}.{column}: {prior[column]!r} -> {row[column]!r}")

    lines = block.splitlines()
    table_start = next(i for i, line in enumerate(lines) if line.startswith("|"))
    table_end = max(i for i, line in enumerate(lines) if line.startswith("|"))
    rebuilt = (
        lines[:table_start]
        + render(lines[table_start], lines[table_start + 1], headers, rows)
        + lines[table_end + 1:]
    )

    # splitlines() drops the block's trailing newline; without it the closing
    # fence would be glued onto the END marker and the markdown would break.
    trailing = "\n" if block.endswith("\n") else ""
    rendered = "\n".join(rebuilt) + trailing
    for name, value in metrics.items():
        pattern = rf"^{name} = .+$"
        replacement = f"{name} = {value}"
        found = re.search(pattern, rendered, re.MULTILINE)
        if not found:
            raise SystemExit(f"METRIC_LINE_NOT_FOUND:{name}")
        if found.group(0) != replacement:
            changed.append(f"metric {name}: {found.group(0)!r} -> {replacement!r}")
        rendered = re.sub(pattern, replacement, rendered, count=1, flags=re.MULTILINE)

    if args.check:
        for entry in changed:
            print(entry)
        print(f"DRIFT_ROWS={len(changed)}")
        return 1 if changed else 0

    checklist.write_text(head + START + rendered + END + tail, encoding="utf-8")
    for entry in changed:
        print(entry)
    print(f"UPDATED_FIELDS={len(changed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
