from __future__ import annotations

from contextlib import nullcontext
from copy import deepcopy
from dataclasses import make_dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from w2.domain.canonical_serialization import (
    HashDomain,
    SerializerVersion,
    canonical_sha256,
    canonical_sha256 as serialize_canonical_sha256,
)
from w2.infrastructure.database import Base
from w2.infrastructure.persistence.api_models import ReadModelCheckpointModel
from w2.infrastructure.persistence.forward_evidence_models import (
    ForwardClockModel,
    RecommendationReviewLedgerModel,
)
from w2.infrastructure.persistence.model_forecast_models import ModelForecastCaptureModel
from w2.infrastructure.persistence.models import ResultModel
from w2.prematch.lifecycle import PRODUCER_INPUT_PROVENANCE_SCHEMA
from w2.prematch.read_model_projection import _analysis_evidence
from w2.strategy.simulate import _canonical_hash
from w2.tracking.forward_evidence import (
    CLOCK_ID,
    T0,
    TRACK_D_FADE,
    VALIDATION_SIGNAL,
    append_forward_evidence_in_session,
    append_validation_signal_settlement_in_session,
    record_shadow_evidence_in_session,
    register_forward_clock,
    settle_track_d_validation_signals_in_session,
)
from w2.tracking.model_forecast_ledger import (
    MODEL_FORECAST_CAPTURE_HASH_DOMAIN,
    MODEL_FORECAST_INPUT_MANIFEST_HASH_DOMAIN,
)


class _Rows:
    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self.rows = rows

    def all(self) -> list[SimpleNamespace]:
        return self.rows


class _Session:
    def __init__(
        self,
        *,
        capture: SimpleNamespace | None = None,
        quotes: list[SimpleNamespace] | None = None,
        shadow_analysis: str | None = None,
    ) -> None:
        self.clock: ForwardClockModel | None = None
        self.capture = capture
        self.quotes = quotes or []
        self.events: dict[str, RecommendationReviewLedgerModel] = {}
        self.shadow_analysis = (
            shadow_analysis if shadow_analysis is not None else _ANALYSIS_EVIDENCE_DIGEST
        )

    def get(self, model: type, key: str):
        if model is ForwardClockModel:
            return self.clock if key == CLOCK_ID else None
        if model is ModelForecastCaptureModel:
            return self.capture if key == "f" else None
        if model is RecommendationReviewLedgerModel:
            return self.events.get(key)
        if model is ReadModelCheckpointModel:
            return SimpleNamespace(
                payload={"input_manifest": {"analysis_evidence_sha256": self.shadow_analysis}}
            )
        raise AssertionError(model)

    def scalars(self, _query: object) -> _Rows:
        return _Rows(self.quotes)

    def scalar(self, _query: object):
        descriptions = getattr(_query, "column_descriptions", None)
        entity = descriptions[0].get("entity") if descriptions else None
        # forward reads the evaluation's own frozen artifact (shadow checkpoint)
        # via a select(ReadModelCheckpointModel); return the bound analysis digest.
        if entity is ReadModelCheckpointModel:
            return SimpleNamespace(
                payload={"input_manifest": {"analysis_evidence_sha256": self.shadow_analysis}}
            )
        return next(
            (row for row in self.events.values() if row.event_type == "DECISION_SNAPSHOT"),
            None,
        )

    def add(self, row: object) -> None:
        if isinstance(row, ForwardClockModel):
            self.clock = row
        elif isinstance(row, RecommendationReviewLedgerModel):
            self.events[row.review_event_id] = row
        else:
            raise AssertionError(type(row))

    def flush(self) -> None:
        pass

    def begin_nested(self):
        return nullcontext()


_SCORE_MATRIX_ROWS = [
    {"home_goals": 0, "away_goals": 0, "probability": 0.25},
    {"home_goals": 2, "away_goals": 1, "probability": 0.5},
    {"home_goals": 3, "away_goals": 0, "probability": 0.25},
]
# TOTALS OVER 2.5 从 _SCORE_MATRIX_ROWS 独立重算的五态（独立 oracle）。
_SETTLED_DISTRIBUTION = {
    "WIN": 0.75, "HALF_WIN": 0.0, "PUSH": 0.0, "HALF_LOSS": 0.0, "LOSS": 0.25,
}
# 真实 writer 语义：capture 的 simulation 与 producer 输入组件，hash 域可复算。
_SIMULATION = {
    "model_version": "v1",
    "lambda_home": 1.2,
    "lambda_away": 1.0,
    "calibration": {
        "params": {"dixon_coles_rho": -0.08},
        "simulation_input_hash": "e" * 64,
    },
}
# R5: producer_input_provenance.simulation_digest is produced by the frozen
# materializer under LEGACY_V1 (read_model_projection.canonical_sha256), so the
# synthetic fixture must match that serialization or the forward cross-check
# rejects every real chain it is meant to model.
_SIMULATION_DIGEST = serialize_canonical_sha256(
    _SIMULATION,
    domain=HashDomain.PREMATCH_READ_MODEL_SIMULATION,
    version=SerializerVersion.LEGACY_V1,
)
_ANALYSIS_EVIDENCE_DIGEST = canonical_sha256(
    {}, domain=HashDomain.PREMATCH_READ_MODEL_ANALYSIS_EVIDENCE
)
_MODEL_INPUT_HASH = canonical_sha256(
    {
        "simulation": _SIMULATION_DIGEST,
        "analysis_evidence": _ANALYSIS_EVIDENCE_DIGEST,
        "lineup_input_hash": None,
    },
    domain=HashDomain.PREMATCH_READ_MODEL_DYNAMIC_EVALUATION,
)


