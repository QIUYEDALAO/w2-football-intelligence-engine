from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, cast

SCORELINE_DIRECTION_MARGIN = 0.03


def _load_payload(path: str) -> dict[str, Any]:
    if path == "-":
        payload = json.loads(sys.stdin.read())
    else:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return cast(dict[str, Any], payload)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _side_from_selection(selection: Any) -> str:
    if selection == "HOME_AH":
        return "HOME"
    if selection == "AWAY_AH":
        return "AWAY"
    return "UNKNOWN"


def _line_for_side(*, side: str, home_line: float | None) -> float | None:
    if home_line is None:
        return None
    if side == "HOME":
        return home_line
    if side == "AWAY":
        return -home_line
    return None


def _side_label(side: str) -> str:
    return {"HOME": "主队", "AWAY": "客队", "DRAW": "平局"}.get(side, "未知")


def _top_scoreline_side(scoreline: dict[str, Any]) -> str:
    home = _number(scoreline.get("home_goals"))
    away = _number(scoreline.get("away_goals"))
    if home is None or away is None:
        return "UNKNOWN"
    if home > away:
        return "HOME"
    if away > home:
        return "AWAY"
    return "DRAW"


def _dominant_result_side(summary: dict[str, Any]) -> str:
    home = _number(summary.get("home_win"))
    away = _number(summary.get("away_win"))
    draw = _number(summary.get("draw"))
    if home is None or away is None:
        return "UNKNOWN"
    if abs(home - away) < SCORELINE_DIRECTION_MARGIN:
        return "DRAW" if draw is not None else "NEUTRAL"
    return "HOME" if home > away else "AWAY"


def _scoreline_alignment(*, selected_side: str, simulation: dict[str, Any]) -> dict[str, Any]:
    score_summary = _dict(simulation.get("score_matrix_summary"))
    scoreline_picks = _list(simulation.get("scoreline_picks"))
    top = _dict(scoreline_picks[0]) if scoreline_picks else {}
    top_side = _top_scoreline_side(top)
    dominant_side = _dominant_result_side(score_summary)
    if selected_side == "UNKNOWN":
        status = "UNKNOWN"
        explanation = "推荐方向无法识别。"
    elif dominant_side == "UNKNOWN":
        status = "UNKNOWN"
        explanation = "模拟胜平负分布缺失，无法判断方向自洽。"
    elif selected_side == dominant_side:
        status = "ALIGNED"
        explanation = f"推荐方向与模拟胜平负最大概率方向一致，均为{_side_label(selected_side)}。"
    elif dominant_side == "DRAW":
        status = "SPREAD_VALUE_OVER_DRAWISH_GAME"
        explanation = "模拟胜平负最大项为平局，受让/让球推荐来自亚洲盘结算 EV，而不是比分胜负方向。"
    else:
        status = "REVERSE_VALUE"
        explanation = (
            f"模拟胜平负最大概率方向为{_side_label(dominant_side)}，"
            f"但推荐为{_side_label(selected_side)}；这属于盘口价值逆因子场景，"
            "需要看 AH 结算分布和赔率是否支撑。"
        )
    return {
        "status": status,
        "explanation_cn": explanation,
        "selected_side": selected_side,
        "top_scoreline": top.get("scoreline"),
        "top_scoreline_side": top_side,
        "dominant_result_side": dominant_side,
        "home_win": score_summary.get("home_win"),
        "draw": score_summary.get("draw"),
        "away_win": score_summary.get("away_win"),
    }


def _simulation_evidence(card: dict[str, Any]) -> dict[str, Any]:
    shadow = _dict(card.get("pricing_shadow"))
    simulation = _dict(shadow.get("simulation"))
    readiness = _dict(card.get("scoreline_readiness"))
    simulations = _number(simulation.get("simulations"))
    scoreline_source = readiness.get("source")
    status = simulation.get("status") or shadow.get("simulation_status")
    return {
        "status": status,
        "scoreline_source": scoreline_source,
        "model_version": simulation.get("model_version") or readiness.get("model_version"),
        "calibration_version": simulation.get("calibration_version")
        or readiness.get("calibration_version"),
        "calibration_status": simulation.get("calibration_status")
        or readiness.get("calibration_status"),
        "simulations": int(simulations) if simulations is not None else None,
        "seed_present": simulation.get("seed") is not None,
        "lambda_home": simulation.get("lambda_home") or readiness.get("lambda_home"),
        "lambda_away": simulation.get("lambda_away") or readiness.get("lambda_away"),
        "scoreline_picks": simulation.get("scoreline_picks") or card.get("scoreline_picks"),
        "has_10000_simulation_evidence": status == "READY"
        and scoreline_source == "formal_simulation"
        and simulations == 10_000,
    }


