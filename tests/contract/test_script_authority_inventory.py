from __future__ import annotations

import ast
import json
import re
import shlex
import subprocess
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

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
UNRESOLVED_PREFIX = "UNRESOLVED_EXECUTION:"
MATRIX_START = "<!-- SCRIPT_AUTHORITY_MATRIX_START -->"
MATRIX_END = "<!-- SCRIPT_AUTHORITY_MATRIX_END -->"
CONFIG_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])"
    r"((?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\.(?:py|sh|mjs|js|ts))"
    r"(?![A-Za-z0-9_.-])"
)
PYTHON_TOOLS = {"python", "python3", "python3.12"}
SHELL_TOOLS = {"bash", "sh"}
SHELL_CONTROL_WORDS = {
    "if",
    "then",
    "else",
    "elif",
    "fi",
    "for",
    "while",
    "until",
    "case",
    "esac",
    "do",
    "done",
    "{",
    "}",
}
ENV_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$")
EXPECTED_CHECK_W2_ALL_SCRIPTS = {
    "script:scripts/check_w2_all.py",
    "script:scripts/check_w2_stage1_contracts.py",
    "script:scripts/check_w2_stage3_data_model.py",
    "script:scripts/check_w2_stage4_ingestion.py",
    "script:scripts/check_w2_stage4b_live_smoke.py",
    "script:scripts/check_w2_stage5_asof.py",
    "script:scripts/check_w2_stage5b.py",
    "script:scripts/check_w2_stage6_market.py",
    "script:scripts/check_w2_stage7_models.py",
    "script:scripts/check_w2_stage8_replay.py",
    "script:scripts/check_w2_stage7b.py",
    "script:scripts/check_w2_stage7c.py",
    "script:scripts/check_w2_stage7d.py",
    "script:scripts/check_w2_stage7e.py",
    "script:scripts/check_w2_stage10a.py",
    "script:scripts/check_w2_stage11a.py",
    "script:scripts/check_w2_stage12a.py",
    "script:scripts/check_w2_stage13a.py",
    "script:scripts/check_w2_stage14a.py",
    "script:scripts/check_w2_stage15a.py",
}
EXPECTED_CHECK_W2_ALL_TOOLS = {"tool:python", "tool:uv"}
DELETED_MANIFEST = (
    Path("docs/ui/dashboard-v2") / ("DASHBOARD_V2_VISUAL_BASELINE_" + "MANIFEST.json")
).as_posix()


@dataclass(frozen=True)
class ModuleResolution:
    module: str
    path: str
    object_path: str | None = None


def _tracked_files(root: Path = ROOT) -> set[str]:
    output = subprocess.check_output(
        ["git", "ls-files", "-z"],
        cwd=root,
    ).decode()
    return {path for path in output.split("\0") if path}


def _module_relative(module: str) -> Path:
    return Path(*module.strip().split("."))


def _first_existing(root: Path, candidates: tuple[Path, ...]) -> str | None:
    for candidate in candidates:
        if (root / candidate).is_file():
            return candidate.as_posix()
    return None


def _resolve_importable_module(module: str, root: Path = ROOT) -> ModuleResolution | None:
    relative = _module_relative(module)
    path = _first_existing(
        root,
        (
            relative.with_suffix(".py"),
            Path("src") / relative.with_suffix(".py"),
            relative / "__init__.py",
            Path("src") / relative / "__init__.py",
        ),
    )
    if path is None:
        return None
    return ModuleResolution(module=module, path=path)


def _resolve_python_module(module: str, root: Path = ROOT) -> ModuleResolution | None:
    relative = _module_relative(module)
    path = _first_existing(
        root,
        (
            relative.with_suffix(".py"),
            Path("src") / relative.with_suffix(".py"),
            relative / "__main__.py",
            Path("src") / relative / "__main__.py",
        ),
    )
    if path is None:
        return None
    return ModuleResolution(module=module, path=path)


def _defined_names(path: str, root: Path) -> set[str]:
    try:
        tree = ast.parse((root / path).read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return set()
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                for child in ast.walk(target):
                    if isinstance(child, ast.Name):
                        names.add(child.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".", maxsplit=1)[0])
    return names


def _object_is_defined(resolution: ModuleResolution, object_path: str, root: Path) -> bool:
    first = object_path.split(".", maxsplit=1)[0]
    return bool(first) and first in _defined_names(resolution.path, root)


def _resolve_uvicorn_target(target: str, root: Path = ROOT) -> ModuleResolution | None:
    if ":" not in target:
        return None
    module, object_path = target.split(":", maxsplit=1)
    resolution = _resolve_importable_module(module, root)
    if resolution is None or not _object_is_defined(resolution, object_path, root):
        return None
    return ModuleResolution(module=module, path=resolution.path, object_path=object_path)


def _resolve_celery_target(target: str, root: Path = ROOT) -> ModuleResolution | None:
    if ":" in target:
        module, object_path = target.split(":", maxsplit=1)
        resolution = _resolve_importable_module(module, root)
        if resolution is None or not _object_is_defined(resolution, object_path, root):
            return None
        return ModuleResolution(module=module, path=resolution.path, object_path=object_path)

    exact = _resolve_importable_module(target, root)
    if exact is not None:
        return exact

    parts = target.split(".")
    for size in range(len(parts) - 1, 0, -1):
        module = ".".join(parts[:size])
        object_path = ".".join(parts[size:])
        resolution = _resolve_importable_module(module, root)
        if resolution is not None and _object_is_defined(resolution, object_path, root):
            return ModuleResolution(
                module=module,
                path=resolution.path,
                object_path=object_path,
            )
    return None


def _module_resolution_nodes(
    resolution: ModuleResolution | None,
    target: str,
    kind: str,
) -> set[str]:
    if resolution is None:
        return {f"{UNRESOLVED_PREFIX}{kind}:{target}"}
    return {
        f"module:{resolution.module}",
        f"script:{resolution.path}",
    }


def _import_module_nodes(module: str, root: Path) -> set[str]:
    return _module_resolution_nodes(
        _resolve_importable_module(module, root),
        module,
        "import-module",
    )