def _version(at: datetime) -> SimpleNamespace:
    return SimpleNamespace(
        evaluation_id="e",
        identity_hash="a" * 64,
        fixture_id="api_football:123",
        market="TOTALS",
        selection="OVER",
        exact_line=2.5,
        bookmaker_id="4",
        capture_id="c",
        quote_identity_hash="b" * 64,
        capture_at=at - timedelta(minutes=1),
        decimal_odds=1.9,
        model_forecast_capture_identity_hash="f",
        evaluated_at=at,
        evaluation_policy_version="candidate-eval.v2",
        calibration_identity="candidate-eval.v2",
        model_input_hash=_MODEL_INPUT_HASH,
        lineup_input_hash=None,
        producer_input_provenance={
            "schema_version": PRODUCER_INPUT_PROVENANCE_SCHEMA,
            "simulation_digest": _SIMULATION_DIGEST,
            "analysis_evidence_digest": _ANALYSIS_EVIDENCE_DIGEST,
            "lineup_input_hash": None,
            # The newest xG snapshot observation time (source fact), independent
            # of the capture time. Must equal the capture's xG as-of upper bound.
            "model_input_available_at": _xg_as_of(at),
            "quote_available_at": (at - timedelta(minutes=1)).isoformat(),
        },
        model_settlement_distribution=dict(_SETTLED_DISTRIBUTION),
        model_version="v1",
        score_matrix_hash=_canonical_hash(_SCORE_MATRIX_ROWS),
        state=SimpleNamespace(value="NO_EDGE_CURRENT"),
        factor_decision_status="ADMITTED",
    )


def _xg_as_of(at: datetime) -> str:
    return (at - timedelta(minutes=5)).astimezone(UTC).isoformat().replace("+00:00", "Z")


def _capture(at: datetime) -> SimpleNamespace:
    """真实 writer 语义：capture 各 hash 域可从 payload 重算，不用重复字母冒充。"""
    frozen_input_manifest = {
        "analysis_evidence_sha256": _ANALYSIS_EVIDENCE_DIGEST,
        "simulation_sha256": _SIMULATION_DIGEST,
    }
    manifest = {
        "frozen_input_manifest": frozen_input_manifest,
        "fixture_identity_hash": "f" * 64,
        "simulation_input_hash": "e" * 64,
        "four_field_xg_identity_hash": "x" * 64,
    }
    rows = deepcopy(_SCORE_MATRIX_ROWS)
    core = {
        "model_input_manifest": manifest,
        "score_matrix_distribution": rows,
        "simulation_replay": {"simulation": deepcopy(_SIMULATION)},
        "four_field_xg_identity": {
            "home": {"as_of": _xg_as_of(at), "xg_for": 1.5, "xg_against": 1.0},
            "away": {"as_of": _xg_as_of(at), "xg_for": 1.2, "xg_against": 1.1},
            "four_fields": {
                "home_xg_for": 1.5,
                "home_xg_against": 1.0,
                "away_xg_for": 1.2,
                "away_xg_against": 1.1,
            },
        },
    }
    capture_identity_hash = canonical_sha256(
        core, domain=MODEL_FORECAST_CAPTURE_HASH_DOMAIN
    )
    payload = {**core, "capture_identity_hash": capture_identity_hash}
    return SimpleNamespace(
        fixture_id="api_football:123",
        captured_at=at - timedelta(minutes=3),
        kickoff_utc=at + timedelta(hours=2),
        model_family="EXACT_DC_POISSON",
        model_version="v1",
        model_input_manifest_hash=canonical_sha256(
            manifest, domain=MODEL_FORECAST_INPUT_MANIFEST_HASH_DOMAIN
        ),
        capture_identity_hash=capture_identity_hash,
        payload_sha256=canonical_sha256(
            payload, domain=MODEL_FORECAST_CAPTURE_HASH_DOMAIN
        ),
        score_matrix_hash=_canonical_hash(rows),
        payload=payload,
    )


