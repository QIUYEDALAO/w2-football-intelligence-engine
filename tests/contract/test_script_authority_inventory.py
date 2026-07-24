from __future__ import annotations

import ast
import re
import shlex
import subprocess
import tomllib
from collections.abc import Callable
from pathlib import Path

import pytest

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
HEAVY_TEST_TOOLS = {"ruff", "mypy", "pytest"}
MATRIX_START = "<!-- SCRIPT_AUTHORITY_MATRIX_START -->"
MATRIX_END = "<!-- SCRIPT_AUTHORITY_MATRIX_END -->"
CONFIG_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])"
    r"((?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\.(?:py|sh|mjs|js|ts))"
    r"(?![A-Za-z0-9_.-])"
)
COMMAND_ANCHOR_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])"
    r"((?:(?:uv)\s+run(?:\s+--python\s+\S+)?\s+)?"
    r"(?:python(?:3(?:\.\d+)?)?|uvicorn|celery|bash|sh|node|ruff|mypy|pytest)\b.*)"
)
PYTHON_TOOLS = {"python", "python3", "python3.12"}
SHELL_TOOLS = {"bash", "sh"}


def _tracked_files(root: Path = ROOT) -> set[str]:
    output = subprocess.check_output(
        ["git", "ls-files", "-z"],
        cwd=root,
    ).decode()
    return {path for path in output.split("\0") if path}


def _resolve_module(module: str, root: Path = ROOT) -> str | None:
    module_name = module.split(":", maxsplit=1)[0].strip()
    parts = module_name.split(".")
    for size in range(len(parts), 0, -1):
        relative = Path(*parts[:size])
        candidates = (
            relative.with_suffix(".py"),
            Path("src") / relative.with_suffix(".py"),
            relative / "__main__.py",
            Path("src") / relative / "__main__.py",
            relative / "__init__.py",
            Path("src") / relative / "__init__.py",
        )
        for candidate in candidates:
            if (root / candidate).is_file():
                return candidate.as_posix()
    return None


def _configuration_sources(tracked: set[str], root: Path = ROOT) -> list[Path]:
    sources: list[Path] = []
    for relative in sorted(tracked):
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
            sources.append(root / relative)
    return sources


def _configuration_path_candidates(
    source: Path,
    relative: Path,
    root: Path = ROOT,
) -> tuple[Path, ...]:
    aliases: list[Path] = []
    relative_text = relative.as_posix().removeprefix("./")
    for prefix in ("app/scripts/", "opt/w2/current/scripts/"):
        if relative_text.startswith(prefix):
            aliases.append(root / "scripts" / relative_text.removeprefix(prefix))
    return (root / relative_text, source.parent / relative_text, *aliases)


def _resolved_path_node(raw_path: str, source: Path, root: Path) -> str | None:
    relative = Path(raw_path.removeprefix("./").lstrip("/"))
    for candidate in _configuration_path_candidates(source, relative, root):
        if candidate.is_file():
            try:
                return f"script:{candidate.relative_to(root).as_posix()}"
            except ValueError:
                continue
    return None


def _module_nodes(module: str, root: Path) -> set[str]:
    module_name = module.split(":", maxsplit=1)[0]
    nodes = {f"module:{module_name}"}
    resolved = _resolve_module(module_name, root)
    if resolved is not None:
        nodes.add(f"script:{resolved}")
    return nodes


def _command_segments(command: str) -> list[list[str]]:
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|")
        lexer.whitespace_split = True
        words = list(lexer)
    except ValueError:
        return []
    segments: list[list[str]] = []
    current: list[str] = []
    for word in words:
        if word in {";", "&&", "||", "|", "&"}:
            if current:
                segments.append(current)
                current = []
        else:
            current.append(word)
    if current:
        segments.append(current)
    return segments


def _first_positional(words: list[str]) -> str | None:
    for word in words:
        if not word.startswith("-"):
            return word
    return None


