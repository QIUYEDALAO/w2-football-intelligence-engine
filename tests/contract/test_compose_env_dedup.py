from __future__ import annotations

import hashlib
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
EXPECTED_FINGERPRINTS = {
    FORMAL: {
        "api": "e5be837ee00dffe47dcf35deaaabd288635d911c6a2678323b0fb895a6ff74c3",
        "worker": "630a34300dda08d26bb8699375f16cc2390dde51e65d7cee387f64e6f9edea3c",
        "scheduler": "ac7709079e5bef261000fba17d6d6c611c90f9873782197511549419dfd0847c",
    },
    LITE: {
        "api": "c87841c26c51cab17c1f679ca13372c143d03cfb8e856dc8cf274231367c626c",
        "worker": "69a0b57d6aa52f0514ad6a418c894a684570b38e5fcc7a010971086f8d7a2d54",
        "scheduler": "34f86427ef3535331d403a107b757212e529a8048f52fe027f2506e675773d5b",
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
            "W2_FORWARD_OUTCOME_BACKFILL_MAX_FIXTURES",
            "W2_FORWARD_OUTCOME_RUNTIME_ROOT",
        },
        "scheduler": {
            "W2_FORWARD_OUTCOME_BACKFILL_ENABLED",
            "W2_FORWARD_OUTCOME_BACKFILL_INTERVAL_SECONDS",
            "W2_FORWARD_OUTCOME_BACKFILL_MAX_FIXTURES",
            "W2_FORWARD_OUTCOME_BACKFILL_WINDOW",
            "W2_FORWARD_OUTCOME_LEDGER_AFTER_MARKET_TIMELINE",
            "W2_FORWARD_OUTCOME_LEDGER_ENABLED",
            "W2_FORWARD_OUTCOME_LEDGER_INTERVAL_SECONDS",
            "W2_FORWARD_OUTCOME_LEDGER_WINDOW",
            "W2_FORWARD_OUTCOME_RUNTIME_ROOT",
            "W2_FUTURE_FIXTURE_REFRESH_ENABLED",
            "W2_MARKET_TIMELINE_MAX_FIXTURES",
            "W2_MARKET_TIMELINE_REFRESH_ENABLED",
            "W2_MARKET_TIMELINE_REFRESH_INTERVAL_SECONDS",
            "W2_MARKET_TIMELINE_WINDOW",
        },
    },
    LITE: {
        "api": {"W2_READINESS_RELEASE_ROOT"},
        "worker": set(),
        "scheduler": {
            "W2_FORWARD_OUTCOME_BACKFILL_ENABLED",
            "W2_FORWARD_OUTCOME_BACKFILL_INTERVAL_SECONDS",
            "W2_FORWARD_OUTCOME_BACKFILL_WINDOW",
            "W2_FORWARD_OUTCOME_LEDGER_AFTER_MARKET_TIMELINE",
            "W2_FORWARD_OUTCOME_LEDGER_ENABLED",
            "W2_FORWARD_OUTCOME_LEDGER_INTERVAL_SECONDS",
            "W2_FORWARD_OUTCOME_LEDGER_WINDOW",
            "W2_FUTURE_FIXTURE_REFRESH_ENABLED",
            "W2_MARKET_TIMELINE_MAX_FIXTURES",
            "W2_MARKET_TIMELINE_REFRESH_ENABLED",
            "W2_MARKET_TIMELINE_REFRESH_INTERVAL_SECONDS",
            "W2_MARKET_TIMELINE_WINDOW",
        },
    },
}


def load_compose(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize(("path", "common_count"), [(FORMAL, 34), (LITE, 30)])
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
        "W2_CANDIDATE_ENABLED": "false",
        "W2_PRODUCTION_RELEASE": "false",
        "W2_EXTERNAL_ALERTING": "false",
        "W2_XG_BACKFILL_ENABLED": "false",
        "W2_FORWARD_HOLDOUT_AUTORUN": "true",
        "W2_FORWARD_HOLDOUT_NETWORK": "true",
    }
    for environment in environments.values():
        assert {key: environment[key] for key in fixed_common} == fixed_common

    assert environments["scheduler"]["W2_FUTURE_FIXTURE_REFRESH_ENABLED"] == "false"
    assert environments["scheduler"]["W2_MARKET_TIMELINE_REFRESH_ENABLED"] == "true"
    assert "W2_FUTURE_FIXTURE_REFRESH_ENABLED" not in environments["api"]
    assert "W2_FUTURE_FIXTURE_REFRESH_ENABLED" not in environments["worker"]
    assert "W2_MARKET_TIMELINE_REFRESH_ENABLED" not in environments["api"]
    assert "W2_MARKET_TIMELINE_REFRESH_ENABLED" not in environments["worker"]
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
def test_compose_expansion_matches_pre_dedup_baseline(path: Path) -> None:
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
    command = ["docker", "compose"]
    if path == LITE:
        command += [
            "-f",
            str(ROOT / "docker-compose.yml"),
            "-f",
            str(path),
            "--profile",
            "staging",
        ]
    else:
        command += ["-f", str(path)]
    result = subprocess.run(
        [*command, "config", "--format", "json"],
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    services = json.loads(result.stdout)["services"]

    for service in SERVICES:
        encoded = json.dumps(
            services[service]["environment"],
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        assert hashlib.sha256(encoded).hexdigest() == EXPECTED_FINGERPRINTS[path][service]
