from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_c9_predeploy_required_event_contract_is_not_weakened() -> None:
    result = subprocess.run(
        ["bash", "scripts/check_c9_predeploy_event_contract.sh"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "c9_predeploy_event_contract PASS" in result.stdout
