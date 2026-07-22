from __future__ import annotations

import argparse
import json
import os
import tempfile
import urllib.request
from pathlib import Path
from typing import Any, cast

from w2.operations.runtime_evidence import (
    capture_runtime_evidence,
    validate_loopback_metrics_url,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Capture loopback-only W2 runtime evidence; --live is unsupported."
    )
    parser.add_argument("--compose-file", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, action="append", default=[])
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--scheduler-expected", choices=("running", "stopped"), required=True)
    parser.add_argument("--metrics-url", default="http://127.0.0.1:18000/metrics")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    if not isinstance(baseline, dict):
        raise ValueError("baseline must be a JSON object")
    compose_prefix = ["docker", "compose"]
    for env_file in args.env_file:
        compose_prefix.extend(["--env-file", str(env_file)])
    compose_prefix.extend(["-f", str(args.compose_file)])
    request = urllib.request.Request(  # noqa: S310 - loopback-only guard above
        validate_loopback_metrics_url(args.metrics_url),
        headers={"Accept": "text/plain"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
        metrics_text = response.read().decode("utf-8")
    payload = capture_runtime_evidence(
        compose_prefix=compose_prefix,
        services=("api", "worker", "scheduler", "web"),
        baseline=cast(dict[str, Any], baseline),
        scheduler_expected=args.scheduler_expected,
        metrics_text=metrics_text,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=args.output.parent, delete=False
    ) as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        temporary = Path(stream.name)
    os.replace(temporary, args.output)
    return 0 if payload["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
