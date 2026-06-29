from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_dockerfiles_install_non_editable_package_and_package_required_runtime_scripts() -> None:
    root = Path(__file__).resolve().parents[2]
    dockerfiles = {
        "Dockerfile.api": ("w2-gate5-preflight",),
        "Dockerfile.worker": ("w2-shadow-comparison-import",),
        "Dockerfile.scheduler": ("w2-shadow-cycle", "w2-stage7i-observer"),
        "Dockerfile.migrations": ("python", "alembic"),
    }
    for name, expected_bins in dockerfiles.items():
        text = (root / name).read_text(encoding="utf-8")
        assert "ENV VIRTUAL_ENV=/app/.venv" in text
        assert "ENV PATH=/app/.venv/bin:$PATH" in text
        assert "uv sync --no-dev --frozen --no-editable" in text
        assert "COPY src ./src" in text
        assert "COPY config ./config" in text
        if name == "Dockerfile.api":
            assert "COPY scripts/run_w2_market_timeline_refresh.py" in text
            assert "scripts/check_w2_market_timeline.py" in text
            assert "scripts/run_w2_handicap_walkforward.py" in text
            assert "scripts/run_w2_formal_tracking.py" in text
            assert "scripts/check_w2_formal_tracking.py" in text
            assert "test -f /app/scripts/run_w2_market_timeline_refresh.py" in text
            assert "test -f /app/scripts/run_w2_formal_tracking.py" in text
        else:
            assert "COPY scripts" not in text
        assert "COPY reports" not in text
        assert "w2.runtime.contract.version" in text
        for binary in expected_bins:
            assert f"test -x /app/.venv/bin/{binary}" in text


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
    scripts = (
        "w2-shadow-cycle",
        "w2-gate5-preflight",
        "w2-shadow-comparison-import",
        "w2-stage7i-observer",
    )
    for script in scripts:
        result = subprocess.run(
            [str(venv / "bin" / script), "--help"],
            cwd=tmp_path,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stdout + result.stderr
    env_path = f"{venv / 'bin'}:/bin:/usr/bin"
    for script in scripts:
        result = subprocess.run(
            ["sh", "-lc", f"command -v {script} >/dev/null && {script} --help >/dev/null"],
            cwd=tmp_path,
            env={"PATH": env_path},
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stdout + result.stderr
