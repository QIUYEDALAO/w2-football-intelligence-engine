from __future__ import annotations

import hashlib
import hmac
import os
import socket
import struct
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Any, NoReturn, cast

from sqlalchemy import DateTime, Numeric, and_, create_engine, or_, select
from sqlalchemy.engine import Connection, Engine, RowMapping
from sqlalchemy.orm import Session

from w2.domain.canonical_serialization import (
    CURRENT_SERIALIZER_VERSION,
    HashDomain,
    canonical_bytes,
    canonical_sha256,
)
from w2.infrastructure.database import Base
from w2.infrastructure.persistence.api_models import ReadModelCheckpointModel
from w2.infrastructure.persistence.dynamic_prematch_models import DynamicPrematchEvaluationModel
from w2.infrastructure.persistence.future_refresh_models import RawPayloadModel
from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayEndpointCaptureModel,
    MatchdayFixtureIdentityModel,
    MatchdayMarketObservationModel,
)
from w2.infrastructure.persistence.models import (
    ResultModel,
    StructuredLineupPlayerModel,
    StructuredLineupSnapshotModel,
)
from w2.infrastructure.persistence.outcome_ledger_models import OutcomeLedgerModel
from w2.providers.api_football import LiveApiFootballResponse
from w2.tracking.outcome_ledger_repository import business_key

ROOT = Path(__file__).resolve().parents[3]
PRIVATE_SCHEMA = ROOT / "contracts/replay/w2_real_fixture_bundle.v1.schema.json"
SANITIZED_SCHEMA = ROOT / "contracts/replay/w2_real_fixture_sanitized_manifest.v1.schema.json"
PRIVATE_MANIFEST = "manifest.private.json"
SANITIZED_MANIFEST = "manifest.sanitized.json"
PRIVATE_SCHEMA_VERSION = "w2.real-fixture-bundle.v1"
SANITIZED_SCHEMA_VERSION = "w2.real-fixture-sanitized-manifest.v1"
EXPECTED_ENDPOINTS = ("status", "fixtures", "odds", "lineups")
OUTPUT_TABLES = frozenset(
    {
        "raw_payload",
        "matchday_endpoint_captures",
        "matchday_endpoint_capture_plans",
        "matchday_market_observations",
        "matchday_fixture_identities",
        "structured_lineup_snapshots",
        "structured_lineup_players",
        "lineup_confirmed_events",
        "dynamic_prematch_evaluations",
        "dynamic_prematch_supersessions",
        "read_model_checkpoint",
        "matchday_evidence_manifests",
        "outcome_ledger",
        "results",
    }
)
CONTEXT_TABLES = (
    "league_profile",
    "league_season",
    "canonical_teams",
    "provider_team_identity_crosswalks",
    "canonical_team_match_history",
    "team_rating_snapshots",
    "team_xg_match",
    "team_xg_rolling_snapshot",
    "player_identity_mappings",
    "transfermarkt_player_references",
    "player_valuation_observations",
    "player_club_membership_observations",
    "team_lineup_baselines",
    "team_value_asof_artifacts",
)


class RealFixtureReplayError(RuntimeError):
    """The bundle cannot be exported or replayed without weakening its contract."""


class BundleIncompleteError(RealFixtureReplayError):
    def __init__(self, fixture_id: str, missing_fields: Sequence[str]) -> None:
        self.fixture_id = fixture_id
        self.missing_fields = tuple(sorted(set(missing_fields)))
        super().__init__(
            "REAL_FIXTURE_BUNDLE_INCOMPLETE:"
            f"fixture={fixture_id}:missing={','.join(self.missing_fields)}"
        )


class NetworkAccessAttempted(RealFixtureReplayError):
    pass


@dataclass(frozen=True)
class VerifiedBundle:
    root: Path
    manifest: dict[str, Any]
    files: dict[str, bytes]

    def json_file(self, relative_path: str) -> Any:
        import json

        return json.loads(self.files[relative_path])


def _schema_validate(instance: object, schema_path: Path) -> None:
    import json

    try:
        import jsonschema  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover - packaging guard
        raise RealFixtureReplayError("JSONSCHEMA_RUNTIME_REQUIRED") from exc
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = jsonschema.validators.validator_for(schema)
    validator.check_schema(schema)
    errors = sorted(validator(schema).iter_errors(instance), key=lambda item: list(item.path))
    if errors:
        first = errors[0]
        path = ".".join(str(item) for item in first.absolute_path) or "$"
        raise RealFixtureReplayError(f"BUNDLE_SCHEMA_INVALID:{path}:{first.message}")


def _canonical_file_bytes(payload: object) -> bytes:
    return canonical_bytes(payload, domain=HashDomain.FUTURE_REFRESH_EVIDENCE) + b"\n"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _bundle_id(manifest_without_id: Mapping[str, Any]) -> str:
    return canonical_sha256(
        dict(manifest_without_id),
        domain=HashDomain.FUTURE_REFRESH_EVIDENCE,
    )


def _safe_bundle_file(root: Path, relative_path: str) -> Path:
    pure = PurePosixPath(relative_path)
    if pure.is_absolute() or not pure.parts or any(part in {"", ".", ".."} for part in pure.parts):
        raise RealFixtureReplayError(f"BUNDLE_PATH_INVALID:{relative_path}")
    candidate = root.joinpath(*pure.parts)
    current = root
    for part in pure.parts:
        current = current / part
        if current.is_symlink():
            raise RealFixtureReplayError(f"BUNDLE_SYMLINK_FORBIDDEN:{relative_path}")
    try:
        candidate.resolve(strict=True).relative_to(root.resolve(strict=True))
    except (FileNotFoundError, ValueError) as exc:
        raise RealFixtureReplayError(f"BUNDLE_PATH_INVALID:{relative_path}") from exc
    if not candidate.is_file():
        raise RealFixtureReplayError(f"BUNDLE_FILE_MISSING:{relative_path}")
    return candidate


def load_verified_bundle(bundle_root: Path) -> VerifiedBundle:
    import json

    root = bundle_root.resolve(strict=True)
    manifest_path = _safe_bundle_file(root, PRIVATE_MANIFEST)
    manifest = json.loads(manifest_path.read_bytes())
    if not isinstance(manifest, dict):
        raise RealFixtureReplayError("BUNDLE_MANIFEST_NOT_OBJECT")
    _schema_validate(manifest, PRIVATE_SCHEMA)
    declared_bundle_id = str(manifest.get("bundle_id") or "")
    core = {key: value for key, value in manifest.items() if key != "bundle_id"}
    if not hmac.compare_digest(_bundle_id(core), declared_bundle_id):
        raise RealFixtureReplayError("BUNDLE_ID_MISMATCH")
    listed = [str(item["path"]) for item in manifest["files"]]
    if len(listed) != len(set(listed)):
        raise RealFixtureReplayError("BUNDLE_FILE_PATH_DUPLICATE")
    files: dict[str, bytes] = {}
    for receipt in manifest["files"]:
        relative_path = str(receipt["path"])
        data = _safe_bundle_file(root, relative_path).read_bytes()
        if len(data) != int(receipt["size_bytes"]):
            raise RealFixtureReplayError(f"BUNDLE_FILE_SIZE_MISMATCH:{relative_path}")
        if not hmac.compare_digest(_sha256(data), str(receipt["sha256"])):
            raise RealFixtureReplayError(f"BUNDLE_FILE_HASH_MISMATCH:{relative_path}")
        files[relative_path] = data
    from w2.ingestion.future_refresh import sha256_payload

    for ordinal, request in enumerate(manifest["requests"], start=1):
        if request["ordinal"] != ordinal or request["endpoint"] != EXPECTED_ENDPOINTS[ordinal - 1]:
            raise RealFixtureReplayError("REPLAY_REQUEST_SEQUENCE_INVALID")
        raw_payload = json.loads(files[str(request["payload_path"])])
        if not isinstance(raw_payload, dict):
            raise RealFixtureReplayError("REPLAY_RAW_PAYLOAD_NOT_OBJECT")
        raw_record = {
            **raw_payload,
            "parameters": request["params"],
            "endpoint": request["endpoint"],
        }
        actual_raw_sha = sha256_payload(
            raw_record,
            domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD,
        )
        if not hmac.compare_digest(actual_raw_sha, str(request["raw_payload_sha256"])):
            raise RealFixtureReplayError(f"REPLAY_RAW_PAYLOAD_HASH_MISMATCH:{request['endpoint']}")
    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name not in {PRIVATE_MANIFEST, SANITIZED_MANIFEST}
    }
    if actual != set(listed):
        raise RealFixtureReplayError("BUNDLE_FILE_SET_MISMATCH")
    sanitized_path = root / SANITIZED_MANIFEST
    if sanitized_path.exists():
        sanitized = json.loads(sanitized_path.read_bytes())
        _schema_validate(sanitized, SANITIZED_SCHEMA)
        if sanitized.get("bundle_id") != declared_bundle_id:
            raise RealFixtureReplayError("SANITIZED_MANIFEST_BUNDLE_ID_MISMATCH")
    return VerifiedBundle(root=root, manifest=manifest, files=files)


