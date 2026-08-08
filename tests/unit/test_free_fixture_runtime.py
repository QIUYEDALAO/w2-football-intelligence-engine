from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest

from w2.competitions.registry import CompetitionRegistryEntry, CoverageProfile
from w2.ingestion.free_fixture_runtime import run_free_fixture_bridge_shadow
from w2.matchday.intake_v2 import parse_utc, stable_hash
from w2.providers.api_football import ApiFootballClient, LiveApiFootballResponse

NOW = datetime(2026, 8, 8, 5, 0, tzinfo=UTC)


def test_runtime_is_off_by_default_and_performs_no_io() -> None:
    result = run_free_fixture_bridge_shadow(mode="OFF")

    assert result["status"] == "DISABLED"
    assert result["provider_calls"] == 0


def test_shadow_runtime_persists_canonical_fixture_and_ah_ou_evidence() -> None:
    usage = FakeUsage(actual=5, remaining=95)
    evidence = FakeEvidence()
    client = FakeClient(
        usage,
        [
            ("fixtures", _fixture_payload("100")),
            ("odds", _odds_payload("100")),
        ],
    )

    result = _run(client, usage, evidence)

    assert result["status"] == "SHADOW_COMPLETE"
    assert result["provider_calls"] == 2
    assert result["active_whitelist_count"] == 1
    assert result["collection_states"]["api_football:100"] == [
        "DISCOVERY",
        "PREMATCH_MARKET",
    ]
    assert {row["endpoint"] for row in evidence.captures.values()} == {"fixtures", "odds"}
    assert evidence.identities[0]["fixture_id"] == "api_football:100"
    assert {row["canonical_market"] for row in evidence.observations} == {
        "ASIAN_HANDICAP",
        "TOTALS",
    }
    assert all(row["bookmaker_name"] == "Pinnacle" for row in evidence.observations)
    assert result["candidate"] is result["formal_recommendation"] is False
    assert result["recommendation_lock"] is result["production"] is False


def test_restart_continuity_uses_persisted_discovery_and_fresh_odds_cache() -> None:
    usage = FakeUsage(actual=5, remaining=95)
    evidence = FakeEvidence()
    first = FakeClient(
        usage,
        [("fixtures", _fixture_payload("100")), ("odds", _odds_payload("100"))],
    )
    assert _run(first, usage, evidence)["status"] == "SHADOW_COMPLETE"

    second = FakeClient(usage, [])
    result = _run(second, usage, evidence, now=NOW + timedelta(minutes=5))

    assert result["status"] == "SHADOW_COMPLETE"
    assert result["provider_calls"] == 0
    assert {row.get("skip_reason") for row in result["requests"]} == {
        "DISCOVERY_CACHED_NO_CALL",
        "FRESH_CAPTURE_CACHE_HIT",
    }


def test_no_target_fixture_has_zero_followup_calls() -> None:
    usage = FakeUsage(actual=5, remaining=95)
    evidence = FakeEvidence()
    client = FakeClient(usage, [("fixtures", _fixture_payload("100", league_id=999))])

    result = _run(client, usage, evidence)

    assert result["status"] == "SHADOW_COMPLETE"
    assert result["provider_calls"] == 1
    assert result["fixture_identity_count"] == 0
    assert result["selected_fixture_ids"] == []
    assert client.endpoints == ["fixtures"]


def test_postmatch_state_is_explicit_but_statistics_are_not_polled_automatically() -> None:
    usage = FakeUsage(actual=5, remaining=95)
    evidence = FakeEvidence()
    client = FakeClient(
        usage,
        [("fixtures", _fixture_payload("100", status="FT", kickoff=NOW - timedelta(hours=2)))],
    )

    result = _run(client, usage, evidence)

    assert result["collection_states"]["api_football:100"] == [
        "DISCOVERY",
        "POSTMATCH_STATISTICS",
    ]
    assert client.endpoints == ["fixtures"]


@pytest.mark.parametrize(
    ("remaining", "blocker"),
    [(20, "PROVIDER_RESERVE_PROTECTED"), (19, "PROVIDER_RESERVE_PROTECTED")],
)
def test_reserve_reached_stops_before_discovery(remaining: int, blocker: str) -> None:
    usage = FakeUsage(actual=5, remaining=remaining)
    result = _run(FakeClient(usage, []), usage, FakeEvidence())

    assert result["status"] == "BLOCKED"
    assert result["provider_calls"] == 0
    assert result["blockers"] == [blocker]


