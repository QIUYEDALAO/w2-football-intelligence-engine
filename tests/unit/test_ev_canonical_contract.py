"""Offline executable contract. Validation below is NOT installed in production."""
from decimal import Decimal, localcontext

import pytest

from w2.domain.five_state_pricing import SettlementDistribution, expected_value
from w2.matchday.cards import _expected_value as cards_ev
from w2.strategy.simulate import ah_expected_value

KEYS = ("WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "LOSS")
FIELDS = tuple(SettlementDistribution.__dataclass_fields__)
TOLERANCE = Decimal("1e-9")  # Frozen 2A boundary, matching market_movement validation.


def contract_ev(odds: object, probabilities: dict[str, object]) -> Decimal:
    """Review-only validation harness; delegates ALL pricing to canonical."""
    if type(odds) is not Decimal or not odds.is_finite() or odds <= 1:
        raise ValueError("INVALID_DECIMAL_ODDS")
    if set(probabilities) != set(KEYS):
        raise ValueError("INVALID_PROBABILITY_KEYS")
    values = [probabilities[k] for k in KEYS]
    if any(type(v) is not Decimal or not v.is_finite() or not 0 <= v <= 1 for v in values):
        raise ValueError("INVALID_PROBABILITY")
    with localcontext() as context:
        context.prec = 28
        if abs(sum(values, Decimal(0)) - 1) > TOLERANCE:
            raise ValueError("INVALID_PROBABILITY_SUM")
        return expected_value(
            odds, SettlementDistribution(**dict(zip(FIELDS, values, strict=True)))
        )


def probabilities(*values: str) -> dict[str, Decimal]:
    return dict(zip(KEYS, map(Decimal, values), strict=True))


GOLDENS = [
    ("win", ("1", "0", "0", "0", "0"), "1.95", "0.95"),
    ("half_win", ("0", "1", "0", "0", "0"), "1.95", "0.475"),
    ("push", ("0", "0", "1", "0", "0"), "1.95", "0"),
    ("half_loss", ("0", "0", "0", "1", "0"), "1.95", "-0.5"),
    ("loss", ("0", "0", "0", "0", "1"), "1.95", "-1"),
    ("all_states", ("0.36", "0.12", "0.08", "0.14", "0.30"), "1.95", "0.029"),
    ("tiny", ("1e-20", "0", "0.99999999999999999999", "0", "0"), "2", "1e-20"),
    ("reported_boundary", ("0", "0.001", "0", "0", "0.999"), "1.193", "-0.9989035"),
    ("zero_gate", ("0.5000002", "0", "0", "0", "0.4999998"), "2", "0.0000004"),
]


@pytest.mark.parametrize("name,values,price,want", GOLDENS)
def test_golden(name: str, values: tuple[str, ...], price: str, want: str) -> None:
    p = probabilities(*values)
    actual = contract_ev(Decimal(price), p)
    assert actual == Decimal(want), name
    assert cards_ev(Decimal(price), dict(zip(FIELDS, p.values(), strict=True))) == actual


@pytest.mark.parametrize("price", [Decimal("1"), Decimal("0.99"), Decimal("NaN"),
                                  Decimal("Infinity"), Decimal("-Infinity"), "1.95", 1.95, None])
def test_invalid_odds_fail_closed(price: object) -> None:
    with pytest.raises(ValueError, match="INVALID_DECIMAL_ODDS"):
        contract_ev(price, probabilities("1", "0", "0", "0", "0"))


@pytest.mark.parametrize("bad", [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity"),
                                Decimal("-1e-20"), Decimal("1.0000000001"), None, "1", 1.0])
def test_invalid_probability_fail_closed(bad: object) -> None:
    p = dict(probabilities("1", "0", "0", "0", "0"))
    p["WIN"] = bad
    with pytest.raises(ValueError, match="INVALID_PROBABILITY"):
        contract_ev(Decimal("2"), p)


@pytest.mark.parametrize("delta", ["0.000000001", "-0.000000001"])
def test_tolerance_is_inclusive_without_normalization(delta: str) -> None:
    p = probabilities("0.5", "0", "0", "0", "0.5")
    p["LOSS"] += Decimal(delta)
    assert contract_ev(Decimal("2"), p) == -Decimal(delta)


@pytest.mark.parametrize("delta", ["0.000000001001", "-0.000000001001"])
def test_outside_tolerance_fails(delta: str) -> None:
    p = probabilities("0.5", "0", "0", "0", "0.5")
    p["LOSS"] += Decimal(delta)
    with pytest.raises(ValueError, match="INVALID_PROBABILITY_SUM"):
        contract_ev(Decimal("2"), p)


@pytest.mark.parametrize("key", KEYS)
def test_missing_state_fails(key: str) -> None:
    p = probabilities("1", "0", "0", "0", "0")
    del p[key]
    with pytest.raises(ValueError, match="INVALID_PROBABILITY_KEYS"):
        contract_ev(Decimal("2"), p)


def test_known_float_difference_not_hidden_by_rounding() -> None:
    p = probabilities("0", "0.001", "0", "0", "0.999")
    old = -0.998903  # Frozen 2A legacy output, not runtime authority.
    assert ah_expected_value(
        {k: float(v) for k, v in p.items()}, decimal_price=1.193
    ) == contract_ev(Decimal("1.193"), p)
    new = contract_ev(Decimal("1.193"), p)
    assert old == -0.998903
    assert new == Decimal("-0.9989035")
    assert Decimal(str(old)) - new == Decimal("0.0000005")


def test_existing_positive_ev_gate_changes_on_synthetic_boundary() -> None:
    p = probabilities("0.5000002", "0", "0", "0", "0.4999998")
    old = 0.0  # Frozen 2A legacy output.
    assert ah_expected_value(
        {k: float(v) for k, v in p.items()}, decimal_price=2.0
    ) == contract_ev(Decimal("2"), p)
    new = contract_ev(Decimal("2"), p)
    assert old == 0.0 and new == Decimal("0.0000004")
    assert (old > 0) is False and (new > 0) is True


def test_formal_recompute_guard_changes_without_patching_production() -> None:
    # SYNTHETIC_EV_2A_GUARD / ASIAN_HANDICAP / HOME. Exact existing guard predicate.
    p = probabilities("0", "0.001", "0", "0", "0.999")
    old = -0.998903  # Frozen 2A legacy output, not runtime authority.
    assert ah_expected_value(
        {k: float(v) for k, v in p.items()}, decimal_price=1.193
    ) == contract_ev(Decimal("1.193"), p)
    new = contract_ev(Decimal("1.193"), p)
    declared = Decimal("-0.9989043")
    assert abs(old - float(declared)) > 0.000001
    assert abs(new - declared) <= Decimal("0.000001")