def _deny_network(*_args: object, **_kwargs: object) -> NoReturn:
    raise NetworkAccessAttempted("NETWORK_ACCESS_DURING_REAL_FIXTURE_REPLAY")


@contextmanager
def network_disabled() -> Iterator[None]:
    original = {
        "connect": socket.socket.connect,
        "connect_ex": socket.socket.connect_ex,
        "create_connection": socket.create_connection,
        "getaddrinfo": socket.getaddrinfo,
    }
    previous = os.environ.get("W2_PROVIDER_CALLS_DISABLED")
    os.environ["W2_PROVIDER_CALLS_DISABLED"] = "true"
    socket.socket.connect = cast(Any, _deny_network)  # type: ignore[method-assign]
    socket.socket.connect_ex = cast(Any, _deny_network)  # type: ignore[method-assign]
    socket.create_connection = cast(Any, _deny_network)
    socket.getaddrinfo = cast(Any, _deny_network)
    try:
        yield
    finally:
        socket.socket.connect = cast(Any, original["connect"])  # type: ignore[method-assign]
        socket.socket.connect_ex = cast(Any, original["connect_ex"])  # type: ignore[method-assign]
        socket.create_connection = cast(Any, original["create_connection"])
        socket.getaddrinfo = cast(Any, original["getaddrinfo"])
        if previous is None:
            os.environ.pop("W2_PROVIDER_CALLS_DISABLED", None)
        else:
            os.environ["W2_PROVIDER_CALLS_DISABLED"] = previous


class BundleProviderClient:
    """Strict saved-response port; it has no network implementation."""

    def __init__(self, bundle: VerifiedBundle) -> None:
        self.bundle = bundle
        self.requests = list(bundle.manifest["requests"])
        self.ordinal = 0

    def request_live(self, endpoint: str, params: dict[str, str]) -> LiveApiFootballResponse:
        if self.ordinal >= len(self.requests):
            raise RealFixtureReplayError("REPLAY_REQUEST_SEQUENCE_EXHAUSTED")
        expected = self.requests[self.ordinal]
        if endpoint != expected["endpoint"] or params != expected["params"]:
            raise RealFixtureReplayError(
                "REPLAY_REQUEST_MISMATCH:"
                f"ordinal={self.ordinal + 1}:expected={expected['endpoint']}:{expected['params']}:"
                f"actual={endpoint}:{params}"
            )
        self.ordinal += 1
        payload = self.bundle.json_file(str(expected["payload_path"]))
        if not isinstance(payload, dict):
            raise RealFixtureReplayError("REPLAY_RAW_PAYLOAD_NOT_OBJECT")
        return LiveApiFootballResponse(
            endpoint=endpoint,
            params=params,
            status_code=int(expected["status_code"]),
            elapsed_ms=int(expected["elapsed_ms"]),
            payload=payload,
            headers={str(key): str(value) for key, value in expected["headers"].items()},
            requested_at=_parse_utc(str(expected["requested_at_utc"])),
            captured_at=_parse_utc(str(expected["captured_at_utc"])),
        )

    def assert_consumed(self) -> None:
        if self.ordinal != len(self.requests):
            raise RealFixtureReplayError(
                f"REPLAY_REQUEST_SEQUENCE_INCOMPLETE:{self.ordinal}/{len(self.requests)}"
            )


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise RealFixtureReplayError("UTC_TIMESTAMP_REQUIRED")
    return parsed.astimezone(UTC)


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _aware_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return _iso(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        raise RealFixtureReplayError("BINARY_DATABASE_VALUE_UNSUPPORTED")
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_value(item) for item in value]
    return value


def _row_dict(row: object) -> dict[str, Any]:
    state = cast(Any, row)
    return {
        column.name: _json_value(getattr(state, column.name)) for column in state.__table__.columns
    }


def _mapping_dict(row: RowMapping) -> dict[str, Any]:
    return {str(key): _json_value(value) for key, value in row.items()}


@dataclass(frozen=True)
class _ExportCandidate:
    identity: MatchdayFixtureIdentityModel
    captures: tuple[MatchdayEndpointCaptureModel, ...]
    raw_payloads: tuple[RawPayloadModel, ...]
    observations: tuple[MatchdayMarketObservationModel, ...]
    lineup_snapshots: tuple[StructuredLineupSnapshotModel, ...]
    lineup_players: tuple[StructuredLineupPlayerModel, ...]
    lineup_player_ids: tuple[str, ...]
    dynamic_evaluations: tuple[DynamicPrematchEvaluationModel, ...]
    checkpoint: ReadModelCheckpointModel | None
    projected_observations: tuple[dict[str, Any], ...]
    outcome_records: tuple[OutcomeLedgerModel, ...]
    results: tuple[ResultModel, ...]


