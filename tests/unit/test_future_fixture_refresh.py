from __future__ import annotations

import hashlib
import json
from base64 import b64encode
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from w2.competitions.seed import apply_collection_policy_update, seed_competition_runtime_authority
from w2.config import get_settings
from w2.infrastructure.database import Base
from w2.infrastructure.persistence.future_refresh_models import FutureRefreshRunAuditModel
from w2.ingestion.future_refresh import (
    FutureFixtureRefreshService,
    FutureRefreshConfig,
    FutureRefreshError,
    FutureRefreshResult,
    RefreshSingletonLock,
    canonical_market,
    config_from_policy,
    deterministic_task_key,
    load_refresh_policy,
    observations_from_odds_payload,
    parse_line,
    refresh_progress_status,
    run_future_refresh_task,
)
from w2.ingestion.raw_fixture_scope import RawFixtureScope
from w2.markets.quote_identity import evaluate_quote_freshness, project_quote_identity
from w2.operations.gate_a import (
    GATE_A_SELECTION_POLICY_VERSION,
    GATE_A_SELECTION_RULE,
    GateARuntimeAuthorization,
    TrustedApprovalKey,
    authorization_signing_message,
)
from w2.providers.api_football import LiveApiFootballResponse
from w2.providers.control import (
    free_plan_fixture_scope_restriction,
    is_free_plan_fixture_scope_restricted,
)

NOW = datetime(2026, 6, 23, 10, 0, tzinfo=UTC)


def _refresh_result(**overrides: Any) -> FutureRefreshResult:
    values: dict[str, Any] = {
        "generated_at_utc": NOW,
        "fixture_count": 1,
        "mapping_count": 1,
        "market_snapshot_count": 0,
        "feature_enrichment_payload_count": 0,
        "ledger_appended_count": 0,
        "request_count": 1,
        "remaining_quota": 99,
        "selected_market_fixture_ids": ["1001"],
    }
    values.update(overrides)
    return FutureRefreshResult(**values)


def test_refresh_progress_distinguishes_data_empty_and_failure() -> None:
    assert refresh_progress_status(_refresh_result(market_snapshot_count=1)) == "DATA_PROGRESS"
    assert refresh_progress_status(_refresh_result()) == "PROVIDER_EMPTY"
    assert (
        refresh_progress_status(_refresh_result(blockers=["PROVIDER_REQUEST_FAILED"])) == "FAILED"
    )


def test_free_plan_fixture_scope_restriction_is_exact() -> None:
    assert free_plan_fixture_scope_restriction({"league": "39", "season": "2026"}) is not None
    assert free_plan_fixture_scope_restriction({"league": "39", "season": "2025"}) is None
    assert free_plan_fixture_scope_restriction({"league": "140", "season": "2026"}) == {
        "competition_id": "la_liga",
        "sample_count": 3,
        "observed_at_utc": "2026-08-12T05:54:21Z/2026-08-14T00:01:01Z",
        "payload_sha256": "1ab19d614ffaa2fd97cd2abddaeaa6e199ddc5de2e6a6b29606833704cf98ab8",
        "provider_error": (
            "Free plans do not have access to this season, try from 2022 to 2024."
        ),
    }
    assert (
        free_plan_fixture_scope_restriction(
            {"id": "1494248", "league": "39", "season": "2026"}
        )
        is None
    )


def test_free_plan_fixture_scope_restriction_matches_only_exact_provider_error() -> None:
    assert is_free_plan_fixture_scope_restricted(
        {
            "errors": {
                "plan": "Free plans do not have access to this season, try from 2022 to 2024."
            },
            "response": [],
        }
    )
    assert not is_free_plan_fixture_scope_restricted(
        {"errors": {"plan": "another restriction"}, "response": []}
    )


def test_runtime_scope_observation_overrides_static_seed(tmp_path: Path) -> None:
    service = FutureFixtureRefreshService(
        client=FakeApiFootballClient(),
        config=FutureRefreshConfig(
            runtime_root=tmp_path,
            competition_id="premier_league",
            league_id="39",
            season="2026",
            persistence="db",
        ),
        now=NOW,
    )

    class Repository:
        @staticmethod
        def latest_provider_quota_authority() -> dict[str, Any]:
            return {"daily_limit": 100}

        @staticmethod
        def free_plan_fixture_scope_state(**_kwargs: Any) -> dict[str, Any]:
            return {"observed": True, "restriction": None, "consecutive_count": 0}

        @staticmethod
        def record_free_plan_fixture_scope_observation(**_kwargs: Any) -> dict[str, Any]:
            return {
                "observed": True,
                "restriction": {"sample_count": 3},
                "consecutive_count": 3,
                "newly_confirmed": True,
            }

    service._db_repository = lambda: Repository()  # type: ignore[method-assign]

    assert service._free_plan_fixture_scope_restriction(
        {"league": "39", "season": "2026"}
    ) is None
    observation = service._record_free_plan_fixture_scope_observation(
        endpoint="fixtures",
        params={"league": "253", "season": "2027"},
        payload={
            "errors": {
                "plan": "Free plans do not have access to this season, try from 2022 to 2024."
            },
            "response": [],
        },
        payload_sha256="a" * 64,
        captured_at=NOW,
    )
    assert observation is not None and observation["newly_confirmed"] is True
    assert service._free_plan_restriction_auto_detected_count == 1


def test_pro_quota_authority_disables_free_scope_seed(tmp_path: Path) -> None:
    service = FutureFixtureRefreshService(
        client=FakeApiFootballClient(),
        config=FutureRefreshConfig(
            runtime_root=tmp_path,
            competition_id="premier_league",
            league_id="39",
            season="2026",
            persistence="db",
        ),
        now=NOW,
    )

    class Repository:
        @staticmethod
        def latest_provider_quota_authority() -> dict[str, Any]:
            return {"daily_limit": 7500}

    service._db_repository = lambda: Repository()  # type: ignore[method-assign]

    assert service._free_plan_fixture_scope_restriction(
        {"league": "39", "season": "2026"}
    ) is None


def test_future_refresh_skips_confirmed_free_plan_restricted_scope_without_dispatch(
    tmp_path: Path,
) -> None:
    client = FakeApiFootballClient()
    result = FutureFixtureRefreshService(
        client=client,
        config=FutureRefreshConfig(
            runtime_root=tmp_path,
            competition_id="premier_league",
            league_id="39",
            season="2026",
            persistence="file",
        ),
        now=NOW,
    ).run()

    assert result.status == "SKIPPED_FREE_PLAN_RESTRICTED"
    assert result.request_count == 0
    assert result.skipped_free_plan_restricted_count == 1
    assert client.calls == []
    audit = json.loads((tmp_path / "future_refresh_audit.json").read_text(encoding="utf-8"))
    assert audit["skipped_free_plan_restricted_count"] == 1
    assert audit["requests"] == [
        {
            "attempt": 0,
            "captured_at_utc": "2026-06-23T10:00:00Z",
            "diagnostic_code": "SKIPPED_FREE_PLAN_RESTRICTED",
            "elapsed_ms": 0,
            "endpoint": "fixtures",
            "error_code": None,
            "params": {
                "from": "2026-06-23",
                "league": "39",
                "season": "2026",
                "to": "2026-06-27",
            },
            "payload_sha256": None,
            "provider_dispatched": False,
            "response_count": 0,
            "restriction_evidence": free_plan_fixture_scope_restriction(
                {"league": "39", "season": "2026"}
            ),
            "status_code": None,
        }
    ]


def _gate_a_authorization() -> GateARuntimeAuthorization:
    signing_key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    payload: dict[str, object] = {
        "schema_version": "w2.gate-a-one-shot-authorization.v4",
        "action": "ONE_SHOT_FOREGROUND_CANARY",
        "review_status": "APPROVED",
        "one_shot": True,
        "persistence": "db",
        "authorization_id": "offline-test",
        "task_key": "future-refresh:world_cup_2026:2026:20260623T100000Z",
        "fixture_id": "1001",
        "competition_id": "world_cup_2026",
        "season": "2026",
        "provider_league_id": "1",
        "competition_policy_config_hash": "d" * 64,
        "fixture_scope_mode": "EXACT_FIXTURE_ID",
        "kickoff_window_start_utc": None,
        "kickoff_window_end_utc": None,
        "selection_policy_version": GATE_A_SELECTION_POLICY_VERSION,
        "selection_rule": GATE_A_SELECTION_RULE,
        "exact_head": "a" * 40,
        "exact_tree": "b" * 40,
        "execution_mode": "COMPLETE_CLEAN_CHECKOUT",
        "runtime_artifact_digest": None,
        "complete_checkout_manifest_sha256": "c" * 64,
        "allowed_endpoints": ["status", "fixtures", "odds", "lineups"],
        "provider_call_cap": 5,
        "issued_at": "2026-06-23T09:59:00Z",
        "expires_at": "2026-06-23T10:30:00Z",
        "author": "implementer",
        "reviewer": "reviewer",
        "approval_mode": "INDEPENDENT_ED25519",
        "approval_key_id": "test-independent-key",
    }
    public_key = b64encode(
        signing_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    ).decode()
    public_key_sha256 = hashlib.sha256(
        signing_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    ).hexdigest()
    payload["approval_public_key_sha256"] = public_key_sha256
    payload["approval_custody_status"] = "INDEPENDENT_SIGNER_CONFIRMED"
    payload["approval_signature"] = b64encode(
        signing_key.sign(authorization_signing_message(payload))
    ).decode()
    return GateARuntimeAuthorization.from_mapping(
        payload,
        trusted_public_keys={
            "test-independent-key": TrustedApprovalKey(
                public_key_base64=public_key,
                public_key_sha256=public_key_sha256,
                custody_status="INDEPENDENT_SIGNER_CONFIRMED",
                authorization_enabled=True,
            )
        },
    )


