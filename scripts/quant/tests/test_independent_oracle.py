"""Golden vectors for the independent settlement oracle."""
from __future__ import annotations

import importlib.util
from decimal import Decimal
from pathlib import Path

import pytest

# loaded by path, not as a package: the oracle must stay importable without any
# w2 or scripts package machinery on sys.path
_ORACLE_PATH = Path(__file__).resolve().parents[1] / "independent_settlement_oracle.py"
_spec = importlib.util.spec_from_file_location("w2_independent_settlement_oracle", _ORACLE_PATH)
assert _spec is not None and _spec.loader is not None
_oracle = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_oracle)
evaluate = _oracle.evaluate
settle = _oracle.settle


@pytest.mark.parametrize(("value", "expected"), [
    (Decimal("0.5"), "WIN"), (Decimal("0.25"), "HALF_WIN"), (Decimal("0"), "PUSH"),
    (Decimal("-0.25"), "HALF_LOSS"), (Decimal("-0.5"), "LOSS"),
])
def test_five_state_boundaries(value, expected):
    assert settle(value) == expected


@pytest.mark.parametrize(("score", "market", "selection", "line", "odds", "state", "profit"), [
    # Whole line: a one-goal win on -1 is a push.
    ("1-0", "ASIAN_HANDICAP", "HOME", -1, 1.95, "PUSH", "0"),
    # Quarter line: a draw on +0.25 is a half win.
    ("1-1", "ASIAN_HANDICAP", "HOME", 0.25, 2.00, "HALF_WIN", "0.50"),
    # Quarter line: a draw on -0.25 is a half loss.
    ("1-1", "ASIAN_HANDICAP", "HOME", -0.25, 2.00, "HALF_LOSS", "-0.5"),
    # Three-quarter line: winning by one on -0.75 is a half win.
    ("1-0", "ASIAN_HANDICAP", "HOME", -0.75, 1.90, "HALF_WIN", "0.45"),
    # exact_line belongs to the selected side. Away receiving +0.75 and losing
    # by one still covers; away giving 1.0 and winning by one is a push.
    ("0-1", "ASIAN_HANDICAP", "AWAY", 0.75, 1.90, "WIN", "0.90"),
    ("1-2", "ASIAN_HANDICAP", "AWAY", -0.5, 1.90, "WIN", "0.90"),
    ("2-1", "ASIAN_HANDICAP", "AWAY", 1.0, 1.90, "PUSH", "0"),
    ("3-3", "ASIAN_HANDICAP", "AWAY", 0.25, 1.90, "HALF_WIN", "0.45"),
    # Totals push and both directions.
    ("1-1", "TOTALS", "OVER", 2.0, 1.90, "PUSH", "0"),
    ("2-1", "TOTALS", "OVER", 2.25, 1.83, "WIN", "0.83"),
    ("1-1", "TOTALS", "OVER", 1.75, 1.90, "HALF_WIN", "0.45"),
    ("1-1", "TOTALS", "UNDER", 1.75, 1.90, "HALF_LOSS", "-0.5"),
    ("1-0", "TOTALS", "UNDER", 2.25, 1.83, "WIN", "0.83"),
])
def test_golden_vectors(score, market, selection, line, odds, state, profit):
    outcome, units = evaluate(score=score, market=market, selection=selection,
                              exact_line=line, decimal_odds=odds)
    assert outcome == state
    assert units == Decimal(profit)


def test_oracle_imports_nothing_from_production():
    import ast
    from pathlib import Path

    source = Path(__file__).resolve().parents[1] / "independent_settlement_oracle.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert "w2" not in imported, "the acceptance oracle must not import production code"
