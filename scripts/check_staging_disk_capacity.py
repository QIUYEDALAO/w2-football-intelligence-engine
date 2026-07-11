from __future__ import annotations

import argparse
import shutil
from pathlib import Path

WARN_PERCENT = 80
BLOCK_PERCENT = 90


def capacity_status(used_percent: int) -> tuple[str, int]:
    if used_percent >= BLOCK_PERCENT:
        return "BLOCKED", 2
    if used_percent >= WARN_PERCENT:
        return "WARN", 0
    return "PASS", 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Check W2 staging build disk capacity")
    parser.add_argument("--path", type=Path, default=Path("/"))
    parser.add_argument("--used-percent", type=int)
    args = parser.parse_args()
    if args.used_percent is None:
        usage = shutil.disk_usage(args.path)
        used_percent = round(usage.used * 100 / usage.total)
    else:
        used_percent = args.used_percent
    status, exit_code = capacity_status(used_percent)
    print(
        f"staging_disk_capacity={status} used_percent={used_percent} "
        f"warn_percent={WARN_PERCENT} block_percent={BLOCK_PERCENT}"
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
