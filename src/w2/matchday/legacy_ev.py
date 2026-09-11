"""Versioned offline snapshot adapter. Never a production read fallback."""
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from typing import Any

from w2.domain.five_state_pricing import SettlementDistribution, validate_ev_inputs

VERSION = "w2.legacy-snapshot-ev-adapter.v1"
KEYS = ("win", "half_win", "push", "half_loss", "loss")


def adapt_legacy_value_row(row: dict[str, Any], *, source: str) -> dict[str, Any]:
    result = deepcopy(row)
    audit = {
        "version": VERSION, "source": source, "role": "HISTORY_ONLY",
        "original_payload": deepcopy(row), "status": "NOT_READY", "reason": "UNMAPPABLE_STATES",
    }
    result["legacy_compatibility"] = audit
    values = row.get("settlement_probabilities")
    if not isinstance(values, dict):
        return result
    try:
        if set(values) == set(KEYS):
            probabilities = [Decimal(str(values[k])) for k in KEYS]
            reason = "EXPLICIT_FIVE_STATE_RENAME"
        elif set(values) == {row.get("selection")}:
            market = row.get("market")
            selection = row.get("selection")
            binary = (market == "ONE_X_TWO" and selection in {"HOME", "DRAW", "AWAY"}) or (
                market == "BTTS" and selection in {"YES", "NO"}
            ) or (
                market == "TOTALS" and selection in {"OVER", "UNDER"}
                and Decimal(str(row.get("line"))).is_finite()
                and Decimal(str(row.get("line"))) % 1 == Decimal("0.5")
            )
            if not binary:
                return result
            win = Decimal(str(values[selection]))
            if Decimal(str(row.get("model_probability"))) != win:
                audit["reason"] = "CONFLICTING_BINARY_PROBABILITY"
                return result
            probabilities = [win, Decimal(0), Decimal(0), Decimal(0), 1-win]
            reason = "EXPLICIT_NO_PUSH_BINARY_SELECTION"
        else:
            return result
        distribution = SettlementDistribution(**dict(zip(
            SettlementDistribution.__dataclass_fields__, probabilities, strict=True,
        )))
        validate_ev_inputs(Decimal(str(row.get("executable_odds"))), distribution)
    except (InvalidOperation, ValueError, TypeError) as exc:
        audit["reason"] = "INVALID_LEGACY_INPUT:" + type(exc).__name__ + ":" + str(exc)
        return result
    result["settlement_probabilities"] = dict(zip(KEYS, probabilities, strict=True))
    audit.update(status="READY", reason=reason)
    return result