def _read_transaction_identity(connection: Connection) -> dict[str, Any]:
    dialect = connection.dialect.name
    if dialect == "postgresql":
        connection.exec_driver_sql("BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        isolation = str(connection.exec_driver_sql("SHOW transaction_isolation").scalar_one())
        read_only = str(connection.exec_driver_sql("SHOW transaction_read_only").scalar_one())
        if read_only.lower() not in {"on", "true"}:
            raise RealFixtureReplayError("EXPORT_TRANSACTION_NOT_READ_ONLY")
        snapshot = str(connection.exec_driver_sql("SELECT txid_current_snapshot()").scalar_one())
        exported_at = connection.exec_driver_sql("SELECT transaction_timestamp()").scalar_one()
    elif dialect == "sqlite":
        connection.exec_driver_sql("PRAGMA query_only = ON")
        connection.commit()
        connection.begin()
        isolation = "SERIALIZABLE"
        read_only = "true"
        snapshot = f"sqlite:{connection.exec_driver_sql('PRAGMA data_version').scalar_one()}"
        exported_at = datetime.now(UTC)
    else:
        raise RealFixtureReplayError(f"EXPORT_DATABASE_DIALECT_UNSUPPORTED:{dialect}")
    body = {
        "database_dialect": dialect,
        "isolation_level": isolation,
        "read_only": read_only.lower() in {"on", "true"},
        "snapshot": snapshot,
        "exported_at_utc": _iso(cast(datetime, exported_at)),
    }
    return {
        "database_dialect": dialect,
        "isolation_level": isolation,
        "read_only": True,
        "snapshot_identity_sha256": canonical_sha256(
            body, domain=HashDomain.FUTURE_REFRESH_EVIDENCE
        ),
        "exported_at_utc": body["exported_at_utc"],
    }


def _identity_candidates(
    session: Session, fixture_id: str | None
) -> list[MatchdayFixtureIdentityModel]:
    query = select(MatchdayFixtureIdentityModel)
    if fixture_id:
        provider_fixture_id = fixture_id.removeprefix("api_football:")
        query = query.where(
            or_(
                MatchdayFixtureIdentityModel.fixture_id == fixture_id,
                MatchdayFixtureIdentityModel.fixture_id == f"api_football:{provider_fixture_id}",
                MatchdayFixtureIdentityModel.provider_fixture_id == provider_fixture_id,
            )
        )
    return list(
        session.scalars(query.order_by(MatchdayFixtureIdentityModel.captured_at.desc()).limit(512))
    )


def _latest_lineup_group(
    session: Session,
    fixture_ids: set[str],
) -> tuple[list[StructuredLineupSnapshotModel], list[StructuredLineupPlayerModel]]:
    rows = list(
        session.scalars(
            select(StructuredLineupSnapshotModel)
            .where(
                StructuredLineupSnapshotModel.fixture_id.in_(fixture_ids),
                StructuredLineupSnapshotModel.confirmed.is_(True),
            )
            .order_by(StructuredLineupSnapshotModel.captured_at.desc())
        )
    )
    grouped: dict[tuple[datetime, str | None], list[StructuredLineupSnapshotModel]] = {}
    for row in rows:
        grouped.setdefault((row.captured_at, row.source_capture_id), []).append(row)
    for snapshots in grouped.values():
        if len({row.team_external_id for row in snapshots}) != 2:
            continue
        snapshot_ids = [row.id for row in snapshots]
        players = list(
            session.scalars(
                select(StructuredLineupPlayerModel)
                .where(StructuredLineupPlayerModel.lineup_snapshot_id.in_(snapshot_ids))
                .order_by(
                    StructuredLineupPlayerModel.lineup_snapshot_id,
                    StructuredLineupPlayerModel.api_football_player_id,
                )
            )
        )
        starters = [row.api_football_player_id for row in players if row.starter]
        if len(starters) == 22 and len(set(starters)) == 22:
            return snapshots, players
    return [], []


def _projected_observations_in_session(
    session: Session,
    fixture_ids: set[str],
) -> list[dict[str, Any]]:
    from w2.infrastructure.persistence.market_projection_view import current_market_projection
    from w2.ingestion.future_refresh_repository import FutureRefreshDbRepository

    rows = session.execute(
        select(current_market_projection)
        .where(current_market_projection.c.fixture_id.in_(fixture_ids))
        .order_by(
            current_market_projection.c.provider,
            current_market_projection.c.projection_fixture_id,
            current_market_projection.c.canonical_market,
            current_market_projection.c.bookmaker_id,
            current_market_projection.c.canonical_selection,
            current_market_projection.c.line,
            current_market_projection.c.observation_id,
        )
    ).mappings()
    return [FutureRefreshDbRepository._projection_row_dict(row) for row in rows]


def _checkpoint_for_fixture(
    session: Session,
    fixture_ids: set[str],
) -> ReadModelCheckpointModel | None:
    prefixes = tuple(f"analysis-card:shadow:v1:{value}" for value in fixture_ids)
    return session.scalar(
        select(ReadModelCheckpointModel)
        .where(ReadModelCheckpointModel.checkpoint_key.in_(prefixes))
        .order_by(ReadModelCheckpointModel.created_at.desc())
        .limit(1)
    )


def _collect_candidate(
    session: Session,
    identity: MatchdayFixtureIdentityModel,
) -> _ExportCandidate:
    provider_fixture_id = identity.provider_fixture_id
    fixture_ids = {provider_fixture_id, f"api_football:{provider_fixture_id}", identity.fixture_id}
    missing: list[str] = []
    try:
        projected = _projected_observations_in_session(session, fixture_ids)
    except Exception:
        projected = []
    checkpoint = _checkpoint_for_fixture(session, fixture_ids)
    lineup_capture = session.scalar(
        select(MatchdayEndpointCaptureModel)
        .where(
            MatchdayEndpointCaptureModel.endpoint == "lineups",
            MatchdayEndpointCaptureModel.fixture_id.in_(fixture_ids),
            MatchdayEndpointCaptureModel.response_count > 0,
            MatchdayEndpointCaptureModel.status_code.between(200, 299),
            MatchdayEndpointCaptureModel.provider_captured_at < identity.kickoff_utc,
        )
        .order_by(
            MatchdayEndpointCaptureModel.provider_captured_at.desc(),
            MatchdayEndpointCaptureModel.capture_id,
        )
        .limit(1)
    )
    if lineup_capture is None:
        missing.append("endpoint_capture.lineups.nonempty_before_kickoff")
    odds_before = (
        lineup_capture.provider_captured_at if lineup_capture is not None else identity.kickoff_utc
    )
    odds_capture = session.scalar(
        select(MatchdayEndpointCaptureModel)
        .where(
            MatchdayEndpointCaptureModel.endpoint == "odds",
            MatchdayEndpointCaptureModel.fixture_id.in_(fixture_ids),
            MatchdayEndpointCaptureModel.response_count > 0,
            MatchdayEndpointCaptureModel.status_code.between(200, 299),
            MatchdayEndpointCaptureModel.provider_captured_at <= odds_before,
        )
        .order_by(
            MatchdayEndpointCaptureModel.provider_captured_at.desc(),
            MatchdayEndpointCaptureModel.capture_id,
        )
        .limit(1)
    )
    if odds_capture is None:
        missing.append("endpoint_capture.odds")
    fixture_before = odds_capture.provider_captured_at if odds_capture is not None else odds_before
    fixture_capture: MatchdayEndpointCaptureModel | None = None
    fixture_raw: RawPayloadModel | None = None
    fixture_capture_candidates = list(
        session.scalars(
            select(MatchdayEndpointCaptureModel)
            .where(
                MatchdayEndpointCaptureModel.endpoint == "fixtures",
                MatchdayEndpointCaptureModel.status_code.between(200, 299),
                MatchdayEndpointCaptureModel.provider_captured_at <= fixture_before,
            )
            .order_by(
                MatchdayEndpointCaptureModel.provider_captured_at.desc(),
                MatchdayEndpointCaptureModel.capture_id,
            )
            .limit(128)
        )
    )
    for fixture_candidate in fixture_capture_candidates:
        raw = session.get(RawPayloadModel, fixture_candidate.raw_payload_sha256)
        response = raw.payload.get("response") if raw is not None else None
        if isinstance(response, list) and any(
            isinstance(item, Mapping)
            and str(cast(Mapping[str, Any], item.get("fixture", {})).get("id") or "")
            == provider_fixture_id
            for item in response
        ):
            fixture_capture = fixture_candidate
            fixture_raw = raw
            break
    if fixture_capture is None:
        missing.append("endpoint_capture.fixtures.same_tick_fixture_payload")
    status_before = (
        fixture_capture.provider_captured_at if fixture_capture is not None else fixture_before
    )
    status_capture = session.scalar(
        select(MatchdayEndpointCaptureModel)
        .where(
            MatchdayEndpointCaptureModel.endpoint == "status",
            MatchdayEndpointCaptureModel.status_code.between(200, 299),
            MatchdayEndpointCaptureModel.provider_captured_at <= status_before,
        )
        .order_by(
            MatchdayEndpointCaptureModel.provider_captured_at.desc(),
            MatchdayEndpointCaptureModel.capture_id,
        )
        .limit(1)
    )
    if status_capture is None:
        missing.append("endpoint_capture.status")
    captures: list[MatchdayEndpointCaptureModel | None] = [
        status_capture,
        fixture_capture,
        odds_capture,
        lineup_capture,
    ]
    capture_times = [row.provider_captured_at for row in captures if row is not None]
    if len(capture_times) == 4 and max(capture_times) - min(capture_times) > timedelta(minutes=15):
        missing.append("endpoint_capture.single_refresh_tick_15m")
    raw_payloads: list[RawPayloadModel] = []
    lineup_player_ids: list[str] = []
    for endpoint, capture in zip(EXPECTED_ENDPOINTS, captures, strict=True):
        if capture is None:
            continue
        raw = (
            fixture_raw
            if endpoint == "fixtures"
            else session.get(RawPayloadModel, capture.raw_payload_sha256)
        )
        if raw is None:
            missing.append(f"raw_payload.{endpoint}")
            continue
        if raw.endpoint != endpoint:
            missing.append(f"raw_payload.{endpoint}.endpoint_identity")
        raw_payloads.append(raw)
        if endpoint == "lineups":
            from w2.ingestion.authoritative_lineup import (
                AuthoritativeLineupError,
                validate_authoritative_lineup,
            )

            try:
                validated = validate_authoritative_lineup(
                    raw.payload.get("response"),
                    expected_team_ids=(
                        identity.home_provider_team_id,
                        identity.away_provider_team_id,
                    ),
                    captured_at=_aware_utc(capture.provider_captured_at),
                    kickoff_utc=_aware_utc(identity.kickoff_utc),
                )
                lineup_player_ids = sorted(
                    player.player_id for team in validated.teams for player in team.starters
                )
            except AuthoritativeLineupError as exc:
                missing.append(f"raw_payload.lineups.authoritative:{exc.code}")
    if len(lineup_player_ids) != 22 or len(set(lineup_player_ids)) != 22:
        missing.append("raw_payload.lineups.unique_starters_22")
    observations = (
        list(
            session.scalars(
                select(MatchdayMarketObservationModel)
                .where(MatchdayMarketObservationModel.capture_id == odds_capture.capture_id)
                .order_by(MatchdayMarketObservationModel.observation_id)
            )
        )
        if odds_capture is not None
        else []
    )
    lineup_snapshots, lineup_players = _latest_lineup_group(session, fixture_ids)
    dynamics = list(
        session.scalars(
            select(DynamicPrematchEvaluationModel)
            .where(DynamicPrematchEvaluationModel.fixture_id.in_(fixture_ids))
            .order_by(DynamicPrematchEvaluationModel.evaluation_id)
        )
    )
    if missing:
        raise BundleIncompleteError(provider_fixture_id, missing)
    outcome = list(
        session.scalars(
            select(OutcomeLedgerModel)
            .where(OutcomeLedgerModel.fixture_id.in_(fixture_ids))
            .order_by(OutcomeLedgerModel.business_key)
        )
    )
    results = list(
        session.scalars(
            select(ResultModel)
            .where(ResultModel.fixture_id.in_(fixture_ids))
            .order_by(ResultModel.result_hash)
        )
    )
    return _ExportCandidate(
        identity=identity,
        captures=cast(tuple[MatchdayEndpointCaptureModel, ...], tuple(captures)),
        raw_payloads=tuple(raw_payloads),
        observations=tuple(observations),
        lineup_snapshots=tuple(lineup_snapshots),
        lineup_players=tuple(lineup_players),
        lineup_player_ids=tuple(lineup_player_ids),
        dynamic_evaluations=tuple(dynamics),
        checkpoint=checkpoint,
        projected_observations=tuple(projected),
        outcome_records=tuple(outcome),
        results=tuple(results),
    )


def _ordered_table_rows(
    session: Session,
    table_name: str,
    where: Any,
    *,
    limit: int = 512,
) -> list[dict[str, Any]]:
    table = Base.metadata.tables[table_name]
    ordering = [column for column in table.primary_key.columns]
    query = select(table).where(where).limit(limit)
    if ordering:
        query = query.order_by(*ordering)
    return [_mapping_dict(row) for row in session.execute(query).mappings()]


def _source_context(session: Session, candidate: _ExportCandidate) -> dict[str, Any]:
    # These imports register the source tables on Base.metadata. No output row
    # is exported through this path.
    from w2.infrastructure.persistence import (  # noqa: F401  # noqa: F401
        factor_model_models,
        future_refresh_models,
        league_models,
        models,
    )

    identity = candidate.identity
    provider_team_ids = {
        identity.home_provider_team_id,
        identity.away_provider_team_id,
    }
    w2_team_ids = {value for value in (identity.home_w2_team_id, identity.away_w2_team_id) if value}
    player_ids = set(candidate.lineup_player_ids)
    competition_id = identity.competition_id
    season = identity.season
    kickoff = identity.kickoff_utc
    tables: dict[str, list[dict[str, Any]]] = {}
    table = Base.metadata.tables
    tables["league_profile"] = _ordered_table_rows(
        session,
        "league_profile",
        table["league_profile"].c.competition_id == competition_id,
    )
    tables["league_season"] = _ordered_table_rows(
        session,
        "league_season",
        and_(
            table["league_season"].c.competition_id == competition_id,
            table["league_season"].c.season == season,
        ),
    )
    tables["canonical_teams"] = _ordered_table_rows(
        session,
        "canonical_teams",
        table["canonical_teams"].c.w2_team_id.in_(w2_team_ids),
    )
    crosswalk = table["provider_team_identity_crosswalks"]
    tables["provider_team_identity_crosswalks"] = _ordered_table_rows(
        session,
        "provider_team_identity_crosswalks",
        and_(
            crosswalk.c.provider == "api_football",
            crosswalk.c.provider_team_id.in_(provider_team_ids),
            crosswalk.c.competition_id == competition_id,
            crosswalk.c.season == season,
            crosswalk.c.valid_from <= kickoff,
            or_(crosswalk.c.valid_to.is_(None), crosswalk.c.valid_to > kickoff),
        ),
    )
    history = table["canonical_team_match_history"]
    tables["canonical_team_match_history"] = _ordered_table_rows(
        session,
        "canonical_team_match_history",
        and_(history.c.team_w2_id.in_(w2_team_ids), history.c.kickoff_utc < kickoff),
    )
    rating = table["team_rating_snapshots"]
    tables["team_rating_snapshots"] = _ordered_table_rows(
        session,
        "team_rating_snapshots",
        and_(rating.c.w2_team_id.in_(w2_team_ids), rating.c.observed_at <= kickoff),
    )
    xg_match = table["team_xg_match"]
    tables["team_xg_match"] = _ordered_table_rows(
        session,
        "team_xg_match",
        and_(
            xg_match.c.team_id.in_(provider_team_ids | w2_team_ids),
            xg_match.c.kickoff_at < kickoff,
        ),
    )
    xg_snapshot = table["team_xg_rolling_snapshot"]
    tables["team_xg_rolling_snapshot"] = _ordered_table_rows(
        session,
        "team_xg_rolling_snapshot",
        and_(
            xg_snapshot.c.team_id.in_(provider_team_ids | w2_team_ids),
            xg_snapshot.c.as_of_time <= kickoff,
        ),
    )
    mapping = table["player_identity_mappings"]
    mapping_rows = _ordered_table_rows(
        session,
        "player_identity_mappings",
        and_(
            mapping.c.api_football_player_id.in_(player_ids),
            mapping.c.team_external_id.in_(provider_team_ids | w2_team_ids),
            mapping.c.valid_from <= kickoff,
            or_(mapping.c.valid_to.is_(None), mapping.c.valid_to > kickoff),
        ),
    )
    tables["player_identity_mappings"] = mapping_rows
    transfermarkt_ids = {
        str(row["transfermarkt_player_id"])
        for row in mapping_rows
        if row.get("transfermarkt_player_id")
    }
    reference = table["transfermarkt_player_references"]
    tables["transfermarkt_player_references"] = _ordered_table_rows(
        session,
        "transfermarkt_player_references",
        reference.c.transfermarkt_player_id.in_(transfermarkt_ids),
    )
    valuation = table["player_valuation_observations"]
    tables["player_valuation_observations"] = _ordered_table_rows(
        session,
        "player_valuation_observations",
        and_(
            valuation.c.transfermarkt_player_id.in_(transfermarkt_ids),
            valuation.c.observed_at <= kickoff,
        ),
    )
    membership = table["player_club_membership_observations"]
    tables["player_club_membership_observations"] = _ordered_table_rows(
        session,
        "player_club_membership_observations",
        and_(
            membership.c.transfermarkt_player_id.in_(transfermarkt_ids),
            membership.c.observed_at <= kickoff,
        ),
    )
    baseline = table["team_lineup_baselines"]
    tables["team_lineup_baselines"] = _ordered_table_rows(
        session,
        "team_lineup_baselines",
        and_(
            baseline.c.team_external_id.in_(provider_team_ids | w2_team_ids),
            baseline.c.competition_external_id.in_({competition_id, identity.provider_league_id}),
            baseline.c.season == season,
            baseline.c.as_of_time <= kickoff,
        ),
    )
    team_value = table["team_value_asof_artifacts"]
    tables["team_value_asof_artifacts"] = _ordered_table_rows(
        session,
        "team_value_asof_artifacts",
        and_(
            team_value.c.team_external_id.in_(provider_team_ids | w2_team_ids),
            team_value.c.competition_id == competition_id,
            team_value.c.as_of <= kickoff,
        ),
    )
    if set(tables) != set(CONTEXT_TABLES):
        raise RealFixtureReplayError("SOURCE_CONTEXT_TABLE_CONTRACT_DRIFT")
    return {
        "schema_version": "w2.real-fixture-source-context.v1",
        "fixture_id_sha256": hashlib.sha256(
            identity.provider_fixture_id.encode("utf-8")
        ).hexdigest(),
        "tables": tables,
    }


def _lineup_business_rows(candidate: _ExportCandidate) -> list[dict[str, Any]]:
    players_by_snapshot: dict[str, list[dict[str, Any]]] = {}
    excluded_player_fields = {"id", "lineup_snapshot_id", "identity_mapping_id"}
    for player in candidate.lineup_players:
        row = _row_dict(player)
        players_by_snapshot.setdefault(player.lineup_snapshot_id, []).append(
            {key: value for key, value in row.items() if key not in excluded_player_fields}
        )
    output = []
    for snapshot in candidate.lineup_snapshots:
        row = _row_dict(snapshot)
        snapshot_id = str(row.pop("id"))
        row["players"] = sorted(
            players_by_snapshot.get(snapshot_id, []),
            key=lambda item: (str(item["api_football_player_id"]), not bool(item["starter"])),
        )
        output.append(row)
    return sorted(output, key=lambda item: str(item["team_external_id"]))


def _source_reference(candidate: _ExportCandidate) -> dict[str, Any]:
    checkpoint_payload = candidate.checkpoint.payload if candidate.checkpoint is not None else None
    card = (
        checkpoint_payload.get("analysis_card") if isinstance(checkpoint_payload, Mapping) else None
    )
    fixture_ids = {
        candidate.identity.fixture_id,
        candidate.identity.provider_fixture_id,
        f"api_football:{candidate.identity.provider_fixture_id}",
    }
    decision_hashes = sorted(
        {row.identity_hash for row in candidate.dynamic_evaluations if row.identity_hash}
    )
    return {
        "schema_version": "w2.real-fixture-production-source-reference.v1",
        "authority": "SOURCE_REFERENCE_ONLY_NOT_REPLAY_EXPECTED",
        "fixture_identity": _row_dict(candidate.identity),
        "endpoint_captures": [_row_dict(row) for row in candidate.captures],
        "market_observations": [_row_dict(row) for row in candidate.observations],
        "projected_observations": list(candidate.projected_observations),
        "lineups": _lineup_business_rows(candidate),
        "dynamic_evaluations": [_row_dict(row) for row in candidate.dynamic_evaluations],
        "checkpoint": (
            {
                "checkpoint_key": candidate.checkpoint.checkpoint_key,
                "source_hash": candidate.checkpoint.source_hash,
                "payload": checkpoint_payload,
            }
            if candidate.checkpoint is not None
            else None
        ),
        "dashboard_card_sha256": (
            canonical_sha256(card, domain=HashDomain.FUTURE_REFRESH_EVIDENCE)
            if isinstance(card, Mapping)
            else None
        ),
        "decision_hashes": decision_hashes,
        "outcome_ledger": [
            _row_dict(row) for row in candidate.outcome_records if row.fixture_id in fixture_ids
        ],
        "results": [_row_dict(row) for row in candidate.results if row.fixture_id in fixture_ids],
    }


def _recomputed_outputs(candidate: _ExportCandidate) -> dict[str, Any]:
    if candidate.checkpoint is None:
        raise RealFixtureReplayError("RECOMPUTED_CHECKPOINT_MISSING")
    checkpoint_payload = candidate.checkpoint.payload
    card = checkpoint_payload.get("analysis_card")
    if not isinstance(card, Mapping):
        raise RealFixtureReplayError("RECOMPUTED_DASHBOARD_CARD_MISSING")
    return {
        "schema_version": "w2.real-fixture-recomputed-outputs.v1",
        "fixture_identity": _row_dict(candidate.identity),
        "raw_payload_sha256": sorted(row.sha256 for row in candidate.raw_payloads),
        "endpoint_captures": [_row_dict(row) for row in candidate.captures],
        "market_observations": [_row_dict(row) for row in candidate.observations],
        "projected_observations": list(candidate.projected_observations),
        "lineups": _lineup_business_rows(candidate),
        "dynamic_evaluations": [_row_dict(row) for row in candidate.dynamic_evaluations],
        "checkpoint": {
            "checkpoint_key": candidate.checkpoint.checkpoint_key,
            "source_hash": candidate.checkpoint.source_hash,
            "payload": checkpoint_payload,
        },
        "dashboard_card_sha256": canonical_sha256(card, domain=HashDomain.FUTURE_REFRESH_EVIDENCE),
        "decision_hashes": sorted(
            row.identity_hash for row in candidate.dynamic_evaluations if row.identity_hash
        ),
        "explicit_not_ready": not candidate.dynamic_evaluations,
    }


def _quota_headers(capture: MatchdayEndpointCaptureModel) -> dict[str, str]:
    quota = capture.quota_values
    headers: dict[str, str] = {}
    sources = (
        ("daily_source", "daily_remaining"),
        ("daily_limit_source", "daily_limit"),
        ("burst_source", "burst_remaining"),
    )
    for source_key, value_key in sources:
        source = quota.get(source_key)
        value = quota.get(value_key)
        if isinstance(source, str) and source.startswith("x-") and value is not None:
            headers[source] = str(value)
    daily = quota.get("daily_remaining")
    if daily is None:
        raise BundleIncompleteError(
            str(capture.fixture_id or "global"),
            [f"endpoint_capture.{capture.endpoint}.quota.daily_remaining"],
        )
    return headers


def _provider_payload(
    raw: RawPayloadModel, capture: MatchdayEndpointCaptureModel
) -> dict[str, Any]:
    payload = dict(raw.payload)
    endpoint = payload.pop("endpoint", capture.endpoint)
    parameters = payload.pop("parameters", capture.sanitized_params)
    if endpoint != capture.endpoint or parameters != capture.sanitized_params:
        raise BundleIncompleteError(
            str(capture.fixture_id or "global"),
            [f"raw_payload.{capture.endpoint}.request_identity"],
        )
    return payload


def _write_bundle_files(
    bundle_root: Path,
    *,
    files: Mapping[str, object],
    manifest_core: dict[str, Any],
) -> dict[str, Any]:
    if bundle_root.exists():
        raise RealFixtureReplayError(f"BUNDLE_ROOT_ALREADY_EXISTS:{bundle_root}")
    bundle_root.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".w2-real-fixture-", dir=bundle_root.parent) as temporary:
        staging = Path(temporary) / "bundle"
        staging.mkdir()
        receipts = []
        for relative_path, payload in sorted(files.items()):
            data = _canonical_file_bytes(payload)
            path = staging.joinpath(*PurePosixPath(relative_path).parts)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            kind = (
                "RAW_PAYLOAD"
                if relative_path.startswith("raw/")
                else "SOURCE_CONTEXT"
                if relative_path.startswith("source/") and relative_path.endswith("context.json")
                else "SOURCE_REFERENCE"
            )
            receipts.append(
                {
                    "path": relative_path,
                    "sha256": _sha256(data),
                    "size_bytes": len(data),
                    "kind": kind,
                }
            )
        core = {**manifest_core, "files": receipts}
        manifest = {**core, "bundle_id": _bundle_id(core)}
        # Keep bundle_id first only for human review; canonical serialization
        # remains the sole byte/hash authority.
        manifest = {"schema_version": manifest.pop("schema_version"), **manifest}
        _schema_validate(manifest, PRIVATE_SCHEMA)
        (staging / PRIVATE_MANIFEST).write_bytes(_canonical_file_bytes(manifest))
        sanitized = sanitized_manifest(manifest)
        (staging / SANITIZED_MANIFEST).write_bytes(_canonical_file_bytes(sanitized))
        staging.replace(bundle_root)
    return manifest


