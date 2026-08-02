"""Read-only reconciliation between the canonical top-level card simulation and
the legacy ``pricing_shadow`` simulation.

ARCH-P1-04D M2. This module only classifies; it never switches reads, mutates
cards, or removes any compatibility chain. The comparison is a full-object
``canonical_sha256`` equality, never a ``simulations`` count or partial-field
comparison.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from w2.domain.canonical_serialization import HashDomain
from w2.prematch.read_model_projection import canonical_sha256

MATCH = "MATCH"
TOP_LEVEL_ONLY = "TOP_LEVEL_ONLY"
LEGACY_ONLY = "LEGACY_ONLY"
BOTH_UNAVAILABLE = "BOTH_UNAVAILABLE"
MISMATCH = "MISMATCH"

RECONCILIATION_STATUSES = (
    MATCH,
    TOP_LEVEL_ONLY,
    LEGACY_ONLY,
    BOTH_UNAVAILABLE,
    MISMATCH,
)


class PublicSimulationReadViolation(RuntimeError):
    """Canonical public simulation is missing, contradictory, or malformed."""


def _present(value: Any) -> bool:
    return isinstance(value, Mapping) and bool(value)


def _legacy_simulation(card: Mapping[str, Any]) -> Any:
    pricing_shadow = card.get("pricing_shadow")
    if isinstance(pricing_shadow, Mapping):
        return pricing_shadow.get("simulation")
    return None


def reconcile_simulation(card: Mapping[str, Any]) -> str:
    """Classify a card by full-object reconciliation of its two simulation sources.

    Compares the canonical top-level ``card["simulation"]`` against the legacy
    ``card["pricing_shadow"]["simulation"]``:

    * both present and ``canonical_sha256`` equal -> ``MATCH``
    * only the top-level present -> ``TOP_LEVEL_ONLY``
    * only the legacy present -> ``LEGACY_ONLY``
    * neither present -> ``BOTH_UNAVAILABLE``
    * both present but full-object hashes differ -> ``MISMATCH``
    """
    top = card.get("simulation")
    legacy = _legacy_simulation(card)
    top_present = _present(top)
    legacy_present = _present(legacy)
    if top_present and legacy_present:
        domain = HashDomain.PREMATCH_READ_MODEL_SIMULATION_RECONCILIATION
        return (
            MATCH
            if canonical_sha256(top, domain=domain) == canonical_sha256(legacy, domain=domain)
            else MISMATCH
        )
    if top_present:
        return TOP_LEVEL_ONLY
    if legacy_present:
        return LEGACY_ONLY
    return BOTH_UNAVAILABLE


def canonical_public_simulation(card: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """Return only the canonical top-level simulation."""
    identity = str(card.get("fixture_id") or "UNKNOWN")
    simulation = card.get("simulation")
    if simulation is None or simulation == {}:
        return None
    if not isinstance(simulation, Mapping):
        raise PublicSimulationReadViolation(
            f"PUBLIC_SIMULATION_INVALID:{identity}:UNKNOWN_STATE"
        )
    if simulation.get("status") not in {"READY", "INSUFFICIENT_INPUTS"}:
        raise PublicSimulationReadViolation(
            f"PUBLIC_SIMULATION_INVALID:{identity}:UNKNOWN_STATE"
        )
    return simulation
