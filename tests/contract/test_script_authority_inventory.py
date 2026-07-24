from __future__ import annotations

import ast
import re
import subprocess
import tomllib
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MASTER_CHECKLIST = (
    ROOT
    / "docs"
    / "operations"
    / "architecture_convergence"
    / "W2_ARCHITECTURE_CONVERGENCE_MASTER_CHECKLIST.md"
)
THIS_TEST = Path(__file__).relative_to(ROOT).as_posix()
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
EXPECTED_CLASSIFICATION_COUNTS = {
    "RUNTIME_ENTRYPOINT": 8,
    "CI_DIRECT": 7,
    "CI_TRANSITIVE": 29,
    "DEPLOYMENT": 11,
    "MANUAL_OPS": 69,
    "MIGRATION_ONLY": 2,
    "ONE_TIME_RECOVERY": 11,
    "DEAD": 8,
}
SCRIPT_SUFFIXES = {".py", ".sh", ".mjs", ".js", ".ts"}
MATRIX_START = "<!-- SCRIPT_AUTHORITY_MATRIX_START -->"
MATRIX_END = "<!-- SCRIPT_AUTHORITY_MATRIX_END -->"
CONFIG_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])"
    r"((?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\.(?:py|sh|mjs|js|ts))"
    r"(?![A-Za-z0-9_.-])"
)
DELETED_MANIFEST = "docs/ui/dashboard-v2/DASHBOARD_V2_VISUAL_BASELINE_MANIFEST.json"
APPROVED_CHECK_W2_ALL_COMMANDS = [
    ["uv", "run", "python", "scripts/check_w2_stage1_contracts.py"],
    ["uv", "run", "python", "scripts/check_w2_stage3_data_model.py"],
    ["uv", "run", "python", "scripts/check_w2_stage4_ingestion.py"],
    ["uv", "run", "python", "scripts/check_w2_stage4b_live_smoke.py"],
    ["uv", "run", "python", "scripts/check_w2_stage5_asof.py"],
    ["uv", "run", "python", "scripts/check_w2_stage5b.py"],
    ["uv", "run", "python", "scripts/check_w2_stage6_market.py"],
    ["uv", "run", "python", "scripts/check_w2_stage7_models.py"],
    ["uv", "run", "python", "scripts/check_w2_stage8_replay.py"],
    ["uv", "run", "python", "scripts/check_w2_stage7b.py"],
    ["uv", "run", "python", "scripts/check_w2_stage7c.py"],
    ["uv", "run", "python", "scripts/check_w2_stage7d.py"],
    ["uv", "run", "python", "scripts/check_w2_stage7e.py"],
    ["uv", "run", "python", "scripts/check_w2_stage10a.py"],
    ["uv", "run", "python", "scripts/check_w2_stage11a.py"],
    ["uv", "run", "python", "scripts/check_w2_stage12a.py"],
    ["uv", "run", "python", "scripts/check_w2_stage13a.py"],
    ["uv", "run", "python", "scripts/check_w2_stage14a.py"],
    ["uv", "run", "python", "scripts/check_w2_stage15a.py"],
]


def _tracked_files() -> set[str]:
    output = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode()
    return {path for path in output.split("\0") if path}


def _resolve_module(module: str) -> str | None:
    relative = Path(*module.split(".")).with_suffix(".py")
    for candidate in (relative, Path("src") / relative):
        if (ROOT / candidate).is_file():
            return candidate.as_posix()
    return None


def _configuration_sources(tracked: set[str]) -> list[Path]:
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
            sources.append(ROOT / relative)
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
    scripts = {
        relative
        for relative in tracked
        if "scripts" in Path(relative).parts
        and Path(relative).suffix in SCRIPT_SUFFIXES
        and (ROOT / relative).is_file()
    }
    return scripts | _configured_entrypoints(tracked)


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
        rows.append(
            (
                columns[0].strip("`"),
                columns[1].strip("`"),
                columns[7].strip("`"),
            )
        )
    return rows


def _check_w2_all_commands() -> list[list[str]]:
    tree = ast.parse((ROOT / "scripts/check_w2_all.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "COMMANDS"
            for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError("scripts/check_w2_all.py has no literal COMMANDS list")


def test_inventory_has_145_unique_classified_identities() -> None:
    rows = _matrix_rows()
    paths = [path for path, _classification, _decision in rows]
    classifications = Counter(
        classification for _path, classification, _decision in rows
    )
    dead = {path for path, classification, _decision in rows if classification == "DEAD"}
    retained = {
        path
        for path, classification, decision in rows
        if classification != "DEAD" and decision == "KEEP"
    }

    assert len(rows) == 145
    assert len(paths) == len(set(paths))
    assert set(classifications) == ALLOWED_CLASSIFICATIONS
    assert dict(classifications) == EXPECTED_CLASSIFICATION_COUNTS
    assert len(retained) == 137
    assert len(dead) == 8
    assert set(paths) == retained | dead
    assert retained == _inventory_universe()


def test_retained_scripts_exist_and_dead_scripts_do_not() -> None:
    for path, classification, decision in _matrix_rows():
        if classification == "DEAD":
            assert decision == "DELETE"
            assert not (ROOT / path).exists()
        else:
            assert decision == "KEEP"
            assert (ROOT / path).is_file()


def test_deleted_dashboard_v2_manifest_is_absent() -> None:
    assert DELETED_MANIFEST not in _tracked_files()
    assert not (ROOT / DELETED_MANIFEST).exists()


def test_nine_deleted_paths_have_no_remaining_references() -> None:
    dead_scripts = {
        path
        for path, classification, _decision in _matrix_rows()
        if classification == "DEAD"
    }
    deleted_paths = dead_scripts | {DELETED_MANIFEST}
    excluded = {MASTER_CHECKLIST.relative_to(ROOT).as_posix(), THIS_TEST}

    for relative in _tracked_files() - excluded:
        path = ROOT / relative
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for deleted_path in deleted_paths:
            assert deleted_path not in text, f"{relative} references {deleted_path}"


def test_no_scripts_archive_directory_is_tracked() -> None:
    for relative in _tracked_files():
        parts = Path(relative).parts
        assert not any(
            parts[index : index + 2] == ("scripts", "archive")
            for index in range(len(parts) - 1)
        )


def test_check_w2_all_commands_are_the_approved_19_checkers() -> None:
    assert _check_w2_all_commands() == APPROVED_CHECK_W2_ALL_COMMANDS


def test_check_w2_all_chain_does_not_run_ruff_mypy_or_pytest() -> None:
    script_paths = ["scripts/check_w2_all.py"] + [
        next(token for token in command if token.startswith("scripts/"))
        for command in APPROVED_CHECK_W2_ALL_COMMANDS
    ]
    source = "\n".join((ROOT / path).read_text(encoding="utf-8") for path in script_paths)
    for forbidden in ("ruff", "mypy", "pytest"):
        assert re.search(rf"\b{forbidden}\b", source, re.IGNORECASE) is None


def test_github_ci_owns_ruff_mypy_and_full_pytest() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "run: uv run --python 3.12 ruff check ." in workflow
    assert "run: uv run --python 3.12 mypy src apps" in workflow
    assert "run: uv run --python 3.12 pytest -q" in workflow