def sanitized_manifest(private: Mapping[str, Any]) -> dict[str, Any]:
    source_reference = next(item for item in private["files"] if item["kind"] == "SOURCE_REFERENCE")
    manifest = {
        "schema_version": SANITIZED_SCHEMA_VERSION,
        "private_bundle_schema_version": private["schema_version"],
        "bundle_id": private["bundle_id"],
        "source_git_sha": private["source_git_sha"],
        "migration_head": private["migration_head"],
        "serializer_version": private["serializer_version"],
        "fixture_id_sha256": private["fixture"]["fixture_id_sha256"],
        "competition_id": private["fixture"]["competition_id"],
        "season": private["fixture"]["season"],
        "kickoff_utc": private["fixture"]["kickoff_utc"],
        "export_snapshot_identity_sha256": private["export_transaction"][
            "snapshot_identity_sha256"
        ],
        "file_receipts": [
            {
                "logical_path": item["path"],
                "sha256": item["sha256"],
                "size_bytes": item["size_bytes"],
                "kind": item["kind"],
            }
            for item in private["files"]
        ],
        "expected": {
            "recompute_mode": private["expected"]["recompute_mode"],
            "source_reference_sha256": source_reference["sha256"],
        },
        "contains_raw_payloads": False,
    }
    _schema_validate(manifest, SANITIZED_SCHEMA)
    return manifest


