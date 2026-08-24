from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from string import hexdigits
from typing import Any, Protocol

from w2.domain.canonical_serialization import HashDomain, canonical_sha256

RAW_HISTORY_CORPUS_SCHEMA_VERSION = "w2.factor_model.raw_history_corpus.v1"
RAW_HISTORY_COVERAGE_SCHEMA_VERSION = "w2.factor_model.raw_history_coverage.v1"
PIT_HISTORY_MANIFEST_SCHEMA_VERSION = "w2.factor_model.pit_history_manifest.v2"
API_FOOTBALL_TEAM_ID_NAMESPACE = "api_football.provider_team_id.v1"
FINISHED_FIXTURE_STATUSES = frozenset({"FT", "AET", "PEN"})
LATE_RESULT_THRESHOLD = timedelta(hours=36)


class HistoricalFixtureRepository(Protocol):
    def raw_payloads(self, endpoint: str) -> list[dict[str, Any]]: ...


@dataclass(frozen=True)
class HistoricalFixtureBatch:
    history_rows: tuple[dict[str, Any], ...]
    coverage_report: dict[str, Any]
    corpus_sha256: str
    provider_calls: int = 0
    source_scope: str = "PERSISTED_RAW_AS_OF"


@dataclass(frozen=True)
class _RawFixtureObservation:
    raw_payload_sha256: str
    raw_captured_at: datetime
    item: dict[str, Any]


def materialize_factor_history_from_persisted_raw(
    repository: HistoricalFixtureRepository,
    *,
    kickoff_from: datetime,
    kickoff_to: datetime,
    as_of: datetime,
    provider_league_id: str | None = None,
) -> HistoricalFixtureBatch:
    """Build an API-Football-ID history corpus from saved DB raw only."""
    lower = _aware_utc(kickoff_from, "kickoff_from")
    requested_upper = _aware_utc(kickoff_to, "kickoff_to")
    feature_as_of = _aware_utc(as_of, "as_of")
    upper = min(requested_upper, feature_as_of)
    if upper < lower:
        raise ValueError("RAW_HISTORY_KICKOFF_WINDOW_INVALID")

    totals: Counter[str] = Counter()
    by_scope: dict[tuple[str, str], Counter[str]] = {}
    observations: dict[str, list[_RawFixtureObservation]] = {}
    raw_rows = repository.raw_payloads("fixtures")
    totals["raw_payload_count"] = len(raw_rows)

    for raw in raw_rows:
        raw_sha = str(raw.get("sha256") or "")
        try:
            captured_at = _aware_utc(raw.get("captured_at"), "raw_captured_at")
        except (TypeError, ValueError):
            totals["malformed_raw_payload_count"] += 1
            continue
        payload = raw.get("payload")
        response = payload.get("response") if isinstance(payload, Mapping) else None
        if not _valid_sha256(raw_sha) or not isinstance(response, list):
            totals["malformed_raw_payload_count"] += 1
            continue
        for item in response:
            if not isinstance(item, dict):
                totals["malformed_fixture_item_count"] += 1
                continue
            fields = _fixture_fields(item)
            league_id = fields["provider_league_id"]
            if provider_league_id is not None and league_id != provider_league_id:
                if not league_id:
                    totals["identity_missing_item_count"] += 1
                continue
            fixture_id = fields["provider_fixture_id"]
            if not fixture_id:
                totals["identity_missing_item_count"] += 1
                continue
            totals["raw_fixture_observation_count"] += 1
            observations.setdefault(fixture_id, []).append(
                _RawFixtureObservation(
                    raw_payload_sha256=raw_sha,
                    raw_captured_at=captured_at,
                    item=item,
                )
            )

    history_rows: list[dict[str, Any]] = []
    for fixture_observations in observations.values():
        visible = [row for row in fixture_observations if row.raw_captured_at < feature_as_of]
        if not visible:
            totals["not_known_at_as_of_fixture_count"] += 1
            continue
        latest_at = max(row.raw_captured_at for row in visible)
        latest = [row for row in visible if row.raw_captured_at == latest_at]
        if len({_fixture_signature(row.item) for row in latest}) != 1:
            _increment(totals, by_scope, "conflict_fixture_count", _common_scope(latest))
            continue
        if len(latest) > 1:
            totals["equivalent_latest_duplicate_count"] += len(latest) - 1
        selected = min(latest, key=lambda row: row.raw_payload_sha256)
        fields = _fixture_fields(selected.item)
        scope = (fields["provider_league_id"], fields["season"])
        kickoff = fields["kickoff_utc"]
        missing_identity = any(
            not fields[field]
            for field in (
                "provider_fixture_id",
                "provider_league_id",
                "season",
                "home_team_id",
                "away_team_id",
            )
        ) or kickoff is None
        if missing_identity:
            _increment(totals, by_scope, "identity_missing_fixture_count", scope)
            continue
        if not lower <= kickoff < upper:
            _increment(totals, by_scope, "out_of_window_fixture_count", scope)
            continue

        _increment(totals, by_scope, "selected_fixture_count", scope)
        if fields["fixture_status"] not in FINISHED_FIXTURE_STATUSES:
            _increment(totals, by_scope, "unfinished_fixture_count", scope)
            continue
        if fields["home_goals"] is None or fields["away_goals"] is None:
            _increment(totals, by_scope, "result_missing_fixture_count", scope)
            continue

        selected_signature = _fixture_signature(selected.item)
        terminal_observations = [
            row
            for row in visible
            if _fixture_signature(row.item) == selected_signature
            and _complete_terminal_result(_fixture_fields(row.item))
        ]
        first_terminal_at = min(row.raw_captured_at for row in terminal_observations)
        result_delay_seconds = int((first_terminal_at - kickoff).total_seconds())
        if first_terminal_at - kickoff > LATE_RESULT_THRESHOLD:
            _increment(totals, by_scope, "late_result_fixture_count", scope)

        history_rows.extend(
            _history_rows(
                fields,
                raw_payload_sha256=selected.raw_payload_sha256,
                raw_captured_at=selected.raw_captured_at,
                result_first_captured_at=first_terminal_at,
                result_capture_delay_seconds=result_delay_seconds,
            )
        )
        _increment(totals, by_scope, "eligible_finished_fixture_count", scope)
        _increment(totals, by_scope, "history_row_count", scope, amount=2)

    history_rows.sort(
        key=lambda row: (row["kickoff_utc"], row["fixture_id"], row["team_side"])
    )
    coverage = _coverage_report(
        totals,
        by_scope,
        kickoff_from=lower,
        kickoff_to=upper,
        as_of=feature_as_of,
        provider_league_id=provider_league_id,
    )
    corpus_body = {
        "schema_version": RAW_HISTORY_CORPUS_SCHEMA_VERSION,
        "provider": "api_football",
        "team_identity_namespace": API_FOOTBALL_TEAM_ID_NAMESPACE,
        "coverage_report_sha256": coverage["coverage_report_sha256"],
        "history_rows": history_rows,
    }
    return HistoricalFixtureBatch(
        history_rows=tuple(history_rows),
        coverage_report=coverage,
        corpus_sha256=_hash("FACTOR_MODEL_RAW_HISTORY_CORPUS", corpus_body),
    )


