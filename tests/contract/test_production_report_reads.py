from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from w2.api import repository
from w2.tracking.formal_results import endpoint_summary

API_SOURCE_ROOTS = (Path("src/w2/api"), Path("apps/api"))
REPORT_PATH_PATTERN = re.compile(r"(?:^|[\"'/])reports(?:[\"'/])", re.IGNORECASE)


def test_production_api_source_cannot_reference_reports_paths() -> None:
    violations: list[str] = []
    for root in API_SOURCE_ROOTS:
        for path in sorted(root.rglob("*.py")):
            source = path.read_text(encoding="utf-8")
            if "REPORTS" in source or REPORT_PATH_PATTERN.search(source):
                violations.append(str(path))
    assert violations == []


def test_removed_report_repository_methods_stay_removed() -> None:
    for name in (
        "stage7e_usage",
        "stage7e_first_cycle",
        "stage7e_scheduler",
        "stage7e_result",
        "stage8_summary",
    ):
        assert not hasattr(repository.ReadModelRepository, name)


def test_formal_tracking_endpoint_ignores_report_file(tmp_path: Path, monkeypatch) -> None:
    report_path = tmp_path / "reports" / "report.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_text(
        '{"status":"POISONED_REPORT","sample_count":999}',
        encoding="utf-8",
    )
    monkeypatch.setenv("W2_FORMAL_TRACKING_REPORT", str(report_path))

    summary = endpoint_summary(runtime_root=tmp_path / "runtime")

    assert summary["status"] == "OBSERVING"
    assert summary["sample_count"] == 0


class EmptyReadModelRepository:
    def dashboard_latest_fixtures(self) -> list[dict[str, Any]]:
        return []

    def dashboard_data_health(self) -> None:
        return None

    def dashboard_provider(self) -> None:
        return None

    def dashboard_forward_status(self) -> None:
        return None

    def operation_payloads(self, name: str) -> list[dict[str, Any]]:
        return []


def test_missing_read_models_return_explicit_system_degraded() -> None:
    service = repository.ReadModelService(
        repository=EmptyReadModelRepository(),  # type: ignore[arg-type]
    )

    assert service.data_health()["gate4_progress"]["status"] == "SYSTEM_DEGRADED"
    assert service.provider_status()["status"] == "SYSTEM_DEGRADED"
    assert service.forward_status()["status"] == "SYSTEM_DEGRADED"
    assert service.operations_items("tasks") == []
