from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "infra/compose/compose.staging.yml"
DEPLOY = ROOT / "scripts/deploy_stage7h_staging.sh"
DIAGNOSE = ROOT / "scripts/diagnose_staging_runtime.sh"
RECOVER = ROOT / "scripts/recover_staging_runtime.sh"
WATCH = ROOT / "scripts/watch_staging_runtime.sh"
HEALTH_CHECK = ROOT / "scripts/check_w2_stage7h.py"
LEGACY_RECOVERY = ROOT / "config/policies/forward_ledger_legacy_recovery.staging.v1.json"
READINESS_FAULT = ROOT / "scripts/run_readiness_fault_injection.sh"
WATCHDOG_SERVICE = ROOT / "infra/systemd/w2-staging-watchdog.service"
WATCHDOG_TIMER = ROOT / "infra/systemd/w2-staging-watchdog.timer"
LOCAL_PYTHON_OVERLAY = ROOT / "infra/local-release/Dockerfile.python-overlay"
LOCAL_WEB_OVERLAY = ROOT / "infra/local-release/Dockerfile.web-overlay"


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


def test_staging_services_use_published_images_without_builds() -> None:
    compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    services = compose["services"]
    for service in ("migration", "api", "worker", "scheduler"):
        assert services[service]["image"].startswith("${W2_PYTHON_IMAGE:")
        assert "build" not in services[service]
    assert services["web"]["image"].startswith("${W2_WEB_IMAGE:")
    assert "build" not in services["web"]


def test_local_release_overlays_are_offline_and_source_scoped() -> None:
    python_overlay = read(LOCAL_PYTHON_OVERLAY)
    web_overlay = read(LOCAL_WEB_OVERLAY)
    for overlay in (python_overlay, web_overlay):
        assert "FROM ${W2_LOCAL_BASE_IMAGE}" in overlay
        after_from = overlay.split("FROM ${W2_LOCAL_BASE_IMAGE}", 1)[1]
        assert "ARG LOCAL_RELEASE_SHA" in after_from
        assert "ARG LOCAL_RELEASE_TIME" in after_from
        assert "https://" not in overlay
        assert "ghcr.io" not in overlay
        assert "apt-get" not in overlay
        assert "pip install" not in overlay
    assert "src/w2 /app/.venv/lib/python3.12/site-packages/w2" in python_overlay
    assert (
        "SC21_FACTOR_ROLE_AUTHORITY_MATRIX.json "
        "/app/docs/review_packages/SC21_FACTOR_INPUT_CHAIN/"
        "SC21_FACTOR_ROLE_AUTHORITY_MATRIX.json"
    ) in python_overlay
    for runtime_root in ("alembic.ini", "apps", "config", "migrations"):
        assert f"{runtime_root} /app/{runtime_root}" in python_overlay
    assert '"web_git_sha"' in web_overlay


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


def test_deploy_is_pull_only_and_health_checked() -> None:
    text = read(DEPLOY)
    assert r"127\.0\.0\.1:5000/w2/" in text
    assert "VPS-loopback registry digest reference" in text
    assert '"${COMPOSE[@]}" pull migration api worker scheduler web' in text
    assert '"${COMPOSE[@]}" run --rm migration' in text
    assert '"${COMPOSE[@]}" up -d --remove-orphans api worker scheduler web' in text
    compose_commands = [
        line.strip()
        for line in text.splitlines()
        if '"${COMPOSE[@]}"' in line
        and any(action in line for action in (" pull ", " run ", " up "))
    ]
    assert compose_commands
    assert all("</dev/null" in command for command in compose_commands)
    assert "http://127.0.0.1:18000/ready" in text
    assert "http://127.0.0.1:18000/v1/version" in text
    assert "http://127.0.0.1:18080/meta.json" in text
    assert "http://127.0.0.1:18080/v1/dashboard/intelligence-workspace" in text
    assert "org.opencontainers.image.revision" in text
    assert "org.opencontainers.image.created" in text
    assert "w2.release.id" in text
    assert '[ "${PYTHON_REVISION}" = "${REVISION}" ]' in text
    assert '[ "${WEB_REVISION}" = "${REVISION}" ]' in text
    assert '[ "${PYTHON_RELEASE_ID}" = "${REVISION}" ]' in text
    assert '[ "${WEB_RELEASE_ID}" = "${REVISION}" ]' in text
    assert "W2_API_IMAGE_ID" in text
    assert "W2_API_OCI_DIGEST" in text
    assert "W2_API_REGISTRY_DIGEST" in text
    assert "w2.release_record.v1" in text
    assert "W2_PUBLIC_RESPONSE_SCHEMA_TOUCHED must be YES or NO" in text
    assert '"public_response_schema_touched"' in text
    assert '"workspace_http_status": "PASS"' in text
    assert "<<'PY' | sudo tee \\" in text
    assert "release.previous.env" in text
    assert "target_seconds=120" in text
    assert "rollback=FAIL health_or_digest_mismatch" in text
    assert "WARM_SWITCH" in text
    assert "COLD_PULL_END_TO_END" in text