def _quotes(at: datetime) -> list[SimpleNamespace]:
    return [
        SimpleNamespace(
            observation_id=side,
            provider_fixture_id="123",
            capture_id="c",
            canonical_market="TOTALS",
            canonical_selection=side,
            bookmaker_id="4",
            line="2.5",
            decimal_odds="1.9" if side == "OVER" else "2.0",
            captured_at=at - timedelta(minutes=1),
        )
        for side in ("OVER", "UNDER")
    ]


def test_clock_is_one_shot_and_cannot_precede_t0() -> None:
    session = _Session()
    with pytest.raises(ValueError, match="BEFORE_T0"):
        register_forward_clock(
            session, started_at=T0 - timedelta(seconds=1), code_revision="a" * 40
        )
    first = register_forward_clock(session, started_at=T0, code_revision="a" * 40)
    assert register_forward_clock(session, started_at=T0, code_revision="a" * 40) is first
    with pytest.raises(ValueError, match="ALREADY_STARTED"):
        register_forward_clock(
            session, started_at=T0 + timedelta(seconds=1), code_revision="a" * 40
        )


def test_new_evaluation_binds_both_quotes_and_model_parameters() -> None:
    """新评估写入并绑定报价/模型参数；producer 输入内容等价性 fail-closed。"""
    at = datetime(2026, 9, 26, 8, tzinfo=UTC)
    session = _Session(capture=_capture(at), quotes=_quotes(at))
    assert append_forward_evidence_in_session(session, _version(at)) is None
    register_forward_clock(session, started_at=T0, code_revision="a" * 40)
    row = append_forward_evidence_in_session(session, _version(at))
    assert row is not None
    # P01：真实 provenance 可复算、simulation 与 capture 交叉一致、时间合法 → PROVABLE。
    assert row.pit_status == "PROVABLE"
    assert row.payload["exclusion_reasons"] == []
    assert row.payload["lambda_home"] == 1.2
    assert row.payload["rho"] == -0.08
    assert row.payload["quote_observation_ids"] == ["OVER", "UNDER"]
    assert (
        append_forward_evidence_in_session(session, _version(at)).review_event_id
        == row.review_event_id
    )
    assert len(session.events) == 1


def test_missing_or_mismatched_evidence_is_kept_but_not_pit_provable() -> None:
    at = datetime(2026, 9, 26, 8, tzinfo=UTC)
    session = _Session(capture=_capture(at), quotes=_quotes(at)[:1])
    register_forward_clock(session, started_at=T0, code_revision="a" * 40)
    row = append_forward_evidence_in_session(session, _version(at))
    assert row is not None and row.pit_status == "PIT_UNPROVABLE"
    assert "QUOTE_PAIR_MISMATCH" in row.payload["exclusion_reasons"]
    assert row.payload["quote_pair_identity"] is None


def _evidence_for(
    at: datetime, capture: SimpleNamespace, version: SimpleNamespace | None = None
):
    session = _Session(capture=capture, quotes=_quotes(at))
    register_forward_clock(session, started_at=T0, code_revision="a" * 40)
    return append_forward_evidence_in_session(session, version or _version(at))


def test_ar2_producer_input_and_manifest_mapping_rejections() -> None:
    """A：producer 输入缺/错、capture manifest 错配 → 明确 UNPROVABLE，不删检查放行。"""
    at = datetime(2026, 9, 26, 8, tzinfo=UTC)

    missing = _version(at)
    missing.model_input_hash = None
    assert "MISSING_PRODUCER_INPUT" in _evidence_for(
        at, _capture(at), missing
    ).payload["exclusion_reasons"]

    non_hex = _version(at)
    non_hex.model_input_hash = "different-producer-input"
    assert "INVALID_PRODUCER_INPUT_HASH" in _evidence_for(
        at, _capture(at), non_hex
    ).payload["exclusion_reasons"]

    manifest_mismatch = _capture(at)
    manifest_mismatch.model_input_manifest_hash = "e" * 64
    assert "MANIFEST_HASH_MISMATCH" in _evidence_for(
        at, manifest_mismatch
    ).payload["exclusion_reasons"]


def test_ar2_producer_input_component_mismatch_rejected() -> None:
    """N01：producer hash 合法但错误、或组件改而未改 hash → 独立拒绝（复算不一致）。"""
    at = datetime(2026, 9, 26, 8, tzinfo=UTC)

    # 内容错误：合法 64hex，但与 provenance 组件复算不一致。
    wrong_content = _version(at)
    wrong_content.model_input_hash = "f" * 64
    row = _evidence_for(at, _capture(at), wrong_content)
    assert row.pit_status == "PIT_UNPROVABLE"
    assert "PRODUCER_INPUT_HASH_MISMATCH" in row.payload["exclusion_reasons"]

    # 组件被改但 hash 未改：simulation_digest 变，model_input_hash 不变。
    tampered = _version(at)
    tampered.producer_input_provenance = dict(tampered.producer_input_provenance)
    tampered.producer_input_provenance["simulation_digest"] = "f" * 64
    row2 = _evidence_for(at, _capture(at), tampered)
    assert row2.pit_status == "PIT_UNPROVABLE"
    assert "PRODUCER_INPUT_HASH_MISMATCH" in row2.payload["exclusion_reasons"]


