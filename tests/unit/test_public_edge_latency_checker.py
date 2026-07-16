from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

CHECKER = Path(__file__).resolve().parents[2] / "scripts/check_w2_public_edge_latency.py"
WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/staging-edge-latency.yml"
CONTRACT = (
    Path(__file__).resolve().parents[2]
    / "config/operations/public_edge_acceptance_v1.json"
)
SPEC = importlib.util.spec_from_file_location("public_edge_latency_checker", CHECKER)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def sample(*, remote_ip: str = "43.155.208.138", path_kind: str = "DIRECT") -> dict[str, object]:
    return {
        "path_kind": path_kind,
        "endpoint": "/ready",
        "status": 200,
        "remote_ip": remote_ip,
        "http_version": "1.1",
        "dns_seconds": 0.001,
        "connect_seconds": 0.12,
        "tls_seconds": 0.0,
        "pretransfer_seconds": 0.12,
        "starttransfer_seconds": 0.25,
        "total_seconds": 0.26,
        "response_bytes": 180,
        "connection_reused": False,
        "request_id": "0123456789abcdef",
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


def test_direct_command_forces_proxy_bypass() -> None:
    command = MODULE.curl_command(
        "http://43.155.208.138/ready",
        path_kind="DIRECT",
    )

    assert command[:3] == ["curl", "--noproxy", "*"]


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


def test_reused_connection_command_discards_every_response_body() -> None:
    command = MODULE.curl_command(
        "http://43.155.208.138/ready",
        path_kind="DIRECT",
        requests=3,
    )

    assert command.count("--output") == 3
    assert command.count("/dev/null") == 3


def test_fresh_connection_command_disables_reuse() -> None:
    command = MODULE.curl_command(
        "http://43.155.208.138/ready",
        path_kind="DIRECT",
        connection_mode="FRESH",
    )

    assert "--fresh-connect" not in command
    assert "--no-keepalive" in command


def test_fresh_connection_command_is_one_request_per_process() -> None:
    with pytest.raises(ValueError, match="one request per process"):
        MODULE.curl_command(
            "http://43.155.208.138/ready",
            path_kind="DIRECT",
            connection_mode="FRESH",
            requests=2,
        )


def test_write_out_captures_layer_timings_and_sanitized_request_id() -> None:
    assert "%{time_pretransfer}" in MODULE._WRITE_OUT
    assert "%header{x-request-id}" in MODULE._WRITE_OUT


def test_zero_http_status_from_transport_failure_is_valid_json() -> None:
    rendered = MODULE._WRITE_OUT.replace("%{http_code}", "000")
    rendered = rendered.replace("%{remote_ip}", "")
    rendered = rendered.replace("%{http_version}", "0")
    for field in (
        "%{time_namelookup}",
        "%{time_connect}",
        "%{time_appconnect}",
        "%{time_pretransfer}",
        "%{time_starttransfer}",
        "%{time_total}",
        "%{size_download}",
        "%{num_connects}",
    ):
        rendered = rendered.replace(field, "0")

    assert json.loads(rendered)["status"] == "000"


def test_direct_sample_rejects_loopback_remote_ip() -> None:
    with pytest.raises(ValueError, match="DIRECT_REMOTE_IP_MISMATCH"):
        MODULE.validate_sample(
            sample(remote_ip="127.0.0.1"),
            expected_remote_ip="43.155.208.138",
        )


def test_direct_and_proxy_samples_cannot_share_one_percentile() -> None:
    with pytest.raises(ValueError, match="MIXED_NETWORK_PATHS"):
        MODULE.summarize_samples(
            [sample(), sample(remote_ip="127.0.0.1", path_kind="PROXY")]
        )


def test_report_omits_query_headers_and_credentials() -> None:
    report = MODULE.build_report(
        samples=[sample()],
        requested_url="http://43.155.208.138/ready?credential=redacted-value",
        expected_remote_ip="43.155.208.138",
        observer={
            "observer_id": "current-external-host",
            "environment": "LOCAL_EXTERNAL",
            "network_provider": "UNDECLARED",
            "target_user_region": False,
            "ip_protocol": "IPv4",
        },
        connection_mode="FRESH",
    )
    rendered = json.dumps(report, sort_keys=True)

    assert report["endpoint"] == "/ready"
    assert "cred" + "ential" not in rendered
    assert "redacted-value" not in rendered
    assert "author" + "ization" not in rendered.lower()
    assert "coo" + "kie" not in rendered.lower()
    assert report["observer"]["observer_id"] == "current-external-host"
    assert report["connection_mode"] == "FRESH"


def test_acceptance_contract_keeps_thresholds_and_target_route_undeclared() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    assert contract["schema"] == "w2.public_edge_acceptance.v1"
    assert contract["target_route"]["status"] == "UNDECLARED"
    assert contract["minimum_independent_public_observers"] == 2
    assert contract["failure_layers"] == [
        "DNS",
        "TCP_CONNECT",
        "TLS_HANDSHAKE",
        "OUTER_EDGE_OR_PROXY",
        "STAGING_NGINX",
        "NGINX_TO_API",
        "API_BUILD",
        "RESPONSE_TRANSFER",
    ]
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
        thresholds={
            "warm_keepalive_p95_seconds": 1.5,
            "next_page_p95_seconds": 3.0,
            "cold_p50_seconds": 4.0,
            "cold_p95_seconds": 8.0,
            "cold_max_seconds_exclusive": 12.0,
            "max_502_504_timeout_count": 0,
        },
    )

    assert result["passed"] is True
    assert result["failed_checks"] == []


