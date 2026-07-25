from __future__ import annotations

import pytest

from w2.prematch.simulation_reconciliation import (
    BOTH_UNAVAILABLE,
    LEGACY_ONLY,
    MATCH,
    MISMATCH,
    TOP_LEVEL_ONLY,
    PublicSimulationReadViolation,
    canonical_public_simulation,
    reconcile_simulation,
)


def _sim(**extra: object) -> dict[str, object]:
    return {"status": "READY", "simulations": 10000, "seed": 7, **extra}


def test_reconcile_match_when_both_present_and_hash_equal() -> None:
    sim = _sim()
    card = {"simulation": dict(sim), "pricing_shadow": {"simulation": dict(sim)}}
    assert reconcile_simulation(card) == MATCH


def test_reconcile_top_level_only() -> None:
    card = {"simulation": _sim(), "pricing_shadow": {}}
    assert reconcile_simulation(card) == TOP_LEVEL_ONLY


def test_reconcile_legacy_only() -> None:
    card = {"pricing_shadow": {"simulation": _sim()}}
    assert reconcile_simulation(card) == LEGACY_ONLY


def test_reconcile_both_unavailable() -> None:
    assert reconcile_simulation({}) == BOTH_UNAVAILABLE
    assert reconcile_simulation({"simulation": {}, "pricing_shadow": {"simulation": {}}}) == (
        BOTH_UNAVAILABLE
    )


def test_reconcile_mismatch_when_full_objects_differ() -> None:
    card = {
        "simulation": _sim(seed=1),
        "pricing_shadow": {"simulation": _sim(seed=2)},
    }
    assert reconcile_simulation(card) == MISMATCH


def test_reconcile_uses_full_object_not_only_simulations_count() -> None:
    # Same simulations count but a different inner field must be MISMATCH, proving
    # the comparison is a full-object hash rather than a count-only check.
    card = {
        "simulation": _sim(fair_ah={"line": "-0.25"}),
        "pricing_shadow": {"simulation": _sim(fair_ah={"line": "-0.75"})},
    }
    assert reconcile_simulation(card) == MISMATCH


def test_public_reader_uses_canonical_top_level_for_match_and_top_only() -> None:
    simulation = _sim()
    assert canonical_public_simulation(
        {"simulation": simulation, "pricing_shadow": {"simulation": dict(simulation)}}
    ) == simulation
    assert canonical_public_simulation({"simulation": simulation}) == simulation


@pytest.mark.parametrize(
    ("card", "reason"),
    [
        ({"pricing_shadow": {"simulation": _sim()}}, LEGACY_ONLY),
        (
            {
                "simulation": _sim(seed=1),
                "pricing_shadow": {"simulation": _sim(seed=2)},
            },
            MISMATCH,
        ),
        ({"simulation": {"status": "PENDING"}}, "UNKNOWN_STATE"),
    ],
)
def test_public_reader_fails_closed_on_legacy_mismatch_or_unknown(
    card: dict[str, object],
    reason: str,
) -> None:
    with pytest.raises(PublicSimulationReadViolation, match=reason):
        canonical_public_simulation(card)
