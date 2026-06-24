from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Decision = Literal["MAIN", "WATCH", "SKIP"]
Direction = Literal["HOME", "DRAW", "AWAY"]
ScoreMatrix = dict[tuple[int, int], float]


@dataclass(frozen=True)
class ScoreScenario:
    home_score: int
    away_score: int
    probability: float
    conditional_probability: float | None = None

    @property
    def score(self) -> str:
        return f"{self.home_score}-{self.away_score}"


@dataclass(frozen=True)
class ScoreScenarioSummary:
    decision: Decision
    direction: Direction | None
    global_top_scores: list[ScoreScenario]
    direction_consistent_scores: list[ScoreScenario]


def score_direction(score: tuple[int, int]) -> Direction:
    home, away = score
    if home > away:
        return "HOME"
    if home < away:
        return "AWAY"
    return "DRAW"


def normalize_score_matrix(score_matrix: ScoreMatrix) -> ScoreMatrix:
    if not score_matrix:
        raise ValueError("score_matrix is required")
    if any(home < 0 or away < 0 for home, away in score_matrix):
        raise ValueError("score_matrix goals must be non-negative")
    total = sum(score_matrix.values())
    if total <= 0:
        raise ValueError("score_matrix total probability must be positive")
    return {score: probability / total for score, probability in score_matrix.items()}


def build_score_scenarios(
    *,
    score_matrix: ScoreMatrix,
    decision: Decision,
    direction: Direction | None,
    limit: int = 3,
) -> ScoreScenarioSummary:
    if limit <= 0:
        raise ValueError("limit must be positive")
    if decision == "SKIP":
        return ScoreScenarioSummary(
            decision=decision,
            direction=None,
            global_top_scores=[],
            direction_consistent_scores=[],
        )
    if direction is None:
        raise ValueError("direction is required unless decision is SKIP")
    normalized = normalize_score_matrix(score_matrix)
    global_top_scores = [
        ScoreScenario(home, away, probability)
        for (home, away), probability in sorted(
            normalized.items(),
            key=lambda item: (-item[1], item[0][0] + item[0][1], item[0][0], item[0][1]),
        )[:limit]
    ]
    direction_rows = {
        score: probability
        for score, probability in normalized.items()
        if score_direction(score) == direction
    }
    direction_total = sum(direction_rows.values())
    if direction_total <= 0:
        raise ValueError("direction bucket has no probability mass")
    direction_consistent_scores = [
        ScoreScenario(
            home,
            away,
            probability,
            conditional_probability=probability / direction_total,
        )
        for (home, away), probability in sorted(
            direction_rows.items(),
            key=lambda item: (-item[1], item[0][0] + item[0][1], item[0][0], item[0][1]),
        )[:limit]
    ]
    if decision == "MAIN" and any(
        score_direction((row.home_score, row.away_score)) != direction
        for row in direction_consistent_scores
    ):
        raise ValueError("MAIN score bucket must match direction")
    return ScoreScenarioSummary(
        decision=decision,
        direction=direction,
        global_top_scores=global_top_scores,
        direction_consistent_scores=direction_consistent_scores,
    )
