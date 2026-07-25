"""ARCH-P1-04D M2 remediation: the live dashboard card must pass through the
canonical top-level simulation from the source analysis card (never backfilled
from pricing_shadow, never recomputed), so the live reconciliation flips the
blocker fixtures from LEGACY_ONLY to MATCH.
"""

from __future__ import annotations

import copy
from typing import Any, cast

import pytest

from w2.dashboard.day_view import _simulation_projection
from w2.prematch.analysis_calculator import ReadModelService
from w2.prematch.read_model_projection import canonical_sha256
from w2.prematch.simulation_reconciliation import (
    LEGACY_ONLY,
    MATCH,
    MISMATCH,
    PublicSimulationReadViolation,
    reconcile_simulation,
)

_ROW = {
    "fixture_id": "F1",
    "status": None,
    "kickoff_utc": "2026-07-26T12:00:00+00:00",
    "competition_id": "C1",
}


def _service() -> ReadModelService:
    return ReadModelService(repository=cast(Any, object()))


def _make_card(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "fixture_id": "F1",
        "kickoff_utc": "2026-07-26T12:00:00+00:00",
        "markets": [],
        "primary_market": "",
        "current_odds": {},
        "market_candidates": {},
        "pricing_shadow": None,
        "decision_contract": None,
        "frozen_artifact_provenance": None,
        "home_cn": "主",
        "away_cn": "客",
        "generated_at": "2026-07-25T00:00:00Z",
        "simulation": None,
    }
    base.update(overrides)
    return base


def _sim(**extra: Any) -> dict[str, Any]:
    return {"status": "READY", "simulations": 10000, "seed": 7, **extra}


def _project(card: dict[str, Any]) -> dict[str, Any]:
    return _service()._dashboard_card_from_matchday(_ROW, analysis_override=card)


def test_live_card_passes_through_top_level_simulation_and_matches() -> None:
    sim = _sim()
    card = _make_card(simulation=dict(sim), pricing_shadow={"simulation": dict(sim)})

    out = _project(card)

    assert out["simulation"] == sim
    assert canonical_sha256(out["simulation"]) == canonical_sha256(card["simulation"])
    assert reconcile_simulation(out) == MATCH


def test_live_card_fails_closed_on_mismatch() -> None:
    top = _sim(seed=1)
    legacy = _sim(seed=2)
    card = _make_card(simulation=dict(top), pricing_shadow={"simulation": dict(legacy)})

    with pytest.raises(PublicSimulationReadViolation, match=MISMATCH):
        _project(card)


def test_live_card_fails_closed_when_only_pricing_shadow() -> None:
    card = _make_card(simulation=None, pricing_shadow={"simulation": _sim()})

    with pytest.raises(PublicSimulationReadViolation, match=LEGACY_ONLY):
        _project(card)


def test_live_card_preserves_insufficient_inputs_and_daytview_maps_unavailable() -> None:
    source = {"status": "INSUFFICIENT_INPUTS", "simulations": 0}
    card = _make_card(
        simulation=dict(source),
        pricing_shadow={"simulation": dict(source)},
    )

    out = _project(card)

    # Dashboard layer preserves the real source status verbatim (no promotion).
    assert out["simulation"] == source
    # DayView M1 projection maps it to UNAVAILABLE, never READY.
    assert _simulation_projection(out) == {
        "status": "UNAVAILABLE",
        "simulation": None,
        "source_status": "INSUFFICIENT_INPUTS",
    }


def test_live_projection_does_not_mutate_source_simulation() -> None:
    sim = _sim()
    card = _make_card(simulation=dict(sim), pricing_shadow={"simulation": dict(sim)})
    before = copy.deepcopy(card["simulation"])

    out = _project(card)

    assert card["simulation"] == before
    assert canonical_sha256(out["simulation"]) == canonical_sha256(before)


def test_match_and_top_only_keep_public_business_outputs_equal() -> None:
    simulation = _sim()
    matched = _project(
        _make_card(
            simulation=dict(simulation),
            pricing_shadow={"simulation": dict(simulation)},
        )
    )
    top_only = _project(_make_card(simulation=dict(simulation)))

    fields = (
        "recommendation",
        "scoreline_picks",
        "scoreline_reference",
        "scoreline_readiness",
        "formal_suppressed",
        "formal_suppressed_reason",
        "formal_recommendation",
        "candidate",
        "pick",
        "non_pick",
    )
    assert {field: matched.get(field) for field in fields} == {
        field: top_only.get(field) for field in fields
    }
