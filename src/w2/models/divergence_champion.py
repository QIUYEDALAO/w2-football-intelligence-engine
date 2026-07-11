from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum


class DivergenceModelFamily(StrEnum):
    FITTED_CALIBRATED = "FITTED_CALIBRATED"
    R4_1_CALIBRATED = "R4_1_CALIBRATED"


R4_1_DIVERGENCE_MODEL_COMPETITIONS = frozenset(
    {
        "bundesliga",
        "chinese_super_league",
        "allsvenskan",
        "eliteserien",
    }
)


@dataclass(frozen=True, kw_only=True)
class DivergenceChampionSelection:
    family: DivergenceModelFamily
    probabilities: Mapping[str, float]
    fallback_reason: str | None = None


def divergence_model_family_for(competition_id: str | None) -> DivergenceModelFamily:
    if (competition_id or "") in R4_1_DIVERGENCE_MODEL_COMPETITIONS:
        return DivergenceModelFamily.R4_1_CALIBRATED
    return DivergenceModelFamily.FITTED_CALIBRATED


def select_divergence_champion_probabilities(
    *,
    competition_id: str | None,
    fitted_calibrated: Mapping[str, float],
    r4_1_calibrated: Mapping[str, float] | None,
) -> DivergenceChampionSelection:
    family = divergence_model_family_for(competition_id)
    if family is DivergenceModelFamily.R4_1_CALIBRATED:
        if r4_1_calibrated:
            return DivergenceChampionSelection(
                family=family,
                probabilities=r4_1_calibrated,
            )
        return DivergenceChampionSelection(
            family=DivergenceModelFamily.FITTED_CALIBRATED,
            probabilities=fitted_calibrated,
            fallback_reason="R4_1_PROBABILITIES_MISSING",
        )
    return DivergenceChampionSelection(
        family=DivergenceModelFamily.FITTED_CALIBRATED,
        probabilities=fitted_calibrated,
    )
