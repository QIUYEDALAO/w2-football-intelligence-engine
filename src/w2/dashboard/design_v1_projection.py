"""Read-only Dashboard design-v1 rows from persisted recommendation facts."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from w2.dashboard.date_window import football_day_for_kickoff
from w2.domain.profit import profit_units_with_rebate, profit_units_with_rebate_from_sums
from w2.identity.public_competition_labels import public_competition_labels

SETTLED = frozenset({"WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "LOSS"})
DECISIVE = frozenset({"WIN", "HALF_WIN", "HALF_LOSS", "LOSS"})
WINNING = frozenset({"WIN", "HALF_WIN"})
MARKET_ZH = {"ASIAN_HANDICAP": "让球", "TOTALS": "大小球"}
SIDE_ZH = {"HOME": "主", "AWAY": "客", "OVER": "大", "UNDER": "小"}
TOTALS_DISPLAY_STATE = "MARKET_VIEW"
TOTALS_DISPLAY_NOTICE = "市场观点展示 · 不作投注建议"


def _label(value: Any) -> str | None:
    if isinstance(value, Mapping):
        text = value.get("display_name") or value.get("raw_provider_name")
        return str(text) if text else None
    return str(value) if value else None


def _league(competition_id: Any, fallback: Any = None) -> str | None:
    return public_competition_labels().get(
        str(competition_id), _label(fallback) or (str(competition_id) if competition_id else None)
    )


def _day(row: Mapping[str, Any]) -> date | None:
    value = row.get("kickoff_utc")
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if isinstance(value, datetime):
        if value.tzinfo is None:
            from datetime import UTC
            value = value.replace(tzinfo=UTC)
        return football_day_for_kickoff(value)
    return None


def performance_summary(
    rows: Sequence[Mapping[str, Any]], *, anchor: date, calibration_identity: str | None,
    total_profit_units: float | None = None,
    total_absolute_profit_units: float | None = None,
) -> dict[str, Any]:
    """One calibration identity only; a missing identity never selects legacy rows."""
    current = [
        row for row in rows
        if calibration_identity and row.get("calibration_identity") == calibration_identity
        and row.get("settlement") in SETTLED and _day(row) is not None
    ]
    def window(days: int) -> dict[str, Any]:
        included = [
            row for row in current
            if anchor - timedelta(days=days - 1) <= _day(row) <= anchor
        ]
        decisive = [row for row in included if row["settlement"] in DECISIVE]
        return {
            "match_count": len(included),
            "hit_rate": (
                sum(row["settlement"] in WINNING for row in decisive) / len(decisive)
                if decisive else None
            ),
            "profit_units": round(sum(float(row.get("profit_units") or 0) for row in included), 3),
        }
    cumulative = 0.0
    daily = []
    for index in range(29, -1, -1):
        day = anchor - timedelta(days=index)
        daily_units = sum(
            float(row.get("profit_units") or 0)
            for row in current if _day(row) == day
        )
        cumulative += daily_units
        daily.append({"date": day.isoformat(), "daily_profit_units": round(daily_units, 3),
                      "cumulative_profit_units": round(cumulative, 3)})
    pure_total = Decimal(str(total_profit_units)) if total_profit_units is not None else sum(
        (
            Decimal(str(row["profit_units"]))
            for row in current
            if row.get("profit_units") is not None
        ),
        Decimal("0"),
    )
    with_rebate = (
        profit_units_with_rebate_from_sums(pure_total, total_absolute_profit_units)
        if total_absolute_profit_units is not None
        else profit_units_with_rebate(
            row["profit_units"] for row in current if row.get("profit_units") is not None
        )
    )
    return {
        "calibration_identity": calibration_identity,
        "status": "AVAILABLE" if calibration_identity else "CURRENT_MODEL_IDENTITY_UNAVAILABLE",
        "total_profit_units": round(float(pure_total), 3),
        "total_profit_units_with_rebate": round(float(with_rebate), 3),
        "last_7_days": window(7), "last_30_days": window(30), "daily_series": daily,
    }


def review_row(row: Mapping[str, Any], *, calibrated: bool = False) -> dict[str, Any]:
    home = _label(row.get("home_team_label"))
    away = _label(row.get("away_team_label"))
    market = str(row.get("market") or "")
    # T1 裁决后 TOTALS 只作「市场观点」仅覆盖今日/未来新产出；历史已结算行保留
    # 原始方向/盘口，不得再覆盖为「市场观点展示 · 不作投注建议」。
    totals_market_view = market == "TOTALS" and row.get("settlement") not in SETTLED
    return {
        "fixture_id": str(row["fixture_id"]),
        "date": _day(row).isoformat() if _day(row) else None,
        "league": _league(row.get("competition_id")),
        "match": f"{home} vs {away}" if home and away else None,
        "recommendation": (
            f"{SIDE_ZH.get(str(row.get('selection')), '')} {row.get('exact_line')}"
        ).strip(),
        "market": MARKET_ZH.get(market),
        "display_state": TOTALS_DISPLAY_STATE if totals_market_view else "RECOMMENDATION",
        "display_notice": TOTALS_DISPLAY_NOTICE if totals_market_view else None,
        "decimal_odds": row.get("decimal_odds"),
        "result": row.get("settlement"),
        "profit_units": row.get("profit_units"),
        **({"calibration_decision": row.get("filter_decision"),
            "calibrated_ev": row.get("ev_corrected"),
            "forward": row.get("forward"), "warmup": row.get("warmup")}
           if calibrated else {}),
    }


def today_recommendations(
    matches: Sequence[Mapping[str, Any]], samples: Sequence[Mapping[str, Any]], *, anchor: date,
    calibration_identity: str | None = None,
) -> list[dict[str, Any]]:
    by_fixture = {
        (str(row.get("fixture_id")), str(row.get("market"))): row
        for row in samples
        if _day(row) == anchor
        and calibration_identity is not None
        and row.get("calibration_identity") == calibration_identity
    }
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for sample in by_fixture.values():
        fixture_id = str(sample["fixture_id"])
        market = str(sample["market"])
        # Historical TOTALS candidates remain available in the validation
        # ledger, but must never enter the public "今日推荐" surface.
        if market == "TOTALS":
            continue
        match = next((item for item in matches if str(item.get("fixture_id")) == fixture_id), {})
        home = _label(sample.get("home_team_label")) or _label(match.get("home_team_label"))
        away = _label(sample.get("away_team_label")) or _label(match.get("away_team_label"))
        withdrawn = str(match.get("lifecycle_status") or "") in {
            "WITHDRAWN", "REVOKED", "CANCELLED"
        }
        result.append({
            "fixture_id": fixture_id, "kickoff_utc": sample.get("kickoff_utc"),
            "competition_name_zh": _league(
                sample.get("competition_id"), match.get("competition_name")
            ),
            "home": home, "away": away, "market": MARKET_ZH.get(market),
            "selection": SIDE_ZH.get(str(sample.get("selection"))),
            "line": sample.get("exact_line"), "odds": sample.get("decimal_odds"),
            "ev": sample.get("current_ev"),
            "status": (
                "settled" if sample.get("settlement") in SETTLED else
                "withdrawn" if withdrawn else
                "confirmed"
            ),
            "withdraw_reason": match.get("reason_code") if withdrawn else None,
            "result": sample.get("settlement"),
        })
        seen.add((fixture_id, market))
    for match in matches:
        pick = match.get("pick")
        if not isinstance(pick, Mapping) or not pick.get("market"):
            continue
        fixture_id = str(match.get("fixture_id"))
        market = str(pick["market"])
        if market == "TOTALS":
            continue
        if (fixture_id, market) in seen:
            continue
        lifecycle = str(match.get("lifecycle_status") or "")
        status = (
            "withdrawn" if lifecycle in {"WITHDRAWN", "REVOKED", "CANCELLED"} else
            "confirmed" if match.get("decision_tier") == "RECOMMEND" else "candidate"
        )
        home = _label(match.get("home_team_label")) or _label(match.get("home_team_name"))
        away = _label(match.get("away_team_label")) or _label(match.get("away_team_name"))
        result.append({
            "fixture_id": fixture_id, "kickoff_utc": match.get("kickoff_utc"),
            "competition_name_zh": _league(
                match.get("competition_id"), match.get("competition_name")
            ),
            "home": home, "away": away,
            "market": MARKET_ZH.get(market),
            "selection": SIDE_ZH.get(str(pick.get("selection"))),
            "line": pick.get("exact_line") or pick.get("line"),
            "odds": pick.get("decimal_odds") or pick.get("odds"),
            "ev": pick.get("expected_value"), "status": status,
            "withdraw_reason": match.get("reason_code") if status == "withdrawn" else None,
            "result": None,
        })
    return result


def replay_display_row(
    match: Mapping[str, Any], versions: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Project actual evaluated timepoints and the final persisted evaluation."""
    home = _label(match.get("home_team_label")) or _label(match.get("home_team_name"))
    away = _label(match.get("away_team_label")) or _label(match.get("away_team_name"))
    last = max(versions, key=lambda row: str(row.get("evaluated_at") or ""), default=None)
    final = None
    final_display_state = "RECOMMENDATION"
    display_notice = None
    if last and last.get("state") == "ANALYSIS_PICK_ACTIVE":
        final = (
            f"{MARKET_ZH.get(str(last.get('market')), last.get('market'))} "
            f"{SIDE_ZH.get(str(last.get('selection')), last.get('selection'))} "
            f"{last.get('exact_line')} @{last.get('decimal_odds')}"
        )
    return {
        "league": _league(match.get("competition_id"), match.get("competition_name")),
        "match": f"{home} vs {away}" if home and away else None,
        "evaluation_count": len({
            str(row["evaluated_at"]) for row in versions if row.get("evaluated_at")
        }),
        "final_recommendation": final,
        "final_display_state": final_display_state if final is not None else None,
        "display_notice": display_notice,
    }
