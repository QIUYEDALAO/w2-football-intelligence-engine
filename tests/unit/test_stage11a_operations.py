from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from apps.api.main import app
from fastapi.testclient import TestClient

from w2.config import get_settings
from w2.operations.alerts import AlertSeverity, AlertStore, OperationalAlert
from w2.operations.drift import drift_report
from w2.operations.observability import StructuredLogEvent
from w2.recovery.backup import LocalBackupRestoreDrill
from w2.security.baseline import Role, default_security_policy


def test_metrics_output_and_production_reject(monkeypatch) -> None:
    client = TestClient(app)
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "w2_api_requests_total" in response.text
    monkeypatch.setenv("W2_ENVIRONMENT", "production")
    get_settings.cache_clear()
    try:
        assert client.get("/metrics").status_code == 403
    finally:
        monkeypatch.setenv("W2_ENVIRONMENT", "local")
        get_settings.cache_clear()


def test_structured_log_redacts_sensitive_values() -> None:
    event = StructuredLogEvent(
        level="INFO",
        message="provider x-apisports-key:value",
        correlation_id="corr",
        payload={"note": "authorization:value"},
    )
    text = str(event.sanitized())
    assert "value" not in text
    assert "[REDACTED]" in text


def test_alert_idempotent_and_resolvable() -> None:
    store = AlertStore()
    alert = OperationalAlert(
        alert_key="low_quota",
        severity=AlertSeverity.WARNING,
        reason="quota low",
    )
    store.raise_alert(alert)
    store.raise_alert(alert)
    assert len(store.alerts) == 1
    assert store.audit[-1]["event"] == "alert_idempotent"
    resolved = store.resolve("low_quota", resolved_at=datetime.now(UTC))
    assert resolved is not None
    assert resolved.severity == AlertSeverity.RESOLVED


def test_drift_is_read_only_and_rbac_policy() -> None:
    drift = drift_report({"prediction": 0.1})
    assert drift["auto_tuning"] is False
    assert drift["auto_model_replacement"] is False
    assert drift["auto_gate_change"] is False
    policy = default_security_policy()
    assert policy.can(Role.VIEWER, "read:operations") is False
    assert policy.can(Role.OPERATOR, "read:operations") is True


def test_backup_restore_drill_verifies_sha(tmp_path: Path) -> None:
    drill = LocalBackupRestoreDrill(tmp_path)
    manifest = drill.backup(drill.synthetic_rows())
    restored = drill.restore(manifest)
    assert restored["verified"] is True
    assert restored["original_row_count"] == restored["restored_row_count"]
    assert restored["real_runtime_touched"] is False


def test_dockerfiles_non_root_and_healthcheck() -> None:
    for name in [
        "Dockerfile.api",
        "Dockerfile.worker",
        "Dockerfile.scheduler",
        "Dockerfile.web",
        "Dockerfile.migrations",
    ]:
        text = Path(name).read_text()
        assert "USER " in text
        assert "HEALTHCHECK" in text