def test_single_observer_warm_failure_remains_a_failure() -> None:
    result = MODULE.evaluate_observer_evidence(
        warm=summary(p95=1.51),
        next_page=summary(),
        cold=summary(),
        thresholds={
            "warm_keepalive_p95_seconds": 1.5,
            "next_page_p95_seconds": 3.0,
            "cold_p50_seconds": 4.0,
            "cold_p95_seconds": 8.0,
            "cold_max_seconds_exclusive": 12.0,
            "max_502_504_timeout_count": 0,
        },
    )

    assert result["passed"] is False
    assert result["failed_checks"] == ["WARM_KEEPALIVE_P95"]


def test_two_passes_and_one_non_target_failure_is_route_specific_warning() -> None:
    result = MODULE.adjudicate_public_observers(
        [
            observer_result("github", passed=True),
            observer_result("external-2", passed=True),
            observer_result("current-host", passed=False),
        ],
        target_route_status="UNDECLARED",
        minimum_independent_observers=2,
        server_diagnostics_passed=True,
    )

    assert result["classification"] == "ROUTE_SPECIFIC_WARNING"
    assert result["blocking"] is False


def test_two_independent_failures_block_global_public_edge() -> None:
    result = MODULE.adjudicate_public_observers(
        [
            observer_result("github", passed=False),
            observer_result("current-host", passed=False),
            observer_result("external-2", passed=True),
        ],
        target_route_status="UNDECLARED",
        minimum_independent_observers=2,
        server_diagnostics_passed=True,
    )

    assert result["classification"] == "GLOBAL_PUBLIC_EDGE_BLOCKED"
    assert result["blocking"] is True


def test_declared_target_route_failure_blocks_even_when_other_routes_pass() -> None:
    result = MODULE.adjudicate_public_observers(
        [
            observer_result("github", passed=True),
            observer_result("external-2", passed=True),
            observer_result("target", passed=False, target_route=True),
        ],
        target_route_status="DECLARED",
        minimum_independent_observers=2,
        server_diagnostics_passed=True,
    )

    assert result["classification"] == "TARGET_ROUTE_BLOCKED"
    assert result["blocking"] is True


def test_one_public_observer_is_insufficient_coverage() -> None:
    result = MODULE.adjudicate_public_observers(
        [observer_result("github", passed=True)],
        target_route_status="UNDECLARED",
        minimum_independent_observers=2,
        server_diagnostics_passed=True,
    )

    assert result["classification"] == "OBSERVER_COVERAGE_INSUFFICIENT"
    assert result["blocking"] is True


def test_external_observer_workflow_uses_direct_checker_only() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "--path-kind DIRECT" in workflow
    assert "--expected-remote-ip 43.155.208.138" in workflow
    assert "--path-kind PROXY" not in workflow
    assert "--observer-id github-hosted" in workflow
    assert "--observer-environment GITHUB_HOSTED" in workflow
    assert "--connection-mode REUSED" in workflow
    assert "--connection-mode FRESH" in workflow
    assert "--concurrency \"$concurrency\"" in workflow
    assert "future-page2" in workflow
    assert "upload-artifact" in workflow