def _formal_row_explanation(card: dict[str, Any]) -> dict[str, Any]:
    recommendation = _dict(card.get("recommendation"))
    shadow = _dict(card.get("pricing_shadow"))
    canonical = _dict(
        shadow.get("canonical_ah_market") or recommendation.get("canonical_ah_market")
    )
    simulation = _dict(shadow.get("simulation"))
    selected_side = _side_from_selection(recommendation.get("selection"))
    home_line = _number(canonical.get("home_line"))
    selected_line = _line_for_side(side=selected_side, home_line=home_line)
    is_underdog = selected_line is not None and selected_line > 0
    alignment = _scoreline_alignment(selected_side=selected_side, simulation=simulation)
    sim_evidence = _simulation_evidence(card)
    distribution = _dict(recommendation.get("ah_settlement_distribution"))
    findings: list[str] = []
    if not sim_evidence["has_10000_simulation_evidence"]:
        findings.append("MISSING_10000_SIMULATION_EVIDENCE")
    if not distribution:
        findings.append("MISSING_AH_SETTLEMENT_DISTRIBUTION")
    if alignment["status"] == "REVERSE_VALUE" and not recommendation.get("reverse_factor_value"):
        findings.append("REVERSE_SCORELINE_WITHOUT_REVERSE_FACTOR_FLAG")
    if is_underdog and recommendation.get("expected_value") is None:
        findings.append("UNDERDOG_FORMAL_WITHOUT_EV")
    return {
        "fixture_id": card.get("fixture_id"),
        "teams": f"{card.get('home_team_name')} vs {card.get('away_team_name')}",
        "recommendation": {
            "selection": recommendation.get("selection"),
            "selection_label_cn": recommendation.get("selection_label_cn"),
            "market": recommendation.get("market"),
            "line": recommendation.get("line"),
            "odds": recommendation.get("odds"),
            "expected_value": recommendation.get("expected_value"),
            "risk_adjusted_ev": recommendation.get("risk_adjusted_ev"),
            "reverse_factor_value": recommendation.get("reverse_factor_value"),
            "devig_probability": recommendation.get("devig_probability"),
        },
        "market": {
            "canonical_home_line": canonical.get("home_line"),
            "selected_side_line": selected_line,
            "selected_side_is_underdog": is_underdog,
            "home_price": canonical.get("home_price"),
            "away_price": canonical.get("away_price"),
            "source": canonical.get("source"),
            "validation_status": canonical.get("validation_status"),
            "blocker": canonical.get("blocker"),
        },
        "simulation_evidence": sim_evidence,
        "scoreline_alignment": alignment,
        "ah_ev_evidence": {
            "expected_value": recommendation.get("expected_value"),
            "settlement_distribution": distribution,
            "effective_cover_probability": recommendation.get("model_probability"),
            "market_baseline_probability": recommendation.get("devig_probability"),
        },
        "explanation_cn": _explanation_cn(
            selected_side=selected_side,
            is_underdog=is_underdog,
            recommendation=recommendation,
            alignment=alignment,
            sim_evidence=sim_evidence,
        ),
        "findings": findings,
    }


def _explanation_cn(
    *,
    selected_side: str,
    is_underdog: bool,
    recommendation: dict[str, Any],
    alignment: dict[str, Any],
    sim_evidence: dict[str, Any],
) -> str:
    side = recommendation.get("selection_label_cn") or _side_label(selected_side)
    ev = recommendation.get("risk_adjusted_ev") or recommendation.get("expected_value")
    simulation_text = (
        "有 10000 次正式模拟证据"
        if sim_evidence.get("has_10000_simulation_evidence")
        else "缺少 10000 次正式模拟证据"
    )
    underdog_text = "这是受让方向" if is_underdog else "这不是受让方向"
    return (
        f"{side} 被选中；{underdog_text}。{simulation_text}。"
        f"方向关系：{alignment.get('explanation_cn')} "
        f"推荐成立依据应看亚洲盘结算分布与 EV（当前 EV={ev}），"
        "比分只作为模拟参考，不等同于推荐比分。"
    )


def build_report(payload: dict[str, Any]) -> dict[str, Any]:
    cards = payload.get("all") if isinstance(payload, dict) else None
    if not isinstance(cards, list):
        raise ValueError("input must be a /v1/dashboard payload with an all[] list")
    formal_cards = [
        card
        for card in cards
        if isinstance(card, dict) and card.get("formal_recommendation") is True
    ]
    rows = [_formal_row_explanation(card) for card in formal_cards]
    selection_counts: dict[str, int] = {}
    for row in rows:
        selection = str(row["recommendation"].get("selection"))
        selection_counts[selection] = selection_counts.get(selection, 0) + 1
    underdog_count = sum(1 for row in rows if row["market"]["selected_side_is_underdog"])
    findings = sorted({finding for row in rows for finding in row["findings"]})
    return {
        "summary": {
            "formal_count": len(rows),
            "formal_selection_counts": selection_counts,
            "formal_underdog_count": underdog_count,
            "formal_favorite_or_pickem_count": len(rows) - underdog_count,
            "simulation_10000_evidence_count": sum(
                1 for row in rows if row["simulation_evidence"]["has_10000_simulation_evidence"]
            ),
            "reverse_value_count": sum(
                1 for row in rows if row["scoreline_alignment"]["status"] == "REVERSE_VALUE"
            ),
            "audit_findings": findings,
        },
        "formal_explanations": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Explain W2 FORMAL recommendations from a dashboard payload "
            "without changing decisions."
        ),
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Dashboard JSON payload path, or '-' for stdin.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON. This is the default output.",
    )
    args = parser.parse_args()
    report = build_report(_load_payload(args.input))
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