def build_pit_history_manifest(
    rows: Sequence[Mapping[str, Any]],
    *,
    target_fixture_id: str,
    target_kickoff: datetime,
    feature_as_of: datetime,
    team_identity_namespace: str,
    immutable_fact_backfill: bool = False,
) -> dict[str, Any]:
    """Select fixture-level history known strictly before a target feature time."""
    target_time = _aware_utc(target_kickoff, "target_kickoff")
    as_of = _aware_utc(feature_as_of, "feature_as_of")
    if as_of > target_time:
        raise ValueError("PIT_HISTORY_FEATURE_ASOF_AFTER_TARGET_KICKOFF")
    if immutable_fact_backfill and as_of != target_time:
        raise ValueError("PIT_HISTORY_IMMUTABLE_FACT_ASOF_MUST_EQUAL_TARGET_KICKOFF")
    if not team_identity_namespace:
        raise ValueError("PIT_HISTORY_TEAM_IDENTITY_NAMESPACE_REQUIRED")

    grouped: dict[str, list[Mapping[str, Any]]] = {}
    malformed_count = 0
    for row in rows:
        fixture_id = str(row.get("fixture_id") or "")
        if not fixture_id:
            malformed_count += 1
            continue
        grouped.setdefault(fixture_id, []).append(row)

    included: list[dict[str, Any]] = []
    excluded: dict[str, int] = {}
    if malformed_count:
        excluded["MALFORMED_FIXTURE_IDENTITY"] = malformed_count

    for fixture_rows in grouped.values():
        reason, fixture = _pit_fixture(
            fixture_rows,
            target_fixture_id=str(target_fixture_id),
            target_kickoff=target_time,
            feature_as_of=as_of,
            team_identity_namespace=team_identity_namespace,
            immutable_fact_backfill=immutable_fact_backfill,
        )
        if reason:
            excluded[reason] = excluded.get(reason, 0) + 1
        elif fixture is not None:
            included.append(fixture)

    included.sort(key=lambda item: (item["kickoff_utc"], item["fixture_id"]))
    body = {
        "schema_version": PIT_HISTORY_MANIFEST_SCHEMA_VERSION,
        "target_fixture_id": str(target_fixture_id),
        "target_kickoff": target_time,
        "feature_as_of": as_of,
        "team_identity_namespace": team_identity_namespace,
        "source_fixture_count": len(included),
        "source_history_row_count": len(included) * 2,
        "source_fixtures": included,
        "excluded_fixture_counts": dict(sorted(excluded.items())),
    }
    if immutable_fact_backfill:
        body.update(
            {
                "visibility_policy": (
                    "IMMUTABLE_FACTS_STRICT_SOURCE_KICKOFF_BEFORE_FEATURE_AS_OF"
                ),
                "immutable_fact_fields": [
                    "kickoff_utc",
                    "home_team_id",
                    "away_team_id",
                    "home_goals",
                    "away_goals",
                ],
                "excluded_from_feature_inputs": [
                    "raw_captured_at",
                    "result_first_captured_at",
                    "result_capture_delay_seconds",
                ],
            }
        )
    return {
        **body,
        "manifest_sha256": canonical_sha256(
            {"identity_type": "FACTOR_MODEL_PIT_HISTORY_MANIFEST", **body},
            domain=HashDomain.PREMATCH_READ_MODEL_GENERIC,
        ),
    }


