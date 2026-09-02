"""Single economic admission contract shared by V1 evaluation paths."""

from __future__ import annotations

from w2.domain.five_state_pricing import MIN_CASHFLOW_PRICE_EDGE

ECONOMIC_ADMISSION_CONTRACT_VERSION = "w2.economic_admission.cashflow.v1"
MIN_CASHFLOW_PRICE_EDGE_FLOAT = float(MIN_CASHFLOW_PRICE_EDGE)
ECONOMIC_ADMISSION_FEATURE_ENABLED = False
ECONOMIC_ADMISSION_STATUS = "RETIRED_PRODUCT_SEMANTICS"
ECONOMIC_ADMISSION_REASON = "NO_VALIDATED_MARKET_EDGE"
ECONOMIC_ADMISSION_REACTIVATION_REQUIRES = (
    "NEW_PREREGISTRATION",
    "NEW_UNSEEN_COHORT",
    "OWNER_AUTHORIZATION",
)


def economic_admission_pass(
    *,
    expected_value: float | None,
    ev_minus_se: float | None,
    cashflow_price_edge: float | None,
) -> bool:
    """Return whether the persisted five-state economic gates all pass.

    Probability delta is intentionally diagnostic only; using it here would
    recreate the split contract that previously allowed lifecycle and market
    candidate paths to disagree.
    """
    return bool(
        expected_value is not None
        and expected_value > 0
        and ev_minus_se is not None
        and ev_minus_se > 0
        and cashflow_price_edge is not None
        and cashflow_price_edge >= MIN_CASHFLOW_PRICE_EDGE_FLOAT
    )
