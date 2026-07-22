#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/ui/dashboard-v2/DASHBOARD_V2_VISUAL_BASELINE_MANIFEST.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    failures: list[str] = []
    for relative, expected in payload["protected_files"].items():
        path = ROOT / relative
        if not path.exists():
            failures.append(f"missing: {relative}")
            continue
        actual = sha256(path)
        if actual != expected["sha256"]:
            failures.append(f"changed: {relative} expected={expected['sha256']} actual={actual}")
    if failures:
        print("Dashboard V2 protected baseline FAILED")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("Dashboard V2 protected baseline PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
