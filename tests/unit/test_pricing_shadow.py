from __future__ import annotations

from pathlib import Path

from w2.pricing.shadow import build_pricing_shadow
from w2.pricing.team_score import independent_team_scores
from w2.pricing.value_vs_market import edge


def contribution(
    factor_id: str,
    *,
    side: str = "NEUTRAL",
    score: float = 0.6,
    weight: float = 1.0,
    status: str = "READY",
    source_group: str | None = None,
    is_independent_signal: bool = True,
    proxy_of: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": factor_id,
        "side": side,
        "score": score,
        "weight": weight,
        "status": status,
        "is_independent_signal": is_independent_signal,
        "collection_status": "READY",
    }
    if source_group is not None:
        payload["source_group"] = source_group
        payload["source"] = f"{source_group}_test_source"
    if proxy_of is not None:
        payload["proxy_of"] = proxy_of
    return payload


def independent_contributions() -> list[dict[str, object]]:
    return [
        contribution(
            "F3_REST_FITNESS",
            side="HOME",
            score=0.75,
            source_group="team_fixture_history",
        ),
        contribution(
            "F4_MATCH_IMPORTANCE",
            side="NEUTRAL",
            score=0.60,
            source_group="match_importance",
            is_independent_signal=False,
        ),
        contribution(
            "F5_RECENT_AH_COVER",
            side="HOME",
            score=0.80,
            source_group="team_fixture_history",
        ),
        contribution("F6_H2H", side="NEUTRAL", score=0.55, source_group="h2h"),
        contribution("F7_STRENGTH_FORM", side="HOME", score=0.85, source_group="ratings"),
        contribution("F8_SQUAD_VALUE", side="HOME", score=0.70, source_group="squad_value"),
        contribution("F9_TRUE_XG", side="HOME", score=0.90, source_group="xg"),
    ]


def test_no_independent_factors_does_not_fabricate_pricing() -> None:
    shadow = build_pricing_shadow(
        fixture_id="fixture-1",
        feature_contributions=None,
        current_odds={"ah": {"home_line": "-0.5"}, "ou": {"line": "2.5"}},
    )

    assert shadow["status"] == "INSUFFICIENT_INDEPENDENT_FACTORS"
    assert shadow["factors"] == []
    assert shadow["coverage"] == 0
    assert shadow["fair_ah"] is None
    assert shadow["fair_ou"] is None
    assert shadow["edge_ah"] is None
    assert shadow["edge_ou"] is None
    assert shadow["beats_market"] is False
    assert shadow["formal_enabled"] is False
    assert shadow["candidate_enabled"] is False


def test_market_and_model_probability_factors_are_excluded_from_independent_score() -> None:
    forbidden = [
        contribution("F1_MARKET_MOVEMENT", side="HOME", score=1.0),
        contribution("F2_BOOKMAKER_INTENT", side="HOME", score=1.0),
        contribution("MARKET_HOME_BASELINE", side="HOME", score=1.0),
        contribution("MARKET_AWAY_BASELINE", side="AWAY", score=1.0),
        contribution("PRICE_COVERAGE", side="NEUTRAL", score=1.0),
        contribution("MODEL_MARKET_DIVERGENCE", side="HOME", score=1.0),
        contribution("F3_MODEL_HOME_PROBABILITY", side="HOME", score=1.0),
        contribution("F4_MODEL_AWAY_PROBABILITY", side="AWAY", score=1.0),
    ]

    shadow = build_pricing_shadow(
        fixture_id="fixture-2",
        feature_contributions=forbidden,
        current_odds={"ah": {"home_line": "-0.5"}},
    )

    assert shadow["factors"] == []
    assert shadow["coverage"] == 0
    assert shadow["status"] == "INSUFFICIENT_INDEPENDENT_FACTORS"


