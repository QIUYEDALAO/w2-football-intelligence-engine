from __future__ import annotations

import hashlib
import json
import os
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal

from w2.domain.recommendation_capabilities import load_recommendation_capability_manifest
from w2.domain.recommendation_decision_v3 import (
    RecommendationOutcomeV3,
    project_decision_v3,
)
from w2.strategy.market_selector import select_analysis_markets

POLICY_VERSION = "w2.matchday_intake_policy.v2"
MATCHDAY_FIXTURE_IDENTITY_VERSION = "MatchdayFixtureIdentityV1"
MATCHDAY_TEAM_CROSSWALK_VERSION = "MatchdayTeamCrosswalkV1"
MATCHDAY_ENDPOINT_CAPTURE_VERSION = "MatchdayEndpointCaptureV1"
MATCHDAY_MARKET_OBSERVATION_VERSION = "MatchdayMarketObservationV2"
MATCHDAY_MARKET_BATCH_AUDIT_VERSION = "MatchdayMarketBatchAuditV1"
MATCHDAY_EVIDENCE_MANIFEST_VERSION = "MatchdayEvidenceManifestV1"
MATCHDAY_ENRICHMENT_POLICY_VERSION = "MatchdayEnrichmentPolicyV1"

CHECKPOINT_STATUSES = {
    "PLANNED",
    "DUE",
    "CAPTURED",
    "PROVIDER_EMPTY",
    "FAILED",
    "MISSED",
    "SKIPPED_POLICY",
    "SKIPPED_BUDGET",
    "CONFLICT",
}
CANONICAL_OUTCOMES = {
    "NOT_READY",
    "NO_EDGE",
    "ANALYSIS_PICK",
    "FORMAL_RECOMMEND",
    "SYSTEM_DEGRADED",
}
REQUIRED_MATCHDAY_COMPETITIONS = frozenset(
    {
        "world_cup_2026",
        "brasileirao_serie_a",
        "chinese_super_league",
        "allsvenskan",
        "eliteserien",
    }
)
MANIFEST_HASH_EXCLUDED_FIELDS = frozenset({"manifest_hash", "audit"})


@dataclass(frozen=True, kw_only=True)
class MatchdayCheckpoint:
    name: str
    offset_seconds_before_kickoff: int
    endpoints: tuple[str, ...]
    grace_seconds: int
    enabled: bool = True


@dataclass(frozen=True, kw_only=True)
class MatchdayCompetitionPolicy:
    competition_id: str
    enabled: bool
    provider: str
    provider_league_id: str
    season: str
    discovery_horizon_hours: int
    fixture_status_allowlist: tuple[str, ...]
    checkpoints: tuple[MatchdayCheckpoint, ...]
    endpoint_matrix: dict[str, tuple[str, ...]]
    odds_max_age_seconds: int
    lineup_requirement: str
    request_caps: dict[str, int]
    provider_allowlist: tuple[str, ...]
    feature_enrichment_policy: dict[str, str]


@dataclass(frozen=True, kw_only=True)
class CheckpointPlan:
    fixture_id: str
    competition_id: str
    season: str
    checkpoint: str
    kickoff_utc: datetime
    scheduled_at: datetime
    window_start: datetime
    window_end: datetime
    endpoints: tuple[str, ...]
    status: str
    blockers: tuple[str, ...]
    policy_version: str = POLICY_VERSION
    missed_at: datetime | None = None
    capture_id: str | None = None
    current_unscheduled_capture_id: str | None = None

    @property
    def natural_identity(self) -> str:
        return ":".join(
            [
                self.fixture_id,
                self.competition_id,
                self.season,
                self.checkpoint,
                self.policy_version,
            ]
        )

    @property
    def plan_hash(self) -> str:
        return stable_hash(self.as_dict(exclude_hash=True))

    def as_dict(self, *, exclude_hash: bool = False) -> dict[str, Any]:
        payload = {
            "fixture_id": self.fixture_id,
            "competition_id": self.competition_id,
            "season": self.season,
            "policy_version": self.policy_version,
            "checkpoint": self.checkpoint,
            "kickoff_utc": iso_z(self.kickoff_utc),
            "scheduled_at": iso_z(self.scheduled_at),
            "window_start": iso_z(self.window_start),
            "window_end": iso_z(self.window_end),
            "endpoints": list(self.endpoints),
            "status": self.status,
            "missed_at": iso_z(self.missed_at) if self.missed_at else None,
            "capture_id": self.capture_id,
            "current_unscheduled_capture_id": self.current_unscheduled_capture_id,
            "blockers": list(self.blockers),
        }
        if not exclude_hash:
            payload["plan_hash"] = self.plan_hash
        return payload


@dataclass(frozen=True, kw_only=True)
class ExecutorResult:
    mode: str
    status: str
    provider_calls: int
    db_writes: int
    endpoint_captures: tuple[dict[str, Any], ...]
    manifests: tuple[dict[str, Any], ...]
    blockers: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "MatchdayIntakeExecutorV1",
            "mode": self.mode,
            "status": self.status,
            "provider_calls": self.provider_calls,
            "db_writes": self.db_writes,
            "endpoint_captures": list(self.endpoint_captures),
            "manifests": list(self.manifests),
            "blockers": list(self.blockers),
            "formal_ah": False,
            "formal_ou": False,
            "recommendation_lock": False,
            "production_recommendation": False,
            "official_captures": 0,
        }


def load_matchday_policy(
    path: Path = Path("config/policies/matchday_intake.v2.json"),
) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") != POLICY_VERSION:
        raise ValueError("MATCHDAY_POLICY_VERSION_INVALID")
    competition_ids = {
        str(item.get("competition_id"))
        for item in _list(payload.get("competitions"))
        if isinstance(item, Mapping)
    }
    missing = REQUIRED_MATCHDAY_COMPETITIONS - competition_ids
    if missing:
        raise ValueError("MATCHDAY_POLICY_NOT_AVAILABLE:" + ",".join(sorted(missing)))
    return dict(payload)


