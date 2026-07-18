from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATES = (
    "implemented",
    "locally_verified",
    "staging_accepted",
    "production_approved",
)


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_delivery_status_vocabulary_is_complete_and_not_overclaimed() -> None:
    policy = read("docs/operations/W2_DELIVERY_STATUS_LEVELS.md")
    state = read("PROJECT_STATE.yaml")
    next_action = read("NEXT_ACTION.md")

    for status in STATES:
        assert f"`{status}`" in policy
        assert f"  - {status}" in state
    assert "status: implemented" in state
    assert "R1 is not yet `staging_accepted`" in next_action
    assert "production_deployed: false" in state


def test_historical_pr_range_is_explicitly_non_authoritative() -> None:
    policy = read("docs/operations/W2_DELIVERY_STATUS_LEVELS.md")
    recovery = read("docs/consolidation/W2_V3_CORRECTNESS_RECOVERY_PLAN_20260718.md")

    assert "PRs #333–#347" in policy
    assert "PRs #333–#347" in recovery
    assert "specification and failure-case inputs only" in recovery
