#!/usr/bin/env python3
"""Deterministic fail-closed pytest file sharding for release candidates."""

from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DURATIONS = ROOT / "ci/pytest_durations.v1.json"
DEDICATED = {
    "tests/contract/test_compose_env_dedup.py",
    "tests/contract/test_compose_staging_ports.py",
    "tests/contract/test_predeploy_e2e_regressions.py",
    "tests/contract/test_runtime_packaging.py",
    "tests/integration/test_future_refresh_e2e_smoke.py",
    "tests/integration/test_future_refresh_staging_parity.py",
    "tests/integration/test_migrations.py",
    "tests/unit/test_analysis_card_api.py",
}
DURATION_RE = re.compile(r"^\s*(?P<seconds>\d+(?:\.\d+)?)s\s+\w+\s+(?P<node>tests/[^: ]+)")


def collected_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "tests/**/test_*.py"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return sorted(line for line in result.stdout.splitlines() if line)


def candidates(kind: str) -> list[str]:
    files = [path for path in collected_files() if path not in DEDICATED]
    if kind == "integration":
        return [path for path in files if path.startswith("tests/integration/")]
    if kind == "unit-contract":
        return [path for path in files if not path.startswith("tests/integration/")]
    raise ValueError(f"unknown shard kind: {kind}")


def load_durations(path: Path = DEFAULT_DURATIONS) -> tuple[dict[str, float], float]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "w2.pytest-durations.v1":
        raise ValueError("unsupported pytest duration schema")
    values = payload.get("files")
    if not isinstance(values, dict) or not values:
        raise ValueError("pytest duration file map is empty")
    durations = {str(key): float(value) for key, value in values.items()}
    if any(value <= 0 for value in durations.values()):
        raise ValueError("pytest durations must be positive")
    default = float(payload.get("default_seconds") or statistics.median(durations.values()))
    if default <= 0:
        raise ValueError("default pytest duration must be positive")
    return durations, default


def lpt_plan(
    files: list[str], durations: dict[str, float], default: float, count: int
) -> list[list[str]]:
    if count < 1:
        raise ValueError("shard count must be positive")
    shards: list[list[str]] = [[] for _ in range(count)]
    totals = [0.0] * count
    for path in sorted(files, key=lambda item: (-durations.get(item, default), item)):
        index = min(range(count), key=lambda item: (totals[item], item))
        shards[index].append(path)
        totals[index] += durations.get(path, default)
    return [sorted(shard) for shard in shards]


def plan(kind: str, count: int, durations_path: Path = DEFAULT_DURATIONS) -> list[list[str]]:
    durations, default = load_durations(durations_path)
    shards = lpt_plan(candidates(kind), durations, default, count)
    assigned = [path for shard in shards for path in shard]
    expected = candidates(kind)
    if sorted(assigned) != expected or len(assigned) != len(set(assigned)):
        raise RuntimeError(f"{kind} shard plan is incomplete or duplicated")
    return shards


def record(source: Path, output: Path, source_sha: str) -> None:
    totals: dict[str, float] = {}
    for line in source.read_text(encoding="utf-8").splitlines():
        match = DURATION_RE.match(line)
        if match:
            path = match.group("node")
            totals[path] = totals.get(path, 0.0) + float(match.group("seconds"))
    files = collected_files()
    measured = [value for path, value in totals.items() if path in files and value > 0]
    if not measured:
        raise RuntimeError("no pytest durations parsed")
    default = statistics.median(measured)
    normalized = {path: round(max(totals.get(path, default), 0.001), 3) for path in files}
    payload: dict[str, Any] = {
        "schema_version": "w2.pytest-durations.v1",
        "generated_from_sha": source_sha,
        "default_seconds": round(default, 3),
        "files": normalized,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    show = subparsers.add_parser("show")
    show.add_argument("--kind", choices=("unit-contract", "integration"), required=True)
    show.add_argument("--count", type=int, required=True)
    show.add_argument("--index", type=int, required=True)
    show.add_argument("--durations", type=Path, default=DEFAULT_DURATIONS)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--durations", type=Path, default=DEFAULT_DURATIONS)
    record_parser = subparsers.add_parser("record")
    record_parser.add_argument("--input", type=Path, required=True)
    record_parser.add_argument("--output", type=Path, required=True)
    record_parser.add_argument("--source-sha", required=True)
    args = parser.parse_args()
    if args.command == "show":
        shards = plan(args.kind, args.count, args.durations)
        if not 0 <= args.index < args.count:
            parser.error("--index is outside shard count")
        print(" ".join(shards[args.index]))
    elif args.command == "verify":
        plan("unit-contract", 4, args.durations)
        plan("integration", 2, args.durations)
    else:
        record(args.input, args.output, args.source_sha)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
