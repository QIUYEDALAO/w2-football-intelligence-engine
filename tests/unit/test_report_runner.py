from __future__ import annotations

import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import ClassVar

import pytest

from w2.reporting.report_runner import HealthCheckError, run_report_job


def _payload() -> dict[str, object]:
    return {
        "selected_football_day": "2026-06-30",
        "generated_at": "2026-06-30T23:40:00Z",
        "data_profile": "real-db",
        "data_source": "read-model-db",
        "all": [
            {
                "fixture_id": "f1",
                "kickoff_utc": "2026-06-30T20:00:00Z",
                "competition_name": "世界杯",
                "home_team_name": "France",
                "away_team_name": "Sweden",
                "status": "NS",
                "formal_recommendation": False,
                "recommendation": {"tier": "WATCH"},
                "pricing_shadow": {
                    "status": "READY",
                    "independent_signal_count": 5,
                    "fair_ah": -1.0,
                    "market_ah": -1.0,
                    "edge_ah": 0,
                    "beats_market": False,
                },
                "market_timeline": {
                    "status": "INSUFFICIENT",
                    "source": "market_timeline_snapshots",
                    "label": "盘口时间线 · 参照 · 未验证",
                    "verified": False,
                    "direction_allowed": False,
                },
                "data_refresh": {"last_success": "2026-06-30T19:00:00Z"},
            },
        ],
    }


class ReportRunnerHandler(BaseHTTPRequestHandler):
    payload: ClassVar[bytes] = json.dumps(_payload()).encode("utf-8")
    seen_paths: ClassVar[list[str]] = []
    fail_ready: ClassVar[bool] = False

    def do_GET(self) -> None:
        self.__class__.seen_paths.append(self.path)
        if self.path == "/health":
            self._write({"database": "ok", "redis": "ok"})
            return
        if self.path == "/ready":
            if self.__class__.fail_ready:
                self._write({"database": "ok"})
            else:
                self._write({"database": "ok", "redis": "ok"})
            return
        if self.path == "/v1/version":
            self._write(
                {
                    "api_git_sha": "test-sha",
                    "data_profile": "real-db",
                    "data_source": "read-model-db",
                    "generated_at": "2026-06-30T23:40:00Z",
                }
            )
            return
        if self.path.startswith("/v1/dashboard?"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(self.payload)
            return
        self.send_response(404)
        self.end_headers()

    def _write(self, payload: dict[str, object]) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode("utf-8"))

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return None


