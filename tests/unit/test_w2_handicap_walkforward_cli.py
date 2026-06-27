from __future__ import annotations

import json
import subprocess
import sys


def test_handicap_walkforward_dry_run_outputs_wave1_json() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/run_w2_handicap_walkforward.py", "--dry-run"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(result.stdout) == {
        "samples": 0,
        "n_min": 200,
        "beats_market": False,
        "reason": "INSUFFICIENT_VALIDATED_SAMPLES",
    }
