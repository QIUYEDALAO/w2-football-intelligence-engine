from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, inspect, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from w2.domain.canonical_serialization import HashDomain, canonical_sha256
from w2.domain.enums import SettlementOutcome
from w2.domain.odds import settle_total_goals
from w2.infrastructure.database import create_engine
from w2.infrastructure.persistence.future_refresh_models import (
    TeamXgMatchModel,
    TeamXgRollingSnapshotModel,
)
from w2.infrastructure.persistence.model_forecast_models import (
    ModelForecastCaptureDataVersionModel,
    ModelForecastCaptureModel,
    ModelForecastOutcomeModel,
    model_forecast_fixture_aliases,
)
from w2.infrastructure.persistence.models import ResultModel
from w2.ingestion.future_refresh_repository import FutureRefreshDbRepository

CAPTURE_SCHEMA = "w2.model_forecast_capture.v2"
OUTCOME_SCHEMA = "w2.model_forecast_outcome.v2"
MODEL_FAMILY = "EXACT_DC_POISSON"
CAPTURE_POLICY = "FIRST_ELIGIBLE_FREEZE_IMMUTABLE"
TERMINAL_RESULT_STATUSES = frozenset({"FT", "AET", "PEN"})
OUTCOME_CLASSES = ("HOME", "DRAW", "AWAY")
LEAD_TIME_BUCKETS = ("LT_6H", "H6_TO_LT_24H", "D1_TO_D3", "GT_3D")
MODEL_FORECAST_CAPTURE_HASH_DOMAIN = HashDomain.FUTURE_REFRESH_EVIDENCE
MODEL_FORECAST_OUTCOME_HASH_DOMAIN = HashDomain.OUTCOME_LEDGER_PAYLOAD
MODEL_FORECAST_XG_IDENTITY_HASH_DOMAIN = HashDomain.FUTURE_REFRESH_FIXTURE_IDENTITY
MODEL_FORECAST_INPUT_MANIFEST_HASH_DOMAIN = HashDomain.FUTURE_REFRESH_EVIDENCE


class ModelForecastLedgerError(ValueError):
    pass


def model_forecast_lead_time_bucket(lead_time_seconds: int) -> str:
    if lead_time_seconds < 0:
        raise ModelForecastLedgerError("MODEL_FORECAST_LEAD_TIME_NEGATIVE")
    if lead_time_seconds < 6 * 60 * 60:
        return "LT_6H"
    if lead_time_seconds < 24 * 60 * 60:
        return "H6_TO_LT_24H"
    if lead_time_seconds <= 3 * 24 * 60 * 60:
        return "D1_TO_D3"
    return "GT_3D"


def _mean(values: Iterable[float]) -> float | None:
    rows = list(values)
    return sum(rows) / len(rows) if rows else None


