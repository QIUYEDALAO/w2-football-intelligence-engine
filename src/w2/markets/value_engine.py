from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Any

from w2.domain.enums import MarketType, SettlementOutcome
from w2.domain.odds import settle_asian_handicap, settle_total_goals

ScoreMatrix = dict[tuple[int, int], Decimal]


class OddsFormat(StrEnum):
    DECIMAL = "DECIMAL"
    HONG_KONG = "HONG_KONG"


class ValueAction(StrEnum):
    WATCH = "WATCH"
    SKIP = "SKIP"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, kw_only=True)
class OddsQuote:
    bookmaker_id: str
    bookmaker_name: str
    market_type: MarketType
    selection: str
    line: Decimal | None
    raw_odds: Decimal
    raw_odds_format: OddsFormat
    decimal_odds: Decimal
    captured_at: datetime
    provider_updated_at: datetime
    suspended: bool
    live: bool
    provenance: str


@dataclass(frozen=True, kw_only=True)
class SettlementDistribution:
    full_win_probability: Decimal = Decimal("0")
    half_win_probability: Decimal = Decimal("0")
    push_probability: Decimal = Decimal("0")
    half_loss_probability: Decimal = Decimal("0")
    full_loss_probability: Decimal = Decimal("0")

    def normalized(self) -> SettlementDistribution:
        total = (
            self.full_win_probability
            + self.half_win_probability
            + self.push_probability
            + self.half_loss_probability
            + self.full_loss_probability
        )
        if total == 0:
            raise ValueError("settlement distribution has zero probability")
        return SettlementDistribution(
            full_win_probability=self.full_win_probability / total,
            half_win_probability=self.half_win_probability / total,
            push_probability=self.push_probability / total,
            half_loss_probability=self.half_loss_probability / total,
            full_loss_probability=self.full_loss_probability / total,
        )

    def as_dict(self) -> dict[str, str]:
        return {
            "full_win_probability": str(self.full_win_probability),
            "half_win_probability": str(self.half_win_probability),
            "push_probability": str(self.push_probability),
            "half_loss_probability": str(self.half_loss_probability),
            "full_loss_probability": str(self.full_loss_probability),
        }


@dataclass(frozen=True, kw_only=True)
class BookmakerPair:
    bookmaker: str
    line: Decimal | None
    side_a_odds: Decimal
    side_b_odds: Decimal
    pair_time_delta_seconds: int
    pair_valid: bool
    rejection_reason: str | None


@dataclass(frozen=True, kw_only=True)
class MarketCandidate:
    market_type: MarketType
    selection: str
    line: Decimal | None
    bookmaker: str
    executable_odds: Decimal
    hong_kong_odds: Decimal
    model_fair_odds: Decimal | None
    market_no_vig_odds: Decimal | None
    settlement_distribution: SettlementDistribution | None
    raw_ev: Decimal | None
    uncertainty_margin: Decimal
    risk_adjusted_ev: Decimal | None
    data_quality: str
    market_quality: str
    evidence_count: int
    raw_research_grade: str
    published_grade: str
    action: ValueAction
    diagnostics: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "market_type": self.market_type.value,
            "selection": self.selection,
            "line": str(self.line) if self.line is not None else None,
            "bookmaker": self.bookmaker,
            "executable_odds": str(self.executable_odds),
            "hong_kong_odds": str(self.hong_kong_odds),
            "model_fair_odds": str(self.model_fair_odds) if self.model_fair_odds else None,
            "market_no_vig_odds": str(self.market_no_vig_odds)
            if self.market_no_vig_odds
            else None,
            "settlement_distribution": self.settlement_distribution.as_dict()
            if self.settlement_distribution
            else None,
            "raw_ev": str(self.raw_ev) if self.raw_ev is not None else None,
            "uncertainty_margin": str(self.uncertainty_margin),
            "risk_adjusted_ev": str(self.risk_adjusted_ev)
            if self.risk_adjusted_ev is not None
            else None,
            "data_quality": self.data_quality,
            "market_quality": self.market_quality,
            "evidence_count": self.evidence_count,
            "raw_research_grade": self.raw_research_grade,
            "published_grade": self.published_grade,
            "action": self.action.value,
            "diagnostics": list(self.diagnostics),
        }


def hong_kong_to_decimal(value: Decimal) -> Decimal:
    if value <= 0:
        raise ValueError("Hong Kong odds must be positive")
    return (value + Decimal("1")).quantize(Decimal("0.0001"))


