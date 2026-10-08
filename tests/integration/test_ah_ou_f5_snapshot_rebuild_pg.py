"""F5 回归：proven 快照重建降级（J1/J2）修复——真实 PG + 真实 trigger。

覆盖 future_refresh_repository.upsert_team_xg_rolling_snapshots 的两条 fail-closed：
- J1：已过 decision_at 的 proven 快照，source_matches 推进重建必须拒绝
  （TEAM_XG_SNAPSHOT_EXPIRED_REBUILD_FORBIDDEN），pit_proven / first_committed_at / 数值保留。
- J2：source_valid=false（提交 source_matches 与独立重算不一致）的 proven 快照重建
  必须拒绝（TEAM_XG_SNAPSHOT_REBUILD_SOURCE_INVALID），proven 行不被未验证数值替换。
"""
from __future__ import annotations

import dataclasses
import os
import subprocess
import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session


@pytest.fixture()
def repo():
    url = os.environ.get("W2_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("W2_TEST_POSTGRES_URL required")
    admin = create_engine(url, isolation_level="AUTOCOMMIT")
    name = "w2_f5_" + uuid.uuid4().hex[:12]
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{name}"'))
    db_url = url.rsplit("/", 1)[0] + "/" + name
    os.environ["W2_DATABASE_URL"] = db_url
    os.environ["W2_ENVIRONMENT"] = "staging"
    os.environ["W2_FUTURE_REFRESH_PERSISTENCE"] = "db"
    subprocess.run([".venv/bin/alembic", "upgrade", "head"], check=True,
                   env=os.environ.copy(), capture_output=True)

    from w2.config import get_settings
    get_settings.cache_clear()
    from w2.ingestion.future_refresh_repository import FutureRefreshDbRepository
    return FutureRefreshDbRepository()


HOME, AWAY = "10", "20"


def _fixture_item(fid: str, kickoff: datetime) -> dict:
    return {
        "fixture": {"id": fid, "date": kickoff.isoformat().replace("+00:00", "Z"),
                    "status": {"short": "FT"}},
        "league": {"id": 113, "season": "2026"},
        "teams": {"home": {"id": int(HOME)}, "away": {"id": int(AWAY)}},
        "goals": {"home": 2, "away": 1},
    }


def _stats_payload(fid: str, home_xg: str, away_xg: str) -> dict:
    return {
        "parameters": {"fixture": fid},
        "response": [
            {"team": {"id": int(HOME)},
             "statistics": [{"type": "expected_goals", "value": home_xg}]},
            {"team": {"id": int(AWAY)},
             "statistics": [{"type": "expected_goals", "value": away_xg}]},
        ],
    }


def _raw(payload: dict, endpoint: str, captured: datetime):
    from w2.domain.canonical_serialization import (
        HashDomain, SerializerVersion, canonical_sha256,
    )
    from w2.infrastructure.persistence.future_refresh_models import RawPayloadModel

    sha = canonical_sha256(payload, domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD,
                           version=SerializerVersion.LEGACY_V1)
    return RawPayloadModel(sha256=sha, endpoint=endpoint, captured_at=captured,
                           storage_uri="probe://local", payload=payload)


def _add_match(session, fid: str, kickoff: datetime, captured: datetime,
               home_xg: str = "1.7", away_xg: str = "0.8"):
    from w2.features.xg_materialization import parse_team_xg_matches
    from w2.infrastructure.persistence.future_refresh_models import TeamXgMatchModel

    fx_payload = {"response": [_fixture_item(fid, kickoff)]}
    st_payload = _stats_payload(fid, home_xg, away_xg)
    session.add(_raw(fx_payload, "fixtures", captured))
    st_raw = _raw(st_payload, "statistics", captured)
    session.add(st_raw)
    rows = parse_team_xg_matches(fixture_payload=_fixture_item(fid, kickoff),
                                 statistics_payload=st_payload,
                                 captured_at=captured,
                                 raw_payload_sha256=st_raw.sha256)
    for r in rows:
        session.add(TeamXgMatchModel(
            id=r.id, fixture_id=r.fixture_id, team_id=r.team_id,
            opponent_team_id=r.opponent_team_id, kickoff_at=r.kickoff_at,
            captured_at=r.captured_at, xg_for=r.xg_for, xg_against=r.xg_against,
            goals_for=r.goals_for, goals_against=r.goals_against,
            raw_payload_sha256=r.raw_payload_sha256, source_system=r.source_system,
        ))
    return rows


def _add_identity(session, target: str, kickoff: datetime, captured: datetime):
    from w2.infrastructure.persistence.matchday_intake_models import (
        MatchdayFixtureIdentityModel,
    )

    fx_raw = _raw({"response": [_fixture_item(target, kickoff)]}, "fixtures", captured)
    session.add(fx_raw)
    session.flush()
    session.add(MatchdayFixtureIdentityModel(
        fixture_id=f"api_football:{target}", provider="api_football",
        provider_fixture_id=target, competition_id="probe_league",
        provider_league_id="113", season="2026", kickoff_utc=kickoff,
        fixture_status="NS", home_provider_team_id=HOME,
        away_provider_team_id=AWAY, home_w2_team_id="w2:home",
        away_w2_team_id="w2:away", team_identity_status="RESOLVED",
        raw_payload_sha256=fx_raw.sha256, captured_at=captured,
        identity_hash="d" * 64, payload=_fixture_item(target, kickoff),
    ))


def _snapshot(decision_at: datetime, matches, team_id: str, target: str) -> dict:
    from w2.features.xg_materialization import materialize_rolling_xg

    snap = materialize_rolling_xg(team_id=team_id, as_of_fixture_id=target,
                                  as_of_time=decision_at, matches=list(matches),
                                  window=5, min_matches=3)
    assert snap is not None
    return dataclasses.asdict(snap)


def _seed_three_matches(repo, decision_at: datetime, prefix: str = "h"):
    with Session(repo.engine) as s:
        matches = []
        for i in range(3):
            k = decision_at - timedelta(days=5 - i)
            matches += _add_match(s, f"{prefix}{i}", k, k + timedelta(hours=3))
        s.commit()
    return matches


def _read(repo, snapshot_id: str):
    from w2.infrastructure.persistence.future_refresh_models import (
        TeamXgRollingSnapshotModel,
    )

    with Session(repo.engine) as s:
        return s.get(TeamXgRollingSnapshotModel, snapshot_id)


def test_f5_j1_expired_proven_snapshot_rebuild_forbidden(repo):
    from w2.ingestion.future_refresh_repository import FutureRefreshPersistenceError

    decision_at = datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=4)
    kickoff = decision_at + timedelta(hours=2)
    matches = _seed_three_matches(repo, decision_at)
    with Session(repo.engine) as s:
        _add_identity(s, "T1", kickoff, datetime.now(UTC) - timedelta(hours=1))
        s.commit()

    snap1 = _snapshot(decision_at, matches, HOME, "T1")
    repo.upsert_team_xg_rolling_snapshots([snap1])
    before = _read(repo, f"{HOME}:T1")
    assert before.pit_proven is True

    time.sleep(5)  # decision_at 过期

    with Session(repo.engine) as s:
        matches += _add_match(s, "h3", decision_at - timedelta(days=1),
                              decision_at - timedelta(hours=1))
        s.commit()
    snap2 = _snapshot(decision_at, matches, HOME, "T1")
    assert {m["id"] for m in snap2["source_matches"]} != {
        m["id"] for m in snap1["source_matches"]}

    with pytest.raises(FutureRefreshPersistenceError) as exc:
        repo.upsert_team_xg_rolling_snapshots([snap2])
    assert "TEAM_XG_SNAPSHOT_EXPIRED_REBUILD_FORBIDDEN" in str(exc.value)

    after = _read(repo, f"{HOME}:T1")
    assert after.pit_proven is True
    assert after.first_committed_at == before.first_committed_at
    assert after.rolling_xg_for == before.rolling_xg_for
    assert after.match_count == before.match_count