def test_ar2_producer_simulation_cross_check_rejected() -> None:
    """N02：组件自洽但来自另一模型计算 → simulation 交叉核验独立拒绝。"""
    at = datetime(2026, 9, 26, 8, tzinfo=UTC)
    tampered = _version(at)
    tampered.producer_input_provenance = dict(tampered.producer_input_provenance)
    wrong_digest = canonical_sha256(
        {"model_version": "v9"}, domain=HashDomain.PREMATCH_READ_MODEL_SIMULATION
    )
    tampered.producer_input_provenance["simulation_digest"] = wrong_digest
    # 组件自洽：model_input_hash 同步改为 wrong_digest 对应的复算值。
    tampered.model_input_hash = canonical_sha256(
        {
            "simulation": wrong_digest,
            "analysis_evidence": _ANALYSIS_EVIDENCE_DIGEST,
            "lineup_input_hash": None,
        },
        domain=HashDomain.PREMATCH_READ_MODEL_DYNAMIC_EVALUATION,
    )
    row = _evidence_for(at, _capture(at), tampered)
    assert row.pit_status == "PIT_UNPROVABLE"
    assert "PRODUCER_SIMULATION_MISMATCH" in row.payload["exclusion_reasons"]
    assert "PRODUCER_INPUT_HASH_MISMATCH" not in row.payload["exclusion_reasons"]


def test_ar2_producer_provenance_missing_or_bad_time_rejected() -> None:
    """N04：缺 profile / 输入时间缺或未来 → 独立拒绝。"""
    at = datetime(2026, 9, 26, 8, tzinfo=UTC)

    missing = _version(at)
    missing.producer_input_provenance = None
    row = _evidence_for(at, _capture(at), missing)
    assert row.pit_status == "PIT_UNPROVABLE"
    assert "MISSING_PRODUCER_INPUT_PROVENANCE" in row.payload["exclusion_reasons"]

    bad_time = _version(at)
    bad_time.producer_input_provenance = dict(bad_time.producer_input_provenance)
    bad_time.producer_input_provenance["model_input_available_at"] = (
        at + timedelta(hours=1)
    ).isoformat()
    row2 = _evidence_for(at, _capture(at), bad_time)
    assert row2.pit_status == "PIT_UNPROVABLE"
    assert "PRODUCER_INPUT_TIME_UNPROVABLE" in row2.payload["exclusion_reasons"]


def _rehash_provenance(version: SimpleNamespace) -> None:
    """重算 model_input_hash，让 provenance 组件自洽（隔离验证交叉核验 guard）。"""
    provenance = version.producer_input_provenance
    body = {
        "simulation": provenance["simulation_digest"],
        "analysis_evidence": provenance["analysis_evidence_digest"],
        "lineup_input_hash": provenance["lineup_input_hash"],
    }
    if provenance.get("scoreline_projection_contract_version") is not None:
        body["scoreline_projection_contract_version"] = provenance[
            "scoreline_projection_contract_version"
        ]
    version.model_input_hash = canonical_sha256(
        body, domain=HashDomain.PREMATCH_READ_MODEL_DYNAMIC_EVALUATION
    )


def test_ar4_producer_lineup_mismatch_rejected() -> None:
    """R4-03：provenance 与 evaluation 自身 lineup 身份错配 → 独立拒绝。"""
    at = datetime(2026, 9, 26, 8, tzinfo=UTC)
    version = _version(at)
    version.lineup_input_hash = "actual-lineup-A"
    version.producer_input_provenance = dict(version.producer_input_provenance)
    version.producer_input_provenance["lineup_input_hash"] = "different-lineup-B"
    _rehash_provenance(version)
    row = _evidence_for(at, _capture(at), version)
    assert row.pit_status == "PIT_UNPROVABLE"
    assert "PRODUCER_LINEUP_MISMATCH" in row.payload["exclusion_reasons"]
    assert "PRODUCER_INPUT_HASH_MISMATCH" not in row.payload["exclusion_reasons"]


def test_ar4_analysis_evidence_reference_rejected() -> None:
    """R4-03：任意 analysis digest（无对应 frozen 证据）→ 引用核验拒绝。"""
    at = datetime(2026, 9, 26, 8, tzinfo=UTC)
    version = _version(at)
    version.producer_input_provenance = dict(version.producer_input_provenance)
    version.producer_input_provenance["analysis_evidence_digest"] = "9" * 64
    _rehash_provenance(version)
    row = _evidence_for(at, _capture(at), version)
    assert row.pit_status == "PIT_UNPROVABLE"
    assert "PRODUCER_ANALYSIS_EVIDENCE_MISMATCH" in row.payload["exclusion_reasons"]