def _command_segment_nodes(words: list[str], source: Path, root: Path) -> set[str]:
    if not words:
        return set()
    executable = Path(words[0]).name
    nodes = {f"tool:{executable}"}
    arguments = words[1:]

    if executable == "uv":
        if arguments and arguments[0] == "run":
            arguments = arguments[1:]
        while arguments and arguments[0].startswith("-"):
            option = arguments.pop(0)
            if option in {"--python", "-p"} and arguments:
                arguments.pop(0)
        if arguments:
            nodes.update(_command_segment_nodes(arguments, source, root))
        return nodes

    if executable in PYTHON_TOOLS:
        if "-m" in arguments:
            index = arguments.index("-m")
            if index + 1 < len(arguments):
                nodes.update(_module_nodes(arguments[index + 1], root))
            return nodes
        if "-c" in arguments:
            index = arguments.index("-c")
            if index + 1 < len(arguments):
                nodes.update(_command_nodes(arguments[index + 1], source, root))
            return nodes
        target = _first_positional(arguments)
        if target and Path(target).suffix in SCRIPT_SUFFIXES:
            nodes.add(f"path:{target.removeprefix('./')}")
            resolved = _resolved_path_node(target, source, root)
            if resolved is not None:
                nodes.add(resolved)
        return nodes

    if executable == "uvicorn":
        target = _first_positional(arguments)
        if target:
            nodes.update(_module_nodes(target, root))
        return nodes

    if executable == "celery":
        for option in ("-A", "--app"):
            if option in arguments:
                index = arguments.index(option)
                if index + 1 < len(arguments):
                    nodes.update(_module_nodes(arguments[index + 1], root))
        return nodes

    if executable in SHELL_TOOLS:
        if "-c" in arguments:
            index = arguments.index("-c")
            if index + 1 < len(arguments):
                nodes.update(_command_nodes(" ".join(arguments[index + 1 :]), source, root))
            return nodes
        target = _first_positional(arguments)
        if target:
            nodes.add(f"path:{target.removeprefix('./')}")
            resolved = _resolved_path_node(target, source, root)
            if resolved is not None:
                nodes.add(resolved)
        return nodes

    if executable == "node":
        target = _first_positional(arguments)
        if target:
            nodes.add(f"path:{target.removeprefix('./')}")
            resolved = _resolved_path_node(target, source, root)
            if resolved is not None:
                nodes.add(resolved)
        return nodes

    return nodes


def _command_nodes(command: str, source: Path, root: Path = ROOT) -> set[str]:
    nodes: set[str] = set()
    for segment in _command_segments(command):
        nodes.update(_command_segment_nodes(segment, source, root))
    return nodes


def _command_nodes_from_text(text: str, source: Path, root: Path = ROOT) -> set[str]:
    nodes: set[str] = set()
    for raw_line in text.splitlines():
        normalized = (
            raw_line.replace('", "', " ")
            .replace('","', " ")
            .replace('["', " ")
            .replace('"]', " ")
            .replace('"', " ")
            .replace("'", " ")
            .replace(",", " ")
        )
        match = COMMAND_ANCHOR_RE.search(normalized)
        if match is not None:
            nodes.update(_command_nodes(match.group(1), source, root))
    return nodes


def _configured_entrypoints(tracked: set[str], root: Path = ROOT) -> set[str]:
    entrypoints: set[str] = set()
    for source in _configuration_sources(tracked, root):
        try:
            text = source.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for match in CONFIG_PATH_RE.finditer(text):
            relative = Path(match.group(1))
            if relative.parts[0] == "tests" and relative.as_posix() != "tests/secret_scan.py":
                continue
            for candidate in _configuration_path_candidates(source, relative, root):
                if candidate.is_file():
                    entrypoints.add(candidate.relative_to(root).as_posix())
                    break
        for node in _command_nodes_from_text(text, source, root):
            if node.startswith("script:"):
                entrypoints.add(node.removeprefix("script:"))

    project_path = root / "pyproject.toml"
    if project_path.is_file():
        project = tomllib.loads(project_path.read_text(encoding="utf-8"))
        for target in project.get("project", {}).get("scripts", {}).values():
            module = str(target).split(":", maxsplit=1)[0]
            resolved = _resolve_module(module, root)
            if resolved is None:
                raise AssertionError(f"unresolved pyproject entrypoint: {target}")
            entrypoints.add(resolved)

    alembic_path = root / "alembic.ini"
    if alembic_path.is_file():
        alembic = alembic_path.read_text(encoding="utf-8")
        match = re.search(r"^script_location\s*=\s*(\S+)\s*$", alembic, re.MULTILINE)
        if match is not None:
            env_path = root / match.group(1) / "env.py"
            if env_path.is_file():
                entrypoints.add(env_path.relative_to(root).as_posix())
    return entrypoints


