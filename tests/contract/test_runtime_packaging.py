from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

REQUIRED_PRODUCTION_SCRIPT_ALLOWLIST = (
    "run_w2_free_mode_model_validation_canary.py",
    "repair_w2_xg_retention_lineage.py",
)


def test_unified_python_image_packages_every_runtime_role() -> None:
    root = Path(__file__).resolve().parents[2]
    text = (root / "Dockerfile.python").read_text(encoding="utf-8")
    assert "ENV VIRTUAL_ENV=/app/.venv" in text
    assert "ENV PATH=/app/.venv/bin:$PATH" in text
    assert "uv sync --no-dev --frozen --no-editable" in text
    assert "COPY apps ./apps" in text
    assert "COPY src ./src" in text
    assert "COPY config ./config" in text
    assert "COPY migrations ./migrations" in text
    assert "COPY scripts ./scripts" not in text
    assert "Runtime script allowlist: model-validation canary and guarded xG lineage repair" in text
    for script in REQUIRED_PRODUCTION_SCRIPT_ALLOWLIST:
        assert f"scripts/{script}" in text
    for forbidden in (
        "audit_football_data_co_uk.py",
        "audit_pr370_totals_quarter_ev.py",
        "build_canonical_historical_ah_facts.py",
        "import_stage5b_historical_data.py",
        "run_w2_r2_offline_evaluation.py",
    ):
        assert f"scripts/{forbidden}" not in text
    assert "COPY reports" not in text
    assert "w2.runtime.contract.version" in text
    for binary in (
        "alembic",
        "w2-gate5-preflight",
        "w2-shadow-comparison-import",
        "w2-stage7i-observer",
        "w2-finished-match-scoring",
    ):
        assert f"test -x /app/.venv/bin/{binary}" in text
    for old in (
        "Dockerfile.api",
        "Dockerfile.worker",
        "Dockerfile.scheduler",
        "Dockerfile.migrations",
    ):
        assert not (root / old).exists()


def test_runtime_entrypoints_do_not_resync_the_environment() -> None:
    root = Path(__file__).resolve().parents[2]
    text = (root / "Dockerfile.python").read_text(encoding="utf-8")
    assert 'CMD ["uvicorn"' in text
    assert 'CMD ["uv", "run"' not in text
    assert "HEALTHCHECK CMD uv run" not in text

    compose = yaml.safe_load(
        (root / "infra/compose/compose.staging.yml").read_text(encoding="utf-8")
    )
    services = compose["services"]
    assert services["migration"]["command"][0] == "alembic"
    assert services["api"]["command"][0] == "uvicorn"
    assert services["worker"]["command"][0] == "celery"
    assert services["scheduler"]["command"][0] == "python"
    assert services["worker"]["healthcheck"]["test"][1] == "python"
    assert services["scheduler"]["healthcheck"]["test"][1] == "python"
    for service in ("api", "worker", "scheduler"):
        environment = services[service]["environment"]
        assert environment["W2_APP_ROOT"] == "/app"
        assert environment["W2_RUNTIME_ROOT"] == "/app/runtime"


def test_release_identity_does_not_invalidate_python_dependency_layers() -> None:
    text = (Path(__file__).resolve().parents[2] / "Dockerfile.python").read_text(encoding="utf-8")
    assert text.index("ARG W2_GIT_SHA=UNKNOWN") > text.rindex("RUN uv sync")
    assert text.index("ENV W2_GIT_SHA=${W2_GIT_SHA}") > text.rindex("RUN uv sync")
    assert "chown -R w2:w2 /app/.venv" not in text


def test_local_image_relay_preserves_immutable_digest() -> None:
    text = (
        Path(__file__).resolve().parents[2] / "scripts/relay_immutable_images_via_local.sh"
    ).read_text(encoding="utf-8")
    assert "@sha256:[0-9a-f]{64}" in text
    assert 'skopeo copy --all "docker://$image_ref"' in text
    assert "ctr -n moby images import --all-platforms --digests" in text
    assert 'docker image inspect "$image_ref"' in text
    assert "docker pull" not in text


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
    policy_path = root / "config/policies/lineup_market_policy.v1.json"
    policy_result = subprocess.run(
        [
            str(python),
            "-c",
            (
                "from w2.lineups.intelligence import lineup_market_policy; "
                "assert lineup_market_policy()['schema_version'] "
                "== 'w2.lineup_market_policy.v1'"
            ),
        ],
        cwd=tmp_path,
        env={"W2_LINEUP_POLICY_PATH": str(policy_path)},
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert policy_result.returncode == 0, policy_result.stdout + policy_result.stderr
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