def test_ar5_null_analysis_digest_rejected() -> None:
    """R5-02：analysis digest 为 null 必须拒绝，不能两端 null 相等放行。"""
    at = datetime(2026, 9, 26, 8, tzinfo=UTC)
    version = _version(at)
    version.producer_input_provenance = dict(version.producer_input_provenance)
    version.producer_input_provenance["analysis_evidence_digest"] = None
    _rehash_provenance(version)
    row = _evidence_for(at, _capture(at), version)
    assert row.pit_status == "PIT_UNPROVABLE"
    assert "INVALID_PRODUCER_ANALYSIS_EVIDENCE_DIGEST" in row.payload["exclusion_reasons"]


def test_ar5_legal_later_quote_update_not_rejected() -> None:
    """R5-02/P03：模型不变 + 较晚合法报价更新，不因新旧 analysis 摘要不同误拒。

    模型证据（simulation/版本/矩阵）仍与 capture 交叉一致；报价证据（analysis
    digest）从本次 evaluation 自己的 frozen artifact 重算，所以新报价摘要合法
    通过，capture 内旧报价摘要不参与该项核验。
    """
    at = datetime(2026, 9, 26, 8, tzinfo=UTC)
    old = {
        "market_candidates": {
            "ou": {
                "analysis_evidence": {
                    "quote_identity": {
                        "captured_at": "2026-09-26T07:56:00Z",
                        "decimal_odds": "1.88",
                    }
                }
            }
        }
    }
    new = deepcopy(old)
    new["market_candidates"]["ou"]["analysis_evidence"]["quote_identity"] = {
        "captured_at": "2026-09-26T07:59:00Z",
        "decimal_odds": "1.90",
    }

    def digest(card: dict) -> str:
        return canonical_sha256(
            _analysis_evidence(card), domain=HashDomain.PREMATCH_READ_MODEL_ANALYSIS_EVIDENCE
        )

    old_digest = digest(old)
    new_digest = digest(new)

    capture = _capture(at)
    capture.payload["model_input_manifest"]["frozen_input_manifest"][
        "analysis_evidence_sha256"
    ] = old_digest
    capture.model_input_manifest_hash = canonical_sha256(
        capture.payload["model_input_manifest"], domain=MODEL_FORECAST_INPUT_MANIFEST_HASH_DOMAIN
    )
    identity = {
        key: value for key, value in capture.payload.items() if key != "capture_identity_hash"
    }
    capture.capture_identity_hash = canonical_sha256(
        identity, domain=MODEL_FORECAST_CAPTURE_HASH_DOMAIN
    )
    capture.payload["capture_identity_hash"] = capture.capture_identity_hash
    capture.payload_sha256 = canonical_sha256(
        capture.payload, domain=MODEL_FORECAST_CAPTURE_HASH_DOMAIN
    )

    version = _version(at)
    version.producer_input_provenance = dict(version.producer_input_provenance)
    version.producer_input_provenance["analysis_evidence_digest"] = new_digest
    _rehash_provenance(version)

    session = _Session(capture=capture, quotes=_quotes(at), shadow_analysis=new_digest)
    register_forward_clock(session, started_at=T0, code_revision="a" * 40)
    row = append_forward_evidence_in_session(session, version)
    assert row.pit_status == "PROVABLE", row.payload["exclusion_reasons"]


def test_ar4_input_source_time_backdate_rejected() -> None:
    """R4-01：无来源的早期 ISO 时间（与 capture xG as-of 不符）→ 来源拒绝。"""
    at = datetime(2026, 9, 26, 8, tzinfo=UTC)
    version = _version(at)
    version.producer_input_provenance = dict(version.producer_input_provenance)
    version.producer_input_provenance["model_input_available_at"] = "2000-01-01T00:00:00Z"
    row = _evidence_for(at, _capture(at), version)
    assert row.pit_status == "PIT_UNPROVABLE"
    assert "PRODUCER_INPUT_SOURCE_MISMATCH" in row.payload["exclusion_reasons"]


