from __future__ import annotations

import ast
import re
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MASTER_CHECKLIST = (
    ROOT
    / "docs"
    / "operations"
    / "architecture_convergence"
    / "W2_ARCHITECTURE_CONVERGENCE_MASTER_CHECKLIST.md"
)
ALLOWED_CLASSIFICATIONS = {
    "RUNTIME_ENTRYPOINT",
    "CI_DIRECT",
    "CI_TRANSITIVE",
    "DEPLOYMENT",
    "MANUAL_OPS",
    "MIGRATION_ONLY",
    "ONE_TIME_RECOVERY",
    "DEAD",
}
SCRIPT_SUFFIXES = {".py", ".sh", ".mjs", ".js", ".ts"}
MATRIX_START = "<!-- SCRIPT_AUTHORITY_MATRIX_START -->"
MATRIX_END = "<!-- SCRIPT_AUTHORITY_MATRIX_END -->"
CONFIG_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])"
    r"((?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\.(?:py|sh|mjs|js|ts))"
    r"(?![A-Za-z0-9_.-])"
)


def _tracked_files() -> set[str]:
    output = subprocess.check_output(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
    ).decode()
    return {path for path in output.split("\0") if path}


def _resolve_module(module: str) -> str | None:
    parts = module.split(".")
    for size in range(len(parts), 0, -1):
        relative = Path(*parts[:size]).with_suffix(".py")
        for candidate in (relative, Path("src") / relative):
            if (ROOT / candidate).is_file():
                return candidate.as_posix()
    return None


def _configuration_sources(tracked: set[str]) -> list[Path]:
    sources: list[Path] = []
    for relative in sorted(tracked):
        path = Path(relative)
        if (
            relative == "pyproject.toml"
            or relative == "alembic.ini"
            or relative == "docker-compose.yml"
            or relative == "Makefile"
            or relative.startswith("Dockerfile")
            or relative == "apps/web/package.json"
            or relative.startswith(".github/workflows/")
            or relative.startswith("infra/")
        ):
            sources.append(ROOT / path)
    return sources


def _configuration_path_candidates(source: Path, relative: Path) -> tuple[Path, ...]:
    aliases: list[Path] = []
    relative_text = relative.as_posix()
    for prefix in ("app/scripts/", "opt/w2/current/scripts/"):
        if relative_text.startswith(prefix):
            aliases.append(ROOT / "scripts" / relative_text.removeprefix(prefix))
    return (ROOT / relative, source.parent / relative, *aliases)


def _configured_entrypoints(tracked: set[str]) -> set[str]:
    entrypoints: set[str] = set()
    for source in _configuration_sources(tracked):
        try:
            text = source.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for match in CONFIG_PATH_RE.finditer(text):
            relative = Path(match.group(1))
            if relative.parts[0] == "tests" and relative.as_posix() != "tests/secret_scan.py":
                continue
            for candidate in _configuration_path_candidates(source, relative):
                if candidate.is_file():
                    entrypoints.add(candidate.relative_to(ROOT).as_posix())
                    break
        for module in re.findall(r"\bapps\.(?:api|worker|scheduler)\.[A-Za-z0-9_.]+", text):
            resolved = _resolve_module(module)
            if resolved is not None:
                entrypoints.add(resolved)

    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    for target in project.get("project", {}).get("scripts", {}).values():
        module = str(target).split(":", maxsplit=1)[0]
        resolved = _resolve_module(module)
        if resolved is None:
            raise AssertionError(f"unresolved pyproject entrypoint: {target}")
        entrypoints.add(resolved)

    alembic = (ROOT / "alembic.ini").read_text(encoding="utf-8")
    match = re.search(r"^script_location\s*=\s*(\S+)\s*$", alembic, re.MULTILINE)
    if match is not None:
        env_path = ROOT / match.group(1) / "env.py"
        if env_path.is_file():
            entrypoints.add(env_path.relative_to(ROOT).as_posix())
    return entrypoints


def _inventory_universe() -> set[str]:
    tracked = _tracked_files()
    script_directories = {
        relative
        for relative in tracked
        if "scripts" in Path(relative).parts
        and Path(relative).suffix in SCRIPT_SUFFIXES
        and (ROOT / relative).is_file()
    }
    return script_directories | _configured_entrypoints(tracked)


def _matrix_rows() -> list[tuple[str, str, str]]:
    text = MASTER_CHECKLIST.read_text(encoding="utf-8")
    section = text.split(MATRIX_START, maxsplit=1)[1].split(MATRIX_END, maxsplit=1)[0]
    rows: list[tuple[str, str, str]] = []
    for line in section.splitlines():
        if not line.startswith("| `"):
            continue
        columns = [column.strip() for column in line.strip().strip("|").split("|")]
        if len(columns) != 9:
            raise AssertionError(f"script matrix row must have 9 columns: {line}")
        path = columns[0].strip("`")
        classification = columns[1].strip("`")
        decision = columns[7].strip("`")
        rows.append((path, classification, decision))
    return rows