class ModelForecastLedgerRepository:
    def __init__(self, engine: Engine | None = None) -> None:
        self.engine = engine or create_engine()
        self.xg_repository = FutureRefreshDbRepository(engine=self.engine)

    def capture(
        self,
        day_view: Mapping[str, Any],
        *,
        captured_at: datetime | None = None,
        dry_run: bool = True,
        write_db: bool = False,
    ) -> dict[str, Any]:
        if dry_run and write_db:
            raise ModelForecastLedgerError("write_db requires dry_run=false")
        now = _utc(captured_at or datetime.now(UTC), "captured_at")
        cards = _cards(day_view)
        coverage_eligible_count = 0
        model_eligible_count = 0
        no_four_field_xg_count = 0
        written = 0
        already_captured = 0
        captures: list[dict[str, Any]] = []
        with Session(self.engine) as session:
            team_xg_match_count = int(
                session.scalar(select(func.count()).select_from(TeamXgMatchModel)) or 0
            )
            data_version = f"TEAM_XG_MATCH_ROWS_{team_xg_match_count}"
            for card in cards:
                kickoff = _parse_time(card.get("kickoff_utc"))
                fixture_id = str(card.get("fixture_id") or "")
                competition_id = str(card.get("competition_id") or "")
                if not fixture_id or not competition_id or kickoff is None or now >= kickoff:
                    continue
                coverage_eligible_count += 1
                simulation = _ready_simulation(card)
                if simulation is None:
                    continue
                xg_identity = self._four_field_xg_identity(
                    session,
                    card=card,
                    fixture_id=fixture_id,
                    kickoff=kickoff,
                )
                if xg_identity is None:
                    no_four_field_xg_count += 1
                    continue
                capture = _build_capture(
                    card=card,
                    simulation=simulation,
                    xg_identity=xg_identity,
                    captured_at=now,
                )
                model_eligible_count += 1
                existing = session.scalar(
                    select(ModelForecastCaptureModel).where(
                        ModelForecastCaptureModel.fixture_id == fixture_id,
                        ModelForecastCaptureModel.model_family == capture["model_family"],
                        ModelForecastCaptureModel.model_version == capture["model_version"],
                    )
                )
                if existing is not None:
                    already_captured += 1
                    continue
                captures.append(capture)
                if write_db:
                    session.add(_capture_model(capture, inserted_at=now))
                    # The version row has a restrictive FK but no ORM relationship;
                    # flush the immutable parent before inserting its sidecar.
                    session.flush()
                    session.add(
                        ModelForecastCaptureDataVersionModel(
                            capture_identity_hash=str(capture["capture_identity_hash"]),
                            data_version=data_version,
                            team_xg_match_count=team_xg_match_count,
                            evidence_source="RECORDED_AT_CAPTURE",
                            recorded_at=now,
                        )
                    )
                    written += 1
            session.commit() if write_db else session.rollback()
        return {
            "schema_version": "w2.model_forecast_capture_run.v1",
            "status": "PASS",
            "dry_run": dry_run,
            "write_db": write_db,
            "provider_calls": 0,
            "db_writes": written,
            "coverage_eligible_count": coverage_eligible_count,
            "model_eligible_count": model_eligible_count,
            "model_forecast_capture_count": len(captures),
            "already_captured_count": already_captured,
            "no_four_field_xg_count": no_four_field_xg_count,
            "data_version": data_version,
            "team_xg_match_count": team_xg_match_count,
            "shadow_candidate_count": _shadow_candidate_count(cards),
            "captures": captures if dry_run else [],
        }

    def xg_ready_fixture_ids(
        self,
        cards: Sequence[Mapping[str, Any]],
    ) -> tuple[str, ...]:
        ready: list[str] = []
        with Session(self.engine) as session:
            for card in cards:
                fixture_id = str(card.get("fixture_id") or "")
                kickoff = _parse_time(card.get("kickoff_utc"))
                if (
                    fixture_id
                    and kickoff is not None
                    and self._four_field_xg_identity(
                        session,
                        card=card,
                        fixture_id=fixture_id,
                        kickoff=kickoff,
                    )
                    is not None
                ):
                    ready.append(fixture_id)
        return tuple(ready)

    def captured_fixture_ids(self) -> tuple[str, ...]:
        with Session(self.engine) as session:
            rows = session.scalars(
                select(ModelForecastCaptureModel.fixture_id).order_by(
                    ModelForecastCaptureModel.kickoff_utc,
                    ModelForecastCaptureModel.fixture_id,
                )
            )
            return tuple(
                dict.fromkeys(str(value).removeprefix("api_football:") for value in rows)
            )

    def denominator_capture_seeds(self) -> tuple[tuple[str, str, str, datetime], ...]:
        """Return immutable inputs needed to record every capture in the market denominator."""
        with Session(self.engine) as session:
            rows = session.execute(
                select(
                    ModelForecastCaptureModel.fixture_id,
                    ModelForecastCaptureModel.capture_identity_hash,
                    ModelForecastCaptureModel.model_input_manifest_hash,
                    ModelForecastCaptureModel.captured_at,
                ).order_by(
                    ModelForecastCaptureModel.kickoff_utc,
                    ModelForecastCaptureModel.fixture_id,
                )
            )
            return tuple(
                (
                    str(fixture_id).removeprefix("api_football:"),
                    str(capture_hash),
                    str(model_input_hash),
                    captured_at,
                )
                for fixture_id, capture_hash, model_input_hash, captured_at in rows
            )

    def schema_ready(self) -> bool:
        tables = set(inspect(self.engine).get_table_names())
        return {
            "model_forecast_capture",
            "model_forecast_capture_data_version",
            "model_forecast_outcome",
        } <= tables

    def settle(
        self,
        *,
        fixture_ids: Sequence[str] | None = None,
        settled_at: datetime | None = None,
        dry_run: bool = True,
        write_db: bool = False,
    ) -> dict[str, Any]:
        if dry_run and write_db:
            raise ModelForecastLedgerError("write_db requires dry_run=false")
        now = _utc(settled_at or datetime.now(UTC), "settled_at")
        selected = {str(value) for value in fixture_ids or () if str(value)}
        outcomes: list[dict[str, Any]] = []
        written = 0
        with Session(self.engine) as session:
            statement = select(ModelForecastCaptureModel).order_by(
                ModelForecastCaptureModel.kickoff_utc,
                ModelForecastCaptureModel.capture_identity_hash,
            )
            if selected:
                aliases = {alias for value in selected for alias in _fixture_aliases(value)}
                statement = statement.where(ModelForecastCaptureModel.fixture_id.in_(aliases))
            captures = list(session.scalars(statement))
            results = {
                alias: row
                for row in session.scalars(select(ResultModel))
                for alias in _fixture_aliases(row.fixture_id)
            }
            for capture in captures:
                if (
                    session.scalar(
                        select(ModelForecastOutcomeModel).where(
                            ModelForecastOutcomeModel.capture_identity_hash
                            == capture.capture_identity_hash
                        )
                    )
                    is not None
                ):
                    continue
                result = next(
                    (results.get(alias) for alias in _fixture_aliases(capture.fixture_id)),
                    None,
                )
                if result is None or result.result_status not in TERMINAL_RESULT_STATUSES:
                    continue
                capture_payload = dict(capture.payload)
                capture_payload.setdefault("lead_time_seconds", capture.lead_time_seconds)
                capture_payload.setdefault("lead_time_bucket", capture.lead_time_bucket)
                outcome = _build_outcome(capture_payload, result=result, settled_at=now)
                outcomes.append(outcome)
                if write_db:
                    session.add(_outcome_model(outcome, inserted_at=now))
                    written += 1
            session.commit() if write_db else session.rollback()
        return {
            "schema_version": "w2.model_forecast_settlement_run.v1",
            "status": "PASS" if outcomes else "NO_DUE_WORK",
            "dry_run": dry_run,
            "write_db": write_db,
            "provider_calls": 0,
            "db_writes": written,
            "model_forecast_settled_count": len(outcomes),
            "probability_metrics_sample_count": len(outcomes),
            "outcomes": outcomes if dry_run else [],
        }

    def counts(self) -> dict[str, int]:
        with Session(self.engine) as session:
            captures = len(list(session.scalars(select(ModelForecastCaptureModel))))
            outcomes = len(list(session.scalars(select(ModelForecastOutcomeModel))))
        return {
            "model_forecast_capture_count": captures,
            "model_forecast_settled_count": outcomes,
            "probability_metrics_sample_count": outcomes,
        }

    def metric_summary_by_data_version_and_lead_time(self) -> dict[str, Any]:
        with Session(self.engine) as session:
            captures = list(session.scalars(select(ModelForecastCaptureModel)))
            versions = list(session.scalars(select(ModelForecastCaptureDataVersionModel)))
            outcomes = list(session.scalars(select(ModelForecastOutcomeModel)))
        version_by_capture = {row.capture_identity_hash: row for row in versions}
        rows: dict[str, dict[str, list[ModelForecastOutcomeModel]]] = {}
        counts: dict[str, int | None] = {}
        for capture in captures:
            version = version_by_capture.get(capture.capture_identity_hash)
            name = version.data_version if version is not None else "LEGACY_UNVERSIONED"
            rows.setdefault(name, {bucket: [] for bucket in LEAD_TIME_BUCKETS})
            counts[name] = version.team_xg_match_count if version is not None else None
        for outcome in outcomes:
            version = version_by_capture.get(outcome.capture_identity_hash)
            name = version.data_version if version is not None else "LEGACY_UNVERSIONED"
            rows.setdefault(name, {bucket: [] for bucket in LEAD_TIME_BUCKETS})
            counts[name] = version.team_xg_match_count if version is not None else None
            if outcome.lead_time_bucket in rows[name]:
                rows[name][outcome.lead_time_bucket].append(outcome)
        return {
            name: {
                "team_xg_match_count": counts[name],
                "lead_time_buckets": {
                    bucket: {
                        "sample_count": len(bucket_rows),
                        "mean_brier": _mean(row.brier for row in bucket_rows),
                        "mean_log_loss": _mean(row.log_loss for row in bucket_rows),
                        "mean_rps": _mean(row.rps for row in bucket_rows),
                    }
                    for bucket, bucket_rows in version_rows.items()
                },
            }
            for name, version_rows in sorted(rows.items())
        }

    def integrity(self) -> dict[str, Any]:
        invalid_captures: list[str] = []
        invalid_outcomes: list[str] = []
        rederivability: list[dict[str, Any]] = []
        with Session(self.engine) as session:
            captures = list(session.scalars(select(ModelForecastCaptureModel)))
            versions = list(session.scalars(select(ModelForecastCaptureDataVersionModel)))
            outcomes = list(session.scalars(select(ModelForecastOutcomeModel)))
            results = list(session.scalars(select(ResultModel)))
            for capture_row in captures:
                frozen_xg = _mapping(_mapping(capture_row.payload).get("four_field_xg_identity"))
                current_xg = self._four_field_xg_identity(
                    session,
                    card={
                        "frozen_artifact_provenance": {
                            "fixture_identity": dict(_mapping(frozen_xg.get("fixture_identity")))
                        }
                    },
                    fixture_id=capture_row.fixture_id,
                    kickoff=capture_row.kickoff_utc,
                    home_team_id_override=str(
                        _mapping(frozen_xg.get("home")).get("team_id") or ""
                    ),
                    away_team_id_override=str(
                        _mapping(frozen_xg.get("away")).get("team_id") or ""
                    ),
                )
                rederivability.append(
                    {
                        "capture_identity_hash": capture_row.capture_identity_hash,
                        "fixture_id": capture_row.fixture_id,
                        "REDERIVABLE_FROM_CURRENT_DB": current_xg is not None
                        and current_xg.get("identity_hash")
                        == capture_row.four_field_xg_identity_hash,
                        "REDERIVABILITY_CLASS": _rederivability_class(
                            frozen_xg,
                            current_xg,
                            frozen_hash=capture_row.four_field_xg_identity_hash,
                        ),
                    }
                )
        captures_by_hash = {row.capture_identity_hash: row for row in captures}
        version_by_capture = {row.capture_identity_hash: row for row in versions}
        results_by_hash = {row.result_hash: row for row in results}
        for capture_row in captures:
            payload = dict(capture_row.payload)
            identity_payload = {
                key: value for key, value in payload.items() if key != "capture_identity_hash"
            }
            valid = (
                capture_row.captured_at < capture_row.kickoff_utc
                and _utc(capture_row.kickoff_utc, "kickoff_utc")
                == _parse_time(payload.get("kickoff_utc"))
                and _utc(capture_row.captured_at, "captured_at")
                == _parse_time(payload.get("captured_at"))
                and capture_row.lead_time_seconds
                == int((capture_row.kickoff_utc - capture_row.captured_at).total_seconds())
                and capture_row.lead_time_bucket
                == model_forecast_lead_time_bucket(capture_row.lead_time_seconds)
                and capture_row.payload_sha256
                == canonical_sha256(payload, domain=MODEL_FORECAST_CAPTURE_HASH_DOMAIN)
                and capture_row.capture_identity_hash
                == canonical_sha256(
                    identity_payload,
                    domain=MODEL_FORECAST_CAPTURE_HASH_DOMAIN,
                )
                and payload.get("candidate_required") is False
                and payload.get("exact_quote_required") is False
            )
            if not valid:
                invalid_captures.append(capture_row.capture_identity_hash)
        for outcome_row in outcomes:
            payload = dict(outcome_row.payload)
            identity_payload = {
                key: value
                for key, value in payload.items()
                if key not in {"capture_to_outcome_identity_hash", "outcome_identity_hash"}
            }
            expected_identity = canonical_sha256(
                identity_payload,
                domain=MODEL_FORECAST_OUTCOME_HASH_DOMAIN,
            )
            result_row = results_by_hash.get(outcome_row.authoritative_result_identity)
            valid = (
                outcome_row.capture_identity_hash in captures_by_hash
                and _utc(outcome_row.settled_at, "settled_at")
                == _parse_time(payload.get("settled_at"))
                and result_row is not None
                and payload.get("final_score")
                == {
                    "home": result_row.home_goals,
                    "away": result_row.away_goals,
                    "status": result_row.result_status,
                }
                and outcome_row.lead_time_seconds
                == captures_by_hash[outcome_row.capture_identity_hash].lead_time_seconds
                and outcome_row.lead_time_bucket
                == captures_by_hash[outcome_row.capture_identity_hash].lead_time_bucket
                and outcome_row.payload_sha256
                == canonical_sha256(payload, domain=MODEL_FORECAST_OUTCOME_HASH_DOMAIN)
                and outcome_row.outcome_identity_hash == expected_identity
                and payload.get("capture_to_outcome_identity_hash") == expected_identity
            )
            if not valid:
                invalid_outcomes.append(outcome_row.outcome_identity_hash)
        return {
            "invalid_capture_count": len(invalid_captures),
            "invalid_outcome_count": len(invalid_outcomes),
            "invalid_capture_hashes": sorted(invalid_captures),
            "invalid_outcome_hashes": sorted(invalid_outcomes),
            "missing_data_version_count": sum(
                row.capture_identity_hash not in version_by_capture for row in captures
            ),
            "data_version_counts": {
                version: sum(row.data_version == version for row in versions)
                for version in sorted({row.data_version for row in versions})
            },
            "rederivable_from_current_db_count": sum(
                bool(row["REDERIVABLE_FROM_CURRENT_DB"]) for row in rederivability
            ),
            "non_rederivable_from_current_db_count": sum(
                not bool(row["REDERIVABLE_FROM_CURRENT_DB"]) for row in rederivability
            ),
            "rederivability_class_counts": {
                name: sum(row["REDERIVABILITY_CLASS"] == name for row in rederivability)
                for name in sorted({row["REDERIVABILITY_CLASS"] for row in rederivability})
            },
            "capture_rederivability": sorted(
                rederivability, key=lambda row: (row["fixture_id"], row["capture_identity_hash"])
            ),
        }

    def _four_field_xg_identity(
        self,
        session: Session,
        *,
        card: Mapping[str, Any],
        fixture_id: str,
        kickoff: datetime,
        home_team_id_override: str | None = None,
        away_team_id_override: str | None = None,
    ) -> dict[str, Any] | None:
        fixture_identity = dict(
            _mapping(_mapping(card.get("frozen_artifact_provenance")).get("fixture_identity"))
        )
        home_team_id = str(
            home_team_id_override
            or fixture_identity.get("home_provider_team_id")
            or fixture_identity.get("home_team_id")
            or ""
        )
        away_team_id = str(
            away_team_id_override
            or fixture_identity.get("away_provider_team_id")
            or fixture_identity.get("away_team_id")
            or ""
        )
        if not home_team_id or not away_team_id:
            canonical_identity = self.xg_repository.matchday_fixture_identity(fixture_id)
            if (
                not isinstance(canonical_identity, Mapping)
                or canonical_identity.get("status") == "FIXTURE_ID_ALIAS_CONFLICT"
            ):
                return None
            fixture_identity = dict(canonical_identity)
            home_team_id = str(fixture_identity.get("home_provider_team_id") or "")
            away_team_id = str(fixture_identity.get("away_provider_team_id") or "")
        if not home_team_id or not away_team_id:
            return None
        fixture_aliases = _fixture_aliases(fixture_id)
        snapshots = list(
            session.scalars(
                select(TeamXgRollingSnapshotModel)
                .where(
                    TeamXgRollingSnapshotModel.as_of_fixture_id.in_(fixture_aliases),
                    TeamXgRollingSnapshotModel.team_id.in_((home_team_id, away_team_id)),
                )
                .order_by(
                    TeamXgRollingSnapshotModel.team_id,
                    TeamXgRollingSnapshotModel.as_of_time.desc(),
                )
            )
        )
        by_team: dict[str, TeamXgRollingSnapshotModel] = {}
        for snapshot in snapshots:
            by_team.setdefault(snapshot.team_id, snapshot)
        if set(by_team) != {home_team_id, away_team_id}:
            return None
        sides: dict[str, dict[str, Any]] = {}
        for side, team_id in (("home", home_team_id), ("away", away_team_id)):
            snapshot = by_team[team_id]
            components = list(
                session.scalars(
                    select(TeamXgMatchModel)
                    .where(
                        TeamXgMatchModel.team_id == team_id,
                        TeamXgMatchModel.kickoff_at < kickoff,
                        TeamXgMatchModel.captured_at < kickoff,
                    )
                    .order_by(TeamXgMatchModel.kickoff_at.desc())
                    .limit(snapshot.match_count)
                )
            )
            if len(components) != snapshot.match_count or not components:
                return None
            component_rows = [
                {
                    "identity": row.id,
                    "fixture_id": row.fixture_id,
                    "kickoff_at": _iso(row.kickoff_at),
                    "captured_at": _iso(row.captured_at),
                    "xg_for": row.xg_for,
                    "xg_against": row.xg_against,
                    "raw_statistics_sha256": row.raw_payload_sha256,
                }
                for row in reversed(components)
            ]
            if not _rolling_values_match(snapshot, component_rows):
                return None
            side_identity = {
                "snapshot_identity": snapshot.snapshot_id,
                "team_id": team_id,
                "as_of_fixture_id": snapshot.as_of_fixture_id,
                "as_of": _iso(snapshot.as_of_time),
                "match_count": snapshot.match_count,
                "xg_for": snapshot.rolling_xg_for,
                "xg_against": snapshot.rolling_xg_against,
                "component_team_xg_matches": component_rows,
            }
            side_identity["identity_hash"] = canonical_sha256(
                side_identity,
                domain=MODEL_FORECAST_XG_IDENTITY_HASH_DOMAIN,
            )
            sides[side] = side_identity
        identity: dict[str, Any] = {
            "fixture_identity": fixture_identity,
            "home": sides["home"],
            "away": sides["away"],
            "four_fields": {
                "home_xg_for": sides["home"]["xg_for"],
                "home_xg_against": sides["home"]["xg_against"],
                "away_xg_for": sides["away"]["xg_for"],
                "away_xg_against": sides["away"]["xg_against"],
            },
        }
        identity["identity_hash"] = canonical_sha256(
            identity,
            domain=MODEL_FORECAST_XG_IDENTITY_HASH_DOMAIN,
        )
        return identity