def test_unknown_quota_allows_only_status_reconciliation_then_stops() -> None:
    usage = FakeUsage(actual=5, remaining=None, limit=None)
    client = FakeClient(usage, [("status", _status_payload())], quota_headers=False)

    result = _run(client, usage, FakeEvidence())

    assert result["status"] == "BLOCKED"
    assert result["provider_calls"] == 1
    assert result["blockers"] == ["DAILY_QUOTA_UNKNOWN"]
    assert client.endpoints == ["status"]


def test_known_non_free_daily_limit_stops_before_discovery() -> None:
    usage = FakeUsage(actual=5, remaining=95, limit=200)
    client = FakeClient(usage, [])

    result = _run(client, usage, FakeEvidence())

    assert result["status"] == "BLOCKED"
    assert result["provider_calls"] == 0
    assert result["blockers"] == ["FREE_PROVIDER_DAILY_LIMIT_MISMATCH"]
    assert client.endpoints == []


@pytest.mark.parametrize(
    ("status_code", "payload", "blocker"),
    [
        (429, {"response": []}, "PROVIDER_HTTP_429"),
        (200, {"errors": {"plan": "restricted"}, "response": []}, "PLAN_RESTRICTED"),
        (200, {"response": {}}, "FREE_BRIDGE_SCHEMA_UNSAFE"),
        (
            200,
            {
                "response": [
                    {
                        "fixture": {
                            "id": None,
                            "date": "2026-08-08T11:00:00+00:00",
                            "status": {"short": "NS"},
                        },
                        "league": {"id": 113, "season": 2026},
                        "teams": {"home": {"id": 10}, "away": {"id": 20}},
                    }
                ]
            },
            "FREE_BRIDGE_EMPTY_OR_INVALID_FIXTURE_ID",
        ),
    ],
)
def test_discovery_hard_stops_preserve_capture_and_never_retry(
    status_code: int,
    payload: dict[str, Any],
    blocker: str,
) -> None:
    usage = FakeUsage(actual=5, remaining=95)
    evidence = FakeEvidence()
    client = FakeClient(usage, [("fixtures", payload, status_code)])

    result = _run(client, usage, evidence)

    assert result["status"] == "BLOCKED"
    assert result["provider_calls"] == 1
    assert result["blockers"] == [blocker]
    assert len(evidence.captures) == 1
    assert result["automatic_retries"] == 0
    assert client.endpoints == ["fixtures"]


def test_fixture_scoped_mismatch_stops_before_normalization_and_lower_priority_calls() -> None:
    usage = FakeUsage(actual=5, remaining=95)
    evidence = FakeEvidence()
    client = FakeClient(
        usage,
        [
            ("fixtures", _fixture_payload("100", checkpoint="T60")),
            ("odds", _odds_payload("999")),
        ],
    )

    result = _run(client, usage, evidence)

    assert result["status"] == "BLOCKED"
    assert result["blockers"] == ["FREE_BRIDGE_OUT_OF_WHITELIST_FIXTURE"]
    assert result["market_observations_written"] == 0
    assert list(evidence.captures.values())[-1]["capture_status"] == "FAILED"
    assert client.endpoints == ["fixtures", "odds"]


def test_heavy_day_orders_all_core_odds_before_optional_lineups() -> None:
    usage = FakeUsage(actual=5, remaining=95)
    evidence = FakeEvidence()
    payload = _fixture_payload("100", checkpoint="T60")
    payload["response"].append(_fixture_payload("101", checkpoint="T60")["response"][0])
    client = FakeClient(
        usage,
        [
            ("fixtures", payload),
            ("odds", _odds_payload("100")),
            ("odds", _odds_payload("101")),
            ("lineups", {"response": []}),
            ("lineups", {"response": []}),
        ],
    )

    result = _run(client, usage, evidence)

    assert result["status"] == "SHADOW_COMPLETE"
    assert client.endpoints == ["fixtures", "odds", "odds", "lineups", "lineups"]


def test_eightieth_global_call_is_allowed_but_eighty_first_is_blocked() -> None:
    usage = FakeUsage(actual=79, remaining=21)
    result = _run(
        FakeClient(usage, [("fixtures", _fixture_payload("100", league_id=999))]),
        usage,
        FakeEvidence(),
    )

    assert result["status"] == "SHADOW_COMPLETE"
    assert result["actual_calls_today"] == 80
    assert result["provider_remaining"] == 20

    blocked_usage = FakeUsage(actual=80, remaining=20)
    blocked = _run(FakeClient(blocked_usage, []), blocked_usage, FakeEvidence())
    assert blocked["status"] == "BLOCKED"
    assert blocked["provider_calls"] == 0


