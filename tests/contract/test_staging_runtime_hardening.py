from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "infra/compose/compose.staging.yml"
DEPLOY = ROOT / "scripts/deploy_stage7h_staging.sh"
DIAGNOSE = ROOT / "scripts/diagnose_staging_runtime.sh"
RECOVER = ROOT / "scripts/recover_staging_runtime.sh"
WATCH = ROOT / "scripts/watch_staging_runtime.sh"
WATCHDOG_SERVICE = ROOT / "infra/systemd/w2-staging-watchdog.service"
WATCHDOG_TIMER = ROOT / "infra/systemd/w2-staging-watchdog.timer"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_staging_compose_limits_container_logs() -> None:
    compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    for service_name, service in compose["services"].items():
        logging = service.get("logging")
        assert logging, f"{service_name} missing logging policy"
        assert logging["driver"] == "local"
        options = logging.get("options", {})
        assert options.get("max-size") == "5m"
        max_file = int(options.get("max-file", "0"))
        assert 1 <= max_file <= 3


def test_staging_compose_has_memory_guards_for_lightweight_host() -> None:
    compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    expected_limits = {
        "postgres": "1g",
        "redis": "256m",
        "migration": "1g",
        "api": "1g",
        "worker": "2g",
        "scheduler": "768m",
        "web": "256m",
    }
    for service_name, expected in expected_limits.items():
        service = compose["services"][service_name]
        assert service.get("mem_limit") == expected
    worker_command = compose["services"]["worker"]["command"]
    assert "--max-tasks-per-child=10" in worker_command
    assert "--max-memory-per-child=1200000" in worker_command


def test_staging_hardening_scripts_do_not_print_env_or_delete_volumes() -> None:
    for path in (DEPLOY, DIAGNOSE, RECOVER, WATCH):
        text = read(path)
        assert "cat /opt/w2/shared/.env" not in text
        assert "\ndocker compose config" not in text
        assert "\nsudo docker compose config" not in text
        assert "docker system prune --volumes" not in text
        assert "docker volume rm" not in text
        assert "docker volume prune" not in text


def test_recovery_script_is_staging_only_and_uses_safe_prunes() -> None:
    text = read(RECOVER)
    assert "sudo systemctl restart w2-staging.service" in text
    assert "docker builder prune -f" in text
    assert "docker image prune -f" in text
    assert "alembic" not in text
    assert "W2_API_FOOTBALL" not in text


def test_deploy_installs_watchdog_and_supports_stability_probe() -> None:
    text = read(DEPLOY)
    assert "w2-staging-watchdog.service" in text
    assert "w2-staging-watchdog.timer" in text
    assert "W2_STAGING_START_AFTER_DEPLOY" in text
    assert "stability_probe=PASS" in text
    assert "http://127.0.0.1:18000/health" in text
    assert "http://127.0.0.1:18000/ready" in text
    assert "http://127.0.0.1:18000/v1/version" in text
    assert "http://127.0.0.1/meta.json" in text
    assert "docker builder prune -f" in text
    assert "W2_STAGING_PRUNE_BUILD_CACHE" in text
    assert "compose up -d --no-deps api" in text
    assert "compose up -d --no-deps web" in text
    assert "worker_scheduler_restart=false" in text


def test_deploy_makes_shared_runtime_writable_for_staging_runtime_tasks() -> None:
    text = read(DEPLOY)
    assert "sudo install -d -o 10001 -g 10001 -m 0775 /opt/w2/shared/runtime" in text
    assert (
        "sudo install -d -o 10001 -g 10001 -m 0775 "
        "/opt/w2/shared/runtime/independent_signal_backfill/raw_payloads"
    ) in text
    assert "sudo chown 10001:10001 /opt/w2/shared/runtime" in text
    assert "sudo chown -R 10001:10001 /opt/w2/shared/runtime/independent_signal_backfill" in text
    assert "sudo chmod u+rwX,g+rwX /opt/w2/shared/runtime" in text
    assert "sudo chmod -R u+rwX,g+rwX /opt/w2/shared/runtime/independent_signal_backfill" in text


def test_watchdog_units_restart_only_staging_service() -> None:
    service = read(WATCHDOG_SERVICE)
    timer = read(WATCHDOG_TIMER)
    script = read(WATCH)
    assert "/opt/w2/current/scripts/watch_staging_runtime.sh" in service
    assert "OnUnitActiveSec=1min" in timer
    assert "sudo systemctl restart w2-staging.service" in script
    assert "production" not in service.lower()
    assert "production" not in timer.lower()
    assert "production" not in script.lower()


def test_diagnostic_script_is_read_only() -> None:
    text = read(DIAGNOSE)
    assert "docker stats --no-stream" in text
    assert "sudo docker system df" in text
    assert "sudo journalctl -u w2-staging.service" in text
    assert "systemctl restart" not in text
    assert "docker builder prune" not in text
    assert "docker image prune" not in text
