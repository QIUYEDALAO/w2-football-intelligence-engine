from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from w2.operations.runtime_evidence import (
    capture_runtime_evidence,
    parse_checkpoint_lag,
    validate_loopback_metrics_url,
)


def fake_runner_factory(*, restart_api: int = 0, oom_worker: bool = False):  # type: ignore[no-untyped-def]
    ids = {
        "api": "a" * 12,
        "worker": "b" * 12,
        "scheduler": "c" * 12,
        "web": "d" * 12,
    }

    def runner(command):  # type: ignore[no-untyped-def]
        if "ps" in command:
            return ids[command[-1]]
        if command[:2] == ["docker", "inspect"]:
            container_id = command[-1]
            service = next(name for name, value in ids.items() if value == container_id)
            return json.dumps(
                [
                    {
                        "RestartCount": restart_api if service == "api" else 0,
                        "State": {
                            "Status": "running",
                            "Health": {"Status": "healthy"},
                            "OOMKilled": oom_worker and service == "worker",
                            "ExitCode": 0,
                        },
                    }
                ]
            )
        if command[:2] == ["docker", "exec"]:
            return "1048576"
        if "redis-cli" in command:
            return "0"
        raise AssertionError(command)

    return runner


def baseline() -> dict[str, object]:
    return {
        "queue_length": 0,
        "services": {
            name: {"restart_count": 0}
            for name in ("api", "worker", "scheduler", "web")
        },
    }


def test_runtime_evidence_passes_only_unchanged_healthy_runtime() -> None:
    payload = capture_runtime_evidence(
        compose_prefix=("docker", "compose", "-f", "compose.yml"),
        services=("api", "worker", "scheduler", "web"),
        baseline=baseline(),
        scheduler_expected="running",
        metrics_text="w2_checkpoint_lag_seconds 42\n",
        runner=fake_runner_factory(),
        generated_at=datetime(2026, 7, 18, tzinfo=UTC),
    )

    assert payload["result"] == "PASS"
    assert payload["queue_length"] == 0
    assert payload["checkpoint_lag_seconds"] == 42
    assert all(item["rss_bytes"] == 1048576 for item in payload["services"].values())


def test_runtime_evidence_fails_on_restart_oom_and_missing_metric() -> None:
    payload = capture_runtime_evidence(
        compose_prefix=("docker", "compose"),
        services=("api", "worker", "scheduler", "web"),
        baseline=baseline(),
        scheduler_expected="running",
        metrics_text="unrelated 1\n",
        runner=fake_runner_factory(restart_api=1, oom_worker=True),
    )

    assert payload["result"] == "FAIL"
    assert "api:restart_increment" in payload["failures"]
    assert "worker:oom_killed" in payload["failures"]
    assert "checkpoint_lag:unavailable" in payload["failures"]
    assert parse_checkpoint_lag("w2_checkpoint_lag_seconds 1.5\n") == 1.5


def test_metrics_probe_rejects_non_loopback_network() -> None:
    assert validate_loopback_metrics_url("http://127.0.0.1:18000/metrics")
    with pytest.raises(ValueError, match="loopback"):
        validate_loopback_metrics_url("https://example.com/metrics")
