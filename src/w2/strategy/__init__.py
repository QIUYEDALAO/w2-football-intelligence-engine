"""Strategy boundary package. No recommendation engine is implemented in Stage 2."""

from w2.strategy.score_scenarios import (
    ScoreScenario,
    ScoreScenarioSummary,
    build_score_scenarios,
    score_direction,
)

__all__ = [
    "ScoreScenario",
    "ScoreScenarioSummary",
    "build_score_scenarios",
    "score_direction",
]
