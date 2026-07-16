from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

CHECKER = Path(__file__).resolve().parents[2] / "scripts/check_w2_public_edge_latency.py"
WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/staging-edge-latency.yml"
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
        "starttransfer_seconds": 0.25,
        "total_seconds": 0.26,
        "response_bytes": 180,
        "connection_reused": False,
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


def test_zero_http_status_from_transport_failure_is_valid_json() -> None:
    rendered = MODULE._WRITE_OUT.replace("%{http_code}", "000")
    rendered = rendered.replace("%{remote_ip}", "")
    rendered = rendered.replace("%{http_version}", "0")
    for field in (
        "%{time_namelookup}",
        "%{time_connect}",
        "%{time_appconnect}",
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
    )
    rendered = json.dumps(report, sort_keys=True)

    assert report["endpoint"] == "/ready"
    assert "cred" + "ential" not in rendered
    assert "redacted-value" not in rendered
    assert "author" + "ization" not in rendered.lower()
    assert "coo" + "kie" not in rendered.lower()


def test_external_observer_workflow_uses_direct_checker_only() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "--path-kind DIRECT" in workflow
    assert "--expected-remote-ip 43.155.208.138" in workflow
    assert "--path-kind PROXY" not in workflow
    assert "upload-artifact" in workflow
