#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_CURRENT = Path("/opt/w2/current")
DEFAULT_RUNTIME = Path("/opt/w2/shared/runtime/stage7i")


def iso_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def read_revision(current: Path) -> str | None:
    path = current / "DEPLOYMENT_REVISION"
    if not path.exists():
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


def sample(current: Path, expected_revision: str | None, expected_source: str) -> dict[str, Any]:
    actual = read_revision(current)
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
        "revision_ok": reason is None,
        "invalidation_reason": reason,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stage7I observation sampler with dynamic revision."
    )
    parser.add_argument("--expected-revision")
    parser.add_argument("--current", type=Path, default=DEFAULT_CURRENT)
    parser.add_argument("--runtime", type=Path, default=DEFAULT_RUNTIME)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    expected, source = resolve_expected_revision(
        explicit=args.expected_revision,
        current=args.current,
    )
    args.runtime.mkdir(parents=True, exist_ok=True)
    record = sample(args.current, expected, source)
    record["observer_started_at_utc"] = iso_now()
    path = args.runtime / "observations.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    if not args.once:
        while True:
            time.sleep(300)
            with path.open("a", encoding="utf-8") as handle:
                payload = sample(args.current, expected, source)
                handle.write(json.dumps(payload, sort_keys=True) + "\n")
    print(json.dumps({"status": "PASS", "expected_revision_source": source}, sort_keys=True))


if __name__ == "__main__":
    main()
