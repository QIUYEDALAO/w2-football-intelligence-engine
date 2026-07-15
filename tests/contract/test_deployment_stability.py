from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "infra/compose/compose.staging.yml"
LITE_COMPOSE = ROOT / "infra/compose/staging-lite.override.yml"
LOCAL_COMPOSE = ROOT / "docker-compose.yml"
NGINX = ROOT / "apps/web/nginx.conf"
DEPLOY = ROOT / "scripts/deploy_stage7h_staging.sh"
SYSTEMD_UNIT = ROOT / "infra/systemd/w2-staging.service"
RUNTIME_DOCKERFILES = (
    ROOT / "Dockerfile.api",
    ROOT / "Dockerfile.migrations",
    ROOT / "Dockerfile.scheduler",
    ROOT / "Dockerfile.worker",
)


def test_runtime_commands_use_built_virtualenv_without_uv_run() -> None:
    for path in RUNTIME_DOCKERFILES:
        text = path.read_text(encoding="utf-8")
        runtime_lines = [
            line for line in text.splitlines() if line.startswith(("CMD ", "HEALTHCHECK "))
        ]
        assert runtime_lines
        assert all("uv run" not in line and '"uv", "run"' not in line for line in runtime_lines)
        assert any("/app/.venv/bin/" in line for line in runtime_lines)

    compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    for service_name in ("migration", "api", "worker", "scheduler"):
        service = compose["services"][service_name]
        assert service["command"][0].startswith("/app/.venv/bin/")
        healthcheck = service.get("healthcheck")
        if healthcheck:
            assert "uv" not in healthcheck["test"]


def test_api_container_healthchecks_use_readiness_not_liveness() -> None:
    for path in (COMPOSE, LITE_COMPOSE, LOCAL_COMPOSE):
        compose = yaml.safe_load(path.read_text(encoding="utf-8"))
        healthcheck = " ".join(
            str(item) for item in compose["services"]["api"]["healthcheck"]["test"]
        )
        assert "/ready" in healthcheck
        assert "/health" not in healthcheck
    dockerfile = (ROOT / "Dockerfile.api").read_text(encoding="utf-8")
    assert "HEALTHCHECK" in dockerfile
    assert "/ready" in dockerfile


def test_web_uses_short_ttl_docker_dns_and_waits_for_healthy_api() -> None:
    nginx = NGINX.read_text(encoding="utf-8")
    assert "resolver 127.0.0.11 valid=10s ipv6=off;" in nginx
    assert "set $api_upstream http://api:8000;" in nginx
    assert "proxy_pass $api_upstream" in nginx

    compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    assert compose["services"]["web"]["depends_on"]["api"]["condition"] == "service_healthy"


def test_release_switches_api_before_web_without_restarting_worker_or_scheduler() -> None:
    deploy = DEPLOY.read_text(encoding="utf-8")
    api_switch = deploy.index("compose up -d --no-deps api")
    api_pass = deploy.index("api_stability_probe=PASS")
    web_switch = deploy.index("compose up -d --no-deps web")

    assert api_switch < api_pass < web_switch
    assert "api_consecutive" in deploy
    assert "release_consecutive" in deploy
    assert "worker_scheduler_restart=false" in deploy
    assert "sudo systemctl restart w2-staging.service" not in deploy
    assert "-p w2-staging" in deploy
    assert "COMPOSE_PROJECT_NAME=w2\n" not in deploy
    assert "check_staging_disk_capacity.py" in deploy
    assert "build migration api web" in deploy
    assert "W2_STAGING_BACKGROUND_DRIFT_REVIEWED" in deploy
    assert "check_dayview_business_readiness.py" in deploy
    assert "check_r4_artifact_release.py" in deploy
    assert "W2_STAGING_APPROVED_ARTIFACT_VERSION" in deploy


def test_release_failure_automatically_restores_previous_api_and_web() -> None:
    deploy = DEPLOY.read_text(encoding="utf-8")

    assert "previous-release-path" in deploy
    assert "rollback_release()" in deploy
    assert "trap rollback_release ERR" in deploy
    assert "up -d --no-deps api web" in deploy
    assert "automatic_rollback_probe=PASS" in deploy
    assert "previous-api-image" in deploy
    assert "previous-web-image" in deploy
    assert "w2-rollback-images.yml" in deploy
    assert "docker commit w2-staging-api-1" in deploy
    assert "docker commit w2-staging-web-1" in deploy
    assert "docker image tag w2-staging-api:latest" in deploy
    assert "docker image tag w2-staging-web:latest" in deploy
    assert "w2-rollback-api:" in deploy
    assert "w2-rollback-web:" in deploy
    assert "--retry-all-errors" in deploy
    assert "api_stability_probe=FAIL' >&2\n  rollback_release" in deploy
    assert "stability_probe=FAIL' >&2\n  rollback_release" in deploy
    assert "if ! compose run --rm --no-deps api" in deploy
    for path in ("health", "ready", "v1/version", "meta.json"):
        assert path in deploy


def test_systemd_and_deploy_target_one_staging_compose_project() -> None:
    unit = SYSTEMD_UNIT.read_text(encoding="utf-8")
    deploy = DEPLOY.read_text(encoding="utf-8")

    assert "Environment=COMPOSE_PROJECT_NAME=w2-staging" in unit
    assert "-p w2-staging" in deploy
    assert "COMPOSE_PROJECT_NAME=w2\n" not in unit
