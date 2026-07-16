from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

CHECKER = Path(__file__).resolve().parents[2] / "scripts/check_w2_public_edge_latency.py"
WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/staging-edge-latency.yml"
CONTRACT = Path(__file__).resolve().parents[2] / "config/operations/public_edge_acceptance_v1.json"
SPEC = importlib.util.spec_from_file_location("public_edge_latency_checker", CHECKER)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def sample(
    *,
    remote_ip: str = "43.155.208.138",
    path_kind: str = "DIRECT",
    request_id: str = "0123456789abcdef",
) -> dict[str, object]:
    return {
        "schema": MODULE.SAMPLE_SCHEMA,
        "collected_at_utc": "2026-07-16T12:00:00Z",
        "curl_process_started_at_utc": "2026-07-16T11:59:59Z",
        "curl_process_finished_at_utc": "2026-07-16T12:00:00Z",
        "path_kind": path_kind,
        "no_proxy": path_kind == "DIRECT",
        "ip_protocol": "IPv4",
        "remote_ip": remote_ip,
        "connection_mode": "FRESH",
        "curl_process_index": 0,
        "request_index_within_process": 0,
        "num_connects": 1,
        "connection_reused": False,
        "curl_exit_code": 0,
        "endpoint": "/ready",
        "status": 200,
        "http_version": "1.1",
        "dns_seconds": 0.001,
        "connect_seconds": 0.12,
        "tls_seconds": 0.0,
        "pretransfer_seconds": 0.12,
        "starttransfer_seconds": 0.25,
        "total_seconds": 0.26,
        "response_bytes": 180,
        "request_id": request_id,
        "server_timing": {"route": 10.0},
        "correlation_status": "CORRELATED",
        "sample_valid_for_success_evidence": True,
        "sample_valid_for_failure_evidence": True,
    }


def observer_result(
    observer_id: str,
    *,
    passed: bool,
    target_route: bool = False,
) -> dict[str, object]:
    return {
        "observer_id": observer_id,
        "observer_kind": "PUBLIC_BLOCKING",
        "independence_group": observer_id,
        "target_route": target_route,
        "passed": passed,
        "failure_layer": None if passed else "TCP_CONNECT",
        "server_5xx": 0,
        "oom_delta": 0,
        "restart_delta": 0,
    }


def summary(
    *,
    p50: float = 0.4,
    p95: float = 0.8,
    maximum: float = 1.0,
    statuses: dict[str, int] | None = None,
) -> dict[str, object]:
    return {
        "p50_seconds": p50,
        "p95_seconds": p95,
        "max_seconds": maximum,
        "http_status_counts": statuses or {"200": 20},
    }


def command(tmp_path: Path, **kwargs: Any) -> list[str]:
    return MODULE.curl_command(
        "http://43.155.208.138/ready",
        path_kind="DIRECT",
        output_dir=tmp_path,
        **kwargs,
    )


def test_direct_command_forces_proxy_bypass_and_ipv4(tmp_path: Path) -> None:
    rendered = command(tmp_path)

    assert rendered[:4] == ["curl", "--noproxy", "*", "--ipv4"]


def test_ipv6_command_is_explicit(tmp_path: Path) -> None:
    assert "--ipv6" in command(tmp_path, ip_protocol="IPv6")


def test_direct_environment_removes_all_proxy_variables() -> None:
    environment = MODULE.curl_environment(
        path_kind="DIRECT",
        source={
            "PATH": "/usr/bin",
            "HTTP_PROXY": "http://loopback.invalid",
            "https_proxy": "http://loopback.invalid",
            "ALL_PROXY": "socks5://loopback.invalid",
            "NO_PROXY": "localhost",
        },
    )

    assert environment == {"PATH": "/usr/bin", "NO_PROXY": "*"}


def test_reused_command_assigns_unique_body_and_header_files(tmp_path: Path) -> None:
    rendered = command(tmp_path, requests=3)

    outputs = [rendered[index + 1] for index, value in enumerate(rendered) if value == "--output"]
    headers = [
        rendered[index + 1] for index, value in enumerate(rendered) if value == "--dump-header"
    ]
    assert len(outputs) == len(set(outputs)) == 3
    assert len(headers) == len(set(headers)) == 3
    assert rendered.count("--next") == 2


