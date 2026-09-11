"""The removed execution surfaces must not silently return as dormant features."""
import tomllib
from importlib.util import find_spec
from pathlib import Path

from w2.domain.factor_registry import ALLOWED_INDEPENDENT_FACTORS, load_factor_registry
from w2.matchday import cards, intake_v2
from w2.pricing.team_score import independent_team_scores


def test_retired_execution_entries_are_absent_but_ingestion_contracts_remain():
    assert find_spec("w2.matchday.cli") is None
    assert find_spec("w2.matchday.orchestrator") is None
    assert not hasattr(cards, "DailyMatchdayCycle")
    assert not hasattr(intake_v2, "execute_matchday_intake")
    assert callable(intake_v2.endpoint_capture_contract)
    assert callable(intake_v2.normalize_matchday_odds_payload)
    project = tomllib.loads(Path("pyproject.toml").read_text())
    assert "w2-matchday" not in project["project"]["scripts"]


def test_old_ready_contributions_cannot_reenable_retired_factors():
    ids = {"F7_STRENGTH_FORM", "F8_SQUAD_VALUE"}
    assert not ids.intersection(ALLOWED_INDEPENDENT_FACTORS)
    assert not ids.intersection(load_factor_registry())
    score = independent_team_scores(feature_contributions=[
        {"id": factor, "status": "READY", "weight": 100, "score": 1,
         "side": "HOME", "source_group": group, "is_independent_signal": True}
        for factor, group in [("F7_STRENGTH_FORM", "ratings"), ("F8_SQUAD_VALUE", "squad_value")]
    ])
    assert score["weight_sum_used"] == 0
    assert score["scoring_factors"] == []
