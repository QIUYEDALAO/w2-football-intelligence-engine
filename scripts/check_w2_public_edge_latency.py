from __future__ import annotations

import argparse
import concurrent.futures
import ipaddress
import json
import math
import os
import re
import statistics
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

REPORT_SCHEMA = "w2.public_edge_latency.v2"
SAMPLE_SCHEMA = "w2.public_edge_latency.sample.v2"
COLLECTOR_VERSION = "w2.public_edge_observer.v2"
MAX_OBSERVER_RESPONSE_BODY_BYTES = 1024 * 1024
MAX_SERVER_TIMING_BYTES = 4 * 1024
MAX_REQUEST_ID_BYTES = 128
_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]+$")
_SERVER_TIMING_METRICS = {
    "route",
    "fixture",
    "capture",
    "market",
    "performance",
    "projection",
    "validation",
    "serialization",
}
_PROXY_ENVIRONMENT_NAMES = {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"}
_WRITE_OUT = (
    '{"status":"%{http_code}","remote_ip":"%{remote_ip}",'
    '"http_version":"%{http_version}","dns_seconds":%{time_namelookup},'
    '"connect_seconds":%{time_connect},"tls_seconds":%{time_appconnect},'
    '"pretransfer_seconds":%{time_pretransfer},'
    '"starttransfer_seconds":%{time_starttransfer},"total_seconds":%{time_total},'
    '"response_bytes":%{size_download},"num_connects":%{num_connects},'
    '"curl_exit_code":%{exitcode}}\n'
)


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def curl_environment(*, path_kind: str, source: Mapping[str, str] | None = None) -> dict[str, str]:
    environment = dict(os.environ if source is None else source)
    if path_kind == "PROXY":
        return environment
    if path_kind != "DIRECT":
        raise ValueError("path_kind must be DIRECT or PROXY")
    direct = {
        name: value
        for name, value in environment.items()
        if name.upper() not in _PROXY_ENVIRONMENT_NAMES
    }
    direct["NO_PROXY"] = "*"
    return direct


def _transfer_paths(root: Path, process_index: int, request_index: int) -> tuple[Path, Path]:
    stem = f"process-{process_index}-transfer-{request_index}"
    return root / f"{stem}.body", root / f"{stem}.headers"


def _prepare_transfer_files(root: Path, process_index: int, count: int) -> None:
    for request_index in range(count):
        for path in _transfer_paths(root, process_index, request_index):
            if path.parent.resolve() != root.resolve():
                raise ValueError("TEMPORARY_FILE_BOUNDARY_INVALID")
            path.touch(mode=0o600)


def _validate_transfer_files(root: Path, process_index: int, count: int) -> None:
    expected_bodies: set[Path] = set()
    expected_headers: set[Path] = set()
    for request_index in range(count):
        body, header = _transfer_paths(root, process_index, request_index)
        expected_bodies.add(body)
        expected_headers.add(header)
    actual_bodies = set(root.glob("*.body"))
    actual_headers = set(root.glob("*.headers"))
    if actual_bodies != expected_bodies or actual_headers != expected_headers:
        raise ValueError("TRANSFER_FILE_PAIRING_INVALID")
    for body in actual_bodies:
        if body.stat().st_size > MAX_OBSERVER_RESPONSE_BODY_BYTES:
            raise ValueError("OBSERVER_RESPONSE_BODY_TOO_LARGE")


def curl_command(
    url: str,
    *,
    path_kind: str,
    requests: int = 1,
    max_time_seconds: int = 12,
    connection_mode: str = "REUSED",
    ip_protocol: str = "IPv4",
    output_dir: Path | None = None,
    process_index: int = 0,
) -> list[str]:
    if path_kind not in {"DIRECT", "PROXY"}:
        raise ValueError("path_kind must be DIRECT or PROXY")
    if requests < 1:
        raise ValueError("requests must be positive")
    if connection_mode not in {"FRESH", "REUSED"}:
        raise ValueError("connection_mode must be FRESH or REUSED")
    if connection_mode == "FRESH" and requests != 1:
        raise ValueError("FRESH mode requires one request per process")
    if ip_protocol not in {"IPv4", "IPv6"}:
        raise ValueError("ip_protocol must be IPv4 or IPv6")
    if output_dir is None:
        raise ValueError("output_dir is required")

    command = ["curl"]
    for request_index in range(requests):
        if request_index:
            command.append("--next")
        if path_kind == "DIRECT":
            command.extend(["--noproxy", "*"])
        command.append("--ipv4" if ip_protocol == "IPv4" else "--ipv6")
        if connection_mode == "FRESH":
            command.append("--no-keepalive")
        body_path, header_path = _transfer_paths(output_dir, process_index, request_index)
        command.extend(
            [
                "--silent",
                "--show-error",
                "--max-time",
                str(max_time_seconds),
                "--dump-header",
                str(header_path),
                "--output",
                str(body_path),
                "--write-out",
                _WRITE_OUT,
                url,
            ]
        )
    return command


def _derive_no_proxy(command: Sequence[str], environment: Mapping[str, str]) -> bool:
    command_has_bypass = any(
        command[index : index + 2] == ["--noproxy", "*"] for index in range(len(command) - 1)
    )
    proxy_names = {name.upper() for name in environment if name.upper() in _PROXY_ENVIRONMENT_NAMES}
    return command_has_bypass and proxy_names == {"NO_PROXY"} and environment.get("NO_PROXY") == "*"


def _parse_request_id(body_path: Path) -> str:
    if not body_path.is_file():
        raise ValueError("BODY_PAIRING_MISSING")
    size = body_path.stat().st_size
    if size > MAX_OBSERVER_RESPONSE_BODY_BYTES:
        raise ValueError("OBSERVER_RESPONSE_BODY_TOO_LARGE")
    try:
        payload = json.loads(body_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("RESPONSE_BODY_INVALID_JSON") from exc
    request_id = payload.get("request_id") if isinstance(payload, Mapping) else None
    if not isinstance(request_id, str) or not request_id:
        raise ValueError("REQUEST_ID_MISSING")
    if len(request_id.encode("utf-8")) > MAX_REQUEST_ID_BYTES or not _REQUEST_ID.fullmatch(
        request_id
    ):
        raise ValueError("REQUEST_ID_INVALID")
    return request_id


def _parse_server_timing(header_path: Path) -> dict[str, float]:
    if not header_path.is_file():
        raise ValueError("HEADER_PAIRING_MISSING")
    raw = header_path.read_bytes()
    if len(raw) > 64 * 1024:
        raise ValueError("HEADER_METADATA_TOO_LARGE")
    values: list[bytes] = []
    for line in raw.splitlines():
        if line.lower().startswith(b"server-timing:"):
            values.append(line.split(b":", 1)[1].strip())
    if len(values) != 1:
        raise ValueError("EVIDENCE_CORRELATION_INVALID")
    value = values[0]
    if len(value) > MAX_SERVER_TIMING_BYTES or any(byte < 32 or byte == 127 for byte in value):
        raise ValueError("EVIDENCE_CORRELATION_INVALID")
    try:
        rendered = value.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ValueError("EVIDENCE_CORRELATION_INVALID") from exc
    metrics: dict[str, float] = {}
    for item in rendered.split(","):
        parts = [part.strip() for part in item.split(";")]
        if len(parts) != 2 or not parts[0] or not parts[1].startswith("dur="):
            raise ValueError("EVIDENCE_CORRELATION_INVALID")
        name = parts[0]
        if name not in _SERVER_TIMING_METRICS or name in metrics:
            raise ValueError("EVIDENCE_CORRELATION_INVALID")
        try:
            duration = float(parts[1][4:])
        except ValueError as exc:
            raise ValueError("EVIDENCE_CORRELATION_INVALID") from exc
        if not math.isfinite(duration) or duration < 0:
            raise ValueError("EVIDENCE_CORRELATION_INVALID")
        metrics[name] = duration
    if not metrics:
        raise ValueError("EVIDENCE_CORRELATION_INVALID")
    return metrics


def _validate_ip_protocol(remote_ip: str, ip_protocol: str) -> None:
    try:
        actual = ipaddress.ip_address(remote_ip)
    except ValueError as exc:
        raise ValueError("REMOTE_IP_INVALID") from exc
    expected_version = 4 if ip_protocol == "IPv4" else 6
    if actual.version != expected_version:
        raise ValueError("IP_PROTOCOL_MISMATCH")


def validate_sample(sample: dict[str, Any], *, expected_remote_ip: str) -> None:
    status = int(sample.get("status", 0))
    curl_exit_code = int(sample.get("curl_exit_code", 0))
    common_required = {
        "schema",
        "collected_at_utc",
        "curl_process_started_at_utc",
        "curl_process_finished_at_utc",
        "path_kind",
        "no_proxy",
        "ip_protocol",
        "remote_ip",
        "connection_mode",
        "curl_process_index",
        "request_index_within_process",
        "num_connects",
        "connection_reused",
        "curl_exit_code",
        "http_version",
        "dns_seconds",
        "connect_seconds",
        "tls_seconds",
        "pretransfer_seconds",
        "starttransfer_seconds",
        "total_seconds",
        "response_bytes",
        "request_id",
        "server_timing",
        "correlation_status",
        "sample_valid_for_success_evidence",
        "sample_valid_for_failure_evidence",
    }
    if common_required.difference(sample):
        raise ValueError("SAMPLE_REQUIRED_FIELDS_MISSING")
    if sample.get("schema") != SAMPLE_SCHEMA:
        raise ValueError("SAMPLE_SCHEMA_INVALID")
    for timestamp_name in (
        "collected_at_utc",
        "curl_process_started_at_utc",
        "curl_process_finished_at_utc",
    ):
        try:
            parsed = datetime.fromisoformat(str(sample[timestamp_name]).replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("SAMPLE_TIMESTAMP_INVALID") from exc
        if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
            raise ValueError("SAMPLE_TIMESTAMP_INVALID")
    if (
        int(sample.get("curl_process_index", -1)) < 0
        or int(sample.get("request_index_within_process", -1)) < 0
    ):
        raise ValueError("SAMPLE_INDEX_INVALID")
    if int(sample.get("num_connects", -1)) < 0:
        raise ValueError("NUM_CONNECTS_INVALID")
    if int(sample.get("response_bytes", -1)) < 0:
        raise ValueError("RESPONSE_BYTES_INVALID")
    if sample.get("sample_valid_for_failure_evidence") is not True:
        raise ValueError("FAILURE_EVIDENCE_INVALID")
    if bool(sample.get("connection_reused")) != (int(sample["num_connects"]) == 0):
        raise ValueError("CONNECTION_REUSE_INVALID")
    if status == 200 and curl_exit_code == 0:
        if sample.get("correlation_status") != "CORRELATED":
            raise ValueError("EVIDENCE_CORRELATION_INVALID")
        if sample.get("sample_valid_for_success_evidence") is not True:
            raise ValueError("SUCCESS_SAMPLE_INVALID")
        server_timing = sample.get("server_timing")
        if not isinstance(server_timing, Mapping) or not server_timing:
            raise ValueError("EVIDENCE_CORRELATION_INVALID")
        for name, duration_value in server_timing.items():
            try:
                duration = float(duration_value)
            except (TypeError, ValueError) as exc:
                raise ValueError("EVIDENCE_CORRELATION_INVALID") from exc
            if name not in _SERVER_TIMING_METRICS or not math.isfinite(duration) or duration < 0:
                raise ValueError("EVIDENCE_CORRELATION_INVALID")
        request_id = sample.get("request_id")
        if (
            not isinstance(request_id, str)
            or len(request_id.encode("utf-8")) > MAX_REQUEST_ID_BYTES
            or not _REQUEST_ID.fullmatch(request_id)
        ):
            raise ValueError("REQUEST_ID_INVALID")
        _validate_ip_protocol(str(sample.get("remote_ip")), str(sample.get("ip_protocol")))
        if (
            sample.get("connection_mode") == "FRESH"
            and sample.get("connection_reused") is not False
        ):
            raise ValueError("FRESH_CONNECTION_REUSED")
        if int(sample.get("response_bytes", 0)) > MAX_OBSERVER_RESPONSE_BODY_BYTES:
            raise ValueError("OBSERVER_RESPONSE_BODY_TOO_LARGE")
    elif sample.get("sample_valid_for_success_evidence") is not False:
        raise ValueError("FAILURE_SAMPLE_MARKED_SUCCESS")
    if sample.get("path_kind") == "DIRECT":
        if sample.get("no_proxy") is not True:
            raise ValueError("DIRECT_NO_PROXY_UNPROVEN")
        remote_ip = str(sample.get("remote_ip") or "")
        if remote_ip:
            _validate_ip_protocol(remote_ip, str(sample.get("ip_protocol")))
        if remote_ip and remote_ip != expected_remote_ip:
            raise ValueError(
                f"DIRECT_REMOTE_IP_MISMATCH:{sample.get('remote_ip')}:{expected_remote_ip}"
            )


def summarize_samples(samples: list[dict[str, Any]]) -> dict[str, Any]:
    if not samples:
        raise ValueError("NO_SAMPLES")
    path_kinds = {str(sample.get("path_kind")) for sample in samples}
    if len(path_kinds) != 1:
        raise ValueError("MIXED_NETWORK_PATHS")
    totals = sorted(float(sample["total_seconds"]) for sample in samples)
    p95_index = max(0, min(len(totals) - 1, int(len(totals) * 0.95) - 1))
    return {
        "path_kind": next(iter(path_kinds)),
        "sample_count": len(samples),
        "http_status_counts": {
            str(status): sum(int(sample["status"]) == status for sample in samples)
            for status in sorted({int(sample["status"]) for sample in samples})
        },
        "p50_seconds": statistics.median(totals),
        "p95_seconds": totals[p95_index],
        "max_seconds": totals[-1],
        "max_response_bytes": max(int(sample["response_bytes"]) for sample in samples),
        "connection_reused_count": sum(bool(sample.get("connection_reused")) for sample in samples),
        "remote_ips": sorted(
            {str(sample["remote_ip"]) for sample in samples if sample.get("remote_ip")}
        ),
        "success_evidence_count": sum(
            sample.get("sample_valid_for_success_evidence") is True for sample in samples
        ),
        "failure_evidence_count": sum(
            sample.get("sample_valid_for_failure_evidence") is True for sample in samples
        ),
        "curl_error_count": sum(int(sample.get("curl_exit_code", 0)) != 0 for sample in samples),
    }


def validate_report(report: Mapping[str, Any]) -> None:
    if report.get("schema") != REPORT_SCHEMA:
        raise ValueError("REPORT_SCHEMA_INVALID")
    if report.get("collector_version") != COLLECTOR_VERSION:
        raise ValueError("COLLECTOR_VERSION_INVALID")
    samples = report.get("samples")
    if not isinstance(samples, list) or not samples:
        raise ValueError("REPORT_SAMPLES_INVALID")
    request_ids: list[str] = []
    for item in samples:
        if not isinstance(item, dict):
            raise ValueError("REPORT_SAMPLE_INVALID")
        validate_sample(item, expected_remote_ip=str(report.get("expected_remote_ip") or ""))
        if item.get("sample_valid_for_success_evidence") is True:
            request_ids.append(str(item["request_id"]))
    if len(request_ids) != len(set(request_ids)):
        raise ValueError("DUPLICATE_REQUEST_ID")
    summary = report.get("summary")
    if not isinstance(summary, Mapping) or int(summary.get("sample_count", -1)) != len(samples):
        raise ValueError("REPORT_SAMPLE_COUNT_MISMATCH")


def build_report(
    *,
    samples: list[dict[str, Any]],
    requested_url: str,
    expected_remote_ip: str,
    observer: Mapping[str, Any] | None = None,
    connection_mode: str = "REUSED",
    concurrency: int = 1,
) -> dict[str, Any]:
    endpoint = urlsplit(requested_url).path or "/"
    report = {
        "schema": REPORT_SCHEMA,
        "collector_version": COLLECTOR_VERSION,
        "endpoint": endpoint,
        "expected_remote_ip": expected_remote_ip,
        "observer": dict(observer or {"observer_id": "UNDECLARED"}),
        "connection_mode": connection_mode,
        "concurrency": concurrency,
        "summary": summarize_samples(samples),
        "samples": samples,
    }
    validate_report(report)
    return report


def _parse_write_out(stdout: str, expected_count: int) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        if line.strip():
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError("CURL_METADATA_INVALID") from exc
            if not isinstance(record, dict):
                raise ValueError("CURL_METADATA_INVALID")
            records.append(record)
    if len(records) != expected_count:
        raise ValueError(f"SAMPLE_COUNT_MISMATCH:{len(records)}:{expected_count}")
    return records


def collect_samples(
    url: str,
    *,
    path_kind: str,
    requests: int,
    expected_remote_ip: str,
    connection_mode: str = "REUSED",
    concurrency: int = 1,
    ip_protocol: str = "IPv4",
    max_time_seconds: int = 12,
) -> list[dict[str, Any]]:
    if concurrency < 1 or concurrency > requests:
        raise ValueError("concurrency must be between 1 and requests")
    if connection_mode == "FRESH":
        counts = [1] * requests
    else:
        base, remainder = divmod(requests, concurrency)
        counts = [base + (index < remainder) for index in range(concurrency)]

    def run_curl(item: tuple[int, int]) -> list[dict[str, Any]]:
        process_index, sample_count = item
        with tempfile.TemporaryDirectory(prefix="w2-public-edge-") as raw_root:
            root = Path(raw_root)
            root.chmod(0o700)
            _prepare_transfer_files(root, process_index, sample_count)
            environment = curl_environment(path_kind=path_kind)
            command = curl_command(
                url,
                path_kind=path_kind,
                requests=sample_count,
                max_time_seconds=max_time_seconds,
                connection_mode=connection_mode,
                ip_protocol=ip_protocol,
                output_dir=root,
                process_index=process_index,
            )
            process_started = utc_now()
            completed = subprocess.run(  # noqa: S603
                command,
                check=False,
                capture_output=True,
                env=environment,
                text=True,
            )
            process_finished = utc_now()
            records = _parse_write_out(completed.stdout, sample_count)
            _validate_transfer_files(root, process_index, sample_count)
            no_proxy = _derive_no_proxy(command, environment)
            samples: list[dict[str, Any]] = []
            for request_index, record in enumerate(records):
                body_path, header_path = _transfer_paths(root, process_index, request_index)
                status = int(record.get("status") or 0)
                curl_exit_code = int(record.get("curl_exit_code") or 0)
                is_success = status == 200 and curl_exit_code == 0
                request_id: str | None = None
                server_timing: dict[str, float] | None = None
                correlation_status = "EDGE_FAILURE_BEFORE_API"
                if is_success:
                    request_id = _parse_request_id(body_path)
                    server_timing = _parse_server_timing(header_path)
                    correlation_status = "CORRELATED"
                elif curl_exit_code == 0 and status not in {0, 502, 504}:
                    correlation_status = "HTTP_FAILURE"
                num_connects = int(record.get("num_connects") or 0)
                sample = {
                    "schema": SAMPLE_SCHEMA,
                    "collected_at_utc": utc_now(),
                    "curl_process_started_at_utc": process_started,
                    "curl_process_finished_at_utc": process_finished,
                    "path_kind": path_kind,
                    "no_proxy": no_proxy,
                    "ip_protocol": ip_protocol,
                    "remote_ip": str(record.get("remote_ip") or ""),
                    "connection_mode": connection_mode,
                    "curl_process_index": process_index,
                    "request_index_within_process": request_index,
                    "num_connects": num_connects,
                    "connection_reused": num_connects == 0,
                    "curl_exit_code": curl_exit_code,
                    "endpoint": urlsplit(url).path or "/",
                    "status": status,
                    "http_version": str(record.get("http_version") or "0"),
                    "dns_seconds": float(record.get("dns_seconds") or 0.0),
                    "connect_seconds": float(record.get("connect_seconds") or 0.0),
                    "tls_seconds": float(record.get("tls_seconds") or 0.0),
                    "pretransfer_seconds": float(record.get("pretransfer_seconds") or 0.0),
                    "starttransfer_seconds": float(record.get("starttransfer_seconds") or 0.0),
                    "total_seconds": float(record.get("total_seconds") or 0.0),
                    "response_bytes": int(record.get("response_bytes") or 0),
                    "request_id": request_id,
                    "server_timing": server_timing,
                    "correlation_status": correlation_status,
                    "sample_valid_for_success_evidence": is_success,
                    "sample_valid_for_failure_evidence": True,
                }
                validate_sample(sample, expected_remote_ip=expected_remote_ip)
                samples.append(sample)
            return samples

    indexed_counts = list(enumerate(counts))
    if concurrency == 1:
        rendered_samples = [run_curl(item) for item in indexed_counts]
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
            rendered_samples = list(pool.map(run_curl, indexed_counts))
    samples = [sample for group in rendered_samples for sample in group]
    if len(samples) != requests:
        raise ValueError(f"SAMPLE_COUNT_MISMATCH:{len(samples)}:{requests}")
    request_ids = [
        str(sample["request_id"])
        for sample in samples
        if sample.get("sample_valid_for_success_evidence") is True
    ]
    if len(request_ids) != len(set(request_ids)):
        raise ValueError("DUPLICATE_REQUEST_ID")
    return samples


def adjudicate_public_observers(
    observers: list[Mapping[str, Any]],
    *,
    target_route_status: str,
    minimum_independent_observers: int,
    server_diagnostics_passed: bool,
) -> dict[str, Any]:
    blocking = [item for item in observers if item.get("observer_kind") == "PUBLIC_BLOCKING"]
    independence_groups = {str(item.get("independence_group")) for item in blocking}
    passed_groups = {
        str(item.get("independence_group")) for item in blocking if item.get("passed") is True
    }
    failed_groups = {
        str(item.get("independence_group")) for item in blocking if item.get("passed") is not True
    }
    target_failed = any(
        item.get("target_route") is True and item.get("passed") is not True for item in blocking
    )
    if len(independence_groups) < minimum_independent_observers:
        classification = "OBSERVER_COVERAGE_INSUFFICIENT"
        is_blocking = True
    elif target_route_status == "DECLARED" and target_failed:
        classification = "TARGET_ROUTE_BLOCKED"
        is_blocking = True
    elif len(failed_groups) >= 2:
        classification = "GLOBAL_PUBLIC_EDGE_BLOCKED"
        is_blocking = True
    elif not failed_groups and len(passed_groups) >= minimum_independent_observers:
        classification = "ALL_BLOCKING_OBSERVERS_PASS"
        is_blocking = False
    elif (
        server_diagnostics_passed
        and len(passed_groups) >= minimum_independent_observers
        and len(failed_groups) == 1
        and not target_failed
    ):
        classification = "ROUTE_SPECIFIC_WARNING"
        is_blocking = False
    else:
        classification = "OBSERVER_COVERAGE_INSUFFICIENT"
        is_blocking = True
    return {
        "schema": "w2.public_edge_adjudication.v1",
        "classification": classification,
        "blocking": is_blocking,
        "target_route_status": target_route_status,
        "independent_observer_count": len(independence_groups),
        "passed_independence_groups": sorted(passed_groups),
        "failed_independence_groups": sorted(failed_groups),
        "server_diagnostics_passed": server_diagnostics_passed,
    }


def evaluate_observer_evidence(
    *,
    warm: Mapping[str, Any],
    next_page: Mapping[str, Any],
    cold: Mapping[str, Any],
    thresholds: Mapping[str, Any],
) -> dict[str, Any]:
    failed: list[str] = []
    if float(warm["p95_seconds"]) > float(thresholds["warm_keepalive_p95_seconds"]):
        failed.append("WARM_KEEPALIVE_P95")
    if float(next_page["p95_seconds"]) > float(thresholds["next_page_p95_seconds"]):
        failed.append("NEXT_PAGE_P95")
    if float(cold["p50_seconds"]) > float(thresholds["cold_p50_seconds"]):
        failed.append("COLD_P50")
    if float(cold["p95_seconds"]) > float(thresholds["cold_p95_seconds"]):
        failed.append("COLD_P95")
    if float(cold["max_seconds"]) >= float(thresholds["cold_max_seconds_exclusive"]):
        failed.append("COLD_MAX")
    error_count = sum(
        int(count)
        for summary in (warm, next_page, cold)
        for status, count in summary.get("http_status_counts", {}).items()
        if str(status) != "200"
    )
    error_count += sum(
        int(summary.get("curl_error_count", 0)) for summary in (warm, next_page, cold)
    )
    if error_count > int(thresholds["max_502_504_timeout_count"]):
        failed.append("HTTP_NON_200")
    return {
        "schema": "w2.public_edge_observer_evaluation.v1",
        "passed": not failed,
        "failed_checks": failed,
        "error_count": error_count,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure one sanitized W2 public edge path")
    parser.add_argument("--validate-report", type=Path)
    parser.add_argument("--url")
    parser.add_argument("--expected-remote-ip")
    parser.add_argument("--path-kind", choices=("DIRECT", "PROXY"))
    parser.add_argument("--requests", type=int, default=20)
    parser.add_argument("--connection-mode", choices=("FRESH", "REUSED"), default="REUSED")
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--observer-id", default="UNDECLARED")
    parser.add_argument("--observer-environment", default="UNDECLARED")
    parser.add_argument("--network-provider", default="UNDECLARED")
    parser.add_argument("--target-user-region", action="store_true")
    parser.add_argument("--ip-protocol", choices=("IPv4", "IPv6"), default="IPv4")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.validate_report:
        validate_report(json.loads(args.validate_report.read_text(encoding="utf-8")))
        print(f"public edge evidence V2 PASS {args.validate_report}")
        return 0
    if not args.url or not args.expected_remote_ip or not args.path_kind:
        parser.error("--url, --expected-remote-ip and --path-kind are required")
    samples = collect_samples(
        args.url,
        path_kind=args.path_kind,
        requests=args.requests,
        expected_remote_ip=args.expected_remote_ip,
        connection_mode=args.connection_mode,
        concurrency=args.concurrency,
        ip_protocol=args.ip_protocol,
    )
    report = build_report(
        samples=samples,
        requested_url=args.url,
        expected_remote_ip=args.expected_remote_ip,
        observer={
            "observer_id": args.observer_id,
            "environment": args.observer_environment,
            "network_provider": args.network_provider,
            "target_user_region": args.target_user_region,
            "ip_protocol": args.ip_protocol,
            "proxy_used": args.path_kind == "PROXY",
        },
        connection_mode=args.connection_mode,
        concurrency=args.concurrency,
    )
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        print(f"public edge latency check failed: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
