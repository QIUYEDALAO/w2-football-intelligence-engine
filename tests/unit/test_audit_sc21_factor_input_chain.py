from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[2] / "scripts" / "audit_sc21_factor_input_chain.py"
SPEC = importlib.util.spec_from_file_location("audit_sc21_factor_input_chain", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _workspace_match() -> dict:
    market = {
        "status": "READY",
        "observation_count": 4,
        "snapshot_count": 1,
        "latest_snapshot_at": "2026-08-13T00:00:00Z",
        "quote_age_seconds": 60,
        "bookmaker_count": 3,
        "eligibility": {
            "candidate_quote_identity_status": "READY",
            "candidate_model_status": "READY",
            "candidate_eligibility_status": "READY",
            "blockers": [],
        },
    }
    return {
        "fixture_id": "1",
        "competition_id": "allsvenskan",
        "kickoff_utc": "2026-08-14T00:00:00Z",
        "home_team_name": "A",
        "away_team_name": "B",
        "market_radar": {"markets": {name: dict(market) for name in MODULE.MARKETS}},
        "model_lab": {"w2_model": {"calibration_status": "BASELINE_PRIOR"}},
        "lineup_collection": {"public_semantics": {"cause": "NOT_YET_DUE"}},
        "shadow_candidate": {"status": "NOT_READY", "market": None},
    }


def _db_row() -> dict:
    return {
        "fixture_id": "1",
        "team_identity_status": "PROVIDER_PRIMARY_READY",
        "xg_ready": True,
        "home_xg_for": 1.0,
        "home_xg_against": 1.0,
        "away_xg_for": 1.0,
        "away_xg_against": 1.0,
        "home_xg_match_count": 3,
        "away_xg_match_count": 3,
        "ratings_ready": False,
        "squad_value_ready": False,
        "lineup_snapshot_count": 0,
        "lineup_event_count": 0,
        "h2h_ready": False,
        "history_ready": False,
        "simulation_status": "READY",
        "simulations_completed": 10000,
        "calibration_status": "BASELINE_PRIOR",
        "capability_status": "ANALYSIS_ONLY",
        "decision_v4_outcome": "ANALYSIS_PICK",
        "decision_v4_blockers": [],
    }


def _meta() -> dict:
    return {"player_valuation_rows": 31507, "team_value_rows": 0}


def test_build_audit_keeps_markets_independent_and_preserves_forward_boundary() -> None:
    match = _workspace_match()
    match["market_radar"]["markets"]["TOTALS"]["bookmaker_count"] = 1
    match["shadow_candidate"] = {
        "status": "ACTIVE",
        "market": "ASIAN_HANDICAP",
        "captured_at": "2026-08-13T00:00:00Z",
        "decision_hash": "a" * 64,
    }
    audit = MODULE.build_audit(
        [{"generated_at": "2026-08-13T00:01:00Z", "matches": [match]}],
        [_db_row()],
        _meta(),
    )
    fixture = audit["fixtures"][0]
    assert fixture["markets"]["ASIAN_HANDICAP"]["candidate_eligibility"]["reason"] == "READY"
    assert fixture["markets"]["TOTALS"]["candidate_eligibility"]["reason"] == "UNDER_SAMPLED"
    assert fixture["markets"]["ASIAN_HANDICAP"]["immutable_forward_record"]["selected"]
    assert fixture["factors"]["lineup"]["reason"] == "NOT_YET_DUE"
    assert fixture["factors"]["calibration"]["reason"] == "OWNER_DECISION_REQUIRED"


def test_build_audit_rejects_non_exact13_and_fixture_set_drift() -> None:
    match = _workspace_match()
    match["competition_id"] = "world_cup_2026"
    with pytest.raises(ValueError, match="non-authorized competitions"):
        MODULE.build_audit([{"matches": [match]}], [_db_row()], _meta())
    with pytest.raises(ValueError, match="fixture sets differ"):
        MODULE.build_audit([{"matches": [_workspace_match()]}], [], _meta())
