#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "src/w2/operations/observability.py",
    "src/w2/operations/alerts.py",
    "src/w2/operations/slo.py",
    "src/w2/operations/drift.py",
    "src/w2/security/baseline.py",
    "src/w2/recovery/backup.py",
    "migrations/versions/0012_create_stage11a_operations.py",
    "config/policies/observability.v1.json",
    "config/policies/alerts.v1.json",
    "config/policies/rbac.v1.json",
    "scripts/run_stage11a_backup_restore_drill.py",
    "scripts/check_w2_stage11a.py",
    "docs/adr/ADR-0014-observability-security-recovery.md",
    "docs/operations/W2_SLO_POLICY_V1.md",
    "docs/operations/W2_ALERT_POLICY_V1.md",
    "docs/security/W2_SECURITY_BASELINE_V1.md",
    "docs/runbooks/BACKUP_AND_RESTORE.md",
    "docs/runbooks/INCIDENT_RESPONSE_LOCAL_STAGING.md",
    "reports/W2_STAGE11A_SLO_AUDIT.json",
    "reports/W2_STAGE11A_BACKUP_RESTORE.json",
    "reports/W2_STAGE11A_SECURITY_AUDIT.json",
    "reports/W2_STAGE11A_RESULT.md",
    ".dockerignore",
    "Dockerfile.api",
    "Dockerfile.worker",
    "Dockerfile.scheduler",
    "Dockerfile.web",
    "Dockerfile.migrations",
]


def fail(message: str) -> None:
    print(f"W2 Stage11A check FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def load(path: str) -> object:
    return json.loads(read(path))


def main() -> int:
    for path in REQUIRED:
        if not (ROOT / path).is_file():
            fail(f"missing {path}")
    combined = "\n".join(read(path) for path in REQUIRED if path.endswith((".py", ".md", ".json")))
    for token in [
        "OperationalMetricRegistry",
        "prometheus_text",
        "StructuredLogEvent",
        "AlertSeverity",
        "CALIBRATION_REQUIRED",
        "DriftDiagnostic",
        "VIEWER",
        "OPERATOR",
        "ADMIN",
        "LocalBackupRestoreDrill",
        "operational_alert",
        "slo_evaluation",
        "backup_run",
        "restore_run",
        "security_audit_event",
    ]:
        if token not in combined:
            fail(f"missing Stage11A token {token}")
    slo = load("reports/W2_STAGE11A_SLO_AUDIT.json")
    backup = load("reports/W2_STAGE11A_BACKUP_RESTORE.json")
    security = load("reports/W2_STAGE11A_SECURITY_AUDIT.json")
    result = read("reports/W2_STAGE11A_RESULT.md")
    if "w2_api_requests_total" not in slo["metrics_text"]:  # type: ignore[index]
        fail("metrics text missing API counter")
    if slo["external_alerting"] is not False:  # type: ignore[index]
        fail("external alerting must be disabled")
    if slo["drift"]["auto_tuning"] is not False:  # type: ignore[index]
        fail("drift must be read-only")
    if backup["restore"]["verified"] is not True:  # type: ignore[index]
        fail("backup restore drill must verify")
    if backup["restore"]["real_runtime_touched"] is not False:  # type: ignore[index]
        fail("backup drill must not touch real runtime")
    if security["production_ops_enabled"] is not False:  # type: ignore[index]
        fail("production operations must be disabled")
    if security["external_notifications_enabled"] is not False:  # type: ignore[index]
        fail("external notifications must be disabled")
    if security["deepseek_enabled"] or security["recommendation_enabled"]:  # type: ignore[index]
        fail("DeepSeek and recommendation must stay disabled")
    for dockerfile in [
        "Dockerfile.api",
        "Dockerfile.worker",
        "Dockerfile.scheduler",
        "Dockerfile.web",
        "Dockerfile.migrations",
    ]:
        text = read(dockerfile)
        if "USER " not in text:
            fail(f"{dockerfile} missing non-root USER")
        if "HEALTHCHECK" not in text:
            fail(f"{dockerfile} missing healthcheck")
    for token in [
        "STAGE_11A=COMPLETED",
        "STAGE_11=PROVISIONAL",
        "EXTERNAL_ALERTING=DISABLED",
        "PRODUCTION_DEPLOYMENT=DISABLED",
        "GATE_4_NATIONAL_1X2=PROVISIONAL_FORWARD_HOLDOUT_PENDING",
        "STAGE_9=BLOCKED",
        "PUSH_BLOCKED_NO_ORIGIN",
    ]:
        if token not in result:
            fail(f"missing status {token}")
    print("W2 Stage11A check PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
