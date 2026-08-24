from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

FINISHED_FIXTURE_STATUSES = frozenset({"FT", "AET", "PEN"})
NON_PLAYED_FIXTURE_STATUSES = frozenset({"PST", "CANC", "ABD"})
EXPECTED_MATCH_LIMIT = 20
EXPECTED_MATCH_MINIMUM = 3


def materialize_saved_fixture_observations(
    *,
    raw_payload_sha256: str,
    raw_captured_at: datetime,
    raw_inserted_at: datetime,
    payload: Mapping[str, Any],
    materialized_at: datetime,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Project one persisted fixture payload into immutable PIT observations."""
    captured_at = _aware_utc(raw_captured_at)
    inserted_at = _aware_utc(raw_inserted_at)
    projected_at = _aware_utc(materialized_at)
    response = payload.get("response")
    if not isinstance(response, list):
        return [], [{"reason": "RAW_FIXTURE_RESPONSE_INVALID", "sample": raw_payload_sha256}]

    observations: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []
    fixture_identities: dict[str, tuple[str, str, str, datetime]] = {}
    for item in response:
        if not isinstance(item, Mapping):
            rejected.append({"reason": "RAW_FIXTURE_ITEM_INVALID", "sample": repr(item)[:160]})
            continue
        fixture = item.get("fixture")
        league = item.get("league")
        teams = item.get("teams")
        goals = item.get("goals")
        fixture = fixture if isinstance(fixture, Mapping) else {}
        league = league if isinstance(league, Mapping) else {}
        teams = teams if isinstance(teams, Mapping) else {}
        goals = goals if isinstance(goals, Mapping) else {}
        home = teams.get("home")
        away = teams.get("away")
        status = fixture.get("status")
        home = home if isinstance(home, Mapping) else {}
        away = away if isinstance(away, Mapping) else {}
        status = status if isinstance(status, Mapping) else {}
        provider_fixture_id = _text(fixture.get("id"))
        provider_league_id = _text(league.get("id"))
        season = _text(league.get("season"))
        home_team_id = _text(home.get("id"))
        away_team_id = _text(away.get("id"))
        status_short = _text(status.get("short")).upper()
        try:
            kickoff_at = _aware_utc(fixture.get("date"))
        except (TypeError, ValueError):
            kickoff_at = None
        missing = [
            name
            for name, value in (
                ("provider_fixture_id", provider_fixture_id),
                ("provider_league_id", provider_league_id),
                ("season", season),
                ("home_provider_team_id", home_team_id),
                ("away_provider_team_id", away_team_id),
                ("fixture_status", status_short),
                ("kickoff_at", kickoff_at),
            )
            if not value
        ]
        if missing or home_team_id == away_team_id:
            rejected.append(
                {
                    "reason": "CANONICAL_PROVIDER_FIXTURE_IDENTITY_INVALID",
                    "sample": f"{provider_fixture_id or 'UNKNOWN'}:{','.join(missing)}",
                }
            )
            continue
        canonical_fixture_id = f"api_football:{provider_fixture_id}"
        provider_identity = (
            provider_league_id,
            home_team_id,
            away_team_id,
            kickoff_at,
        )
        prior_identity = fixture_identities.get(provider_fixture_id)
        if prior_identity is not None:
            if prior_identity != provider_identity:
                rejected.append(
                    {
                        "reason": "CANONICAL_PROVIDER_FIXTURE_IDENTITY_CONFLICT",
                        "sample": provider_fixture_id,
                    }
                )
            continue
        fixture_identities[provider_fixture_id] = provider_identity
        identity = {
            "provider": "api_football",
            "provider_fixture_id": provider_fixture_id,
            "canonical_fixture_id": canonical_fixture_id,
            "provider_league_id": provider_league_id,
            "season": season,
            "kickoff_at": kickoff_at,
            "home_provider_team_id": home_team_id,
            "away_provider_team_id": away_team_id,
            "fixture_status": status_short,
            "home_goals": _integer_or_none(goals.get("home")),
            "away_goals": _integer_or_none(goals.get("away")),
            "raw_payload_sha256": raw_payload_sha256,
            "captured_at": captured_at,
            "source_inserted_at": inserted_at,
            "materialized_at": projected_at,
        }
        observations.append(
            {
                "observation_hash": _observation_hash(identity),
                **identity,
            }
        )
    return observations, rejected


def classify_expected_match_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    team_id: str,
    limit: int = EXPECTED_MATCH_LIMIT,
) -> dict[str, Any]:
    """Classify latest PIT fixture rows for one team without inventing evidence."""
    expected: list[dict[str, Any]] = []
    for row in rows:
        status = _text(row.get("fixture_status")).upper()
        if status in NON_PLAYED_FIXTURE_STATUSES:
            continue
        if status not in FINISHED_FIXTURE_STATUSES:
            return _fail_closed("EXPECTED_MATCH_RESULT_NOT_VISIBLE_AT_AS_OF", team_id)
        if row.get("home_goals") is None or row.get("away_goals") is None:
            return _fail_closed("EXPECTED_MATCH_RESULT_MISSING_AT_AS_OF", team_id)
        expected.append(dict(row))
        if len(expected) == limit:
            break
    if len(expected) < EXPECTED_MATCH_MINIMUM:
        return _fail_closed("EXPECTED_MATCH_DENOMINATOR_INSUFFICIENT", team_id)
    return {
        "status": "AVAILABLE",
        "team_id": team_id,
        "expected_match_count": len(expected),
        "canonical_fixture_ids": [str(row["canonical_fixture_id"]) for row in expected],
        "rows": expected,
        "high_confidence_allowed": True,
    }


def _fail_closed(reason: str, team_id: str) -> dict[str, Any]:
    return {
        "status": "UNAVAILABLE_FAIL_CLOSED",
        "reason": reason,
        "team_id": team_id,
        "expected_match_count": None,
        "canonical_fixture_ids": [],
        "rows": [],
        "high_confidence_allowed": False,
    }


def _observation_hash(identity: Mapping[str, Any]) -> str:
    serializable = {
        key: value.astimezone(UTC).isoformat().replace("+00:00", "Z")
        if isinstance(value, datetime)
        else value
        for key, value in identity.items()
        if key != "materialized_at"
    }
    encoded = json.dumps(serializable, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _aware_utc(value: Any) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("EXPECTED_MATCH_DATETIME_MUST_BE_AWARE")
    return value.astimezone(UTC)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _integer_or_none(value: Any) -> int | None:
    return None if value is None else int(value)
