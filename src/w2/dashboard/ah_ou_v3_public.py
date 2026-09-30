"""Read-only Design v1 projection of the one frozen AH/OU v3.1 ledger.

No quote, direction, settlement or model result is computed here. The input is
the decision-id keyed readback of v3.1 ledger plus its versioned settlement.
Legacy V4 picks and v2 validation samples are never an input.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from w2.dashboard.date_window import football_day_for_kickoff
from w2.domain.profit import profit_units_with_rebate
from w2.identity.public_competition_labels import public_competition_labels

_SETTLED = frozenset({"WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "LOSS"})
_DECISIVE = _SETTLED - {"PUSH"}
_MARKETS = ("ASIAN_HANDICAP", "TOTALS")


def _day(row: Mapping[str, Any]) -> date:
    kickoff = datetime.fromisoformat(str(row["kickoff_utc"]).replace("Z", "+00:00"))
    if kickoff.tzinfo is None:
        raise ValueError("V3_PUBLIC_KICKOFF_TZ_MISSING")
    return football_day_for_kickoff(kickoff.astimezone(UTC))


def _units(rows: Sequence[Mapping[str, Any]]) -> Decimal:
    return sum((Decimal(str(row["net_units"])) for row in rows), Decimal(0))


def _window(
    rows: Sequence[Mapping[str, Any]], *, anchor: date, days: int | None,
) -> dict[str, Any]:
    subset = [
        row for row in rows
        if days is None or anchor - timedelta(days=days - 1) <= _day(row) <= anchor
    ]
    settled = [row for row in subset if row["state"] == "SETTLED"]
    decisive = [row for row in settled if row["settlement"] in _DECISIVE]
    wins = sum(Decimal("0.5") if row["settlement"] == "HALF_WIN" else
               Decimal(1) if row["settlement"] == "WIN" else Decimal(0)
               for row in decisive)
    return {
        "match_count": len(settled),  # UI labels this as decision rows, not fixtures.
        "selected_count": len(subset),
        "pending_count": sum(row["state"] == "PENDING" for row in subset),
        "blocked_count": sum(row["state"] == "BLOCKED" for row in subset),
        "void_count": sum(row["state"] == "VOID" for row in subset),
        "hit_rate_denominator": len(decisive),
        "hit_rate": float(wins / len(decisive)) if decisive else None,
        "profit_units": float(_units(settled)),
    }


def public_v3_home_projection(
    rows: Sequence[Mapping[str, Any]], *, anchor: date,
) -> dict[str, Any]:
    """Build homepage rows and KPIs from exactly one v3.1 decision set."""
    ids = [str(row["decision_id"]) for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("V3_PUBLIC_DUPLICATE_DECISION_ID")
    for row in rows:
        if row["decision_contract"] != "w2.ah_ou_decision.v3.1":
            raise ValueError("V3_PUBLIC_CONTRACT_MISMATCH")
        if row["market"] not in _MARKETS or row["state"] not in {
            "PENDING", "SETTLED", "VOID", "BLOCKED"
        }:
            raise ValueError("V3_PUBLIC_STATE_INVALID")
        if row["state"] == "SETTLED" and row["settlement"] not in _SETTLED:
            raise ValueError("V3_PUBLIC_SETTLEMENT_INVALID")
        _day(row)
    today = [row for row in rows if _day(row) == anchor]
    today.sort(key=lambda row: (str(row["kickoff_utc"]), str(row["fixture_id"]),
                                _MARKETS.index(str(row["market"]))))
    names = public_competition_labels()
    recommendations = []
    for row in today:
        state = str(row["state"])
        recommendations.append({
            "schema_version": "w2.ah_ou_v3_public_recommendation.v1",
            "decision_id": row["decision_id"],
            "decision_contract": row["decision_contract"],
            "fixture_id": row["fixture_id"],
            "kickoff_utc": row["kickoff_utc"],
            "competition_id": row["competition_id"],
            "competition_name_zh": names.get(str(row["competition_id"]), row["competition_id"]),
            "home": row["home"], "away": row["away"],
            "market": row["market"],
            "selection": row["selection"],
            "line": row["exact_line"],
            "odds": row["decimal_odds"],
            "score": row["score"],
            "model_version": row["model_version"],
            "calibration_version": row["calibration_version"],
            "quote_capture_id": row["quote_capture_id"],
            "quote_raw_sha256": row["quote_raw_sha256"],
            "terms_hash": row["terms_hash"],
            "status": state.lower(),
            "result": row["settlement"],
            "net_units": row["net_units"] if state == "SETTLED" else None,
            "settlement_hash": row["settlement_hash"],
        })
    settled = [row for row in rows if row["state"] == "SETTLED"]
    daily = []
    cumulative = Decimal(0)
    for index in range(29, -1, -1):
        day = anchor - timedelta(days=index)
        profit = _units([row for row in settled if _day(row) == day])
        cumulative += profit
        daily.append({"date": day.isoformat(), "daily_profit_units": float(profit),
                      "cumulative_profit_units": float(cumulative)})
    summary = {
        "schema_version": "w2.ah_ou_v3_public_performance.v1",
        "calibration_identity": "w2.ah_ou_decision.v3.1",
        "status": "AVAILABLE",
        "selected_count": len(rows),
        "settled_count": len(settled),
        "pending_count": sum(row["state"] == "PENDING" for row in rows),
        "blocked_count": sum(row["state"] == "BLOCKED" for row in rows),
        "void_count": sum(row["state"] == "VOID" for row in rows),
        "total_profit_units": float(_units(settled)),
        "total_profit_units_with_rebate": float(
            profit_units_with_rebate(row["net_units"] for row in settled)
        ),
        "last_7_days": _window(rows, anchor=anchor, days=7),
        "last_30_days": _window(rows, anchor=anchor, days=30),
        "daily_series": daily,
        "by_market": {
            market: _window([row for row in rows if row["market"] == market],
                            anchor=anchor, days=None)
            for market in _MARKETS
        },
    }
    return {"today_recommendations": recommendations, "performance_summary": summary}