def _check_w2_all_commands() -> list[list[str]]:
    tree = ast.parse((ROOT / "scripts/check_w2_all.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "COMMANDS" for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError("scripts/check_w2_all.py has no literal COMMANDS list")


def _script_edges(path: str) -> set[str]:
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    edges: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = ""
            if isinstance(node.func, ast.Name):
                name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                owner = node.func.value
                if isinstance(owner, ast.Name):
                    name = f"{owner.id}.{node.func.attr}"
            if name.startswith(("subprocess.", "runpy.", "os.system")):
                for child in ast.walk(node):
                    if (
                        isinstance(child, ast.Constant)
                        and isinstance(child.value, str)
                        and child.value.startswith("scripts/")
                        and (ROOT / child.value).is_file()
                    ):
                        edges.add(child.value)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("scripts."):
                    candidate = alias.name.replace(".", "/") + ".py"
                    if (ROOT / candidate).is_file():
                        edges.add(candidate)
        elif isinstance(node, ast.ImportFrom) and (node.module or "").startswith("scripts."):
            candidate = str(node.module).replace(".", "/") + ".py"
            if (ROOT / candidate).is_file():
                edges.add(candidate)
    return edges


def _check_w2_all_graph() -> dict[str, set[str]]:
    graph = {"scripts/check_w2_all.py": set()}
    pending: list[str] = []
    for command in _check_w2_all_commands():
        scripts = [token for token in command if token.startswith("scripts/")]
        graph["scripts/check_w2_all.py"].update(scripts)
        pending.extend(scripts)
    while pending:
        path = pending.pop()
        if path in graph:
            continue
        graph[path] = _script_edges(path)
        pending.extend(graph[path])
    return graph


def test_inventory_covers_every_script_exactly_once() -> None:
    rows = _matrix_rows()
    paths = [path for path, _classification, _decision in rows]
    assert len(paths) == len(set(paths))
    observed_classifications = {
        classification for _path, classification, _decision in rows
    }
    assert not (observed_classifications - ALLOWED_CLASSIFICATIONS)

    dead = {path for path, classification, _decision in rows if classification == "DEAD"}
    retained = {
        path
        for path, classification, decision in rows
        if classification != "DEAD" and decision == "KEEP"
    }
    assert set(paths) == retained | dead
    assert retained == _inventory_universe()


def test_dead_scripts_are_absent_and_non_dead_scripts_exist() -> None:
    rows = _matrix_rows()
    for path, classification, decision in rows:
        if classification == "DEAD":
            assert decision == "DELETE"
            assert not (ROOT / path).exists()
        else:
            assert decision == "KEEP"
            assert (ROOT / path).is_file()


def test_deleted_script_references_are_absent() -> None:
    dead = {
        path
        for path, classification, _decision in _matrix_rows()
        if classification == "DEAD"
    }
    for relative in _tracked_files():
        if relative == MASTER_CHECKLIST.relative_to(ROOT).as_posix():
            continue
        path = ROOT / relative
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        assert not (dead & {candidate for candidate in dead if candidate in text}), relative


def test_no_scripts_archive_directory_is_tracked() -> None:
    for relative in _tracked_files():
        parts = Path(relative).parts
        assert not any(
            parts[index : index + 2] == ("scripts", "archive")
            for index in range(len(parts) - 1)
        )


def test_ci_deployment_systemd_and_cron_script_references_resolve() -> None:
    tracked = _tracked_files()
    for source in _configuration_sources(tracked):
        text = source.read_text(encoding="utf-8")
        for match in CONFIG_PATH_RE.finditer(text):
            relative = Path(match.group(1))
            if relative.parts[0] == "tests" and relative.as_posix() != "tests/secret_scan.py":
                continue
            assert any(
                candidate.is_file()
                for candidate in _configuration_path_candidates(source, relative)
            ), f"{source.relative_to(ROOT)} -> {relative}"


def test_check_w2_all_only_runs_stage_or_contract_checkers() -> None:
    commands = _check_w2_all_commands()
    assert commands
    for command in commands:
        script_paths = [token for token in command if token.startswith("scripts/")]
        assert len(script_paths) == 1
        name = Path(script_paths[0]).name
        assert name.startswith("check_w2_stage") or "contract" in name


def test_check_w2_all_transitive_graph_excludes_ruff_mypy_and_pytest() -> None:
    graph = _check_w2_all_graph()
    serialized = "\n".join(
        f"{caller} -> {callee}" for caller, callees in graph.items() for callee in callees
    ).lower()
    commands = "\n".join(" ".join(command) for command in _check_w2_all_commands()).lower()
    for forbidden in ("ruff", "mypy", "pytest"):
        assert forbidden not in serialized
        assert forbidden not in commands


def test_github_ci_owns_ruff_mypy_and_full_pytest() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "run: uv run --python 3.12 ruff check ." in workflow
    assert "run: uv run --python 3.12 mypy src apps" in workflow
    assert "run: uv run --python 3.12 pytest -q" in workflow