def test_deploy_uploads_to_revision_scoped_remote_directory() -> None:
    text = read(DEPLOY)
    assert 'REMOTE_TMP_DIR="/tmp/w2-deploy-${REVISION}"' in text
    assert '"${SSH_HOST}:${REMOTE_TMP_DIR}/"' in text
    assert '"${REMOTE_TMP_DIR}/release.env"' in text
    assert '"${SSH_HOST}:/tmp/"' not in text


def test_health_check_targets_the_canonical_compose_project_and_cohort() -> None:
    text = read(HEALTH_CHECK)
    assert 'COMPOSE_PROJECT = "w2-staging"' in text
    assert 'COMPOSE_FILE = "/opt/w2/deploy/compose.staging.yml"' in text
    assert (
        'CONTROLLED_REFRESH_OVERRIDE = '
        '"/opt/w2/deploy/controlled-future-refresh.override.yml"'
    ) in text
    assert 'ENV_FILE = "/opt/w2/shared/.env"' in text
    assert 'name = svc.get("Service", "?")' in text
    assert 'ledger.get("schema_version") != "w2.forward_ledger_performance.v3"' in text
    assert 'if invariants.get("status") != "PASS":' in text
    assert '"closing_within_30m_before_kickoff" not in clv.get("method", "")' in text
    assert 'fail("performance cohort CLV candidate partition is inconsistent")' in text
    assert 'cohort.get("integrity_status") != "PASS"' in text
    assert 'fail("performance cohort evidence and settlement integrity is not PASS")' in text


def test_controlled_future_refresh_is_source_controlled_and_deployed_with_scheduler() -> None:
    override_path = ROOT / "infra/compose/controlled-future-refresh.override.yml"
    override = yaml.safe_load(override_path.read_text(encoding="utf-8"))
    worker = override["services"]["worker"]["environment"]
    scheduler = override["services"]["scheduler"]["environment"]
    for environment in (worker, scheduler):
        assert environment["W2_PROVIDER_HTTP_MAX_ATTEMPTS"] == "1"
        assert environment["W2_PROVIDER_ENDPOINT_ALLOWLIST"] == (
            "${W2_PROVIDER_ENDPOINT_ALLOWLIST:-status,fixtures}"
        )
        assert environment["W2_PROVIDER_REQUEST_LEDGER_ENABLED"] == "true"
        assert environment["W2_PROVIDER_REFRESH_TICK_HARD_CAP"] == "30"
        assert environment["W2_PROVIDER_DAILY_HARD_CAP"] == "70"
        assert environment["W2_POSTMATCH_RESULT_DAILY_HARD_CAP"] == "20"
        assert environment["W2_PROVIDER_DAILY_UNALLOCATED_BUFFER"] == "10"
        assert environment["W2_PROVIDER_QUOTA_AUTHORITY_MAX_AGE_SECONDS"] == "7200"
        assert environment["W2_PROVIDER_PREFLIGHT_MIN_REMAINING"] == "20"
        assert environment["W2_CANDIDATE_ENABLED"] == "true"
        assert environment["W2_FORMAL_RECOMMENDATION_ENABLED"] == "false"
        assert environment["W2_PRODUCTION_RELEASE"] == "false"
    assert scheduler["W2_FUTURE_FIXTURE_REFRESH_ENABLED"] == "true"
    assert scheduler["W2_POSTMATCH_ONLY_ENABLED"] == (
        "${W2_POSTMATCH_ONLY_ENABLED:-true}"
    )
    assert scheduler["W2_FIXTURE_DISCOVERY_ENABLED"] == (
        "${W2_FIXTURE_DISCOVERY_ENABLED:-false}"
    )
    assert scheduler["W2_FIXTURE_DISCOVERY_MAX_OFFSET_DAYS"] == "1"
    assert "W2_FUTURE_REFRESH_COMPETITION_ALLOWLIST" not in scheduler
    deploy = read(DEPLOY)
    unit = read(ROOT / "infra/systemd/w2-staging.service")
    assert "controlled-future-refresh.override.yml" in deploy
    assert "controlled-future-refresh.override.yml" in unit
    assert "api worker scheduler web" in deploy
    assert "api worker scheduler web" in unit


