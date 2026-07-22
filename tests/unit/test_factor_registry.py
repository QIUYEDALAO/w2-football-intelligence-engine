from __future__ import annotations

from w2.domain.factor_registry import factor_policy, is_scoring_factor, load_factor_registry
from w2.lineups.intelligence import LineupGate
from w2.pricing.team_score import independent_team_scores


def _factor(factor_id: str, source_group: str) -> dict[str, object]:
    return {
        "id": factor_id,
        "status": "READY",
        "side": "HOME",
        "weight": 0.1,
        "score": 0.8,
        "source_group": source_group,
        "is_independent_signal": True,
    }


def test_legacy_f10_is_retired_and_cannot_score() -> None:
    assert factor_policy("F10_LINEUPS_INJURIES")["lifecycle"] == "RETIRED"
    assert not is_scoring_factor("F10_LINEUPS_INJURIES")
    shadow = independent_team_scores(
        feature_contributions=[_factor("F10_LINEUPS_INJURIES", "lineup")]
    )
    assert shadow["factor_count_used"] == 0


def test_lmm_is_gate_explanation_only_and_never_adds_evidence_group() -> None:
    lmm = factor_policy("F10_LMM_V1")
    assert lmm["numeric_effect_enabled"] is False
    assert lmm["independent_evidence_eligible"] is False
    shadow = independent_team_scores(
        feature_contributions=[
            _factor("F9_TRUE_XG", "xg"),
            _factor("F10_LMM_V1", "lineup"),
        ]
    )
    assert shadow["distinct_evidence_group_count"] == 1
    assert shadow["threshold_validation_status"] == "POLICY_THRESHOLD_UNVALIDATED"


def test_top_five_confirmation_does_not_require_value_mapping_or_formation() -> None:
    gate = LineupGate().evaluate(
        competition_code="GB1",
        confirmed=True,
        home_starters=11,
        away_starters=11,
        uniquely_mapped_starters=0,
        valued_starters=0,
        formation_count=0,
        quotes_complete_and_fresh=True,
        audited_coverage_rate=0.0,
    )
    assert gate.eligible
    assert not gate.numeric_adjustment_enabled


def test_registry_has_unique_entries() -> None:
    registry = load_factor_registry()
    assert set(registry) >= {"F1_MARKET_MOVEMENT", "F9_TRUE_XG", "F10_LMM_V1"}