def _configuration_sources(tracked: set[str], root: Path = ROOT) -> list[Path]:
    sources: list[Path] = []
    for relative in sorted(tracked):
        if (
            relative == "pyproject.toml"
            or relative == "alembic.ini"
            or relative == "docker-compose.yml"
            or relative == "Makefile"
            or relative.startswith("Dockerfile")
            or Path(relative).name == "package.json"
            or relative.startswith(".github/workflows/")
            or relative.startswith("infra/")
            or Path(relative).name == "crontab"
            or Path(relative).suffix == ".cron"
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


def _strip_wrapper_options(
    words: list[str],
    valued_options: set[str],
    *,
    skip_assignments: bool = False,
) -> list[str]:
    remaining = list(words)
    while remaining:
        word = remaining[0]
        if word == "--":
            return remaining[1:]
        if skip_assignments and "=" in word and not word.startswith("-"):
            remaining.pop(0)
            continue
        if not word.startswith("-"):
            break
        option = remaining.pop(0)
        if option in valued_options and remaining:
            remaining.pop(0)
    return remaining


def _contains_dynamic_shell(words: list[str]) -> bool:
    return any("$" in word or "`" in word or "${" in word or "$(" in word for word in words)


def _script_target_nodes(target: str, source: Path, root: Path) -> set[str]:
    normalized = target.removeprefix("./")
    nodes = {f"path:{normalized}"}
    resolved = _resolved_path_node(target, source, root)
    if resolved is None:
        nodes.add(f"{UNRESOLVED_PREFIX}script-path:{target}")
    else:
        nodes.add(resolved)
    return nodes


def _python_api_tool(name: str) -> str | None:
    if name in {"pytest.main", "pytest.console_main"}:
        return "pytest"
    if name in {"mypy.api.run", "mypy.main.main", "mypy.__main__.console_entry"}:
        return "mypy"
    if name in {"ruff.main", "ruff.__main__.main", "ruff.__main__.find_ruff_bin"}:
        return "ruff"
    return None


def _command_segment_nodes(words: list[str], source: Path, root: Path) -> set[str]:
    if not words:
        return set()
    while words and ENV_ASSIGNMENT_RE.fullmatch(words[0]):
        words = words[1:]
    if not words:
        return {f"{UNRESOLVED_PREFIX}environment-assignment"}
    raw_executable = words[0]
    executable = raw_executable if raw_executable == "." else Path(raw_executable).name
    if executable == "__PYTHON__":
        executable = "python"
    nodes = {f"tool:{executable}"}
    arguments = words[1:]

    if executable in SHELL_CONTROL_WORDS:
        return {f"{UNRESOLVED_PREFIX}shell-control:{executable}"}

    if _contains_dynamic_shell(words):
        nodes.add(f"{UNRESOLVED_PREFIX}dynamic-shell-command")

    if executable in HEAVY_TEST_TOOLS:
        return {f"tool:{executable}"}

    if Path(raw_executable).suffix in SCRIPT_SUFFIXES:
        nodes.update(_script_target_nodes(raw_executable, source, root))
        return nodes

    if executable in {"source", "."}:
        target = _first_positional(arguments)
        if target is None:
            nodes.add(f"{UNRESOLVED_PREFIX}{executable}")
        else:
            nodes.update(_script_target_nodes(target, source, root))
        return nodes

    if executable == "exec":
        nested = _strip_wrapper_options(arguments, set())
        if nested:
            nodes.update(_command_segment_nodes(nested, source, root))
        else:
            nodes.add(f"{UNRESOLVED_PREFIX}exec")
        return nodes

    if executable == "env":
        nested = _strip_wrapper_options(
            arguments,
            {"-u", "--unset", "-C", "--chdir", "-S", "--split-string"},
            skip_assignments=True,
        )
        if nested:
            nodes.update(_command_segment_nodes(nested, source, root))
        else:
            nodes.add(f"{UNRESOLVED_PREFIX}env")
        return nodes

    if executable == "sudo":
        nested = _strip_wrapper_options(
            arguments,
            {"-u", "--user", "-g", "--group", "-h", "--host", "-p", "--prompt", "-C"},
        )
        if nested:
            nodes.update(_command_segment_nodes(nested, source, root))
        else:
            nodes.add(f"{UNRESOLVED_PREFIX}sudo")
        return nodes

    if executable == "timeout":
        nested = _strip_wrapper_options(
            arguments,
            {"-k", "--kill-after", "-s", "--signal"},
        )
        if nested:
            nested = nested[1:]
        if nested:
            nodes.update(_command_segment_nodes(nested, source, root))
        else:
            nodes.add(f"{UNRESOLVED_PREFIX}timeout")
        return nodes

    if executable == "uv":
        if "run" not in arguments:
            return nodes
        nested = arguments[arguments.index("run") + 1 :]
        nested = _strip_wrapper_options(
            nested,
            {
                "--python",
                "-p",
                "--project",
                "--directory",
                "--with",
                "--package",
                "--index",
            },
        )
        if nested:
            nodes.update(_command_segment_nodes(nested, source, root))
        else:
            nodes.add(f"{UNRESOLVED_PREFIX}uv-run")
        return nodes

    if executable in PYTHON_TOOLS:
        if "-m" in arguments:
            index = arguments.index("-m")
            if index + 1 < len(arguments):
                module = arguments[index + 1]
                heavy = module.split(".", maxsplit=1)[0]
                if heavy in HEAVY_TEST_TOOLS:
                    nodes.add(f"tool:{heavy}")
                else:
                    nodes.update(
                        _module_resolution_nodes(
                            _resolve_python_module(module, root),
                            module,
                            "python-m",
                        )
                    )
            else:
                nodes.add(f"{UNRESOLVED_PREFIX}python-m")
            return nodes
        if "-c" in arguments:
            index = arguments.index("-c")
            if index + 1 < len(arguments):
                try:
                    nodes.update(_python_execution_nodes(arguments[index + 1], source, root))
                except SyntaxError:
                    nodes.add(f"{UNRESOLVED_PREFIX}python-c")
            else:
                nodes.add(f"{UNRESOLVED_PREFIX}python-c")
            return nodes
        target = _first_positional(arguments)
        if target:
            if _contains_dynamic_shell([target]):
                nodes.add(f"{UNRESOLVED_PREFIX}python-script-target:{target}")
            elif Path(target).suffix in SCRIPT_SUFFIXES:
                nodes.update(_script_target_nodes(target, source, root))
        return nodes

    if executable == "uvicorn":
        target = _first_positional(arguments)
        if target:
            nodes.update(
                _module_resolution_nodes(
                    _resolve_uvicorn_target(target, root),
                    target,
                    "uvicorn",
                )
            )
        else:
            nodes.add(f"{UNRESOLVED_PREFIX}uvicorn")
        return nodes

    if executable == "celery":
        found = False
        for option in ("-A", "--app"):
            if option in arguments:
                index = arguments.index(option)
                if index + 1 < len(arguments):
                    target = arguments[index + 1]
                    nodes.update(
                        _module_resolution_nodes(
                            _resolve_celery_target(target, root),
                            target,
                            "celery",
                        )
                    )
                    found = True
        for argument in arguments:
            if argument.startswith("--app="):
                target = argument.split("=", maxsplit=1)[1]
                nodes.update(
                    _module_resolution_nodes(
                        _resolve_celery_target(target, root),
                        target,
                        "celery",
                    )
                )
                found = True
        if not found:
            nodes.add(f"{UNRESOLVED_PREFIX}celery-app")
        return nodes

    if executable in SHELL_TOOLS:
        if "-c" in arguments:
            index = arguments.index("-c")
            if index + 1 < len(arguments):
                nodes.update(_command_nodes(arguments[index + 1], source, root))
            else:
                nodes.add(f"{UNRESOLVED_PREFIX}{executable}-c")
            return nodes
        remaining = _strip_wrapper_options(
            arguments,
            {"-O", "+O", "--rcfile", "--init-file"},
        )
        target = _first_positional(remaining)
        if target:
            nodes.update(_script_target_nodes(target, source, root))
        else:
            nodes.add(f"{UNRESOLVED_PREFIX}{executable}-script")
        return nodes

    if executable == "node":
        if "-e" in arguments or "--eval" in arguments:
            return nodes
        target = _first_positional(arguments)
        if target:
            nodes.update(_script_target_nodes(target, source, root))
        else:
            nodes.add(f"{UNRESOLVED_PREFIX}node-script")
        return nodes

    return nodes


def _command_nodes(command: str, source: Path, root: Path = ROOT) -> set[str]:
    nodes: set[str] = set()
    for segment in _command_segments(command):
        nodes.update(_command_segment_nodes(segment, source, root))
    return nodes


def _logical_shell_lines(text: str) -> list[str]:
    lines: list[str] = []
    current = ""
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("#!"):
            continue
        current = f"{current} {stripped}".strip()
        if current.endswith("\\"):
            current = current[:-1].rstrip()
            continue
        lines.append(current.lstrip("@-+"))
        current = ""
    if current:
        lines.append(current)
    return lines


def _shell_command_sequences(text: str) -> list[list[str]]:
    sequences: list[list[str]] = []
    for line in _logical_shell_lines(text):
        sequences.extend(_command_segments(line))
    return sequences


def _value_sequences(value: object) -> list[list[str]]:
    if isinstance(value, str):
        return _shell_command_sequences(value)
    if isinstance(value, dict):
        sequences: list[list[str]] = []
        for item in value.values():
            sequences.extend(_value_sequences(item))
        return sequences
    if isinstance(value, list):
        if value and all(isinstance(item, (str, int, float)) for item in value):
            return [[str(item) for item in value]]
        sequences: list[list[str]] = []
        for item in value:
            sequences.extend(_value_sequences(item))
        return sequences
    return []


def _yaml_command_sequences(data: object) -> list[list[str]]:
    sequences: list[list[str]] = []
    if isinstance(data, dict):
        for key, value in data.items():
            if str(key) == "healthcheck" and isinstance(value, dict):
                sequences.extend(_healthcheck_sequences(value.get("test")))
            elif str(key) in {"run", "command", "entrypoint"}:
                sequences.extend(_value_sequences(value))
            else:
                sequences.extend(_yaml_command_sequences(value))
    elif isinstance(data, list):
        for item in data:
            sequences.extend(_yaml_command_sequences(item))
    return sequences


def _healthcheck_sequences(value: object) -> list[list[str]]:
    sequences: list[list[str]] = []
    for words in _value_sequences(value):
        if not words:
            continue
        marker = words[0].upper()
        if marker == "CMD":
            sequences.append(words[1:])
        elif marker == "CMD-SHELL":
            sequences.extend(_shell_command_sequences(" ".join(words[1:])))
        elif marker == "NONE":
            continue
        else:
            sequences.append(words)
    return sequences


def _dockerfile_command_sequences(text: str) -> list[list[str]]:
    sequences: list[list[str]] = []
    for line in _logical_shell_lines(text):
        match = re.match(
            r"^(CMD|ENTRYPOINT|RUN|HEALTHCHECK)\s+(.+)$",
            line,
            re.IGNORECASE,
        )
        if match is None:
            continue
        instruction = match.group(1).upper()
        payload = match.group(2).strip()
        if instruction == "HEALTHCHECK":
            command_match = re.search(r"(?:^|\s)CMD\s+(.+)$", payload, re.IGNORECASE)
            if command_match is None:
                sequences.append([f"{UNRESOLVED_PREFIX}docker-healthcheck"])
                continue
            command = command_match.group(1).strip()
            if command.startswith("["):
                try:
                    value = json.loads(command)
                except json.JSONDecodeError:
                    sequences.append([f"{UNRESOLVED_PREFIX}docker-healthcheck-json"])
                else:
                    sequences.extend(_healthcheck_sequences(["CMD", *value]))
            else:
                sequences.extend(_shell_command_sequences(command))
        elif instruction in {"CMD", "ENTRYPOINT"} and payload.startswith("["):
            try:
                value = json.loads(payload)
            except json.JSONDecodeError:
                sequences.append([f"{UNRESOLVED_PREFIX}docker-json"])
            else:
                sequences.extend(_value_sequences(value))
        else:
            sequences.extend(_shell_command_sequences(payload))
    return sequences


def _systemd_command_sequences(text: str) -> list[list[str]]:
    sequences: list[list[str]] = []
    for line in _logical_shell_lines(text):
        match = re.match(r"^Exec[A-Za-z]*=(.+)$", line)
        if match is not None:
            sequences.extend(_shell_command_sequences(match.group(1)))
    return sequences


def _makefile_command_sequences(text: str) -> list[list[str]]:
    variables: dict[str, str] = {}
    command_lines: list[str] = []
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if raw_line.startswith("\t"):
            command_lines.append(raw_line.strip().lstrip("@-+"))
            continue
        line = raw_line.strip()
        assignment = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*[?:]?=\s*(.+)$", line)
        if assignment is not None:
            variables[assignment.group(1)] = assignment.group(2)
    expanded = "\n".join(command_lines)
    for name, value in variables.items():
        expanded = expanded.replace(f"$({name})", value).replace(f"${{{name}}}", value)
    return _shell_command_sequences(expanded)


def _cron_command_sequences(text: str) -> list[list[str]]:
    sequences: list[list[str]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("@"):
            parts = line.split(maxsplit=1)
            if len(parts) != 2:
                sequences.append([f"{UNRESOLVED_PREFIX}cron-macro"])
            else:
                sequences.extend(_shell_command_sequences(parts[1]))
            continue
        parts = line.split(maxsplit=5)
        if len(parts) != 6:
            sequences.append([f"{UNRESOLVED_PREFIX}cron-fields"])
            continue
        sequences.extend(_shell_command_sequences(parts[5]))
    return sequences


def _configuration_command_sequences(source: Path, text: str) -> list[list[str]]:
    relative = source.as_posix()
    if source.suffix in {".yml", ".yaml"}:
        try:
            return _yaml_command_sequences(yaml.safe_load(text))
        except yaml.YAMLError:
            return [[f"{UNRESOLVED_PREFIX}yaml"]]
    if source.suffix == ".json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return [[f"{UNRESOLVED_PREFIX}json"]]
        if source.name == "package.json" and isinstance(data, dict):
            return _value_sequences(data.get("scripts", {}))
        return _yaml_command_sequences(data)
    if source.name.startswith("Dockerfile"):
        return _dockerfile_command_sequences(text)
    if source.suffix in {".service", ".timer"}:
        return _systemd_command_sequences(text)
    if source.name == "crontab" or source.suffix == ".cron" or "cron" in source.parts:
        return _cron_command_sequences(text)
    if source.name == "Makefile":
        return _makefile_command_sequences(text)
    if source.suffix == ".sh":
        return _shell_command_sequences(text)
    if ".github/workflows/" in relative or "/compose/" in relative:
        try:
            return _yaml_command_sequences(yaml.safe_load(text))
        except yaml.YAMLError:
            return [[f"{UNRESOLVED_PREFIX}yaml"]]
    return _shell_command_sequences(text)


def _command_nodes_from_text(text: str, source: Path, root: Path = ROOT) -> set[str]:
    nodes: set[str] = set()
    for words in _configuration_command_sequences(source, text):
        if words and words[0].startswith(UNRESOLVED_PREFIX):
            nodes.add(words[0])
        else:
            nodes.update(_command_segment_nodes(words, source, root))
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
            if node.startswith(
                (
                    f"{UNRESOLVED_PREFIX}python-m:",
                    f"{UNRESOLVED_PREFIX}uvicorn:",
                    f"{UNRESOLVED_PREFIX}celery:",
                    f"{UNRESOLVED_PREFIX}script-path:",
                    f"{UNRESOLVED_PREFIX}python-script-target:",
                )
            ):
                raise AssertionError(
                    f"{source.relative_to(root)} has unresolved execution target: {node}"
                )
            if node.startswith("script:"):
                entrypoints.add(node.removeprefix("script:"))

    project_path = root / "pyproject.toml"
    if project_path.is_file():
        project = tomllib.loads(project_path.read_text(encoding="utf-8"))
        for target in project.get("project", {}).get("scripts", {}).values():
            module = str(target).split(":", maxsplit=1)[0]
            resolved = _resolve_importable_module(module, root)
            if resolved is None:
                raise AssertionError(f"unresolved pyproject entrypoint: {target}")
            entrypoints.add(resolved.path)

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


def _script_paths(nodes: set[str]) -> set[str]:
    return {node.removeprefix("script:") for node in nodes if node.startswith("script:")}


def _configuration_execution_targets(
    predicate: Callable[[Path], bool],
    root: Path = ROOT,
) -> set[str]:
    targets: set[str] = set()
    for source in _configuration_sources(_tracked_files(root), root):
        if not predicate(source):
            continue
        text = source.read_text(encoding="utf-8")
        targets.update(_script_paths(_command_nodes_from_text(text, source, root)))
    return targets


def _pyproject_entrypoint_targets(root: Path = ROOT) -> set[str]:
    project_path = root / "pyproject.toml"
    if not project_path.is_file():
        return set()
    project = tomllib.loads(project_path.read_text(encoding="utf-8"))
    targets: set[str] = set()
    for target in project.get("project", {}).get("scripts", {}).values():
        module = str(target).split(":", maxsplit=1)[0]
        resolved = _resolve_importable_module(module, root)
        if resolved is not None:
            targets.add(resolved.path)
    return targets


def _runtime_execution_targets(root: Path = ROOT) -> set[str]:
    targets = _configuration_execution_targets(
        lambda source: (
            source.name.startswith("Dockerfile")
            or source.name == "docker-compose.yml"
            or source.name == "package.json"
            or source.suffix in {".yml", ".yaml"}
            and "compose" in source.as_posix()
        ),
        root,
    )
    return targets | _pyproject_entrypoint_targets(root)


def _ci_direct_targets(root: Path = ROOT) -> set[str]:
    return _configuration_execution_targets(
        lambda source: ".github/workflows/" in source.as_posix(),
        root,
    )


def _assigned_script_paths(tree: ast.AST) -> dict[str, set[str]]:
    assignments: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        value = node.value
        if value is None:
            continue
        paths = {
            child.value.removeprefix("./")
            for child in ast.walk(value)
            if isinstance(child, ast.Constant)
            and isinstance(child.value, str)
            and Path(child.value).suffix in SCRIPT_SUFFIXES
        }
        for target in targets:
            if isinstance(target, ast.Name) and paths:
                assignments[target.id] = paths
    return assignments


def _subprocess_script_targets(text: str, root: Path = ROOT) -> set[str]:
    tree = ast.parse(text)
    aliases = _import_aliases(tree)
    assignments = _assigned_script_paths(tree)
    targets: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _expression_name(node.func, aliases)
        if name not in {
            "subprocess.run",
            "subprocess.Popen",
            "subprocess.check_call",
            "subprocess.check_output",
        }:
            continue
        argument = _call_command_argument(node)
        if argument is None:
            continue
        candidates = {
            child.value.removeprefix("./")
            for child in ast.walk(argument)
            if isinstance(child, ast.Constant)
            and isinstance(child.value, str)
            and Path(child.value).suffix in SCRIPT_SUFFIXES
        }
        candidates.update(
            path
            for child in ast.walk(argument)
            if isinstance(child, ast.Name)
            for path in assignments.get(child.id, set())
        )
        targets.update(path for path in candidates if (root / path).is_file())
    return targets


def _ci_transitive_targets(root: Path = ROOT) -> set[str]:
    graph = _check_w2_all_graph(root)
    targets = {
        node.removeprefix("script:")
        for node in graph
        if node.startswith("script:") and node != "script:scripts/check_w2_all.py"
    }
    tests_root = root / "tests"
    if not tests_root.is_dir():
        return targets
    for source in tests_root.rglob("*.py"):
        text = source.read_text(encoding="utf-8")
        try:
            targets.update(_script_paths(_python_execution_nodes(text, source, root)))
            targets.update(_subprocess_script_targets(text, root))
        except SyntaxError:
            continue
    return targets


def _release_execution_targets(root: Path = ROOT) -> set[str]:
    targets = _configuration_execution_targets(
        lambda source: (
            source.name.startswith("Dockerfile")
            or source.name == "package.json"
            or source.suffix in {".service", ".timer", ".cron"}
            or source.name == "crontab"
            or "compose" in source.as_posix()
        ),
        root,
    )
    scripts_root = root / "scripts"
    if scripts_root.is_dir():
        for source in scripts_root.glob("*.sh"):
            targets.update(
                _script_paths(
                    _command_nodes_from_text(
                        source.read_text(encoding="utf-8"),
                        source,
                        root,
                    )
                )
            )
    runbooks = root / "docs/runbooks"
    if runbooks.is_dir():
        for source in runbooks.rglob("*.md"):
            targets.update(
                _script_paths(
                    _command_nodes_from_text(
                        source.read_text(encoding="utf-8"),
                        source,
                        root,
                    )
                )
            )
    return targets


def _migration_execution_targets(root: Path = ROOT) -> set[str]:
    targets: set[str] = set()
    alembic_path = root / "alembic.ini"
    if alembic_path.is_file():
        match = re.search(
            r"^script_location\s*=\s*(\S+)\s*$",
            alembic_path.read_text(encoding="utf-8"),
            re.MULTILINE,
        )
        if match is not None:
            env_path = Path(match.group(1)) / "env.py"
            if (root / env_path).is_file():
                targets.add(env_path.as_posix())
    versions = root / "migrations/versions"
    if versions.is_dir():
        for source in versions.glob("*.py"):
            targets.update(_subprocess_script_targets(source.read_text(encoding="utf-8"), root))
    return targets


def _classification_paths(
    rows: list[tuple[str, str, str]],
    classification: str,
) -> set[str]:
    return {path for path, observed, _decision in rows if observed == classification}


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


def _static_command_part(node: ast.expr, aliases: dict[str, str]) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if _expression_name(node, aliases) == "sys.executable":
        return "__PYTHON__"
    return None


def _static_command(node: ast.expr, aliases: dict[str, str]) -> str | None:
    scalar = _static_command_part(node, aliases)
    if scalar is not None:
        return scalar
    if isinstance(node, (ast.List, ast.Tuple)):
        parts = [_static_command_part(item, aliases) for item in node.elts]
        if all(part is not None for part in parts):
            return shlex.join([part for part in parts if part is not None])
    return None


def _call_command_argument(node: ast.Call) -> ast.expr | None:
    return node.args[0] if node.args else None


def _static_string(node: ast.expr, aliases: dict[str, str]) -> str | None:
    value = _static_command_part(node, aliases)
    return value if value != "__PYTHON__" else None


def _python_execution_nodes(text: str, source: Path, root: Path = ROOT) -> set[str]:
    tree = ast.parse(text)
    aliases = _import_aliases(tree)
    nodes: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("scripts."):
                    nodes.update(_import_module_nodes(alias.name, root))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "scripts":
                for alias in node.names:
                    nodes.update(_import_module_nodes(f"scripts.{alias.name}", root))
            elif module.startswith("scripts."):
                nodes.update(_import_module_nodes(module, root))
        elif isinstance(node, ast.Call):
            name = _expression_name(node.func, aliases)
            api_tool = _python_api_tool(name)
            if api_tool is not None:
                nodes.add(f"tool:{api_tool}")
            if name in {
                "subprocess.run",
                "subprocess.Popen",
                "subprocess.check_call",
                "subprocess.check_output",
            }:
                argument = _call_command_argument(node)
                command = _static_command(argument, aliases) if argument is not None else None
                if command is None:
                    nodes.add(f"{UNRESOLVED_PREFIX}{name}")
                else:
                    nodes.update(_command_nodes(command, source, root))
            elif name in {"os.system", "os.popen"}:
                argument = _call_command_argument(node)
                command = _static_command(argument, aliases) if argument is not None else None
                if command is None:
                    nodes.add(f"{UNRESOLVED_PREFIX}{name}")
                else:
                    nodes.update(_command_nodes(command, source, root))
            elif name in {"runpy.run_module", "importlib.import_module"}:
                argument = _call_command_argument(node)
                module = _static_string(argument, aliases) if argument is not None else None
                if module is None:
                    nodes.add(f"{UNRESOLVED_PREFIX}{name}")
                else:
                    nodes.update(_import_module_nodes(module, root))
            elif name == "runpy.run_path":
                argument = _call_command_argument(node)
                target = _static_string(argument, aliases) if argument is not None else None
                if target is None:
                    nodes.add(f"{UNRESOLVED_PREFIX}{name}")
                else:
                    nodes.update(_script_target_nodes(target, source, root))
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
            module = node.removeprefix("module:")
            resolved = _resolve_importable_module(module, root)
            graph[node] = (
                {f"script:{resolved.path}"}
                if resolved is not None
                else {f"{UNRESOLVED_PREFIX}graph-module:{module}"}
            )
        else:
            graph[node] = set()
        pending.extend(graph[node])
    return graph


def _assert_graph_excludes_heavy_tools(graph: dict[str, set[str]]) -> None:
    unresolved = sorted(node for node in graph if node.startswith(UNRESOLVED_PREFIX))
    assert not unresolved, f"reachable unresolved execution: {unresolved}"
    forbidden = sorted(
        node.removeprefix("tool:")
        for node in graph
        if node.startswith("tool:") and node.removeprefix("tool:").lower() in HEAVY_TEST_TOOLS
    )
    assert not forbidden, f"reachable heavy test tools: {forbidden}"


def _assert_graph_topology(
    graph: dict[str, set[str]],
    *,
    expected_scripts: set[str],
    expected_tools: set[str],
) -> None:
    unresolved = {node for node in graph if node.startswith(UNRESOLVED_PREFIX)}
    scripts = {node for node in graph if node.startswith("script:")}
    tools = {node for node in graph if node.startswith("tool:")}
    assert not unresolved, f"reachable unresolved execution: {sorted(unresolved)}"
    assert scripts == expected_scripts, (
        f"unexpected_scripts={sorted(scripts - expected_scripts)} "
        f"missing_scripts={sorted(expected_scripts - scripts)}"
    )
    assert tools == expected_tools, (
        f"unexpected_tools={sorted(tools - expected_tools)} "
        f"missing_tools={sorted(expected_tools - tools)}"
    )


def _deletion_identities(path: str) -> set[str]:
    relative = Path(path)
    identities = {
        relative.as_posix(),
        relative.name,
    }
    if relative.suffix in SCRIPT_SUFFIXES:
        identities.update(
            {
                relative.stem,
                relative.with_suffix("").as_posix().replace("/", "."),
            }
        )
    return identities


def _deletion_closure() -> set[str]:
    dead = {path for path, classification, _decision in _matrix_rows() if classification == "DEAD"}
    assert len(dead) == 8
    return dead | {DELETED_MANIFEST}


def _assert_deleted_objects_absent(
    deleted: set[str],
    *,
    tracked: set[str],
    root: Path,
) -> None:
    for path in deleted:
        assert path not in tracked, f"deleted path is tracked again: {path}"
        assert not (root / path).exists(), f"deleted path exists again: {path}"


def _node_identities(node: str) -> set[str]:
    value = node.split(":", maxsplit=1)[-1].removeprefix("./")
    path = Path(value)
    identities = {value, path.name, path.stem}
    if "/" in value:
        identities.add(path.with_suffix("").as_posix().replace("/", "."))
    return identities


def _referenced_deleted_paths(
    source: Path,
    text: str,
    deleted: set[str],
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
    for path in deleted:
        identities = _deletion_identities(path)
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
    observed_classifications = {classification for _path, classification, _decision in rows}
    assert not (observed_classifications - ALLOWED_CLASSIFICATIONS)

    dead = {path for path, classification, _decision in rows if classification == "DEAD"}
    retained = {
        path
        for path, classification, decision in rows
        if classification != "DEAD" and decision == "KEEP"
    }
    assert set(paths) == retained | dead
    _assert_inventory_classified(_inventory_universe(), rows)


def test_classification_counts_and_exact_execution_evidence() -> None:
    rows = _matrix_rows()
    expected_counts = {
        "RUNTIME_ENTRYPOINT": 8,
        "CI_DIRECT": 7,
        "CI_TRANSITIVE": 30,
        "DEPLOYMENT": 8,
        "MANUAL_OPS": 72,
        "MIGRATION_ONLY": 1,
        "ONE_TIME_RECOVERY": 11,
        "DEAD": 8,
    }
    observed_counts = {
        classification: len(_classification_paths(rows, classification))
        for classification in ALLOWED_CLASSIFICATIONS
    }
    assert observed_counts == expected_counts
    assert sum(observed_counts.values()) == 145

    runtime = _classification_paths(rows, "RUNTIME_ENTRYPOINT")
    ci_direct = _classification_paths(rows, "CI_DIRECT")
    ci_transitive = _classification_paths(rows, "CI_TRANSITIVE")
    deployment = _classification_paths(rows, "DEPLOYMENT")
    migration = _classification_paths(rows, "MIGRATION_ONLY")

    assert runtime <= _runtime_execution_targets()
    assert ci_direct == _ci_direct_targets()
    assert ci_transitive <= _ci_transitive_targets()
    assert deployment <= _release_execution_targets()
    assert migration <= _migration_execution_targets()


def test_same_named_library_calls_do_not_count_as_script_execution() -> None:
    worker = ROOT / "apps/worker/celery_app.py"
    migration = ROOT / "migrations/versions/0037_seed_competition_runtime_authority.py"
    worker_nodes = _python_execution_nodes(worker.read_text(encoding="utf-8"), worker)
    migration_nodes = _python_execution_nodes(
        migration.read_text(encoding="utf-8"),
        migration,
    )
    assert "script:scripts/run_xg_history_backfill.py" not in worker_nodes
    assert "script:scripts/seed_competition_runtime_authority.py" not in migration_nodes
    assert "scripts/run_xg_history_backfill.py" not in _runtime_execution_targets()
    assert "scripts/seed_competition_runtime_authority.py" not in (_migration_execution_targets())


def test_checklist_acceptance_claims_match_computed_contracts() -> None:
    text = MASTER_CHECKLIST.read_text(encoding="utf-8")
    rows = _matrix_rows()
    for classification in ALLOWED_CLASSIFICATIONS:
        count = len(_classification_paths(rows, classification))
        assert f"{classification} = {count}" in text
    graph = _check_w2_all_graph()
    edge_count = sum(len(edges) for edges in graph.values())
    assert f"EXECUTION_GRAPH = {len(graph)}_NODES_{edge_count}_EDGES" in text
    assert f"CHECK_W2_ALL_EXACT_SCRIPT_NODES = {len(EXPECTED_CHECK_W2_ALL_SCRIPTS)}" in text
    assert f"CHECK_W2_ALL_EXACT_TOOL_NODES = {len(EXPECTED_CHECK_W2_ALL_TOOLS)}" in text
    assert f"DELETION_CLOSURE_OBJECTS = {len(_deletion_closure())}" in text
    assert "CLASSIFICATION_EVIDENCE_CONTRACT = PASS" in text
    assert "CONFIGURATION_EXECUTION_SURFACE_CONTRACT = PASS" in text
    assert "DELETION_CLOSURE_ABSENCE_AND_REFERENCE = PASS" in text


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


def _write_example_module(tmp_path: Path, text: str = "app = object()\n") -> Path:
    module = tmp_path / "src/w2/example.py"
    module.parent.mkdir(parents=True)
    module.write_text(text, encoding="utf-8")
    return module


def test_python_module_requires_exact_target(tmp_path: Path) -> None:
    _write_example_module(tmp_path)
    nodes = _command_nodes("python -m w2.nonexistent", tmp_path / "config.yml", tmp_path)
    assert f"{UNRESOLVED_PREFIX}python-m:w2.nonexistent" in nodes


def test_python_module_rejects_package_without_main(tmp_path: Path) -> None:
    package = tmp_path / "src/w2/package"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("VALUE = 1\n", encoding="utf-8")
    nodes = _command_nodes("python -m w2.package", tmp_path / "config.yml", tmp_path)
    assert f"{UNRESOLVED_PREFIX}python-m:w2.package" in nodes


def test_python_module_file_resolves_exactly(tmp_path: Path) -> None:
    _write_example_module(tmp_path)
    nodes = _command_nodes("python -m w2.example", tmp_path / "config.yml", tmp_path)
    assert {"module:w2.example", "script:src/w2/example.py"} <= nodes


def test_python_package_main_resolves_exactly(tmp_path: Path) -> None:
    package = tmp_path / "src/w2/package"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("VALUE = 1\n", encoding="utf-8")
    (package / "__main__.py").write_text("print('ok')\n", encoding="utf-8")
    nodes = _command_nodes("python -m w2.package", tmp_path / "config.yml", tmp_path)
    assert {"module:w2.package", "script:src/w2/package/__main__.py"} <= nodes


def test_uvicorn_module_object_resolves_exactly(tmp_path: Path) -> None:
    _write_example_module(tmp_path)
    nodes = _command_nodes("uvicorn w2.example:app", tmp_path / "config.yml", tmp_path)
    assert {"module:w2.example", "script:src/w2/example.py"} <= nodes


@pytest.mark.parametrize(
    "target",
    [
        "w2.example:app",
        "w2.example.app",
    ],
)
def test_celery_module_object_resolves_exactly(target: str, tmp_path: Path) -> None:
    _write_example_module(tmp_path)
    nodes = _command_nodes(f"celery -A {target} worker", tmp_path / "config.yml", tmp_path)
    assert {"module:w2.example", "script:src/w2/example.py"} <= nodes


@pytest.mark.parametrize(
    ("command", "kind"),
    [
        ("uvicorn w2.nonexistent:app", "uvicorn"),
        ("celery -A w2.nonexistent:app worker", "celery"),
    ],
)
def test_server_entrypoint_rejects_nonexistent_module(
    command: str,
    kind: str,
    tmp_path: Path,
) -> None:
    nodes = _command_nodes(command, tmp_path / "config.yml", tmp_path)
    assert any(node.startswith(f"{UNRESOLVED_PREFIX}{kind}:") for node in nodes)


def test_uv_run_python_module_entrypoint_resolves(tmp_path: Path) -> None:
    _write_example_module(tmp_path, "VALUE = 1\n")
    nodes = _command_nodes(
        "uv run --python 3.12 python -m w2.example",
        tmp_path / "workflow.yml",
        tmp_path,
    )
    assert "module:w2.example" in nodes
    assert "script:src/w2/example.py" in nodes


@pytest.mark.parametrize(
    ("name", "text", "expected"),
    [
        (
            "docker-compose.yml",
            """
services:
  worker:
    command:
      - python
      - -m
      - w2.example
""",
            "module:w2.example",
        ),
        (
            "workflow.yml",
            """
jobs:
  verify:
    steps:
      - run: |
          python -m w2.example
      - run:
          - uvicorn
          - w2.example:app
""",
            "module:w2.example",
        ),
        (
            "docker-compose.yml",
            """
services:
  worker:
    command:
      - celery
      - -A
      - w2.example:app
      - worker
""",
            "module:w2.example",
        ),
        (
            "workflow.yaml",
            """
jobs:
  serve:
    steps:
      - run:
          - uvicorn
          - w2.example:app
""",
            "module:w2.example",
        ),
    ],
)
def test_multiline_yaml_commands_resolve_modules(
    name: str,
    text: str,
    expected: str,
    tmp_path: Path,
) -> None:
    _write_example_module(tmp_path)
    source = tmp_path / name
    nodes = _command_nodes_from_text(text, source, tmp_path)
    assert expected in nodes
    assert not any(node.startswith(UNRESOLVED_PREFIX) for node in nodes)


def test_package_json_script_resolves_module(tmp_path: Path) -> None:
    _write_example_module(tmp_path)
    source = tmp_path / "package.json"
    text = json.dumps({"scripts": {"serve": "uvicorn w2.example:app"}})
    nodes = _command_nodes_from_text(text, source, tmp_path)
    assert {"module:w2.example", "script:src/w2/example.py"} <= nodes


def test_systemd_exec_start_post_is_parsed(tmp_path: Path) -> None:
    script = tmp_path / "scripts/post.sh"
    script.parent.mkdir(parents=True)
    script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    source = tmp_path / "fixture.service"
    text = "[Service]\nExecStartPost=/bin/bash scripts/post.sh\n"
    nodes = _command_nodes_from_text(text, source, tmp_path)
    assert "script:scripts/post.sh" in nodes


def test_compose_healthcheck_python_module_is_parsed(tmp_path: Path) -> None:
    _write_example_module(tmp_path)
    source = tmp_path / "docker-compose.yml"
    text = """
services:
  api:
    healthcheck:
      test: [CMD, python, -m, w2.example]
"""
    nodes = _command_nodes_from_text(text, source, tmp_path)
    assert {"module:w2.example", "script:src/w2/example.py"} <= nodes


def test_docker_healthcheck_python_module_is_parsed(tmp_path: Path) -> None:
    _write_example_module(tmp_path)
    source = tmp_path / "Dockerfile.api"
    nodes = _command_nodes_from_text(
        "HEALTHCHECK CMD python -m w2.example\n",
        source,
        tmp_path,
    )
    assert {"module:w2.example", "script:src/w2/example.py"} <= nodes


@pytest.mark.parametrize(
    "line",
    [
        "* * * * * python scripts/cron_job.py",
        "@reboot python scripts/cron_job.py",
    ],
)
def test_cron_script_commands_are_parsed(line: str, tmp_path: Path) -> None:
    script = tmp_path / "scripts/cron_job.py"
    script.parent.mkdir(parents=True)
    script.write_text("print('ok')\n", encoding="utf-8")
    source = tmp_path / "fixture.cron"
    nodes = _command_nodes_from_text(line + "\n", source, tmp_path)
    assert "script:scripts/cron_job.py" in nodes


def test_environment_assignment_precedes_command(tmp_path: Path) -> None:
    source = tmp_path / "fixture.sh"
    nodes = _command_nodes("MODE=test pytest -q", source, tmp_path)
    assert "tool:pytest" in nodes
    assert "tool:MODE=test" not in nodes


def test_dynamic_configuration_script_target_fails_closed(tmp_path: Path) -> None:
    source = tmp_path / "docker-compose.yml"
    text = 'services:\n  job:\n    command: python "$SCRIPT"\n'
    nodes = _command_nodes_from_text(text, source, tmp_path)
    assert any(node.startswith(f"{UNRESOLVED_PREFIX}python-script-target:") for node in nodes)
    source.write_text(text, encoding="utf-8")
    with pytest.raises(AssertionError, match="unresolved execution target"):
        _configured_entrypoints({"docker-compose.yml"}, tmp_path)


def test_pyproject_entrypoint_uses_exact_importable_module(tmp_path: Path) -> None:
    _write_example_module(tmp_path)
    project = tmp_path / "pyproject.toml"
    project.write_text(
        '[project]\nname = "fixture"\nversion = "0.0.0"\n'
        '[project.scripts]\nfixture = "w2.example:app"\n',
        encoding="utf-8",
    )
    entrypoints = _configured_entrypoints(
        {"pyproject.toml", "src/w2/example.py"},
        tmp_path,
    )
    assert "src/w2/example.py" in entrypoints


def test_dead_scripts_are_absent_and_non_dead_scripts_exist() -> None:
    rows = _matrix_rows()
    for path, classification, decision in rows:
        if classification == "DEAD":
            assert decision == "DELETE"
            assert not (ROOT / path).exists()
        else:
            assert decision == "KEEP"
            assert (ROOT / path).is_file()


def test_deleted_object_references_are_absent() -> None:
    deleted = _deletion_closure()
    assert len(deleted) == 9
    tracked = _tracked_files()
    _assert_deleted_objects_absent(deleted, tracked=tracked, root=ROOT)
    for relative in tracked:
        if relative == MASTER_CHECKLIST.relative_to(ROOT).as_posix():
            continue
        path = ROOT / relative
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        references = _referenced_deleted_paths(path, text, deleted)
        assert not references, f"{relative}: {sorted(references)}"


def test_deleted_manifest_cannot_be_recreated(tmp_path: Path) -> None:
    manifest = tmp_path / DELETED_MANIFEST
    manifest.parent.mkdir(parents=True)
    manifest.write_text("{}\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="exists again"):
        _assert_deleted_objects_absent(
            {DELETED_MANIFEST},
            tracked=set(),
            root=tmp_path,
        )


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
    assert _referenced_deleted_paths(source, text, {dead_path}, tmp_path) == {dead_path}


def test_deleted_manifest_reference_is_detected(tmp_path: Path) -> None:
    source = tmp_path / "runbook.md"
    manifest = "docs/ui/dashboard-v2/" + "DASHBOARD_V2_VISUAL_BASELINE_" + "MANIFEST.json"
    text = f"Read `{manifest}` before release.\n"
    assert _referenced_deleted_paths(source, text, {DELETED_MANIFEST}, tmp_path) == {
        DELETED_MANIFEST
    }


def test_no_scripts_archive_directory_is_tracked() -> None:
    for relative in _tracked_files():
        parts = Path(relative).parts
        assert not any(
            parts[index : index + 2] == ("scripts", "archive") for index in range(len(parts) - 1)
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
            assert not node.startswith(
                (
                    f"{UNRESOLVED_PREFIX}python-m:",
                    f"{UNRESOLVED_PREFIX}uvicorn:",
                    f"{UNRESOLVED_PREFIX}celery:",
                )
            ), f"{source.relative_to(ROOT)} -> {node}"


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
    _assert_graph_topology(
        graph,
        expected_scripts=EXPECTED_CHECK_W2_ALL_SCRIPTS,
        expected_tools=EXPECTED_CHECK_W2_ALL_TOOLS,
    )


def test_graph_rejects_additional_transitive_script(tmp_path: Path) -> None:
    graph = _write_check_graph_fixture(
        tmp_path,
        "import subprocess\nsubprocess.run(['python', 'scripts/manual_ops.py'])\n",
        extra_files={"scripts/manual_ops.py": "print('manual')\n"},
    )
    with pytest.raises(AssertionError, match="unexpected_scripts"):
        _assert_graph_topology(
            graph,
            expected_scripts={
                "script:scripts/check_w2_all.py",
                "script:scripts/child.py",
            },
            expected_tools=EXPECTED_CHECK_W2_ALL_TOOLS,
        )


@pytest.mark.parametrize(
    "command",
    [
        "make test",
        "npm test",
        "MODE=test pytest -q",
        "unknown-tool --check",
    ],
)
def test_graph_rejects_unapproved_tools(command: str, tmp_path: Path) -> None:
    graph = _write_check_graph_fixture(
        tmp_path,
        f"import os\nos.system({command!r})\n",
    )
    with pytest.raises(AssertionError, match="unexpected_tools"):
        _assert_graph_topology(
            graph,
            expected_scripts={
                "script:scripts/check_w2_all.py",
                "script:scripts/child.py",
            },
            expected_tools=EXPECTED_CHECK_W2_ALL_TOOLS,
        )


def test_graph_rejects_unresolved_shell_control_syntax(tmp_path: Path) -> None:
    graph = _write_check_graph_fixture(
        tmp_path,
        "import subprocess\nsubprocess.run(['bash', 'scripts/control.sh'])\n",
        extra_files={
            "scripts/control.sh": "#!/bin/sh\nif true; then pytest -q; fi\n",
        },
    )
    with pytest.raises(AssertionError, match="UNRESOLVED_EXECUTION"):
        _assert_graph_topology(
            graph,
            expected_scripts={
                "script:scripts/check_w2_all.py",
                "script:scripts/child.py",
                "script:scripts/control.sh",
            },
            expected_tools=EXPECTED_CHECK_W2_ALL_TOOLS,
        )


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


@pytest.mark.parametrize(
    ("command", "tool"),
    [
        ("python -m pytest", "pytest"),
        ("python -m mypy", "mypy"),
        ("python -m ruff", "ruff"),
        ("uv run python -m pytest", "pytest"),
        ('python -c "import pytest; pytest.main([])"', "pytest"),
    ],
)
def test_graph_normalizes_heavy_module_forms(
    command: str,
    tool: str,
    tmp_path: Path,
) -> None:
    graph = _write_check_graph_fixture(
        tmp_path,
        f"import subprocess\nsubprocess.run({command!r}, shell=True)\n",
    )
    with pytest.raises(AssertionError, match=tool):
        _assert_graph_excludes_heavy_tools(graph)


@pytest.mark.parametrize(
    ("child_text", "tool"),
    [
        ("import pytest\npytest.console_main()\n", "pytest"),
        ("from mypy.api import run\nrun([])\n", "mypy"),
        ("from ruff.__main__ import main\nmain()\n", "ruff"),
    ],
)
def test_graph_normalizes_heavy_python_apis(
    child_text: str,
    tool: str,
    tmp_path: Path,
) -> None:
    graph = _write_check_graph_fixture(tmp_path, child_text)
    with pytest.raises(AssertionError, match=tool):
        _assert_graph_excludes_heavy_tools(graph)


@pytest.mark.parametrize(
    "child_text",
    [
        "import subprocess\ncmd = ['pytest']\nsubprocess.run(cmd)\n",
        "import subprocess\ncmd = ['pytest']\nsubprocess.run(args=cmd)\n",
        "import os\nname = 'pytest'\nos.system('uv run ' + name)\n",
        "import runpy\nname = 'scripts.indirect'\nrunpy.run_module(name)\n",
    ],
)
def test_graph_fails_closed_for_dynamic_execution(
    child_text: str,
    tmp_path: Path,
) -> None:
    graph = _write_check_graph_fixture(tmp_path, child_text)
    with pytest.raises(AssertionError, match="UNRESOLVED_EXECUTION"):
        _assert_graph_excludes_heavy_tools(graph)


def test_graph_rejects_keyword_subprocess_args(tmp_path: Path) -> None:
    graph = _write_check_graph_fixture(
        tmp_path,
        "import subprocess\nsubprocess.run(args=['pytest', '-q'])\n",
    )
    with pytest.raises(AssertionError, match="UNRESOLVED_EXECUTION"):
        _assert_graph_excludes_heavy_tools(graph)


def test_graph_normalizes_sys_executable_module(tmp_path: Path) -> None:
    graph = _write_check_graph_fixture(
        tmp_path,
        "import subprocess\nimport sys\nsubprocess.run([sys.executable, '-m', 'pytest'])\n",
    )
    with pytest.raises(AssertionError, match="pytest"):
        _assert_graph_excludes_heavy_tools(graph)


@pytest.mark.parametrize(
    "parent_command",
    [
        "scripts/child.sh",
        "./scripts/child.sh",
        "bash -O extglob scripts/child.sh",
    ],
)
def test_graph_follows_direct_shell_children(
    parent_command: str,
    tmp_path: Path,
) -> None:
    graph = _write_check_graph_fixture(
        tmp_path,
        f"import subprocess\nsubprocess.run({parent_command!r}, shell=True)\n",
        extra_files={"scripts/child.sh": "#!/bin/sh\npytest -q\n"},
    )
    with pytest.raises(AssertionError, match="pytest"):
        _assert_graph_excludes_heavy_tools(graph)


@pytest.mark.parametrize(
    "shell_text",
    [
        "source scripts/grandchild.sh\n",
        ". scripts/grandchild.sh\n",
        "exec scripts/grandchild.sh\n",
    ],
)
def test_graph_follows_source_and_exec(
    shell_text: str,
    tmp_path: Path,
) -> None:
    graph = _write_check_graph_fixture(
        tmp_path,
        "import subprocess\nsubprocess.run(['bash', 'scripts/child.sh'])\n",
        extra_files={
            "scripts/child.sh": shell_text,
            "scripts/grandchild.sh": "#!/bin/sh\npytest -q\n",
        },
    )
    with pytest.raises(AssertionError, match="pytest"):
        _assert_graph_excludes_heavy_tools(graph)


@pytest.mark.parametrize(
    "wrapped",
    [
        "env MODE=test pytest -q",
        "sudo -u nobody pytest -q",
        "timeout -k 1 5 pytest -q",
        "uv --project . run --python 3.12 python -m pytest",
    ],
)
def test_graph_unwraps_execution_wrappers(wrapped: str, tmp_path: Path) -> None:
    graph = _write_check_graph_fixture(
        tmp_path,
        f"import subprocess\nsubprocess.run({wrapped!r}, shell=True)\n",
    )
    with pytest.raises(AssertionError, match="pytest"):
        _assert_graph_excludes_heavy_tools(graph)


def test_github_ci_owns_ruff_mypy_and_full_pytest() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "run: uv run --python 3.12 ruff check ." in workflow
    assert "run: uv run --python 3.12 mypy src apps" in workflow
    assert "run: uv run --python 3.12 pytest -q" in workflow
