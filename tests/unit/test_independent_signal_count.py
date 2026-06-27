from __future__ import annotations

from w2.pricing.shadow import build_pricing_shadow


def factor(
    factor_id: str,
    *,
    source_group: str,
    side: str = "HOME",
    score: float = 0.6,
    independent: bool = True,
    proxy_of: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": factor_id,
        "status": "READY",
        "side": side,
        "score": score,
        "weight": 1.0,
        "source": f"{source_group}_source",
        "source_group": source_group,
        "is_independent_signal": independent,
        "collection_status": "READY" if independent else "PROXY_ONLY",
    }
    if proxy_of is not None:
        payload["proxy_of"] = proxy_of
    return payload


def test_xg_proxy_factors_do_not_inflate_isc() -> None:
    shadow = build_pricing_shadow(
        fixture_id="fx",
        feature_contributions=[
            factor(
                "F3_REST_FITNESS",
                source_group="xg",
                independent=False,
                proxy_of="team_fixture_history",
            ),
            factor("F4_MATCH_IMPORTANCE", source_group="match_importance", independent=False),
            factor(
                "F7_STRENGTH_FORM",
                source_group="xg",
                independent=False,
                proxy_of="ratings",
            ),
            factor("F9_TRUE_XG", source_group="xg"),
        ],
        current_odds={"ah": {"home_line": "0"}},
    )

    assert shadow["coverage"] == 0.571429
    assert shadow["independent_signal_count"] == 1
    assert shadow["independent_signal_groups"] == ["xg"]
    assert shadow["xg_derived_factor_count"] == 3
    assert shadow["factor_source_summary"]["F3_REST_FITNESS"]["proxy_of"] == (
        "team_fixture_history"
    )
    assert shadow["factor_source_summary"]["F7_STRENGTH_FORM"]["is_independent_signal"] is False


def test_isc_counts_distinct_authoritative_signal_groups_only() -> None:
    shadow = build_pricing_shadow(
        fixture_id="fx",
        feature_contributions=[
            factor("F1_MARKET_MOVEMENT", source_group="market"),
            factor("F2_BOOKMAKER_INTENT", source_group="market"),
            factor("F3_REST_FITNESS", source_group="team_fixture_history"),
            factor("F4_MATCH_IMPORTANCE", source_group="match_importance", independent=False),
            factor("F6_H2H", source_group="h2h"),
            factor("F7_STRENGTH_FORM", source_group="ratings"),
            factor("F8_SQUAD_VALUE", source_group="squad_value"),
            factor("F9_TRUE_XG", source_group="xg"),
        ],
        current_odds={"ah": {"home_line": "0"}},
    )

    assert shadow["independent_signal_count"] == 5
    assert shadow["independent_signal_groups"] == [
        "h2h",
        "ratings",
        "squad_value",
        "team_fixture_history",
        "xg",
    ]
    assert "market" not in shadow["independent_signal_groups"]
    assert "match_importance" not in shadow["independent_signal_groups"]


def test_meaningful_isc_can_move_fair_ah_off_pickem() -> None:
    shadow = build_pricing_shadow(
        fixture_id="strong-weak",
        feature_contributions=[
            factor("F3_REST_FITNESS", source_group="team_fixture_history", score=0.7),
            factor("F6_H2H", source_group="h2h", score=0.9),
            factor("F7_STRENGTH_FORM", source_group="ratings", score=0.95),
            factor("F9_TRUE_XG", source_group="xg", score=0.6),
        ],
        current_odds={"ah": {"home_line": "0"}},
    )

    assert shadow["independent_signal_count"] >= 3
    assert shadow["team_score"]["home"] > shadow["team_score"]["away"]
    assert shadow["fair_ah"] < 0
    assert shadow["beats_market"] is False