def export_real_fixture_bundle(
    *,
    engine: Engine,
    bundle_root: Path,
    source_git_sha: str,
    migration_head: str,
    fixture_id: str | None = None,
) -> dict[str, Any]:
    if len(source_git_sha) != 40 or any(
        character not in "0123456789abcdef" for character in source_git_sha
    ):
        raise RealFixtureReplayError("EXACT_SOURCE_GIT_SHA_REQUIRED")
    failures: list[BundleIncompleteError] = []
    with engine.connect() as connection:
        transaction_identity = _read_transaction_identity(connection)
        session = Session(bind=connection, autoflush=False, expire_on_commit=False)
        try:
            candidates = _identity_candidates(session, fixture_id)
            if not candidates:
                raise BundleIncompleteError(str(fixture_id or "AUTO"), ["fixture_identity"])
            candidate: _ExportCandidate | None = None
            for identity in candidates:
                try:
                    candidate = _collect_candidate(session, identity)
                    break
                except BundleIncompleteError as exc:
                    failures.append(exc)
            if candidate is None:
                best = min(failures, key=lambda item: len(item.missing_fields))
                raise best
            context = _source_context(session, candidate)
            source_reference = _source_reference(candidate)
            # Everything used below was materialized in this one transaction.
            captures = candidate.captures
            raw_by_sha = {row.sha256: row for row in candidate.raw_payloads}
            request_rows: list[dict[str, Any]] = []
            file_payloads: dict[str, object] = {
                "source/context.json": context,
                "source/reference.json": source_reference,
            }
            for ordinal, (endpoint, capture) in enumerate(
                zip(EXPECTED_ENDPOINTS, captures, strict=True), start=1
            ):
                if capture.endpoint != endpoint:
                    raise BundleIncompleteError(
                        candidate.identity.provider_fixture_id,
                        [f"endpoint_capture.sequence.{endpoint}"],
                    )
                raw = raw_by_sha[capture.raw_payload_sha256]
                payload_path = f"raw/{ordinal:02d}-{endpoint}.json"
                file_payloads[payload_path] = _provider_payload(raw, capture)
                request_rows.append(
                    {
                        "ordinal": ordinal,
                        "endpoint": endpoint,
                        "params": {
                            str(key): str(value) for key, value in capture.sanitized_params.items()
                        },
                        "status_code": capture.status_code,
                        "elapsed_ms": capture.elapsed_ms,
                        "requested_at_utc": _iso(capture.requested_at),
                        "captured_at_utc": _iso(capture.provider_captured_at),
                        "headers": _quota_headers(capture),
                        "payload_path": payload_path,
                        "capture_id": capture.capture_id,
                        "raw_payload_sha256": capture.raw_payload_sha256,
                    }
                )
            replay_now = min(capture.requested_at for capture in captures)
            ingested_at = captures[2].provider_captured_at
            projected_at = max(capture.provider_captured_at for capture in captures)
            manifest_core = {
                "schema_version": PRIVATE_SCHEMA_VERSION,
                "source_git_sha": source_git_sha,
                "migration_head": migration_head,
                "serializer_version": CURRENT_SERIALIZER_VERSION.value,
                "fixture": {
                    "fixture_id": candidate.identity.provider_fixture_id,
                    "fixture_id_sha256": hashlib.sha256(
                        candidate.identity.provider_fixture_id.encode("utf-8")
                    ).hexdigest(),
                    "identity_hash": candidate.identity.identity_hash,
                    "competition_id": candidate.identity.competition_id,
                    "provider_league_id": candidate.identity.provider_league_id,
                    "season": candidate.identity.season,
                    "kickoff_utc": _iso(candidate.identity.kickoff_utc),
                },
                "export_transaction": transaction_identity,
                "replay": {
                    "now_utc": _iso(replay_now),
                    "ingested_at_utc": _iso(ingested_at),
                    "projected_at_utc": _iso(projected_at),
                    "expected_endpoint_sequence": list(EXPECTED_ENDPOINTS),
                },
                "requests": request_rows,
                "expected": {
                    "recompute_mode": "FIRST_ISOLATED_RECOMPUTE_THEN_SECOND_COMPARE",
                    "source_reference_path": "source/reference.json",
                },
            }
        finally:
            session.close()
            connection.rollback()
    return _write_bundle_files(
        bundle_root,
        files=file_payloads,
        manifest_core=manifest_core,
    )