def test_fresh_connection_command_is_one_request_per_process(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="one request per process"):
        command(tmp_path, connection_mode="FRESH", requests=2)


def test_fresh_samples_with_single_worker_run_every_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    class Completed:
        returncode = 0
        stderr = ""

        def __init__(self, stdout: str) -> None:
            self.stdout = stdout

    def fake_run(rendered: list[str], **_: object) -> Completed:
        call_index = len(calls)
        calls.append(rendered)
        body = Path(rendered[rendered.index("--output") + 1])
        headers = Path(rendered[rendered.index("--dump-header") + 1])
        body.write_text(json.dumps({"request_id": f"request-{call_index}"}))
        headers.write_text("HTTP/1.1 200 OK\r\nServer-Timing: route;dur=1.0\r\n\r\n")
        return Completed(
            '{"status":"200","remote_ip":"43.155.208.138",'
            '"http_version":"1.1","dns_seconds":0.001,'
            '"connect_seconds":0.01,"tls_seconds":0.0,'
            '"pretransfer_seconds":0.01,"starttransfer_seconds":0.02,'
            '"total_seconds":0.03,"response_bytes":100,'
            '"num_connects":1,"curl_exit_code":0}\n'
        )

    monkeypatch.setattr(MODULE.subprocess, "run", fake_run)
    samples = MODULE.collect_samples(
        "http://43.155.208.138/ready",
        path_kind="DIRECT",
        requests=10,
        expected_remote_ip="43.155.208.138",
        connection_mode="FRESH",
        concurrency=1,
    )

    assert len(samples) == 10
    assert len(calls) == 10
    assert all(item["connection_reused"] is False for item in samples)
    assert len({item["request_id"] for item in samples}) == 10


def test_write_out_captures_transfer_facts_without_headers() -> None:
    assert "%{time_pretransfer}" in MODULE._WRITE_OUT
    assert "%{exitcode}" in MODULE._WRITE_OUT
    assert "%header{" not in MODULE._WRITE_OUT


def test_server_timing_is_allowlisted_and_control_characters_fail(tmp_path: Path) -> None:
    valid = tmp_path / "valid.headers"
    valid.write_bytes(b"HTTP/1.1 200 OK\r\nServer-Timing: route;dur=1.2, fixture;dur=0\r\n\r\n")
    assert MODULE._parse_server_timing(valid) == {"route": 1.2, "fixture": 0.0}

    invalid = tmp_path / "invalid.headers"
    invalid.write_bytes(b"HTTP/1.1 200 OK\r\nServer-Timing: route;dur=1\tbad\r\n\r\n")
    with pytest.raises(ValueError, match="EVIDENCE_CORRELATION_INVALID"):
        MODULE._parse_server_timing(invalid)


def test_request_id_limits_and_json_validation(tmp_path: Path) -> None:
    body = tmp_path / "response.body"
    body.write_text('{"request_id":"valid-id:1"}')
    assert MODULE._parse_request_id(body) == "valid-id:1"

    body.write_text('{"request_id":"invalid id"}')
    with pytest.raises(ValueError, match="REQUEST_ID_INVALID"):
        MODULE._parse_request_id(body)

    body.write_text("not-json")
    with pytest.raises(ValueError, match="RESPONSE_BODY_INVALID_JSON"):
        MODULE._parse_request_id(body)


def test_direct_sample_rejects_loopback_remote_ip() -> None:
    with pytest.raises(ValueError, match="DIRECT_REMOTE_IP_MISMATCH"):
        MODULE.validate_sample(
            sample(remote_ip="127.0.0.1"),
            expected_remote_ip="43.155.208.138",
        )


def test_ip_protocol_mismatch_fails() -> None:
    item = sample()
    item["ip_protocol"] = "IPv6"
    with pytest.raises(ValueError, match="IP_PROTOCOL_MISMATCH"):
        MODULE.validate_sample(item, expected_remote_ip="43.155.208.138")


def test_direct_and_proxy_samples_cannot_share_one_percentile() -> None:
    with pytest.raises(ValueError, match="MIXED_NETWORK_PATHS"):
        MODULE.summarize_samples([sample(), sample(remote_ip="127.0.0.1", path_kind="PROXY")])