def run_model_forecast_capture(
    day_view: Mapping[str, Any],
    *,
    repository: ModelForecastLedgerRepository | None = None,
    captured_at: datetime | None = None,
    dry_run: bool = True,
    write_db: bool = False,
) -> dict[str, Any]:
    return (repository or ModelForecastLedgerRepository()).capture(
        day_view,
        captured_at=captured_at,
        dry_run=dry_run,
        write_db=write_db,
    )


def settle_model_forecasts(
    *,
    repository: ModelForecastLedgerRepository | None = None,
    fixture_ids: Sequence[str] | None = None,
    settled_at: datetime | None = None,
    dry_run: bool = True,
    write_db: bool = False,
) -> dict[str, Any]:
    return (repository or ModelForecastLedgerRepository()).settle(
        fixture_ids=fixture_ids,
        settled_at=settled_at,
        dry_run=dry_run,
        write_db=write_db,
    )


def _build_capture(
    *,
    card: Mapping[str, Any],
    simulation: Mapping[str, Any],
    xg_identity: Mapping[str, Any],
    captured_at: datetime,
) -> dict[str, Any]:
    summary = _mapping(simulation.get("score_matrix_summary"))
    probability_vector = {
        "HOME": _probability(summary.get("home_win")),
        "DRAW": _probability(summary.get("draw")),
        "AWAY": _probability(summary.get("away_win")),
    }
    _validate_probability_vector(probability_vector)
    score_matrix_hash = _sha(summary.get("score_matrix_hash"), "score_matrix_hash")
    provenance = _mapping(card.get("frozen_artifact_provenance"))
    fixture_identity = _mapping(xg_identity.get("fixture_identity")) or _mapping(
        provenance.get("fixture_identity")
    )
    fixture_raw_hash = fixture_identity.get("raw_payload_sha256") or provenance.get("source_hash")
    input_manifest = {
        "frozen_input_manifest": dict(_mapping(provenance.get("input_manifest"))),
        "fixture_identity_hash": fixture_identity.get("identity_hash"),
        "fixture_raw_payload_sha256": fixture_raw_hash,
        "simulation_input_hash": _mapping(simulation.get("calibration")).get(
            "simulation_input_hash"
        ),
        "four_field_xg_identity_hash": xg_identity.get("identity_hash"),
    }
    model_input_manifest_hash = canonical_sha256(
        input_manifest,
        domain=MODEL_FORECAST_INPUT_MANIFEST_HASH_DOMAIN,
    )
    source_hashes = _source_artifact_hashes(
        card=card,
        simulation=simulation,
        xg_identity=xg_identity,
        model_input_manifest_hash=model_input_manifest_hash,
    )
    _validate_source_artifact_hashes(source_hashes)
    fixture_id = str(card.get("fixture_id") or "")
    competition_id = str(card.get("competition_id") or "")
    kickoff = _parse_time(card.get("kickoff_utc"))
    if not fixture_id or not competition_id or kickoff is None or captured_at >= kickoff:
        raise ModelForecastLedgerError("MODEL_FORECAST_CAPTURE_NOT_PREMATCH")
    lead_time_seconds = int((kickoff - captured_at).total_seconds())
    lead_time_bucket = model_forecast_lead_time_bucket(lead_time_seconds)
    core = {
        "schema_version": CAPTURE_SCHEMA,
        "fixture_identity": {
            **dict(fixture_identity),
            "fixture_id": fixture_id,
        },
        "competition_identity": {"competition_id": competition_id},
        "kickoff_utc": _iso(kickoff),
        "captured_at": _iso(captured_at),
        "lead_time_seconds": lead_time_seconds,
        "lead_time_bucket": lead_time_bucket,
        "capture_policy": CAPTURE_POLICY,
        "model_family": MODEL_FAMILY,
        "model_version": str(simulation.get("model_version") or ""),
        "calibration_version": _required_text(
            simulation.get("calibration_version"), "calibration_version"
        ),
        "calibration_status": _required_text(
            simulation.get("calibration_status"), "calibration_status"
        ),
        "model_input_manifest_hash": model_input_manifest_hash,
        "four_field_xg_identity": dict(xg_identity),
        "probability_vector": probability_vector,
        "ah_settlement_distributions": _ah_settlement_distributions(simulation),
        "ou_settlement_distributions": _ou_settlement_distributions(simulation),
        "score_matrix_hash": score_matrix_hash,
        "source_artifact_hashes": source_hashes,
        "candidate_required": False,
        "exact_quote_required": False,
        "validation_scope": "MODEL_FORECAST_ONLY",
    }
    if not core["model_version"]:
        raise ModelForecastLedgerError("MODEL_FORECAST_MODEL_VERSION_MISSING")
    identity = canonical_sha256(core, domain=MODEL_FORECAST_CAPTURE_HASH_DOMAIN)
    return {**core, "capture_identity_hash": identity}