def test_independent_f3_to_f9_contributions_drive_s1_shadow_only() -> None:
    shadow = build_pricing_shadow(
        fixture_id="fixture-3",
        feature_contributions=independent_contributions(),
        current_odds={
            "ah": {"home_line": "0.25"},
            "ou": {"line": "2.5"},
        },
    )

    assert shadow["status"] == "RULE_BASED_UNCALIBRATED"
    assert 0 <= shadow["coverage"] <= 1
    assert shadow["coverage"] == 1
    assert shadow["independent_signal_count"] == 5
    assert shadow["fair_ah"] < 0
    assert shadow["fair_ou"] is None
    assert shadow["edge_ah"] > 0
    assert shadow["edge_ou"] is None
    assert {factor["id"] for factor in shadow["factors"]} == {
        "F3_REST_FITNESS",
        "F4_MATCH_IMPORTANCE",
        "F5_RECENT_AH_COVER",
        "F6_H2H",
        "F7_STRENGTH_FORM",
        "F8_SQUAD_VALUE",
        "F9_TRUE_XG",
    }
    assert shadow["beats_market"] is False
    assert shadow["formal_enabled"] is False
    assert shadow["candidate_enabled"] is False
    assert shadow["team_score_audit"]["weight_sum_used"] > 0
    assert shadow["team_score_audit"]["factor_count_used"] > 0
    assert shadow["factor_scale_version"] == "w2.factor_scale.v1"
    assert shadow["factor_scale"]["supremacy_score_per_quarter_line"] == 0.16
    assert all("sigma" in factor for factor in shadow["factors"])


def test_weighted_score_normalizes_by_available_ready_factor_weight() -> None:
    compact = independent_team_scores(
        feature_contributions=[
            contribution(
                "F3_REST_FITNESS",
                side="HOME",
                score=0.8,
                weight=1.0,
                source_group="team_fixture_history",
            ),
            contribution(
                "F6_H2H",
                side="AWAY",
                score=0.2,
                weight=1.0,
                source_group="h2h",
            ),
        ]
    )
    expanded = independent_team_scores(
        feature_contributions=[
            contribution(
                "F3_REST_FITNESS",
                side="HOME",
                score=0.8,
                weight=1.0,
                source_group="team_fixture_history",
            ),
            contribution(
                "F5_RECENT_AH_COVER",
                side="HOME",
                score=0.8,
                weight=1.0,
                source_group="team_fixture_history",
            ),
            contribution(
                "F6_H2H",
                side="AWAY",
                score=0.2,
                weight=1.0,
                source_group="h2h",
            ),
            contribution(
                "F7_STRENGTH_FORM",
                side="AWAY",
                score=0.2,
                weight=1.0,
                source_group="ratings",
            ),
        ]
    )

    assert compact["weight_sum_used"] == 2.0
    assert expanded["weight_sum_used"] == 4.0
    assert compact["factor_count_used"] == 2
    assert expanded["factor_count_used"] == 4
    assert compact["home_score"] - compact["away_score"] == expanded[
        "home_score"
    ] - expanded["away_score"]
    assert compact["factor_scale"]["version"] == "w2.factor_scale.v1"


def test_coverage_below_half_watches_without_promotion() -> None:
    shadow = build_pricing_shadow(
        fixture_id="fixture-4",
        feature_contributions=[
            contribution("F3_REST_FITNESS", side="HOME", score=0.75),
            contribution("F9_TRUE_XG", side="HOME", score=0.90, source_group="xg"),
        ],
        current_odds={"ah": {"home_line": "-0.25"}, "ou": {"line": "2.5"}},
    )

    assert shadow["coverage"] < 0.5
    assert shadow["status"] == "WATCH"
    assert shadow["beats_market"] is False


def test_ah_edge_uses_negative_home_gives_sign_convention() -> None:
    assert edge(-1.25, -0.5) > 0
    assert edge(-0.25, -1.0) < 0
    assert edge(0, 0) == 0


def test_pricing_shadow_does_not_fit_ou_mu_from_market_lines() -> None:
    pricing_files = [
        Path("src/w2/pricing/shadow.py"),
        Path("src/w2/pricing/supremacy.py"),
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in pricing_files)

    assert "fit_total_goals_mu" not in combined
