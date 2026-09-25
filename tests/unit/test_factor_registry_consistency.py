from __future__ import annotations

from datetime import UTC, datetime

from w2.domain.factor_registry import (
    ALLOWED_INDEPENDENT_FACTORS,
    load_factor_registry,
)
from w2.domain.factor_versions import FACTOR_BUILDER_BINDINGS
from w2.features.framework import (
    FeatureContribution,
    FeatureSet,
    FeatureStatus,
    TeamSide,
)
from w2.strategy.factor_score import build_factor_score

NOW = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)


def _registry_independent_scoring_ids() -> set[str]:
    """Factors the registry JSON marks as ACTIVE independent scoring factors."""
    return {
        str(raw["factor_id"])
        for raw in load_factor_registry().values()
        if raw.get("lifecycle") == "ACTIVE"
        and "SCORING" in raw.get("roles", [])
        and raw.get("independent_evidence_eligible") is True
        and raw.get("numeric_effect_enabled") is True
    }


def test_allowlist_matches_registry_independent_scoring_factors() -> None:
    assert ALLOWED_INDEPENDENT_FACTORS == _registry_independent_scoring_ids()


def test_allowlist_matches_version_bindings() -> None:
    assert ALLOWED_INDEPENDENT_FACTORS == set(FACTOR_BUILDER_BINDINGS)


def test_version_bindings_match_registry_independent_scoring_factors() -> None:
    assert set(FACTOR_BUILDER_BINDINGS) == _registry_independent_scoring_ids()


def test_f4_match_importance_is_explanation_only_and_not_independent() -> None:
    assert "F4_MATCH_IMPORTANCE" not in ALLOWED_INDEPENDENT_FACTORS
    assert "F4_MATCH_IMPORTANCE" not in FACTOR_BUILDER_BINDINGS
    f4 = load_factor_registry()["F4_MATCH_IMPORTANCE"]
    assert f4["lifecycle"] == "EXPLANATION_ONLY"
    assert f4["independent_evidence_eligible"] is False


def test_explanation_only_factor_never_enters_absent() -> None:
    contributions = (
        FeatureContribution(
            feature_id="F9_TRUE_XG",
            label="四字段 xG",
            status=FeatureStatus.READY,
            score=0.6,
            weight=0.10,
            side=TeamSide.HOME,
            reason="AS_OF_ROLLING_XG_DIFF",
            source_group="xg",
            is_independent_signal=True,
            observed_at=NOW,
        ),
        FeatureContribution(
            feature_id="F6_H2H",
            label="历史交锋",
            status=FeatureStatus.READY,
            score=0.3,
            weight=0.18,
            side=TeamSide.HOME,
            reason="INTERNAL_FIXTURE_H2H_DIFF",
            source_group="h2h",
            is_independent_signal=True,
            observed_at=NOW,
        ),
        FeatureContribution(
            feature_id="F3_REST_FITNESS",
            label="体能/休息差",
            status=FeatureStatus.READY,
            score=0.2,
            weight=0.10,
            side=TeamSide.HOME,
            reason="REST_DAYS_DIFF_COMPUTED",
            source_group="team_fixture_history",
            is_independent_signal=True,
            observed_at=NOW,
        ),
        # A genuine absent scoring factor (in the allowlist, not participating).
        FeatureContribution(
            feature_id="F5_RECENT_AH_COVER",
            label="近期赢盘率",
            status=FeatureStatus.INSUFFICIENT_DATA,
            score=None,
            weight=0.05,
            reason="MISSING_AH_EVIDENCE",
            source_group="team_fixture_history",
            is_independent_signal=False,
        ),
        # F4 is EXPLANATION_ONLY in the registry: even a READY reading must never
        # surface as "missing evidence".
        FeatureContribution(
            feature_id="F4_MATCH_IMPORTANCE",
            label="赛事重要性",
            status=FeatureStatus.READY,
            score=0.5,
            weight=0.08,
            side=TeamSide.HOME,
            reason="CONFIG_DRIVEN_STAGE_IMPORTANCE",
            source_group="match_importance",
            is_independent_signal=False,
        ),
    )
    feature_set = FeatureSet(
        fixture_id="fx",
        competition_id="c",
        as_of=NOW,
        status=FeatureStatus.READY,
        contributions=contributions,
    )

    result = build_factor_score(feature_set)

    absent_ids = {item.feature_id for item in result.absent}
    assert "F5_RECENT_AH_COVER" in absent_ids
    assert "F4_MATCH_IMPORTANCE" not in absent_ids