def competition_policies(payload: Mapping[str, Any]) -> dict[str, MatchdayCompetitionPolicy]:
    output = {}
    for item in _list(payload.get("competitions")):
        checkpoints = tuple(
            MatchdayCheckpoint(
                name=str(cp["name"]),
                offset_seconds_before_kickoff=int(cp["offset_seconds_before_kickoff"]),
                endpoints=tuple(str(endpoint) for endpoint in _list(cp.get("endpoints"))),
                grace_seconds=int(cp.get("grace_seconds", 0)),
                enabled=bool(cp.get("enabled") is True),
            )
            for cp in _list(item.get("checkpoints"))
        )
        endpoint_matrix = {
            str(key): tuple(str(endpoint) for endpoint in _list(value))
            for key, value in _mapping(item.get("endpoint_matrix")).items()
        }
        output[str(item["competition_id"])] = MatchdayCompetitionPolicy(
            competition_id=str(item["competition_id"]),
            enabled=bool(item.get("enabled") is True),
            provider=str(item["provider"]),
            provider_league_id=str(item["provider_league_id"]),
            season=str(item["season"]),
            discovery_horizon_hours=int(item["discovery_horizon_hours"]),
            fixture_status_allowlist=tuple(
                str(status) for status in _list(item.get("fixture_status_allowlist"))
            ),
            checkpoints=checkpoints,
            endpoint_matrix=endpoint_matrix,
            odds_max_age_seconds=int(item["odds_max_age_seconds"]),
            lineup_requirement=str(item["lineup_requirement"]),
            request_caps={str(k): int(v) for k, v in _mapping(item.get("request_caps")).items()},
            provider_allowlist=tuple(
                str(endpoint) for endpoint in _list(item.get("provider_allowlist"))
            ),
            feature_enrichment_policy={
                str(k): str(v) for k, v in _mapping(item.get("feature_enrichment_policy")).items()
            },
        )
    missing = REQUIRED_MATCHDAY_COMPETITIONS - set(output)
    if missing:
        raise ValueError("MATCHDAY_POLICY_NOT_AVAILABLE:" + ",".join(sorted(missing)))
    return output


def require_competition_policy(
    policies: Mapping[str, MatchdayCompetitionPolicy],
    competition_id: str,
) -> MatchdayCompetitionPolicy:
    policy = policies.get(competition_id)
    if policy is None or not policy.enabled:
        raise ValueError("MATCHDAY_POLICY_NOT_AVAILABLE")
    return policy


def policy_fingerprint(path: Path = Path("config/policies/matchday_intake.v2.json")) -> str:
    return sha256_bytes(path.read_bytes())


def build_checkpoint_plans(
    *,
    fixture_id: str,
    competition_id: str,
    season: str,
    kickoff_utc: datetime,
    now: datetime,
    policy: MatchdayCompetitionPolicy,
) -> list[CheckpointPlan]:
    current = normalize_utc(now)
    kickoff = normalize_utc(kickoff_utc)
    plans = []
    for checkpoint in policy.checkpoints:
        if not checkpoint.enabled:
            continue
        scheduled = kickoff - timedelta(seconds=checkpoint.offset_seconds_before_kickoff)
        window_start = scheduled
        window_end = scheduled + timedelta(seconds=checkpoint.grace_seconds)
        status = "PLANNED"
        blockers: tuple[str, ...] = ()
        missed_at = None
        if current > window_end:
            status = "MISSED"
            blockers = ("CHECKPOINT_MISSING",)
            missed_at = current
        elif window_start <= current <= window_end:
            status = "DUE"
        plans.append(
            CheckpointPlan(
                fixture_id=fixture_id,
                competition_id=competition_id,
                season=season,
                checkpoint=checkpoint.name,
                kickoff_utc=kickoff,
                scheduled_at=scheduled,
                window_start=window_start,
                window_end=window_end,
                endpoints=checkpoint.endpoints,
                status=status,
                blockers=blockers,
                missed_at=missed_at,
            )
        )
    return plans


def current_unscheduled_capture(
    *,
    fixture_id: str,
    competition_id: str,
    season: str,
    kickoff_utc: datetime,
    captured_at: datetime,
    endpoints: Sequence[str],
    reason: Literal["CURRENT_UNSCHEDULED_CAPTURE", "LATE_START_CURRENT_CAPTURE"],
) -> dict[str, Any]:
    captured = normalize_utc(captured_at)
    kickoff = normalize_utc(kickoff_utc)
    if captured >= kickoff:
        raise ValueError("POST_KICKOFF_CAPTURE_REJECTED")
    payload = {
        "schema_version": "MatchdayCurrentCaptureV1",
        "fixture_id": fixture_id,
        "competition_id": competition_id,
        "season": season,
        "capture_kind": reason,
        "captured_at": iso_z(captured),
        "kickoff_utc": iso_z(kickoff),
        "endpoints": list(endpoints),
        "completes_historical_checkpoint": False,
    }
    payload["capture_id"] = stable_hash(payload)
    return payload


def checkpoint_coverage(plans: Sequence[CheckpointPlan | Mapping[str, Any]]) -> dict[str, Any]:
    rows = [_plan_status(item) for item in plans]
    captured = sum(1 for status in rows if status == "CAPTURED")
    planned_count = len(rows)
    missed = sum(1 for status in rows if status == "MISSED")
    if planned_count == 0 or captured == 0:
        coverage = "NONE"
    elif captured == planned_count:
        coverage = "FULL"
    else:
        coverage = "PARTIAL"
    return {
        "checkpoint_coverage": coverage,
        "movement_readiness": "READY" if coverage == "FULL" else coverage,
        "captured": captured,
        "missed": missed,
        "planned": planned_count,
        "warning": "CHECKPOINT_HISTORY_PARTIAL" if coverage == "PARTIAL" else None,
    }


