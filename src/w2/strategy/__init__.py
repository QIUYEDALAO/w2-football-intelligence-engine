"""Strategy boundary, analysis-grade cards, and score scenario helpers.

Stage 9A introduces research-grade shadow decisions only. Public outputs remain
non-formal by default. Analysis-grade cards may emit ANALYSIS_PICK as an
explainable attention signal, but they do not set candidate/formal flags.
"""

from w2.strategy.analysis_score import (
    AnalysisCard,
    AnalysisInput,
    AnalysisPolicy,
    FactorContribution,
    MarketMovementSignal,
    ModelMarketSignal,
    TeamComparisonSignal,
    build_analysis_card,
)
from w2.strategy.score_scenarios import (
    ScoreScenario,
    ScoreScenarioSummary,
    build_score_scenarios,
    score_direction,
)

__all__ = [
    "AnalysisCard",
    "AnalysisInput",
    "AnalysisPolicy",
    "FactorContribution",
    "MarketMovementSignal",
    "ModelMarketSignal",
    "ScoreScenario",
    "ScoreScenarioSummary",
    "TeamComparisonSignal",
    "build_analysis_card",
    "build_score_scenarios",
    "score_direction",
]