def _pit_fixture(
    rows: list[Mapping[str, Any]],
    *,
    target_fixture_id: str,
    target_kickoff: datetime,
    feature_as_of: datetime,
    team_identity_namespace: str,
    immutable_fact_backfill: bool,
) -> tuple[str | None, dict[str, Any] | None]:
    if str(rows[0].get("fixture_id")) == target_fixture_id:
        return "TARGET_FIXTURE", None
    if any(
        str(row.get("team_identity_namespace") or "") != team_identity_namespace
        for row in rows
    ):
        return "TEAM_IDENTITY_NAMESPACE_MISMATCH", None
    if any(
        str(row.get("fixture_status") or "").upper() not in FINISHED_FIXTURE_STATUSES
        for row in rows
    ):
        return "UNFINISHED_FIXTURE", None

    try:
        kickoffs = {_aware_utc(row.get("kickoff_utc"), "kickoff_utc") for row in rows}
        captures = [
            _aware_utc(row.get("raw_captured_at"), "raw_captured_at") for row in rows
        ]
    except (TypeError, ValueError):
        return "MALFORMED_FIXTURE_IDENTITY", None
    if len(kickoffs) != 1:
        return "IDENTITY_CONFLICT", None
    kickoff = next(iter(kickoffs))
    if kickoff >= target_kickoff:
        return "NOT_BEFORE_TARGET_KICKOFF", None
    if not immutable_fact_backfill and any(
        captured_at >= feature_as_of for captured_at in captures
    ):
        return "RESULT_NOT_KNOWN_AT_ASOF", None

    by_side: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        side = str(row.get("team_side") or "").upper()
        if side not in {"HOME", "AWAY"}:
            return "MALFORMED_FIXTURE_IDENTITY", None
        previous = by_side.get(side)
        if previous is not None and _history_identity(previous) != _history_identity(row):
            return "IDENTITY_CONFLICT", None
        by_side[side] = row
    if set(by_side) != {"HOME", "AWAY"}:
        return "INCOMPLETE_FIXTURE_IDENTITY", None

    home = by_side["HOME"]
    away = by_side["AWAY"]
    if not _coherent_pair(home, away):
        return "IDENTITY_CONFLICT", None

    fixture = {
        "fixture_id": str(home["fixture_id"]),
        "provider": str(home["provider"]),
        "provider_fixture_id": str(home["provider_fixture_id"]),
        "provider_league_id": str(home["provider_league_id"]),
        "season": str(home["season"]),
        "kickoff_utc": kickoff,
        "fixture_status": str(home["fixture_status"]).upper(),
        "team_identity_namespace": team_identity_namespace,
        "home_team_id": str(home["team_id"]),
        "away_team_id": str(away["team_id"]),
        "home_goals": int(home["goals_for"]),
        "away_goals": int(away["goals_for"]),
        "result_identity_hash": str(home["result_identity_hash"]),
        "raw_captured_at": max(captures),
        "source_history_hashes": sorted(
            {str(row["history_hash"]) for row in by_side.values()}
        ),
        "source_raw_payload_sha256": sorted(
            {str(row["raw_payload_sha256"]) for row in by_side.values()}
        ),
    }
    if not immutable_fact_backfill:
        fixture.update(
            {
                "result_first_captured_at": home.get("result_first_captured_at"),
                "result_capture_delay_seconds": home.get("result_capture_delay_seconds"),
            }
        )
    return None, fixture


