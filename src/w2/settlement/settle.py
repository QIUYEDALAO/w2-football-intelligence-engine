from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal

from w2.domain.odds import settle_asian_handicap, settle_total_goals

WIN_UNITS = {
    "WIN": Decimal("1"),
    "HALF_WIN": Decimal("0.5"),
    "PUSH": Decimal("0"),
    "HALF_LOSS": Decimal("-0.5"),
    "LOSS": Decimal("-1"),
}


@dataclass(frozen=True, kw_only=True)
class LockedPrediction:
    fixture_id: str
    market: str
    selection: str
    line: str | None
    locked_decimal_odds: Decimal
    model_probability: Decimal
    locked_at: datetime
    prediction_hash: str
    candidate: Literal[False] = False
    formal_recommendation: Literal[False] = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "market": self.market,
            "selection": self.selection,
            "line": self.line,
            "locked_decimal_odds": str(self.locked_decimal_odds),
            "model_probability": str(self.model_probability),
            "locked_at": iso(self.locked_at),
            "prediction_hash": self.prediction_hash,
            "candidate": False,
            "formal_recommendation": False,
        }


@dataclass(frozen=True, kw_only=True)
class MatchResult:
    fixture_id: str
    home_goals_90: int
    away_goals_90: int
    final_at: datetime


@dataclass(frozen=True, kw_only=True)
class SettlementEvaluation:
    fixture_id: str
    prediction_hash: str
    market: str
    selection: str
    line: str | None
    outcome: str
    settled_units: Decimal
    locked_decimal_odds: Decimal
    closing_decimal_odds: Decimal | None
    clv_decimal: Decimal | None
    replay_hash: str
    evaluated_at: datetime
    candidate: Literal[False] = False
    formal_recommendation: Literal[False] = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "prediction_hash": self.prediction_hash,
            "market": self.market,
            "selection": self.selection,
            "line": self.line,
            "outcome": self.outcome,
            "settled_units": str(self.settled_units),
            "locked_decimal_odds": str(self.locked_decimal_odds),
            "closing_decimal_odds": (
                str(self.closing_decimal_odds) if self.closing_decimal_odds is not None else None
            ),
            "clv_decimal": str(self.clv_decimal) if self.clv_decimal is not None else None,
            "replay_hash": self.replay_hash,
            "evaluated_at": iso(self.evaluated_at),
            "candidate": False,
            "formal_recommendation": False,
        }


def iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def settle_prediction(
    prediction: LockedPrediction,
    result: MatchResult,
    *,
    closing_decimal_odds: Decimal | None,
    evaluated_at: datetime,
) -> SettlementEvaluation:
    if prediction.fixture_id != result.fixture_id:
        raise ValueError("prediction/result fixture mismatch")
    outcome = settle_market(
        market=prediction.market,
        selection=prediction.selection,
        line=prediction.line,
        home_goals_90=result.home_goals_90,
        away_goals_90=result.away_goals_90,
    )
    clv = (
        (closing_decimal_odds - prediction.locked_decimal_odds)
        if closing_decimal_odds is not None
        else None
    )
    replay_payload = {
        "prediction": prediction.as_dict(),
        "result": {
            "fixture_id": result.fixture_id,
            "home_goals_90": result.home_goals_90,
            "away_goals_90": result.away_goals_90,
            "final_at": iso(result.final_at),
        },
        "closing_decimal_odds": str(closing_decimal_odds) if closing_decimal_odds else None,
        "outcome": outcome,
    }
    return SettlementEvaluation(
        fixture_id=prediction.fixture_id,
        prediction_hash=prediction.prediction_hash,
        market=prediction.market,
        selection=prediction.selection,
        line=prediction.line,
        outcome=outcome,
        settled_units=WIN_UNITS[outcome],
        locked_decimal_odds=prediction.locked_decimal_odds,
        closing_decimal_odds=closing_decimal_odds,
        clv_decimal=clv,
        replay_hash=stable_hash(replay_payload),
        evaluated_at=evaluated_at,
    )


def settle_market(
    *,
    market: str,
    selection: str,
    line: str | None,
    home_goals_90: int,
    away_goals_90: int,
) -> str:
    if market == "ONE_X_TWO":
        if home_goals_90 > away_goals_90:
            actual = "HOME"
        elif home_goals_90 < away_goals_90:
            actual = "AWAY"
        else:
            actual = "DRAW"
        return "WIN" if selection in {actual, f"{actual}_WIN"} else "LOSS"
    if market == "ASIAN_HANDICAP":
        if line is None:
            raise ValueError("ASIAN_HANDICAP settlement requires line")
        return settle_asian_handicap(home_goals_90, away_goals_90, selection, Decimal(line)).value
    if market == "TOTALS":
        if line is None:
            raise ValueError("TOTALS settlement requires line")
        return settle_total_goals(home_goals_90 + away_goals_90, selection, Decimal(line)).value
    if market == "BTTS":
        actual = "YES" if home_goals_90 > 0 and away_goals_90 > 0 else "NO"
        return "WIN" if selection == actual else "LOSS"
    raise ValueError(f"unsupported market {market}")


def stable_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode()).hexdigest()
