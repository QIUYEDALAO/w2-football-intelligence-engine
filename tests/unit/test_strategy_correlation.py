from __future__ import annotations

from decimal import Decimal

from w2.strategy.candidate import GeneratedCandidate
from w2.strategy.correlation import low_correlation, select_uncorrelated_candidates


def candidate(
    *,
    market: str,
    selection: str,
    odds: str = "2.05",
) -> GeneratedCandidate:
    return GeneratedCandidate(
        fixture_id="1489404",
        decision="WATCH",
        market=market,
        selection=selection,
        line="2.5" if market == "TOTALS" else None,
        decimal_odds=Decimal(odds),
        bookmaker_count=4,
        hard_gate_reasons=(),
    )


def test_two_highly_correlated_candidates_keep_only_primary() -> None:
    first = candidate(market="TOTALS", selection="OVER")
    second = candidate(market="BTTS", selection="YES")

    selection = select_uncorrelated_candidates([first, second])

    assert low_correlation(first, second) is False
    assert selection.primary is not None
    assert selection.primary.candidate == first
    assert selection.backup is None
    assert selection.suppressed_count == 1
    assert selection.as_dict()["candidate"] is False
    assert selection.as_dict()["formal_recommendation"] is False


def test_low_correlation_candidate_is_retained_as_single_backup() -> None:
    first = candidate(market="TOTALS", selection="OVER")
    backup = candidate(market="ONE_X_TWO", selection="AWAY")
    extra = candidate(market="BTTS", selection="YES")

    selection = select_uncorrelated_candidates([first, backup, extra])

    assert low_correlation(first, backup) is True
    assert selection.primary is not None
    assert selection.primary.candidate == first
    assert selection.backup is not None
    assert selection.backup.candidate == backup
    assert selection.backup.role == "BACKUP"
    assert selection.suppressed_count == 1


def test_same_market_candidates_are_highly_correlated() -> None:
    first = candidate(market="ONE_X_TWO", selection="HOME")
    second = candidate(market="ONE_X_TWO", selection="DRAW")

    selection = select_uncorrelated_candidates([first, second])

    assert low_correlation(first, second) is False
    assert selection.primary is not None
    assert selection.backup is None
    assert selection.suppressed_count == 1
