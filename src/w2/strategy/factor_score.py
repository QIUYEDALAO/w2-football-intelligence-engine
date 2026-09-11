from __future__ import annotations

from dataclasses import dataclass

from w2.features.framework import FeatureSet, FeatureStatus, TeamSide
from w2.pricing.team_score import (
    ALLOWED_INDEPENDENT_FACTORS,
    independent_team_scores_from_contributions,
)

# Owner-approved admission rule (2026-09-03): a match only produces a
# factor-score-driven recommendation when F9_TRUE_XG actually participated
# in the weighted score AND at least 3 factors participated in total.
# No score threshold is set yet — see W2_UPGRADE_PLAN.md cut 06 step 5: the
# system must run and accumulate score/outcome pairs before any line is
# defensible. Do not add a strength threshold here without that data.
MANDATORY_FACTOR_ID = "F9_TRUE_XG"
MIN_PARTICIPATING_FACTORS = 3


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

    team_scores = independent_team_scores_from_contributions(feature_set.contributions)
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
    # simply not part of this scoring family yet.
    absent = tuple(
        FactorAbsence(
            feature_id=item.feature_id,
            label=item.label,
            status=item.status,
            reason=item.reason,
        )
        for item in feature_set.contributions
        if item.feature_id in ALLOWED_INDEPENDENT_FACTORS
        and item.feature_id not in participating_ids
    )

    home_score = float(team_scores["home_score"])
    away_score = float(team_scores["away_score"])
    margin = round(home_score - away_score, 6)
    direction = TeamSide.HOME if margin > 0 else TeamSide.AWAY if margin < 0 else TeamSide.NEUTRAL

    blockers: list[str] = []
    if MANDATORY_FACTOR_ID not in participating_ids:
        blockers.append(f"MANDATORY_FACTOR_MISSING:{MANDATORY_FACTOR_ID}")
    if len(participants) < MIN_PARTICIPATING_FACTORS:
        blockers.append(
            f"PARTICIPATING_FACTORS_BELOW_MINIMUM:{len(participants)}/{MIN_PARTICIPATING_FACTORS}"
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
