from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from w2.dashboard import day_view, scorelines
from w2.prematch import analysis_calculator
from w2.prematch.simulation_reconciliation import PublicSimulationReadViolation
from w2.tracking import formal_results


def test_all_public_simulation_consumers_use_canonical_reader() -> None:
    consumers = (
        day_view._scoreline_simulations,
        scorelines._simulation_from_card,
        analysis_calculator.run_simulation_from_card,
        analysis_calculator.ReadModelService._dashboard_scoreline_readiness,
        formal_results._simulation_evidence,
    )
    for consumer in consumers:
        source = inspect.getsource(consumer)
        assert "canonical_public_simulation" in source
        assert "pricing_shadow" not in source

    dashboard_source = inspect.getsource(
        analysis_calculator.ReadModelService._dashboard_card_from_matchday
    )
    assert "simulation=run_simulation_from_card(card)" in dashboard_source
    assert "run_simulation_from_shadow" not in dashboard_source


def test_legacy_shadow_deserializer_has_no_runtime_callers() -> None:
    src_root = Path(__file__).resolve().parents[2] / "src"
    callers = []
    for path in src_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        if any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "run_simulation_from_shadow"
            for node in ast.walk(tree)
        ):
            callers.append(path.relative_to(src_root).as_posix())
    assert callers == []


def test_formal_simulation_evidence_fails_closed_on_legacy_only() -> None:
    with pytest.raises(PublicSimulationReadViolation, match="LEGACY_ONLY"):
        formal_results._simulation_evidence(
            {
                "fixture_id": "formal-legacy",
                "pricing_shadow": {
                    "simulation": {"status": "READY", "simulations": 10000}
                },
            }
        )
