from __future__ import annotations

import ast
import importlib.util
import re
import tomllib
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src/w2"
CHECKLIST = (
    ROOT
    / "docs/operations/architecture_convergence/"
    "W2_ARCHITECTURE_CONVERGENCE_MASTER_CHECKLIST.md"
)
START = "<!-- SRC_W2_PACKAGE_MATRIX_START -->"
END = "<!-- SRC_W2_PACKAGE_MATRIX_END -->"
ROLES = {
    "RUNTIME_ENTRYPOINT",
    "RUNTIME_LIBRARY",
    "WRITE_SIDE_PROJECTION",
    "PUBLIC_READ",
    "OFFLINE_TOOL",
    "MIGRATION_ONLY",
    "AUDIT_EXPORT",
    "DEAD",
}
DECISIONS = {"KEEP", "KEEP_OFFLINE", "KEEP_MIGRATION", "KEEP_AUDIT", "DELETE"}
PROTECTED_OFFLINE_PACKAGES = {"replay", "data_assets", "migration", "audit_export"}
METRICS = {
    "TOP_LEVEL_PACKAGE_COUNT",
    "MAPPED_PACKAGE_COUNT",
    "UNMAPPED_PACKAGE_COUNT",
    "DEPENDENCY_EDGE_COUNT",
    "CYCLE_COUNT",
    "RUNTIME_REACHABLE_PACKAGE_COUNT",
    "OFFLINE_ONLY_PACKAGE_COUNT",
    "DEAD_PACKAGE_COUNT",
    "DELETED_PACKAGE_COUNT",
}


def _packages() -> set[str]:
    return {
        path.name
        for path in SRC.iterdir()
        if path.is_dir()
        and not path.name.startswith(".")
        and path.name != "__pycache__"
        and any(path.rglob("*.py"))
    }


def _modules() -> dict[str, Path]:
    modules: dict[str, Path] = {}
    for path in SRC.rglob("*.py"):
        parts = list(path.relative_to(ROOT / "src").with_suffix("").parts)
        if parts[-1] == "__init__":
            parts.pop()
        modules[".".join(parts)] = path
    return modules