def _build_outcome(
    capture: Mapping[str, Any],
    *,
    result: ResultModel,
    settled_at: datetime,
) -> dict[str, Any]:
    vector = {
        key: float(value) for key, value in _mapping(capture.get("probability_vector")).items()
    }
    _validate_probability_vector(vector)
    actual = (
        "HOME"
        if result.home_goals > result.away_goals
        else "AWAY"
        if result.home_goals < result.away_goals
        else "DRAW"
    )
    observed = {key: 1.0 if key == actual else 0.0 for key in OUTCOME_CLASSES}
    brier = sum((vector[key] - observed[key]) ** 2 for key in OUTCOME_CLASSES)
    log_loss = -math.log(max(min(vector[actual], 1 - 1e-15), 1e-15))
    cumulative_probability = 0.0
    cumulative_observed = 0.0
    rps_terms = []
    for key in OUTCOME_CLASSES[:-1]:
        cumulative_probability += vector[key]
        cumulative_observed += observed[key]
        rps_terms.append((cumulative_probability - cumulative_observed) ** 2)
    rps = sum(rps_terms) / len(rps_terms)
    confidence_class = max(OUTCOME_CLASSES, key=lambda key: (vector[key], key))
    result_identity = _sha(result.result_hash, "authoritative_result_identity")
    lead_time_seconds = int(capture["lead_time_seconds"])
    lead_time_bucket = model_forecast_lead_time_bucket(lead_time_seconds)
    core = {
        "schema_version": OUTCOME_SCHEMA,
        "capture_identity_hash": capture.get("capture_identity_hash"),
        "fixture_id": result.fixture_id,
        "authoritative_result_identity": result_identity,
        "final_score": {
            "home": result.home_goals,
            "away": result.away_goals,
            "status": result.result_status,
        },
        "actual_outcome": actual,
        "brier": round(brier, 12),
        "log_loss": round(log_loss, 12),
        "rps": round(rps, 12),
        "lead_time_seconds": lead_time_seconds,
        "lead_time_bucket": lead_time_bucket,
        "ece_input": {
            "predicted_class": confidence_class,
            "confidence": vector[confidence_class],
            "actual_class": actual,
            "correct": confidence_class == actual,
        },
        "settled_at": _iso(settled_at),
    }
    link = canonical_sha256(core, domain=MODEL_FORECAST_OUTCOME_HASH_DOMAIN)
    return {
        **core,
        "capture_to_outcome_identity_hash": link,
        "outcome_identity_hash": link,
    }