def _inventory_universe(
    tracked: set[str] | None = None,
    root: Path = ROOT,
) -> set[str]:
    tracked = _tracked_files(root) if tracked is None else tracked
    directly_tracked = {
        relative
        for relative in tracked
        if Path(relative).suffix in SCRIPT_SUFFIXES
        and (len(Path(relative).parts) == 1 or Path(relative).parts[0] == "infra")
        and (root / relative).is_file()
    }
    script_directories = {
        relative
        for relative in tracked
        if "scripts" in Path(relative).parts
        and Path(relative).suffix in SCRIPT_SUFFIXES
        and (root / relative).is_file()
    }
    return directly_tracked | script_directories | _configured_entrypoints(tracked, root)


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


def _assert_inventory_classified(
    universe: set[str],
    rows: list[tuple[str, str, str]],
) -> None:
    dead = {path for path, classification, _decision in rows if classification == "DEAD"}
    retained = {
        path
        for path, classification, decision in rows
        if classification != "DEAD" and decision == "KEEP"
    }
    assert retained == universe, (
        f"unclassified={sorted(universe - retained)} "
        f"missing={sorted(retained - universe)} dead={sorted(dead & universe)}"
    )


def _check_w2_all_commands(root: Path = ROOT) -> list[list[str]]:
    tree = ast.parse((root / "scripts/check_w2_all.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "COMMANDS" for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError("scripts/check_w2_all.py has no literal COMMANDS list")


def _expression_name(node: ast.expr, aliases: dict[str, str]) -> str:
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        owner = _expression_name(node.value, aliases)
        return f"{owner}.{node.attr}" if owner else node.attr
    return ""


def _import_aliases(tree: ast.AST) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name.split(".", maxsplit=1)[0]
                aliases[local] = alias.name
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                local = alias.asname or alias.name
                aliases[local] = f"{module}.{alias.name}".strip(".")
    return aliases


def _literal_command(node: ast.expr) -> str | None:
    try:
        value = ast.literal_eval(node)
    except (ValueError, TypeError):
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)) and all(isinstance(item, str) for item in value):
        return shlex.join(value)
    return None


def _python_execution_nodes(text: str, source: Path, root: Path = ROOT) -> set[str]:
    tree = ast.parse(text)
    aliases = _import_aliases(tree)
    nodes: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("scripts."):
                    nodes.update(_module_nodes(alias.name, root))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "scripts":
                for alias in node.names:
                    nodes.update(_module_nodes(f"scripts.{alias.name}", root))
            elif module.startswith("scripts."):
                nodes.update(_module_nodes(module, root))
        elif isinstance(node, ast.Call):
            name = _expression_name(node.func, aliases)
            if name in {
                "subprocess.run",
                "subprocess.Popen",
                "subprocess.check_call",
                "subprocess.check_output",
            }:
                if node.args:
                    command = _literal_command(node.args[0])
                    if command is not None:
                        nodes.update(_command_nodes(command, source, root))
            elif name in {"os.system", "os.popen"}:
                if node.args:
                    command = _literal_command(node.args[0])
                    if command is not None:
                        nodes.update(_command_nodes(command, source, root))
            elif name in {"runpy.run_module", "importlib.import_module"}:
                if node.args:
                    module = _literal_command(node.args[0])
                    if module is not None:
                        nodes.update(_module_nodes(module, root))
            elif name == "runpy.run_path":
                if node.args:
                    target = _literal_command(node.args[0])
                    if target is not None:
                        nodes.add(f"path:{target.removeprefix('./')}")
                        resolved = _resolved_path_node(target, source, root)
                        if resolved is not None:
                            nodes.add(resolved)
            elif name == "pytest.main":
                nodes.add("tool:pytest")
    return nodes


def _script_edges(path: str, root: Path = ROOT) -> set[str]:
    source = root / path
    text = source.read_text(encoding="utf-8")
    if source.suffix == ".py":
        return _python_execution_nodes(text, source, root)
    if source.suffix in {".sh", ".mjs", ".js", ".ts"}:
        return _command_nodes_from_text(text, source, root)
    return set()


