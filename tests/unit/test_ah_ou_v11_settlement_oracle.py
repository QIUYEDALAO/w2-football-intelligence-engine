"""Fixed examples calculated from independent split-stake arithmetic."""

from decimal import Decimal

import pytest

from w2.domain.odds import settle_asian_handicap, settle_total_goals
from w2.tracking.ah_ou_v3_postmatch import _net_units


@pytest.mark.parametrize(
    "market,score,side,line,outcome,net",
    [
        ("AH", (1, 1), "HOME", "+0.25", "HALF_WIN", "0.475"),
        ("AH", (1, 1), "HOME", "-0.25", "HALF_LOSS", "-0.5"),
        ("AH", (1, 1), "HOME", "+0.5", "WIN", "0.95"),
        ("AH", (1, 1), "HOME", "0", "PUSH", "0"),
        ("AH", (1, 1), "HOME", "-0.5", "LOSS", "-1"),
        ("AH", (0, 1), "AWAY", "+0.25", "WIN", "0.95"),
        ("OU", (2, 0), "OVER", "2.25", "HALF_LOSS", "-0.5"),
        ("OU", (2, 1), "OVER", "2.75", "HALF_WIN", "0.475"),
        ("OU", (2, 0), "OVER", "2.5", "LOSS", "-1"),
        ("OU", (2, 1), "OVER", "2.5", "WIN", "0.95"),
        ("OU", (2, 1), "UNDER", "3", "PUSH", "0"),
        ("OU", (2, 1), "UNDER", "2.75", "HALF_LOSS", "-0.5"),
    ],
)
def test_fixed_split_stake_oracle(market, score, side, line, outcome, net):
    # The expected columns above are literal split-stake results. No production
    # calculator is used to derive the oracle values.
    actual = (
        settle_asian_handicap(*score, side, Decimal(line))
        if market == "AH"
        else settle_total_goals(sum(score), side, Decimal(line))
    )
    assert actual.value == outcome
    assert _net_units(actual.value, Decimal("1.95")) == Decimal(net)
