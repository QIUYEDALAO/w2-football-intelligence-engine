"""One authority for whether a calibration may carry a formal recommendation.

It lives in ``w2.domain`` rather than ``w2.strategy`` for two reasons. Which
calibration states may carry authority is a domain invariant, not a strategy
computation. And ``tests/contract/test_api_projection_read_authority.py`` forbids
the API's transitive import graph from reaching ``w2.strategy``; ``lifecycle`` sits
on that graph, so the predicate has to live somewhere the read path may import.

Before this module the question had three answers in three places:

* ``analysis_calculator.model_probabilities`` called a probability calibrated only
  for ``PRODUCTION_VALIDATED`` and ``APPROVED_VALIDATED``;
* ``round3_intelligence._model_blockers`` also accepted ``READY``;
* ``lifecycle`` and ``market_candidate`` — the two paths that actually decide
  whether something becomes a formal candidate — never asked at all.

``READY`` is the status of the simulation pipeline: it means a distribution was
produced, not that the probability behind it was ever validated against outcomes.
Accepting it conflates "the model ran" with "the model is right", so it is absent
from the allowlist here and must not be reintroduced.

The rule this module enforces is narrow on purpose. An unvalidated calibration
stays fully available as **analysis evidence** — the distribution, EV, EV_SE and the
whole audit trail are still computed, stored and shown. What it may not do is form a
candidate, a confirmation, a lock, or a notification recommendation. Hiding the
evidence would be a different defect; the defect being fixed is that evidence
carried authority it never earned.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

#: A record that never carried a calibration status at all. Distinct from
#: BASELINE_PRIOR, which is a real declaration that the probability came from the
#: hand-set prior. Both fail closed, but conflating them loses the difference
#: between "we know it was unvalidated" and "we do not know what this was".
ABSENT_STATUS = "ABSENT"

RECOMMENDATION_BLOCKER = "MODEL_CALIBRATION_NOT_VALIDATED"
AUTHORITY_VERSION = "w2.domain.calibration_authority.v1"


#: Statuses that record a completed validation of the probability against outcomes.
#: Membership here is the only thing that authorises a formal recommendation.
RECOMMENDATION_VALIDATED_STATUSES = frozenset(
    {
        "PRODUCTION_VALIDATED",
        "APPROVED_VALIDATED",
    }
)

#: Statuses seen in the codebase that describe pipeline or provenance state rather
#: than a validation verdict. Listed so that adding one to the allowlist by mistake
#: is visibly a change of meaning rather than a typo.
NON_VALIDATION_STATUSES = frozenset(
    {
        "READY",          # the simulation produced a distribution
        "BASELINE_PRIOR",  # hand-set prior, never fitted
        "UNVALIDATED",
        "NOT_CALIBRATED",
        "NO_SETTLED_SAMPLE",
        "UNKNOWN",
        ABSENT_STATUS,
    }
)



def normalise_status(status: object) -> str:
    """Upper-cased status text. Absent or blank becomes ``ABSENT``.

    Absent used to normalise to ``BASELINE_PRIOR``, which failed closed correctly
    but destroyed an audit distinction: a record that declared the hand-set prior
    and a record that declared nothing are different facts about what was known.
    Both are inadmissible; only one of them tells you the pipeline was working.
    """
    text = "" if status is None else str(status).strip().upper()
    return text or ABSENT_STATUS


def recommendation_admissible(status: object) -> bool:
    """May a calibration in this state support a formal recommendation?"""
    return normalise_status(status) in RECOMMENDATION_VALIDATED_STATUSES


def recommendation_blocker(status: object) -> str | None:
    """``RECOMMENDATION_BLOCKER`` when the status cannot carry a recommendation."""
    return None if recommendation_admissible(status) else RECOMMENDATION_BLOCKER


def status_of(simulation: Mapping[str, Any] | None) -> str:
    """Read the calibration status off a simulation mapping, failing closed."""
    if not isinstance(simulation, Mapping):
        return normalise_status(None)
    return normalise_status(simulation.get("calibration_status"))


def evidence_record(status: object) -> dict[str, Any]:
    """The audit fields a decision record must carry about its calibration.

    The evaluation payload for fixture 1570340 contained no calibration field at
    all, so a reviewer reading the frozen record could not tell whether the
    probability behind a delivered recommendation had ever been validated. Every
    decision record now carries this.
    """
    normalised = normalise_status(status)
    return {
        "calibration_status_raw": None if status is None else str(status),
        "calibration_status": normalised,
        "calibration_recommendation_admissible": recommendation_admissible(normalised),
        "calibration_authority": AUTHORITY_VERSION,
    }
