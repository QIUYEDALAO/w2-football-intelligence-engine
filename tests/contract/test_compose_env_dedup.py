from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
FORMAL = ROOT / "infra/compose/compose.staging.yml"
LITE = ROOT / "infra/compose/staging-lite.override.yml"
SERVICES = ("api", "worker", "scheduler")
BASE_SHA = "a607d65b0b71afbc0caa50c44a6e162cf397e4e4"
REMOVED_EVAL_01A_ENV = {
    FORMAL: {
        "api": set(),
        "worker": {
            "W2_FORWARD_OUTCOME_BACKFILL_MAX_FIXTURES",
            "W2_FORWARD_OUTCOME_RUNTIME_ROOT",
        },
        "scheduler": {
            "W2_FORWARD_OUTCOME_BACKFILL_ENABLED",
            "W2_FORWARD_OUTCOME_BACKFILL_INTERVAL_SECONDS",
            "W2_FORWARD_OUTCOME_BACKFILL_MAX_FIXTURES",
            "W2_FORWARD_OUTCOME_BACKFILL_WINDOW",
            "W2_FORWARD_OUTCOME_RUNTIME_ROOT",
        },
    },
    LITE: {
        "api": set(),
        "worker": set(),
        "scheduler": {
            "W2_FORWARD_OUTCOME_BACKFILL_ENABLED",
            "W2_FORWARD_OUTCOME_BACKFILL_INTERVAL_SECONDS",
            "W2_FORWARD_OUTCOME_BACKFILL_WINDOW",
        },
    },
}
EXPECTED_UNIQUE = {
    FORMAL: {
        "api": {
            "W2_FORMAL_RECOMMENDATION_ENABLED",
            "W2_IMAGE_ID",
            "W2_OCI_DIGEST",
            "W2_READINESS_RELEASE_ROOT",
            "W2_REGISTRY_DIGEST",
        },
        "worker": {
            "W2_FORMAL_RECOMMENDATION_ENABLED",
        },
        "scheduler": {
            "W2_FORWARD_OUTCOME_LEDGER_ENABLED",
            "W2_FORWARD_OUTCOME_LEDGER_INTERVAL_SECONDS",
            "W2_FORWARD_OUTCOME_LEDGER_WINDOW",
            "W2_FUTURE_FIXTURE_REFRESH_ENABLED",
        },
    },
    LITE: {
        "api": {"W2_READINESS_RELEASE_ROOT"},
        "worker": set(),
        "scheduler": {
            "W2_FORWARD_OUTCOME_LEDGER_ENABLED",
            "W2_FORWARD_OUTCOME_LEDGER_INTERVAL_SECONDS",
            "W2_FORWARD_OUTCOME_LEDGER_WINDOW",
            "W2_FUTURE_FIXTURE_REFRESH_ENABLED",
        },
    },
}