def _source_runtime_environment(context: Mapping[str, Any]) -> str:
    tables = context.get("tables")
    seasons = tables.get("league_season") if isinstance(tables, Mapping) else None
    if seasons == []:
        return "test"
    if not isinstance(seasons, list):
        raise RealFixtureReplayError("SOURCE_CONTEXT_RUNTIME_ENVIRONMENT_MISSING")
    environments = {
        str(payload["environment"]).strip().lower()
        for row in seasons
        if isinstance(row, Mapping)
        and isinstance((payload := row.get("payload")), Mapping)
        and isinstance(payload.get("environment"), str)
        and str(payload["environment"]).strip()
    }
    if len(environments) != 1:
        raise RealFixtureReplayError("SOURCE_CONTEXT_RUNTIME_ENVIRONMENT_INVALID")
    return environments.pop()


@contextmanager
def _replay_environment(
    database_url: str,
    source_git_sha: str,
    runtime_environment: str,
) -> Iterator[None]:
    from w2.config import get_settings

    values = {
        "W2_DATABASE_URL": database_url,
        "W2_ENVIRONMENT": runtime_environment,
        "W2_GIT_SHA": source_git_sha,
        "W2_PROVIDER_CALLS_DISABLED": "true",
        "W2_PROVIDER_ENDPOINT_ALLOWLIST": "status,fixtures,odds,lineups",
        "W2_PROVIDER_HTTP_MAX_ATTEMPTS": "1",
        "W2_PROVIDER_PREFLIGHT_MIN_REMAINING": "0",
        "W2_PROVIDER_DAILY_HARD_CAP": "10000",
        "W2_PROVIDER_DAILY_RESERVE": "0",
        "W2_PROVIDER_REFRESH_TICK_HARD_CAP": "4",
        "W2_FUTURE_REFRESH_PERSISTENCE": "db",
    }
    previous = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    get_settings.cache_clear()
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()