def decimal_to_hong_kong(value: Decimal) -> Decimal:
    if value <= 1:
        raise ValueError("decimal odds must be greater than 1")
    return (value - Decimal("1")).quantize(Decimal("0.0001"))


def infer_decimal_odds(raw: Decimal, raw_format: OddsFormat | None) -> Decimal:
    if raw_format is None:
        raise ValueError("odds format is required")
    if raw_format == OddsFormat.DECIMAL:
        if raw <= 1:
            raise ValueError("decimal odds must be greater than 1")
        return raw
    if raw_format == OddsFormat.HONG_KONG:
        return hong_kong_to_decimal(raw)
    raise ValueError(f"unsupported odds format: {raw_format}")


def settlement_distribution_ah(
    score_matrix: ScoreMatrix,
    *,
    selection: str,
    line: Decimal,
) -> SettlementDistribution:
    totals = _empty_distribution()
    for (home, away), probability in score_matrix.items():
        outcome = settle_asian_handicap(home, away, selection, line)
        totals[outcome] += probability
    return _distribution_from_outcome_map(totals).normalized()


def settlement_distribution_totals(
    score_matrix: ScoreMatrix,
    *,
    selection: str,
    line: Decimal,
) -> SettlementDistribution:
    totals = _empty_distribution()
    for (home, away), probability in score_matrix.items():
        outcome = settle_total_goals(home + away, selection, line)
        totals[outcome] += probability
    return _distribution_from_outcome_map(totals).normalized()


def _empty_distribution() -> dict[SettlementOutcome, Decimal]:
    return {
        SettlementOutcome.WIN: Decimal("0"),
        SettlementOutcome.HALF_WIN: Decimal("0"),
        SettlementOutcome.PUSH: Decimal("0"),
        SettlementOutcome.HALF_LOSS: Decimal("0"),
        SettlementOutcome.LOSS: Decimal("0"),
    }


def _distribution_from_outcome_map(
    totals: dict[SettlementOutcome, Decimal],
) -> SettlementDistribution:
    return SettlementDistribution(
        full_win_probability=totals[SettlementOutcome.WIN],
        half_win_probability=totals[SettlementOutcome.HALF_WIN],
        push_probability=totals[SettlementOutcome.PUSH],
        half_loss_probability=totals[SettlementOutcome.HALF_LOSS],
        full_loss_probability=totals[SettlementOutcome.LOSS],
    )


def expected_value(decimal_odds: Decimal, distribution: SettlementDistribution) -> Decimal:
    hk_profit = decimal_odds - Decimal("1")
    return (
        distribution.full_win_probability * hk_profit
        + distribution.half_win_probability * Decimal("0.5") * hk_profit
        - distribution.half_loss_probability * Decimal("0.5")
        - distribution.full_loss_probability
    )


def fair_hk_odds(distribution: SettlementDistribution) -> Decimal:
    numerator = (
        distribution.full_loss_probability
        + Decimal("0.5") * distribution.half_loss_probability
    )
    denominator = (
        distribution.full_win_probability
        + Decimal("0.5") * distribution.half_win_probability
    )
    if denominator == 0:
        raise ValueError("fair odds denominator is zero")
    return (numerator / denominator).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def fair_decimal_odds(distribution: SettlementDistribution) -> Decimal:
    return (fair_hk_odds(distribution) + Decimal("1")).quantize(
        Decimal("0.0001"),
        rounding=ROUND_HALF_UP,
    )


def binary_distribution(probability: Decimal) -> SettlementDistribution:
    if not Decimal("0") <= probability <= Decimal("1"):
        raise ValueError("probability must be within [0, 1]")
    return SettlementDistribution(
        full_win_probability=probability,
        full_loss_probability=Decimal("1") - probability,
    )


def pair_bookmaker_quotes(
    quote_a: OddsQuote,
    quote_b: OddsQuote,
    *,
    tolerance_seconds: int,
) -> BookmakerPair:
    delta = int(abs((quote_a.captured_at - quote_b.captured_at).total_seconds()))
    reason = None
    if quote_a.bookmaker_id != quote_b.bookmaker_id:
        reason = "BOOKMAKER_MISMATCH"
    elif quote_a.market_type != quote_b.market_type:
        reason = "MARKET_MISMATCH"
    elif quote_a.line != quote_b.line:
        reason = "LINE_MISMATCH"
    elif delta > tolerance_seconds:
        reason = "CAPTURE_TIME_DELTA_EXCEEDS_TOLERANCE"
    return BookmakerPair(
        bookmaker=quote_a.bookmaker_name,
        line=quote_a.line,
        side_a_odds=quote_a.decimal_odds,
        side_b_odds=quote_b.decimal_odds,
        pair_time_delta_seconds=delta,
        pair_valid=reason is None,
        rejection_reason=reason,
    )


