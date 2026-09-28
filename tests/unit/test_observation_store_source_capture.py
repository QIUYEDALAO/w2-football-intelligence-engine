"""F1R-B store: source_capture_id 应用层自洽校验（任务 9 方案①）。

不建跨表 FK；``source_capture_sha256`` 仅契约 hash 校验，跨表引用一致性改由
``source_capture_id`` 与 ``factor_inputs.source_record_ids`` 重算比对。
"""
from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "quant"))

from f1r_b_observation_store import (  # noqa: E402
    ForwardFactorObservationStore,
    StoreError,
    contract,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from w2.domain.canonical_serialization import HashDomain, canonical_sha256  # noqa: E402
from w2.infrastructure.persistence.forward_factor_models import (  # noqa: E402
    ForwardAhFactorObservationModel,
)

NOW = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
FACTORS = ("F3_REST_FITNESS", "F5_RECENT_AH_COVER", "F6_H2H", "F9_TRUE_XG")


def _source_capture_id(factor_id: str, record_ids: list[str]) -> str:
    digest = canonical_sha256(
        {
            "contract": "w2.f1r_b_source_capture.v1",
            "factor_id": factor_id,
            "record_ids": sorted(record_ids),
        },
        domain=HashDomain.FUTURE_REFRESH_EVIDENCE,
    )
    return f"w2.consumed_source_set.v1:{digest}"


def _record(factor_id: str, record_ids: list[str] | None = None) -> dict:
    if record_ids is None:
        record_ids = [f"{factor_id}-rec-1", f"{factor_id}-rec-2"]
    return {
        "evaluation_id": "eval-1",
        "attempt_id": "attempt-1",
        "fixture_id": "fix-1",
        "market": "ASIAN_HANDICAP",
        "factor_id": factor_id,
        "factor_version": f"w2.factor.{factor_id}",
        "factor_status": "INSUFFICIENT_DATA",
        "participated": False,
        "applied_weight": "0",
        "signed_score": None,
        "factor_inputs": {"source_record_ids": ",".join(record_ids)},
        "evidence_time_utc": (NOW - timedelta(days=2)).isoformat(),
        "evaluated_at_utc": NOW.isoformat(),
        "created_at_utc": (NOW + timedelta(minutes=1)).isoformat(),
        "source_capture_id": _source_capture_id(factor_id, record_ids),
        "source_capture_sha256": "b" * 64,
        "source_version": "sv",
    }


@pytest.fixture()
def store():
    from sqlalchemy import text

    from w2.infrastructure.persistence.factor_model_models import (
        CanonicalTeamMatchHistoryModel,
    )
    from w2.infrastructure.persistence import TeamXgRollingSnapshotModel

    engine = create_engine("sqlite://")
    ForwardAhFactorObservationModel.__table__.create(engine)
    CanonicalTeamMatchHistoryModel.__table__.create(engine)
    TeamXgRollingSnapshotModel.__table__.create(engine)
    # 存在校验需要 source 表里有被引用的 record_id。
    with engine.begin() as conn:
        for factor_id in FACTORS:
            for i in (1, 2):
                conn.execute(
                    text(
                        "INSERT INTO canonical_team_match_history "
                        "(history_id, fixture_id, provider, provider_fixture_id, competition_id, "
                        "season, kickoff_utc, fixture_status, team_side, team_provider_id, "
                        "opponent_provider_id, team_w2_id, opponent_w2_id, goals_for, goals_against, "
                        "result_identity_hash, source_raw_hash, captured_at, history_hash, payload) "
                        "VALUES (:rid, :fx, 'p', :pfx, 'c', 's', :ko, 'FT', 'HOME', 'tp', 'op', 'th', 'oa', 1, 0, 'rh', 'sh', :ko, :hh, '{}')"
                    ),
                    {
                        "rid": f"{factor_id}-rec-{i}",
                        "fx": f"fx-{factor_id}-{i}",
                        "pfx": f"pfx-{factor_id}-{i}",
                        "ko": (NOW - timedelta(days=10 - i)).isoformat(),
                        "hh": f"hh-{factor_id}-{i}",
                    },
                )
    return ForwardFactorObservationStore(engine)


def _make(store, overrides: dict | None = None):
    overrides = overrides or {}
    batch = []
    for factor_id in FACTORS:
        record = _record(factor_id)
        record.update(overrides.get(factor_id, {}))
        batch.append(contract.ForwardFactorObservation(**record))
    return store.append_batch(batch)


def test_self_consistent_batch_appends(store) -> None:
    result = _make(store)
    assert result["appended"] == 4


def test_forged_capture_id_refused(store) -> None:
    with pytest.raises(StoreError) as exc:
        _make(store, {"F6_H2H": {
            "source_capture_id": _source_capture_id("F6_H2H", ["other-rec"])}})
    assert exc.value.code == "SOURCE_CAPTURE_ID_MISMATCH"


def test_dropped_record_refused(store) -> None:
    with pytest.raises(StoreError) as exc:
        _make(store, {"F9_TRUE_XG": {
            "factor_inputs": {"source_record_ids": "F9_TRUE_XG-rec-1"}}})
    assert exc.value.code == "SOURCE_CAPTURE_ID_MISMATCH"


def test_malformed_capture_id_refused(store) -> None:
    with pytest.raises(StoreError) as exc:
        _make(store, {"F3_REST_FITNESS": {"source_capture_id": "not-a-prefix:abcd"}})
    assert exc.value.code == "SOURCE_CAPTURE_ID_FORMAT_INVALID"


def test_missing_record_ids_refused(store) -> None:
    with pytest.raises(StoreError) as exc:
        _make(store, {"F3_REST_FITNESS": {"factor_inputs": {}}})
    assert exc.value.code == "SOURCE_RECORD_IDS_MISSING"


def test_dangling_source_record_refused(store) -> None:
    # 自洽但引用了不存在的 source record（存在校验，整改 item 4）。
    with pytest.raises(StoreError) as exc:
        _make(store, {"F6_H2H": {
            "factor_inputs": {"source_record_ids": "ghost-rec"},
            "source_capture_id": _source_capture_id("F6_H2H", ["ghost-rec"]),
        }})
    assert exc.value.code == "SOURCE_RECORD_NOT_FOUND"