def _database_value(column: Any, value: Any) -> Any:
    if value is None:
        return None
    if isinstance(column.type, DateTime):
        return _parse_utc(str(value))
    if isinstance(column.type, Numeric):
        if isinstance(value, Mapping) and set(value) == {"$w2_float"}:
            encoded = value["$w2_float"]
            if not isinstance(encoded, str) or len(encoded) != 16:
                raise RealFixtureReplayError("SOURCE_CONTEXT_FLOAT_INVALID")
            try:
                value = struct.unpack(">d", bytes.fromhex(encoded))[0]
            except (ValueError, struct.error) as exc:
                raise RealFixtureReplayError("SOURCE_CONTEXT_FLOAT_INVALID") from exc
        return Decimal(str(value))
    return value


def _seed_source_context(engine: Engine, context: Mapping[str, Any]) -> int:
    from w2.infrastructure.persistence import (  # noqa: F401  # noqa: F401
        factor_model_models,
        future_refresh_models,
        league_models,
        models,
    )

    if context.get("schema_version") != "w2.real-fixture-source-context.v1":
        raise RealFixtureReplayError("SOURCE_CONTEXT_SCHEMA_INVALID")
    tables = context.get("tables")
    if not isinstance(tables, Mapping):
        raise RealFixtureReplayError("SOURCE_CONTEXT_TABLES_INVALID")
    names = {str(name) for name in tables}
    if names & OUTPUT_TABLES:
        raise RealFixtureReplayError("MANUAL_OUTPUT_SEED_FORBIDDEN")
    if names != set(CONTEXT_TABLES):
        raise RealFixtureReplayError("SOURCE_CONTEXT_TABLE_SET_INVALID")
    inserted = 0
    with engine.begin() as connection:
        for table_name in CONTEXT_TABLES:
            table = Base.metadata.tables[table_name]
            rows = tables[table_name]
            if not isinstance(rows, list):
                raise RealFixtureReplayError(f"SOURCE_CONTEXT_ROWS_INVALID:{table_name}")
            decoded = []
            for row in rows:
                if not isinstance(row, Mapping) or set(row) != {
                    column.name for column in table.columns
                }:
                    raise RealFixtureReplayError(f"SOURCE_CONTEXT_ROW_SHAPE_INVALID:{table_name}")
                decoded.append(
                    {
                        column.name: _database_value(column, row[column.name])
                        for column in table.columns
                    }
                )
            if decoded:
                connection.execute(table.insert(), decoded)
                inserted += len(decoded)
    return inserted


def _materializer(projected_at: datetime) -> Any:
    from w2.dashboard.scorelines import scoreline_reference_from_card
    from w2.prematch.analysis_calculator import ReadModelRepository, ReadModelService
    from w2.prematch.read_model_projection import (
        AnalysisCardCanaryMaterializer,
        ScopedAnalysisRepository,
        write_frozen_analysis_artifacts,
    )

    repository = ReadModelRepository()

    def calculate(
        scoped_repository: ScopedAnalysisRepository,
        fixture_id: str,
        evaluated_at: datetime,
    ) -> dict[str, object] | None:
        return ReadModelService(
            repository=cast(ReadModelRepository, scoped_repository)
        ).public_analysis_card_bounded(
            fixture_id,
            evaluation_time=evaluated_at,
            use_frozen_canary=False,
        )

    def build_scoreline_reference(
        card: Any,
        version: Any,
        quote_identity: Any,
    ) -> dict[str, Any] | None:
        return scoreline_reference_from_card(
            card,
            recommendation={
                "market": version.market,
                "selection": version.selection,
                "line": version.exact_line,
                "decision_tier": "ANALYSIS_PICK",
                "quote_identity": quote_identity,
            },
            decision_hash=version.identity_hash,
        )

    materializer = AnalysisCardCanaryMaterializer(
        cast(Any, repository),
        calculate_analysis_card=calculate,
        build_scoreline_reference=build_scoreline_reference,
        clock=lambda: projected_at,
    )

    def materialize(events: list[Any]) -> list[str]:
        from w2.infrastructure.database import create_engine as w2_create_engine

        engine = w2_create_engine()
        ordered = sorted(
            {
                (event.fixture_id, event.event_type, event.event_id): event for event in events
            }.values(),
            key=lambda event: (event.event_at, event.fixture_id, event.event_type, event.event_id),
        )
        for event in ordered:
            artifact = materializer.build(
                event.fixture_id,
                evaluated_at=event.event_at,
                source_event=event,
            )
            write_frozen_analysis_artifacts(engine, [artifact])
        return list(dict.fromkeys(event.fixture_id for event in ordered))

    return materialize


def _actual_outputs(engine: Engine, fixture_id: str) -> dict[str, Any]:
    with Session(engine) as session:
        identities = _identity_candidates(session, fixture_id)
        if len(identities) != 1:
            raise RealFixtureReplayError("REPLAY_FIXTURE_IDENTITY_COUNT_INVALID")
        candidate = _collect_candidate(session, identities[0])
        return _recomputed_outputs(candidate)