def _check_w2_all_graph(root: Path = ROOT) -> dict[str, set[str]]:
    root_node = "script:scripts/check_w2_all.py"
    graph: dict[str, set[str]] = {root_node: set()}
    source = root / "scripts/check_w2_all.py"
    for command in _check_w2_all_commands(root):
        graph[root_node].update(_command_nodes(shlex.join(command), source, root))

    pending = list(graph[root_node])
    while pending:
        node = pending.pop()
        if node in graph:
            continue
        if node.startswith("script:"):
            path = node.removeprefix("script:")
            graph[node] = _script_edges(path, root)
        elif node.startswith("module:"):
            resolved = _resolve_module(node.removeprefix("module:"), root)
            graph[node] = {f"script:{resolved}"} if resolved is not None else set()
        else:
            graph[node] = set()
        pending.extend(graph[node])
    return graph


def _assert_graph_excludes_heavy_tools(graph: dict[str, set[str]]) -> None:
    forbidden = sorted(
        node.removeprefix("tool:")
        for node in graph
        if node.startswith("tool:")
        and node.removeprefix("tool:").lower() in HEAVY_TEST_TOOLS
    )
    assert not forbidden, f"reachable heavy test tools: {forbidden}"


def _dead_identities(path: str) -> set[str]:
    relative = Path(path)
    return {
        relative.as_posix(),
        relative.name,
        relative.stem,
        relative.with_suffix("").as_posix().replace("/", "."),
    }


def _node_identities(node: str) -> set[str]:
    value = node.split(":", maxsplit=1)[-1].removeprefix("./")
    path = Path(value)
    identities = {value, path.name, path.stem}
    if "/" in value:
        identities.add(path.with_suffix("").as_posix().replace("/", "."))
    return identities


def _referenced_dead_paths(
    source: Path,
    text: str,
    dead: set[str],
    root: Path = ROOT,
) -> set[str]:
    try:
        if source.suffix == ".py":
            nodes = _python_execution_nodes(text, source, root)
        else:
            nodes = _command_nodes_from_text(text, source, root)
    except SyntaxError:
        nodes = set()

    references: set[str] = set()
    node_identities = set().union(*(_node_identities(node) for node in nodes)) if nodes else set()
    for path in dead:
        identities = _dead_identities(path)
        if identities & node_identities:
            references.add(path)
            continue
        if any(
            re.search(rf"(?<![A-Za-z0-9_.-]){re.escape(identity)}(?![A-Za-z0-9_.-])", text)
            for identity in identities
        ):
            references.add(path)
    return references


def _write_check_graph_fixture(
    root: Path,
    child_text: str,
    *,
    extra_files: dict[str, str] | None = None,
) -> dict[str, set[str]]:
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "check_w2_all.py").write_text(
        "COMMANDS = [['uv', 'run', 'python', 'scripts/child.py']]\n",
        encoding="utf-8",
    )
    (scripts / "child.py").write_text(child_text, encoding="utf-8")
    for relative, text in (extra_files or {}).items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return _check_w2_all_graph(root)


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
    _assert_inventory_classified(_inventory_universe(), rows)


def test_unreferenced_root_script_is_unclassified(tmp_path: Path) -> None:
    path = tmp_path / "root_tool.py"
    path.write_text("print('root tool')\n", encoding="utf-8")
    universe = _inventory_universe({"root_tool.py"}, tmp_path)
    with pytest.raises(AssertionError, match="root_tool.py"):
        _assert_inventory_classified(universe, [])


def test_unreferenced_infra_script_is_unclassified(tmp_path: Path) -> None:
    path = tmp_path / "infra/ops/tool.sh"
    path.parent.mkdir(parents=True)
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    universe = _inventory_universe({"infra/ops/tool.sh"}, tmp_path)
    with pytest.raises(AssertionError, match="infra/ops/tool.sh"):
        _assert_inventory_classified(universe, [])


@pytest.mark.parametrize(
    "command",
    [
        "python -m w2.example",
        "uvicorn w2.example:app",
        "celery -A w2.example worker",
    ],
)
def test_generic_module_entrypoints_resolve(command: str, tmp_path: Path) -> None:
    module = tmp_path / "src/w2/example.py"
    module.parent.mkdir(parents=True)
    module.write_text("app = object()\n", encoding="utf-8")
    nodes = _command_nodes(command, tmp_path / "config.yml", tmp_path)
    assert "module:w2.example" in nodes
    assert "script:src/w2/example.py" in nodes