def test_ar2_payload_identity_and_matrix_real_recompute() -> None:
    """B：payload / identity / 完整矩阵用现有 canonical 合同真实重算，任一不自洽拒绝。"""
    at = datetime(2026, 9, 26, 8, tzinfo=UTC)

    payload_hash = _capture(at)
    payload_hash.payload_sha256 = "e" * 64
    assert "PAYLOAD_HASH_MISMATCH" in _evidence_for(
        at, payload_hash
    ).payload["exclusion_reasons"]

    identity = _capture(at)
    identity.capture_identity_hash = "e" * 64
    assert "CAPTURE_IDENTITY_MISMATCH" in _evidence_for(
        at, identity
    ).payload["exclusion_reasons"]

    version_conflict = _capture(at)
    version_conflict.payload["simulation_replay"]["simulation"]["model_version"] = "other-model"
    assert "MODEL_VERSION_MISMATCH" in _evidence_for(
        at, version_conflict
    ).payload["exclusion_reasons"]

    # 原矩阵真实 hash 不变、完整矩阵内容改变 → 拒绝。
    tampered = _capture(at)
    digest = _canonical_hash(list(tampered.payload["score_matrix_distribution"]))
    tampered.score_matrix_hash = digest
    version = _version(at)
    version.score_matrix_hash = digest
    tampered.payload["score_matrix_distribution"] = [
        {"home_goals": 0, "away_goals": 0, "probability": 0.25},
        {"home_goals": 1, "away_goals": 2, "probability": 0.75},
    ]
    assert "CAPTURE_SCORE_MATRIX_HASH_MISMATCH" in _evidence_for(
        at, tampered, version
    ).payload["exclusion_reasons"]


def test_ar2_matrix_rejected_before_parse() -> None:
    """B：坏行、2.9 比分、重复格、非法概率在解析转换前整体拒绝，不静默修理。"""
    at = datetime(2026, 9, 26, 8, tzinfo=UTC)

    bad_row = _capture(at)
    bad_row.payload["score_matrix_distribution"].append({"bad": "row"})
    assert "INVALID_SCORE_MATRIX" in _evidence_for(
        at, bad_row
    ).payload["exclusion_reasons"]

    fractional = _capture(at)
    fractional.payload["score_matrix_distribution"][1]["home_goals"] = 2.9
    assert "INVALID_SCORE_MATRIX" in _evidence_for(
        at, fractional
    ).payload["exclusion_reasons"]

    duplicate = _capture(at)
    duplicate.payload["score_matrix_distribution"].append(
        dict(duplicate.payload["score_matrix_distribution"][0])
    )
    assert "INVALID_SCORE_MATRIX" in _evidence_for(
        at, duplicate
    ).payload["exclusion_reasons"]

    bad_prob = _capture(at)
    bad_prob.payload["score_matrix_distribution"][0]["probability"] = -0.1
    assert "INVALID_SCORE_MATRIX" in _evidence_for(
        at, bad_prob
    ).payload["exclusion_reasons"]


def test_forecast_capture_semantic_rejections() -> None:
    """M05/M06/M09：错比赛、错模型 family、错输入 manifest、错分布各自拒绝，不 PROVABLE。"""
    at = datetime(2026, 9, 26, 8, tzinfo=UTC)

    def evidence_for(capture, version=None):
        session = _Session(capture=capture, quotes=_quotes(at))
        register_forward_clock(session, started_at=T0, code_revision="a" * 40)
        return append_forward_evidence_in_session(session, version or _version(at))

    wrong_fixture = _capture(at)
    wrong_fixture.fixture_id = "api_football:999"
    row = evidence_for(wrong_fixture)
    assert "MODEL_IDENTITY_UNPROVABLE" in row.payload["exclusion_reasons"]

    wrong_family = _capture(at)
    wrong_family.model_family = "OTHER_FAMILY"
    assert "MODEL_FAMILY_MISMATCH" in evidence_for(wrong_family).payload["exclusion_reasons"]

    wrong_version = _capture(at)
    wrong_version.model_version = "v2"  # 列与 payload 的 simulation.model_version("v1") 不一致
    assert "MODEL_VERSION_MISMATCH" in evidence_for(wrong_version).payload["exclusion_reasons"]

    wrong_manifest = _capture(at)
    wrong_manifest.payload["model_input_manifest"] = {}
    assert "MISSING_MODEL_INPUT_MANIFEST" in evidence_for(
        wrong_manifest
    ).payload["exclusion_reasons"]

    wrong_dist = _version(at)
    wrong_dist.model_settlement_distribution = {
        "WIN": 0.0, "HALF_WIN": 0.0, "PUSH": 0.0, "HALF_LOSS": 0.0, "LOSS": 1.0,
    }
    assert "SETTLEMENT_DISTRIBUTION_MISMATCH" in evidence_for(
        _capture(at), wrong_dist
    ).payload["exclusion_reasons"]


def test_five_state_independent_oracle_recomputes_from_score_matrix() -> None:
    """M03：独立 oracle 用 settle_total_goals 重算五态，不依赖实现的校验函数。"""
    from w2.domain.odds import settle_total_goals

    values = {"WIN": 0.0, "HALF_WIN": 0.0, "PUSH": 0.0, "HALF_LOSS": 0.0, "LOSS": 0.0}
    for (home, away), probability in {
        (0, 0): 0.25, (2, 1): 0.5, (3, 0): 0.25,
    }.items():
        outcome = settle_total_goals(home + away, "OVER", Decimal("2.5")).value
        values[outcome] += probability
    assert values == _SETTLED_DISTRIBUTION