def load_compose(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize(("path", "common_count"), [(FORMAL, 36), (LITE, 32)])
def test_runtime_services_share_one_common_environment_anchor(
    path: Path,
    common_count: int,
) -> None:
    text = path.read_text(encoding="utf-8")
    compose = load_compose(path)

    assert text.count("x-common-env: &common-env") == 1
    assert text.count("<<: *common-env") == 3
    assert len(compose["x-common-env"]) == common_count


@pytest.mark.parametrize("path", [FORMAL, LITE])
def test_service_only_environment_variables_do_not_leak(path: Path) -> None:
    compose = load_compose(path)
    common = set(compose["x-common-env"])

    for service in SERVICES:
        environment = set(compose["services"][service]["environment"])
        assert environment - common == EXPECTED_UNIQUE[path][service]


@pytest.mark.parametrize("path", [FORMAL, LITE])
def test_safety_switches_keep_their_values_and_ownership(path: Path) -> None:
    compose = load_compose(path)
    environments = {
        service: compose["services"][service]["environment"] for service in SERVICES
    }
    fixed_common = {
        "W2_PROVIDER_CALLS_DISABLED": "true",
        "W2_PROVIDER_SCHEDULER_ENABLED": "false",
        "W2_RECOMMENDATION_ENABLED": "false",
        "W2_CANDIDATE_ENABLED": "true",
        "W2_PRODUCTION_RELEASE": "false",
        "W2_EXTERNAL_ALERTING": "false",
        "W2_XG_BACKFILL_ENABLED": "false",
        "W2_FORWARD_HOLDOUT_AUTORUN": "true",
        "W2_FORWARD_HOLDOUT_NETWORK": "true",
    }
    for environment in environments.values():
        assert {key: environment[key] for key in fixed_common} == fixed_common

    assert environments["scheduler"]["W2_FUTURE_FIXTURE_REFRESH_ENABLED"] == "false"
    assert "W2_MARKET_TIMELINE_REFRESH_ENABLED" not in environments["scheduler"]
    assert "W2_FUTURE_FIXTURE_REFRESH_ENABLED" not in environments["api"]
    assert "W2_FUTURE_FIXTURE_REFRESH_ENABLED" not in environments["worker"]
    assert all(
        "W2_MARKET_TIMELINE_REFRESH_ENABLED" not in environment
        for environment in environments.values()
    )
    if path == FORMAL:
        expected_formal = "${W2_FORMAL_RECOMMENDATION_ENABLED:-false}"
        assert environments["api"]["W2_FORMAL_RECOMMENDATION_ENABLED"] == expected_formal
        assert environments["worker"]["W2_FORMAL_RECOMMENDATION_ENABLED"] == expected_formal
    else:
        assert "W2_FORMAL_RECOMMENDATION_ENABLED" not in environments["api"]
        assert "W2_FORMAL_RECOMMENDATION_ENABLED" not in environments["worker"]
    assert "W2_FORMAL_RECOMMENDATION_ENABLED" not in environments["scheduler"]


@pytest.mark.skipif(shutil.which("docker") is None, reason="Docker Compose unavailable")
@pytest.mark.parametrize("path", [FORMAL, LITE])
def test_compose_expansion_matches_authorized_runtime_delta(
    path: Path,
    tmp_path: Path,
) -> None:
    environment = os.environ.copy()
    compose_text = path.read_text(encoding="utf-8")
    for name in re.findall(r"\$\{([A-Z0-9_]+)", compose_text):
        environment.pop(name, None)
    environment.update(
        {
            "POSTGRES_PASSWORD": "baseline-postgres",
            "W2_PYTHON_IMAGE": "ghcr.io/example/python@sha256:" + "1" * 64,
            "W2_WEB_IMAGE": "ghcr.io/example/web@sha256:" + "2" * 64,
            "W2_API_FOOTBALL_API_KEY": "baseline-api-key",
            "W2_GIT_SHA": "3" * 40,
            "W2_BUILD_TIME": "2026-07-28T00:00:00Z",
            "W2_RELEASE_ID": "3" * 40,
            "W2_API_IMAGE_ID": "sha256:" + "4" * 64,
            "W2_API_OCI_DIGEST": "sha256:" + "5" * 64,
            "W2_API_REGISTRY_DIGEST": "sha256:" + "6" * 64,
        }
    )
    baseline = tmp_path / path.name
    baseline.write_text(
        subprocess.run(
            ["git", "show", f"{BASE_SHA}:{path.relative_to(ROOT)}"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout,
        encoding="utf-8",
    )
    current_command = ["docker", "compose"]
    baseline_command = ["docker", "compose"]
    if path == LITE:
        current_command += [
            "-f",
            str(ROOT / "docker-compose.yml"),
            "-f",
            str(path),
            "--profile",
            "staging",
        ]
        baseline_command += [
            "-f",
            str(ROOT / "docker-compose.yml"),
            "-f",
            str(baseline),
            "--profile",
            "staging",
        ]
    else:
        current_command += ["-f", str(path)]
        baseline_command += ["-f", str(baseline)]
    current = subprocess.run(
        [*current_command, "config", "--format", "json"],
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    before = subprocess.run(
        [*baseline_command, "config", "--format", "json"],
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    current_services = json.loads(current.stdout)["services"]
    baseline_services = json.loads(before.stdout)["services"]

    for service in SERVICES:
        expected = dict(baseline_services[service]["environment"])
        for name in REMOVED_EVAL_01A_ENV[path][service]:
            expected.pop(name)
        expected.update(
            {
                "W2_FIXTURE_DISCOVERY_ENABLED": "false",
                "W2_FIXTURE_DISCOVERY_INTERVAL_SECONDS": "300",
                "W2_CANDIDATE_ENABLED": "true",
            }
        )
        assert current_services[service]["environment"] == expected
