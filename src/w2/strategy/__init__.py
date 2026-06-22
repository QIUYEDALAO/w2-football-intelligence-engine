"""Shadow-only strategy boundary and score scenario helpers.

Stage 9A introduces research-grade shadow decisions only. Public outputs remain
limited to NOT_READY, SKIP, and WATCH while Gate 4 is pending.
"""

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
