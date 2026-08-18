"""Pre-registered evaluation opportunities for the candidate funnel.

The funnel's denominator is *not* the collection ladder and *not* the projection
refresh count.  It is the set of moments the system committed, in advance, to
evaluating a fixture at.  Those are different things: the ladder also contains
lineup retries and discovery sweeps that never constitute a candidate decision,
and a projection refresh is a read, not an opportunity.

Recording anything else measures the scheduler's cadence instead of the match's
chances.  Fixture 1494246 evaluated at five slots across two markets, so its
honest denominator is ten -- not fourteen ladder entries, and not the dozens of
refreshes that touched it.
"""

from __future__ import annotations

from typing import Final

EVALUATION_POLICY_V1: Final = "candidate-eval.v1"

# Only checkpoints that both refresh odds and are expected to run a full
# gate + Decision V4 pass belong here.  Lineup-only retries are inputs to a
# slot, never a slot: promoting them would inflate the denominator with
# opportunities the system never intended to take.
EVALUATION_SLOTS: Final[dict[str, tuple[str, ...]]] = {
    EVALUATION_POLICY_V1: (
        "T3_ODDS",
        "T60_ODDS_LINEUPS",
        "T45_ODDS",
        "T-30m_VALIDATION_LOCK",
        "T15_ODDS",
    ),
}

CURRENT_EVALUATION_POLICY: Final = EVALUATION_POLICY_V1


class EvaluationSlotError(ValueError):
    """Raised when a denominator write cannot name its authoritative slot."""


def evaluation_slots(policy_version: str = CURRENT_EVALUATION_POLICY) -> tuple[str, ...]:
    try:
        return EVALUATION_SLOTS[policy_version]
    except KeyError:
        raise EvaluationSlotError(
            f"EVALUATION_POLICY_NOT_REGISTERED:{policy_version}"
        ) from None


def is_evaluation_slot(
    checkpoint: str, *, policy_version: str = CURRENT_EVALUATION_POLICY
) -> bool:
    return checkpoint in evaluation_slots(policy_version)


def require_evaluation_slot(
    checkpoint: str | None, *, policy_version: str = CURRENT_EVALUATION_POLICY
) -> str:
    """Fail closed: an unnamed checkpoint must never become a denominator row.

    The previous implementation inferred the checkpoint from the projected card
    and fell back to the literal ``"capture"`` when the market timeline was
    empty.  For a fixture whose odds had already stopped that produced a row
    claiming zero bookmakers at a checkpoint that was never observed.
    """

    resolved = str(checkpoint or "").strip()
    if not resolved:
        raise EvaluationSlotError("EVALUATION_SLOT_UNRESOLVED")
    if not is_evaluation_slot(resolved, policy_version=policy_version):
        raise EvaluationSlotError(f"EVALUATION_SLOT_NOT_REGISTERED:{resolved}")
    return resolved


def expected_opportunity_count(
    *, markets: int, policy_version: str = CURRENT_EVALUATION_POLICY
) -> int:
    return len(evaluation_slots(policy_version)) * markets
