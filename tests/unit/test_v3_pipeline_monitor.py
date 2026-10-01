"""Read-only production monitor must surface real persisted task faults."""

import importlib.util
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[2] / "ops/host/w2-v3-readonly-monitor.py"
spec = importlib.util.spec_from_file_location("v3_readonly_monitor", SOURCE)
assert spec is not None and spec.loader is not None
monitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor)


def test_monitor_empty_change_control_and_completed_pipeline():
    healthy = {"provider_stage_counts": [
        {"stage": stage, "state": "DONE", "count": 1}
        for stage in ("h2h", "xg", "refresh_forward", "task")
    ], "stale_provider_stages": [], "checkpoint_health": [], "done_without_forward": []}
    assert monitor.pipeline_issues(healthy) == []
    assert monitor.pipeline_issues(dict(healthy)) == []


@pytest.mark.parametrize("state,reason", [
    ({"provider_stage_counts": [{"stage": "xg", "state": "SIDE_EFFECT_UNCERTAIN"}]},
     "PROVIDER_STAGE_BLOCKED:xg:SIDE_EFFECT_UNCERTAIN"),
    ({"provider_stage_counts": [{"stage": "task", "state": "BLOCKED"}]},
     "PROVIDER_STAGE_BLOCKED:task:BLOCKED"),
    ({"provider_stage_counts": [{"stage": "h2h", "state": "UNKNOWN"}]},
     "PROVIDER_STAGE_STATE_UNKNOWN:h2h:UNKNOWN"),
    ({"stale_provider_stages": [{"state": "ATTEMPTING"}]},
     "PROVIDER_STAGE_STALE_ATTEMPTING"),
    ({"done_without_forward": [{"task_id": "incomplete"}]}, "TASK_DONE_WITHOUT_REFRESH_FORWARD"),
    ({"failed_task_results": [{"stored_status": "BLOCKED_WITH_RECORDING_INCOMPLETE"}]},
     "TASK_RESULT_FAILED:BLOCKED_WITH_RECORDING_INCOMPLETE"),
    ({"checkpoint_health": [{"status": "FAILED"}]}, "CHECKPOINT_FAILED"),
])
def test_monitor_no_selected_rows_cannot_hide_pipeline_fault(state, reason):
    state["decisions"] = []
    assert monitor.pipeline_issues(state) == [reason]