class _CallReservation:
    def __init__(self) -> None:
        self.endpoints: list[str] = []
        self.final_statuses: list[str] = []
        self.outcomes: list[tuple[int, str, str | None]] = []

    def reserve_provider_call(self, endpoint: str, *, fixture_id: str | None = None) -> int:
        del fixture_id
        self.endpoints.append(endpoint)
        return len(self.endpoints)

    def finalize(self, status: str) -> None:
        self.final_statuses.append(status)

    def record_provider_outcome(
        self,
        ordinal: int,
        *,
        state: str,
        error_code: str | None = None,
    ) -> None:
        self.outcomes.append((ordinal, state, error_code))


class FakeApiFootballClient:
    def __init__(
        self,
        *,
        remaining: int = 7000,
        status_code: int = 200,
        burst_remaining: int | None = None,
        daily_header: str = "x-ratelimit-requests-remaining",
        include_status_daily_payload: bool = True,
    ) -> None:
        self.remaining = remaining
        self.status_code = status_code
        self.burst_remaining = burst_remaining
        self.daily_header = daily_header
        self.include_status_daily_payload = include_status_daily_payload
        self.calls: list[tuple[str, dict[str, str]]] = []

    def request_live(self, endpoint: str, params: dict[str, str]) -> LiveApiFootballResponse:
        self.calls.append((endpoint, params))
        payload = self.payload(endpoint, params)
        headers = {self.daily_header: str(self.remaining)}
        if self.burst_remaining is not None:
            headers["x-ratelimit-remaining"] = str(self.burst_remaining)
        return LiveApiFootballResponse(
            endpoint=endpoint,
            params=params,
            status_code=self.status_code,
            elapsed_ms=7,
            payload=payload,
            headers=headers,
            captured_at=NOW,
        )

    def payload(self, endpoint: str, params: dict[str, str]) -> dict[str, Any]:
        if endpoint == "status":
            if not self.include_status_daily_payload:
                return {"response": {"requests": {}}}
            return {"response": {"requests": {"remaining": self.remaining}}}
        if endpoint == "fixtures":
            return {
                "response": [
                    {
                        "fixture": {
                            "id": 1489404,
                            "date": "2026-06-23T17:00:00+00:00",
                            "status": {"short": "NS"},
                            "venue": {"name": "Test Venue"},
                        },
                        "league": {"id": 1, "name": "World Cup", "round": "Group K"},
                        "teams": {
                            "home": {"id": 10, "name": "Team A"},
                            "away": {"id": 20, "name": "Team B"},
                        },
                    },
                    {
                        "fixture": {
                            "id": 1480000,
                            "date": "2026-06-22T17:00:00+00:00",
                            "status": {"short": "NS"},
                        },
                        "league": {"id": 1, "name": "World Cup"},
                        "teams": {"home": {"id": 1}, "away": {"id": 2}},
                    },
                ]
            }
        if endpoint == "odds":
            return {
                "response": [
                    {
                        "fixture": {"id": int(params["fixture"])},
                        "bookmakers": [
                            {
                                "id": 1,
                                "name": "Book A",
                                "bets": [
                                    {
                                        "id": 1,
                                        "name": "Match Winner",
                                        "values": [
                                            {"value": "Home", "odd": "1.80"},
                                            {"value": "Draw", "odd": "3.70"},
                                        ],
                                    }
                                ],
                            },
                            {
                                "id": 2,
                                "name": "Book B",
                                "bets": [
                                    {
                                        "id": 1,
                                        "name": "Match Winner",
                                        "values": [{"value": "Home", "odd": "1.82"}],
                                    }
                                ],
                            },
                        ],
                    }
                ]
            }
        if endpoint == "statistics":
            return {
                "response": [
                    {
                        "team": {"id": 10},
                        "statistics": [{"type": "expected_goals", "value": "1.5"}],
                    },
                    {
                        "team": {"id": 20},
                        "statistics": [{"type": "expected_goals", "value": "0.8"}],
                    },
                ]
            }
        if endpoint == "lineups":
            return {
                "response": [
                    {"team": {"id": 10}, "startXI": [{} for _ in range(11)], "substitutes": []},
                    {"team": {"id": 20}, "startXI": [{} for _ in range(11)], "substitutes": [{}]},
                ]
            }
        if endpoint == "injuries":
            return {"response": []}
        raise AssertionError(endpoint)


class _FailingProvider:
    def __init__(self) -> None:
        self.calls = 0

    def request_live(self, endpoint: str, params: dict[str, str]) -> LiveApiFootballResponse:
        self.calls += 1
        raise TimeoutError("uncertain")


class _SchemaDriftProvider(FakeApiFootballClient):
    def payload(self, endpoint: str, params: dict[str, str]) -> dict[str, Any]:
        if endpoint == "fixtures":
            return {"response": {"unexpected": True}}
        return super().payload(endpoint, params)


class _ProviderErrorsWithoutQuota(FakeApiFootballClient):
    def request_live(self, endpoint: str, params: dict[str, str]) -> LiveApiFootballResponse:
        self.calls.append((endpoint, params))
        return LiveApiFootballResponse(
            endpoint=endpoint,
            params=params,
            status_code=200,
            elapsed_ms=7,
            payload={"errors": {"plan": "restricted"}, "response": {}},
            headers={},
            captured_at=NOW,
        )


class _EmptyFixturesProvider(FakeApiFootballClient):
    def payload(self, endpoint: str, params: dict[str, str]) -> dict[str, Any]:
        if endpoint == "fixtures":
            return {"response": []}
        return super().payload(endpoint, params)


def test_fixture_identity_uses_existing_provider_team_authority(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    class Repository:
        @staticmethod
        def provider_team_mapping(**kwargs: Any) -> dict[str, str]:
            assert kwargs["provider"] == "api_football"
            assert kwargs["competition_id"] == "world_cup_2026"
            assert kwargs["season"] == "2026"
            assert kwargs["as_of"] == NOW
            return {"10": "w2:team:10", "20": "w2:team:20"}

    client = FakeApiFootballClient()
    response = client.request_live("fixtures", {})
    service = FutureFixtureRefreshService(
        client=client,
        config=FutureRefreshConfig(runtime_root=tmp_path, persistence="db"),
        now=NOW,
    )
    monkeypatch.setattr(service, "_db_repository", Repository)

    identities = service._fixture_identities_from_response(
        fixtures_response=response,
        fixtures=service._future_fixtures(response.payload),
    )

    assert identities[0]["home_w2_team_id"] == "w2:team:10"
    assert identities[0]["away_w2_team_id"] == "w2:team:20"
    assert identities[0]["team_identity_status"] == "PROVIDER_PRIMARY_READY"


def test_canonical_market_keeps_only_full_time_asian_handicap_in_ah_pool() -> None:
    assert canonical_market("Asian Handicap") == "ASIAN_HANDICAP"
    assert canonical_market("Handicap") == "ASIAN_HANDICAP"
    assert canonical_market("Asian Handicap First Half") == "ASIAN_HANDICAP_FIRST_HALF"
    assert canonical_market("Asian Handicap (2nd Half)") == "ASIAN_HANDICAP_(2ND_HALF)"
    assert canonical_market("Corners Asian Handicap") == "CORNERS_ASIAN_HANDICAP"
    assert canonical_market("Yellow Asian Handicap") == "YELLOW_ASIAN_HANDICAP"


def test_parse_line_preserves_asian_split_quarter_lines() -> None:
    assert parse_line("Over 2/2.5") == "2.25"
    assert parse_line("Under 2 - 2.5") == "2.25"
    assert parse_line("Home -0/0.5") == "-0.25"
    assert parse_line("Away +0.5/1") == "0.75"
    assert parse_line("Over 2.5") == "2.5"


def test_odds_payload_does_not_put_half_or_card_handicap_into_full_time_ah_pool() -> None:
    payload = {
        "response": [
            {
                "fixture": {"id": 1489404},
                "bookmakers": [
                    {
                        "id": 1,
                        "name": "Book A",
                        "bets": [
                            {
                                "id": 4,
                                "name": "Asian Handicap",
                                "values": [
                                    {"value": "Home -1.25", "odd": "1.91"},
                                    {"value": "Away +1.25", "odd": "1.97"},
                                ],
                            },
                            {
                                "id": 5,
                                "name": "Asian Handicap First Half",
                                "values": [
                                    {"value": "Home -0.5", "odd": "1.88"},
                                    {"value": "Away +0.5", "odd": "2.00"},
                                ],
                            },
                            {
                                "id": 6,
                                "name": "Cards Asian Handicap",
                                "values": [
                                    {"value": "Home -1.5", "odd": "1.90"},
                                    {"value": "Away +1.5", "odd": "1.98"},
                                ],
                            },
                        ],
                    }
                ],
            }
        ]
    }
    response = LiveApiFootballResponse(
        endpoint="odds",
        params={"fixture": "1489404"},
        status_code=200,
        elapsed_ms=7,
        payload=payload,
        headers={},
        captured_at=NOW,
    )

    rows = observations_from_odds_payload(
        fixture_id="1489404",
        payload=payload,
        response=response,
        source_revision="test",
        raw_payload_sha256="payload",
    )

    full_time_ah_rows = [row for row in rows if row["canonical_market"] == "ASIAN_HANDICAP"]
    assert {row["raw_market_label"] for row in full_time_ah_rows} == {"Asian Handicap"}
    assert {row["line"] for row in full_time_ah_rows} == {"-1.25", "+1.25"}
    assert {
        row["canonical_market"] for row in rows if row["raw_market_label"] != "Asian Handicap"
    } == {"ASIAN_HANDICAP_FIRST_HALF", "CARDS_ASIAN_HANDICAP"}


def test_odds_payload_records_split_totals_line_as_quarter_line() -> None:
    payload = {
        "response": [
            {
                "fixture": {"id": 1489404},
                "bookmakers": [
                    {
                        "id": 1,
                        "name": "Book A",
                        "bets": [
                            {
                                "id": 5,
                                "name": "Goals Over/Under",
                                "values": [
                                    {"value": "Over 2/2.5", "odd": "2.03"},
                                    {"value": "Under 2/2.5", "odd": "1.85"},
                                ],
                            },
                        ],
                    },
                ],
            },
        ],
    }
    response = LiveApiFootballResponse(
        endpoint="odds",
        params={"fixture": "1489404"},
        status_code=200,
        elapsed_ms=7,
        payload=payload,
        headers={},
        captured_at=NOW,
    )

    rows = observations_from_odds_payload(
        fixture_id="1489404",
        payload=payload,
        response=response,
        source_revision="test",
        raw_payload_sha256="payload",
    )

    totals_rows = [row for row in rows if row["canonical_market"] == "TOTALS"]
    assert {row["line"] for row in totals_rows} == {"2.25"}
    assert {row["decimal_odds"] for row in totals_rows} == {"2.03", "1.85"}


def test_unchanged_odds_reobserved_later_get_new_append_only_capture_identity() -> None:
    client = FakeApiFootballClient()
    payload = client.payload("odds", {"fixture": "1489404"})
    first_response = LiveApiFootballResponse(
        endpoint="odds",
        params={"fixture": "1489404"},
        status_code=200,
        elapsed_ms=7,
        payload=payload,
        headers={},
        captured_at=NOW,
    )
    confirmed_at = NOW + timedelta(minutes=45)
    second_response = LiveApiFootballResponse(
        endpoint="odds",
        params={"fixture": "1489404"},
        status_code=200,
        elapsed_ms=7,
        payload=payload,
        headers={},
        captured_at=confirmed_at,
    )

    first = observations_from_odds_payload(
        fixture_id="1489404",
        payload=payload,
        response=first_response,
        source_revision="test",
        raw_payload_sha256="same-payload",
    )
    replay = observations_from_odds_payload(
        fixture_id="1489404",
        payload=payload,
        response=first_response,
        source_revision="test",
        raw_payload_sha256="same-payload",
    )
    confirmed = observations_from_odds_payload(
        fixture_id="1489404",
        payload=payload,
        response=second_response,
        source_revision="test",
        raw_payload_sha256="same-payload",
    )

    assert [row["observation_id"] for row in replay] == [row["observation_id"] for row in first]
    assert {row["observation_id"] for row in first}.isdisjoint(
        row["observation_id"] for row in confirmed
    )
    assert {row["captured_at"] for row in first} == {NOW.isoformat().replace("+00:00", "Z")}
    assert {row["captured_at"] for row in confirmed} == {
        confirmed_at.isoformat().replace("+00:00", "Z")
    }


def test_unchanged_ah_odds_later_confirmation_restores_complete_freshness() -> None:
    payload = {
        "response": [
            {
                "fixture": {"id": 1489404},
                "bookmakers": [
                    {
                        "id": 1,
                        "name": "Book A",
                        "bets": [
                            {
                                "id": 4,
                                "name": "Asian Handicap",
                                "values": [
                                    {"value": "Home -0.5", "odd": "1.91"},
                                    {"value": "Away +0.5", "odd": "1.97"},
                                ],
                            }
                        ],
                    }
                ],
            }
        ]
    }

    def observations_at(captured_at: datetime) -> list[dict[str, Any]]:
        response = LiveApiFootballResponse(
            endpoint="odds",
            params={"fixture": "1489404"},
            status_code=200,
            elapsed_ms=7,
            payload=payload,
            headers={},
            captured_at=captured_at,
        )
        return observations_from_odds_payload(
            fixture_id="1489404",
            payload=payload,
            response=response,
            source_revision="test",
            raw_payload_sha256="same-payload-hash",
        )

    first_rows = observations_at(NOW)
    confirmed_at = NOW + timedelta(minutes=45)
    confirmed_rows = observations_at(confirmed_at)

    def freshness(rows: list[dict[str, Any]]) -> dict[str, Any]:
        by_selection = {str(row["selection"]).split()[0].lower(): row for row in rows}
        identity = project_quote_identity(
            market="ASIAN_HANDICAP",
            selected_line="-0.5",
            authoritative_rows={
                "home": by_selection["home"],
                "away": by_selection["away"],
            },
        )
        return evaluate_quote_freshness(
            identity,
            evaluated_at=confirmed_at + timedelta(minutes=1),
        )

    assert freshness(first_rows)["freshness_status"] == "STALE"
    confirmed_freshness = freshness(confirmed_rows)
    assert confirmed_freshness["freshness_status"] == "COMPLETE"
    assert confirmed_freshness["age_seconds"] == 60
    assert {row["raw_payload_sha256"] for row in confirmed_rows} == {"same-payload-hash"}


class ManyFutureFixturesClient(FakeApiFootballClient):
    def payload(self, endpoint: str, params: dict[str, str]) -> dict[str, Any]:
        if endpoint != "fixtures":
            return super().payload(endpoint, params)
        return {
            "response": [
                {
                    "fixture": {
                        "id": 1489400 + index,
                        "date": f"2026-06-23T{11 + index:02d}:00:00+00:00",
                        "status": {"short": "NS"},
                    },
                    "league": {"id": 1, "name": "World Cup", "round": "Group K"},
                    "teams": {
                        "home": {"id": 100 + index, "name": f"Team H {index}"},
                        "away": {"id": 200 + index, "name": f"Team A {index}"},
                    },
                }
                for index in range(12)
            ]
        }


class EmptyLineupsClient(FakeApiFootballClient):
    def payload(self, endpoint: str, params: dict[str, str]) -> dict[str, Any]:
        if endpoint == "lineups":
            return {"response": []}
        return super().payload(endpoint, params)


class NineFutureFixturesClient(FakeApiFootballClient):
    def payload(self, endpoint: str, params: dict[str, str]) -> dict[str, Any]:
        if endpoint != "fixtures":
            return super().payload(endpoint, params)
        return {
            "response": [
                {
                    "fixture": {
                        "id": 1489400 + index,
                        "date": f"2026-06-23T{11 + index:02d}:00:00+00:00",
                        "status": {"short": "NS"},
                    },
                    "league": {"id": 1, "name": "World Cup", "round": "Group K"},
                    "teams": {
                        "home": {"id": 100 + index, "name": f"Team H {index}"},
                        "away": {"id": 200 + index, "name": f"Team A {index}"},
                    },
                }
                for index in range(9)
            ]
        }


def test_future_fixture_refresh_writes_idempotent_read_model(tmp_path: Path) -> None:
    client = FakeApiFootballClient()
    config = FutureRefreshConfig(runtime_root=tmp_path, quota_reserve=1500, persistence="file")
    service = FutureFixtureRefreshService(
        client=client,
        config=config,
        now=NOW,
        sleep=lambda _: None,
    )

    first = service.run()
    second = FutureFixtureRefreshService(
        client=client,
        config=config,
        now=NOW,
        sleep=lambda _: None,
    ).run()

    assert first.fixture_count == 1
    assert first.mapping_count == 1
    assert first.market_snapshot_count == 1
    assert second.fixture_count == 1
    assert (tmp_path / "read_model/fixtures.json").is_file()
    assert (tmp_path / "read_model/provider_mappings.json").is_file()
    assert (tmp_path / "read_model/market_snapshots.json").is_file()
    assert len(list((tmp_path / "raw").glob("fixtures_*.json"))) == 1
    assert len(list((tmp_path / "raw").glob("odds_*.json"))) == 1
    assert first.ledger_appended_count == 3
    assert second.ledger_appended_count == 0
    ledger_lines = (tmp_path / "ledger/market_observations.jsonl").read_text().splitlines()
    assert len(ledger_lines) == 3


def test_future_refresh_saves_lineups_raw_before_materialization_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def fail_projection(**_kwargs: Any) -> list[dict[str, Any]]:
        raise RuntimeError("materialization exploded")

    monkeypatch.setenv("W2_PROVIDER_ENDPOINT_ALLOWLIST", "status,fixtures,odds,lineups")
    monkeypatch.setattr(
        "w2.ingestion.future_refresh.project_ledger_to_read_model",
        fail_projection,
    )
    client = FakeApiFootballClient()
    config = FutureRefreshConfig(
        runtime_root=tmp_path,
        persistence="file",
        feature_enrichment_enabled=True,
        feature_enrichment_endpoints=("lineups",),
        feature_enrichment_request_budget=1,
    )

    result = FutureFixtureRefreshService(
        client=client,
        config=config,
        now=NOW,
        sleep=lambda _: None,
    ).run()
    audit = json.loads((tmp_path / "future_refresh_audit.json").read_text(encoding="utf-8"))

    assert result.status == "PARTIAL_FAILED"
    assert result.error_code == "RuntimeError"
    assert list((tmp_path / "raw").glob("lineups_1489404_*.json"))
    assert audit["status"] == "PARTIAL_FAILED"
    assert audit["error_code"] == "RuntimeError"
    assert audit["raw_payload_written_count"] >= 3
    assert any(
        item["endpoint"] == "lineups" and item["raw_payload_persisted"] is True
        for item in audit["requests"]
    )


def test_future_refresh_lineups_empty_diagnostic(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("W2_PROVIDER_ENDPOINT_ALLOWLIST", "status,fixtures,odds,lineups")
    client = EmptyLineupsClient()
    config = FutureRefreshConfig(
        runtime_root=tmp_path,
        persistence="file",
        feature_enrichment_enabled=True,
        feature_enrichment_endpoints=("lineups",),
        feature_enrichment_request_budget=1,
    )

    result = FutureFixtureRefreshService(
        client=client,
        config=config,
        now=NOW,
        sleep=lambda _: None,
    ).run()
    audit = json.loads((tmp_path / "future_refresh_audit.json").read_text(encoding="utf-8"))

    assert result.blockers == []
    assert any(
        item["endpoint"] == "lineups"
        and item["response_count"] == 0
        and item["diagnostic_code"] == "PROVIDER_LINEUPS_EMPTY"
        for item in audit["requests"]
    )


def test_future_refresh_lineups_materialization_missing_diagnostic(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("W2_PROVIDER_ENDPOINT_ALLOWLIST", "status,fixtures,odds,lineups")
    client = FakeApiFootballClient()
    config = FutureRefreshConfig(
        runtime_root=tmp_path,
        persistence="file",
        feature_enrichment_enabled=True,
        feature_enrichment_endpoints=("lineups",),
        feature_enrichment_request_budget=1,
    )

    result = FutureFixtureRefreshService(
        client=client,
        config=config,
        now=NOW,
        sleep=lambda _: None,
    ).run()
    audit = json.loads((tmp_path / "future_refresh_audit.json").read_text(encoding="utf-8"))

    assert result.blockers == []
    assert any(
        item["endpoint"] == "lineups"
        and item["response_count"] > 0
        and item["diagnostic_code"] == "LINEUPS_MATERIALIZATION_MISSING"
        for item in audit["requests"]
    )


def test_future_refresh_batches_lineups_without_disallowed_endpoints(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("W2_PROVIDER_ENDPOINT_ALLOWLIST", "status,fixtures,odds,lineups")
    monkeypatch.setenv("W2_PROVIDER_REFRESH_BATCH_SIZE", "3")
    client = NineFutureFixturesClient()
    config = FutureRefreshConfig(
        runtime_root=tmp_path,
        persistence="file",
        max_fixture_candidates=9,
        max_odds_requests=0,
        request_budget=20,
        feature_enrichment_enabled=True,
        feature_enrichment_endpoints=("lineups", "statistics", "injuries"),
        feature_enrichment_request_budget=9,
        provider_refresh_batch_size=3,
    )

    result = FutureFixtureRefreshService(
        client=client,
        config=config,
        now=NOW,
        sleep=lambda _: None,
    ).run()
    audit = json.loads((tmp_path / "future_refresh_audit.json").read_text(encoding="utf-8"))

    endpoints = [endpoint for endpoint, _params in client.calls]
    assert endpoints.count("lineups") == 9
    assert "statistics" not in endpoints
    assert "injuries" not in endpoints
    assert "h2h" not in endpoints
    assert result.feature_enrichment_payload_count == 9
    assert audit["feature_enrichment_batch_count"] == 3
    assert len(list((tmp_path / "raw").glob("lineups_*.json"))) == 9


def test_future_fixture_refresh_preserves_core_tasks_when_reserve_locked(
    tmp_path: Path,
) -> None:
    client = FakeApiFootballClient(remaining=1499)
    config = FutureRefreshConfig(
        runtime_root=tmp_path,
        quota_reserve=1500,
        persistence="file",
        feature_enrichment_enabled=True,
        feature_enrichment_request_budget=3,
        feature_enrichment_endpoints=("statistics", "lineups", "injuries"),
    )
    result = FutureFixtureRefreshService(
        client=client,
        config=config,
        now=NOW,
        sleep=lambda _: None,
    ).run()

    assert result.blockers == []
    assert result.fixture_count == 1
    assert result.market_snapshot_count == 1
    assert ("odds", {"fixture": "1489404"}) in client.calls
    assert ("lineups", {"fixture": "1489404"}) in client.calls
    assert all(endpoint != "statistics" for endpoint, _ in client.calls)
    assert all(endpoint != "injuries" for endpoint, _ in client.calls)
    assert (tmp_path / "future_refresh_audit.json").is_file()


def test_future_refresh_requests_odds_for_all_fixture_candidates(tmp_path: Path) -> None:
    client = ManyFutureFixturesClient()
    config = FutureRefreshConfig(
        runtime_root=tmp_path,
        max_fixture_candidates=12,
        max_odds_requests=12,
        request_budget=30,
        persistence="file",
    )

    result = FutureFixtureRefreshService(
        client=client,
        config=config,
        now=NOW,
        sleep=lambda _: None,
    ).run()
    audit = json.loads((tmp_path / "future_refresh_audit.json").read_text(encoding="utf-8"))
    odds_calls = [params["fixture"] for endpoint, params in client.calls if endpoint == "odds"]

    assert result.fixture_count == 12
    assert odds_calls == [str(1489400 + index) for index in range(12)]
    assert audit["odds_request_fixture_ids"] == odds_calls
    assert audit["odds_request_attempt_count"] == 12
    assert audit["odds_request_limit"] == 12
    assert audit["odds_request_coverage_ratio"] == 1.0


def test_future_refresh_daily_quota_is_not_burst_quota(tmp_path: Path) -> None:
    client = FakeApiFootballClient(remaining=6774, burst_remaining=299)
    config = FutureRefreshConfig(runtime_root=tmp_path, quota_reserve=1500, persistence="file")

    result = FutureFixtureRefreshService(
        client=client,
        config=config,
        now=NOW,
        sleep=lambda _: None,
    ).run()

    assert result.blockers == []
    assert result.remaining_quota == 6774


def test_future_refresh_burst_only_is_daily_unknown(tmp_path: Path) -> None:
    client = FakeApiFootballClient(
        remaining=299,
        daily_header="x-ratelimit-remaining",
        include_status_daily_payload=False,
    )
    config = FutureRefreshConfig(runtime_root=tmp_path, quota_reserve=1500, persistence="file")

    result = FutureFixtureRefreshService(
        client=client,
        config=config,
        now=NOW,
        sleep=lambda _: None,
    ).run()

    assert result.blockers == ["DAILY_QUOTA_UNKNOWN"]


def test_future_refresh_uses_persisted_quota_when_response_omits_daily_quota(
    tmp_path: Path,
) -> None:
    client = FakeApiFootballClient(
        remaining=299,
        daily_header="x-ratelimit-remaining",
        include_status_daily_payload=False,
    )
    service = FutureFixtureRefreshService(
        client=client,
        config=FutureRefreshConfig(runtime_root=tmp_path, quota_reserve=20, persistence="file"),
        now=NOW,
        sleep=lambda _: None,
    )
    service._latest_remaining = 95

    result = service.run()

    assert result.blockers == []
    assert result.remaining_quota == 92


def test_future_refresh_loads_strictest_persisted_quota(monkeypatch: Any, tmp_path: Path) -> None:
    class Repository:
        @staticmethod
        def provider_quota_snapshot(_day_start: datetime) -> dict[str, int | None]:
            return {"daily_limit": 100, "used": 5, "remaining": 95}

    service = FutureFixtureRefreshService(
        client=FakeApiFootballClient(),
        config=FutureRefreshConfig(runtime_root=tmp_path, persistence="db"),
        now=NOW,
    )
    monkeypatch.setattr(service, "_db_repository", Repository)

    service._load_persisted_provider_remaining()

    assert service._latest_remaining == 95


def test_future_refresh_uses_provider_quota_as_daily_usage_authority(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    class Repository:
        @staticmethod
        def request_count_since(
            _day_start: datetime,
            *,
            include_quota_usage: bool = True,
        ) -> int:
            assert include_quota_usage is True
            return 10

    service = FutureFixtureRefreshService(
        client=FakeApiFootballClient(),
        config=FutureRefreshConfig(
            runtime_root=tmp_path,
            persistence="db",
            daily_usage_scope="w2_ledger",
        ),
        now=NOW,
    )
    monkeypatch.setattr(service, "_db_repository", Repository)

    assert service._actual_provider_calls_today() == 10


def test_future_refresh_surfaces_quota_usage_ledger_divergence(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("W2_PROVIDER_HTTP_MAX_ATTEMPTS", "1")

    class Repository:
        @staticmethod
        def fixture_payloads() -> list[dict[str, Any]]:
            return []

        @staticmethod
        def request_count_evidence_since(
            _day_start: datetime,
            *,
            include_quota_usage: bool = True,
            as_of: datetime | None = None,
        ) -> dict[str, int | bool]:
            assert include_quota_usage is True
            assert as_of == NOW
            return {
                "known_count": 10,
                "quota_usage_count": 10,
                "run_audit_count": 135,
                "provider_ledger_count": 135,
                "billable_from_provider": 10,
                "local_ledger_count": 135,
                "last_authority_at": NOW.isoformat(),
                "authority_age_seconds": 0,
                "dispatched_count": 135,
                "dispatched_since_authority_count": 0,
                "attempt_count": 135,
                "quota_authority_status": "AUTHORITATIVE",
                "quota_authority_degraded": False,
                "quota_degradation_classification": None,
                "quota_usage_ledger_delta": 125,
                "quota_usage_ledger_divergence": True,
            }

        @staticmethod
        def successful_request_count_since(_day_start: datetime) -> int:
            return 135

        @staticmethod
        def postmatch_result_request_count_since(_day_start: datetime) -> int:
            return 10

        @staticmethod
        def postmatch_result_successful_request_count_since(_day_start: datetime) -> int:
            return 10

        @staticmethod
        def unsettled_model_forecast_postmatch_count(**_kwargs: Any) -> int:
            return 2

    service = FutureFixtureRefreshService(
        client=FakeApiFootballClient(),
        config=FutureRefreshConfig(
            runtime_root=tmp_path,
            persistence="db",
            daily_hard_cap=70,
            daily_reserve=0,
        ),
        now=NOW,
    )
    monkeypatch.setattr(service, "_db_repository", Repository)

    decision = service._provider_hard_cap_preflight()

    assert decision["allowed"] is True
    assert decision["operational_status"] == "QUOTA_USAGE_LEDGER_DIVERGENCE"
    assert decision["actual_calls_today"] == 10
    assert decision["quota_usage_ledger_delta"] == 125

    postmatch_service = FutureFixtureRefreshService(
        client=FakeApiFootballClient(),
        config=FutureRefreshConfig(
            runtime_root=tmp_path,
            persistence="db",
            checkpoint_fixture_ids=("1494241",),
            refresh_checkpoints=(
                {
                    "checkpoint": "POSTMATCH_RESULT",
                    "endpoints": ["status", "fixtures"],
                },
            ),
        ),
        now=NOW,
    )
    monkeypatch.setattr(postmatch_service, "_db_repository", Repository)

    postmatch_decision = postmatch_service._provider_hard_cap_preflight()

    assert postmatch_decision["planned_calls"] == 3, postmatch_decision
    assert postmatch_decision["reserved_capture_calls"] == 6, postmatch_decision
    assert postmatch_decision["allowed"] is True, postmatch_decision
    assert postmatch_decision["actual_calls_today"] == 10
    assert postmatch_decision["operational_status"] == "QUOTA_USAGE_LEDGER_DIVERGENCE"


def test_future_refresh_classifies_stale_quota_authority_as_expected_degraded(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("W2_PROVIDER_HTTP_MAX_ATTEMPTS", "1")

    class Repository:
        @staticmethod
        def fixture_payloads() -> list[dict[str, Any]]:
            return []

        @staticmethod
        def request_count_evidence_since(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
            return {
                "known_count": 12,
                "quota_usage_count": 10,
                "run_audit_count": 135,
                "provider_ledger_count": 135,
                "billable_from_provider": 10,
                "local_ledger_count": 135,
                "last_authority_at": "2026-06-23T07:00:00Z",
                "authority_age_seconds": 10800,
                "dispatched_count": 135,
                "dispatched_since_authority_count": 2,
                "attempt_count": 135,
                "quota_authority_status": "DEGRADED",
                "quota_authority_degraded": True,
                "quota_degradation_classification": "EXPECTED_DEGRADED",
                "quota_usage_ledger_delta": 125,
                "quota_usage_ledger_divergence": True,
            }

        @staticmethod
        def successful_request_count_since(_day_start: datetime) -> int:
            return 135

    service = FutureFixtureRefreshService(
        client=FakeApiFootballClient(),
        config=FutureRefreshConfig(
            runtime_root=tmp_path,
            persistence="db",
            daily_hard_cap=70,
            daily_reserve=0,
        ),
        now=NOW,
    )
    monkeypatch.setattr(service, "_db_repository", Repository)

    decision = service._provider_hard_cap_preflight()

    assert decision["actual_calls_today"] == 12
    assert decision["operational_statuses"] == [
        "QUOTA_AUTHORITY_DEGRADED",
        "EXPECTED_DEGRADED",
        "QUOTA_USAGE_LEDGER_DIVERGENCE",
    ]


def test_future_refresh_blocks_when_header_remaining_below_preflight_minimum(
    tmp_path: Path,
) -> None:
    client = FakeApiFootballClient(remaining=49)
    config = FutureRefreshConfig(runtime_root=tmp_path, quota_reserve=20, persistence="file")

    result = FutureFixtureRefreshService(
        client=client,
        config=config,
        now=NOW,
        sleep=lambda _: None,
    ).run()
    audit = json.loads((tmp_path / "future_refresh_audit.json").read_text(encoding="utf-8"))

    assert result.blockers == ["PROVIDER_HEADER_REMAINING_BELOW_MINIMUM"]
    assert client.calls == [("status", {})]
    assert audit["request_count"] == 1
    assert audit["requests"][0]["daily_remaining"] == 49
    assert audit["requests"][0]["daily_limit"] is None


def test_future_fixture_refresh_request_budget(tmp_path: Path) -> None:
    client = FakeApiFootballClient()
    config = FutureRefreshConfig(runtime_root=tmp_path, request_budget=1, persistence="file")
    result = FutureFixtureRefreshService(
        client=client,
        config=config,
        now=NOW,
        sleep=lambda _: None,
    ).run()

    assert result.blockers == ["REQUEST_BUDGET_EXHAUSTED"]
    assert len(client.calls) == 1


def test_provider_ingress_defaults_to_fail_closed(tmp_path: Path) -> None:
    service = FutureFixtureRefreshService(
        config=FutureRefreshConfig(runtime_root=tmp_path, persistence="file"),
        now=NOW,
    )
    assert service.client.allow_live is False


def test_gate_a_uncertain_delivery_reserves_once_and_never_retries(tmp_path: Path) -> None:
    client = _FailingProvider()
    reservation = _CallReservation()
    result = FutureFixtureRefreshService(
        client=client,
        config=FutureRefreshConfig(runtime_root=tmp_path, persistence="file"),
        now=NOW,
        sleep=lambda _: None,
        runtime_authorization=_gate_a_authorization(),
        provider_call_reservation=reservation,  # type: ignore[arg-type]
    ).run()

    assert result.status == "BLOCKED"
    assert result.blockers == ["PROVIDER_DELIVERY_UNCERTAIN:TimeoutError"]
    assert client.calls == 1
    assert reservation.endpoints == ["status"]
    assert reservation.outcomes == [(1, "DELIVERY_UNCERTAIN", "TimeoutError")]


def test_gate_a_http_failure_is_not_automatically_retried(tmp_path: Path) -> None:
    client = FakeApiFootballClient(status_code=429)
    reservation = _CallReservation()
    result = FutureFixtureRefreshService(
        client=client,
        config=FutureRefreshConfig(runtime_root=tmp_path, persistence="file"),
        now=NOW,
        sleep=lambda _: None,
        runtime_authorization=_gate_a_authorization(),
        provider_call_reservation=reservation,  # type: ignore[arg-type]
    ).run()

    assert result.status == "BLOCKED"
    assert result.blockers == ["PROVIDER_MINUTE_RATE_LIMIT_EXCEEDED"]
    assert client.calls == [("status", {})]
    assert reservation.endpoints == ["status"]
    assert reservation.outcomes == [(1, "RESPONSE_RECEIVED", None)]


def test_gate_a_task_persists_blocked_terminal_state_and_finalizes_reservation(
    tmp_path: Path,
) -> None:
    reservation = _CallReservation()
    audit = run_future_refresh_task(
        task_id="gate-a-task",
        key="gate-a-key",
        owner="foreground-owner",
        competition_id="world_cup_2026",
        runtime_root=tmp_path,
        client=_FailingProvider(),
        now=NOW,
        persistence="file",
        runtime_authorization=_gate_a_authorization(),
        provider_call_reservation=reservation,  # type: ignore[arg-type]
    )

    assert audit.status == "BLOCKED"
    assert audit.result["blockers"] == ["PROVIDER_DELIVERY_UNCERTAIN:TimeoutError"]
    assert reservation.endpoints == ["status"]
    assert reservation.final_statuses == ["BLOCKED"]


def test_gate_a_schema_drift_fails_closed_after_evidence_capture(tmp_path: Path) -> None:
    reservation = _CallReservation()
    result = FutureFixtureRefreshService(
        client=_SchemaDriftProvider(),
        config=FutureRefreshConfig(runtime_root=tmp_path, persistence="file"),
        now=NOW,
        runtime_authorization=_gate_a_authorization(),
        provider_call_reservation=reservation,  # type: ignore[arg-type]
    ).run()

    assert result.status == "BLOCKED"
    assert result.blockers == ["PROVIDER_FIXTURES_SCHEMA_DRIFT"]
    assert result.raw_payload_written_count == 2
    assert reservation.endpoints == ["status", "fixtures"]


def test_provider_errors_precede_missing_quota(tmp_path: Path) -> None:
    result = FutureFixtureRefreshService(
        client=_ProviderErrorsWithoutQuota(),
        config=FutureRefreshConfig(runtime_root=tmp_path, persistence="file"),
        now=NOW,
    ).run()

    assert result.blockers == ["PROVIDER_STATUS_ERRORS"]


def test_gate_a_abnormal_empty_fails_closed(tmp_path: Path) -> None:
    reservation = _CallReservation()
    result = FutureFixtureRefreshService(
        client=_EmptyFixturesProvider(),
        config=FutureRefreshConfig(runtime_root=tmp_path, persistence="file"),
        now=NOW,
        runtime_authorization=_gate_a_authorization(),
        provider_call_reservation=reservation,  # type: ignore[arg-type]
    ).run()

    assert result.status == "BLOCKED"
    assert result.blockers == ["PROVIDER_FIXTURES_EMPTY"]
    assert result.raw_payload_written_count == 2


def test_future_refresh_controlled_feature_enrichment_uses_budget_and_audit(
    tmp_path: Path,
) -> None:
    client = FakeApiFootballClient()
    config = FutureRefreshConfig(
        runtime_root=tmp_path,
        quota_reserve=1500,
        persistence="file",
        feature_enrichment_enabled=True,
        feature_enrichment_endpoints=("statistics", "lineups", "injuries"),
        feature_enrichment_request_budget=2,
    )

    result = FutureFixtureRefreshService(
        client=client,
        config=config,
        now=NOW,
        sleep=lambda _: None,
    ).run()
    audit = (tmp_path / "future_refresh_audit.json").read_text(encoding="utf-8")

    assert result.blockers == []
    assert result.feature_enrichment_payload_count == 1
    assert ("statistics", {"fixture": "1489404"}) not in client.calls
    assert ("lineups", {"fixture": "1489404"}) in client.calls
    assert ("injuries", {"fixture": "1489404"}) not in client.calls
    assert list((tmp_path / "raw").glob("lineups_*.json"))
    assert "STATISTICS_NOT_POSTMATCH" in audit
    assert "ENDPOINT_NOT_AUTHORIZED:injuries" in audit
    assert '"candidate": false' in audit
    assert '"formal_recommendation": false' in audit


def test_future_refresh_endpoint_allowlist_skips_unauthorized_enrichment(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("W2_PROVIDER_ENDPOINT_ALLOWLIST", "status,fixtures,odds,lineups")
    client = FakeApiFootballClient()
    config = FutureRefreshConfig(
        runtime_root=tmp_path,
        quota_reserve=1500,
        persistence="file",
        feature_enrichment_enabled=True,
        feature_enrichment_endpoints=("statistics", "lineups", "injuries"),
        feature_enrichment_request_budget=3,
    )

    result = FutureFixtureRefreshService(
        client=client,
        config=config,
        now=NOW,
        sleep=lambda _: None,
    ).run()
    audit = json.loads((tmp_path / "future_refresh_audit.json").read_text(encoding="utf-8"))

    assert result.blockers == []
    assert result.request_count == 4
    assert [endpoint for endpoint, _params in client.calls] == [
        "status",
        "fixtures",
        "odds",
        "lineups",
    ]
    assert result.feature_enrichment_payload_count == 1
    assert any(
        item["error_code"] == "ENDPOINT_NOT_AUTHORIZED:statistics" for item in audit["requests"]
    )
    assert any(
        item["error_code"] == "ENDPOINT_NOT_AUTHORIZED:injuries" for item in audit["requests"]
    )


def test_future_refresh_skips_optional_enrichment_at_request_budget(tmp_path: Path) -> None:
    client = FakeApiFootballClient()
    config = FutureRefreshConfig(
        runtime_root=tmp_path,
        persistence="file",
        request_budget=3,
        max_odds_requests=1,
        feature_enrichment_enabled=True,
        feature_enrichment_endpoints=("lineups",),
        feature_enrichment_request_budget=1,
    )

    result = FutureFixtureRefreshService(
        client=client,
        config=config,
        now=NOW,
        sleep=lambda _: None,
    ).run()
    audit = json.loads((tmp_path / "future_refresh_audit.json").read_text(encoding="utf-8"))

    assert result.blockers == []
    assert result.request_count == 3
    assert [endpoint for endpoint, _params in client.calls] == ["status", "fixtures", "odds"]
    assert result.feature_enrichment_payload_count == 0
    assert audit["requests"][-1]["error_code"] == ("FEATURE_ENRICHMENT_SKIPPED_REQUEST_BUDGET")


def test_future_refresh_tick_hard_cap_blocks_before_provider_call(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("W2_PROVIDER_HTTP_MAX_ATTEMPTS", "3")
    client = FakeApiFootballClient()
    config = FutureRefreshConfig(
        runtime_root=tmp_path,
        persistence="file",
        max_fixture_candidates=31,
        max_odds_requests=31,
        request_budget=40,
    )

    result = FutureFixtureRefreshService(
        client=client,
        config=config,
        now=NOW,
        sleep=lambda _: None,
    ).run()
    audit = json.loads((tmp_path / "future_refresh_audit.json").read_text(encoding="utf-8"))

    assert result.status == "BLOCKED"
    assert result.blockers == ["PROVIDER_REFRESH_BUDGET_TOO_HIGH"]
    assert result.request_count == 0
    assert client.calls == []
    assert audit["request_count"] == 0
    assert audit["requests"][0]["projected_calls"] == 99


def test_postmatch_minute_preflight_uses_recent_local_attempts(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("W2_PROVIDER_HTTP_MAX_ATTEMPTS", "1")
    monkeypatch.setenv("W2_PROVIDER_ENDPOINT_ALLOWLIST", "status,fixtures")

    class Repository:
        @staticmethod
        def provider_request_count_since(_since: datetime) -> int:
            return 9

    service = FutureFixtureRefreshService(
        client=FakeApiFootballClient(),
        config=FutureRefreshConfig(
            runtime_root=tmp_path,
            persistence="db",
            checkpoint_fixture_ids=("1494241",),
            refresh_checkpoints=(
                {
                    "checkpoint": "POSTMATCH_RESULT",
                    "endpoints": ["status", "fixtures"],
                },
            ),
        ),
        now=NOW,
    )
    monkeypatch.setattr(service, "_db_repository", Repository)

    decision = service._provider_tick_hard_cap_preflight()

    assert decision["allowed"] is False
    assert decision["blocker"] == "PROVIDER_MINUTE_RATE_LIMIT_PROTECTED"
    assert decision["minute_limit"] == 10
    assert decision["minute_calls_observed"] == 9
    assert decision["projected_calls"] == 2


def test_future_refresh_projected_calls_ignore_disallowed_enrichment(tmp_path: Path) -> None:
    client = ManyFutureFixturesClient()
    config = FutureRefreshConfig(
        runtime_root=tmp_path,
        persistence="file",
        max_fixture_candidates=5,
        max_odds_requests=5,
        request_budget=30,
        feature_enrichment_enabled=True,
        feature_enrichment_endpoints=("statistics", "lineups", "injuries"),
        feature_enrichment_request_budget=15,
    )

    result = FutureFixtureRefreshService(
        client=client,
        config=config,
        now=NOW,
        sleep=lambda _: None,
    ).run()

    assert result.blockers == []
    assert result.request_count == 12
    assert result.feature_enrichment_payload_count == 5
    assert all(endpoint != "statistics" for endpoint, _params in client.calls)
    assert all(endpoint != "injuries" for endpoint, _params in client.calls)
    assert len([endpoint for endpoint, _params in client.calls if endpoint == "lineups"]) == 5


def test_future_refresh_records_401_without_retry(tmp_path: Path) -> None:
    client = FakeApiFootballClient(status_code=401)
    config = FutureRefreshConfig(runtime_root=tmp_path, persistence="file")
    result = FutureFixtureRefreshService(
        client=client,
        config=config,
        now=NOW,
        sleep=lambda _: None,
    ).run()
    audit = (tmp_path / "future_refresh_audit.json").read_text(encoding="utf-8")

    assert result.blockers == ["PROVIDER_HTTP_401"]
    assert len(client.calls) == 1
    assert "PROVIDER_HTTP_401" in audit


def test_future_refresh_records_429_without_tight_retry(tmp_path: Path) -> None:
    client = FakeApiFootballClient(status_code=429)
    config = FutureRefreshConfig(runtime_root=tmp_path, persistence="file")
    result = FutureFixtureRefreshService(
        client=client,
        config=config,
        now=NOW,
        sleep=lambda _: None,
    ).run()
    audit = (tmp_path / "future_refresh_audit.json").read_text(encoding="utf-8")

    assert result.blockers == ["PROVIDER_MINUTE_RATE_LIMIT_EXCEEDED"]
    assert len(client.calls) == 1
    assert "PROVIDER_MINUTE_RATE_LIMIT_EXCEEDED" in audit


def test_future_refresh_caps_configured_provider_retries(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("W2_PROVIDER_HTTP_MAX_ATTEMPTS", "999")
    monkeypatch.setenv("W2_PROVIDER_REFRESH_TICK_HARD_CAP", "100")
    client = FakeApiFootballClient(status_code=429)
    result = FutureFixtureRefreshService(
        client=client,
        config=FutureRefreshConfig(runtime_root=tmp_path, persistence="file"),
        now=NOW,
        sleep=lambda _: None,
    ).run()

    assert result.blockers == ["PROVIDER_MINUTE_RATE_LIMIT_EXCEEDED"]
    assert result.request_count == 3
    assert len(client.calls) == 3


def test_future_refresh_daily_hard_cap_blocks_before_provider_call(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("W2_PROVIDER_REFRESH_TICK_HARD_CAP", "100")
    client = FakeApiFootballClient()
    config = FutureRefreshConfig(
        runtime_root=tmp_path,
        persistence="file",
        daily_hard_cap=7500,
        daily_reserve=1500,
        actual_provider_calls_today=6000,
        max_odds_requests=20,
        feature_enrichment_enabled=True,
        feature_enrichment_request_budget=9,
    )
    result = FutureFixtureRefreshService(
        client=client,
        config=config,
        now=NOW,
        sleep=lambda _: None,
    ).run()
    audit = json.loads((tmp_path / "future_refresh_audit.json").read_text(encoding="utf-8"))

    assert result.status == "BLOCKED"
    assert result.blockers == ["PROVIDER_RESERVE_PROTECTED"]
    assert result.request_count == 0
    assert client.calls == []
    assert audit["request_count"] == 0
    assert audit["requests"][0]["error_code"] == "PROVIDER_RESERVE_PROTECTED"


def test_future_refresh_w2_budget_scope_ignores_provider_header_usage(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("W2_PROVIDER_REFRESH_TICK_HARD_CAP", "100")
    client = FakeApiFootballClient()
    config = FutureRefreshConfig(
        runtime_root=tmp_path,
        persistence="file",
        daily_hard_cap=100,
        daily_reserve=20,
        daily_usage_scope="w2_ledger",
        actual_provider_calls_today=70,
        max_odds_requests=5,
        feature_enrichment_enabled=True,
        feature_enrichment_request_budget=3,
    )
    result = FutureFixtureRefreshService(
        client=client,
        config=config,
        now=NOW,
        sleep=lambda _: None,
    ).run()

    assert result.status != "BLOCKED"
    assert "PROVIDER_RESERVE_PROTECTED" not in result.blockers


def test_future_refresh_policy_allows_only_registered_competitions(tmp_path: Path) -> None:
    policy = load_refresh_policy(competition_id="world_cup_2026")
    config = config_from_policy(
        competition_id="world_cup_2026",
        runtime_root=tmp_path / "runtime",
    )

    assert policy.provider_league_id == "1"
    assert config.season == "2026"
    assert config.max_odds_requests == 20
    try:
        load_refresh_policy(competition_id="premier_league")
    except FutureRefreshError as exc:
        assert str(exc) == "COMPETITION_NOT_ENABLED:premier_league"
    else:  # pragma: no cover
        raise AssertionError("unregistered policy unexpectedly loaded")


def test_future_refresh_binds_source_revision_to_staging_git_sha(monkeypatch) -> None:
    monkeypatch.setenv("W2_ENVIRONMENT", "staging")
    monkeypatch.setenv("W2_GIT_SHA", "a" * 40)

    config = config_from_policy(competition_id="world_cup_2026")

    assert config.source_revision == "a" * 40


def test_future_refresh_staging_requires_exact_source_revision(monkeypatch) -> None:
    monkeypatch.setenv("W2_ENVIRONMENT", "staging")
    monkeypatch.setenv("W2_GIT_SHA", "UNKNOWN")

    try:
        config_from_policy(competition_id="world_cup_2026")
    except FutureRefreshError as exc:
        assert str(exc) == "SOURCE_REVISION_NOT_BOUND_TO_EXACT_GIT_SHA"
    else:  # pragma: no cover
        raise AssertionError("staging refresh must fail closed without exact source revision")


def test_world_cup_future_refresh_policy_uses_zero_trickle_backfill_budget() -> None:
    config = config_from_policy(competition_id="world_cup_2026")

    assert config.daily_hard_cap == 7500
    assert config.daily_unallocated_buffer == 0
    assert config.daily_reserve == 1500
    assert config.request_budget == 30
    assert config.checkpoint_mode == "matchday_checkpoint_plan"
    assert config.trickle_backfill_daily_budget == 120


def test_future_refresh_rejects_registered_budget_above_observed_plan_limit(
    monkeypatch,
) -> None:
    monkeypatch.setenv("W2_PROVIDER_DAILY_HARD_CAP", "7501")

    try:
        config_from_policy(competition_id="world_cup_2026")
    except FutureRefreshError as exc:
        assert str(exc) == "PROVIDER_DAILY_BUDGET_EXCEEDS_OBSERVED_PLAN_LIMIT"
    else:  # pragma: no cover
        raise AssertionError("registered budget above the observed plan limit must fail closed")


def test_future_refresh_accepts_header_bound_pro_budget(monkeypatch) -> None:
    monkeypatch.setenv("W2_PROVIDER_DAILY_HARD_CAP", "7500")
    monkeypatch.setenv("W2_PROVIDER_DAILY_UNALLOCATED_BUFFER", "0")
    monkeypatch.setenv("W2_PROVIDER_DAILY_RESERVE", "1500")
    monkeypatch.setenv("W2_PROVIDER_OBSERVED_DAILY_LIMIT", "7500")
    monkeypatch.setenv("W2_PROVIDER_OBSERVED_DAILY_LIMIT_AT", "2026-08-16T16:47:41Z")

    config = config_from_policy(competition_id="world_cup_2026")

    assert config.daily_hard_cap == 7500
    assert config.daily_reserve == 1500
    assert config.quota_reserve == 1500


def test_future_refresh_rejects_unattributed_non_free_limit(monkeypatch) -> None:
    monkeypatch.setenv("W2_PROVIDER_OBSERVED_DAILY_LIMIT", "7500")
    monkeypatch.delenv("W2_PROVIDER_OBSERVED_DAILY_LIMIT_AT", raising=False)

    with pytest.raises(FutureRefreshError, match="PROVIDER_PLAN_LIMIT_AUTHORITY_MISSING"):
        config_from_policy(competition_id="world_cup_2026")


def test_future_refresh_file_lock_prevents_duplicate_owner(tmp_path: Path) -> None:
    first = RefreshSingletonLock(
        key="future-refresh:world_cup_2026:2026:bucket",
        owner="owner-a",
        runtime_root=tmp_path,
        ttl_seconds=60,
    )
    second = RefreshSingletonLock(
        key="future-refresh:world_cup_2026:2026:bucket",
        owner="owner-b",
        runtime_root=tmp_path,
        ttl_seconds=60,
    )

    assert first.acquire(now=NOW)
    assert not second.acquire(now=NOW)
    assert first.release()


def test_future_refresh_task_writes_audit_and_blocks_duplicate_bucket(tmp_path: Path) -> None:
    key = deterministic_task_key(
        competition_id="world_cup_2026",
        season="2026",
        now=NOW,
        interval_seconds=900,
    )
    existing = RefreshSingletonLock(
        key=key,
        owner="existing",
        runtime_root=tmp_path,
        ttl_seconds=60,
    )
    assert existing.acquire(now=NOW)

    audit = run_future_refresh_task(
        task_id="task-1",
        key=key,
        owner="new-owner",
        queued_at=NOW,
        runtime_root=tmp_path,
        client=FakeApiFootballClient(),
        now=NOW,
        persistence="file",
    )

    assert audit.status == "ALREADY_RUNNING"
    assert (tmp_path / "task_audit/task-1.json").is_file()
    assert existing.release()


@pytest.mark.parametrize("endpoints", [["odds"], [], ["statistics"]])
def test_file_checkpoint_execution_is_rejected_before_provider_calls(
    tmp_path: Path, endpoints: list[str]
) -> None:
    client = FakeApiFootballClient()
    checkpoint = {
        "fixture_id": "1489404",
        "checkpoint": "T1_LINEUPS",
        "kickoff_utc": "2026-06-23T17:00:00Z",
        "due_at": "2026-06-23T16:00:00Z",
        "endpoints": endpoints,
        "source": "scheduled",
    }

    audit = run_future_refresh_task(
        task_id="task-materialize",
        key="checkpoint-refresh:test:materialize",
        queued_at=NOW,
        runtime_root=tmp_path,
        client=client,
        now=NOW,
        persistence="file",
        checkpoint_fixture_ids=("1489404",),
        refresh_checkpoints=(checkpoint,),
    )

    assert audit.status == "BLOCKED"
    assert audit.result["blockers"] == ["CHECKPOINT_ENDPOINT_SET_INVALID"]
    assert client.calls == []


def test_raw_lineup_persistence_defers_materialization_until_fixture_identity_exists(
    monkeypatch,
    tmp_path: Path,
) -> None:
    class Repository:
        materialization_called = False

        def save_raw_payload(self, **_kwargs: Any) -> bool:
            return True

        def save_lineup_snapshots(self, **_kwargs: Any) -> int:
            self.materialization_called = True
            raise AssertionError("lineup materialization must be deferred")

    repository = Repository()
    service = FutureFixtureRefreshService(
        client=FakeApiFootballClient(),
        config=FutureRefreshConfig(
            runtime_root=tmp_path,
            persistence="db",
        ),
        now=NOW,
    )
    monkeypatch.setattr(service, "_db_repository", lambda: repository)
    response = LiveApiFootballResponse(
        endpoint="lineups",
        params={"fixture": "1489404"},
        status_code=200,
        elapsed_ms=1,
        payload={"response": []},
        headers={},
        captured_at=NOW,
    )

    assert service._save_raw_payload_first(
        endpoint="lineups",
        params={"fixture": "1489404"},
        response=response,
        payload_hash="a" * 64,
        payload={"response": []},
    ) == (True, None)
    assert repository.materialization_called is False
    assert service._projection_events == {}


def test_fixture_discovery_raw_is_classified_live_at_write_time(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, Any] = {}

    class Repository:
        def save_raw_payload(self, **kwargs: Any) -> str:
            captured.update(kwargs)
            return "db://raw_payload/hash"

    service = FutureFixtureRefreshService(
        client=FakeApiFootballClient(),
        config=FutureRefreshConfig(
            runtime_root=tmp_path,
            persistence="db",
            discovery_date="2026-06-23",
        ),
        now=NOW,
    )
    monkeypatch.setattr(service, "_db_repository", Repository)
    response = LiveApiFootballResponse(
        endpoint="fixtures",
        params={"date": "2026-06-23"},
        status_code=200,
        elapsed_ms=1,
        payload={"response": []},
        headers={},
        captured_at=NOW,
    )

    assert service._save_raw_payload_first(
        endpoint="fixtures",
        params={"date": "2026-06-23"},
        response=response,
        payload_hash="a" * 64,
        payload={"response": []},
    ) == (True, None)
    assert captured["fixture_scope"] is RawFixtureScope.LIVE_DISCOVERY
    assert isinstance(captured["request_identity"], str)


def test_fixture_change_triggers_projection_before_task_success(
    monkeypatch,
    tmp_path: Path,
) -> None:
    class RuntimeRepository:
        def upsert_fixture_identities_with_business_changes(
            self,
            _rows: list[dict[str, Any]],
        ) -> tuple[int, list[str]]:
            return 1, ["api_football:1489404"]

        def insert_market_observations(self, _rows: list[dict[str, Any]]) -> int:
            return 0

    materialized: list[list[tuple[str, str]]] = []
    service = FutureFixtureRefreshService(
        client=FakeApiFootballClient(),
        config=FutureRefreshConfig(
            runtime_root=tmp_path,
            persistence="db",
        ),
        now=NOW,
        materialize_public_artifacts=lambda events: (
            materialized.append([(event.fixture_id, event.event_type) for event in events])
            or [event.fixture_id for event in events]
        ),
    )
    monkeypatch.setattr(
        "w2.matchday.repository.MatchdayRuntimeRepository",
        RuntimeRepository,
    )
    monkeypatch.setattr(service, "_write_audit", lambda _result: None)
    monkeypatch.setattr(service, "_seed_provider_primary_identities", lambda **_kwargs: None)
    response = LiveApiFootballResponse(
        endpoint="fixtures",
        params={},
        status_code=200,
        elapsed_ms=1,
        payload=FakeApiFootballClient().payload("fixtures", {}),
        headers={},
        captured_at=NOW,
    )

    result = service._persist_db(
        response,
        response.payload["response"][:1],
        [],
        [],
        [],
    )

    assert result.status == "COMPLETED"
    assert materialized == [[("1489404", "FIXTURE_CHANGED")]]


def test_checkpoint_refresh_fails_before_completion_when_materialization_fails(
    monkeypatch,
    tmp_path: Path,
) -> None:
    class MaterializableApiFootballClient(FakeApiFootballClient):
        def payload(self, endpoint: str, params: dict[str, str]) -> dict[str, Any]:
            if endpoint != "lineups":
                return super().payload(endpoint, params)

            def lineup(team_id: int, offset: int) -> dict[str, Any]:
                return {
                    "team": {"id": team_id},
                    "formation": "4-3-3",
                    "startXI": [
                        {
                            "player": {
                                "id": offset + index,
                                "name": f"Player {offset + index}",
                                "number": index + 1,
                                "pos": "G" if index == 0 else "M",
                            }
                        }
                        for index in range(11)
                    ],
                    "substitutes": [],
                }

            return {"response": [lineup(10, 100), lineup(20, 200)]}

    def fail_materialization(_events: list[object]) -> list[str]:
        raise RuntimeError("artifact write failed")

    database_url = f"sqlite+pysqlite:///{tmp_path / 'materialization.db'}"
    monkeypatch.setenv("W2_DATABASE_URL", database_url)
    get_settings.cache_clear()
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    seed_competition_runtime_authority(engine, environment="test", now=NOW)
    apply_collection_policy_update(engine, updated_by="materialization-test", now=NOW)

    audit = run_future_refresh_task(
        task_id="checkpoint-materialization-failure",
        key="checkpoint-materialization-failure",
        queued_at=NOW,
        competition_id="allsvenskan",
        runtime_root=tmp_path,
        client=MaterializableApiFootballClient(),
        now=NOW,
        persistence="db",
        materialize_public_artifacts=fail_materialization,
    )
    with Session(engine) as session:
        refresh_audit = session.scalar(select(FutureRefreshRunAuditModel))

    assert audit.status == "BLOCKED"
    assert audit.result["blockers"] == ["RuntimeError"]
    assert refresh_audit is not None and refresh_audit.blockers == ["RuntimeError"]


def test_future_refresh_error_type_is_runtime_error() -> None:
    assert issubclass(FutureRefreshError, RuntimeError)
