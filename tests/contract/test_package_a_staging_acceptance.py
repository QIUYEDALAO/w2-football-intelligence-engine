from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ACCEPTANCE = ROOT / "reports/W2_PACKAGE_A_STAGING_ACCEPTANCE.json"
HANDOFF = ROOT / "reports/W2_CURRENT_HANDOFF.md"
ROADMAP = ROOT / "reports/W2_ROADMAP_STATUS.json"


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_package_a_acceptance_records_dynamic_staging_state() -> None:
    payload = load_json(ACCEPTANCE)

    assert payload["package_id"] == "W2_PACKAGE_A"
    assert payload["status"] == "STAGING_ACCEPTED"
    assert payload["deployed_revision"] == "3e79fdfa34cdf13e3c1e71159625aaa2535a7b9f"
    assert payload["alembic_head"] == "0018_create_future_refresh_persistence"
    assert payload["classification"] == "EXPECTED_FORWARD_ACCUMULATION"
    assert payload["persistence"] == "POSTGRESQL"
    assert payload["runtime_writable"] is False
    assert payload["runtime_writability_required"] is False
    assert payload["shared_runtime_blocker_resolved"] is True
    assert payload["candidate"] is False
    assert payload["formal_recommendation"] is False

    baseline = payload["baseline_minimums"]
    observed = payload["observed_counts"]
    growth = payload["growth_since_initial_acceptance"]
    assert isinstance(baseline, dict)
    assert isinstance(observed, dict)
    assert isinstance(growth, dict)
    for key in (
        "future_market_observation",
        "future_refresh_task_audit",
        "future_refresh_run_audit",
        "raw_payload",
    ):
        assert observed[key] >= baseline[key]
        assert growth[key] == observed[key] - baseline[key]
        assert growth[key] >= 0

    assert observed["future_market_observation"] == observed["distinct_observation_id"]
    assert observed["duplicate_observation_id"] == 0
    assert observed["candidate_true"] == 0
    assert observed["formal_recommendation_true"] == 0
    assert payload["latest_task_status"] == "COMPLETED"
    assert payload["latest_request_count"] == 12


def test_handoff_v42_records_package_a_without_closing_gates() -> None:
    handoff = HANDOFF.read_text(encoding="utf-8")

    assert "handoff_version: 42" in handoff
    assert "handoff_correction: PACKAGE_A_STAGING_ACCEPTANCE_RECONCILED" in handoff
    assert "server_revision: 3e79fdfa34cdf13e3c1e71159625aaa2535a7b9f" in handoff
    assert "alembic_head: 0018_create_future_refresh_persistence" in handoff
    assert "package_a_status: STAGING_ACCEPTED" in handoff
    for item in ("A1", "A2", "A3", "A4", "A5"):
        assert f"  - {item}" in handoff
    assert "  - A6_OBJECT_STORAGE" in handoff
    assert "future_refresh_deployment_status: STAGING_ACCEPTED" in handoff
    assert "future_refresh_persistence: POSTGRESQL" in handoff
    assert "future_refresh_counts_are_dynamic: true" in handoff
    assert "future_refresh_count_classification: EXPECTED_FORWARD_ACCUMULATION" in handoff
    assert "future_refresh_runtime_writability_required: false" in handoff
    assert "shared_runtime_blocker: RESOLVED_BY_DB_PERSISTENCE" in handoff
    assert "gate3_status: PARTIAL" in handoff
    assert "gate5: OPEN" in handoff
    assert "candidate: false" in handoff
    assert "formal_recommendation: false" in handoff
    assert "BLOCKED_NON_QUALIFYING_LIFECYCLE_GAP" in handoff
    assert "stage10e_deployed: false" in handoff


def test_roadmap_status_tracks_package_a_and_next_package() -> None:
    payload = load_json(ROADMAP)

    assert payload["candidate"] is False
    assert payload["formal_recommendation"] is False
    assert payload["future_refresh_hardening"] == "STAGING_ACCEPTED"
    assert payload["forward_collection"] == "ACTIVE"
    assert payload["next_active_package"] == "Stage7I lifecycle supervision B1+B2"

    package_a = payload["package_a"]
    assert package_a["A1"] == "COMPLETE"
    assert package_a["A2"] == "COMPLETE_APPLIED"
    assert package_a["A3"] == "COMPLETE"
    assert package_a["A4"] == "COMPLETE"
    assert package_a["A5"] == "STAGING_ACCEPTED"
    assert package_a["A6"] == "PENDING_OBJECT_STORAGE"
    assert package_a["shared_runtime_not_writable_blocker"] == "RESOLVED_BY_DB_PERSISTENCE"
    assert package_a["counts_are_dynamic"] is True

    assert payload["gates"]["3"]["status"] == "PARTIAL"
    assert payload["gates"]["4"]["status"] == "OPEN"
    assert payload["gates"]["5"]["status"] == "OPEN"
