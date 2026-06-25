from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from statistics import median

from w2.domain.time import require_utc


@dataclass(frozen=True, kw_only=True)
class OddsQuote:
    bookmaker: str
    market: str
    selection: str
    decimal_odds: Decimal
    captured_at: datetime
    provider_updated_at: datetime
    line: Decimal | None = None
    suspended: bool = False
    live: bool = False
    stale: bool = False

    def __post_init__(self) -> None:
        if self.decimal_odds <= Decimal("1"):
            raise ValueError("decimal_odds must be greater than 1")
        object.__setattr__(self, "captured_at", require_utc(self.captured_at, "captured_at"))
        object.__setattr__(
            self,
            "provider_updated_at",
            require_utc(self.provider_updated_at, "provider_updated_at"),
        )


@dataclass(frozen=True, kw_only=True)
class ConsensusConfig:
    bookmaker_weights: dict[str, float] | None = None
    excluded_bookmakers: frozenset[str] = frozenset()
    max_staleness_seconds: int = 3600
    trim_fraction: float = 0.10
    min_bookmakers: int = 2


@dataclass(frozen=True, kw_only=True)
class MarketConsensus:
    status: str
    method: str
    fair_decimal_odds: Decimal | None
    effective_bookmakers: int
    dispersion: float | None
    outliers: tuple[str, ...]
    coherence: float | None
    diagnostics: tuple[str, ...]


def _weighted_median(values: list[tuple[float, float]]) -> float:
    total_weight = sum(weight for _, weight in values)
    midpoint = total_weight / 2
    running = 0.0
    for value, weight in sorted(values, key=lambda item: item[0]):
        running += weight
        if running >= midpoint:
            return value
    return sorted(values, key=lambda item: item[0])[-1][0]


def _trimmed_mean(values: list[float], trim_fraction: float) -> float:
    if not values:
        raise ValueError("values cannot be empty")
    ordered = sorted(values)
    trim = int(len(ordered) * trim_fraction)
    trimmed = ordered[trim : len(ordered) - trim] if trim else ordered
    if not trimmed:
        trimmed = ordered
    return sum(trimmed) / len(trimmed)


class MarketConsensusBuilder:
    def __init__(self, config: ConsensusConfig | None = None) -> None:
        self.config = config or ConsensusConfig()

    def build(
        self,
        quotes: list[OddsQuote],
        *,
        as_of_time: datetime,
        method: str = "weighted_median",
    ) -> MarketConsensus:
        as_of = require_utc(as_of_time, "as_of_time")
        diagnostics: list[str] = []
        usable: list[tuple[OddsQuote, float]] = []
        for quote in quotes:
            if quote.bookmaker in self.config.excluded_bookmakers:
                diagnostics.append(f"EXCLUDED_BOOKMAKER:{quote.bookmaker}")
                continue
            if quote.suspended or quote.live:
                diagnostics.append(f"UNUSABLE_QUOTE:{quote.bookmaker}")
                continue
            age = max((as_of - quote.provider_updated_at).total_seconds(), 0.0)
            base_weight = (self.config.bookmaker_weights or {}).get(quote.bookmaker, 1.0)
            is_stale = quote.stale or age > self.config.max_staleness_seconds
            staleness_weight = 0.5 if is_stale else 1.0
            usable.append((quote, base_weight * staleness_weight))
        if len({quote.bookmaker for quote, _ in usable}) < self.config.min_bookmakers:
            return MarketConsensus(
                status="INSUFFICIENT_INPUT",
                method=method,
                fair_decimal_odds=None,
                effective_bookmakers=len({quote.bookmaker for quote, _ in usable}),
                dispersion=None,
                outliers=(),
                coherence=None,
                diagnostics=tuple(diagnostics + ["SINGLE_BOOKMAKER_NOT_FORMAL_CONSENSUS"]),
            )
        prices = [float(quote.decimal_odds) for quote, _ in usable]
        center = median(prices)
        deviations = [abs(price - center) for price in prices]
        mad = median(deviations) or 1e-9
        outliers = tuple(
            quote.bookmaker
            for quote, _ in usable
            if abs(float(quote.decimal_odds) - center) > 3 * mad
        )
        filtered = [(quote, weight) for quote, weight in usable if quote.bookmaker not in outliers]
        if not filtered:
            return MarketConsensus(
                status="INSUFFICIENT_INPUT",
                method=method,
                fair_decimal_odds=None,
                effective_bookmakers=0,
                dispersion=None,
                outliers=outliers,
                coherence=None,
                diagnostics=tuple(diagnostics + ["NO_EFFECTIVE_BOOKMAKERS_AFTER_FILTER"]),
            )
        if method == "median":
            value = median([float(quote.decimal_odds) for quote, _ in filtered])
        elif method == "trimmed_mean":
            value = _trimmed_mean(
                [float(quote.decimal_odds) for quote, _ in filtered],
                self.config.trim_fraction,
            )
        elif method == "weighted_median":
            value = _weighted_median(
                [(float(quote.decimal_odds), weight) for quote, weight in filtered]
            )
        else:
            raise ValueError(f"unsupported consensus method {method}")
        mean_price = sum(prices) / len(prices)
        variance = sum((price - mean_price) ** 2 for price in prices) / len(prices)
        dispersion = variance**0.5
        coherence = max(0.0, 1.0 - dispersion / max(mean_price, 1e-9))
        status = "READY" if not outliers and coherence >= 0.90 else "WATCH_ONLY"
        return MarketConsensus(
            status=status,
            method=method,
            fair_decimal_odds=Decimal(str(round(value, 6))),
            effective_bookmakers=len({quote.bookmaker for quote, _ in filtered}),
            dispersion=dispersion,
            outliers=outliers,
            coherence=coherence,
            diagnostics=tuple(diagnostics),
        )
