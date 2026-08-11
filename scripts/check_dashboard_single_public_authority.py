#!/usr/bin/env python3
"""Fail when retired Dashboard public authorities re-enter current code or contracts."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN_ROOTS = (
    "src/w2/dashboard",
    "src/w2/api/schemas.py",
    "apps/web/src",
    "apps/web/e2e",
    "tests/contract",
    "tests/unit",
    "examples",
    "docs/ui/dashboard-v4.1",
    "DASHBOARD_DATA_CONTRACT.md",
)
TEXT_SUFFIXES = {".css", ".json", ".md", ".py", ".ts", ".tsx"}
RETIRED = (
    "DashboardDayMode",
    "day_mode",
    "default_focus_type",
    "default_focus_fixture_id",
    "DashboardFocusType",
    "public_system_health",
    "DAY_MODE_LABELS",
    "TEAM_TRANSLATIONS",
    "translateTeam",
    "v41-global--blocked",
    "v41-global--calm",
    "v41-global--empty",
    "v41-pill--mode-",
)


def files() -> list[Path]:
    output: list[Path] = []
    for raw in SCAN_ROOTS:
        path = ROOT / raw
        if path.is_file():
            output.append(path)
        elif path.is_dir():
            output.extend(
                item
                for item in path.rglob("*")
                if item.is_file()
                and item.suffix in TEXT_SUFFIXES
                and "docs/archive" not in item.as_posix()
            )
    return sorted(set(output))


def main() -> int:
    failures: list[str] = []
    for path in files():
        relative = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        for retired_identifier in RETIRED:
            if retired_identifier in text:
                failures.append(
                    f"{relative}: retired public authority {retired_identifier!r}"
                )
        if relative.startswith("apps/web/") or relative.startswith("src/w2/"):
            if re.search(r'collection[_-]incident', text, re.IGNORECASE) and (
                "NOT_YET_DUE" in text and relative.endswith("publicPresentation.ts")
            ):
                failures.append(
                    f"{relative}: normal waiting is coupled to collection-incident presentation"
                )
        if "date_strip" in relative and "display" + "_state" in text:
            failures.append(f"{relative}: date-strip has a second presentation state")

    presentation_files = [
        path
        for path in (ROOT / "apps/web/src").rglob("*.ts*")
        if re.search(r"export function publicPresentation\s*\(", path.read_text())
    ]
    if [path.relative_to(ROOT).as_posix() for path in presentation_files] != [
        "apps/web/src/lib/publicPresentation.ts"
    ]:
        failures.append("exactly one PublicPresentation converter is required")

    if failures:
        print("SC20_SINGLE_PUBLIC_AUTHORITY=FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("SC20_SINGLE_PUBLIC_AUTHORITY=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