def test_f5_j2_source_invalid_proven_rebuild_forbidden(repo):
    from w2.ingestion.future_refresh_repository import FutureRefreshPersistenceError

    decision_at = datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=4)
    kickoff = decision_at + timedelta(hours=2)
    matches = _seed_three_matches(repo, decision_at, prefix="g")
    with Session(repo.engine) as s:
        _add_identity(s, "T2", kickoff, datetime.now(UTC) - timedelta(hours=1))
        s.commit()

    snap_b = _snapshot(decision_at, matches, AWAY, "T2")
    repo.upsert_team_xg_rolling_snapshots([snap_b])
    before = _read(repo, f"{AWAY}:T2")
    assert before.pit_proven is True

    tampered = dict(snap_b)
    tampered["source_matches"] = [dict(m, id="ghost:99") for m in snap_b["source_matches"]]
    tampered["rolling_xg_for"] = 9.99  # 独立重算绝不认可的数值

    with pytest.raises(FutureRefreshPersistenceError) as exc:
        repo.upsert_team_xg_rolling_snapshots([tampered])
    assert "TEAM_XG_SNAPSHOT_REBUILD_SOURCE_INVALID" in str(exc.value)

    after = _read(repo, f"{AWAY}:T2")
    assert after is not None
    assert after.rolling_xg_for == before.rolling_xg_for
    assert after.pit_proven is True