def _run(
    client: FakeClient,
    usage: FakeUsage,
    evidence: FakeEvidence,
    *,
    now: datetime = NOW,
) -> dict[str, Any]:
    return run_free_fixture_bridge_shadow(
        now=now,
        client=cast(ApiFootballClient, client),
        usage_repository=usage,
        evidence_repository=evidence,
        lineup_repository=FakeLineups(),
        registry=cast(Any, FakeRegistry()),
        mode="SHADOW_ONLY",
        source_revision="unit",
        expected_whitelist_size=1,
        require_persistent_ledger=False,
    )


class FakeUsage:
    def __init__(
        self,
        *,
        actual: int,
        remaining: int | None,
        limit: int | None = 100,
    ) -> None:
        self.actual = actual
        self.remaining = remaining
        self.limit = limit
        self.audits: list[dict[str, Any]] = []

    def request_count_since(self, since: datetime, *, include_quota_usage: bool = True) -> int:
        return self.actual

    def provider_quota_snapshot(self, day_start: datetime) -> dict[str, int | None]:
        used = self.limit - self.remaining if self.limit is not None and self.remaining else None
        return {"daily_limit": self.limit, "used": used, "remaining": self.remaining}

    def write_run_audit(self, payload: dict[str, Any]) -> None:
        self.audits.append(payload)


class FakeClient:
    def __init__(
        self,
        usage: FakeUsage,
        responses: list[
            tuple[str, dict[str, Any]] | tuple[str, dict[str, Any], int]
        ],
        *,
        quota_headers: bool = True,
    ) -> None:
        self.usage = usage
        self.responses = list(responses)
        self.quota_headers = quota_headers
        self.endpoints: list[str] = []

    def request_live(self, endpoint: str, params: dict[str, str]) -> LiveApiFootballResponse:
        expected = self.responses.pop(0)
        assert endpoint == expected[0]
        self.endpoints.append(endpoint)
        self.usage.actual += 1
        if self.usage.remaining is not None:
            self.usage.remaining -= 1
        headers = (
            {
                "x-ratelimit-requests-limit": str(self.usage.limit),
                "x-ratelimit-requests-remaining": str(self.usage.remaining),
            }
            if self.quota_headers
            else {}
        )
        return LiveApiFootballResponse(
            endpoint=endpoint,
            params=params,
            status_code=expected[2] if len(expected) == 3 else 200,
            elapsed_ms=1,
            payload=expected[1],
            headers=headers,
            requested_at=NOW,
            captured_at=NOW,
        )


class FakeEvidence:
    def __init__(self) -> None:
        self.raw: dict[str, dict[str, Any]] = {}
        self.captures: dict[str, dict[str, Any]] = {}
        self.identities: list[dict[str, Any]] = []
        self.observations: list[dict[str, Any]] = []
        self.plans: dict[str, dict[str, Any]] = {}

    def save_raw_payload(
        self,
        *,
        sha256: str,
        endpoint: str,
        captured_at: datetime,
        payload: Mapping[str, Any],
    ) -> bool:
        self.raw[sha256] = dict(payload)
        return True

    def insert_endpoint_capture(self, capture: Mapping[str, Any]) -> str:
        value = dict(capture)
        self.captures[str(value["capture_id"])] = value
        return str(value["capture_id"])

    def latest_endpoint_capture(
        self,
        *,
        request_task_key: str,
        since: datetime,
    ) -> dict[str, Any] | None:
        rows = [
            row
            for row in self.captures.values()
            if row["request_task_key"] == request_task_key
            and (parse_utc(row["provider_captured_at"]) or NOW) >= since
            and row["capture_status"] in {"CAPTURED", "PROVIDER_EMPTY"}
        ]
        if not rows:
            return None
        capture = rows[-1]
        return {
            "capture": capture,
            "payload": self.raw[str(capture["raw_payload_sha256"])],
        }

    def upsert_fixture_identities_with_business_changes(
        self,
        fixtures: Sequence[Mapping[str, Any]],
    ) -> tuple[int, list[str]]:
        self.identities = [dict(item) for item in fixtures]
        return len(fixtures), [str(item["fixture_id"]) for item in fixtures]

    def insert_market_observations(self, observations: Sequence[Mapping[str, Any]]) -> int:
        self.observations.extend(dict(item) for item in observations)
        return len(observations)

    def upsert_checkpoint_plan(self, plan: Mapping[str, Any] | Any) -> str:
        payload = plan.as_dict() if hasattr(plan, "as_dict") else dict(plan)
        plan_id = _plan_id(payload)
        existing = self.plans.get(plan_id)
        if existing is None or existing["status"] not in {"CAPTURED", "PROVIDER_EMPTY"}:
            self.plans[plan_id] = payload
        return plan_id

    def transition_checkpoint(self, **kwargs: Any) -> None:
        plan_id = stable_hash(
            ":".join(
                str(kwargs[key])
                for key in (
                    "fixture_id",
                    "competition_id",
                    "season",
                    "checkpoint",
                    "policy_version",
                )
            )
        )
        self.plans[plan_id]["status"] = kwargs["status"]

    def link_endpoint_capture_plans(self, **kwargs: Any) -> list[dict[str, Any]]:
        return []


