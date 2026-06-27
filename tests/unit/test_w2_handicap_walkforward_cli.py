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

    payload = json.loads(result.stdout)

    assert payload["samples"] == 0
    assert payload["n_min"] == 200
    assert payload["beats_market"] is False
    assert payload["reason"] == "INSUFFICIENT_VALIDATED_SAMPLES"
    assert payload["report_type"] == "S2_VALIDATION_READINESS_DRY_RUN"
    assert payload["gate"]["beats_market"] is False
    assert payload["gate"]["gate_checks"] == {
        "sample_minimum": False,
        "devig_market_advantage": False,
        "time_split": False,
        "holdout_replication": False,
        "forward_shadow": False,
    }
    assert payload["settlement_policy"] == {
        "market_snapshot": "AS_OF_LOCKED_MARKET_SNAPSHOT_REQUIRED",
        "devig_method": "REQUIRED_FOR_MARKET_BASELINE",
        "asian_handicap_outcomes": [
            "WIN",
            "HALF_WIN",
            "PUSH",
            "HALF_LOSS",
            "LOSS",
            "VOID",
        ],
        "push_counts_as_win": False,
        "void_included_in_sample": False,
    }
