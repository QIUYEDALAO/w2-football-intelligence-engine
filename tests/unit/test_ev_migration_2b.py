"""Migration checks against the frozen 2A corpus, not an alternate EV implementation."""
import json
from decimal import Decimal
from pathlib import Path

import pytest

from w2.domain.five_state_pricing import SettlementDistribution, expected_value
from w2.matchday.cards import _expected_value
from w2.strategy.simulate import ah_expected_value


def test_frozen_29601_rows_match_exactly() -> None:
    path = (
        Path(__file__).resolve().parents[2]
        / 'docs/review_packages/EV_CONTRACT_2A_20260906/differences.json'
    )
    rows = json.loads(path.read_text())['rows']
    assert len(rows) == 29601
    differences = []
    for row in rows:
        odds = Decimal(row['decimal_odds'])
        dist = SettlementDistribution(
            half_win_probability=Decimal(row['half_win']),
            full_loss_probability=Decimal(row['loss']),
        )
        canonical = expected_value(odds, dist)
        values = {k: getattr(dist, k) for k in dist.__dataclass_fields__}
        simulate = ah_expected_value(
            {
                'WIN': 0,
                'HALF_WIN': float(row['half_win']),
                'PUSH': 0,
                'HALF_LOSS': 0,
                'LOSS': float(row['loss']),
            },
            decimal_price=float(odds),
        )
        assert _expected_value(odds, values) == simulate == canonical == Decimal(row['canonical'])
        differences.append(abs(Decimal(row['simulate'])-canonical))
    assert sum(d != 0 for d in differences) == 7500
    assert max(differences) == Decimal('5e-7')


@pytest.mark.parametrize(
    'odds', [1, 0.9, float('nan'), float('inf'), float('-inf'), '1.95', None]
)
def test_simulate_rejects_bad_odds(odds: object) -> None:
    assert ah_expected_value(
        dict(WIN=1, HALF_WIN=0, PUSH=0, HALF_LOSS=0, LOSS=0), decimal_price=odds
    ) is None


@pytest.mark.parametrize(
    'loss',
    [Decimal('0.500000001001'), Decimal('-0.1'), Decimal('NaN'), Decimal('Infinity')],
)
def test_wrappers_reject_invalid_probabilities(loss: Decimal) -> None:
    dist = SettlementDistribution(full_win_probability=Decimal('0.5'), full_loss_probability=loss)
    with pytest.raises(ValueError):
        _expected_value(Decimal('2'), {k: getattr(dist,k) for k in dist.__dataclass_fields__})
    assert ah_expected_value(
        dict(WIN=Decimal('0.5'), HALF_WIN=0, PUSH=0, HALF_LOSS=0, LOSS=loss),
        decimal_price=2,
    ) is None
