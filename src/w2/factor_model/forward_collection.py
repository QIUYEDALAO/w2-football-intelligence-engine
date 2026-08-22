from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine as sqlalchemy_create_engine
from sqlalchemy import event, func, inspect, or_, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from w2.competitions.registry import CompetitionRegistry
from w2.domain.canonical_serialization import HashDomain, canonical_sha256
from w2.domain.factor_shadow_v2 import (
    FactorShadowSourceMode,
    factor_shadow_forecast_contract,
)
from w2.factor_model.ablation_scoring import build_b0_b1_b2_ablation
from w2.factor_model.history import (
    API_FOOTBALL_TEAM_ID_NAMESPACE,
    build_pit_history_manifest,
    materialize_factor_history_from_persisted_raw,
)
from w2.factor_model.pit_dataset import NORMALIZED_FEATURE_SCHEMA_VERSION
from w2.factor_model.pit_features import RecursiveRatingPolicy, build_pit_feature_snapshot
from w2.features.xg_materialization import XG_METHOD_VERSION
from w2.infrastructure.database import create_engine
from w2.infrastructure.persistence.dynamic_prematch_models import (
    CandidateNotificationOutboxModel,
    DynamicPrematchEvaluationModel,
    DynamicPrematchOpportunityModel,
)
from w2.infrastructure.persistence.factor_shadow_models import (
    FactorShadowForecastCaptureModel,
)
from w2.infrastructure.persistence.future_refresh_models import RawPayloadModel
from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayCheckpointPlanModel,
    MatchdayEndpointCaptureModel,
)
from w2.infrastructure.persistence.model_forecast_models import (
    ModelForecastCaptureModel,
    ModelForecastOutcomeModel,
    model_forecast_fixture_aliases,
)
from w2.infrastructure.persistence.models import ResultModel
from w2.infrastructure.persistence.outcome_ledger_models import OutcomeLedgerModel
from w2.matchday.intake_v2 import REQUIRED_MATCHDAY_COMPETITIONS

FORWARD_COLLECTION_SCHEMA_VERSION = "w2.factor_model.forward_collection_run.v1"
FORWARD_COLLECTION_ARTIFACT_SCHEMA_VERSION = (
    "w2.factor_model.forward_collection_artifact.v1"
)
FORWARD_COLLECTION_ROLE = "w2_factor_shadow_v2_writer"
FORWARD_MODEL_FAMILY = "factor_model_v2"
FORWARD_MODEL_VERSION = "factor-v2.f3-f7.forward-collection.v1"
ACTIVE_FACTORS = ("F3_REST_FITNESS", "F7_STRENGTH_FORM")
NEAR_CHECKPOINTS = (
    "T60_ODDS",
    "T45_ODDS",
    "T-30m_VALIDATION_LOCK",
    "T15_ODDS",
)
V2_WRITABLE_TABLES = frozenset(
    {
        "factor_shadow_forecast_capture",
        "factor_shadow_market_opportunity",
        "factor_shadow_market_attempt",
        "factor_shadow_forecast_outcome",
        "factor_shadow_v2_admission",
    }
)
PROTECTED_V1_MODELS = (
    ModelForecastCaptureModel,
    ModelForecastOutcomeModel,
    DynamicPrematchOpportunityModel,
    DynamicPrematchEvaluationModel,
    CandidateNotificationOutboxModel,
    OutcomeLedgerModel,
    MatchdayEndpointCaptureModel,
    MatchdayCheckpointPlanModel,
    RawPayloadModel,
    ResultModel,
)
RATING_POLICY = RecursiveRatingPolicy(
    version="factor-v2.elo-1500-k20-ha60-r400.v1",
    initial_rating=1500.0,
    k_factor=20.0,
    home_advantage_rating=60.0,
    rating_scale=400.0,
)


@dataclass(frozen=True, kw_only=True)
class ForwardCollectionConfig:
    enabled: bool
    control_file: Path
    artifact_path: Path
    preregistration_path: Path
    report_dir: Path
    daily_state_file: Path
    quiet_horizon_seconds: int = 3600

    @classmethod
    def from_environment(cls) -> ForwardCollectionConfig:
        root = Path(__file__).resolve().parents[3]
        return cls(
            enabled=os.getenv("W2_FACTOR_V2_FORWARD_COLLECTION_ENABLED", "false").lower()
            == "true",
            control_file=Path(
                os.getenv(
                    "W2_FACTOR_V2_FORWARD_COLLECTION_CONTROL_FILE",
                    "/app/runtime/factor-v2/enabled",
                )
            ),
            artifact_path=Path(
                os.getenv(
                    "W2_FACTOR_V2_FORWARD_COLLECTION_ARTIFACT",
                    str(
                        root
                        / "config/calibration/"
                        "factor_model_v2.f3_f7.forward_collection_only.json"
                    ),
                )
            ),
            preregistration_path=Path(
                os.getenv(
                    "W2_FACTOR_V2_FORWARD_PREREGISTRATION",
                    str(
                        root
                        / "docs/operations/"
                        "FACTOR_V2_FORWARD_COLLECTION_PREREGISTRATION_20260822.json"
                    ),
                )
            ),
            report_dir=Path(
                os.getenv(
                    "W2_FACTOR_V2_FORWARD_COLLECTION_REPORT_DIR",
                    "/app/runtime/factor-v2/reports",
                )
            ),
            daily_state_file=Path(
                os.getenv(
                    "W2_FACTOR_V2_FORWARD_COLLECTION_DAILY_STATE_FILE",
                    "/app/runtime/factor-v2/last-success-utc-date",
                )
            ),
            quiet_horizon_seconds=int(
                os.getenv("W2_FACTOR_V2_QUIET_HORIZON_SECONDS", "3600")
            ),
        )