def _serve() -> tuple[HTTPServer, threading.Thread, str]:
    ReportRunnerHandler.seen_paths = []
    ReportRunnerHandler.fail_ready = False
    server = HTTPServer(("127.0.0.1", 0), ReportRunnerHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, f"http://127.0.0.1:{server.server_port}"


def test_report_runner_dry_run_is_read_only_and_returns_summary(tmp_path: Path) -> None:
    server, thread, base_url = _serve()
    try:
        result = run_report_job(base_url=base_url, sink="stdout", runtime_root=tmp_path)
    finally:
        server.shutdown()
        thread.join(timeout=2)

    assert "W2 足球日报告 · 2026-06-30" in result.report
    assert result.output_path is None
    assert not (tmp_path / "reports").exists()
    assert result.health["status"] == "PASS"
    assert result.status_summary["rows"] == 1
    assert result.status_summary["data_profile"] == "real-db"
    assert result.quota_summary == {
        "network_quota_required": False,
        "provider_calls": 0,
        "status": "NOT_REQUIRED_READ_ONLY_REPORT",
    }
    assert "/health" in ReportRunnerHandler.seen_paths
    assert "/ready" in ReportRunnerHandler.seen_paths
    assert "/v1/version" in ReportRunnerHandler.seen_paths
    assert sum(path.startswith("/v1/dashboard?") for path in ReportRunnerHandler.seen_paths) == 1


def test_report_runner_file_sink_writes_runtime_reports(tmp_path: Path) -> None:
    server, thread, base_url = _serve()
    try:
        result = run_report_job(
            base_url=base_url,
            sink="file",
            runtime_root=tmp_path,
            output_format="text",
        )
    finally:
        server.shutdown()
        thread.join(timeout=2)

    assert result.output_path is not None
    assert result.output_path.parent == tmp_path / "reports"
    assert result.output_path.suffix == ".txt"
    assert "W2 足球日报告 · 2026-06-30" in result.output_path.read_text(encoding="utf-8")


def test_report_runner_html_file_sink_writes_day_page(tmp_path: Path) -> None:
    server, thread, base_url = _serve()
    try:
        result = run_report_job(
            base_url=base_url,
            sink="file",
            runtime_root=tmp_path,
            output_format="html",
        )
    finally:
        server.shutdown()
        thread.join(timeout=2)

    assert result.output_path == tmp_path / "reports" / "w2_day_2026-06-30.html"
    html = result.output_path.read_text(encoding="utf-8") if result.output_path else ""
    assert "<!doctype html>" in html
    assert "W2 足球日报告 · 2026-06-30" in html
    assert "推荐：全场让球" not in html
    assert "方向未识别" not in html


def test_report_runner_health_gate_fails_before_file_write(tmp_path: Path) -> None:
    server, thread, base_url = _serve()
    ReportRunnerHandler.fail_ready = True
    try:
        with pytest.raises(HealthCheckError, match="HEALTH_CHECK_FAILED: ready=UNKNOWN"):
            run_report_job(base_url=base_url, sink="file", runtime_root=tmp_path)
    finally:
        server.shutdown()
        thread.join(timeout=2)

    assert not (tmp_path / "reports").exists()


def test_report_runner_cli_dry_run_prints_report_and_summary(tmp_path: Path) -> None:
    server, thread, base_url = _serve()
    try:
        result = subprocess.run(
            [
                sys.executable,
                "scripts/run_w2_report_runner.py",
                "--base-url",
                base_url,
                "--dry-run",
                "--runtime-root",
                str(tmp_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    finally:
        server.shutdown()
        thread.join(timeout=2)

    assert "W2 足球日报告 · 2026-06-30" in result.stdout
    summary = json.loads(result.stderr)
    assert summary["sink"] == "stdout"
    assert summary["quota_summary"]["provider_calls"] == 0
    assert not (tmp_path / "reports").exists()


def test_report_runner_cli_file_sink_writes_report(tmp_path: Path) -> None:
    server, thread, base_url = _serve()
    try:
        result = subprocess.run(
            [
                sys.executable,
                "scripts/run_w2_report_runner.py",
                "--base-url",
                base_url,
                "--file-sink",
                "--format",
                "text",
                "--runtime-root",
                str(tmp_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    finally:
        server.shutdown()
        thread.join(timeout=2)

    summary = json.loads(result.stdout)
    assert summary["sink"] == "file"
    output_path = Path(summary["output_path"])
    assert output_path.exists()
    assert output_path.parent == tmp_path / "reports"
    assert "W2 足球日报告 · 2026-06-30" in output_path.read_text(encoding="utf-8")


def test_report_runner_cli_html_file_sink_writes_report(tmp_path: Path) -> None:
    server, thread, base_url = _serve()
    try:
        result = subprocess.run(
            [
                sys.executable,
                "scripts/run_w2_report_runner.py",
                "--base-url",
                base_url,
                "--file-sink",
                "--format",
                "html",
                "--runtime-root",
                str(tmp_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    finally:
        server.shutdown()
        thread.join(timeout=2)

    summary = json.loads(result.stdout)
    assert summary["sink"] == "file"
    output_path = Path(summary["output_path"])
    assert output_path == tmp_path / "reports" / "w2_day_2026-06-30.html"
    assert "<!doctype html>" in output_path.read_text(encoding="utf-8")


def test_report_runner_cli_health_failure_exits_nonzero_without_file(
    tmp_path: Path,
) -> None:
    server, thread, base_url = _serve()
    ReportRunnerHandler.fail_ready = True
    try:
        result = subprocess.run(
            [
                sys.executable,
                "scripts/run_w2_report_runner.py",
                "--base-url",
                base_url,
                "--file-sink",
                "--runtime-root",
                str(tmp_path),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
    finally:
        server.shutdown()
        thread.join(timeout=2)

    assert result.returncode != 0
    assert "HEALTH_CHECK_FAILED: ready=UNKNOWN" in result.stderr
    assert result.stdout == ""
    assert not (tmp_path / "reports").exists()