def test_pre_clock_evaluations_are_never_backfilled() -> None:
    session = _Session()
    register_forward_clock(session, started_at=T0 + timedelta(hours=2), code_revision="a" * 40)
    assert append_forward_evidence_in_session(session, _version(T0 + timedelta(hours=1))) is None
    assert not session.events


def test_shadow_writer_logs_failure_without_aborting_evaluation(monkeypatch, caplog) -> None:
    def broken(_session, _version):
        raise RuntimeError("storage unavailable")

    monkeypatch.setattr("w2.tracking.forward_evidence.append_forward_evidence_in_session", broken)
    record_shadow_evidence_in_session(_Session(), _version(T0))
    assert "FORWARD_EVIDENCE_WRITE_FAILED evaluation_id=e" in caplog.text


def test_under_evaluation_creates_separate_pit_fade_decision_and_channel_settlement() -> None:
    at = datetime(2026, 9, 26, 8, tzinfo=UTC)
    source = _version(at)
    source.selection = "UNDER"
    source.bookmaker_id = "36"
    source.decimal_odds = 1.98
    source.track_d_validation_signal = None
    source.model_settlement_distribution = {
        "WIN": 0.25, "HALF_WIN": 0.0, "PUSH": 0.0,
        "HALF_LOSS": 0.0, "LOSS": 0.75,
    }
    version_type = make_dataclass("UnderVersion", [(key, object) for key in vars(source)])
    version = version_type(**vars(source))
    quotes = [
        SimpleNamespace(
            observation_id=f"{bookmaker}-{side}",
            provider_fixture_id="123",
            capture_id="c",
            canonical_market="TOTALS",
            canonical_selection=side,
            bookmaker_id=bookmaker,
            line="2.5",
            decimal_odds=price,
            captured_at=at - timedelta(minutes=1),
        )
        for bookmaker, side, price in (
            ("36", "UNDER", "1.98"), ("36", "OVER", "1.92"),
            ("4", "UNDER", "1.90"), ("4", "OVER", "1.93"),
        )
    ]
    session = _Session(capture=_capture(at), quotes=quotes)
    register_forward_clock(session, started_at=T0, code_revision="a" * 40)

    fade_returned = record_shadow_evidence_in_session(session, version)

    rows = list(session.events.values())
    assert len(rows) == 2
    fade = next(row for row in rows if row.event_type == "DECISION_SNAPSHOT")
    assert fade_returned is fade
    assert fade.pit_status == "PROVABLE"
    assert fade.payload["candidate_kind"] == TRACK_D_FADE
    assert fade.payload["display_state"] == VALIDATION_SIGNAL
    assert fade.payload["official_recommendation"] is False
    assert fade.payload["original_selection"] == "UNDER"
    assert fade.payload["selection"] == "OVER"
    assert fade.payload["derived_from_evaluation_id"] == version.evaluation_id
    assert fade.payload["decimal_odds_channel"] == 1.92
    assert fade.payload["decimal_odds_pinnacle"] == 1.93
    assert fade.payload["channel_quote_identity"] == "36-OVER"
    assert fade.payload["pinnacle_quote_identity"]
    assert fade.payload["market_quote_identity"] == fade.payload["pinnacle_quote_identity"]
    assert fade.payload["source_quote_identity"] == version.quote_identity_hash
    assert fade.payload["track_d_validation_signal"]["fade_delta"] == 0.05

    settled = append_validation_signal_settlement_in_session(
        session,
        evaluation_id=version.evaluation_id,
        settlement="WIN",
        profit_units_channel=0.92,
        settled_at=at + timedelta(hours=3),
        home_goals=2,
        away_goals=1,
    )
    assert settled.payload["profit_units_channel"] == 0.92
    assert settled.payload["rebate_units_channel"] == pytest.approx(0.023)
    assert settled.payload["profit_units_channel_with_rebate"] == pytest.approx(0.943)


def test_t1_totals_no_edge_reclassify_keeps_fade_derivation() -> None:
    """裁决 T1 把 TOTALS 改判 NO_EDGE_CURRENT 后，fade 仍从 UNDER 评估派生。"""
    at = datetime(2026, 9, 26, 8, tzinfo=UTC)
    source = _version(at)
    source.selection = "UNDER"
    source.bookmaker_id = "36"
    source.decimal_odds = 1.98
    source.state = SimpleNamespace(value="NO_EDGE_CURRENT")
    source.track_d_validation_signal = None
    source.model_settlement_distribution = {
        "WIN": 0.25, "HALF_WIN": 0.0, "PUSH": 0.0,
        "HALF_LOSS": 0.0, "LOSS": 0.75,
    }
    version_type = make_dataclass("T1NoEdgeUnder", [(key, object) for key in vars(source)])
    version = version_type(**vars(source))
    quotes = [
        SimpleNamespace(
            observation_id=f"{bookmaker}-{side}",
            provider_fixture_id="123",
            capture_id="c",
            canonical_market="TOTALS",
            canonical_selection=side,
            bookmaker_id=bookmaker,
            line="2.5",
            decimal_odds=price,
            captured_at=at - timedelta(minutes=1),
        )
        for bookmaker, side, price in (
            ("36", "UNDER", "1.98"), ("36", "OVER", "1.92"),
            ("4", "UNDER", "1.90"), ("4", "OVER", "1.93"),
        )
    ]
    session = _Session(capture=_capture(at), quotes=quotes)
    register_forward_clock(session, started_at=T0, code_revision="a" * 40)

    fade = record_shadow_evidence_in_session(session, version)

    assert fade is not None
    assert fade.payload["candidate_kind"] == TRACK_D_FADE
    assert fade.payload["display_state"] == VALIDATION_SIGNAL
    assert fade.payload["selection"] == "OVER"


