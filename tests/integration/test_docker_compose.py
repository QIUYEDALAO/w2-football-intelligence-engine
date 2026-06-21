from __future__ import annotations

import yaml


def test_docker_compose_has_required_services_and_healthchecks() -> None:
    with open("docker-compose.yml", encoding="utf-8") as handle:
        compose = yaml.safe_load(handle)
    services = compose["services"]
    expected = {"api", "worker", "scheduler", "web", "postgres", "redis", "minio"}
    assert expected <= set(services)
    for service_name in expected:
        assert "healthcheck" in services[service_name]
    assert {"postgres-data", "redis-data", "minio-data"} <= set(compose["volumes"])

