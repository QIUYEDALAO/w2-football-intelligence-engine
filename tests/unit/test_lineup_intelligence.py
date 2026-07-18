from __future__ import annotations

from datetime import UTC, datetime, timedelta

from w2.lineups.intelligence import (
    CoverageGrade,
    LineupAdjustment,
    LineupGate,
    MappingStatus,
    PlayerIdentityCandidate,
    apply_lineup_adjustments,
    build_team_baseline,
    derive_lineup_change_features,
    grade_coverage,
    resolve_player_identity,
)


def test_identity_mapping_is_deterministic_and_team_scoped() -> None:
    candidates = [
        PlayerIdentityCandidate(
            transfermarkt_player_id="tm-1",
            player_name="José Álvarez",
            team_external_id="team-1",
            position="Central Midfield",
        ),
        PlayerIdentityCandidate(
            transfermarkt_player_id="tm-2",
            player_name="Jose Alvarez",
            team_external_id="team-2",
            position="Central Midfield",
        ),
    ]
    first = resolve_player_identity(
        api_football_player_id="api-1",
        player_name="Jose Alvarez",
        team_external_id="team-1",
        provider_position="M",
        candidates=candidates,
    )
    second = resolve_player_identity(
        api_football_player_id="api-1",
        player_name="José Álvarez",
        team_external_id="team-1",
        provider_position="M",
        candidates=candidates,
    )
    assert first.status is MappingStatus.MATCHED
    assert first.transfermarkt_player_id == "tm-1"
    assert first.identity_hash == second.identity_hash


def test_identity_mapping_fails_closed_on_ambiguity() -> None:
    candidate = PlayerIdentityCandidate(
        transfermarkt_player_id="tm-1",
        player_name="John Smith",
        team_external_id="team-1",
    )
    result = resolve_player_identity(
        api_football_player_id="api-1",
        player_name="John Smith",
        team_external_id="team-1",
        provider_position=None,
        candidates=[candidate, candidate],
    )
    assert result.status is MappingStatus.CONFLICT
    assert result.transfermarkt_player_id is None


def test_baseline_is_asof_safe_and_deterministic() -> None:
    as_of = datetime(2026, 7, 19, tzinfo=UTC)
    rows = [
        {
            "fixture_id": f"f-{index}",
            "team_external_id": "team-1",
            "kickoff_at": as_of - timedelta(days=index + 1),
            "formation": "4-3-3",
            "starters": [{"player_id": "p-1", "position": "F"}],
        }
        for index in range(11)
    ]
    rows.append(
        {
            "fixture_id": "future",
            "team_external_id": "team-1",
            "kickoff_at": as_of + timedelta(days=1),
            "formation": "5-4-1",
            "starters": [{"player_id": "future", "position": "F"}],
        }
    )
    first = build_team_baseline(rows, team_external_id="team-1", as_of=as_of)
    second = build_team_baseline(list(reversed(rows)), team_external_id="team-1", as_of=as_of)
    assert first == second
    assert first["match_count"] == 10
    assert "future" not in first["input_fixture_ids"]


def test_independent_lineup_adjustments_are_evidence_gated_and_capped() -> None:
    disabled = apply_lineup_adjustments(
        lambda_home=1.5,
        lambda_away=1.0,
        adjustment=LineupAdjustment(ah_delta=1.0, totals_delta=1.0),
    )
    enabled = apply_lineup_adjustments(
        lambda_home=1.5,
        lambda_away=1.0,
        adjustment=LineupAdjustment(
            ah_delta=1.0,
            totals_delta=1.0,
            ah_evidence_enabled=True,
            totals_evidence_enabled=True,
        ),
    )
    assert disabled == (1.5, 1.0)
    assert enabled == (1.775, 1.025)


def test_lineup_changes_are_position_aware_and_fail_closed() -> None:
    baseline = {
        "common_formation": "4-3-3",
        "players": [{"player_id": "regular", "starter_weight": 5.0, "usual_position": "D"}],
    }
    starters = [
        {"player_id": "regular", "position": "F", "value_delta_eur": -1_000_000},
        *({"player_id": f"p-{index}", "position": "M"} for index in range(9)),
    ]
    features = derive_lineup_change_features(
        baseline=baseline,
        starters=starters,
        substitutes=[{"market_value_eur": 2_000_000}],
        formation="5-4-1",
    )
    assert features.status == "INCOMPLETE"
    assert features.blockers == ("STARTING_XI_INCOMPLETE",)
    assert features.out_of_position_count == 1
    assert features.formation_changed
    assert features.bench_value_eur == 2_000_000


def test_top_five_gate_requires_complete_22_player_identity_and_value() -> None:
    gate = LineupGate()
    blocked = gate.evaluate(
        competition_code="GB1",
        confirmed=True,
        home_starters=11,
        away_starters=11,
        uniquely_mapped_starters=21,
        valued_starters=22,
        formation_count=2,
        quotes_complete_and_fresh=True,
        audited_coverage_rate=0.95,
    )
    assert not blocked.eligible
    assert blocked.blockers == ("PLAYER_IDENTITY_INCOMPLETE",)


def test_non_top_five_grade_controls_numeric_enhancement_not_pick_gate() -> None:
    gate = LineupGate()
    result = gate.evaluate(
        competition_code="SE1",
        confirmed=False,
        home_starters=0,
        away_starters=0,
        uniquely_mapped_starters=0,
        valued_starters=0,
        formation_count=0,
        quotes_complete_and_fresh=True,
        audited_coverage_rate=0.49,
    )
    assert result.eligible
    assert result.grade is CoverageGrade.C
    assert not result.numeric_adjustment_enabled
    assert grade_coverage(0.5) is CoverageGrade.B
    assert grade_coverage(0.9) is CoverageGrade.A
