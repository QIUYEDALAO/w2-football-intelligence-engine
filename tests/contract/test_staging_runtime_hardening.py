from __future__ import annotations

import json
import subprocess
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
    # The matrix goes where an installed package reads it. The overlay used to
    # write it under /app/docs, which the released image does not carry -- the
    # dashboard 500'd on every request there while this test passed.
    for destination in (
        "/app/src/w2/dashboard/data/SC21_FACTOR_ROLE_AUTHORITY_MATRIX.json",
        "/app/.venv/lib/python3.12/site-packages/w2/dashboard/data/"
        "SC21_FACTOR_ROLE_AUTHORITY_MATRIX.json",
    ):
        assert (
            "docs/review_packages/SC21_FACTOR_INPUT_CHAIN/"
            f"SC21_FACTOR_ROLE_AUTHORITY_MATRIX.json {destination}"
        ) in python_overlay
    assert "/app/docs/review_packages" not in python_overlay
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


def test_deploy_rollback_does_not_run_an_older_migration_image() -> None:
    text = read(DEPLOY)
    rollback = text.split("rollback() {", 1)[1].split("trap rollback ERR", 1)[0]

    assert '"${COMPOSE[@]}" pull api worker scheduler web' in rollback
    assert '"${COMPOSE[@]}" run --rm migration' not in rollback
    assert "--max-time 30 http://127.0.0.1:18000/v1/version" in text


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
            "${W2_PROVIDER_ENDPOINT_ALLOWLIST:-status,fixtures,odds,lineups,statistics}"
        )
        assert environment["W2_PROVIDER_REQUEST_LEDGER_ENABLED"] == "true"
        assert environment["W2_PROVIDER_REFRESH_TICK_HARD_CAP"] == "30"
        assert environment["W2_PROVIDER_DAILY_HARD_CAP"] == "7500"
        assert environment["W2_POSTMATCH_RESULT_DAILY_HARD_CAP"] == "800"
        assert environment["W2_PROVIDER_DAILY_UNALLOCATED_BUFFER"] == "0"
        assert environment["W2_PROVIDER_QUOTA_AUTHORITY_MAX_AGE_SECONDS"] == "7200"
        assert environment["W2_PROVIDER_PREFLIGHT_MIN_REMAINING"] == "1500"
        assert environment["W2_CANDIDATE_ENABLED"] == "true"
        assert environment["W2_FORMAL_RECOMMENDATION_ENABLED"] == "false"
        assert environment["W2_PRODUCTION_RELEASE"] == "false"
    common = yaml.safe_load(
        (ROOT / "infra/compose/compose.staging.yml").read_text(encoding="utf-8")
    )["x-common-env"]
    assert common["W2_PROVIDER_REQUEST_TIMEOUT_SECONDS"] == (
        "${W2_PROVIDER_REQUEST_TIMEOUT_SECONDS:-45}"
    )
    assert common["W2_PROVIDER_TIMEOUT_MAX_ATTEMPTS"] == (
        "${W2_PROVIDER_TIMEOUT_MAX_ATTEMPTS:-2}"
    )
    assert common["W2_PROVIDER_TIMEOUT_RETRY_BACKOFF_SECONDS"] == (
        "${W2_PROVIDER_TIMEOUT_RETRY_BACKOFF_SECONDS:-2}"
    )
    assert scheduler["W2_FUTURE_FIXTURE_REFRESH_ENABLED"] == "true"
    assert scheduler["W2_POSTMATCH_ONLY_ENABLED"] == (
        "${W2_POSTMATCH_ONLY_ENABLED:-false}"
    )
    assert scheduler["W2_FIXTURE_DISCOVERY_ENABLED"] == (
        "${W2_FIXTURE_DISCOVERY_ENABLED:-false}"
    )
    assert scheduler["W2_FIXTURE_DISCOVERY_MAX_OFFSET_DAYS"] == "7"
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


def test_deploy_preserve_remote_refresh_disabled_defaults_off_and_rejects_junk() -> None:
    text = read(DEPLOY)
    # Off unless asked for, so an ordinary deploy keeps its historical behaviour.
    assert 'PRESERVE_REMOTE_REFRESH_DISABLED="${W2_PRESERVE_REMOTE_REFRESH_DISABLED:-NO}"' in text
    # A value that is neither YES nor NO stops the deploy instead of being ignored.
    assert "W2_PRESERVE_REMOTE_REFRESH_DISABLED must be YES or NO" in text
    assert text.count("W2_PRESERVE_REMOTE_REFRESH_DISABLED must be YES or NO") == 2
    assert 'PRESERVE_REMOTE_REFRESH_DISABLED="$7"' in text