def test_uv_run_python_module_entrypoint_resolves(tmp_path: Path) -> None:
    module = tmp_path / "src/w2/example.py"
    module.parent.mkdir(parents=True)
    module.write_text("VALUE = 1\n", encoding="utf-8")
    nodes = _command_nodes(
        "uv run --python 3.12 python -m w2.example",
        tmp_path / "workflow.yml",
        tmp_path,
    )
    assert "module:w2.example" in nodes
    assert "script:src/w2/example.py" in nodes


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
        references = _referenced_dead_paths(path, text, dead)
        assert not references, f"{relative}: {sorted(references)}"


@pytest.mark.parametrize(
    ("suffix", "source_builder"),
    [
        (".sh", lambda stem: f"python -m scripts.{stem}\n"),
        (".py", lambda stem: f"from scripts import {stem}\n"),
        (".sh", lambda stem: f"python {stem}.py\n"),
        (".sh", lambda stem: f'bash -c "python {stem}.py"\n'),
    ],
)
def test_dead_reference_identity_forms_are_detected(
    suffix: str,
    source_builder: Callable[[str], str],
    tmp_path: Path,
) -> None:
    stem = "check_w2_" + "stage6b"
    dead_path = f"scripts/{stem}.py"
    source = tmp_path / f"caller{suffix}"
    text = source_builder(stem)
    assert _referenced_dead_paths(source, text, {dead_path}, tmp_path) == {dead_path}


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
        for node in _command_nodes_from_text(text, source):
            if node.startswith("module:"):
                target = node.removeprefix("module:")
                assert _resolve_module(target) is not None, (
                    f"{source.relative_to(ROOT)} -> {target}"
                )


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
    direct_scripts = {
        node for node in graph["script:scripts/check_w2_all.py"] if node.startswith("script:")
    }
    assert len(direct_scripts) == 19
    _assert_graph_excludes_heavy_tools(graph)


def test_graph_rejects_subprocess_uv_pytest(tmp_path: Path) -> None:
    graph = _write_check_graph_fixture(
        tmp_path,
        "import subprocess\nsubprocess.run(['uv', 'run', 'pytest', '-q'])\n",
    )
    with pytest.raises(AssertionError, match="pytest"):
        _assert_graph_excludes_heavy_tools(graph)


def test_graph_rejects_subprocess_alias_mypy(tmp_path: Path) -> None:
    graph = _write_check_graph_fixture(
        tmp_path,
        "from subprocess import run\nrun(['mypy', 'src'])\n",
    )
    with pytest.raises(AssertionError, match="mypy"):
        _assert_graph_excludes_heavy_tools(graph)


def test_graph_rejects_os_system_ruff(tmp_path: Path) -> None:
    graph = _write_check_graph_fixture(
        tmp_path,
        "import os\nos.system('uv run ruff check .')\n",
    )
    with pytest.raises(AssertionError, match="ruff"):
        _assert_graph_excludes_heavy_tools(graph)


def test_graph_rejects_pytest_main(tmp_path: Path) -> None:
    graph = _write_check_graph_fixture(
        tmp_path,
        "import pytest\npytest.main([])\n",
    )
    with pytest.raises(AssertionError, match="pytest"):
        _assert_graph_excludes_heavy_tools(graph)


def test_graph_rejects_shell_child_pytest(tmp_path: Path) -> None:
    graph = _write_check_graph_fixture(
        tmp_path,
        "import subprocess\nsubprocess.check_call(['bash', 'scripts/child.sh'])\n",
        extra_files={"scripts/child.sh": "#!/bin/sh\npytest -q\n"},
    )
    with pytest.raises(AssertionError, match="pytest"):
        _assert_graph_excludes_heavy_tools(graph)


@pytest.mark.parametrize(
    "loader",
    [
        "import runpy\nrunpy.run_path('scripts/indirect.py')\n",
        "import importlib\nimportlib.import_module('scripts.indirect')\n",
    ],
)
def test_graph_rejects_runpy_and_importlib_indirect_pytest(
    loader: str,
    tmp_path: Path,
) -> None:
    graph = _write_check_graph_fixture(
        tmp_path,
        loader,
        extra_files={
            "scripts/indirect.py": "import pytest\npytest.main([])\n",
        },
    )
    with pytest.raises(AssertionError, match="pytest"):
        _assert_graph_excludes_heavy_tools(graph)


def test_github_ci_owns_ruff_mypy_and_full_pytest() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "run: uv run --python 3.12 ruff check ." in workflow
    assert "run: uv run --python 3.12 mypy src apps" in workflow
    assert "run: uv run --python 3.12 pytest -q" in workflow
