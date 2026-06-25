from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

MODULES = [
    "w2.strategy.shadow_cycle_cli",
    "w2.gates.gate5_preflight_cli",
    "w2.shadow.comparison_import_cli",
    "w2.observability.stage7i_observer_cli",
]

CONSOLE_SCRIPTS = [
    "w2-shadow-cycle",
    "w2-gate5-preflight",
    "w2-shadow-comparison-import",
    "w2-stage7i-observer",
]


def run_command(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    combined = result.stdout + result.stderr
    assert result.returncode == 0, combined
    blocked_markers = ("API" + "_FOOTBALL", "AUTHOR" + "IZATION", "PASS" + "WORD")
    assert not any(token in combined.upper() for token in blocked_markers)
    assert '"candidate": true' not in combined.lower()
    assert '"formal_recommendation": true' not in combined.lower()
    return combined


def test_runtime_modules_import_and_help_from_temp_directory(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "src")
    for module in MODULES:
        run_command([sys.executable, "-m", module, "--help"], cwd=tmp_path, env=env)


def test_console_scripts_help() -> None:
    root = Path(__file__).resolve().parents[2]
    for script in CONSOLE_SCRIPTS:
        run_command(["uv", "run", script, "--help"], cwd=root)


def test_shadow_cli_retrospective_is_shadow_only(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "src")
    output = run_command(
        [
            sys.executable,
            "-m",
            "w2.strategy.shadow_cycle_cli",
            "--execution-kind",
            "RETROSPECTIVE",
            "--dry-run",
            "--json",
        ],
        cwd=tmp_path,
        env=env,
    )
    payload = json.loads(output)
    assert payload["shadow_only"] is True
    assert payload["forward_lock_count"] == 0
    assert payload["allowed_shadow_actions"] == ["SHADOW_WATCH", "SHADOW_SKIP"]


def test_gate5_cli_cannot_close(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "src")
    output = run_command(
        [sys.executable, "-m", "w2.gates.gate5_preflight_cli", "--dry-run", "--json"],
        cwd=tmp_path,
        env=env,
    )
    payload = json.loads(output)
    assert payload["closed"] is False
    assert payload["gate5_result"] == "PROVISIONAL_BLOCKED_GATE4"


def test_stage7i_observer_help_does_not_require_repo_paths(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "src")
    run_command(
        [sys.executable, "-m", "w2.observability.stage7i_observer_cli", "--help"],
        cwd=tmp_path,
        env=env,
    )