class _PersistedRawRepository:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def raw_payloads(self, endpoint: str) -> list[dict[str, Any]]:
        return self.rows if endpoint == "fixtures" else []


def run_forward_collection(
    *,
    config: ForwardCollectionConfig | None = None,
    engine: Engine | None = None,
    writer_engine: Engine | None = None,
    computed_at: datetime | None = None,
    write_db: bool = False,
) -> dict[str, Any]:
    resolved = config or ForwardCollectionConfig.from_environment()
    now = _utc(computed_at or datetime.now(UTC), "computed_at")
    preregistration, preregistration_file_sha256 = _load_preregistration(
        resolved.preregistration_path
    )
    artifact = _load_collection_artifact(resolved.artifact_path)
    switch = _switch_state(resolved)
    base = {
        "schema_version": FORWARD_COLLECTION_SCHEMA_VERSION,
        "computed_at": _iso(now),
        "captured_at_semantics": "EXACT_V1_PRODUCTION_CAPTURE_TIMESTAMP",
        "feature_as_of_semantics": "EXACT_V1_PRODUCTION_CAPTURE_TIMESTAMP",
        "preregistration_file_sha256": preregistration_file_sha256,
        "collection_artifact_sha256": artifact["artifact_sha256"],
        "provider_calls": 0,
        "production_worker_used": False,
        "candidate_output_count": 0,
        "notification_output_count": 0,
        "official_profit_and_loss_output_count": 0,
        "switch": switch,
    }
    if not switch["enabled"]:
        return {**base, "status": "COLLECTION_DISABLED", "database_writes": 0}
    if _already_collected_today(resolved.daily_state_file, now):
        return {**base, "status": "ALREADY_COLLECTED_TODAY", "database_writes": 0}

    reader_engine = engine or create_engine()
    restricted_writer_engine = writer_engine or (
        reader_engine
        if reader_engine.dialect.name != "postgresql"
        else sqlalchemy_create_engine(reader_engine.url, pool_pre_ping=True)
    )
    _install_read_only_session(reader_engine)
    _install_restricted_role(restricted_writer_engine)
    role_audit = _role_audit(restricted_writer_engine)
    if not role_audit["pass"]:
        _disable_switch(resolved.control_file)
        return {
            **base,
            "status": "ROLE_ISOLATION_FAILED_COLLECTION_DISABLED",
            "database_writes": 0,
            "role_audit": role_audit,
        }

    with Session(reader_engine) as session:
        quiet_window = _quiet_window_audit(
            session,
            now=now,
            horizon=timedelta(seconds=resolved.quiet_horizon_seconds),
        )
        if not quiet_window["pass"]:
            return {
                **base,
                "status": "DEFERRED_FOR_V1_CHECKPOINT_SLOT",
                "database_writes": 0,
                "role_audit": role_audit,
                "quiet_window": quiet_window,
            }

    provider_league_authority = _provider_league_authority(reader_engine)
    base = {
        **base,
        "provider_league_authority_sha256": provider_league_authority[
            "authority_sha256"
        ],
    }
    with Session(reader_engine) as session:
        before = _daily_self_attestation(session, now=now)
        captures = _eligible_captures(
            session,
            computed_at=now,
            not_before=_utc(
                preregistration["forward_cohort"][
                    "production_capture_captured_at_not_before"
                ],
                "production_capture_captured_at_not_before",
            ),
            historical_replay_cutoff=_utc(
                preregistration["historical_replay_cutoff"],
                "historical_replay_cutoff",
            ),
        )
        raw_repository = _PersistedRawRepository(
            [
                {
                    "sha256": row.sha256,
                    "captured_at": _db_utc(row.captured_at, "raw_captured_at"),
                    "payload": row.payload,
                }
                for row in session.scalars(
                    select(RawPayloadModel)
                    .where(RawPayloadModel.endpoint == "fixtures")
                    .order_by(RawPayloadModel.captured_at, RawPayloadModel.sha256)
                )
            ]
        )

    forecasts: list[dict[str, Any]] = []
    exclusions: dict[str, int] = {}
    leakage_violation_count = 0
    written = 0
    stopped_by_switch = False
    write_error_type: str | None = None
    for capture in captures:
        if not _switch_state(resolved)["enabled"]:
            stopped_by_switch = True
            break
        try:
            forecast = _build_forward_forecast(
                capture=capture,
                raw_repository=raw_repository,
                artifact=artifact,
                provider_league_authority=provider_league_authority,
                preregistration_file_sha256=preregistration_file_sha256,
                computed_at=now,
            )
        except ValueError as exc:
            reason = str(exc).split(":", 1)[0]
            exclusions[reason] = exclusions.get(reason, 0) + 1
            if "LEAKAGE" in reason or "AFTER_FEATURE_ASOF" in reason:
                leakage_violation_count += 1
            continue
        forecasts.append(forecast)
        if write_db:
            try:
                with Session(restricted_writer_engine) as session:
                    session.add(_forecast_model(forecast))
                    session.commit()
                    written += 1
            except Exception as exc:
                write_error_type = type(exc).__name__
                break

    with Session(reader_engine) as session:
        after = _daily_self_attestation(session, now=now)
    anomalies = _attestation_anomalies(before, after)
    if leakage_violation_count:
        anomalies.append("POINT_IN_TIME_LEAKAGE_VIOLATION")
    if write_error_type:
        anomalies.append(f"V2_WRITE_FAILED:{write_error_type}")
    if anomalies:
        _disable_switch(resolved.control_file)
    status = (
        "ANOMALY_COLLECTION_DISABLED"
        if anomalies
        else "COLLECTION_STOPPED_BY_SWITCH"
        if stopped_by_switch
        else "PASS"
    )
    if status == "PASS" and write_db:
        _record_daily_success(resolved.daily_state_file, now)
    return {
        **base,
        "status": status,
        "write_db": write_db,
        "database_writes": written,
        "new_rows": {"factor_shadow_forecast_capture": written},
        "eligible_v1_capture_count": len(captures),
        "computed_forecast_count": len(forecasts),
        "exclusions": dict(sorted(exclusions.items())),
        "point_in_time_leakage_violation_count": leakage_violation_count,
        "stopped_by_switch": stopped_by_switch,
        "write_error_type": write_error_type,
        "role_audit": role_audit,
        "quiet_window": quiet_window,
        "daily_self_attestation_before": before,
        "daily_self_attestation_after": after,
        "anomalies": anomalies,
        "forecasts": forecasts if not write_db else [],
    }


