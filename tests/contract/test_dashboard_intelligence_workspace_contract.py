from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

from apps.api.main import app

from w2.api.schemas import DashboardIntelligenceWorkspaceResponse
from w2.dashboard.workspace import build_dashboard_intelligence_workspace

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "examples" / "dashboard_intelligence_workspace.v1.json"
P1_CONTRACTS = (
    ROOT / "PERFECT_INTELLIGENCE_CAPABILITY_MATRIX.md",
    ROOT / "CURRENT_W2_GAP_MATRIX.md",
    ROOT / "DASHBOARD_DATA_CONTRACT.md",
    ROOT / "FRESHNESS_CONTRACT.md",
)
PROHIBITED_FIELDS = {
    "roi",
    "clv",
    "expected_value",
    "value_score",
    "opportunity_score",
    "lock_eligible",
    "anonymous_live_odds_benchmark",
    "market_pick",
}


def _empty_day_view() -> dict[str, Any]:
    return {
        "generated_at": "2026-08-09T02:00:00Z",
        "date": "2026-08-09",
        "football_day": "2026-08-09",
        "environment": "staging",
        "timezone": "Asia/Shanghai",
        "window": "today",
        "source": "dashboard_read_model",
        "checkpoint_key": "dashboard:day_view:2026-08-09",
        "provider_calls": 0,
        "db_writes": 0,
        "would_write_checkpoint": False,
        "navigation": {"current_date": "2026-08-09"},
        "freshness": {
            "page_updated_at": "2026-08-09T02:00:00Z",
            "provider_budget_status": "OK",
        },
        "counts": {"total": 0},
        "degradation": {"state": "EMPTY_DAY"},
        "performance": {},
        "cards": [],
    }


def _empty_replay(day_view: dict[str, Any]) -> dict[str, Any]:
    return {
        "replay_status": "MISSING_OUTCOMES",
        "known_at_summary": {
            "has_day_view": True,
            "generated_at": day_view["generated_at"],
            "source": day_view["source"],
            "checkpoint_key": day_view["checkpoint_key"],
        },
        "reason_summary": [],
        "outcome_tracking_summary": {
            "tracked_count": 0,
            "matched_outcome_count": 0,
            "missing_outcome_count": 0,
            "tracked_fixture_ids": [],
            "matched_fixture_ids": [],
            "missing_outcome_fixture_ids": [],
        },
        "card_hash_checks": [],
        "replay_gaps": [
            "MISSING_AUDIT_MANIFEST",
            "MISSING_AUDIT_TABLES",
            "MISSING_OUTCOMES",
        ],
    }


def _keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in _keys(item)}
    if isinstance(value, list):
        return {key for item in value for key in _keys(item)}
    return set()


def test_committed_sample_is_deterministic_and_schema_valid() -> None:
    sample = json.loads(SAMPLE.read_text())
    day_view = _empty_day_view()
    expected = {
        "request_id": "deterministic-sample",
        **build_dashboard_intelligence_workspace(
            day_view,
            replay=_empty_replay(day_view),
        ),
    }

    assert sample == expected
    assert DashboardIntelligenceWorkspaceResponse.model_validate(sample)
    keys = _keys(sample)
    assert keys.isdisjoint(PROHIBITED_FIELDS)
    assert not any(key.lower().endswith(("_roi", "_clv")) for key in keys)


def test_workspace_is_a_pure_adapter_without_provider_or_scheduler_imports() -> None:
    source = (ROOT / "src/w2/dashboard/workspace.py").read_text()
    router_source = (ROOT / "src/w2/api/routers.py").read_text()
    modules = {
        node.module
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom) and node.module
    }

    assert modules == {"__future__", "collections.abc", "typing"}
    assert "create_engine" not in source
    assert "session.commit" not in source
    assert "provider_client" not in source
    assert "scheduler" not in source.lower()
    assert "build_replay_front_door(" in router_source


def test_openapi_publishes_only_the_unified_workspace_response_contract() -> None:
    operation = app.openapi()["paths"]["/v1/dashboard/intelligence-workspace"]["get"]
    response = operation["responses"]["200"]["content"]["application/json"]["schema"]

    assert response == {
        "$ref": "#/components/schemas/DashboardIntelligenceWorkspaceResponse"
    }


def test_p1_contract_set_is_complete_and_field_bound() -> None:
    for path in P1_CONTRACTS:
        assert path.is_file()
        assert "BASE_MAIN_SHA = f0fe9d332d05a84f1ef04be86fd9fb44b69d69e3" in (
            path.read_text()
        )

    data_contract = P1_CONTRACTS[2].read_text()
    assert "| FIELD | SOURCE | AVAILABILITY | FRESHNESS_DOMAIN |" in data_contract
    assert "| NO_CALL_ON_READ |" in data_contract
    assert data_contract.count("| `") >= 60
    for field in PROHIBITED_FIELDS:
        assert field in data_contract


def test_freshness_contract_binds_every_approved_domain() -> None:
    contract = P1_CONTRACTS[3].read_text()
    for domain in (
        "FIXTURES",
        "EVENTS",
        "STATISTICS",
        "PLAYERS",
        "LINEUPS",
        "ODDS_PREMATCH",
        "ODDS_LIVE",
        "INJURIES",
        "PREDICTIONS",
        "STANDINGS",
        "TEAMS_STATISTICS",
        "PAGE_PROJECTION",
    ):
        assert f"`{domain}`" in contract
    assert "NO_CALL_ON_READ = true" in contract
