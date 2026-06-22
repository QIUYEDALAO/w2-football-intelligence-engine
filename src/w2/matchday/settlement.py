from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from w2.domain.odds import settle_asian_handicap, settle_total_goals


@dataclass(frozen=True, kw_only=True)
class SettlementEvent:
    fixture_id: str
    market: str
    selection: str
    line: str | None
    outcome: str
    append_only: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "market": self.market,
            "selection": self.selection,
            "line": self.line,
            "outcome": self.outcome,
            "append_only": self.append_only,
        }


class MatchdaySettlementService:
    def settle_direction(
        self,
        *,
        fixture_id: str,
        home_goals_90: int,
        away_goals_90: int,
        market: str,
        selection: str,
        line: str | None,
    ) -> SettlementEvent:
        if market == "ONE_X_TWO":
            if home_goals_90 > away_goals_90:
                actual = "HOME"
            elif home_goals_90 < away_goals_90:
                actual = "AWAY"
            else:
                actual = "DRAW"
            outcome = "WIN" if selection in {actual, f"{actual}_WIN"} else "LOSS"
        elif market == "ASIAN_HANDICAP":
            if line is None:
                raise ValueError("AH settlement requires line")
            outcome = settle_asian_handicap(
                home_goals_90,
                away_goals_90,
                selection,
                Decimal(line),
            ).value
        elif market == "TOTALS":
            if line is None:
                raise ValueError("OU settlement requires line")
            outcome = settle_total_goals(
                home_goals_90 + away_goals_90,
                selection,
                Decimal(line),
            ).value
        elif market == "BTTS":
            actual = "YES" if home_goals_90 > 0 and away_goals_90 > 0 else "NO"
            outcome = "WIN" if selection == actual else "LOSS"
        else:
            raise ValueError(f"unsupported market {market}")
        return SettlementEvent(
            fixture_id=fixture_id,
            market=market,
            selection=selection,
            line=line,
            outcome=outcome,
        )