def grade_candidate(
    risk_adjusted_ev: Decimal | None,
    *,
    data_quality: str,
    market_quality: str,
    gate4_pending: bool,
) -> tuple[str, str, ValueAction]:
    if data_quality == "BLOCKED" or market_quality == "BLOCKED" or risk_adjusted_ev is None:
        return ("X", "X", ValueAction.BLOCKED)
    if (
        risk_adjusted_ev >= Decimal("0.05")
        and data_quality == "READY"
        and market_quality == "READY"
    ):
        raw = "A"
    elif risk_adjusted_ev >= Decimal("0.025"):
        raw = "B"
    elif risk_adjusted_ev > Decimal("0"):
        raw = "C"
    else:
        raw = "D"
    published = raw
    if gate4_pending and raw in {"A", "B"}:
        published = "C"
    action = ValueAction.WATCH if published in {"A", "B", "C"} else ValueAction.SKIP
    return (raw, published, action)


class MarketValueEngine:
    def __init__(self, *, uncertainty_margin: Decimal = Decimal("0.035")) -> None:
        self.uncertainty_margin = uncertainty_margin

    def evaluate(
        self,
        *,
        score_matrix: ScoreMatrix,
        independent_probabilities: dict[str, Decimal],
        quotes: list[OddsQuote],
        data_quality: str = "READY",
        market_quality: str = "READY",
        gate4_pending: bool = True,
    ) -> list[MarketCandidate]:
        candidates: list[MarketCandidate] = []
        for quote in quotes:
            distribution = self._distribution_for_quote(
                quote,
                score_matrix=score_matrix,
                probabilities=independent_probabilities,
            )
            computed_ev = expected_value(quote.decimal_odds, distribution)
            raw_ev: Decimal | None = computed_ev
            risk_ev: Decimal | None = computed_ev - self.uncertainty_margin
            try:
                model_fair = fair_decimal_odds(distribution)
            except ValueError:
                model_fair = None
                raw_ev = None
                risk_ev = None
            raw_grade, published_grade, action = grade_candidate(
                risk_ev,
                data_quality=data_quality,
                market_quality=market_quality,
                gate4_pending=gate4_pending,
            )
            candidates.append(
                MarketCandidate(
                    market_type=quote.market_type,
                    selection=quote.selection,
                    line=quote.line,
                    bookmaker=quote.bookmaker_name,
                    executable_odds=quote.decimal_odds,
                    hong_kong_odds=decimal_to_hong_kong(quote.decimal_odds),
                    model_fair_odds=model_fair,
                    market_no_vig_odds=None,
                    settlement_distribution=distribution,
                    raw_ev=raw_ev,
                    uncertainty_margin=self.uncertainty_margin,
                    risk_adjusted_ev=risk_ev,
                    data_quality=data_quality,
                    market_quality=market_quality,
                    evidence_count=1,
                    raw_research_grade=raw_grade,
                    published_grade=published_grade,
                    action=action,
                )
            )
        return sorted(
            candidates,
            key=lambda item: (
                item.risk_adjusted_ev if item.risk_adjusted_ev is not None else Decimal("-999")
            ),
            reverse=True,
        )

    def _distribution_for_quote(
        self,
        quote: OddsQuote,
        *,
        score_matrix: ScoreMatrix,
        probabilities: dict[str, Decimal],
    ) -> SettlementDistribution:
        if quote.market_type == MarketType.ASIAN_HANDICAP:
            if quote.line is None:
                raise ValueError("AH quote requires line")
            return settlement_distribution_ah(
                score_matrix,
                selection=quote.selection,
                line=quote.line,
            )
        if quote.market_type == MarketType.TOTALS:
            if quote.line is None:
                raise ValueError("totals quote requires line")
            return settlement_distribution_totals(
                score_matrix,
                selection=quote.selection,
                line=quote.line,
            )
        key = quote.selection
        probability = probabilities.get(key)
        if probability is None:
            raise ValueError(f"missing independent probability for {key}")
        return binary_distribution(probability)


class AsianHandicapLadderEvaluator(MarketValueEngine):
    pass


class TotalsLadderEvaluator(MarketValueEngine):
    pass
