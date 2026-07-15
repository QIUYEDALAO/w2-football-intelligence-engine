from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from w2.tracking.day_view_capture_index import DayViewCaptureSummary


def project_day_view_card(row: Mapping[str, Any], summary: DayViewCaptureSummary) -> dict[str, Any]:
    return {
        **summary.as_card_fields(),
        "fixture_id": row.get("fixture_id"),
        "kickoff_utc": row.get("kickoff_utc"),
        "kickoff_beijing": row.get("kickoff_beijing"),
        "competition_id": row.get("competition_id"),
        "competition_name": row.get("competition_name"),
        "home_team_id": row.get("home_team_id"),
        "away_team_id": row.get("away_team_id"),
        "home_team_name": row.get("home_team_name"),
        "away_team_name": row.get("away_team_name"),
        "status": row.get("status"),
    }
