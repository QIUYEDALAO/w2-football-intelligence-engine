from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_dockerfiles_install_non_editable_package_and_do_not_copy_scripts() -> None:
    root = Path(__file__).resolve().parents[2]
    dockerfiles = (
        "Dockerfile.api",
        "Dockerfile.worker",
        "Dockerfile.scheduler",
        "Dockerfile.migrations",
    )
    for name in dockerfiles:
        text = (root / name).read_text(encoding="utf-8")
        assert "uv sync --no-dev --frozen --no-editable" in text
        assert "COPY src ./src" in text
        assert "COPY config ./config" in text
        assert "COPY scripts" not in text
        assert "COPY reports" not in text
        assert "w2.runtime.contract.version" in text


def test_dockerignore_excludes_runtime_reports_and_private_inputs() -> None:
    text = (Path(__file__).resolve().parents[2] / ".dockerignore").read_text(encoding="utf-8")
    for entry in ("runtime", "reports", ".env", ".env.*", "data/raw", "data/processed"):
        assert entry in text


def test_wheel_install_exposes_entrypoints(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    dist = tmp_path / "dist"
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(dist)],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    wheel = next(dist.glob("*.whl"))
    venv = tmp_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True, timeout=60)
    pip = venv / "bin" / "pip"
    python = venv / "bin" / "python"
    subprocess.run(
        [str(pip), "install", "--no-deps", str(wheel)],
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    for module in (
        "w2.strategy.shadow_cycle_cli",
        "w2.gates.gate5_preflight_cli",
        "w2.shadow.comparison_import_cli",
        "w2.observability.stage7i_observer_cli",
    ):
        result = subprocess.run(
            [str(python), "-m", module, "--help"],
            cwd=tmp_path,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stdout + result.stderr
    for script in (
        "w2-shadow-cycle",
        "w2-gate5-preflight",
        "w2-shadow-comparison-import",
        "w2-stage7i-observer",
    ):
        result = subprocess.run(
            [str(venv / "bin" / script), "--help"],
            cwd=tmp_path,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stdout + result.stderr
