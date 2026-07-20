from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest

from w2.ingestion.checkpoint_refresh import checkpoint_plan_for_fixture
from w2.matchday.intake_v2 import (
    MatchdayCompetitionPolicy,
    build_checkpoint_plans,
    checkpoint_coverage,
    competition_policies,
    current_unscheduled_capture,
    endpoint_capture_contract,
    endpoint_params,
    enrichment_status,
    execute_matchday_intake,
    fixture_discovery_from_payloads,
    freshness_status,
    load_matchday_policy,
    market_batch_audit,
    materialize_evidence_manifest,
    name_only_crosswalk_review,
    normalize_matchday_odds_payload,
    public_manifest_read,
    team_crosswalk_contract,
    validate_manifest_identity,
)

NOW = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
KICKOFF = datetime(2026, 7, 20, 18, 0, tzinfo=UTC)


def _policy() -> MatchdayCompetitionPolicy:
    return competition_policies(load_matchday_policy())["allsvenskan"]


def test_single_canonical_policy_and_legacy_adapter_keeps_scheduled_at() -> None:
    policy = load_matchday_policy()
    assert policy["version"] == "w2.matchday_intake_policy.v2"

    plans = checkpoint_plan_for_fixture(
        fixture_id="fx-1",
        kickoff_utc=KICKOFF,
        generated_at_utc=KICKOFF - timedelta(hours=1),
    )

    t24 = next(item for item in plans if item.checkpoint == "T24_ODDS")
    assert t24.due_at_utc == KICKOFF - timedelta(hours=24)
    assert t24.status == "MISSED"


def test_t24_capture_due_and_missed_not_backfilled() -> None:
    policy = _policy()
    due = build_checkpoint_plans(
        fixture_id="fx-1",
        competition_id="allsvenskan",
        season="2026",
        kickoff_utc=KICKOFF,
        now=KICKOFF - timedelta(hours=24) + timedelta(minutes=10),
        policy=policy,
    )
    late = build_checkpoint_plans(
        fixture_id="fx-1",
        competition_id="allsvenskan",
        season="2026",
        kickoff_utc=KICKOFF,
        now=KICKOFF - timedelta(hours=1),
        policy=policy,
    )

    assert next(item for item in due if item.checkpoint == "T24_ODDS").status == "DUE"
    missed = next(item for item in late if item.checkpoint == "T24_ODDS")
    assert missed.status == "MISSED"
    assert missed.scheduled_at == KICKOFF - timedelta(hours=24)
    assert "CHECKPOINT_MISSING" in missed.blockers


def test_late_current_capture_does_not_complete_t24_and_partial_coverage() -> None:
    policy = _policy()
    plans = build_checkpoint_plans(
        fixture_id="fx-1",
        competition_id="allsvenskan",
        season="2026",
        kickoff_utc=KICKOFF,
        now=KICKOFF - timedelta(minutes=50),
        policy=policy,
    )
    current = current_unscheduled_capture(
        fixture_id="fx-1",
        competition_id="allsvenskan",
        season="2026",
        kickoff_utc=KICKOFF,
        captured_at=KICKOFF - timedelta(minutes=50),
        endpoints=("odds",),
        reason="LATE_START_CURRENT_CAPTURE",
    )

    assert current["completes_historical_checkpoint"] is False
    assert next(item for item in plans if item.checkpoint == "T24_ODDS").status == "MISSED"
    coverage_rows = [
        item.as_dict() | {"status": "CAPTURED"} if item.checkpoint == "T60_ODDS_LINEUPS" else item
        for item in plans
    ]
    coverage = checkpoint_coverage(coverage_rows)
    assert coverage["checkpoint_coverage"] == "PARTIAL"
    assert coverage["movement_readiness"] == "PARTIAL"


def test_fixture_discovery_allowlist_duplicate_conflict_and_crosswalk() -> None:
    policy = _policy()
    approved_home = team_crosswalk_contract(
        provider="api_football",
        provider_team_id="10",
        w2_team_id="team-home",
        competition_id="allsvenskan",
        season="2026",
        valid_from=NOW,
        valid_to=None,
        source="manual_review",
        review_status="APPROVED",
        evidence={"ticket": "unit"},
    )
    payloads = [_fixture_payload("100", "10", "11"), _fixture_payload("100", "10", "12")]

    result = fixture_discovery_from_payloads(
        payloads,
        policies={"allsvenskan": policy},
        captured_at=NOW,
        source_payload_sha256="a" * 64,
        team_crosswalks=[approved_home],
    )

    assert result["candidate_fixtures"][0]["team_identity_status"] == "TEAM_IDENTITY_NOT_READY"
    assert len(result["identity_conflicts"]) == 1
    assert result["duplicate_fixtures"] == 0


