#!/usr/bin/env python3
from __future__ import annotations

import fnmatch
import subprocess

FORBIDDEN_PATTERNS = (
    "reports/**",
    "runtime/**",
    "dist/**",
    "**/dist/**",
)


def _tracked_files() -> list[str]:
    completed = subprocess.run(
        ["git", "ls-files"],
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in completed.stdout.splitlines() if line]


def _is_forbidden(path: str) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in FORBIDDEN_PATTERNS)


def find_tracked_outputs(paths: list[str] | None = None) -> list[str]:
    tracked = _tracked_files() if paths is None else paths
    return sorted(path for path in tracked if _is_forbidden(path))


def main() -> int:
    violations = find_tracked_outputs()
    if violations:
        print("Tracked runtime/build outputs are not allowed:")
        for path in violations:
            print(f"- {path}")
        return 1
    print("check_tracked_outputs PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