def _replay_once(
    bundle: VerifiedBundle,
    database_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    from w2.config import get_settings
    from w2.ingestion import future_refresh
    from w2.ingestion.future_refresh import FutureFixtureRefreshService, FutureRefreshConfig

    manifest = bundle.manifest
    source_git_sha = str(manifest["source_git_sha"])
    database_url = f"sqlite+pysqlite:///{database_path}"
    context = bundle.json_file("source/context.json")
    source_reference = bundle.json_file(str(manifest["expected"]["source_reference_path"]))
    if not isinstance(source_reference, dict) or not isinstance(context, dict):
        raise RealFixtureReplayError("REPLAY_BUNDLE_JSON_SHAPE_INVALID")
    if source_reference.get("authority") != "SOURCE_REFERENCE_ONLY_NOT_REPLAY_EXPECTED":
        raise RealFixtureReplayError("SOURCE_REFERENCE_AUTHORITY_INVALID")
    runtime_environment = _source_runtime_environment(context)
    with (
        _replay_environment(
            database_url,
            source_git_sha,
            runtime_environment,
        ),
        network_disabled(),
    ):
        # Importing persistence registers every current table and the current
        # market projection view before the isolated schema is created.
        import w2.infrastructure.persistence  # noqa: F401
        from w2.infrastructure.persistence import (
            factor_model_models,  # noqa: F401
            league_models,  # noqa: F401
            models,  # noqa: F401
        )

        engine = create_engine(database_url)
        Base.metadata.create_all(engine)
        context_count = _seed_source_context(engine, context)
        fixture = manifest["fixture"]
        replay = manifest["replay"]
        requests = manifest["requests"]
        fixtures_params = dict(requests[1]["params"])
        config = FutureRefreshConfig(
            competition_id=str(fixture["competition_id"]),
            league_id=str(fixture["provider_league_id"]),
            season=str(fixture["season"]),
            horizon_days=30,
            max_fixture_candidates=1,
            max_odds_requests=1,
            quota_reserve=0,
            request_budget=4,
            feature_enrichment_enabled=True,
            feature_enrichment_endpoints=("lineups",),
            feature_enrichment_request_budget=1,
            source_revision=source_git_sha,
            enabled=True,
            persistence="db",
            daily_hard_cap=10000,
            daily_reserve=0,
            actual_provider_calls_today=0,
            provider_refresh_batch_size=1,
            checkpoint_fixture_ids=(str(fixture["fixture_id"]),),
        )

        class ReplayRefreshService(FutureFixtureRefreshService):
            def _fixtures_request_params(self) -> dict[str, str]:
                return {str(key): str(value) for key, value in fixtures_params.items()}

        client = BundleProviderClient(bundle)
        replay_now = _parse_utc(str(replay["now_utc"]))
        ingested_at = _parse_utc(str(replay["ingested_at_utc"]))
        projected_at = _parse_utc(str(replay["projected_at_utc"]))
        original_utc_now = future_refresh.utc_now
        future_refresh.utc_now = lambda: ingested_at
        try:
            service = ReplayRefreshService(
                client=client,
                config=replace(config),
                now=replay_now,
                materialize_public_artifacts=_materializer(projected_at),
            )
            result = service.run()
        finally:
            future_refresh.utc_now = original_utc_now
        client.assert_consumed()
        if result.status != "COMPLETED" or result.blockers:
            raise RealFixtureReplayError(
                f"REAL_FIXTURE_PRODUCTION_CHAIN_BLOCKED:{result.status}:{result.blockers}"
            )
        actual = _actual_outputs(engine, str(fixture["fixture_id"]))
        actual_bytes = canonical_bytes(actual, domain=HashDomain.FUTURE_REFRESH_EVIDENCE)
        checkpoint = cast(Mapping[str, Any], actual["checkpoint"])
        payload = cast(Mapping[str, Any], checkpoint["payload"])
        get_settings.cache_clear()
    metadata = {
        "bundle_id": manifest["bundle_id"],
        "source_git_sha": source_git_sha,
        "migration_head": manifest["migration_head"],
        "recomputed_outputs_sha256": hashlib.sha256(actual_bytes).hexdigest(),
        "dashboard_card_sha256": actual["dashboard_card_sha256"],
        "checkpoint_source_hash": checkpoint["source_hash"],
        "checkpoint_artifact_hash": payload["artifact_hash"],
        "decision_hashes": actual["decision_hashes"],
        "explicit_not_ready": actual["explicit_not_ready"],
        "source_context_rows": context_count,
        "saved_response_count": client.ordinal,
        "source_dynamic_evaluation_count": len(source_reference["dynamic_evaluations"]),
        "source_outcome_ledger_count": len(source_reference["outcome_ledger"]),
        "source_result_count": len(source_reference["results"]),
        **_postmatch_ledger_replay(source_reference),
    }
    return actual, metadata


def _postmatch_ledger_replay(source_reference: Mapping[str, Any]) -> dict[str, Any]:
    raw_ledger = source_reference.get("outcome_ledger")
    raw_results = source_reference.get("results")
    ledger = [dict(row) for row in raw_ledger] if isinstance(raw_ledger, list) else []
    results = [dict(row) for row in raw_results] if isinstance(raw_results, list) else []
    identities_match = bool(ledger) and all(
        isinstance(row.get("payload"), Mapping)
        and business_key(cast(Mapping[str, Any], row["payload"]), str(row.get("record_type") or ""))
        == row.get("business_key")
        for row in ledger
    )
    settlement_candidates = [
        row
        for row in ledger
        if row.get("record_type") == "capture"
        and isinstance(row.get("payload"), Mapping)
        and _source_capture_has_pick(cast(Mapping[str, Any], row["payload"]))
    ]
    return {
        "POSTMATCH_LEDGER_REPLAY": "PENDING",
        "POSTMATCH_LEDGER_REPLAY_REASON": (
            "NO_SETTLEMENT_ELIGIBLE_PREMATCH_PICK_IN_SOURCE_LEDGER"
            if results and not settlement_candidates
            else "SAVED_RESULT_EVIDENCE_MISSING"
            if not results
            else "SETTLEMENT_REPLAY_NOT_PROVEN"
        ),
        "LEDGER_BUSINESS_IDENTITY_MATCH": identities_match,
        "SOURCE_SETTLEMENT_ELIGIBLE_CAPTURE_COUNT": len(settlement_candidates),
        "MANUAL_LEDGER_INSERTS": 0,
    }


def _source_capture_has_pick(payload: Mapping[str, Any]) -> bool:
    return any(
        isinstance(value, Mapping) and bool(value)
        for value in (payload.get("pick"), payload.get("shadow_pick"))
    )


def replay_real_fixture_bundle(
    *,
    bundle_root: Path,
    current_git_sha: str,
    current_migration_head: str,
) -> dict[str, Any]:
    bundle = load_verified_bundle(bundle_root)
    manifest = bundle.manifest
    if manifest["source_git_sha"] != current_git_sha:
        raise RealFixtureReplayError("REPLAY_GIT_SHA_MISMATCH")
    if manifest["migration_head"] != current_migration_head:
        raise RealFixtureReplayError("REPLAY_MIGRATION_HEAD_MISMATCH")
    with TemporaryDirectory(prefix="w2-real-fixture-replay-") as temporary:
        root = Path(temporary)
        first_outputs, first = _replay_once(bundle, root / "first.db")
        second_outputs, second = _replay_once(bundle, root / "second.db")
    first_bytes = canonical_bytes(first_outputs, domain=HashDomain.FUTURE_REFRESH_EVIDENCE)
    second_bytes = canonical_bytes(second_outputs, domain=HashDomain.FUTURE_REFRESH_EVIDENCE)
    if not hmac.compare_digest(first_bytes, second_bytes) or first != second:
        raise RealFixtureReplayError("REAL_FIXTURE_REPLAY_NOT_IDEMPOTENT")
    return {
        "schema_version": "w2.real-fixture-replay-receipt.v1",
        "REAL_FIXTURE_OFFLINE_REPLAY": "PASS",
        "REAL_FIXTURE_PREMATCH_RECOMMENDATION_REPLAY": "PASS",
        "NETWORK_CALLS_DURING_REPLAY": 0,
        "REAL_PROVIDER_CALLS_EXECUTED": 0,
        "MANUAL_EVALUATION_INSERTS": 0,
        "MANUAL_PAIR_INSERTS": 0,
        "MANUAL_CHECKPOINT_INSERTS": 0,
        "DB_RECOMPUTE_BYTE_IDENTICAL": True,
        "REPLAY_IDEMPOTENT": True,
        "CANDIDATE": "OFF",
        "FORMAL": "OFF",
        "LOCK": "OFF",
        "PRODUCTION": "OFF",
        **first,
    }
