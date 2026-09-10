"""F1R-B: offline rows shaped exactly like the production projections.

Every row here has the field names and types a production reader already
returns, so the ports are exercised against the real shape rather than a mock
of it:

* history rows match `FutureRefreshDbRepository._canonical_match_history_dict`;
* capture rows match the `matchday_endpoint_captures` columns the ports read;
* snapshot rows match `FutureRefreshDbRepository._team_xg_rolling_snapshot_dict`.

These are offline test vectors, not production data. Nothing here was read from
a database, a Provider or a VPS. The capture identities the ports derive from
them are computed, not fabricated: they are the true hashes of this content,
which is exactly why they can be used to prove the identity rules.
"""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

FIXTURE_KIND = "OFFLINE_FIXTURE_ROWS_SHAPED_AS_PRODUCTION_PROJECTIONS"

KICKOFF = datetime(2026, 10, 1, 19, 30, tzinfo=UTC)
AS_OF = KICKOFF - timedelta(hours=1)
EVALUATED_AT = KICKOFF - timedelta(minutes=55)
CREATED_AT = KICKOFF - timedelta(minutes=54)

HOME_TEAM = "w2-team-home-1"
AWAY_TEAM = "w2-team-away-1"
COMPETITION = "offline_league"
SEASON = "2026"
PROVIDER = "api_football"
FIXTURE_ID = "9000001"

# The lag between a finished fixture and the provider read that carried it.
# Any positive value works; three hours is simply a plausible one.
CAPTURE_LAG = timedelta(hours=3)


def _hex(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def history_row(
    *,
    team_w2_id: str,
    opponent_w2_id: str,
    days_ago: int,
    goals_for: int,
    goals_against: int,
) -> dict[str, Any]:
    """One `canonical_team_match_history` row as production projects it."""
    kickoff = KICKOFF - timedelta(days=days_ago)
    provider_fixture_id = f"{8000000 + days_ago}"
    history_id = f"{PROVIDER}:{provider_fixture_id}:{team_w2_id}"
    capture_id = _hex(f"capture:{provider_fixture_id}")[:64]
    return {
        "history_id": history_id,
        "fixture_id": f"{PROVIDER}:{provider_fixture_id}",
        "provider": PROVIDER,
        "provider_fixture_id": provider_fixture_id,
        "competition_id": COMPETITION,
        "season": SEASON,
        "kickoff_utc": iso(kickoff),
        "fixture_status": "FT",
        "team_side": "HOME" if team_w2_id == HOME_TEAM else "AWAY",
        "team_provider_id": f"p-{team_w2_id}",
        "opponent_provider_id": f"p-{opponent_w2_id}",
        "team_w2_id": team_w2_id,
        "opponent_w2_id": opponent_w2_id,
        "goals_for": goals_for,
        "goals_against": goals_against,
        "result_identity_hash": _hex(f"result:{history_id}"),
        "source_raw_hash": _hex(f"raw:{provider_fixture_id}"),
        "endpoint_capture_id": capture_id,
        # The materialisation clock, deliberately earlier than the provider read
        # it points at. The ports must never use this as an evidence time.
        "captured_at": iso(kickoff + timedelta(minutes=30)),
        "history_hash": _hex(f"history:{history_id}"),
    }


def capture_row(history: dict[str, Any], *, status: str = "CAPTURED") -> dict[str, Any]:
    """The `matchday_endpoint_captures` row a history row points at."""
    kickoff = datetime.fromisoformat(history["kickoff_utc"].replace("Z", "+00:00"))
    return {
        "capture_id": history["endpoint_capture_id"],
        "endpoint": "fixtures",
        "provider_captured_at": iso(kickoff + CAPTURE_LAG),
        "raw_payload_sha256": history["source_raw_hash"],
        "capture_status": status,
    }


def xg_snapshot_row(*, team_id: str, days_ago: int, xg_for: float,
                    xg_against: float) -> dict[str, Any]:
    """One `team_xg_rolling_snapshot` row as production projects it."""
    return {
        "snapshot_id": f"{team_id}:{FIXTURE_ID}",
        "team_id": team_id,
        "as_of_fixture_id": FIXTURE_ID,
        "as_of_time": iso(AS_OF - timedelta(days=days_ago)),
        "match_count": 5,
        "rolling_xg_for": xg_for,
        "rolling_xg_against": xg_against,
        "rolling_goals_for": 1.6,
        "rolling_goals_against": 1.0,
        "regression_index": 0.12,
        "source_system": "api_football_statistics",
        "candidate": False,
        "formal_recommendation": False,
    }


def event_time_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop every result field, leaving what F3 is allowed to read."""
    dropped = {"goals_for", "goals_against", "result_identity_hash",
               "settlement_outcome", "ah_result"}
    return [{key: value for key, value in row.items() if key not in dropped}
            for row in rows]