def _imports(path: Path, module: str, modules: set[str]) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    package = module if path.name == "__init__.py" else module.rpartition(".")[0]
    targets: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            targets.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = importlib.util.resolve_name(
                    "." * node.level + (node.module or ""), package
                )
            else:
                base = node.module or ""
            if base:
                targets.add(base)
            targets.update(
                f"{base}.{alias.name}"
                for alias in node.names
                if alias.name != "*" and base and f"{base}.{alias.name}" in modules
            )
        elif (
            isinstance(node, ast.Call)
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            name = ""
            if isinstance(node.func, ast.Name):
                name = node.func.id
            elif isinstance(node.func, ast.Attribute) and isinstance(
                node.func.value, ast.Name
            ):
                name = f"{node.func.value.id}.{node.func.attr}"
            if name in {"__import__", "import_module", "importlib.import_module"}:
                targets.add(node.args[0].value)
    return targets


def _top_package(target: str, packages: set[str]) -> str | None:
    if not target.startswith("w2."):
        return None
    package = target.split(".", 2)[1]
    return package if package in packages else None


def _graph() -> dict[str, set[str]]:
    packages = _packages()
    modules = _modules()
    graph = {package: set() for package in packages}
    for module, path in modules.items():
        parts = module.split(".")
        if len(parts) < 2 or parts[1] not in packages:
            continue
        source = parts[1]
        for target in _imports(path, module, set(modules)):
            dependency = _top_package(target, packages)
            if dependency and dependency != source:
                graph[source].add(dependency)
    return graph


def _external_callers() -> dict[str, dict[str, set[Path]]]:
    packages = _packages()
    modules = set(_modules())
    callers: dict[str, dict[str, set[Path]]] = {
        package: defaultdict(set) for package in packages
    }
    for surface in ("apps", "scripts", "migrations", "tests"):
        base = ROOT / surface
        for path in base.rglob("*.py"):
            if any(
                part.startswith(".") or part == "__pycache__"
                for part in path.relative_to(base).parts
            ):
                continue
            module = ".".join(path.relative_to(ROOT).with_suffix("").parts)
            for target in _imports(path, module, modules):
                package = _top_package(target, packages)
                if package:
                    callers[package][surface].add(path)
    return callers


def _runtime_reachability(graph: dict[str, set[str]]) -> tuple[set[str], set[str]]:
    callers = _external_callers()

    def closure(roots: set[str]) -> set[str]:
        reached: set[str] = set()
        pending = list(roots)
        while pending:
            package = pending.pop()
            if package in reached:
                continue
            reached.add(package)
            pending.extend(graph[package] - reached)
        return reached

    def roots(app: str) -> set[str]:
        marker = f"apps/{app}/"
        return {
            package
            for package, surfaces in callers.items()
            if any(marker in path.as_posix() for path in surfaces.get("apps", set()))
        }

    return closure(roots("api")), closure(roots("worker") | roots("scheduler"))


def _cycle_memberships(graph: dict[str, set[str]]) -> dict[str, str]:
    order: list[str] = []
    visited: set[str] = set()

    def visit(package: str) -> None:
        if package in visited:
            return
        visited.add(package)
        for dependency in graph[package]:
            visit(dependency)
        order.append(package)

    for package in sorted(graph):
        visit(package)

    reverse = {package: set() for package in graph}
    for package, dependencies in graph.items():
        for dependency in dependencies:
            reverse[dependency].add(package)

    components: list[list[str]] = []
    visited.clear()

    def collect(package: str, component: list[str]) -> None:
        if package in visited:
            return
        visited.add(package)
        component.append(package)
        for caller in reverse[package]:
            collect(caller, component)

    for package in reversed(order):
        if package not in visited:
            component: list[str] = []
            collect(package, component)
            if len(component) > 1:
                components.append(sorted(component))

    memberships = {package: "-" for package in graph}
    for index, component in enumerate(sorted(components), start=1):
        for package in component:
            memberships[package] = f"SCC-{index}"
    return memberships


def _matrix() -> tuple[list[str], list[dict[str, str]], dict[str, int]]:
    text = CHECKLIST.read_text(encoding="utf-8")
    block = text[text.index(START) + len(START) : text.index(END)]
    lines = [line for line in block.splitlines() if line.startswith("|")]
    headers = [cell.strip() for cell in lines[0].strip("|").split("|")]
    rows = [
        dict(
            zip(
                headers,
                (cell.strip().strip("`") for cell in line.strip("|").split("|")),
                strict=True,
            )
        )
        for line in lines[2:]
    ]
    metrics = {
        name: int(value)
        for name, value in re.findall(r"^([A-Z_]+) = ([0-9]+)$", block, re.MULTILINE)
        if name in METRICS
    }
    return headers, rows, metrics


def test_matrix_covers_every_top_level_package_once() -> None:
    headers, rows, metrics = _matrix()
    packages = _packages()
    mapped = [row["package"] for row in rows if row["decision"] != "DELETE"]

    assert len(headers) == 13
    names = [row["package"] for row in rows]
    assert len(names) == len(set(names))
    assert set(mapped) == packages
    assert metrics["TOP_LEVEL_PACKAGE_COUNT"] == len(packages)
    assert metrics["MAPPED_PACKAGE_COUNT"] == len(mapped)
    assert metrics["UNMAPPED_PACKAGE_COUNT"] == 0


def test_matrix_rows_match_the_current_dependency_graph() -> None:
    _, rows, metrics = _matrix()
    graph = _graph()
    reverse = {package: set() for package in graph}
    for package, dependencies in graph.items():
        for dependency in dependencies:
            reverse[dependency].add(package)
    api, worker_or_scheduler = _runtime_reachability(graph)
    memberships = _cycle_memberships(graph)
    by_package = {row["package"]: row for row in rows}

    for package in graph:
        row = by_package[package]
        assert int(row["python_file_count"]) == len(list((SRC / package).rglob("*.py")))
        assert row["internal_dependencies"] == (
            ",".join(sorted(graph[package])) or "-"
        )
        assert row["reverse_callers"] == (
            ",".join(sorted(reverse[package])) or "-"
        )
        assert row["cycle_membership"] == memberships[package]
        assert row["api_or_web_reachability"] == ("YES" if package in api else "NO")
        assert row["scheduler_or_worker_reachability"] == (
            "YES" if package in worker_or_scheduler else "NO"
        )
        assert row["docker_image_inclusion"] == "PYTHON_IMAGE"

    runtime = api | worker_or_scheduler
    assert metrics["DEPENDENCY_EDGE_COUNT"] == sum(map(len, graph.values()))
    assert metrics["CYCLE_COUNT"] == len(set(memberships.values()) - {"-"})
    assert metrics["RUNTIME_REACHABLE_PACKAGE_COUNT"] == len(runtime)
    assert metrics["OFFLINE_ONLY_PACKAGE_COUNT"] == len(graph) - len(runtime)


def test_matrix_callers_entrypoints_and_classifications_are_complete() -> None:
    _, rows, metrics = _matrix()
    callers = _external_callers()
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    console_scripts = project["project"]["scripts"]

    assert "COPY src ./src" in (ROOT / "Dockerfile.python").read_text(encoding="utf-8")
    for row in rows:
        package = row["package"]
        expected_callers = ";".join(
            f"{surface}:{len(callers[package].get(surface, set()))}"
            for surface in ("apps", "scripts", "migrations", "tests")
        )
        expected_entrypoints = sorted(
            name
            for name, target in console_scripts.items()
            if target.startswith(f"w2.{package}.")
        )
        assert row["direct_callers"] == expected_callers
        assert row["entrypoints"] == (",".join(expected_entrypoints) or "-")
        assert row["role"] in ROLES
        assert row["decision"] in DECISIONS
        assert row["evidence"]

    dead = [row for row in rows if row["role"] == "DEAD"]
    deleted = [row for row in rows if row["decision"] == "DELETE"]
    block = CHECKLIST.read_text(encoding="utf-8").split(START, 1)[1].split(END, 1)[0]
    def recorded_counts(name: str) -> Counter[str]:
        value = re.search(rf"^{name} = (.+)$", block, re.MULTILINE)
        assert value
        return Counter(
            {
                key: int(count)
                for item in value.group(1).split(";")
                for key, count in [item.split(":", 1)]
            }
        )

    assert recorded_counts("ROLE_COUNTS") == Counter(row["role"] for row in rows)
    assert recorded_counts("DECISION_COUNTS") == Counter(
        row["decision"] for row in rows
    )
    assert metrics["DEAD_PACKAGE_COUNT"] == len(dead)
    assert metrics["DELETED_PACKAGE_COUNT"] == len(deleted)
    runbooks = "\n".join(
        path.read_text(encoding="utf-8") for path in (ROOT / "docs/runbooks").rglob("*.md")
    )
    for row in deleted:
        assert not (SRC / row["package"]).exists()
        assert "ZERO_REF_9_OF_9" in row["evidence"]
        assert not re.search(rf"\bw2\.{re.escape(row['package'])}\b", runbooks)
    for package in PROTECTED_OFFLINE_PACKAGES:
        row = next(row for row in rows if row["package"] == package)
        assert row["role"] != "DEAD"
        assert row["decision"] != "DELETE"


def test_runtime_entry_surfaces_are_included_in_the_analysis() -> None:
    dockerfiles = list(ROOT.glob("Dockerfile*")) + list((ROOT / "infra").rglob("Dockerfile*"))
    compose_files = list((ROOT / "infra").rglob("*compose*.yml")) + list(
        (ROOT / "infra").rglob("*compose*.yaml")
    )
    workflows = list((ROOT / ".github/workflows").glob("*.yml")) + list(
        (ROOT / ".github/workflows").glob("*.yaml")
    )
    docker_text = "\n".join(path.read_text(encoding="utf-8") for path in dockerfiles)
    runtime_text = "\n".join(
        path.read_text(encoding="utf-8") for path in compose_files + workflows
    )

    assert "COPY src ./src" in docker_text
    for entrypoint in (
        "apps.api.main",
        "apps.worker.celery_app",
        "apps.scheduler.main",
    ):
        assert entrypoint in runtime_text


def test_p2_05_and_eval_01a_boundaries_remain_closed() -> None:
    checklist = CHECKLIST.read_text(encoding="utf-8")
    p2_05 = checklist[checklist.index("**ARCH-P2-05") : checklist.index("### 阶段 B")]
    state = yaml.safe_load((ROOT / "PROJECT_STATE.yaml").read_text(encoding="utf-8"))
    eval_01a = state["tasks"]["EVAL-01A"]

    assert "Status: DONE" not in p2_05
    assert "Status: IMPLEMENTED_PENDING_ACCEPTANCE" in p2_05
    assert "- [ ] exact-head FULL CI、外部验收与 PR 合并" in p2_05
    assert eval_01a["status"] == "BLOCKED"
    assert eval_01a["mergeable"] is False
    assert eval_01a["blockers"] == [
        "EXACT_HEAD_IMAGE_TRANSFER_BLOCKED",
        "BASE_DIVERGENCE_MERGE_CONFLICT",
    ]
