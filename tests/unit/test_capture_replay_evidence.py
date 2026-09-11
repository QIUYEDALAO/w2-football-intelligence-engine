"""Replay saved JSON and check mapping against independent split-stake arithmetic."""
import copy
import json
from decimal import Decimal

import pytest

from w2.domain.odds import settle_asian_handicap, settle_total_goals
from w2.strategy.simulate import SimulationInputs, replay_simulation, run_simulation


def test_complete_simulation_json_roundtrip_and_tamper_rejection():
    inputs = SimulationInputs(
        fixture_id='replay', home_team_id='home', away_team_id='away',
        home_xg_for=1.73, home_xg_against=0.91,
        away_xg_for=1.12, away_xg_against=1.48,
        lambda_sigma_home=0.17, lambda_sigma_away=0.23,
        lambda_uncertainty_status='ANALYSIS_READY', neutral_site=True,
    )
    snapshot = json.loads(json.dumps(run_simulation(inputs, simulations=100).as_dict()))
    assert replay_simulation(snapshot).as_dict() == snapshot
    for field in SimulationInputs.__dataclass_fields__:
        broken = copy.deepcopy(snapshot)
        del broken['calibration']['replay_inputs'][field]
        with pytest.raises(ValueError, match='EVIDENCE_MISSING'):
            replay_simulation(broken)
    for section, key in [('calibration', 'params'), ('score_matrix_summary', 'distribution')]:
        broken = copy.deepcopy(snapshot)
        broken[section][key] = {}
        with pytest.raises(ValueError, match='REPLAY_MISMATCH'):
            replay_simulation(broken)


def test_mapping_against_independent_split_stake_oracle():
    # Integer quarter units avoid floating-point and do not call production
    # settlement logic to derive the expected outcome.
    outcomes = {-2: 'LOSS', -1: 'HALF_LOSS', 0: 'PUSH', 1: 'HALF_WIN', 2: 'WIN'}
    for home in range(8):
        for away in range(8):
            for quarter in range(-16, 17):
                legs = [quarter, quarter] if quarter % 2 == 0 else [quarter-1, quarter+1]
                for side in ('HOME', 'AWAY', 'OVER', 'UNDER'):
                    if side in ('HOME', 'AWAY'):
                        diff = home-away if side == 'HOME' else away-home
                        margins = [4*diff+leg for leg in legs]
                        actual = settle_asian_handicap(home, away, side, Decimal(quarter)/4)
                    else:
                        if quarter < 0:
                            continue
                        margins = [(4*(home+away)-leg)*(1 if side == 'OVER' else -1)
                                   for leg in legs]
                        actual = settle_total_goals(home+away, side, Decimal(quarter)/4)
                    signs = sum((v > 0)-(v < 0) for v in margins)
                    assert actual.value == outcomes[signs], (home, away, side, quarter)