def test_report_is_v2_and_omits_url_sensitive_material() -> None:
    report = MODULE.build_report(
        samples=[sample()],
        requested_url="http://43.155.208.138/ready?private_value=redacted-value",
        expected_remote_ip="43.155.208.138",
        observer={"observer_id": "current-external-host", "ip_protocol": "IPv4"},
        connection_mode="FRESH",
    )
    rendered = json.dumps(report, sort_keys=True)

    assert report["schema"] == MODULE.REPORT_SCHEMA
    assert report["collector_version"] == MODULE.COLLECTOR_VERSION
    assert report["endpoint"] == "/ready"
    assert "redacted-value" not in rendered


def test_v1_report_and_duplicate_request_ids_are_rejected() -> None:
    with pytest.raises(ValueError, match="REPORT_SCHEMA_INVALID"):
        MODULE.validate_report({"schema": "w2.public_edge_latency.v1"})

    report = MODULE.build_report(
        samples=[sample(request_id="one")],
        requested_url="http://43.155.208.138/ready",
        expected_remote_ip="43.155.208.138",
    )
    report["samples"].append(sample(request_id="one"))
    report["summary"]["sample_count"] = 2
    with pytest.raises(ValueError, match="DUPLICATE_REQUEST_ID"):
        MODULE.validate_report(report)


def test_acceptance_contract_requires_v2_and_keeps_thresholds() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    assert contract["required_evidence_schema"] == MODULE.REPORT_SCHEMA
    assert contract["required_sample_schema"] == MODULE.SAMPLE_SCHEMA
    assert contract["required_collector_version"] == MODULE.COLLECTOR_VERSION
    assert contract["target_route"]["status"] == "UNDECLARED"
    assert contract["minimum_independent_public_observers"] == 2
    assert contract["thresholds"] == {
        "warm_keepalive_p95_seconds": 1.5,
        "next_page_p95_seconds": 3.0,
        "cold_p50_seconds": 4.0,
        "cold_p95_seconds": 8.0,
        "cold_max_seconds_exclusive": 12.0,
        "max_502_504_timeout_count": 0,
    }


def test_observer_thresholds_are_evaluated_without_cross_observer_average() -> None:
    result = MODULE.evaluate_observer_evidence(
        warm=summary(p95=1.49),
        next_page=summary(p95=2.99),
        cold=summary(p50=3.99, p95=7.99, maximum=11.99),
        thresholds=json.loads(CONTRACT.read_text())["thresholds"],
    )
    assert result["passed"] is True


def test_non_200_sample_fails_observer() -> None:
    result = MODULE.evaluate_observer_evidence(
        warm=summary(statuses={"200": 19, "500": 1}),
        next_page=summary(),
        cold=summary(),
        thresholds=json.loads(CONTRACT.read_text())["thresholds"],
    )
    assert result["passed"] is False
    assert result["failed_checks"] == ["HTTP_NON_200"]


@pytest.mark.parametrize(
    ("observers", "target_status", "expected"),
    [
        (
            [observer_result("github", passed=True)],
            "UNDECLARED",
            "OBSERVER_COVERAGE_INSUFFICIENT",
        ),
        (
            [observer_result("github", passed=False), observer_result("external", passed=False)],
            "UNDECLARED",
            "GLOBAL_PUBLIC_EDGE_BLOCKED",
        ),
        (
            [
                observer_result("github", passed=True),
                observer_result("external", passed=True),
                observer_result("target", passed=False, target_route=True),
            ],
            "DECLARED",
            "TARGET_ROUTE_BLOCKED",
        ),
        (
            [
                observer_result("github", passed=True),
                observer_result("external", passed=True),
                observer_result("other", passed=False),
            ],
            "UNDECLARED",
            "ROUTE_SPECIFIC_WARNING",
        ),
    ],
)
def test_public_adjudication(
    observers: list[dict[str, object]], target_status: str, expected: str
) -> None:
    result = MODULE.adjudicate_public_observers(
        observers,
        target_route_status=target_status,
        minimum_independent_observers=2,
        server_diagnostics_passed=True,
    )
    assert result["classification"] == expected


def test_workflow_collects_and_validates_direct_ipv4_v2_only() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "--path-kind DIRECT" in workflow
    assert "--expected-remote-ip 43.155.208.138" in workflow
    assert "--path-kind PROXY" not in workflow
    assert "--observer-id github-hosted" in workflow
    assert workflow.count("--validate-report") == 3