def fixture_discovery_from_payloads(
    payloads: Sequence[Mapping[str, Any]],
    *,
    policies: Mapping[str, MatchdayCompetitionPolicy],
    captured_at: datetime,
    source_payload_sha256: str,
    team_crosswalks: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    crosswalk_index = {
        (
            str(item.get("provider")),
            str(item.get("provider_team_id")),
            str(item.get("competition_id")),
            str(item.get("season")),
        ): item
        for item in team_crosswalks
        if item.get("review_status") == "APPROVED"
    }
    fixtures = []
    unsupported = []
    duplicates = 0
    conflicts = []
    seen: dict[str, dict[str, Any]] = {}
    for item in payloads:
        league = _mapping(item.get("league"))
        fixture = _mapping(item.get("fixture"))
        teams = _mapping(item.get("teams"))
        competition_id = _competition_id_for_provider_league(policies, str(league.get("id") or ""))
        if competition_id is None:
            unsupported.append(str(league.get("id") or "UNKNOWN"))
            continue
        policy = policies[competition_id]
        status = str(_mapping(fixture.get("status")).get("short") or "")
        if status not in policy.fixture_status_allowlist:
            continue
        provider_fixture_id = str(fixture.get("id") or "")
        kickoff = parse_utc(fixture.get("date"))
        home = _mapping(teams.get("home"))
        away = _mapping(teams.get("away"))
        if not provider_fixture_id or kickoff is None:
            continue
        home_provider_id = str(home.get("id") or "")
        away_provider_id = str(away.get("id") or "")
        home_mapping = crosswalk_index.get(
            (policy.provider, home_provider_id, competition_id, policy.season)
        )
        away_mapping = crosswalk_index.get(
            (policy.provider, away_provider_id, competition_id, policy.season)
        )
        identity_status = "READY"
        if home_mapping is None or away_mapping is None:
            identity_status = "TEAM_IDENTITY_NOT_READY"
        row = {
            "schema_version": MATCHDAY_FIXTURE_IDENTITY_VERSION,
            "fixture_id": f"{policy.provider}:{provider_fixture_id}",
            "provider": policy.provider,
            "provider_fixture_id": provider_fixture_id,
            "competition_id": competition_id,
            "provider_league_id": policy.provider_league_id,
            "season": policy.season,
            "kickoff_utc": iso_z(kickoff),
            "fixture_status": status,
            "home_provider_team_id": home_provider_id,
            "away_provider_team_id": away_provider_id,
            "home_w2_team_id": str(home_mapping.get("w2_team_id")) if home_mapping else None,
            "away_w2_team_id": str(away_mapping.get("w2_team_id")) if away_mapping else None,
            "fixture_identity_status": "READY",
            "team_identity_status": identity_status,
            "source_payload_sha256": source_payload_sha256,
            "captured_at": iso_z(captured_at),
        }
        row["identity_hash"] = stable_hash(row)
        previous = seen.get(provider_fixture_id)
        if previous is None:
            seen[provider_fixture_id] = row
            fixtures.append(row)
            continue
        if _fixture_conflict_identity(previous) == _fixture_conflict_identity(row):
            duplicates += 1
        else:
            conflicts.append(
                {
                    "provider_fixture_id": provider_fixture_id,
                    "status": "FIXTURE_IDENTITY_CONFLICT",
                    "conflict_hash": stable_hash([previous, row]),
                }
            )
    return {
        "candidate_fixtures": fixtures,
        "unsupported_competitions": sorted(set(unsupported)),
        "duplicate_fixtures": duplicates,
        "identity_conflicts": conflicts,
        "discovery_manifest_hash": stable_hash(
            {
                "fixtures": fixtures,
                "unsupported": sorted(set(unsupported)),
                "duplicates": duplicates,
                "conflicts": conflicts,
            }
        ),
    }


def team_crosswalk_contract(
    *,
    provider: str,
    provider_team_id: str,
    w2_team_id: str | None,
    competition_id: str,
    season: str,
    valid_from: datetime,
    valid_to: datetime | None,
    source: str,
    review_status: str,
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    if review_status == "APPROVED" and not w2_team_id:
        raise ValueError("APPROVED_CROSSWALK_REQUIRES_W2_TEAM_ID")
    payload = {
        "schema_version": MATCHDAY_TEAM_CROSSWALK_VERSION,
        "provider": provider,
        "provider_team_id": provider_team_id,
        "w2_team_id": w2_team_id,
        "competition_id": competition_id,
        "season": season,
        "valid_from": iso_z(valid_from),
        "valid_to": iso_z(valid_to) if valid_to else None,
        "source": source,
        "review_status": review_status,
        "evidence": dict(evidence),
    }
    payload["identity_hash"] = stable_hash(payload)
    return payload


def name_only_crosswalk_review(
    *,
    provider: str,
    provider_team_id: str,
    provider_name: str,
    competition_id: str,
    season: str,
    valid_from: datetime,
) -> dict[str, Any]:
    return team_crosswalk_contract(
        provider=provider,
        provider_team_id=provider_team_id,
        w2_team_id=None,
        competition_id=competition_id,
        season=season,
        valid_from=valid_from,
        valid_to=None,
        source="name_only_candidate",
        review_status="REVIEW_REQUIRED",
        evidence={"provider_name": provider_name, "auto_approved": False},
    )


def endpoint_params(
    endpoint: str,
    *,
    competition: MatchdayCompetitionPolicy,
    fixture_id: str | None = None,
) -> dict[str, str]:
    if endpoint == "status":
        return {}
    if endpoint == "fixtures":
        return {"league": competition.provider_league_id, "season": competition.season}
    if endpoint in {"odds", "lineups"}:
        if not fixture_id:
            raise ValueError(f"{endpoint.upper()}_REQUIRES_FIXTURE_ID")
        return {"fixture": fixture_id}
    if endpoint in {"injuries", "statistics"}:
        raise ValueError(f"ENDPOINT_DISABLED_BY_POLICY:{endpoint}")
    raise ValueError(f"ENDPOINT_UNAUTHORIZED:{endpoint}")


def endpoint_capture_contract(
    *,
    endpoint: str,
    params: Mapping[str, str],
    requested_at: datetime,
    provider_captured_at: datetime,
    status_code: int,
    elapsed_ms: int,
    payload: Mapping[str, Any],
    fixture_id: str | None = None,
    competition_id: str | None = None,
    checkpoint: str | None = None,
    attempt: int = 1,
    quota_values: Mapping[str, Any] | None = None,
    provider_event_time: str | None = None,
) -> dict[str, Any]:
    requested = normalize_utc(requested_at)
    captured = normalize_utc(provider_captured_at)
    if captured < requested - timedelta(minutes=10):
        raise ValueError("CAPTURED_AT_BEFORE_REQUEST_WINDOW")
    response = payload.get("response")
    response_count = len(response) if isinstance(response, list) else 0
    raw_sha = stable_hash(payload)
    status = "PROVIDER_EMPTY" if response_count == 0 and 200 <= status_code < 300 else "CAPTURED"
    if status_code >= 400:
        status = "FAILED"
    sanitized = sanitize_params(params)
    capture = {
        "schema_version": MATCHDAY_ENDPOINT_CAPTURE_VERSION,
        "fixture_id": fixture_id,
        "competition_id": competition_id,
        "checkpoint": checkpoint,
        "endpoint": endpoint,
        "sanitized_params": sanitized,
        "params_hash": stable_hash(sanitized),
        "request_task_key": request_task_key(endpoint, sanitized),
        "attempt": attempt,
        "requested_at": iso_z(requested),
        "provider_captured_at": iso_z(captured),
        "status_code": status_code,
        "elapsed_ms": elapsed_ms,
        "response_count": response_count,
        "quota_values": dict(quota_values or {}),
        "raw_payload_sha256": raw_sha,
        "provider_event_time": provider_event_time,
        "capture_status": status,
        "error_code": None if status != "FAILED" else "PROVIDER_HTTP_ERROR",
    }
    capture["capture_id"] = stable_hash(capture)
    return capture


def normalize_matchday_odds_payload(
    payload: Mapping[str, Any],
    *,
    captured_at: datetime,
    ingested_at: datetime,
    raw_payload_sha256: str,
    source_revision: str,
    capture_id: str,
    provider: str = "api_football",
    competition_id: str = "UNKNOWN",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for fixture in _list(payload.get("response")):
        fixture_id = str(
            _mapping(fixture.get("fixture")).get("id")
            or _mapping(payload.get("parameters")).get("fixture")
            or ""
        )
        for bookmaker in _list(fixture.get("bookmakers")):
            bookmaker_id = str(bookmaker.get("id") or bookmaker.get("name") or "")
            bookmaker_name = str(bookmaker.get("name") or bookmaker_id or "")
            if not bookmaker_id:
                rejected.append({"reason": "MISSING_BOOKMAKER", "fixture_id": fixture_id})
                continue
            for bet in _list(bookmaker.get("bets")):
                raw_market = str(bet.get("name") or "")
                market = canonical_market(raw_market)
                if market is None:
                    rejected.append(
                        {"reason": "UNSUPPORTED_MARKET", "raw_market_label": raw_market}
                    )
                    continue
                provider_bet_id = str(bet.get("id") or raw_market)
                for value in _list(bet.get("values")):
                    normalized = _normalize_value(
                        value,
                        market=market,
                        raw_market_label=raw_market,
                        fixture_id=fixture_id,
                    )
                    if "reason" in normalized:
                        rejected.append(normalized)
                        continue
                    row: dict[str, Any] = {
                        "schema_version": MATCHDAY_MARKET_OBSERVATION_VERSION,
                        "fixture_id": f"{provider}:{fixture_id}",
                        "provider_fixture_id": fixture_id,
                        "competition_id": competition_id,
                        "provider": provider,
                        "bookmaker_id": bookmaker_id,
                        "bookmaker_name": bookmaker_name,
                        "capture_batch_id": raw_payload_sha256,
                        "capture_id": capture_id,
                        "provider_bet_id": provider_bet_id,
                        "raw_market_label": raw_market,
                        "canonical_market": market,
                        "canonical_selection": normalized["selection"],
                        "provider_selection": normalized["provider_selection"],
                        "line": normalized["line"],
                        "decimal_odds": normalized["decimal_odds"],
                        "suspended": _truthy(value.get("suspended")),
                        "live": _truthy(value.get("live")),
                        "provider_updated_at": str(value.get("last_update") or ""),
                        "captured_at": iso_z(captured_at),
                        "ingested_at": iso_z(ingested_at),
                        "raw_payload_sha256": raw_payload_sha256,
                        "source_revision": source_revision,
                        "normalization_version": "matchday_market_observation.v2",
                    }
                    if row["suspended"]:
                        rejected.append({"reason": "SUSPENDED_QUOTE", "observation": row})
                        continue
                    if row["live"]:
                        rejected.append({"reason": "LIVE_QUOTE", "observation": row})
                        continue
                    row["observation_id"] = stable_hash(
                        {
                            "fixture_id": row["fixture_id"],
                            "provider": provider,
                            "bookmaker_id": bookmaker_id,
                            "capture_id": capture_id,
                            "market": market,
                            "selection": row["canonical_selection"],
                            "line": row["line"],
                            "odds": row["decimal_odds"],
                        }
                    )
                    rows.append(row)
    return _dedupe_observations(rows, rejected), rejected


def market_batch_audit(
    observations: Sequence[Mapping[str, Any]],
    *,
    evaluated_at: datetime,
    max_age_seconds: int,
    normalization_rejections: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    grouped: dict[tuple[str, str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in observations:
        grouped[
            (
                str(row.get("fixture_id")),
                str(row.get("provider")),
                str(row.get("bookmaker_id")),
                str(row.get("capture_batch_id")),
            )
        ].append(row)
    ah_candidates = []
    ou_candidates = []
    one_x_two_batches = []
    joint_ready = []
    rejections = [dict(item) for item in normalization_rejections]
    freshness = {}
    recommendation_max_age_seconds = min(max_age_seconds, 30 * 60)
    for key, rows in grouped.items():
        fixture_id, provider, bookmaker_id, batch_id = key
        fresh = freshness_status(
            rows,
            evaluated_at=evaluated_at,
            max_age_seconds=recommendation_max_age_seconds,
        )
        for row in rows:
            freshness[str(row.get("observation_id"))] = fresh
        ah = _ah_pair(rows)
        ou = _pair(rows, market="TOTALS", left="OVER", right="UNDER")
        one_x_two = _triplet(rows, market="1X2", selections=("HOME", "DRAW", "AWAY"))
        if ah:
            ah_candidates.append({**ah, "freshness": fresh})
        else:
            rejections.append(
                {
                    "fixture_id": fixture_id,
                    "bookmaker_id": bookmaker_id,
                    "reason": "AH_PAIR_INCOMPLETE",
                }
            )
        if ou:
            ou_candidates.append({**ou, "freshness": fresh})
        else:
            rejections.append(
                {
                    "fixture_id": fixture_id,
                    "bookmaker_id": bookmaker_id,
                    "reason": "OU_PAIR_INCOMPLETE",
                }
            )
        if one_x_two:
            one_x_two_batches.append({**one_x_two, "freshness": fresh})
        else:
            rejections.append(
                {
                    "fixture_id": fixture_id,
                    "bookmaker_id": bookmaker_id,
                    "reason": "ONE_X_TWO_INCOMPLETE",
                }
            )
        if ah and ou and one_x_two:
            joint_ready.append(
                {
                    "fixture_id": fixture_id,
                    "provider": provider,
                    "bookmaker_id": bookmaker_id,
                    "capture_batch_id": batch_id,
                    "status": "JOINT_MARKET_BASELINE_READY",
                    "ah": ah,
                    "ou": ou,
                    "one_x_two": one_x_two,
                    "freshness": fresh,
                }
            )
    joint_status = (
        "JOINT_MARKET_BASELINE_READY" if joint_ready else "JOINT_MARKET_BASELINE_INCOMPLETE"
    )
    payload = {
        "schema_version": MATCHDAY_MARKET_BATCH_AUDIT_VERSION,
        "ah_complete_sets": len(ah_candidates),
        "ou_complete_sets": len(ou_candidates),
        "one_x_two_complete_sets": len(one_x_two_batches),
        "same_family_joint_sets": len(joint_ready),
        "joint_status": joint_status,
        "ah_candidates": ah_candidates,
        "ou_candidates": ou_candidates,
        "one_x_two_batches": one_x_two_batches,
        "joint_market_baselines": joint_ready,
        "independent_candidates": [*ah_candidates, *ou_candidates],
        "rejections": rejections,
        "integrity_status": "CONFLICT"
        if any(item.get("reason") == "OBSERVATION_IDENTITY_CONFLICT" for item in rejections)
        else "PASS",
        "freshness": freshness,
        "collection_refresh_max_age_seconds": max_age_seconds,
        "recommendation_quote_max_age_seconds": recommendation_max_age_seconds,
    }
    payload["audit_hash"] = stable_hash(payload)
    return payload


def freshness_status(
    rows: Sequence[Mapping[str, Any]],
    *,
    evaluated_at: datetime,
    max_age_seconds: int,
) -> dict[str, Any]:
    captured_values = [parse_utc(row.get("captured_at")) for row in rows]
    captures = [value for value in captured_values if value is not None]
    if not rows or len(captures) != len(rows):
        return {
            "freshness_status": "INCOMPLETE",
            "captured_at": None,
            "evaluated_at": iso_z(evaluated_at),
            "age_seconds": None,
            "max_age_seconds": max_age_seconds,
        }
    if len({iso_z(item) for item in captures}) > 1:
        return {
            "freshness_status": "CONFLICT",
            "captured_at": None,
            "evaluated_at": iso_z(evaluated_at),
            "age_seconds": None,
            "max_age_seconds": max_age_seconds,
        }
    captured = captures[0]
    age = int((normalize_utc(evaluated_at) - captured).total_seconds())
    if age < 0:
        return {
            "freshness_status": "CONFLICT",
            "captured_at": iso_z(captured),
            "evaluated_at": iso_z(evaluated_at),
            "age_seconds": age,
            "max_age_seconds": max_age_seconds,
            "error_code": "CAPTURED_AT_AFTER_EVALUATION",
        }
    return {
        "freshness_status": "COMPLETE" if age <= max_age_seconds else "STALE",
        "captured_at": iso_z(captured),
        "evaluated_at": iso_z(evaluated_at),
        "age_seconds": age,
        "max_age_seconds": max_age_seconds,
    }


def enrichment_status(
    *,
    competition_policy: MatchdayCompetitionPolicy,
    endpoint: str,
    kickoff_utc: datetime,
    evaluated_at: datetime,
    payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if endpoint in {"injuries", "statistics"}:
        return {
            "schema_version": MATCHDAY_ENRICHMENT_POLICY_VERSION,
            "endpoint": endpoint,
            "status": competition_policy.feature_enrichment_policy.get(
                endpoint, "DISABLED_BY_POLICY"
            ),
            "as_of_safe_model_input": False,
        }
    if endpoint != "lineups":
        raise ValueError("UNSUPPORTED_ENRICHMENT_ENDPOINT")
    minutes_to_kickoff = int(
        (normalize_utc(kickoff_utc) - normalize_utc(evaluated_at)).total_seconds() // 60
    )
    if payload is None and minutes_to_kickoff > 60:
        status = "EXPECTED_NOT_AVAILABLE"
    else:
        response = _list(payload.get("response")) if payload else []
        status = "PROVIDER_EMPTY" if not response else _lineup_response_status(response)
    return {
        "schema_version": MATCHDAY_ENRICHMENT_POLICY_VERSION,
        "endpoint": "lineups",
        "requirement": competition_policy.lineup_requirement,
        "status": status,
        "blocks_analysis": (
            competition_policy.lineup_requirement == "STRICT" and status != "COMPLETE"
        ),
        "numeric_ah_adjustment_enabled": False,
        "numeric_ou_adjustment_enabled": False,
    }


def materialize_evidence_manifest(
    *,
    fixture_identity: Mapping[str, Any],
    competition_policy: MatchdayCompetitionPolicy,
    generated_at: datetime,
    checkpoint_plans: Sequence[CheckpointPlan | Mapping[str, Any]],
    endpoint_captures: Sequence[Mapping[str, Any]],
    market_audit: Mapping[str, Any],
    enrichments: Mapping[str, Any],
    model_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    movement = checkpoint_coverage(checkpoint_plans)
    decision = v3_decision_from_matchday(
        fixture_identity=fixture_identity,
        market_audit=market_audit,
        model_evidence=model_evidence,
        movement=movement,
        as_of=generated_at,
    )
    payload = {
        "schema_version": MATCHDAY_EVIDENCE_MANIFEST_VERSION,
        "fixture_identity": dict(fixture_identity),
        "team_crosswalk_state": fixture_identity.get(
            "team_identity_status", "TEAM_IDENTITY_NOT_READY"
        ),
        "competition_policy": {
            "policy_version": POLICY_VERSION,
            "competition_id": competition_policy.competition_id,
            "lineup_requirement": competition_policy.lineup_requirement,
            "enabled_checkpoints": [
                item.name for item in competition_policy.checkpoints if item.enabled
            ],
        },
        "kickoff_status": {
            "kickoff_utc": fixture_identity.get("kickoff_utc"),
            "fixture_status": fixture_identity.get("fixture_status"),
        },
        "generated_at": iso_z(generated_at),
        "as_of": iso_z(generated_at),
        "checkpoint_matrix": [
            item.as_dict() if isinstance(item, CheckpointPlan) else dict(item)
            for item in checkpoint_plans
        ],
        "endpoint_captures": [dict(item) for item in endpoint_captures],
        "market_evidence": dict(market_audit),
        "movement_evidence": movement,
        "enrichments": dict(enrichments),
        "model_evidence": dict(model_evidence),
        "decision": decision,
        "audit": {},
        "formal_readiness": False,
        "recommendation_lock": False,
        "official_capture": False,
    }
    payload["input_manifest_hash"] = stable_hash(
        {
            "fixture_identity": payload["fixture_identity"],
            "checkpoint_matrix": payload["checkpoint_matrix"],
            "endpoint_captures": payload["endpoint_captures"],
            "market_evidence_hash": market_audit.get("audit_hash"),
            "model_evidence": payload["model_evidence"],
        }
    )
    payload["audit"] = {
        "input_manifest_hash": payload["input_manifest_hash"],
        "source_refs": {
            "endpoint_capture_hashes": [
                capture.get("raw_payload_sha256") for capture in endpoint_captures
            ],
        },
    }
    payload["manifest_hash"] = canonical_manifest_hash(payload)
    payload["audit"]["manifest_hash"] = payload["manifest_hash"]
    if payload["decision"]["outcome"] == "SYSTEM_DEGRADED":
        payload["audit"]["manifest_integrity_status"] = "SYSTEM_DEGRADED"
    else:
        payload["audit"]["manifest_integrity_status"] = "PASS"
    return payload


def canonical_manifest_hash(manifest: Mapping[str, Any]) -> str:
    return stable_hash(
        {key: value for key, value in manifest.items() if key not in MANIFEST_HASH_EXCLUDED_FIELDS}
    )


def validate_manifest_identity(manifest: Mapping[str, Any]) -> str:
    expected = canonical_manifest_hash(manifest)
    audit_hash = _mapping(manifest.get("audit")).get("manifest_hash")
    if manifest.get("manifest_hash") != expected or audit_hash != expected:
        raise ValueError("MANIFEST_IDENTITY_CONFLICT")
    return expected


def v3_decision_from_matchday(
    *,
    fixture_identity: Mapping[str, Any],
    market_audit: Mapping[str, Any],
    model_evidence: Mapping[str, Any],
    movement: Mapping[str, Any],
    as_of: datetime,
) -> dict[str, Any]:
    selected_candidate = _selected_analysis_candidate(model_evidence)
    if market_audit.get("integrity_status") == "CONFLICT":
        outcome = RecommendationOutcomeV3.SYSTEM_DEGRADED
        reason = "INTEGRITY_CONFLICT"
    elif fixture_identity.get("team_identity_status") != "READY":
        outcome = RecommendationOutcomeV3.NOT_READY
        reason = "TEAM_IDENTITY_NOT_READY"
    elif not market_audit.get("independent_candidates"):
        outcome = RecommendationOutcomeV3.NOT_READY
        reason = "CURRENT_QUOTE_MISSING"
    elif _selected_candidate_stale(selected_candidate):
        outcome = RecommendationOutcomeV3.NOT_READY
        reason = "CURRENT_QUOTE_STALE"
    elif model_evidence.get("status") != "COMPLETE":
        outcome = RecommendationOutcomeV3.NOT_READY
        reason = "MODEL_EVIDENCE_NOT_READY"
    elif not _truthy(_mapping(model_evidence.get("comparison")).get("analysis_direction_allowed")):
        outcome = RecommendationOutcomeV3.NO_EDGE
        reason = "NO_ANALYSIS_EDGE"
    elif selected_candidate is None:
        outcome = RecommendationOutcomeV3.NO_EDGE
        reason = "NO_ANALYSIS_EDGE"
    else:
        outcome = RecommendationOutcomeV3.ANALYSIS_PICK
        reason = "ANALYSIS_ONLY"
    selected = selected_candidate if outcome is RecommendationOutcomeV3.ANALYSIS_PICK else None
    evaluated_candidate = selected_candidate or _evaluated_candidate_from_model(model_evidence)
    if outcome is RecommendationOutcomeV3.FORMAL_RECOMMEND:
        raise AssertionError("FORMAL_RECOMMEND_DISABLED_FOR_MATCHDAY_INTAKE_V2")
    warnings = []
    if movement.get("checkpoint_coverage") == "PARTIAL":
        warnings.append("CHECKPOINT_HISTORY_PARTIAL")
    contract = {
        "fixture_id": fixture_identity.get("fixture_id"),
        "competition_id": fixture_identity.get("competition_id"),
        "as_of": iso_z(as_of),
        "integrity_status": "CONFLICT"
        if outcome is RecommendationOutcomeV3.SYSTEM_DEGRADED
        else "PASS",
        "quote_provenance_status": "VALID",
        "data_status": "READY" if outcome is RecommendationOutcomeV3.ANALYSIS_PICK else "PARTIAL",
        "decision_tier": outcome.value,
        "reason_code": reason,
        "model_version": str(model_evidence.get("model_version") or ""),
        "calibration_version": str(model_evidence.get("calibration_version") or ""),
        "selected_market_candidate": evaluated_candidate,
        "pick": selected,
        "warnings": warnings,
    }
    decision = project_decision_v3(
        contract,
        manifest=load_recommendation_capability_manifest(),
    ).as_dict()
    decision["reason_code"] = reason
    decision["reason"] = reason
    decision["formal_readiness"] = False
    decision["capability_status"] = "ANALYSIS_ONLY"
    return decision


def execute_matchday_intake(
    *,
    mode: Literal["DRY_RUN", "SAVED_PAYLOAD_REPLAY", "CONTROLLED_PROVIDER_CANARY"],
    fixture_ids: Sequence[str] = (),
    approve_provider_calls: bool = False,
    hard_cap: int = 10,
    saved_payloads: Sequence[Mapping[str, Any]] = (),
) -> ExecutorResult:
    if mode == "DRY_RUN":
        return ExecutorResult(
            mode=mode,
            status="DRY_RUN_READY",
            provider_calls=0,
            db_writes=0,
            endpoint_captures=(),
            manifests=(),
            blockers=(),
        )
    if mode == "SAVED_PAYLOAD_REPLAY":
        captures = tuple(
            endpoint_capture_contract(
                endpoint=str(payload.get("endpoint", "fixtures")),
                params=_mapping(payload.get("params")),
                requested_at=parse_utc(payload.get("requested_at"))
                or _raise_invalid_replay_time("INVALID_REQUESTED_AT"),
                provider_captured_at=parse_utc(payload.get("captured_at"))
                or _raise_invalid_replay_time("INVALID_CAPTURED_AT"),
                status_code=int(payload.get("status_code", 200)),
                elapsed_ms=int(payload.get("elapsed_ms", 0)),
                payload=_mapping(payload.get("payload")),
            )
            for payload in saved_payloads
        )
        return ExecutorResult(
            mode=mode,
            status="REPLAY_VALIDATED",
            provider_calls=0,
            db_writes=0,
            endpoint_captures=captures,
            manifests=(),
            blockers=(),
        )
    authorized = (
        approve_provider_calls
        and os.environ.get("W2_MATCHDAY_CANARY_APPROVED") == "true"
        and len(fixture_ids) > 0
        and hard_cap <= 10
    )
    if not authorized:
        return ExecutorResult(
            mode=mode,
            status="PROVIDER_CANARY_NOT_EXECUTED_NO_AUTHORIZATION",
            provider_calls=0,
            db_writes=0,
            endpoint_captures=(),
            manifests=(),
            blockers=("PROVIDER_CANARY_NOT_EXECUTED_NO_AUTHORIZATION",),
        )
    return ExecutorResult(
        mode=mode,
        status="CONTROLLED_PROVIDER_CANARY_AUTHORIZED_BUT_NOT_IMPLEMENTED_IN_UNIT_PORT",
        provider_calls=0,
        db_writes=0,
        endpoint_captures=(),
        manifests=(),
        blockers=("PROVIDER_PORT_NOT_BOUND",),
    )


def public_manifest_read(manifest: Mapping[str, Any]) -> dict[str, Any]:
    return {"provider_calls": 0, "db_writes": 0, "manifest": dict(manifest)}


def _raise_invalid_replay_time(code: str) -> datetime:
    raise ValueError(code)


def stable_hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def parse_utc(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return normalize_utc(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def normalize_utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)


def iso_z(value: datetime) -> str:
    return normalize_utc(value).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sanitize_params(params: Mapping[str, str]) -> dict[str, str]:
    blocked = {"key", "api_key", "token", "password", "authorization"}
    return {
        key: ("REDACTED" if key.lower() in blocked else str(value)) for key, value in params.items()
    }


def request_task_key(endpoint: str, params: Mapping[str, str]) -> str:
    return "matchday-intake:" + endpoint + ":" + stable_hash(params)[:16]


def canonical_market(raw_market: str) -> str | None:
    key = raw_market.strip().upper().replace(" ", "_")
    if key in {"MATCH_WINNER", "1X2"}:
        return "1X2"
    if key in {"ASIAN_HANDICAP", "AH"}:
        return "ASIAN_HANDICAP"
    if key in {"GOALS_OVER/UNDER", "TOTALS", "OU"}:
        return "TOTALS"
    return None


def _normalize_value(
    value: Mapping[str, Any],
    *,
    market: str,
    raw_market_label: str,
    fixture_id: str,
) -> dict[str, Any]:
    price = decimal_odds(value.get("odd"))
    if price is None:
        return {
            "reason": "INVALID_ODDS",
            "fixture_id": fixture_id,
            "raw_market_label": raw_market_label,
        }
    provider_selection = str(value.get("value") or "")
    try:
        selection, line = parse_selection(provider_selection, market)
    except ValueError as exc:
        return {
            "reason": str(exc),
            "fixture_id": fixture_id,
            "provider_selection": provider_selection,
            "raw_market_label": raw_market_label,
        }
    return {
        "provider_selection": provider_selection,
        "selection": selection,
        "line": line,
        "decimal_odds": price,
    }


def parse_selection(text: str, market: str) -> tuple[str, str | None]:
    raw = text.strip()
    lowered = raw.lower()
    if market == "1X2":
        if lowered in {"home", "1"}:
            return "HOME", None
        if lowered in {"draw", "x"}:
            return "DRAW", None
        if lowered in {"away", "2"}:
            return "AWAY", None
        raise ValueError("INVALID_SELECTION")
    parts = raw.split()
    head = parts[0].lower() if parts else ""
    line = decimal_line(parts[-1]) if len(parts) > 1 else decimal_line(raw)
    if market == "TOTALS":
        if head in {"over", "o"} and line is not None:
            return "OVER", line
        if head in {"under", "u"} and line is not None:
            return "UNDER", line
        raise ValueError("INVALID_LINE" if line is None else "INVALID_SELECTION")
    if market == "ASIAN_HANDICAP":
        if head in {"home", "1"} and line is not None:
            return "HOME", line
        if head in {"away", "2"} and line is not None:
            return "AWAY", line
        raise ValueError("INVALID_LINE" if line is None else "INVALID_SELECTION")
    raise ValueError("UNSUPPORTED_MARKET")


def decimal_line(value: Any) -> str | None:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if parsed * Decimal("4") != (parsed * Decimal("4")).to_integral_value():
        return None
    return str(parsed.normalize())


def decimal_odds(value: Any) -> str | None:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if parsed <= Decimal("1"):
        return None
    return str(parsed.normalize())


def _ah_pair(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    home_rows = [
        row
        for row in rows
        if row.get("canonical_market") == "ASIAN_HANDICAP"
        and row.get("canonical_selection") == "HOME"
    ]
    away_rows = [
        row
        for row in rows
        if row.get("canonical_market") == "ASIAN_HANDICAP"
        and row.get("canonical_selection") == "AWAY"
    ]
    for home in sorted(home_rows, key=lambda item: str(item.get("line"))):
        home_line = _decimal_or_none(home.get("line"))
        if home_line is None:
            continue
        for away in away_rows:
            away_line = _decimal_or_none(away.get("line"))
            if away_line is not None and home_line + away_line == Decimal("0"):
                return {
                    "market": "ASIAN_HANDICAP",
                    "line": str(home_line.normalize()),
                    "left": dict(home),
                    "right": dict(away),
                    "status": "COMPLETE",
                }
    return None


def _pair(
    rows: Sequence[Mapping[str, Any]],
    *,
    market: str,
    left: str,
    right: str,
) -> dict[str, Any] | None:
    by_line: dict[str, dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for row in rows:
        if row.get("canonical_market") != market:
            continue
        by_line[str(row.get("line"))][str(row.get("canonical_selection"))] = row
    for line, selections in sorted(by_line.items()):
        if left in selections and right in selections:
            return {
                "market": market,
                "line": line,
                "left": dict(selections[left]),
                "right": dict(selections[right]),
                "status": "COMPLETE",
            }
    return None


def _triplet(
    rows: Sequence[Mapping[str, Any]],
    *,
    market: str,
    selections: tuple[str, str, str],
) -> dict[str, Any] | None:
    found = {
        str(row.get("canonical_selection")): row
        for row in rows
        if row.get("canonical_market") == market
    }
    if all(selection in found for selection in selections):
        return {
            "market": market,
            "selections": {key: dict(found[key]) for key in selections},
            "status": "COMPLETE",
        }
    return None


def _decimal_or_none(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _dedupe_observations(
    rows: Sequence[dict[str, Any]],
    rejections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for row in rows:
        existing = seen.get(str(row["observation_id"]))
        if existing is not None and existing != row:
            rejections.append(
                {
                    "reason": "OBSERVATION_IDENTITY_CONFLICT",
                    "observation_id": row["observation_id"],
                    "existing_hash": stable_hash(existing),
                    "incoming_hash": stable_hash(row),
                }
            )
            continue
        seen[str(row["observation_id"])] = row
    return [seen[key] for key in sorted(seen)]


def _selected_candidate_stale(candidate: Mapping[str, Any] | None) -> bool:
    fresh = _mapping(candidate.get("freshness")) if candidate else {}
    return fresh.get("freshness_status") in {"STALE", "INCOMPLETE", "CONFLICT"}


def _evaluated_candidate_from_model(model_evidence: Mapping[str, Any]) -> dict[str, Any] | None:
    if model_evidence.get("status") != "COMPLETE":
        return None
    comparison = _mapping(model_evidence.get("comparison"))
    return {
        "market": str(model_evidence.get("market") or "ASIAN_HANDICAP"),
        "selection": model_evidence.get("selection"),
        "line": model_evidence.get("line"),
        "model_status": "READY",
        "analysis_evidence": {
            "status": "COMPLETE",
            "model_probability": model_evidence.get("model_probability"),
            "market_probability": model_evidence.get("market_probability"),
            "probability_delta": model_evidence.get("probability_delta"),
            "expected_value": model_evidence.get("expected_value"),
            "uncertainty": model_evidence.get("uncertainty"),
            "comparison": {
                "analysis_direction_allowed": _truthy(
                    comparison.get("analysis_direction_allowed")
                )
            },
        },
    }


def _selected_analysis_candidate(model_evidence: Mapping[str, Any]) -> dict[str, Any] | None:
    candidates = _list(model_evidence.get("analysis_markets"))
    selectable = []
    for item in candidates:
        if not isinstance(item, Mapping):
            continue
        evidence = _mapping(item.get("analysis_evidence"))
        if evidence.get("status") != "COMPLETE":
            continue
        score = _decimal_or_none(item.get("decision_score") or item.get("signal_strength"))
        if score is None:
            continue
        selectable.append(
            {
                **dict(item),
                "analysis_evidence": dict(evidence),
                "decision": str(item.get("decision") or "ANALYSIS_PICK"),
                "decision_score": float(score),
                "line_status": str(item.get("line_status") or "READY"),
                "market_candidate": item.get("market_candidate") or {"ev_eligible": True},
                "quote_age_seconds": int(item.get("quote_age_seconds") or 0),
                "calibration_comparable": item.get("calibration_comparable") is True,
            }
        )
    selection = select_analysis_markets(selectable)
    if selection.primary_market is None:
        return None
    for item in selectable:
        if item.get("market") == selection.primary_market:
            return item
    return None


def _lineup_response_status(response: Sequence[Any]) -> str:
    teams = [item for item in response if isinstance(item, Mapping)]
    return "COMPLETE" if len(teams) >= 2 else "CONFLICT"


def _competition_id_for_provider_league(
    policies: Mapping[str, MatchdayCompetitionPolicy], provider_league_id: str
) -> str | None:
    for competition_id, policy in policies.items():
        if policy.provider_league_id == provider_league_id and policy.enabled:
            return competition_id
    return None


def _fixture_conflict_identity(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        row.get("provider_fixture_id"),
        row.get("competition_id"),
        row.get("kickoff_utc"),
        row.get("home_provider_team_id"),
        row.get("away_provider_team_id"),
    )


def _plan_status(item: CheckpointPlan | Mapping[str, Any]) -> str:
    return item.status if isinstance(item, CheckpointPlan) else str(item.get("status"))


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _truthy(value: Any) -> bool:
    return value is True or str(value).lower() in {"true", "1", "yes"}