def test_unsupported_competition_excluded_and_name_only_mapping_review() -> None:
    result = fixture_discovery_from_payloads(
        [_fixture_payload("200", "1", "2", league_id="999")],
        policies={"allsvenskan": _policy()},
        captured_at=NOW,
        source_payload_sha256="b" * 64,
    )
    review = name_only_crosswalk_review(
        provider="api_football",
        provider_team_id="1",
        provider_name="Kalmar FF",
        competition_id="allsvenskan",
        season="2026",
        valid_from=NOW,
    )

    assert result["candidate_fixtures"] == []
    assert result["unsupported_competitions"] == ["999"]
    assert review["review_status"] == "REVIEW_REQUIRED"
    assert review["w2_team_id"] is None


def test_endpoint_params_capture_empty_and_provider_canary_requires_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    params = endpoint_params("fixtures", competition=_policy())
    capture = endpoint_capture_contract(
        endpoint="lineups",
        params={"fixture": "100"},
        requested_at=NOW,
        provider_captured_at=NOW,
        status_code=200,
        elapsed_ms=5,
        payload={"response": []},
        quota_values={"remaining": 100},
    )

    assert params == {"league": "113", "season": "2026"}
    assert capture["capture_status"] == "PROVIDER_EMPTY"
    with pytest.raises(ValueError, match="ENDPOINT_DISABLED_BY_POLICY"):
        endpoint_params("injuries", competition=_policy(), fixture_id="100")
    monkeypatch.delenv("W2_MATCHDAY_CANARY_APPROVED", raising=False)
    result = execute_matchday_intake(
        mode="CONTROLLED_PROVIDER_CANARY",
        fixture_ids=("100",),
        approve_provider_calls=True,
    )
    assert result.provider_calls == 0
    assert result.status == "PROVIDER_CANARY_NOT_EXECUTED_NO_AUTHORIZATION"


def test_dry_run_and_replay_have_zero_provider_calls() -> None:
    dry = execute_matchday_intake(mode="DRY_RUN")
    replay = execute_matchday_intake(
        mode="SAVED_PAYLOAD_REPLAY",
        saved_payloads=(
            {
                "endpoint": "fixtures",
                "params": {"league": "113", "season": "2026"},
                "requested_at": NOW.isoformat(),
                "captured_at": NOW.isoformat(),
                "payload": {"response": [_fixture_payload("100", "10", "11")]},
            },
        ),
    )

    assert dry.provider_calls == 0
    assert dry.db_writes == 0
    assert replay.provider_calls == 0
    assert replay.endpoint_captures[0]["capture_status"] == "CAPTURED"


def test_market_normalization_pairs_freshness_and_joint_same_family() -> None:
    payload = _odds_payload()
    rows, rejected = normalize_matchday_odds_payload(
        payload,
        captured_at=NOW,
        ingested_at=NOW,
        raw_payload_sha256="c" * 64,
        source_revision="unit",
        capture_id="capture-unit",
        competition_id="allsvenskan",
    )
    audit = market_batch_audit(rows, evaluated_at=NOW + timedelta(minutes=5), max_age_seconds=3600)

    assert rejected == []
    assert audit["ah_complete_sets"] == 1
    assert audit["ou_complete_sets"] == 1
    assert audit["one_x_two_complete_sets"] == 1
    assert audit["same_family_joint_sets"] == 1
    assert audit["joint_status"] == "JOINT_MARKET_BASELINE_READY"
    assert audit["recommendation_quote_max_age_seconds"] == 1800


def test_same_raw_payload_different_checkpoint_preserves_distinct_capture_identity() -> None:
    payload = _odds_payload()
    first = endpoint_capture_contract(
        endpoint="odds",
        params={"fixture": "100"},
        requested_at=NOW,
        provider_captured_at=NOW,
        status_code=200,
        elapsed_ms=1,
        payload=payload,
        fixture_id="api_football:100",
        checkpoint="T6_ODDS",
    )
    second = endpoint_capture_contract(
        endpoint="odds",
        params={"fixture": "100"},
        requested_at=NOW,
        provider_captured_at=NOW,
        status_code=200,
        elapsed_ms=1,
        payload=payload,
        fixture_id="api_football:100",
        checkpoint="T3_ODDS",
    )
    rows_one, _ = normalize_matchday_odds_payload(
        payload,
        captured_at=NOW,
        ingested_at=NOW,
        raw_payload_sha256=first["raw_payload_sha256"],
        source_revision="unit",
        capture_id=str(first["capture_id"]),
        competition_id="allsvenskan",
    )
    rows_two, _ = normalize_matchday_odds_payload(
        payload,
        captured_at=NOW,
        ingested_at=NOW,
        raw_payload_sha256=second["raw_payload_sha256"],
        source_revision="unit",
        capture_id=str(second["capture_id"]),
        competition_id="allsvenskan",
    )

    assert first["raw_payload_sha256"] == second["raw_payload_sha256"]
    assert first["capture_id"] != second["capture_id"]
    assert rows_one[0]["observation_id"] != rows_two[0]["observation_id"]