def _capture_model(
    payload: Mapping[str, Any], *, inserted_at: datetime
) -> ModelForecastCaptureModel:
    return ModelForecastCaptureModel(
        capture_identity_hash=str(payload["capture_identity_hash"]),
        fixture_id=str(_mapping(payload["fixture_identity"])["fixture_id"]),
        competition_id=str(_mapping(payload["competition_identity"])["competition_id"]),
        kickoff_utc=_utc(_parse_time(payload["kickoff_utc"]), "kickoff_utc"),
        captured_at=_utc(_parse_time(payload["captured_at"]), "captured_at"),
        lead_time_seconds=int(payload["lead_time_seconds"]),
        lead_time_bucket=str(payload["lead_time_bucket"]),
        model_family=str(payload["model_family"]),
        model_version=str(payload["model_version"]),
        model_input_manifest_hash=str(payload["model_input_manifest_hash"]),
        four_field_xg_identity_hash=str(
            _mapping(payload["four_field_xg_identity"])["identity_hash"]
        ),
        score_matrix_hash=str(payload["score_matrix_hash"]),
        payload=dict(payload),
        payload_sha256=canonical_sha256(payload, domain=MODEL_FORECAST_CAPTURE_HASH_DOMAIN),
        inserted_at=inserted_at,
    )


