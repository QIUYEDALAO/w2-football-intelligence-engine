from __future__ import annotations

import argparse
import json
import os
import time
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

DEFAULT_CURRENT = Path("/opt/w2/current")
DEFAULT_RUNTIME_ROOT = Path(os.environ.get("W2_STAGE7I_RUNTIME_ROOT", "runtime/stage7i"))


def iso_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def read_revision(current: Path) -> str | None:
    path = current / "DEPLOYMENT_REVISION"
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8").strip()


def read_revision_file(path: Path | None) -> str | None:
    if path is None or not path.exists() or not path.is_file():
        return None
    return path.read_text(encoding="utf-8").strip()


def resolve_expected_revision(
    *,
    explicit: str | None,
    current: Path,
    environ: dict[str, str] | None = None,
) -> tuple[str | None, str]:
    env = environ if environ is not None else os.environ
    if explicit:
        return explicit, "CLI"
    if env.get("W2_STAGE7I_EXPECTED_REVISION"):
        return env["W2_STAGE7I_EXPECTED_REVISION"], "ENV"
    revision = read_revision(current)
    return revision, "CURRENT_DEPLOYMENT_REVISION"


def resolve_actual_revision(
    *,
    current: Path,
    actual_revision_file: Path | None,
    environ: dict[str, str] | None = None,
) -> tuple[str | None, str]:
    env = environ if environ is not None else os.environ
    if env.get("W2_DEPLOYMENT_REVISION"):
        return env["W2_DEPLOYMENT_REVISION"], "ENV"
    from_file = read_revision_file(actual_revision_file)
    if from_file:
        return from_file, "ACTUAL_REVISION_FILE"
    return read_revision(current), "CURRENT_DEPLOYMENT_REVISION"


def sample(
    current: Path,
    expected_revision: str | None,
    expected_source: str,
    *,
    actual_revision_file: Path | None = None,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    actual, actual_source = resolve_actual_revision(
        current=current,
        actual_revision_file=actual_revision_file,
        environ=environ,
    )
    reason = None
    if expected_revision is None:
        reason = "EXPECTED_REVISION_UNAVAILABLE"
    elif actual != expected_revision:
        reason = "REVISION_MISMATCH"
    return {
        "timestamp_utc": iso_now(),
        "expected_revision": expected_revision,
        "expected_revision_source": expected_source,
        "actual_revision": actual,
        "actual_revision_source": actual_source,
        "revision_ok": reason is None,
        "invalidation_reason": reason,
        "blocker": reason,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Stage7I staging observation sampler.")
    parser.add_argument("--expected-revision")
    parser.add_argument("--current", type=Path, default=DEFAULT_CURRENT)
    parser.add_argument("--actual-revision-file", type=Path)
    parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME_ROOT)
    parser.add_argument("--duration-hours", type=float, default=24.0)
    parser.add_argument("--sample-interval-seconds", type=float, default=300.0)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def _append(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.duration_hours <= 0:
        parser.error("duration-hours must be positive")
    if args.sample_interval_seconds <= 0:
        parser.error("sample-interval-seconds must be positive")

    expected, source = resolve_expected_revision(
        explicit=args.expected_revision,
        current=args.current,
    )
    observations = args.runtime_root / "observations.jsonl"
    started = datetime.now(UTC)
    first = sample(
        args.current,
        expected,
        source,
        actual_revision_file=args.actual_revision_file,
    )
    first["observer_started_at_utc"] = started.isoformat().replace("+00:00", "Z")
    _append(observations, first)
    if not args.once:
        deadline = started + timedelta(hours=args.duration_hours)
        while datetime.now(UTC) < deadline:
            time.sleep(args.sample_interval_seconds)
            _append(
                observations,
                sample(
                    args.current,
                    expected,
                    source,
                    actual_revision_file=args.actual_revision_file,
                ),
            )
        (args.runtime_root / "COMPLETED").write_text(iso_now() + "\n", encoding="utf-8")

    summary = {
        "status": "PASS" if first["revision_ok"] else "BLOCKED",
        "expected_revision_source": source,
        "runtime_root": str(args.runtime_root),
        "observations": str(observations),
        "blocker": first["blocker"],
    }
    print(json.dumps(summary, sort_keys=True))
    return 0 if first["revision_ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
