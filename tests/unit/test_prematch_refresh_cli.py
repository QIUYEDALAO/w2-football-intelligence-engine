from __future__ import annotations

import json
import subprocess


def test_prematch_refresh_defaults_to_no_provider_call_plan() -> None:
    completed = subprocess.run(
        [
            "python3",
            "scripts/run_prematch_refresh.py",
            "--competition-id",
            "world_cup_2026",
            "--season",
            "2026",
            "--now-utc",
            "2026-06-27T00:08:25Z",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)
    assert payload["status"] == "DRY_RUN"
    assert payload["would_execute"] is False
    assert payload["provider_calls"] is False
    assert payload["task_key"] == "future-refresh:world_cup_2026:2026:20260627T000000Z"
    assert payload["candidate"] is False
    assert payload["formal_recommendation"] is False
    assert payload["beats_market"] is False