class FakeLineups:
    def save_lineup_snapshots(self, **kwargs: Any) -> int:
        return 2


class FakeRegistry:
    def entries(self) -> dict[str, CompetitionRegistryEntry]:
        return {"allsvenskan": _entry()}


def _entry() -> CompetitionRegistryEntry:
    return CompetitionRegistryEntry(
        competition_id="allsvenskan",
        season="2026",
        enabled=False,
        coverage_profile=CoverageProfile(
            xg="UNKNOWN",
            lineups_injuries="UNKNOWN",
            squad_value="UNKNOWN",
            bookmaker_depth="UNKNOWN",
            h2h="UNKNOWN",
            settled_ah="UNKNOWN",
        ),
        config_path=Path("allsvenskan.json"),
        provider_mapping={
            "provider": "api_football",
            "api_football_league_id": "113",
            "api_football_season": "2026",
        },
        timezone="Europe/Stockholm",
        market_scope=("AH", "OU"),
        refresh_switches={},
        future_refresh_policy=None,
        matchday_policy={
            "competition_id": "allsvenskan",
            "provider": "api_football",
            "provider_league_id": "113",
            "season": "2026",
            "fixture_status_allowlist": ["NS", "TBD"],
            "checkpoints": [
                {
                    "name": "T6_ODDS",
                    "offset_seconds_before_kickoff": 21600,
                    "endpoints": ["odds"],
                    "grace_seconds": 1800,
                    "enabled": True,
                },
                {
                    "name": "T60_ODDS_LINEUPS",
                    "offset_seconds_before_kickoff": 3600,
                    "endpoints": ["odds", "lineups"],
                    "grace_seconds": 1200,
                    "enabled": True,
                }
            ],
            "odds_max_age_seconds": 3600,
        },
        scope_group="top_five",
        audit_cohort="",
        audit_order=1,
        config_hash="unit",
        profile_payload={},
    )


def _fixture_payload(
    fixture_id: str,
    *,
    league_id: int = 113,
    status: str = "NS",
    kickoff: datetime | None = None,
    checkpoint: str = "T6",
) -> dict[str, Any]:
    scheduled = kickoff or (
        NOW + timedelta(hours=1) if checkpoint == "T60" else NOW + timedelta(hours=6)
    )
    return {
        "response": [
            {
                "fixture": {
                    "id": int(fixture_id),
                    "date": scheduled.isoformat(),
                    "status": {"short": status},
                },
                "league": {"id": league_id, "season": 2026},
                "teams": {"home": {"id": 10}, "away": {"id": 20}},
            }
        ]
    }


def _odds_payload(fixture_id: str) -> dict[str, Any]:
    return {
        "response": [
            {
                "fixture": {"id": int(fixture_id)},
                "bookmakers": [
                    {
                        "id": 4,
                        "name": "Pinnacle",
                        "bets": [
                            {
                                "id": 33,
                                "name": "Asian Handicap",
                                "values": [
                                    {"value": "Home -0.5", "odd": "1.91"},
                                    {"value": "Away +0.5", "odd": "1.95"},
                                ],
                            },
                            {
                                "id": 5,
                                "name": "Goals Over/Under",
                                "values": [
                                    {"value": "Over 2.5", "odd": "1.90"},
                                    {"value": "Under 2.5", "odd": "1.96"},
                                ],
                            },
                        ],
                    }
                ],
            }
        ]
    }


def _status_payload() -> dict[str, Any]:
    return {"response": {"account": {"firstname": "redacted"}, "requests": {}}}


def _plan_id(plan: Mapping[str, Any]) -> str:
    return stable_hash(
        ":".join(
            str(plan[key])
            for key in (
                "fixture_id",
                "competition_id",
                "season",
                "checkpoint",
                "policy_version",
            )
        )
    )
