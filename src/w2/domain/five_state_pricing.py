from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal


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


def cashflow_price_edge(decimal_odds: Decimal, fair_odds: Decimal) -> Decimal:
    """Return executable price advantage over the five-state break-even price."""
    if decimal_odds <= 1:
        raise ValueError("decimal odds must be greater than 1")
    if fair_odds < 1:
        raise ValueError("fair decimal odds must be at least 1")
    return decimal_odds / fair_odds - Decimal("1")
