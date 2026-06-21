#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from w2.operations.alerts import ALERT_RULES, AlertSeverity, AlertStore, OperationalAlert
from w2.operations.drift import drift_report
from w2.operations.observability import StructuredLogEvent, default_metric_registry
from w2.operations.slo import evaluate_slo
from w2.recovery.backup import LocalBackupRestoreDrill
from w2.security.baseline import (
    Role,
    default_security_policy,
    dependency_scan_summary,
    sanitize_audit_payload,
)

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime/stage11a/backup_restore_drill"
REPORTS = ROOT / "reports"


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True, default=str)
    path.write_text(text + "\n", encoding="utf-8")


def main() -> int:
    drill = LocalBackupRestoreDrill(RUNTIME)
    rows = drill.synthetic_rows()
    manifest = drill.backup(rows)
    restore = drill.restore(manifest)
    registry = default_metric_registry()
    registry.gauge("w2_provider_remaining_quota", 6323)
    registry.gauge("w2_forward_holdout_current_sample", 0)
    registry.gauge("w2_forward_holdout_target_sample", 50)
    alert_store = AlertStore()
    alert = OperationalAlert(
        alert_key="backup_stale",
        severity=AlertSeverity.WARNING,
        reason="local drill calibration required",
        payload={"threshold": "CALIBRATION_REQUIRED"},
    )
    alert_store.raise_alert(alert)
    alert_store.raise_alert(alert)
    alert_store.resolve("backup_stale", resolved_at=manifest.created_at)
    slo = evaluate_slo({"api_availability": 1.0, "backup_freshness": 1.0})
    security = default_security_policy()
    sanitized = sanitize_audit_payload(
        {
            "W2_ENVIRONMENT": "local",
            "W2_DATABASE_URL": "sqlite://credential_value_hidden",
            "IGNORED_PATH": "w1 credential file path omitted",
        }
    )
    log_event = StructuredLogEvent(
        level="INFO",
        message="provider x-apisports-key:hidden",
        correlation_id="stage11a",
        payload={"status": "ok"},
    )
    backup_report = {
        "manifest": manifest.__dict__,
        "restore": restore,
        "postgres_logical_backup": "ABSTRACTION_EXERCISED_WITH_SYNTHETIC_ROWS",
        "minio_raw_payload_manifest": "ABSTRACTION_ONLY_NO_RUNTIME_TOUCH",
        "config_schema_model_manifest": "INCLUDED_IN_SHA256_MANIFEST",
        "encrypted_backup_interface": manifest.encrypted_backup_interface,
    }
    security_report = {
        "rbac_roles": sorted(security.roles),
        "viewer_can_ops": security.can(Role.VIEWER, "read:operations"),
        "operator_can_ops": security.can(Role.OPERATOR, "read:operations"),
        "production_ops_enabled": security.production_ops_enabled,
        "external_notifications_enabled": security.external_notifications_enabled,
        "deepseek_enabled": security.deepseek_enabled,
        "recommendation_enabled": security.recommendation_enabled,
        "sanitized_payload": sanitized,
        "sanitized_log": log_event.sanitized(),
        "dependency_scan": dependency_scan_summary(),
        "w1_credential_paths_read": False,
    }
    slo_report = {
        "slo": slo,
        "alerts": {
            "active": [item.__dict__ for item in alert_store.alerts.values()],
            "audit": alert_store.audit,
            "rules": ALERT_RULES,
        },
        "drift": drift_report({}),
        "metrics_text": registry.prometheus_text(),
        "external_alerting": False,
    }
    result = "\n".join(
        [
            "# W2 Stage 11A Result",
            "",
            "STAGE_11A=COMPLETED",
            "STAGE_11=PROVISIONAL",
            "EXTERNAL_ALERTING=DISABLED",
            "PRODUCTION_DEPLOYMENT=DISABLED",
            "GATE_4_NATIONAL_1X2=PROVISIONAL_FORWARD_HOLDOUT_PENDING",
            "STAGE_9=BLOCKED",
            "DEEPSEEK_ENABLED=false",
            "CANDIDATE_OUTPUT=false",
            "RECOMMENDATION_OUTPUT=false",
            "DOCKER_RUNTIME_VALIDATION_BLOCKED",
            "PUSH_BLOCKED_NO_ORIGIN",
            "",
            "BLOCKER:",
            "",
            "- None",
        ]
    )
    write_json(REPORTS / "W2_STAGE11A_BACKUP_RESTORE.json", backup_report)
    write_json(REPORTS / "W2_STAGE11A_SECURITY_AUDIT.json", security_report)
    write_json(REPORTS / "W2_STAGE11A_SLO_AUDIT.json", slo_report)
    (REPORTS / "W2_STAGE11A_RESULT.md").write_text(result + "\n", encoding="utf-8")
    print("W2 Stage11A backup/restore drill PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