def _history_identity(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return tuple(
        row.get(field)
        for field in (
            "fixture_id",
            "provider",
            "provider_fixture_id",
            "provider_league_id",
            "season",
            "kickoff_utc",
            "fixture_status",
            "team_identity_namespace",
            "team_side",
            "team_id",
            "opponent_team_id",
            "goals_for",
            "goals_against",
            "result_identity_hash",
            "raw_payload_sha256",
            "raw_captured_at",
            "result_first_captured_at",
            "result_capture_delay_seconds",
            "history_hash",
        )
    )


def _coherent_pair(home: Mapping[str, Any], away: Mapping[str, Any]) -> bool:
    same_fields = (
        "fixture_id",
        "provider",
        "provider_fixture_id",
        "provider_league_id",
        "season",
        "kickoff_utc",
        "fixture_status",
        "team_identity_namespace",
        "result_identity_hash",
        "raw_payload_sha256",
        "raw_captured_at",
        "result_first_captured_at",
        "result_capture_delay_seconds",
    )
    return (
        all(home.get(field) == away.get(field) for field in same_fields)
        and home.get("team_id") == away.get("opponent_team_id")
        and away.get("team_id") == home.get("opponent_team_id")
        and home.get("goals_for") == away.get("goals_against")
        and away.get("goals_for") == home.get("goals_against")
    )


def _fixture_fields(item: Mapping[str, Any]) -> dict[str, Any]:
    fixture = item.get("fixture")
    fixture = fixture if isinstance(fixture, Mapping) else {}
    league = item.get("league")
    league = league if isinstance(league, Mapping) else {}
    teams = item.get("teams")
    teams = teams if isinstance(teams, Mapping) else {}
    home = teams.get("home")
    home = home if isinstance(home, Mapping) else {}
    away = teams.get("away")
    away = away if isinstance(away, Mapping) else {}
    status = fixture.get("status")
    status = status if isinstance(status, Mapping) else {}
    goals = item.get("goals")
    goals = goals if isinstance(goals, Mapping) else {}
    return {
        "provider_fixture_id": str(fixture.get("id") or ""),
        "provider_league_id": str(league.get("id") or ""),
        "season": str(league.get("season") or ""),
        "kickoff_utc": _optional_utc(fixture.get("date")),
        "fixture_status": str(status.get("short") or "").upper(),
        "home_team_id": str(home.get("id") or ""),
        "away_team_id": str(away.get("id") or ""),
        "home_goals": _optional_int(goals.get("home")),
        "away_goals": _optional_int(goals.get("away")),
    }


def _fixture_signature(item: Mapping[str, Any]) -> tuple[Any, ...]:
    fields = _fixture_fields(item)
    return tuple(fields[field] for field in fields)


def _complete_terminal_result(fields: Mapping[str, Any]) -> bool:
    return (
        fields["fixture_status"] in FINISHED_FIXTURE_STATUSES
        and fields["home_goals"] is not None
        and fields["away_goals"] is not None
    )


def _history_rows(
    fields: Mapping[str, Any],
    *,
    raw_payload_sha256: str,
    raw_captured_at: datetime,
    result_first_captured_at: datetime,
    result_capture_delay_seconds: int,
) -> list[dict[str, Any]]:
    provider_fixture_id = str(fields["provider_fixture_id"])
    common = {
        "fixture_id": f"api_football:{provider_fixture_id}",
        "provider": "api_football",
        "provider_fixture_id": provider_fixture_id,
        "provider_league_id": str(fields["provider_league_id"]),
        "season": str(fields["season"]),
        "kickoff_utc": fields["kickoff_utc"],
        "fixture_status": str(fields["fixture_status"]),
        "team_identity_namespace": API_FOOTBALL_TEAM_ID_NAMESPACE,
        "result_identity_hash": _hash(
            "API_FOOTBALL_FIXTURE_RESULT",
            {
                "provider_fixture_id": provider_fixture_id,
                "fixture_status": str(fields["fixture_status"]),
                "home_goals": int(fields["home_goals"]),
                "away_goals": int(fields["away_goals"]),
            },
        ),
        "raw_payload_sha256": raw_payload_sha256,
        "raw_captured_at": raw_captured_at,
        "result_first_captured_at": result_first_captured_at,
        "result_capture_delay_seconds": result_capture_delay_seconds,
    }
    sides = (
        (
            "HOME",
            fields["home_team_id"],
            fields["away_team_id"],
            fields["home_goals"],
            fields["away_goals"],
        ),
        (
            "AWAY",
            fields["away_team_id"],
            fields["home_team_id"],
            fields["away_goals"],
            fields["home_goals"],
        ),
    )
    rows: list[dict[str, Any]] = []
    for side, team_id, opponent_team_id, goals_for, goals_against in sides:
        body = {
            **common,
            "team_side": side,
            "team_id": str(team_id),
            "opponent_team_id": str(opponent_team_id),
            "goals_for": int(goals_for),
            "goals_against": int(goals_against),
        }
        rows.append(
            {**body, "history_hash": _hash("FACTOR_MODEL_RAW_HISTORY_ROW", body)}
        )
    return rows


def _coverage_report(
    totals: Counter[str],
    by_scope: dict[tuple[str, str], Counter[str]],
    *,
    kickoff_from: datetime,
    kickoff_to: datetime,
    as_of: datetime,
    provider_league_id: str | None,
) -> dict[str, Any]:
    scope_metrics = (
        "selected_fixture_count",
        "eligible_finished_fixture_count",
        "history_row_count",
        "identity_missing_fixture_count",
        "unfinished_fixture_count",
        "result_missing_fixture_count",
        "late_result_fixture_count",
        "conflict_fixture_count",
        "out_of_window_fixture_count",
    )
    total_metrics = (
        "raw_payload_count",
        "raw_fixture_observation_count",
        "malformed_raw_payload_count",
        "malformed_fixture_item_count",
        "identity_missing_item_count",
        "not_known_at_as_of_fixture_count",
        "equivalent_latest_duplicate_count",
        *scope_metrics,
    )
    scope_rows = [
        {
            "provider_league_id": league_id or "MISSING",
            "season": season or "MISSING",
            **{metric: counts[metric] for metric in scope_metrics},
        }
        for (league_id, season), counts in sorted(by_scope.items())
    ]
    body = {
        "schema_version": RAW_HISTORY_COVERAGE_SCHEMA_VERSION,
        "provider": "api_football",
        "team_identity_namespace": API_FOOTBALL_TEAM_ID_NAMESPACE,
        "provider_league_filter": provider_league_id,
        "kickoff_from": kickoff_from,
        "kickoff_to": kickoff_to,
        "feature_as_of": as_of,
        "selection_policy": "LATEST_RAW_CAPTURE_STRICTLY_BEFORE_FEATURE_AS_OF",
        "late_result_threshold_seconds": int(LATE_RESULT_THRESHOLD.total_seconds()),
        "totals": {metric: totals[metric] for metric in total_metrics},
        "by_league_season": scope_rows,
        "provider_calls": 0,
        "database_writes": 0,
    }
    return {
        **body,
        "coverage_report_sha256": _hash("FACTOR_MODEL_RAW_HISTORY_COVERAGE", body),
    }


def _increment(
    totals: Counter[str],
    by_scope: dict[tuple[str, str], Counter[str]],
    metric: str,
    scope: tuple[str, str] | None,
    *,
    amount: int = 1,
) -> None:
    totals[metric] += amount
    if scope is not None:
        by_scope.setdefault(scope, Counter())[metric] += amount


def _common_scope(
    observations: list[_RawFixtureObservation],
) -> tuple[str, str] | None:
    scopes = {
        (fields["provider_league_id"], fields["season"])
        for fields in (_fixture_fields(row.item) for row in observations)
    }
    return next(iter(scopes)) if len(scopes) == 1 else None


def _valid_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in hexdigits for character in value)


def _optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_utc(value: Any) -> datetime | None:
    try:
        return _aware_utc(value, "fixture_kickoff")
    except (TypeError, ValueError):
        return None


def _hash(identity_type: str, body: Mapping[str, Any]) -> str:
    return canonical_sha256(
        {"identity_type": identity_type, **body},
        domain=HashDomain.PREMATCH_READ_MODEL_GENERIC,
    )


def _aware_utc(value: Any, field: str) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"PIT_HISTORY_{field.upper()}_NAIVE_OR_INVALID")
    return value.astimezone(UTC)
