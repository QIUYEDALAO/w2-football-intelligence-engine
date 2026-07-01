from __future__ import annotations

import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import ClassVar


def _payload() -> dict[str, object]:
    return {
        "selected_football_day": "2026-06-30",
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


def test_generate_w2_report_cli_reads_input_file(tmp_path: Path) -> None:
    payload_path = tmp_path / "dashboard.json"
    payload_path.write_text(json.dumps(_payload()), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/generate_w2_report.py",
            "--input",
            str(payload_path),
            "--report-type",
            "final",
            "--format",
            "markdown",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "W2 足球日报告 · 2026-06-30 · 临场最终" in result.stdout
    assert "状态：观察" in result.stdout


def test_generate_w2_report_cli_reads_url(tmp_path: Path) -> None:
    payload_text = json.dumps(_payload()).encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        payload: ClassVar[bytes] = payload_text

        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(self.payload)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return None

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    output_path = tmp_path / "report.txt"
    try:
        result = subprocess.run(
            [
                sys.executable,
                "scripts/generate_w2_report.py",
                "--url",
                f"http://127.0.0.1:{server.server_port}/dashboard",
                "--report-type",
                "morning",
                "--format",
                "text",
                "--output",
                str(output_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    finally:
        server.shutdown()
        thread.join(timeout=2)

    assert result.stdout == ""
    assert "W2 足球日报告 · 2026-06-30 · 早间预览" in output_path.read_text(
        encoding="utf-8"
    )
