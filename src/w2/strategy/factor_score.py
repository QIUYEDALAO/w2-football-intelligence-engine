from __future__ import annotations

from dataclasses import dataclass

from w2.domain.factor_registry import (
    RECOMMENDATION_ALLOWED_INDEPENDENT_FACTORS,
    RECOMMENDATION_REQUIRED_SIGNAL_GROUPS,
    factor_policy,
)
from w2.features.framework import FeatureSet, FeatureStatus, TeamSide
from w2.pricing.team_score import independent_team_scores_from_contributions

# New single-chain admission (2026-09-28, AH/OU v3): the recommendation-driving
# factor score only requires the two evidence families F9_TRUE_XG (xg) and
# F6_H2H (h2h). The historical ">= 3 participating factors" count gate
# (MIN_PARTICIPATING_FACTORS) is retired — do not reintroduce it. Missing F9 or
# F6 fails closed (no recommendation); the decision never degrades to a
# single-factor pick. No strength threshold is layered on top of an admitted
# score.
MANDATORY_FACTOR_ID = "F9_TRUE_XG"
REQUIRED_EVIDENCE_FACTORS = frozenset({"F9_TRUE_XG", "F6_H2H"})


@dataclass(frozen=True, kw_only=True)
class FactorShare:
    feature_id: str
    label: str
    magnitude: float
    weight: float
    share: float
    side: TeamSide


@dataclass(frozen=True, kw_only=True)
class FactorAbsence:
    feature_id: str
    label: str
    status: FeatureStatus
    reason: str


@dataclass(frozen=True, kw_only=True)
class FactorScore:
    home_score: float
    away_score: float
    margin: float
    direction: TeamSide
    weight_sum_used: float
    participant_count: int
    participants: tuple[FactorShare, ...]
    absent: tuple[FactorAbsence, ...]
    admitted: bool
    admission_blockers: tuple[str, ...]

    @property
    def strength(self) -> float:
        return round(abs(self.margin), 6)


def build_factor_score(feature_set: FeatureSet) -> FactorScore:
    """Derive the recommendation-driving factor score.

    This calls `independent_team_scores_from_contributions()` — the exact
    same weighted-aggregation function that produces Path B's `team_score` —
    so this number and Path B's number are always the same computation, not
    two parallel implementations of "weighted factor score" that can drift
    apart the way `_factor_leader` and rest-day calculation once did.
    """
    labels = {item.feature_id: item.label for item in feature_set.contributions}

    team_scores = independent_team_scores_from_contributions(
        feature_set.contributions,
        allowlist=RECOMMENDATION_ALLOWED_INDEPENDENT_FACTORS,
        required_groups=RECOMMENDATION_REQUIRED_SIGNAL_GROUPS,
    )
    scoring = team_scores["scoring_factors"]
    weight_sum_used = float(team_scores["weight_sum_used"])

    participants = tuple(
        FactorShare(
            feature_id=str(row["id"]),
            label=labels.get(str(row["id"]), str(row["id"])),
            magnitude=float(row["score"]),
            weight=float(row["weight"]),
            share=float(row["share"]),
            side=_team_side(row["side"]),
        )
        for row in scoring
    )
    participating_ids = {share.feature_id for share in participants}

    # Only report absence for factors that are candidates for scoring at all
    # (the code-level allowlist); factors outside it (e.g. F1/F2 before they
    # are added to the allowlist, F4) are not "missing evidence", they are
    # simply not part of this scoring family yet.  EXPLANATION_ONLY factors are
    # additionally excluded at the policy level so they can never surface as a
    # "missing evidence" absence even if a stale entry ever re-enters the
    # allowlist.
    absent = tuple(
        FactorAbsence(
            feature_id=item.feature_id,
            label=item.label,
            status=item.status,
            reason=item.reason,
        )
        for item in feature_set.contributions
        if item.feature_id in RECOMMENDATION_ALLOWED_INDEPENDENT_FACTORS
        and item.feature_id not in participating_ids
        and factor_policy(item.feature_id).get("lifecycle") != "EXPLANATION_ONLY"
    )

    home_score = float(team_scores["home_score"])
    away_score = float(team_scores["away_score"])
    margin = round(home_score - away_score, 6)
    direction = TeamSide.HOME if margin > 0 else TeamSide.AWAY if margin < 0 else TeamSide.NEUTRAL

    blockers: list[str] = []
    missing_evidence = REQUIRED_EVIDENCE_FACTORS - participating_ids
    if missing_evidence:
        blockers.append(
            f"REQUIRED_EVIDENCE_MISSING:{','.join(sorted(missing_evidence))}"
        )

    return FactorScore(
        home_score=home_score,
        away_score=away_score,
        margin=margin,
        direction=direction,
        weight_sum_used=round(weight_sum_used, 6),
        participant_count=len(participants),
        participants=participants,
        absent=absent,
        admitted=not blockers,
        admission_blockers=tuple(blockers),
    )


def _team_side(value: object) -> TeamSide:
    text = str(value)
    if text in {"HOME", "AWAY", "NEUTRAL"}:
        return TeamSide(text)
    return TeamSide.NEUTRAL