def _outcome_model(
    payload: Mapping[str, Any], *, inserted_at: datetime
) -> ModelForecastOutcomeModel:
    return ModelForecastOutcomeModel(
        outcome_identity_hash=str(payload["outcome_identity_hash"]),
        capture_identity_hash=str(payload["capture_identity_hash"]),
        fixture_id=str(payload["fixture_id"]),
        authoritative_result_identity=str(payload["authoritative_result_identity"]),
        brier=float(payload["brier"]),
        log_loss=float(payload["log_loss"]),
        rps=float(payload["rps"]),
        lead_time_seconds=int(payload["lead_time_seconds"]),
        lead_time_bucket=str(payload["lead_time_bucket"]),
        settled_at=_utc(_parse_time(payload["settled_at"]), "settled_at"),
        payload=dict(payload),
        payload_sha256=canonical_sha256(payload, domain=MODEL_FORECAST_OUTCOME_HASH_DOMAIN),
        inserted_at=inserted_at,
    )


def _ou_settlement_distributions(simulation: Mapping[str, Any]) -> dict[str, Any]:
    matrix = _score_matrix(simulation)
    ladder = _mapping(simulation.get("ou_probabilities")).get("ladder")
    if not matrix or not isinstance(ladder, list):
        raise ModelForecastLedgerError("MODEL_FORECAST_OU_DISTRIBUTION_MISSING")
    rows = []
    for item in ladder:
        if not isinstance(item, Mapping):
            continue
        line = Decimal(str(item.get("line")))
        rows.append(
            {
                "line": float(line),
                "over_settlement_distribution": _totals_distribution(matrix, "OVER", line),
                "under_settlement_distribution": _totals_distribution(matrix, "UNDER", line),
            }
        )
    return {"ladder": rows}