def test_pinnacle_cannot_be_used_as_fade_channel_price() -> None:
    at = datetime(2026, 9, 26, 8, tzinfo=UTC)
    version = _version(at)
    version.selection = "OVER"
    version.bookmaker_id = "4"
    version.track_d_validation_signal = {"source_selection": "UNDER"}
    session = _Session(capture=_capture(at), quotes=_quotes(at))
    register_forward_clock(session, started_at=T0, code_revision="a" * 40)

    row = append_forward_evidence_in_session(
        session, version, _event_type="DECISION_SNAPSHOT"
    )

    assert row is not None
    assert row.payload["candidate_kind"] != TRACK_D_FADE
    assert "TRACK_D_CHANNEL_OR_MARKET_QUOTE_UNPROVABLE" in row.payload["exclusion_reasons"]


def test_result_materialization_settles_fade_at_frozen_channel_price() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[RecommendationReviewLedgerModel.__table__, ResultModel.__table__],
    )
    at = datetime(2026, 9, 26, 8, tzinfo=UTC)
    source = {
        "candidate_kind": TRACK_D_FADE,
        "fixture_id": "api_football:123",
        "market": "TOTALS",
        "selection": "OVER",
        "exact_line": "2.5",
        "decimal_odds_channel": 1.92,
        "market_quote_identity": "m" * 64,
        "channel_quote_identity": "36-OVER",
        "evaluated_at": at.isoformat(),
        "first_quote_captured_at": (at - timedelta(minutes=1)).isoformat(),
        "kickoff_utc": (at + timedelta(hours=2)).isoformat(),
    }
    with Session(engine) as session:
        session.add(RecommendationReviewLedgerModel(
            review_event_id="a" * 64,
            evaluation_id="e",
            event_type="DECISION_SNAPSHOT",
            evaluated_at=at,
            pit_status="PROVABLE",
            payload=source,
            payload_sha256="a" * 64,
            created_at=at,
        ))
        session.add(ResultModel(
            fixture_id="api_football:123",
            home_goals=2,
            away_goals=1,
            result_status="FT",
            confirmed_at=at + timedelta(hours=3),
            source_payload_sha256="b" * 64,
            result_hash="c" * 64,
        ))
        session.commit()

        assert settle_track_d_validation_signals_in_session(
            session, now=at + timedelta(hours=2, minutes=30)
        ) == {"signals": 1, "settled": 0}
        report = settle_track_d_validation_signals_in_session(
            session, now=at + timedelta(hours=3)
        )
        assert report == {"signals": 1, "settled": 1}
        settled = session.query(RecommendationReviewLedgerModel).filter_by(
            event_type="SETTLEMENT_OBSERVED"
        ).one()
        assert settled.payload["settlement"] == "WIN"
        assert settled.payload["profit_units_channel"] == pytest.approx(0.92)
        assert settled.payload["rebate_units_channel"] == pytest.approx(0.023)
        assert settled.payload["profit_units_channel_with_rebate"] == pytest.approx(0.943)
        session.commit()
        assert settle_track_d_validation_signals_in_session(
            session, now=at + timedelta(hours=4)
        ) == {"signals": 0, "settled": 0}


def test_track_d_fade_tripwire_enforces_pinnacle_anchor() -> None:
    from w2.domain.profit import FROZEN_FADE_DELTA, track_d_fair_probability
    from w2.tracking.forward_evidence import _assert_track_d_fade_not_intent_gated

    odds = {"OVER": 1.9, "UNDER": 2.0}
    p_over = track_d_fair_probability(odds, "OVER")
    p_fade = min(0.99, max(0.01, p_over + FROZEN_FADE_DELTA))

    # A correct Pinnacle-anchored fade passes the tripwire.
    _assert_track_d_fade_not_intent_gated(odds, p_fade)

    # Any other probability source (e.g. an intent-gate output) is forbidden.
    with pytest.raises(
        AssertionError, match="TRACK_D_FADE_MUST_USE_PINNACLE_ANCHOR"
    ):
        _assert_track_d_fade_not_intent_gated(odds, 0.5)
