#!/usr/bin/env python3
from __future__ import annotations

import fnmatch
import re
import subprocess

FORBIDDEN_PATTERNS = (
    "reports/**",
    "runtime/**",
    "dist/**",
    "**/dist/**",
)
SYSTEM_TRUTH_DIRECTORY = "docs/audits/system_truth/"
HUMAN_MAINTAINED_SYSTEM_TRUTH_FILES = frozenset(
    {
        f"{SYSTEM_TRUTH_DIRECTORY}W2_CONSOLIDATION_IMPLEMENTATION_REPORT_V1.json",
        f"{SYSTEM_TRUTH_DIRECTORY}W2_CONSOLIDATION_IMPLEMENTATION_REPORT_V1.md",
        f"{SYSTEM_TRUTH_DIRECTORY}W2_SIMPLIFICATION_PLAN_V1.md",
    }
)
GENERATED_SYSTEM_TRUTH_MARKDOWN = re.compile(
    rf"^{re.escape(SYSTEM_TRUTH_DIRECTORY)}W2_.+_V\d+\.md$"
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
    if any(fnmatch.fnmatch(path, pattern) for pattern in FORBIDDEN_PATTERNS):
        return True
    if path in HUMAN_MAINTAINED_SYSTEM_TRUTH_FILES:
        return False
    if path.startswith(SYSTEM_TRUTH_DIRECTORY) and path.endswith(".json"):
        return True
    return GENERATED_SYSTEM_TRUTH_MARKDOWN.fullmatch(path) is not None


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