def _ah_settlement_distributions(simulation: Mapping[str, Any]) -> dict[str, Any]:
    probabilities = _mapping(simulation.get("ah_probabilities"))
    ladder = probabilities.get("ladder")
    if not isinstance(ladder, list) or not ladder:
        raise ModelForecastLedgerError("MODEL_FORECAST_AH_DISTRIBUTION_MISSING")
    for item in ladder:
        row = _mapping(item)
        for side in ("home", "away"):
            distribution = _mapping(row.get(f"{side}_settlement_distribution"))
            if set(distribution) != {outcome.value for outcome in SettlementOutcome}:
                raise ModelForecastLedgerError("MODEL_FORECAST_AH_DISTRIBUTION_INVALID")
            if abs(sum(float(value) for value in distribution.values()) - 1.0) > 1e-5:
                raise ModelForecastLedgerError("MODEL_FORECAST_AH_DISTRIBUTION_INVALID")
    return dict(probabilities)


def _totals_distribution(
    matrix: Mapping[tuple[int, int], float],
    selection: str,
    line: Decimal,
) -> dict[str, float]:
    values = {outcome.value: 0.0 for outcome in SettlementOutcome}
    for (home, away), probability in matrix.items():
        outcome = settle_total_goals(home + away, selection, line)
        values[outcome.value] += probability
    return {key: round(value, 12) for key, value in values.items()}


def _score_matrix(simulation: Mapping[str, Any]) -> dict[tuple[int, int], float]:
    rows = _mapping(simulation.get("score_matrix_summary")).get("distribution")
    if not isinstance(rows, list):
        return {}
    return {
        (int(row["home_goals"]), int(row["away_goals"])): float(row["probability"])
        for row in rows
        if isinstance(row, Mapping)
    }


def _source_artifact_hashes(
    *,
    card: Mapping[str, Any],
    simulation: Mapping[str, Any],
    xg_identity: Mapping[str, Any],
    model_input_manifest_hash: str,
) -> dict[str, Any]:
    provenance = _mapping(card.get("frozen_artifact_provenance"))
    fixture_identity = _mapping(xg_identity.get("fixture_identity")) or _mapping(
        provenance.get("fixture_identity")
    )
    fixture_identity_hash = fixture_identity.get("identity_hash") or canonical_sha256(
        fixture_identity,
        domain=MODEL_FORECAST_INPUT_MANIFEST_HASH_DOMAIN,
    )
    fixture_raw_hash = fixture_identity.get("raw_payload_sha256") or provenance.get("source_hash")
    raw_hashes = sorted(
        {
            str(component["raw_statistics_sha256"])
            for side in ("home", "away")
            for component in _mapping_list(
                _mapping(xg_identity.get(side)).get("component_team_xg_matches")
            )
        }
    )
    return {
        "frozen_artifact_hash": provenance.get("artifact_hash") or card.get("artifact_hash"),
        "frozen_source_hash": provenance.get("source_hash"),
        "fixture_identity_hash": fixture_identity_hash,
        "fixture_raw_payload_sha256": fixture_raw_hash,
        "simulation_input_hash": _mapping(simulation.get("calibration")).get(
            "simulation_input_hash"
        ),
        "score_matrix_hash": _mapping(simulation.get("score_matrix_summary")).get(
            "score_matrix_hash"
        ),
        "model_input_manifest_hash": model_input_manifest_hash,
        "four_field_xg_identity_hash": xg_identity.get("identity_hash"),
        "raw_statistics_sha256": raw_hashes,
    }


