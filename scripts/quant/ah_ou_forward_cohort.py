"""AH/OU 软最大值切换 · 前向 T−2h cohort 记录（只读落盘，切换后运行）。

按 `docs/operations/W2_AH_OU_SOFTMAX_SWITCH_PREREGISTRATION_20260928.json`
预注册判据，每场在 kickoff−2h 落盘三方方向：

* ``new``：``build_ah_ou_selections`` 的软最大值方向；
* ``old``：切换前 factor_score 链路的最后一次产出方向（由调用方传入，见
  ``old_ah_side`` 参数——切换后旧链路已停用，旧方向只能来自历史决策快照）；
* ``pure``：Pinnacle 主盘比例去水 q（q_home≥0.5 → HOME，q_over≥0.5 → OVER）。

只写 append-only JSONL，不写生产、不写推荐、不触发任何生产开关。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from w2.strategy.ah_ou_decision import DECISION_LEAD_TIME, build_ah_ou_selections

COHORT_SCHEMA = "w2.ah_ou_forward_cohort.v1"


@dataclass(frozen=True, kw_only=True)
class CohortRecord:
    fixture_id: str
    home_team_id: str
    away_team_id: str
    competition_id: str
    season: str
    kickoff: datetime
    ah_line: float
    ah_home_odds: float
    ah_away_odds: float
    ou_line: float
    ou_over_odds: float
    ou_under_odds: float
    old_ah_side: str | None = None  # 切换前 factor_score 方向，历史快照提供
    settlement_home_goals: int | None = None
    settlement_away_goals: int | None = None


def _pure_ah_side(home_odds: float, away_odds: float) -> str:
    q_home = (1 / home_odds) / ((1 / home_odds) + (1 / away_odds))
    return "HOME" if q_home >= 0.5 else "AWAY"


def _pure_ou_side(over_odds: float, under_odds: float) -> str:
    q_over = (1 / over_odds) / ((1 / over_odds) + (1 / under_odds))
    return "OVER" if q_over >= 0.5 else "UNDER"


def record_cohort(
    repository: Any,
    record: CohortRecord,
    *,
    path: Path,
) -> dict[str, Any]:
    """Append one T−2h cohort row. New/pure sides are computed; old is supplied."""
    decision_at = record.kickoff - DECISION_LEAD_TIME
    result = build_ah_ou_selections(
        repository,
        fixture_id=record.fixture_id,
        home_team_id=record.home_team_id,
        away_team_id=record.away_team_id,
        kickoff=record.kickoff,
        competition_id=record.competition_id,
        season=record.season,
        ah_line=record.ah_line,
        ah_home_odds=record.ah_home_odds,
        ah_away_odds=record.ah_away_odds,
        ou_line=record.ou_line,
        ou_over_odds=record.ou_over_odds,
        ou_under_odds=record.ou_under_odds,
    )
    new_ah = result["ah"]
    new_ou = result["ou"]
    row = {
        "schema": COHORT_SCHEMA,
        "fixture_id": record.fixture_id,
        "competition_id": record.competition_id,
        "season": record.season,
        "kickoff": record.kickoff.isoformat(),
        "decision_at": decision_at.isoformat(),
        "ah_line": record.ah_line,
        "ah_home_odds": record.ah_home_odds,
        "ah_away_odds": record.ah_away_odds,
        "ou_line": record.ou_line,
        "ou_over_odds": record.ou_over_odds,
        "ou_under_odds": record.ou_under_odds,
        "new_status": result["status"],
        "new_ah_side": new_ah.get("side") if new_ah else None,
        "new_ah_selected": bool(new_ah and new_ah.get("selected")),
        "new_ou_side": "OVER" if (new_ou and new_ou.get("selected")) else None,
        "new_ou_selected": bool(new_ou and new_ou.get("selected")),
        "old_ah_side": record.old_ah_side,
        "pure_ah_side": _pure_ah_side(record.ah_home_odds, record.ah_away_odds),
        "pure_ou_side": _pure_ou_side(record.ou_over_odds, record.ou_under_odds),
        "settlement_home_goals": record.settlement_home_goals,
        "settlement_away_goals": record.settlement_away_goals,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return row
