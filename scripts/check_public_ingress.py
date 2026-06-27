from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERIFY_RELEASE_SYNC = ROOT / "scripts" / "verify_release_sync.py"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check W2 public ingress via the release sync verifier.",
    )
    parser.add_argument("--base-url")
    parser.add_argument("--public-url", dest="base_url")
    parser.add_argument("--expected-sha")
    parser.add_argument("--min-fixtures", type=int, default=0)
    parser.add_argument("--allow-empty-data", nargs="?", const="true", default=None)
    parser.add_argument("--require-future-fixtures-visible", action="store_true")
    parser.add_argument("--require-next-available-date-if-empty", action="store_true")
    parser.add_argument(
        "--timeout",
        type=int,
        default=15,
        help="Accepted for caller compatibility; verify_release_sync owns request timeouts.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not args.base_url:
        parser.error("--base-url or --public-url is required")

    command = [
        sys.executable,
        str(VERIFY_RELEASE_SYNC),
        "--base-url",
        args.base_url,
        "--min-fixtures",
        str(args.min_fixtures),
    ]
    if args.expected_sha:
        command.extend(["--expected-sha", args.expected_sha])
    if args.allow_empty_data is not None:
        command.extend(["--allow-empty-data", args.allow_empty_data])
    if args.require_future_fixtures_visible:
        command.append("--require-future-fixtures-visible")
    if args.require_next_available_date_if_empty:
        command.append("--require-next-available-date-if-empty")

    completed = subprocess.run(command, cwd=ROOT, check=False)  # noqa: S603
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