def test_malformed_live_suspended_and_mixed_batch_rejected() -> None:
    bad = _odds_payload()
    fixture = cast(dict[str, Any], bad["response"][0])
    bookmaker = cast(dict[str, Any], fixture["bookmakers"][0])
    bets = cast(list[dict[str, Any]], bookmaker["bets"])
    bets[0]["values"][0]["odd"] = "0.9"
    bets[2]["values"][0]["live"] = True

    rows, rejected = normalize_matchday_odds_payload(
        bad,
        captured_at=NOW,
        ingested_at=NOW,
        raw_payload_sha256="d" * 64,
        source_revision="unit",
        capture_id="capture-unit",
        competition_id="allsvenskan",
    )
    audit = market_batch_audit(rows, evaluated_at=NOW + timedelta(minutes=5), max_age_seconds=3600)

    assert {item["reason"] for item in rejected} >= {"INVALID_ODDS", "LIVE_QUOTE"}
    assert audit["same_family_joint_sets"] == 0
    assert audit["joint_status"] == "JOINT_MARKET_BASELINE_INCOMPLETE"
    assert audit["independent_candidates"]


def test_selected_ah_independent_of_stale_ou_and_freshness_from_captured_at_only() -> None:
    fresh = freshness_status(
        [{"captured_at": NOW.isoformat()}],
        evaluated_at=NOW + timedelta(minutes=10),
        max_age_seconds=900,
    )
    stale = freshness_status(
        [{"captured_at": NOW.isoformat()}],
        evaluated_at=NOW + timedelta(minutes=31),
        max_age_seconds=900,
    )

    assert fresh["freshness_status"] == "COMPLETE"
    assert stale["freshness_status"] == "STALE"


def test_enrichment_policy_lineups_and_no_fake_xg() -> None:
    policy = _policy()
    early = enrichment_status(
        competition_policy=policy,
        endpoint="lineups",
        kickoff_utc=KICKOFF,
        evaluated_at=KICKOFF - timedelta(hours=2),
        payload=None,
    )
    empty = enrichment_status(
        competition_policy=policy,
        endpoint="lineups",
        kickoff_utc=KICKOFF,
        evaluated_at=KICKOFF - timedelta(minutes=30),
        payload={"response": []},
    )
    stats = enrichment_status(
        competition_policy=policy,
        endpoint="statistics",
        kickoff_utc=KICKOFF,
        evaluated_at=NOW,
        payload=None,
    )

    assert early["status"] == "EXPECTED_NOT_AVAILABLE"
    assert empty["status"] == "PROVIDER_EMPTY"
    assert empty["blocks_analysis"] is False
    assert stats["status"] == "DISABLED_BY_POLICY"
    assert stats["as_of_safe_model_input"] is False


def test_manifest_deterministic_v3_outcomes_and_public_read_no_write() -> None:
    policy = _policy()
    fixture = _fixture_identity(team_ready=True)
    rows, _rejected = normalize_matchday_odds_payload(
        _odds_payload(),
        captured_at=NOW,
        ingested_at=NOW,
        raw_payload_sha256="e" * 64,
        source_revision="unit",
        capture_id="capture-unit",
        competition_id="allsvenskan",
    )
    audit = market_batch_audit(rows, evaluated_at=NOW + timedelta(minutes=5), max_age_seconds=3600)
    plans = build_checkpoint_plans(
        fixture_id=str(fixture["fixture_id"]),
        competition_id="allsvenskan",
        season="2026",
        kickoff_utc=KICKOFF,
        now=KICKOFF - timedelta(minutes=50),
        policy=policy,
    )
    model = {"status": "COMPLETE", "comparison": {"analysis_direction_allowed": True}}

    first = materialize_evidence_manifest(
        fixture_identity=fixture,
        competition_policy=policy,
        generated_at=NOW,
        checkpoint_plans=plans,
        endpoint_captures=[],
        market_audit=audit,
        enrichments={},
        model_evidence=model,
    )
    second = materialize_evidence_manifest(
        fixture_identity=fixture,
        competition_policy=policy,
        generated_at=NOW,
        checkpoint_plans=plans,
        endpoint_captures=[],
        market_audit=audit,
        enrichments={},
        model_evidence=model,
    )
    public = public_manifest_read(first)

    assert first["manifest_hash"] == second["manifest_hash"]
    assert first["audit"]["manifest_hash"] == first["manifest_hash"]
    assert validate_manifest_identity(first) == first["manifest_hash"]
    assert first["decision"]["outcome"] == "ANALYSIS_PICK"
    assert first["decision"]["formal_readiness"] is False
    assert first["recommendation_lock"] is False
    assert public["provider_calls"] == 0
    assert public["db_writes"] == 0


