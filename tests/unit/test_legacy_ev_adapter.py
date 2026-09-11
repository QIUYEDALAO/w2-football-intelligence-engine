from copy import deepcopy
from decimal import Decimal

import pytest

from w2.matchday.cards import ResearchCardBuilder, _distribution_from_value_row, _expected_value
from w2.matchday.legacy_ev import VERSION, adapt_legacy_value_row


def legacy_row():
    return dict(market="BTTS", selection="YES", line=None, executable_odds="2.2",
                model_probability=0.49, settlement_probabilities={"YES": 0.49})


def test_safe_binary_mapping_keeps_raw_and_uses_canonical():
    original = legacy_row()
    before = deepcopy(original)
    adapted = adapt_legacy_value_row(original, source="offline/model_output.json")
    audit = adapted["legacy_compatibility"]
    assert original == before == audit["original_payload"]
    assert audit["version"] == VERSION and audit["role"] == "HISTORY_ONLY"
    assert audit["source"] == "offline/model_output.json"
    assert audit["status"] == "READY"
    assert _expected_value(
        Decimal("2.2"), _distribution_from_value_row(adapted)
    ) == Decimal("0.078")


def test_complete_new_five_state_needs_no_legacy_adapter():
    row = dict(settlement_probabilities=dict(win="0.5", half_win="0", push="0",
                                            half_loss="0", loss="0.5"))
    assert _expected_value(Decimal("2"), _distribution_from_value_row(row)) == 0
    assert "legacy_compatibility" not in row


@pytest.mark.parametrize("market,line,values", [
    ("ASIAN_HANDICAP", "0.75", {"win": 0.47, "half_loss": 0.25, "loss": 0.28}),
    ("TOTALS", "2", {"YES": 0.49}),
    ("BTTS", None, {"YES": float("nan")}),
    ("BTTS", None, {}),
])
def test_unmappable_legacy_never_gets_ev(market,line,values):
    row = legacy_row()
    row.update(market=market,line=line,settlement_probabilities=values)
    adapted = adapt_legacy_value_row(row, source="offline")
    assert adapted["legacy_compatibility"]["status"] == "NOT_READY"
    ranked = ResearchCardBuilder()._ranking(normalized_rows=[],value_rows=[row],
                                           data_quality="READY",legacy_source="offline")
    assert ranked[0]["raw_ev"] is None and ranked[0]["status"] == "NOT_READY"
    assert ranked[0]["legacy_compatibility"]["reason"]
    assert ranked[0]["formal_recommendation"] is False


def test_canonical_entry_does_not_use_legacy_fallback():
    with pytest.raises(ValueError,match="INVALID_PROBABILITY_KEYS"):
        ResearchCardBuilder()._ranking(normalized_rows=[],value_rows=[legacy_row()],data_quality="READY")


def test_complete_legacy_mapping_is_validated():
    row=legacy_row()
    row["settlement_probabilities"]=dict(win="0.5",half_win="0",push="0",half_loss="0",loss="0.5")
    assert (
        adapt_legacy_value_row(row, source="offline")["legacy_compatibility"]["status"]
        == "READY"
    )
    row["settlement_probabilities"]["loss"]="0.500000002"
    assert (
        adapt_legacy_value_row(row, source="offline")["legacy_compatibility"]["status"]
        == "NOT_READY"
    )
