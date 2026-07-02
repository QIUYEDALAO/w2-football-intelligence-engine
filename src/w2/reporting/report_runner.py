from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from w2.reporting.report_generator import ReportFormat, ReportType, render_report

ReportSink = Literal["stdout", "file"]


class HealthCheckError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReportRunResult:
    report: str
    report_type: ReportType
    output_format: ReportFormat
    sink: ReportSink
    output_path: Path | None
    health: dict[str, Any]
    status_summary: dict[str, Any]
    quota_summary: dict[str, Any]

    def summary(self) -> dict[str, Any]:
        return {
            "status": "PASS",
            "report_type": self.report_type,
            "format": self.output_format,
            "sink": self.sink,
            "output_path": str(self.output_path) if self.output_path is not None else None,
            "health": self.health,
            "status_summary": self.status_summary,
            "quota_summary": self.quota_summary,
        }


def run_report_job(
    *,
    base_url: str,
    window: str = "today",
    report_type: ReportType = "final",
    output_format: ReportFormat = "markdown",
    sink: ReportSink = "stdout",
    runtime_root: Path = Path("runtime"),
    include_debug: bool = True,
    timeout_seconds: float = 20,
) -> ReportRunResult:
    normalized_base = base_url.rstrip("/")
    health = _health_precheck(
        base_url=normalized_base,
        window=window,
        include_debug=include_debug,
        timeout_seconds=timeout_seconds,
    )
    dashboard = _dict(health.pop("_dashboard_payload"))
    report = render_report(dashboard, report_type=report_type, output_format=output_format)
    output_path = None
    if sink == "file":
        output_path = _write_report_file(
            report,
            payload=dashboard,
            report_type=report_type,
            output_format=output_format,
            runtime_root=runtime_root,
            window=window,
        )
    return ReportRunResult(
        report=report,
        report_type=report_type,
        output_format=output_format,
        sink=sink,
        output_path=output_path,
        health=health,
        status_summary=_status_summary(dashboard=dashboard, version=health["version"]),
        quota_summary=_quota_summary(),
    )


def _health_precheck(
    *,
    base_url: str,
    window: str,
    include_debug: bool,
    timeout_seconds: float,
) -> dict[str, Any]:
    checks = {
        "health": _fetch_json(f"{base_url}/health", timeout_seconds=timeout_seconds),
        "ready": _fetch_json(f"{base_url}/ready", timeout_seconds=timeout_seconds),
        "version": _fetch_json(f"{base_url}/v1/version", timeout_seconds=timeout_seconds),
        "dashboard": _fetch_json(
            _dashboard_url(base_url, window=window, include_debug=include_debug),
            timeout_seconds=timeout_seconds,
        ),
    }
    health = {
        "status": "PASS",
        "health": _endpoint_status(checks["health"]),
        "ready": _endpoint_status(checks["ready"]),
        "version_status": _endpoint_status(checks["version"]),
        "dashboard": _endpoint_status(checks["dashboard"]),
        "version_sha": checks["version"].get("api_git_sha"),
        "dashboard_rows": len(_list(checks["dashboard"].get("all"))),
        "version": checks["version"],
        "_dashboard_payload": checks["dashboard"],
    }
    _raise_for_unhealthy(health)
    return health


def _raise_for_unhealthy(health: dict[str, Any]) -> None:
    failed = [
        key
        for key in ("health", "ready", "version_status", "dashboard")
        if health.get(key) != "PASS"
    ]
    if failed:
        detail = ", ".join(f"{key}={health.get(key)}" for key in failed)
        raise HealthCheckError(f"HEALTH_CHECK_FAILED: {detail}")


def _fetch_json(url: str, *, timeout_seconds: float) -> dict[str, Any]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("report runner only supports http/https URLs")
    request = Request(url, headers={"Accept": "application/json"})  # noqa: S310
    with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
        raw = response.read().decode("utf-8")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError(f"endpoint did not return a JSON object: {url}")
    return payload


def _dashboard_url(base_url: str, *, window: str, include_debug: bool) -> str:
    query = urlencode({"window": window, "include_debug": str(include_debug).lower()})
    return f"{base_url}/v1/dashboard?{query}"


def _endpoint_status(payload: dict[str, Any]) -> str:
    if payload.get("database") == "ok" and payload.get("redis") == "ok":
        return "PASS"
    if payload.get("api_git_sha") or payload.get("generated_at"):
        return "PASS"
    if payload.get("all") is not None:
        return "PASS"
    return "UNKNOWN"


def _status_summary(*, dashboard: dict[str, Any], version: dict[str, Any]) -> dict[str, Any]:
    matches = [item for item in _list(dashboard.get("all")) if isinstance(item, dict)]
    return {
        "data_profile": dashboard.get("data_profile") or version.get("data_profile"),
        "data_source": dashboard.get("data_source") or version.get("data_source"),
        "generated_at": dashboard.get("generated_at"),
        "selected_football_day": dashboard.get("selected_football_day"),
        "rows": len(matches),
        "formal_payload_count": sum(1 for match in matches if match.get("formal_recommendation")),
        "candidate_true_count": sum(1 for match in matches if match.get("candidate") is True),
        "beats_market_true_count": sum(
            1
            for match in matches
            if _dict(match.get("pricing_shadow")).get("beats_market") is True
        ),
    }


def _quota_summary() -> dict[str, Any]:
    return {
        "network_quota_required": False,
        "provider_calls": 0,
        "status": "NOT_REQUIRED_READ_ONLY_REPORT",
    }


def _write_report_file(
    report: str,
    *,
    payload: dict[str, Any],
    report_type: ReportType,
    output_format: ReportFormat,
    runtime_root: Path,
    window: str,
) -> Path:
    generated_at = str(payload.get("generated_at") or payload.get("as_of") or payload.get("asof"))
    if not generated_at or generated_at == "None":
        raise ValueError("dashboard payload missing generated_at/as_of")
    safe_generated_at = (
        generated_at.replace(":", "")
        .replace("-", "")
        .replace(".", "")
        .replace("+", "")
        .replace("Z", "Z")
    )
    extension = {"markdown": "md", "text": "txt", "html": "html"}[output_format]
    reports_dir = runtime_root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    if output_format == "html":
        football_day = str(
            payload.get("selected_football_day") or payload.get("selected_date") or "unknown"
        )
        output_path = reports_dir / f"w2_day_{football_day}.{extension}"
    else:
        output_path = reports_dir / f"w2_{report_type}_{window}_{safe_generated_at}.{extension}"
    output_path.write_text(report, encoding="utf-8")
    return output_path


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []
