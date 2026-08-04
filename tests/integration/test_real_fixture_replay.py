from __future__ import annotations

import json
import socket
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Column, Numeric, create_engine, delete

from w2.config import get_settings
from w2.infrastructure.database import Base
from w2.infrastructure.persistence.models import (
    StructuredLineupPlayerModel,
    StructuredLineupSnapshotModel,
)
from w2.ingestion import future_refresh
from w2.ingestion.future_refresh import (
    FutureFixtureRefreshService,
    FutureRefreshConfig,
)
from w2.providers.api_football import LiveApiFootballResponse
from w2.replay.real_fixture import (
    BundleIncompleteError,
    NetworkAccessAttempted,
    RealFixtureReplayError,
    _database_value,
    _materializer,
    _postmatch_ledger_replay,
    _seed_source_context,
    _source_runtime_environment,
    export_real_fixture_bundle,
    load_verified_bundle,
    network_disabled,
    replay_real_fixture_bundle,
)
from w2.tracking.outcome_ledger_repository import business_key

FIXTURE_ID = "990001"
SOURCE_SHA = "a" * 40
MIGRATION_HEAD = "test-head"


class _SavedSequenceSource:
    def __init__(self, now: datetime) -> None:
        self.now = now
        self.ordinal = 0

    def request_live(self, endpoint: str, params: dict[str, str]) -> LiveApiFootballResponse:
        expected = ("status", "fixtures", "odds", "lineups")
        assert endpoint == expected[self.ordinal]
        self.ordinal += 1
        return LiveApiFootballResponse(
            endpoint=endpoint,
            params=params,
            status_code=200,
            elapsed_ms=self.ordinal,
            payload=self._payload(endpoint),
            headers={
                "x-ratelimit-requests-remaining": "7000",
                "x-ratelimit-requests-limit": "7500",
            },
            requested_at=self.now + timedelta(seconds=self.ordinal),
            captured_at=self.now + timedelta(seconds=self.ordinal),
        )

    def _payload(self, endpoint: str) -> dict[str, Any]:
        if endpoint == "status":
            return {"response": {"requests": {"remaining": 7000, "limit": 7500}}}
        if endpoint == "fixtures":
            return {
                "response": [
                    {
                        "fixture": {
                            "id": int(FIXTURE_ID),
                            "date": (self.now + timedelta(days=7)).isoformat(),
                            "status": {"short": "NS"},
                        },
                        "league": {"id": 1, "season": 2026, "name": "Fixture League"},
                        "teams": {
                            "home": {"id": 10, "name": "Home"},
                            "away": {"id": 20, "name": "Away"},
                        },
                    }
                ]
            }
        if endpoint == "odds":
            return {
                "response": [
                    {
                        "fixture": {"id": int(FIXTURE_ID)},
                        "bookmakers": [
                            {
                                "id": 1,
                                "name": "Saved Book",
                                "bets": [
                                    {
                                        "id": 4,
                                        "name": "Asian Handicap",
                                        "values": [
                                            {"value": "Home -0.5", "odd": "1.91"},
                                            {"value": "Away +0.5", "odd": "1.93"},
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ]
            }
        assert endpoint == "lineups"
        return {
            "response": [
                _lineup(10, "Home", 100),
                _lineup(20, "Away", 200),
            ]
        }


def _lineup(team_id: int, team_name: str, offset: int) -> dict[str, Any]:
    return {
        "team": {"id": team_id, "name": team_name},
        "formation": "4-3-3",
        "startXI": [
            {"player": {"id": offset + index, "name": f"P{offset + index}"}} for index in range(11)
        ],
        "substitutes": [],
    }


def _source_bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    import w2.infrastructure.persistence  # noqa: F401
    from w2.infrastructure.persistence import (
        factor_model_models,  # noqa: F401
        league_models,  # noqa: F401
        models,  # noqa: F401
    )

    now = datetime(2026, 8, 4, 4, 0, tzinfo=UTC)
    database_url = f"sqlite+pysqlite:///{tmp_path / 'source.db'}"
    monkeypatch.setenv("W2_DATABASE_URL", database_url)
    monkeypatch.setenv("W2_ENVIRONMENT", "test")
    monkeypatch.setenv("W2_GIT_SHA", SOURCE_SHA)
    monkeypatch.setenv("W2_PROVIDER_CALLS_DISABLED", "true")
    monkeypatch.setenv("W2_PROVIDER_ENDPOINT_ALLOWLIST", "status,fixtures,odds,lineups")
    monkeypatch.setenv("W2_PROVIDER_HTTP_MAX_ATTEMPTS", "1")
    monkeypatch.setenv("W2_PROVIDER_PREFLIGHT_MIN_REMAINING", "0")
    monkeypatch.setenv("W2_PROVIDER_DAILY_HARD_CAP", "10000")
    monkeypatch.setenv("W2_PROVIDER_DAILY_RESERVE", "0")
    monkeypatch.setenv("W2_PROVIDER_REFRESH_TICK_HARD_CAP", "4")
    get_settings.cache_clear()
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    config = FutureRefreshConfig(
        competition_id="world_cup_2026",
        league_id="1",
        season="2026",
        horizon_days=10,
        max_fixture_candidates=1,
        max_odds_requests=1,
        quota_reserve=0,
        request_budget=4,
        feature_enrichment_enabled=True,
        feature_enrichment_endpoints=("lineups",),
        feature_enrichment_request_budget=1,
        source_revision=SOURCE_SHA,
        enabled=True,
        persistence="db",
        daily_hard_cap=10000,
        daily_reserve=0,
        actual_provider_calls_today=0,
        provider_refresh_batch_size=1,
        checkpoint_fixture_ids=(FIXTURE_ID,),
    )
    original_utc_now = future_refresh.utc_now
    future_refresh.utc_now = lambda: now + timedelta(seconds=5)
    try:
        result = FutureFixtureRefreshService(
            client=_SavedSequenceSource(now),
            config=config,
            now=now,
            materialize_public_artifacts=_materializer(now + timedelta(seconds=6)),
        ).run()
    finally:
        future_refresh.utc_now = original_utc_now
    assert result.status == "COMPLETED", result.blockers
    # Production candidate 1494232 has complete saved lineup raw but no
    # structured snapshots. The exporter must select raw evidence, not require
    # an already-materialized derivative.
    with engine.begin() as connection:
        connection.execute(delete(StructuredLineupPlayerModel))
        connection.execute(delete(StructuredLineupSnapshotModel))
    bundle_root = tmp_path / "private-bundle"
    export_real_fixture_bundle(
        engine=engine,
        bundle_root=bundle_root,
        source_git_sha=SOURCE_SHA,
        migration_head=MIGRATION_HEAD,
        fixture_id=FIXTURE_ID,
    )
    get_settings.cache_clear()
    return bundle_root


def test_real_fixture_raw_replay_is_offline_byte_identical_and_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle_root = _source_bundle(tmp_path, monkeypatch)
    receipt = replay_real_fixture_bundle(
        bundle_root=bundle_root,
        current_git_sha=SOURCE_SHA,
        current_migration_head=MIGRATION_HEAD,
    )
    assert receipt["REAL_FIXTURE_OFFLINE_REPLAY"] == "PASS"
    assert receipt["REAL_FIXTURE_PREMATCH_RECOMMENDATION_REPLAY"] == "PASS"
    assert receipt["NETWORK_CALLS_DURING_REPLAY"] == 0
    assert receipt["MANUAL_EVALUATION_INSERTS"] == 0
    assert receipt["MANUAL_PAIR_INSERTS"] == 0
    assert receipt["MANUAL_CHECKPOINT_INSERTS"] == 0
    assert receipt["DB_RECOMPUTE_BYTE_IDENTICAL"] is True
    assert receipt["REPLAY_IDEMPOTENT"] is True
    assert receipt["POSTMATCH_LEDGER_REPLAY"] == "PENDING"
    assert receipt["POSTMATCH_LEDGER_REPLAY_REASON"] == "SAVED_RESULT_EVIDENCE_MISSING"
    assert receipt["MANUAL_LEDGER_INSERTS"] == 0

    sanitized = json.loads((bundle_root / "manifest.sanitized.json").read_bytes())
    logical_paths = {item["logical_path"] for item in sanitized["file_receipts"]}
    assert logical_paths == {
        "raw/01-status.json",
        "raw/02-fixtures.json",
        "raw/03-odds.json",
        "raw/04-lineups.json",
        "source/context.json",
        "source/reference.json",
    }
    assert all(not path.startswith("/") for path in logical_paths)


def test_bundle_hash_tamper_is_rejected_before_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle_root = _source_bundle(tmp_path, monkeypatch)
    raw_path = bundle_root / "raw/03-odds.json"
    raw_path.write_bytes(raw_path.read_bytes() + b" ")
    with pytest.raises(RealFixtureReplayError, match="BUNDLE_FILE_(SIZE|HASH)_MISMATCH"):
        load_verified_bundle(bundle_root)


def test_network_guard_fails_closed() -> None:
    with network_disabled(), pytest.raises(NetworkAccessAttempted):
        socket.create_connection(("127.0.0.1", 9))


def test_source_context_restores_canonical_float_for_numeric_columns() -> None:
    value = _database_value(Column(Numeric), {"$w2_float": "3ff8000000000000"})

    assert value == Decimal("1.5")


def test_replay_uses_database_authority_runtime_environment() -> None:
    context = {
        "tables": {
            "league_season": [{"payload": {"environment": "staging"}}],
        }
    }

    assert _source_runtime_environment(context) == "staging"


def test_saved_result_without_prematch_pick_keeps_postmatch_replay_pending() -> None:
    payload = {
        "schema_version": "w2.forward_outcome_ledger.v3",
        "record_type": "capture",
        "fixture_id": "1494232",
        "captured_at": "2026-08-03T11:02:51Z",
        "capture_identity_hash": "a" * 64,
        "pick": {},
        "shadow_pick": None,
    }
    replay = _postmatch_ledger_replay(
        {
            "outcome_ledger": [
                {
                    "business_key": business_key(payload, "capture"),
                    "record_type": "capture",
                    "payload": payload,
                }
            ],
            "results": [
                {
                    "fixture_id": "api_football:1494232",
                    "result_status": "FT",
                    "home_goals": 0,
                    "away_goals": 2,
                }
            ],
        }
    )

    assert replay == {
        "POSTMATCH_LEDGER_REPLAY": "PENDING",
        "POSTMATCH_LEDGER_REPLAY_REASON": (
            "NO_SETTLEMENT_ELIGIBLE_PREMATCH_PICK_IN_SOURCE_LEDGER"
        ),
        "LEDGER_BUSINESS_IDENTITY_MATCH": True,
        "SOURCE_SETTLEMENT_ELIGIBLE_CAPTURE_COUNT": 0,
        "MANUAL_LEDGER_INSERTS": 0,
    }


def test_incomplete_database_reports_exact_missing_field_without_writing(
    tmp_path: Path,
) -> None:
    import w2.infrastructure.persistence  # noqa: F401

    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'empty.db'}")
    Base.metadata.create_all(engine)
    bundle_root = tmp_path / "must-not-exist"
    with pytest.raises(BundleIncompleteError) as raised:
        export_real_fixture_bundle(
            engine=engine,
            bundle_root=bundle_root,
            source_git_sha=SOURCE_SHA,
            migration_head=MIGRATION_HEAD,
            fixture_id=FIXTURE_ID,
        )
    assert raised.value.missing_fields == ("fixture_identity",)
    assert not bundle_root.exists()


def test_source_context_cannot_seed_any_recomputed_output_table(tmp_path: Path) -> None:
    import w2.infrastructure.persistence  # noqa: F401

    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'guard.db'}")
    Base.metadata.create_all(engine)
    with pytest.raises(RealFixtureReplayError, match="MANUAL_OUTPUT_SEED_FORBIDDEN"):
        _seed_source_context(
            engine,
            {
                "schema_version": "w2.real-fixture-source-context.v1",
                "tables": {"read_model_checkpoint": []},
            },
        )
