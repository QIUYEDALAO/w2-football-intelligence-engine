#!/usr/bin/env python3
from __future__ import annotations

import subprocess

COMMANDS = [
    ["uv", "run", "python", "scripts/check_w2_stage1_contracts.py"],
    ["uv", "run", "python", "scripts/check_w2_stage3_data_model.py"],
    ["uv", "run", "python", "scripts/check_w2_stage4_ingestion.py"],
    ["uv", "run", "python", "scripts/check_w2_stage4b_live_smoke.py"],
    ["uv", "run", "python", "scripts/check_w2_stage5_asof.py"],
    ["uv", "run", "python", "scripts/check_w2_stage5b.py"],
    ["uv", "run", "python", "scripts/check_w2_stage6_market.py"],
    ["uv", "run", "python", "scripts/check_w2_stage7_models.py"],
    ["uv", "run", "python", "scripts/check_w2_stage8_replay.py"],
    ["uv", "run", "python", "scripts/check_w2_stage7b.py"],
    ["uv", "run", "python", "scripts/check_w2_stage7c.py"],
    ["uv", "run", "python", "scripts/check_w2_stage7d.py"],
    ["uv", "run", "python", "scripts/check_w2_stage7e.py"],
    ["uv", "run", "python", "scripts/check_w2_stage10a.py"],
    ["uv", "run", "python", "scripts/check_w2_stage11a.py"],
    ["uv", "run", "python", "scripts/check_w2_stage12a.py"],
    ["uv", "run", "python", "scripts/check_w2_stage13a.py"],
    ["uv", "run", "python", "scripts/check_w2_stage14a.py"],
    ["uv", "run", "python", "scripts/check_w2_stage15a.py"],
    ["uv", "run", "ruff", "check", "."],
    ["uv", "run", "mypy", "src", "apps"],
    ["uv", "run", "pytest", "-q"],
]


def main() -> int:
    for command in COMMANDS:
        print("+", " ".join(command))
        completed = subprocess.run(command, check=False)
        if completed.returncode != 0:
            return completed.returncode
    print("W2 all-stage verify PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