def _eligible_captures(
    session: Session,
    *,
    computed_at: datetime,
    not_before: datetime,
    historical_replay_cutoff: datetime,
) -> list[ModelForecastCaptureModel]:
    existing = select(FactorShadowForecastCaptureModel.production_capture_identity_hash).where(
        FactorShadowForecastCaptureModel.source_mode
        == FactorShadowSourceMode.FORWARD_SHADOW.value,
        FactorShadowForecastCaptureModel.production_capture_identity_hash.is_not(None),
    )
    return list(
        session.scalars(
            select(ModelForecastCaptureModel)
            .where(
                ModelForecastCaptureModel.captured_at >= not_before,
                ModelForecastCaptureModel.captured_at <= computed_at,
                ModelForecastCaptureModel.kickoff_utc >= historical_replay_cutoff,
                ModelForecastCaptureModel.captured_at < ModelForecastCaptureModel.kickoff_utc,
                ModelForecastCaptureModel.capture_identity_hash.not_in(existing),
            )
            .order_by(
                ModelForecastCaptureModel.captured_at,
                ModelForecastCaptureModel.capture_identity_hash,
            )
        )
    )


def _build_forward_forecast(
    *,
    capture: ModelForecastCaptureModel,
    raw_repository: _PersistedRawRepository,
    artifact: dict[str, Any],
    provider_league_authority: dict[str, Any],
    preregistration_file_sha256: str,
    computed_at: datetime,
) -> dict[str, Any]:
    payload = dict(capture.payload)
    xg_identity = _mapping(payload.get("four_field_xg_identity"))
    fixture_identity = _mapping(xg_identity.get("fixture_identity"))
    home = _mapping(xg_identity.get("home"))
    away = _mapping(xg_identity.get("away"))
    four_fields = _mapping(xg_identity.get("four_fields"))
    home_team_id = str(home.get("team_id") or fixture_identity.get("home_provider_team_id") or "")
    away_team_id = str(away.get("team_id") or fixture_identity.get("away_provider_team_id") or "")
    provider_league_identity = _provider_league_identity(
        competition_id=capture.competition_id,
        xg_fixture_identity=fixture_identity,
        authority=provider_league_authority,
    )
    provider_league_id = provider_league_identity["provider_league_id"]
    if not home_team_id or not away_team_id or not provider_league_id:
        raise ValueError("FORWARD_CAPTURE_PROVIDER_IDENTITY_MISSING")
    _verify_xg_components(
        xg_identity,
        target_fixture_id=capture.fixture_id,
        target_kickoff=_db_utc(capture.kickoff_utc, "kickoff_utc"),
        feature_as_of=_db_utc(capture.captured_at, "captured_at"),
    )
    try:
        xg_values = {
            key: float(four_fields[key])
            for key in (
                "home_xg_for",
                "home_xg_against",
                "away_xg_for",
                "away_xg_against",
            )
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("FORWARD_CAPTURE_FOUR_FIELD_XG_MISSING") from exc

    feature_as_of = _db_utc(capture.captured_at, "captured_at")
    kickoff = _db_utc(capture.kickoff_utc, "kickoff_utc")
    corpus = materialize_factor_history_from_persisted_raw(
        raw_repository,
        kickoff_from=datetime(2022, 1, 1, tzinfo=UTC),
        kickoff_to=kickoff,
        as_of=feature_as_of,
        provider_league_id=provider_league_id,
    )
    manifest = build_pit_history_manifest(
        corpus.history_rows,
        target_fixture_id=capture.fixture_id,
        target_kickoff=kickoff,
        feature_as_of=feature_as_of,
        team_identity_namespace=API_FOOTBALL_TEAM_ID_NAMESPACE,
    )
    snapshot = build_pit_feature_snapshot(
        manifest,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        team_identity_namespace=API_FOOTBALL_TEAM_ID_NAMESPACE,
        rating_policy=RATING_POLICY,
    )
    normalized = _normalize(snapshot, artifact["preprocessing"])
    b1_identity = canonical_sha256(
        {
            "identity_type": "FACTOR_V2_FORWARD_B1_RECOMPUTED_INPUT",
            "production_capture_identity_hash": capture.capture_identity_hash,
            "four_field_xg_identity_hash": xg_identity.get("identity_hash"),
        },
        domain=HashDomain.PREMATCH_READ_MODEL_GENERIC,
    )
    baseline_lambda_home, baseline_lambda_away = _baseline_lambdas(xg_values)
    baseline = build_b0_b1_b2_ablation(
        fixture_id=capture.fixture_id,
        **xg_values,
        b1_lambda_home=baseline_lambda_home,
        b1_lambda_away=baseline_lambda_away,
        b1_input_identity_hash=b1_identity,
        normalized_features=normalized,
        factor_calibration=artifact["factor_calibration"],
        b1_track_id="B1_RECOMPUTED",
    )
    b2 = baseline["tracks"]["B2_FACTOR_V2"]
    pit_input_identity_hash = canonical_sha256(
        {
            "identity_type": "FACTOR_V2_FORWARD_PIT_INPUT",
            "production_capture_identity_hash": capture.capture_identity_hash,
            "feature_snapshot_sha256": snapshot["feature_snapshot_sha256"],
            "normalized_features_sha256": normalized["normalized_features_sha256"],
            "xg_identity_hash": xg_identity.get("identity_hash"),
            "provider_league_identity_sha256": provider_league_identity[
                "identity_sha256"
            ],
            "collection_artifact_sha256": artifact["artifact_sha256"],
            "preregistration_file_sha256": preregistration_file_sha256,
        },
        domain=HashDomain.PREMATCH_READ_MODEL_GENERIC,
    )
    contract = factor_shadow_forecast_contract(
        fixture_id=capture.fixture_id,
        model_family=FORWARD_MODEL_FAMILY,
        model_version=FORWARD_MODEL_VERSION,
        feature_registry_version=artifact["feature_registry_version"],
        calibration_version=artifact["factor_calibration"]["calibration_version"],
        pit_input_identity_hash=pit_input_identity_hash,
        captured_at=feature_as_of,
        feature_as_of=feature_as_of,
        computed_at=computed_at,
        source_mode=FactorShadowSourceMode.FORWARD_SHADOW,
        production_capture_identity_hash=capture.capture_identity_hash,
        production_captured_at=feature_as_of,
    )
    body = _json_safe({
        **contract,
        "competition_id": capture.competition_id,
        "kickoff_utc": kickoff,
        "lambda_home": b2["lambda_home"],
        "lambda_away": b2["lambda_away"],
        "score_matrix_hash": b2["score_matrix_sha256"],
        "tracks": baseline["tracks"],
        "feature_snapshot": snapshot,
        "normalized_features": normalized,
        "pit_history_manifest_sha256": manifest["manifest_sha256"],
        "pit_source_fixture_count": manifest["source_fixture_count"],
        "pit_excluded_fixture_counts": manifest["excluded_fixture_counts"],
        "provider_league_identity": provider_league_identity,
        "collection_only": True,
        "gate1_status": "FAIL",
        "gate2_status": "CLOSED",
        "candidate_eligible": False,
        "notification_eligible": False,
        "official_profit_and_loss_eligible": False,
        "preregistration_file_sha256": preregistration_file_sha256,
        "collection_artifact_sha256": artifact["artifact_sha256"],
    })
    return {
        **body,
        "payload_sha256": canonical_sha256(
            body, domain=HashDomain.PREMATCH_READ_MODEL_GENERIC
        ),
    }


def _baseline_lambdas(values: dict[str, float]) -> tuple[float, float]:
    from w2.strategy.calibration import calibrate_lambdas

    output = calibrate_lambdas(
        home_xg_for=values["home_xg_for"],
        home_xg_against=values["home_xg_against"],
        away_xg_for=values["away_xg_for"],
        away_xg_against=values["away_xg_against"],
        home_elo=None,
        away_elo=None,
        home_squad_value_eur=None,
        away_squad_value_eur=None,
    )
    return output.lambda_home, output.lambda_away


def _provider_league_identity(
    *,
    competition_id: str,
    xg_fixture_identity: dict[str, Any],
    authority: dict[str, Any],
) -> dict[str, str]:
    mapping = _mapping(authority.get("mapping"))
    policy_league_id = mapping.get(str(competition_id))
    xg_league_id = str(xg_fixture_identity.get("provider_league_id") or "")
    if not policy_league_id:
        raise ValueError("FORWARD_CAPTURE_COMPETITION_NOT_WHITELISTED")
    if xg_league_id and xg_league_id != policy_league_id:
        raise ValueError("FORWARD_CAPTURE_PROVIDER_LEAGUE_ID_CONFLICT")
    body = {
        "competition_id": str(competition_id),
        "provider": "api_football",
        "provider_league_id": policy_league_id,
        "source": "W2_COMPETITION_DB_AUTHORITY",
        "authority_sha256": str(authority["authority_sha256"]),
    }
    return {
        **body,
        "identity_sha256": canonical_sha256(
            {"identity_type": "FORWARD_PROVIDER_LEAGUE_IDENTITY", **body},
            domain=HashDomain.PREMATCH_READ_MODEL_GENERIC,
        ),
    }


def _provider_league_authority(engine: Engine) -> dict[str, Any]:
    entries = CompetitionRegistry(engine).entries()
    rows = []
    for competition_id in sorted(REQUIRED_MATCHDAY_COMPETITIONS):
        entry = entries.get(competition_id)
        mapping = entry.provider_mapping if entry is not None else {}
        provider = str(mapping.get("provider") or "")
        provider_league_id = str(mapping.get("api_football_league_id") or "")
        if entry is None or provider != "api_football" or not provider_league_id:
            raise ValueError("FORWARD_COLLECTION_COMPETITION_DB_AUTHORITY_INCOMPLETE")
        rows.append(
            {
                "competition_id": competition_id,
                "provider": provider,
                "provider_league_id": provider_league_id,
                "season": entry.season,
                "config_hash": entry.config_hash,
            }
        )
    body = {
        "source": "W2_COMPETITION_DB_AUTHORITY",
        "required_competition_count": len(REQUIRED_MATCHDAY_COMPETITIONS),
        "entries": rows,
    }
    return {
        **body,
        "mapping": {
            str(row["competition_id"]): str(row["provider_league_id"])
            for row in rows
        },
        "authority_sha256": canonical_sha256(
            {"identity_type": "FORWARD_PROVIDER_LEAGUE_AUTHORITY", **body},
            domain=HashDomain.PREMATCH_READ_MODEL_GENERIC,
        ),
    }


def _normalize(snapshot: dict[str, Any], preprocessing: dict[str, Any]) -> dict[str, Any]:
    factors: dict[str, dict[str, Any]] = {}
    for factor_id in ACTIVE_FACTORS:
        factor = snapshot["factors"][factor_id]
        parameter = preprocessing["parameters"][factor_id]
        missing = factor.get("missing") is True or factor.get("raw_value") is None
        raw = float(parameter["mean"] if missing else factor["raw_value"])
        factors[factor_id] = {
            "status": "READY",
            "raw_value": factor.get("raw_value"),
            "normalized_value": (raw - float(parameter["mean"]))
            / float(parameter["standard_deviation"]),
            "missing_indicator": int(missing),
            "imputation_applied": missing,
        }
    body = {
        "schema_version": NORMALIZED_FEATURE_SCHEMA_VERSION,
        "target_fixture_id": snapshot["target_fixture_id"],
        "feature_snapshot_sha256": snapshot["feature_snapshot_sha256"],
        "preprocessing_sha256": preprocessing["preprocessing_sha256"],
        "factors": factors,
        "numeric_effect_enabled": False,
    }
    return {
        **body,
        "normalized_features_sha256": canonical_sha256(
            {"identity_type": "NORMALIZED_FEATURES", **body},
            domain=HashDomain.PREMATCH_READ_MODEL_GENERIC,
        ),
    }


def _verify_xg_components(
    identity: dict[str, Any],
    *,
    target_fixture_id: str,
    target_kickoff: datetime,
    feature_as_of: datetime,
) -> None:
    target_aliases = set(model_forecast_fixture_aliases(target_fixture_id))
    for side in ("home", "away"):
        components = _mapping(identity.get(side)).get("component_team_xg_matches")
        if not isinstance(components, list) or not components:
            raise ValueError("FORWARD_XG_COMPONENTS_MISSING")
        for row in components:
            if not isinstance(row, dict):
                raise ValueError("FORWARD_XG_COMPONENT_INVALID")
            if str(row.get("fixture_id")) in target_aliases:
                raise ValueError("FORWARD_XG_TARGET_FIXTURE_LEAKAGE")
            if _utc(row.get("kickoff_at"), "xg_kickoff_at") >= target_kickoff:
                raise ValueError("FORWARD_XG_KICKOFF_LEAKAGE")
            if _utc(row.get("captured_at"), "xg_captured_at") >= feature_as_of:
                raise ValueError("FORWARD_XG_CAPTURE_AFTER_FEATURE_ASOF")


def _forecast_model(payload: dict[str, Any]) -> FactorShadowForecastCaptureModel:
    return FactorShadowForecastCaptureModel(
        forecast_identity_hash=payload["forecast_identity_hash"],
        fixture_id=payload["fixture_id"],
        competition_id=payload["competition_id"],
        production_capture_identity_hash=payload["production_capture_identity_hash"],
        kickoff_utc=_utc(payload["kickoff_utc"], "kickoff_utc"),
        captured_at=_utc(payload["captured_at"], "captured_at"),
        feature_as_of=_utc(payload["feature_as_of"], "feature_as_of"),
        computed_at=_utc(payload["computed_at"], "computed_at"),
        source_mode=payload["source_mode"],
        model_family=payload["model_family"],
        model_version=payload["model_version"],
        feature_registry_version=payload["feature_registry_version"],
        calibration_version=payload["calibration_version"],
        pit_input_identity_hash=payload["pit_input_identity_hash"],
        lambda_home=float(payload["lambda_home"]),
        lambda_away=float(payload["lambda_away"]),
        score_matrix_hash=payload["score_matrix_hash"],
        probability_method=payload["probability_method"],
        sampling_used=False,
        payload=payload,
        payload_sha256=payload["payload_sha256"],
        inserted_at=_utc(payload["computed_at"], "computed_at"),
    )


def _daily_self_attestation(session: Session, *, now: datetime) -> dict[str, Any]:
    counts = {
        model.__tablename__: int(session.scalar(select(func.count()).select_from(model)) or 0)
        for model in PROTECTED_V1_MODELS
    }
    day_start = datetime.combine(now.date(), time.min, tzinfo=UTC)
    matured = (
        MatchdayCheckpointPlanModel.test_only.is_(False),
        MatchdayCheckpointPlanModel.checkpoint.in_(NEAR_CHECKPOINTS),
        MatchdayCheckpointPlanModel.window_end >= day_start,
        MatchdayCheckpointPlanModel.window_end <= now,
    )
    denominator = int(
        session.scalar(
            select(func.count()).select_from(MatchdayCheckpointPlanModel).where(*matured)
        )
        or 0
    )
    captured = int(
        session.scalar(
            select(func.count())
            .select_from(MatchdayCheckpointPlanModel)
            .where(*matured, MatchdayCheckpointPlanModel.status == "CAPTURED")
        )
        or 0
    )
    v2_rows_today = int(
        session.scalar(
            select(func.count())
            .select_from(FactorShadowForecastCaptureModel)
            .where(
                FactorShadowForecastCaptureModel.source_mode
                == FactorShadowSourceMode.FORWARD_SHADOW.value,
                FactorShadowForecastCaptureModel.computed_at >= day_start,
                FactorShadowForecastCaptureModel.computed_at <= now,
            )
        )
        or 0
    )
    completed_pairs = int(
        session.scalar(
            select(func.count())
            .select_from(FactorShadowForecastCaptureModel)
            .join(
                ResultModel,
                or_(
                    ResultModel.fixture_id
                    == FactorShadowForecastCaptureModel.fixture_id,
                    ResultModel.fixture_id
                    == func.replace(
                        FactorShadowForecastCaptureModel.fixture_id,
                        "api_football:",
                        "",
                    ),
                ),
            )
            .where(
                FactorShadowForecastCaptureModel.source_mode
                == FactorShadowSourceMode.FORWARD_SHADOW.value
            )
        )
        or 0
    )
    return {
        "as_of": _iso(now),
        "v1_authority_table_row_counts": counts,
        "v1_near_checkpoint_captured_rate_utc_day": {
            "captured": captured,
            "matured": denominator,
            "rate": None if denominator == 0 else round(captured / denominator, 8),
            "checkpoints": list(NEAR_CHECKPOINTS),
        },
        "v2_forward_new_rows_utc_day": v2_rows_today,
        "v2_forward_completed_pair_count": completed_pairs,
    }


def _attestation_anomalies(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    anomalies = [
        f"V1_AUTHORITY_ROW_COUNT_DECREASE:{table}"
        for table, count in before["v1_authority_table_row_counts"].items()
        if after["v1_authority_table_row_counts"][table] < count
    ]
    before_rate = before["v1_near_checkpoint_captured_rate_utc_day"]["rate"]
    after_rate = after["v1_near_checkpoint_captured_rate_utc_day"]["rate"]
    if before_rate is not None and after_rate is not None and after_rate < before_rate:
        anomalies.append("V1_NEAR_CHECKPOINT_CAPTURED_RATE_DECREASE")
    return anomalies


def _quiet_window_audit(
    session: Session, *, now: datetime, horizon: timedelta
) -> dict[str, Any]:
    rows = list(
        session.execute(
            select(
                MatchdayCheckpointPlanModel.fixture_id,
                MatchdayCheckpointPlanModel.checkpoint,
                MatchdayCheckpointPlanModel.scheduled_at,
                MatchdayCheckpointPlanModel.window_start,
                MatchdayCheckpointPlanModel.window_end,
                MatchdayCheckpointPlanModel.status,
            ).where(
                MatchdayCheckpointPlanModel.test_only.is_(False),
                MatchdayCheckpointPlanModel.status.in_(("PLANNED", "DUE")),
                or_(
                    MatchdayCheckpointPlanModel.scheduled_at.between(
                        now, now + horizon
                    ),
                    (
                        (MatchdayCheckpointPlanModel.window_start <= now + horizon)
                        & (MatchdayCheckpointPlanModel.window_end >= now)
                    ),
                ),
            )
        )
    )
    return {
        "pass": not rows,
        "checked_from": _iso(now),
        "checked_to": _iso(now + horizon),
        "formal_checkpoint_slot_count": len(rows),
        "near_checkpoint_slot_count": sum(
            str(row.checkpoint) in NEAR_CHECKPOINTS for row in rows
        ),
        "formal_checkpoint_slots": [
            {
                "fixture_id": str(row.fixture_id),
                "checkpoint": str(row.checkpoint),
                "scheduled_at": _iso(_db_utc(row.scheduled_at, "scheduled_at")),
                "window_start": _iso(_db_utc(row.window_start, "window_start")),
                "window_end": _iso(_db_utc(row.window_end, "window_end")),
                "status": str(row.status),
            }
            for row in rows
        ],
    }


def _install_restricted_role(engine: Engine) -> None:
    if engine.dialect.name != "postgresql":
        return

    @event.listens_for(engine, "begin")
    def _set_role(connection: Any) -> None:
        connection.exec_driver_sql(f"SET LOCAL ROLE {FORWARD_COLLECTION_ROLE}")


def _install_read_only_session(engine: Engine) -> None:
    if engine.dialect.name != "postgresql":
        return

    @event.listens_for(engine, "begin")
    def _set_read_only(connection: Any) -> None:
        connection.exec_driver_sql("SET TRANSACTION READ ONLY")


def _role_audit(engine: Engine) -> dict[str, Any]:
    if engine.dialect.name != "postgresql":
        return {"pass": True, "dialect": engine.dialect.name, "live_verified": False}
    with engine.connect() as connection:
        current_role = str(connection.scalar(text("select current_user")))
        role_attributes = connection.execute(
            text(
                "select rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, "
                "rolreplication, rolbypassrls "
                "from pg_roles where rolname = :role"
            ),
            {"role": FORWARD_COLLECTION_ROLE},
        ).mappings().one_or_none()
        membership = connection.execute(
            text(
                "select membership.inherit_option, membership.set_option, "
                "membership.admin_option "
                "from pg_auth_members membership "
                "join pg_roles granted_role on granted_role.oid = membership.roleid "
                "join pg_roles member_role on member_role.oid = membership.member "
                "where granted_role.rolname = :role "
                "and member_role.rolname = session_user"
            ),
            {"role": FORWARD_COLLECTION_ROLE},
        ).mappings().one_or_none()
        tables = inspect(connection).get_table_names(schema="public")
        violations: list[str] = []
        if role_attributes is None or any(role_attributes.values()):
            violations.append("ROLE_ATTRIBUTES_NOT_LEAST_PRIVILEGE")
        if (
            membership is None
            or membership["inherit_option"] is not False
            or membership["set_option"] is not True
            or membership["admin_option"] is not False
        ):
            violations.append("ROLE_MEMBERSHIP_OPTIONS_INVALID")
        for table in tables:
            privileges = {
                privilege: bool(
                    connection.scalar(
                        text("select has_table_privilege(current_user, :table, :privilege)"),
                        {"table": f"public.{table}", "privilege": privilege},
                    )
                )
                for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE")
            }
            expected_v2_privilege = table in V2_WRITABLE_TABLES
            if privileges["INSERT"] != expected_v2_privilege:
                violations.append(f"INSERT:{table}:{privileges['INSERT']}")
            if privileges["SELECT"] != expected_v2_privilege:
                violations.append(f"SELECT:{table}:{privileges['SELECT']}")
            for privilege in ("UPDATE", "DELETE", "TRUNCATE"):
                if privileges[privilege]:
                    violations.append(f"{privilege}:{table}:true")
        return {
            "pass": current_role == FORWARD_COLLECTION_ROLE and not violations,
            "dialect": "postgresql",
            "live_verified": True,
            "current_role": current_role,
            "role_attributes": dict(role_attributes or {}),
            "session_membership": dict(membership or {}),
            "v2_insert_select_table_count": len(V2_WRITABLE_TABLES),
            "inspected_public_table_count": len(tables),
            "violations": violations,
        }


def _load_collection_artifact(path: Path) -> dict[str, Any]:
    loaded: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("FORWARD_COLLECTION_ARTIFACT_INVALID")
    artifact: dict[str, Any] = loaded
    if artifact.get("schema_version") != FORWARD_COLLECTION_ARTIFACT_SCHEMA_VERSION:
        raise ValueError("FORWARD_COLLECTION_ARTIFACT_SCHEMA_INVALID")
    body = {key: value for key, value in artifact.items() if key != "artifact_sha256"}
    expected = canonical_sha256(
        {"identity_type": "FACTOR_V2_FORWARD_COLLECTION_ARTIFACT", **body},
        domain=HashDomain.PREMATCH_READ_MODEL_GENERIC,
    )
    if artifact.get("artifact_sha256") != expected:
        raise ValueError("FORWARD_COLLECTION_ARTIFACT_HASH_MISMATCH")
    if artifact.get("influence_eligible") is not False:
        raise ValueError("FORWARD_COLLECTION_INFLUENCE_MUST_BE_FALSE")
    if (
        artifact.get("xg_pit_semantics") != "SOURCE_KICKOFF_ONLY"
        or artifact.get("xg_method_version") != XG_METHOD_VERSION
    ):
        raise ValueError("FORWARD_COLLECTION_XG_METHOD_CONTRACT_INVALID")
    return artifact


def _load_preregistration(path: Path) -> tuple[dict[str, Any], str]:
    loaded: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("FORWARD_COLLECTION_PREREGISTRATION_INVALID")
    payload: dict[str, Any] = loaded
    if payload.get("owner_decision") != "COLLECTION_APPROVED_INFLUENCE_FORBIDDEN":
        raise ValueError("FORWARD_COLLECTION_PREREGISTRATION_INVALID")
    return payload, hashlib.sha256(path.read_bytes()).hexdigest()


def _switch_state(config: ForwardCollectionConfig) -> dict[str, Any]:
    value = (
        config.control_file.read_text(encoding="utf-8").strip()
        if config.control_file.is_file()
        else "MISSING"
    )
    return {
        "enabled": config.enabled and value == "ENABLED",
        "environment_enabled": config.enabled,
        "control_file": str(config.control_file),
        "control_file_value": value,
        "effective_stop_delay": "BEFORE_NEXT_FIXTURE_TRANSACTION",
    }


def _disable_switch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text("DISABLED\n", encoding="utf-8")
    temporary.replace(path)


def disable_forward_collection(config: ForwardCollectionConfig) -> None:
    _disable_switch(config.control_file)


def _already_collected_today(path: Path, now: datetime) -> bool:
    return path.is_file() and path.read_text(encoding="utf-8").strip() == now.date().isoformat()


def _record_daily_success(path: Path, now: datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(now.date().isoformat() + "\n", encoding="utf-8")
    temporary.replace(path)


def write_run_report(report: dict[str, Any], report_dir: Path) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = _utc(report["computed_at"], "computed_at").strftime("%Y%m%dT%H%M%SZ")
    path = report_dir / f"factor-v2-forward-collection-{timestamp}.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=_json_default)
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return path


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _utc(value: Any, field: str) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"FORWARD_COLLECTION_TIME_INVALID:{field}")
    return value.astimezone(UTC)


def _db_utc(value: Any, field: str) -> datetime:
    if not isinstance(value, datetime):
        return _utc(value, field)
    return (
        value.replace(tzinfo=UTC)
        if value.tzinfo is None or value.utcoffset() is None
        else value.astimezone(UTC)
    )


def _iso(value: datetime) -> str:
    return _utc(value, "time").isoformat().replace("+00:00", "Z")


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return _iso(value)
    raise TypeError(f"unsupported JSON value: {type(value)!r}")


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return _iso(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value
