from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "infra/compose/compose.staging.yml"
NGINX = ROOT / "apps/web/nginx.conf"
DEPLOY = ROOT / "scripts/deploy_stage7h_staging.sh"
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