def test_deploy_preserve_mode_never_installs_the_enabled_override() -> None:
    """Protection mode must not be able to switch collection back on.

    The repository override enables provider calls and the scheduler. When
    preservation is requested the deployment has to leave the remote override
    alone and fail closed unless that remote file already disables both, so a
    hotfix cannot silently restart collection.
    """
    text = read(DEPLOY)
    guarded = text.split('if [ "${PRESERVE_REMOTE_REFRESH_DISABLED}" = "YES" ]; then', 1)[1]
    preserve_branch, remainder = guarded.split("\nelse\n", 1)
    assert "verify_remote_refresh_disabled" in preserve_branch
    assert "sudo install" not in preserve_branch
    assert (
        'sudo install -o root -g root -m 0644 \\\n'
        '    "${REMOTE_TMP_DIR}/controlled-future-refresh.override.yml"'
    ) in remainder

    helper = text.split("verify_remote_refresh_disabled() {", 1)[1].split("\n}\n", 1)[0]
    # It reads the remote gate that actually governs the containers ...
    assert '[ -f "${REMOTE_REFRESH_OVERRIDE}" ]' in helper
    assert "W2_PROVIDER_CALLS_DISABLED" in helper
    assert "W2_PROVIDER_SCHEDULER_ENABLED" in helper
    assert "W2_FUTURE_FIXTURE_REFRESH_ENABLED" in helper
    # ... and refuses anything that is not the disabled variant.
    assert helper.count("return 1") == 4
    # The staged override is installed exactly once, from the enabled branch only.
    assert text.count('"${REMOTE_TMP_DIR}/controlled-future-refresh.override.yml"') == 1


# The shape the live host actually carries while collection is paused: provider
# calls are off, the scheduler service stays up, and the scheduled future
# refresh is what is switched off.
_DISABLED_OVERRIDE = """\
services:
  worker:
    environment:
      W2_PROVIDER_CALLS_DISABLED: "true"
      W2_PROVIDER_SCHEDULER_ENABLED: "true"
  scheduler:
    environment:
      W2_PROVIDER_CALLS_DISABLED: "true"
      W2_PROVIDER_SCHEDULER_ENABLED: "true"
      W2_FUTURE_FIXTURE_REFRESH_ENABLED: "false"
"""

_ENABLED_OVERRIDE = _DISABLED_OVERRIDE.replace(
    'W2_PROVIDER_CALLS_DISABLED: "true"', 'W2_PROVIDER_CALLS_DISABLED: "false"'
).replace('W2_FUTURE_FIXTURE_REFRESH_ENABLED: "false"', 'W2_FUTURE_FIXTURE_REFRESH_ENABLED: "true"')


def _run_preserve_guard(tmp_path: Path, override: str | None) -> subprocess.CompletedProcess[str]:
    """Run the deploy script's own guard against a candidate remote override."""
    script = read(DEPLOY)
    body = script.split("verify_remote_refresh_disabled() {", 1)[1].split("\n}\n", 1)[0]
    path = tmp_path / "controlled-future-refresh.override.yml"
    if override is not None:
        path.write_text(override, encoding="utf-8")
    harness = (
        "set -uo pipefail\n"
        f'REMOTE_REFRESH_OVERRIDE="{path}"\n'
        "verify_remote_refresh_disabled() {" + body + "\n}\n"
        "verify_remote_refresh_disabled && echo GUARD_PASS\n"
    )
    return subprocess.run(["bash", "-c", harness], capture_output=True, text=True, check=False)


def test_preserve_guard_accepts_the_live_disabled_override(tmp_path: Path) -> None:
    result = _run_preserve_guard(tmp_path, _DISABLED_OVERRIDE)
    assert result.returncode == 0, result.stderr
    assert "GUARD_PASS" in result.stdout


def test_preserve_guard_accepts_the_scheduler_disabled_form(tmp_path: Path) -> None:
    override = _DISABLED_OVERRIDE.replace(
        'W2_PROVIDER_SCHEDULER_ENABLED: "true"', 'W2_PROVIDER_SCHEDULER_ENABLED: "false"'
    )
    result = _run_preserve_guard(tmp_path, override)
    assert result.returncode == 0, result.stderr


def test_preserve_guard_rejects_an_override_that_enables_collection(tmp_path: Path) -> None:
    result = _run_preserve_guard(tmp_path, _ENABLED_OVERRIDE)
    assert result.returncode != 0
    assert "enables W2_PROVIDER_CALLS_DISABLED" in result.stderr


def test_preserve_guard_rejects_a_missing_override(tmp_path: Path) -> None:
    result = _run_preserve_guard(tmp_path, None)
    assert result.returncode != 0
    assert "preserve mode requires" in result.stderr


def test_preserve_guard_rejects_an_override_without_the_disabled_gate(tmp_path: Path) -> None:
    override = (
        "services:\n"
        "  scheduler:\n"
        "    environment:\n"
        '      W2_PROVIDER_SCHEDULER_ENABLED: "true"\n'
    )
    result = _run_preserve_guard(tmp_path, override)
    assert result.returncode != 0
    assert "W2_PROVIDER_CALLS_DISABLED=true" in result.stderr


def test_preserve_guard_rejects_scheduled_refresh_left_on(tmp_path: Path) -> None:
    override = (
        "services:\n"
        "  scheduler:\n"
        "    environment:\n"
        '      W2_PROVIDER_CALLS_DISABLED: "true"\n'
        '      W2_PROVIDER_SCHEDULER_ENABLED: "true"\n'
        '      W2_FUTURE_FIXTURE_REFRESH_ENABLED: "true"\n'
    )
    result = _run_preserve_guard(tmp_path, override)
    assert result.returncode != 0
    assert "scheduled future refresh" in result.stderr
