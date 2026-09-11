"""Migration checks against the frozen 2A corpus, not an alternate EV implementation."""
import hashlib
import json
from decimal import Decimal

import pytest

from w2.domain.five_state_pricing import SettlementDistribution, expected_value
from w2.matchday.cards import _expected_value
from w2.strategy.simulate import ah_expected_value

# The 2A corpus is an 8.8MB artifact that was never committed. A test that read
# it out of docs/ therefore passed only on the one machine that happened to hold
# the file and failed on every clean checkout, CI included.
#
# The grid is fully determined by its own generator, so it is rebuilt here and
# pinned to the byte length and SHA-256 of the original artifact. That is not a
# weaker check than reading the file: the hash is what makes it exact, and
# unlike the file it holds everywhere.
FROZEN_2A_CORPUS_SHA256 = 'd5d5a987a49ecc5fec2ed6351328daf5a99e2468f796414120fd5d56b1c75feb'
FROZEN_2A_CORPUS_BYTES = 9261289
FROZEN_2A_GATE_COUNTEREXAMPLE = {
    'fixture': 'SYNTHETIC_EV_2A_GUARD',
    'market': 'ASIAN_HANDICAP',
    'selection': 'HOME',
    'declared_ev': '-0.9989043',
    'old_recomputed': '-0.998903',
    'canonical_recomputed': '-0.9989035',
    'existing_conflict_tolerance': '0.000001',
    'old_guard': 'REJECT',
    'new_guard': 'PASS',
    'scope': (
        'formal_recommendation._candidate_evaluation EV conflict predicate '
        'ONLY; not end-to-end recommendation'
    ),
}


def _legacy_simulate(half_win: Decimal, loss: Decimal, decimal_odds: Decimal) -> str:
    """The pre-migration simulate formula, frozen exactly as 2A computed it.

    Kept in float arithmetic on purpose. It is the behaviour the migration
    changed, so reproducing it in Decimal would erase the very difference this
    corpus exists to record.
    """
    return str(round(float(half_win) * ((float(decimal_odds) - 1) / 2) - float(loss), 6))


def _rebuild_frozen_2a_corpus() -> tuple[dict[str, object], list[dict[str, str]], list[Decimal]]:
    """Regenerate the 99x299 grid and check all three implementations per cell."""
    rows: list[dict[str, str]] = []
    deltas: list[Decimal] = []
    cards_differences = 0
    simulate_differences = 0
    six_place_differences = 0

    for i in range(1, 100):
        half_win = Decimal(i) / 1000
        loss = 1 - half_win
        for j in range(1001, 1300):
            decimal_odds = Decimal(j) / 1000
            dist = SettlementDistribution(
                half_win_probability=half_win,
                full_loss_probability=loss,
            )
            values = {k: getattr(dist, k) for k in dist.__dataclass_fields__}
            canonical = expected_value(decimal_odds, dist)
            cards = _expected_value(decimal_odds, values)
            simulate = ah_expected_value(
                {
                    'WIN': 0,
                    'HALF_WIN': float(half_win),
                    'PUSH': 0,
                    'HALF_LOSS': 0,
                    'LOSS': float(loss),
                },
                decimal_price=float(decimal_odds),
            )
            # The three current implementations must agree cell by cell.
            assert cards == simulate == canonical

            legacy = _legacy_simulate(half_win, loss, decimal_odds)
            delta = Decimal(legacy) - canonical
            deltas.append(abs(delta))
            cards_differences += cards != canonical
            simulate_differences += Decimal(legacy) != canonical
            six_place_differences += round(float(canonical), 6) != float(legacy)
            rows.append({
                'fixture': f'SYNTHETIC_GRID_{i}_{j}',
                'market': 'ASIAN_HANDICAP',
                'selection': 'HOME',
                'half_win': str(half_win),
                'loss': str(loss),
                'decimal_odds': str(decimal_odds),
                'cards': str(cards),
                'simulate': legacy,
                'canonical': str(canonical),
                'delta': str(delta),
            })

    summary: dict[str, object] = {
        'corpus': 'SYNTHETIC_ONLY_NOT_PRODUCTION',
        'count': len(rows),
        'cards_numeric_differences': cards_differences,
        'simulate_numeric_differences': simulate_differences,
        'max_abs_simulate_delta': str(max(deltas)),
        'six_place_projection_differences_diagnostic_only': six_place_differences,
        'real_fixture_gate_changes': 'NOT_ASSESSED_NO_FROZEN_CORPUS',
        'gate_counterexample': FROZEN_2A_GATE_COUNTEREXAMPLE,
        'status': 'EV_MIGRATION_BLOCKED_BEHAVIOR_CHANGE',
    }
    return summary, rows, deltas


def test_frozen_29601_rows_match_exactly() -> None:
    summary, rows, deltas = _rebuild_frozen_2a_corpus()
    assert len(rows) == 29601

    payload = json.dumps({'summary': summary, 'rows': rows}, indent=2) + '\n'
    raw = payload.encode('utf-8')
    # Byte length and digest of the original 2A artifact. If any cell, field,
    # field order or formatting drifts, this fails.
    assert len(raw) == FROZEN_2A_CORPUS_BYTES
    assert hashlib.sha256(raw).hexdigest() == FROZEN_2A_CORPUS_SHA256

    assert summary['corpus'] == 'SYNTHETIC_ONLY_NOT_PRODUCTION'
    assert summary['count'] == 29601
    assert summary['cards_numeric_differences'] == 0
    assert summary['simulate_numeric_differences'] == 7500
    assert summary['max_abs_simulate_delta'] == '5E-7'
    assert summary['six_place_projection_differences_diagnostic_only'] == 2173
    assert summary['status'] == 'EV_MIGRATION_BLOCKED_BEHAVIOR_CHANGE'

    assert sum(d != 0 for d in deltas) == 7500
    assert max(deltas) == Decimal('5e-7')


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
