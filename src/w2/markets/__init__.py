"""Market baseline and analysis utilities for W2 Stage 6."""

from w2.markets.consensus import MarketConsensusBuilder, OddsQuote
from w2.markets.devig import DevigMethod, devig
from w2.markets.movement import MovementFeatureBuilder
from w2.markets.poisson import DixonColesBaseline, fit_total_goals_mu
from w2.markets.quality import MarketQualityAssessor

__all__ = [
    "DevigMethod",
    "DixonColesBaseline",
    "MarketConsensusBuilder",
    "MarketQualityAssessor",
    "MovementFeatureBuilder",
    "OddsQuote",
    "devig",
    "fit_total_goals_mu",
]
