from __future__ import annotations

import importlib.util
import json
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

CHECKER = Path(__file__).resolve().parents[2] / "scripts/check_w2_public_edge_latency.py"
SPEC = importlib.util.spec_from_file_location("public_edge_curl_evidence", CHECKER)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class EvidenceHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    counter = 0
    counter_lock = threading.Lock()

    def log_message(self, _format: str, *args: object) -> None:
        del args

    def _next_id(self) -> str:
        with self.counter_lock:
            type(self).counter += 1
            return f"request-{type(self).counter}"

    def _send(
        self,
        status: int,
        body: bytes,
        *,
        timing: str | None = "route;dur=1.0, fixture;dur=0.5",
        close: bool = False,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if timing is not None:
            self.send_header("Server-Timing", timing)
        if close:
            self.send_header("Connection", "close")
        self.end_headers()
        try:
            self.wfile.write(body)
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        self.close_connection = close

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/timeout":
            time.sleep(0.3)
            self._send(200, json.dumps({"request_id": self._next_id()}).encode())
            return
        if path == "/badgateway":
            self._send(502, b"<html>bad gateway</html>", timing=None)
            return
        if path == "/malformed":
            self._send(200, b"not-json")
            return
        if path == "/empty":
            self._send(200, b'{"request_id":""}')
            return
        if path == "/oversized":
            self._send(
                200,
                json.dumps(
                    {
                        "request_id": self._next_id(),
                        "padding": "x" * MODULE.MAX_OBSERVER_RESPONSE_BODY_BYTES,
                    }
                ).encode(),
            )
            return
        request_id = self._next_id()
        self._send(
            200,
            json.dumps({"request_id": request_id}).encode(),
            close=path == "/reconnect",
        )


@pytest.fixture
def evidence_server() -> Iterator[str]:
    EvidenceHandler.counter = 0
    server = ThreadingHTTPServer(("127.0.0.1", 0), EvidenceHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def collect(url: str, **kwargs: Any) -> list[dict[str, Any]]:
    return MODULE.collect_samples(
        url,
        path_kind="DIRECT",
        requests=int(kwargs.pop("requests", 1)),
        expected_remote_ip="127.0.0.1",
        connection_mode=str(kwargs.pop("connection_mode", "FRESH")),
        concurrency=int(kwargs.pop("concurrency", 1)),
        ip_protocol="IPv4",
        **kwargs,
    )


def test_real_curl_reused_process_pairs_unique_bodies_and_reuses_connection(
    evidence_server: str,
) -> None:
    samples = collect(
        f"{evidence_server}/ok?private_value=must-not-survive",
        requests=3,
        connection_mode="REUSED",
    )

    assert [item["request_index_within_process"] for item in samples] == [0, 1, 2]
    assert [item["num_connects"] for item in samples] == [1, 0, 0]
    assert [item["connection_reused"] for item in samples] == [False, True, True]
    assert len({item["request_id"] for item in samples}) == 3
    assert all(item["correlation_status"] == "CORRELATED" for item in samples)
    report = MODULE.build_report(
        samples=samples,
        requested_url=f"{evidence_server}/ok?private_value=must-not-survive",
        expected_remote_ip="127.0.0.1",
    )
    rendered = json.dumps(report)
    assert "must-not-survive" not in rendered
    assert "padding" not in rendered


def test_real_curl_fresh_uses_one_process_per_transfer(evidence_server: str) -> None:
    samples = collect(
        f"{evidence_server}/ok",
        requests=4,
        connection_mode="FRESH",
        concurrency=2,
    )

    assert {item["curl_process_index"] for item in samples} == {0, 1, 2, 3}
    assert all(item["request_index_within_process"] == 0 for item in samples)
    assert all(item["num_connects"] == 1 for item in samples)
    assert all(item["connection_reused"] is False for item in samples)


def test_server_forced_reconnect_is_not_inferred_from_request_position(
    evidence_server: str,
) -> None:
    samples = collect(
        f"{evidence_server}/reconnect",
        requests=3,
        connection_mode="REUSED",
    )

    assert [item["num_connects"] for item in samples] == [1, 1, 1]
    assert all(item["connection_reused"] is False for item in samples)


@pytest.mark.parametrize(
    ("route", "error"),
    [
        ("malformed", "RESPONSE_BODY_INVALID_JSON"),
        ("empty", "REQUEST_ID_MISSING"),
        ("oversized", "OBSERVER_RESPONSE_BODY_TOO_LARGE"),
    ],
)
def test_success_correlation_failures_are_closed(
    evidence_server: str, route: str, error: str
) -> None:
    with pytest.raises(ValueError, match=error):
        collect(f"{evidence_server}/{route}")


def test_http_502_html_body_is_retained_as_failure_evidence(
    evidence_server: str,
) -> None:
    item = collect(f"{evidence_server}/badgateway")[0]

    assert item["status"] == 502
    assert item["request_id"] is None
    assert item["server_timing"] is None
    assert item["sample_valid_for_success_evidence"] is False
    assert item["sample_valid_for_failure_evidence"] is True
    assert item["correlation_status"] == "EDGE_FAILURE_BEFORE_API"


def test_timeout_is_retained_as_failure_evidence(evidence_server: str) -> None:
    item = collect(f"{evidence_server}/timeout", max_time_seconds=0.1)[0]

    assert item["status"] == 0
    assert item["curl_exit_code"] != 0
    assert item["sample_valid_for_success_evidence"] is False
    assert item["sample_valid_for_failure_evidence"] is True


def test_temporary_directories_are_cleaned(
    evidence_server: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_temporary_directory = MODULE.tempfile.TemporaryDirectory

    def temporary_directory(*args: Any, **kwargs: Any) -> Any:
        return real_temporary_directory(*args, dir=tmp_path, **kwargs)

    monkeypatch.setattr(MODULE.tempfile, "TemporaryDirectory", temporary_directory)
    collect(f"{evidence_server}/ok")

    assert list(tmp_path.iterdir()) == []
