from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

_WRITE_OUT = (
    '{"status":"%{http_code}","remote_ip":"%{remote_ip}",'
    '"http_version":"%{http_version}","dns_seconds":%{time_namelookup},'
    '"connect_seconds":%{time_connect},"tls_seconds":%{time_appconnect},'
    '"starttransfer_seconds":%{time_starttransfer},"total_seconds":%{time_total},'
    '"response_bytes":%{size_download},"num_connects":%{num_connects}}\n'
)

_PROXY_ENVIRONMENT_NAMES = {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"}


def curl_environment(
    *, path_kind: str, source: Mapping[str, str] | None = None
) -> dict[str, str]:
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


def curl_command(
    url: str,
    *,
    path_kind: str,
    requests: int = 1,
    max_time_seconds: int = 12,
) -> list[str]:
    if path_kind not in {"DIRECT", "PROXY"}:
        raise ValueError("path_kind must be DIRECT or PROXY")
    if requests < 1:
        raise ValueError("requests must be positive")
    command = ["curl"]
    if path_kind == "DIRECT":
        command.extend(["--noproxy", "*"])
    command.extend(
        [
            "--silent",
            "--show-error",
            "--max-time",
            str(max_time_seconds),
            "--write-out",
            _WRITE_OUT,
        ]
    )
    for _ in range(requests):
        command.extend(["--output", "/dev/null", url])
    return command


def validate_sample(sample: dict[str, Any], *, expected_remote_ip: str) -> None:
    if sample.get("path_kind") == "DIRECT" and sample.get("remote_ip") != expected_remote_ip:
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
        "connection_reused_count": sum(
            bool(sample.get("connection_reused")) for sample in samples
        ),
        "remote_ips": sorted({str(sample["remote_ip"]) for sample in samples}),
    }


def build_report(
    *,
    samples: list[dict[str, Any]],
    requested_url: str,
    expected_remote_ip: str,
) -> dict[str, Any]:
    for sample in samples:
        validate_sample(sample, expected_remote_ip=expected_remote_ip)
    endpoint = urlsplit(requested_url).path or "/"
    return {
        "schema": "w2.public_edge_latency.v1",
        "endpoint": endpoint,
        "expected_remote_ip": expected_remote_ip,
        "summary": summarize_samples(samples),
        "samples": samples,
    }


def collect_samples(
    url: str,
    *,
    path_kind: str,
    requests: int,
    expected_remote_ip: str,
) -> list[dict[str, Any]]:
    completed = subprocess.run(  # noqa: S603
        curl_command(url, path_kind=path_kind, requests=requests),
        check=True,
        capture_output=True,
        env=curl_environment(path_kind=path_kind),
        text=True,
    )
    samples: list[dict[str, Any]] = []
    for line in completed.stdout.splitlines():
        if not line.strip():
            continue
        sample = json.loads(line)
        sample["status"] = int(sample["status"])
        sample["path_kind"] = path_kind
        sample["endpoint"] = urlsplit(url).path or "/"
        sample["connection_reused"] = int(sample.pop("num_connects", 1)) == 0
        validate_sample(sample, expected_remote_ip=expected_remote_ip)
        samples.append(sample)
    if len(samples) != requests:
        raise ValueError(f"SAMPLE_COUNT_MISMATCH:{len(samples)}:{requests}")
    return samples


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure one sanitized W2 public edge path")
    parser.add_argument("--url", required=True)
    parser.add_argument("--expected-remote-ip", required=True)
    parser.add_argument("--path-kind", choices=("DIRECT", "PROXY"), required=True)
    parser.add_argument("--requests", type=int, default=20)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    samples = collect_samples(
        args.url,
        path_kind=args.path_kind,
        requests=args.requests,
        expected_remote_ip=args.expected_remote_ip,
    )
    report = build_report(
        samples=samples,
        requested_url=args.url,
        expected_remote_ip=args.expected_remote_ip,
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