def test_v3_not_ready_no_edge_and_system_degraded() -> None:
    policy = _policy()
    fixture = _fixture_identity(team_ready=True)
    rows, _rejected = normalize_matchday_odds_payload(
        _odds_payload(),
        captured_at=NOW,
        ingested_at=NOW,
        raw_payload_sha256="f" * 64,
        source_revision="unit",
        capture_id="capture-unit",
        competition_id="allsvenskan",
    )
    audit = market_batch_audit(rows, evaluated_at=NOW, max_age_seconds=3600)
    base = {
        "fixture_identity": fixture,
        "competition_policy": policy,
        "generated_at": NOW,
        "checkpoint_plans": [],
        "endpoint_captures": [],
        "enrichments": {},
    }

    not_ready = materialize_evidence_manifest(
        **base,
        market_audit=audit,
        model_evidence={"status": "NOT_READY"},
    )
    no_edge = materialize_evidence_manifest(
        **base,
        market_audit=audit,
        model_evidence={"status": "COMPLETE", "comparison": {"analysis_direction_allowed": False}},
    )
    degraded = materialize_evidence_manifest(
        **base,
        market_audit={**audit, "integrity_status": "CONFLICT"},
        model_evidence={"status": "COMPLETE", "comparison": {"analysis_direction_allowed": True}},
    )

    assert not_ready["decision"]["outcome"] == "NOT_READY"
    assert no_edge["decision"]["outcome"] == "NO_EDGE"
    assert degraded["decision"]["outcome"] == "SYSTEM_DEGRADED"


def test_safety_authority_files_unchanged_and_no_web_diff() -> None:
    assert Path("config/capabilities/recommendation_capabilities.v1.json").is_file()
    assert Path("config/factors/factor_registry.v1.json").is_file()
    assert Path("config/evaluations/ah_formal_evidence.v1.json").is_file()


def _fixture_payload(
    fixture_id: str,
    home_id: str,
    away_id: str,
    *,
    league_id: str = "113",
) -> dict[str, object]:
    return {
        "fixture": {
            "id": fixture_id,
            "date": KICKOFF.isoformat(),
            "status": {"short": "NS"},
        },
        "league": {"id": league_id, "season": 2026},
        "teams": {
            "home": {"id": home_id, "name": "Home"},
            "away": {"id": away_id, "name": "Away"},
        },
    }


def _fixture_identity(*, team_ready: bool) -> dict[str, object]:
    return {
        "schema_version": "MatchdayFixtureIdentityV1",
        "fixture_id": "api_football:100",
        "provider": "api_football",
        "provider_fixture_id": "100",
        "competition_id": "allsvenskan",
        "provider_league_id": "113",
        "season": "2026",
        "kickoff_utc": KICKOFF.isoformat(),
        "fixture_status": "NS",
        "home_provider_team_id": "10",
        "away_provider_team_id": "11",
        "home_w2_team_id": "team-home" if team_ready else None,
        "away_w2_team_id": "team-away" if team_ready else None,
        "fixture_identity_status": "READY",
        "team_identity_status": "READY" if team_ready else "TEAM_IDENTITY_NOT_READY",
        "source_payload_sha256": "z" * 64,
        "captured_at": NOW.isoformat(),
    }


def _odds_payload() -> dict[str, object]:
    return {
        "parameters": {"fixture": "100"},
        "response": [
            {
                "fixture": {"id": "100"},
                "bookmakers": [
                    {
                        "id": "8",
                        "name": "Book",
                        "bets": [
                            {
                                "id": "1",
                                "name": "Match Winner",
                                "values": [
                                    {"value": "Home", "odd": "2.10"},
                                    {"value": "Draw", "odd": "3.30"},
                                    {"value": "Away", "odd": "3.60"},
                                ],
                            },
                            {
                                "id": "4",
                                "name": "Asian Handicap",
                                "values": [
                                    {"value": "Home -0.25", "odd": "1.91"},
                                    {"value": "Away 0.25", "odd": "1.95"},
                                ],
                            },
                            {
                                "id": "5",
                                "name": "Goals Over/Under",
                                "values": [
                                    {"value": "Over 2.5", "odd": "1.88"},
                                    {"value": "Under 2.5", "odd": "2.02"},
                                ],
                            },
                        ],
                    }
                ],
            }
        ],
    }
