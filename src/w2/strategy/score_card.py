from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from w2.competitions.registry import CompetitionRegistry
from w2.strategy.score_scenarios import (
    Decision,
    Direction,
    ScoreMatrix,
    ScoreScenario,
    ScoreScenarioSummary,
    build_score_scenarios,
    score_direction,
)

ScoreScenarioRole = Literal["MAIN", "ALTERNATIVE"]


class ScoreCardScenario(BaseModel):
    role: ScoreScenarioRole
    scoreline: str = Field(pattern=r"^\d+-\d+$")
    home_score: int = Field(ge=0)
    away_score: int = Field(ge=0)
    score_direction: Direction
    probability: float = Field(ge=0, le=1)
    conditional_probability: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def scoreline_and_direction_match_goals(self) -> ScoreCardScenario:
        if self.scoreline != f"{self.home_score}-{self.away_score}":
            raise ValueError("scoreline must match home_score-away_score")
        if self.score_direction != score_direction((self.home_score, self.away_score)):
            raise ValueError("score_direction must match scoreline")
        return self


class ScoreCard(BaseModel):
    schema_version: Literal["W2_SCORE_CARD_V1"] = "W2_SCORE_CARD_V1"
    decision: Decision
    primary_direction: Direction | None = None
    scenarios: list[ScoreCardScenario]
    candidate: Literal[False] = False
    formal_recommendation: Literal[False] = False

    @model_validator(mode="after")
    def enforce_score_contract(self) -> ScoreCard:
        if self.decision == "SKIP":
            if self.primary_direction is not None:
                raise ValueError("SKIP score card must not carry primary_direction")
            if self.scenarios:
                raise ValueError("SKIP score card must not carry scenarios")
            return self
        if self.primary_direction is None:
            raise ValueError("primary_direction is required unless decision is SKIP")
        if self.decision == "MAIN":
            main_rows = [row for row in self.scenarios if row.role == "MAIN"]
            if not main_rows:
                raise ValueError("MAIN score card requires direction-consistent scenarios")
            if any(row.score_direction != self.primary_direction for row in main_rows):
                raise ValueError("MAIN score scenario bucket must match primary_direction")
        return self


def _scenario_payload(row: ScoreScenario, *, role: ScoreScenarioRole) -> ScoreCardScenario:
    return ScoreCardScenario(
        role=role,
        scoreline=row.score,
        home_score=row.home_score,
        away_score=row.away_score,
        score_direction=score_direction((row.home_score, row.away_score)),
        probability=row.probability,
        conditional_probability=row.conditional_probability,
    )


def score_card_from_summary(summary: ScoreScenarioSummary) -> ScoreCard:
    if summary.decision == "SKIP":
        return ScoreCard(decision="SKIP", primary_direction=None, scenarios=[])
    scenarios = [
        _scenario_payload(row, role="MAIN")
        for row in summary.direction_consistent_scores
    ]
    return ScoreCard(
        decision=summary.decision,
        primary_direction=summary.direction,
        scenarios=scenarios,
    )


def build_score_card(
    *,
    score_matrix: ScoreMatrix | None,
    decision: Decision,
    primary_direction: Direction | None,
    competition_id: str | None = None,
    registry: CompetitionRegistry | None = None,
    limit: int = 3,
) -> ScoreCard:
    if competition_id is not None:
        resolved_registry = registry or CompetitionRegistry()
        if not resolved_registry.is_analysis_available(competition_id):
            return ScoreCard(decision="SKIP", primary_direction=None, scenarios=[])
    if decision == "SKIP":
        return ScoreCard(decision="SKIP", primary_direction=None, scenarios=[])
    if not score_matrix:
        raise ValueError("complete score_matrix is required before emitting score scenarios")
    summary = build_score_scenarios(
        score_matrix=score_matrix,
        decision=decision,
        direction=primary_direction,
        limit=limit,
    )
    return score_card_from_summary(summary)


def render_score_card(card: ScoreCard) -> str:
    if card.decision == "SKIP":
        return "W2 research review: SKIP; no score scenarios displayed."
    rows = " / ".join(
        f"{scenario.role} {scenario.scoreline} P(score|direction)="
        f"{scenario.conditional_probability:.3f}"
        for scenario in card.scenarios
        if scenario.conditional_probability is not None
    )
    return f"W2 research review: {card.decision} {card.primary_direction}; {rows}"
