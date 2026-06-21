from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, kw_only=True)
class MarketQuality:
    liquidity: str
    bookmaker_coverage: str
    freshness: str
    dispersion: str
    conflict: str
    status: str


class MarketQualityAssessor:
    def assess(
        self,
        *,
        bookmaker_count: int,
        stale_fraction: float,
        dispersion: float,
        coherence: float,
    ) -> MarketQuality:
        liquidity = "LOW" if bookmaker_count < 2 else "MEDIUM" if bookmaker_count < 5 else "HIGH"
        coverage = (
            "BLOCKED" if bookmaker_count == 0 else "WATCH" if bookmaker_count < 2 else "READY"
        )
        freshness = (
            "STALE" if stale_fraction > 0.5 else "WATCH" if stale_fraction > 0.2 else "FRESH"
        )
        dispersion_status = (
            "HIGH" if dispersion > 0.35 else "MEDIUM" if dispersion > 0.15 else "LOW"
        )
        conflict = "HIGH" if coherence < 0.75 else "MEDIUM" if coherence < 0.90 else "LOW"
        if coverage == "BLOCKED" or freshness == "STALE" or conflict == "HIGH":
            status = "BLOCKED"
        elif coverage == "WATCH" or freshness == "WATCH" or dispersion_status == "HIGH":
            status = "WATCH_ONLY"
        else:
            status = "READY"
        return MarketQuality(
            liquidity=liquidity,
            bookmaker_coverage=coverage,
            freshness=freshness,
            dispersion=dispersion_status,
            conflict=conflict,
            status=status,
        )