def _validate_source_artifact_hashes(hashes: Mapping[str, Any]) -> None:
    for name in (
        "fixture_identity_hash",
        "fixture_raw_payload_sha256",
        "simulation_input_hash",
        "score_matrix_hash",
        "model_input_manifest_hash",
        "four_field_xg_identity_hash",
    ):
        _sha(hashes.get(name), name)
    for name in ("frozen_artifact_hash", "frozen_source_hash"):
        if hashes.get(name) is not None:
            _sha(hashes.get(name), name)
    raw_hashes = hashes.get("raw_statistics_sha256")
    if not isinstance(raw_hashes, list) or not raw_hashes:
        raise ModelForecastLedgerError("MODEL_FORECAST_RAW_STATISTICS_HASHES_MISSING")
    for raw_hash in raw_hashes:
        _sha(raw_hash, "raw_statistics_sha256")


def _rolling_values_match(
    snapshot: TeamXgRollingSnapshotModel,
    components: Sequence[Mapping[str, Any]],
) -> bool:
    count = len(components)
    xg_for = sum(float(row["xg_for"]) for row in components) / count
    xg_against = sum(float(row["xg_against"]) for row in components) / count
    return (
        abs(round(xg_for, 4) - snapshot.rolling_xg_for) < 1e-9
        and abs(round(xg_against, 4) - snapshot.rolling_xg_against) < 1e-9
    )


def _rederivability_class(
    frozen: Mapping[str, Any],
    current: Mapping[str, Any] | None,
    *,
    frozen_hash: str,
) -> str:
    if current is None:
        return "CURRENT_DB_UNAVAILABLE"
    if current.get("identity_hash") == frozen_hash:
        return "CURRENT_DB_MATCH"
    if _mapping(frozen.get("four_fields")) != _mapping(current.get("four_fields")):
        return "FOUR_FIELD_VALUE_DRIFT"
    if _without_rederivability_metadata(frozen) == _without_rederivability_metadata(current):
        return "AS_OF_TIME_RELABEL_ONLY"
    return "IDENTITY_METADATA_DRIFT"


def _without_rederivability_metadata(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: _without_rederivability_metadata(item)
            for key, item in value.items()
            if key not in {"as_of", "identity_hash"}
        }
    if isinstance(value, list):
        return [_without_rederivability_metadata(item) for item in value]
    return value


def _ready_simulation(card: Mapping[str, Any]) -> Mapping[str, Any] | None:
    envelope = _mapping(card.get("simulation"))
    simulation = _mapping(envelope.get("simulation"))
    return (
        simulation
        if envelope.get("status") == "READY" and simulation.get("status") == "READY"
        else None
    )


def _cards(day_view: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    cards = day_view.get("cards")
    return [item for item in cards if isinstance(item, Mapping)] if isinstance(cards, list) else []


def _shadow_candidate_count(cards: Sequence[Mapping[str, Any]]) -> int:
    return sum(
        1
        for card in cards
        if card.get("decision_tier") == "ANALYSIS_PICK" and card.get("outcome_tracked") is True
    )


def _validate_probability_vector(vector: Mapping[str, float]) -> None:
    if set(vector) != set(OUTCOME_CLASSES) or any(
        value < 0 or value > 1 for value in vector.values()
    ):
        raise ModelForecastLedgerError("MODEL_FORECAST_PROBABILITY_VECTOR_INVALID")
    if abs(sum(vector.values()) - 1.0) > 1e-5:
        raise ModelForecastLedgerError("MODEL_FORECAST_PROBABILITY_VECTOR_NOT_NORMALIZED")


def _probability(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ModelForecastLedgerError("MODEL_FORECAST_PROBABILITY_MISSING") from exc


def _required_text(value: Any, name: str) -> str:
    resolved = str(value or "").strip()
    if not resolved:
        raise ModelForecastLedgerError(f"MODEL_FORECAST_{name.upper()}_MISSING")
    return resolved


def _sha(value: Any, name: str) -> str:
    text = str(value or "").lower()
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise ModelForecastLedgerError(f"MODEL_FORECAST_{name.upper()}_INVALID")
    return text


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _mapping_list(value: Any) -> list[Mapping[str, Any]]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _utc(value: datetime | None, name: str) -> datetime:
    if value is None:
        raise ModelForecastLedgerError(f"{name} missing")
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


def _iso(value: datetime) -> str:
    return _utc(value, "datetime").isoformat().replace("+00:00", "Z")


def _fixture_aliases(value: str) -> tuple[str, ...]:
    return model_forecast_fixture_aliases(value)