def test_staging_legacy_recovery_manifest_contains_only_unique_capture_cases() -> None:
    payload = json.loads(read(LEGACY_RECOVERY))
    entries = payload["entries"]

    assert payload["schema_version"] == "w2.forward_ledger_legacy_recovery.v1"
    assert payload["environment"] == "staging"
    assert payload["policy"] == "unique_validation_capture_exact_identity"
    assert payload["authority_status"] == "MIGRATION_INPUT_ONLY"
    assert {entry["fixture_id"] for entry in entries} == {
        "1492295",
        "1492297",
        "1492299",
        "1576804",
    }
    assert all(len(entry["capture_hash"]) == 64 for entry in entries)


def test_deploy_has_no_server_build_or_source_release() -> None:
    text = read(DEPLOY)
    for forbidden in (
        "docker build",
        "compose build",
        "git archive",
        "tar -x",
        "uv sync",
        "pip install",
        "/opt/w2/releases/${REVISION}/src",
    ):
        assert forbidden not in text
    assert "W2_PYTHON_IMAGE" in text
    assert "W2_WEB_IMAGE" in text
    assert "@sha256:" in text


def test_deploy_writes_release_metadata_with_root_owned_install() -> None:
    text = read(DEPLOY)
    assert 'BUILD_TIME="$(date' not in text
    assert "VITE_BUILD_TIME" not in text
    assert (
        'sudo install -o root -g root -m 0644 "${REMOTE_TMP_DIR}/release.env"'
    ) in text
    pull_end = text.index('sudo docker pull "${WEB_IMAGE}"')
    identity_verified = text.index('[[ "${WEB_REGISTRY_DIGEST}" =~')
    activation = text.index("ACTIVATED=true")
    assert pull_end < identity_verified < activation
    assert "activation=SKIPPED preactivation_verification_failed" in text


def test_deploy_installs_documented_health_checker_without_source_upload() -> None:
    deploy = read(DEPLOY)
    runbook = read(ROOT / "docs/runbooks/STAGE7H_VPS_STAGING.md")
    installed_path = "/opt/w2/deploy/check_w2_stage7h.py"

    assert installed_path in deploy
    assert '"${W2_DEPLOY_ROOT}/deploy/check_w2_stage7h.py"' in runbook
    assert "/opt/w2" not in runbook
    assert "install -o root -g root -m 0444" in deploy
    assert "${W2_DEPLOY_ROOT}/current/scripts/check_w2_stage7h.py" not in runbook


def test_runtime_healthchecks_and_release_probes_use_canonical_ready() -> None:
    compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    api_healthcheck = " ".join(
        str(item) for item in compose["services"]["api"]["healthcheck"]["test"]
    )
    assert "http://127.0.0.1:8000/ready" in api_healthcheck
    assert "/health" not in api_healthcheck
    for path in (DEPLOY, RECOVER, WATCH):
        text = read(path)
        assert "http://127.0.0.1:18000/ready" in text
        assert "http://127.0.0.1:18000/health" not in text


def test_readiness_fault_injection_is_isolated_from_formal_staging() -> None:
    text = read(READINESS_FAULT)
    assert "w2-readiness-fault" in text
    assert "W2_READINESS_FAULT_IMAGE_PREFIX" in text
    assert "W2_READINESS_FAULT_PORT" in text
    assert "w2-staging" not in text
    assert "/opt/w2/shared" not in text
    assert "docker volume rm \"${VOLUME}\"" in text


def test_deploy_makes_shared_runtime_writable_for_staging_runtime_tasks() -> None:
    text = read(DEPLOY)
    assert "sudo install -d -o 10001 -g 10001 -m 0775 /opt/w2/shared/runtime" in text
    assert (
        "/opt/w2/shared/runtime/independent_signal_backfill/raw_payloads"
    ) in text
    assert "/opt/w2/shared/runtime/market_timeline_snapshots" in text
    assert "/opt/w2/shared/runtime/reports/public" in text


def test_watchdog_units_restart_only_staging_service() -> None:
    service = read(WATCHDOG_SERVICE)
    timer = read(WATCHDOG_TIMER)
    script = read(WATCH)
    assert "/opt/w2/deploy/watch_staging_runtime.sh" in service
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
