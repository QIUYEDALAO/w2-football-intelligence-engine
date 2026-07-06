from __future__ import annotations

from w2.competitions.odds_market_mapping import (
    bookmaker_observed_evidence,
    normalize_market_name,
    normalize_odds_markets,
)


def test_market_name_aliases_normalize_to_ah_and_ou() -> None:
    assert normalize_market_name("Asian Handicap") == "AH"
    assert normalize_market_name("Handicap Result") == "AH"
    assert normalize_market_name("Asian Handicap First Half") == "AH"
    assert normalize_market_name("Goals Over/Under") == "OU"
    assert normalize_market_name("Over/Under") == "OU"
    assert normalize_market_name("Total Goals") == "OU"
    assert normalize_market_name("Match Goals") == "OU"
    assert normalize_market_name("Match Winner") == "OTHER"


def test_flat_rows_extract_ah_ou_lines_and_bookmaker_count() -> None:
    evidence = bookmaker_observed_evidence(
        [
            {"bookmaker": "b1", "market": "Handicap Result", "line": "-0.25"},
            {"bookmaker": "b2", "market": "Total Goals", "line": "2.5"},
            {"bookmaker": "b3", "market": "Match Goals", "line": "3.0"},
        ]
    )

    assert evidence == {
        "observed_bookmaker_count": 3,
        "observed_ah_ou_market_names": ["Handicap Result", "Match Goals", "Total Goals"],
        "observed_has_ah": True,
        "observed_has_ou": True,
        "observed_has_line": True,
    }


def test_nested_provider_rows_extract_lines_from_values() -> None:
    markets = normalize_odds_markets(
        [
            {
                "bookmakers": [
                    {
                        "name": "BookA",
                        "bets": [
                            {"name": "Asian Handicap", "values": [{"value": "Home -0.25"}]},
                            {"name": "Goals Over/Under", "values": [{"value": "Over 2.5"}]},
                        ],
                    }
                ]
            }
        ]
    )

    assert [(item.normalized_market_type, item.line_value) for item in markets] == [
        ("AH", "-0.25"),
        ("OU", "2.5"),
    ]


def test_missing_line_is_not_counted_as_pass_evidence() -> None:
    evidence = bookmaker_observed_evidence(
        [
            {"bookmaker": "b1", "market": "Asian Handicap"},
            {"bookmaker": "b2", "market": "Over/Under"},
            {"bookmaker": "b3", "market": "Total Goals"},
        ]
    )

    assert evidence["observed_bookmaker_count"] == 3
    assert evidence["observed_has_ah"] is True
    assert evidence["observed_has_ou"] is True
    assert evidence["observed_has_line"] is False
