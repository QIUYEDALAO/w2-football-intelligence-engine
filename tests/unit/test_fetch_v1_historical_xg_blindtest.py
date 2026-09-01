from scripts.fetch_v1_historical_xg_blindtest import _numeric_xg


def test_numeric_xg_keeps_only_two_numeric_expected_goals() -> None:
    payload = {
        "response": [
            {"team": {"id": 1}, "statistics": [{"type": "Expected Goals", "value": "1.25"}]},
            {"team": {"id": 2}, "statistics": [{"type": "Expected Goals", "value": 0.75}]},
        ]
    }

    assert _numeric_xg(payload) == {"1": 1.25, "2": 0.75}


def test_numeric_xg_rejects_null_and_unrelated_fields() -> None:
    payload = {
        "response": [
            {
                "team": {"id": 1},
                "statistics": [
                    {"type": "Expected Goals", "value": None},
                    {"type": "Total Shots", "value": 9},
                ],
            }
        ]
    }

    assert _numeric_xg(payload) == {}
