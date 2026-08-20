"""Projection-only production read service.

The API reads materialized payloads from ``read_model_checkpoint``. Analysis
features, pricing and simulation remain write-side concerns and are never
recomputed in a request.
"""

from __future__ import annotations

import os
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from time import monotonic
from typing import Any, Literal, cast

from pydantic import ValidationError
from sqlalchemy import func, literal, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from w2.api.schemas import (
    PerformanceCohortProjection,
    PerformanceFixtureProjection,
    PerformanceResponse,
    PerformanceWindowProjection,
)
from w2.competitions.league_whitelist_scope import load_league_whitelist_scope
from w2.competitions.registry import CompetitionRegistry, CompetitionRegistryError
from w2.config import get_settings
from w2.dashboard.date_strip import build_persisted_date_strip, next_available_date
from w2.dashboard.date_window import (
    FOOTBALL_DAY_CUTOFF_HOUR,
    FOOTBALL_DAY_TZ,
    default_football_day,
    football_day_window,
)
from w2.dashboard.factor_checklist import MIN_XG_MATCHES
from w2.dashboard.performance import dashboard_performance
from w2.dashboard.results import FINISHED_STATUSES, normalize_match_status
from w2.dashboard.validation_summary import validation_summary
from w2.domain.decision_card import compute_card_hash
from w2.domain.odds import settle_asian_handicap, settle_total_goals
from w2.domain.recommendation_capabilities import load_recommendation_capability_manifest
from w2.domain.recommendation_decision_v4 import (
    RecommendationOutcomeV4,
    build_recommendation_decision_v4,
    validate_decision_v4_identity,
)
from w2.identity.public_team_labels import (
    pending_public_team_labels,
    reviewed_public_team_labels,
)
from w2.infrastructure.database import create_engine
from w2.infrastructure.persistence.api_models import ReadModelCheckpointModel
from w2.infrastructure.persistence.dynamic_prematch_models import (
    DynamicPrematchEvaluationModel,
    DynamicPrematchOpportunityModel,
    DynamicPrematchSupersessionModel,
)
from w2.infrastructure.persistence.factor_model_models import (
    CanonicalTeamModel,
)
from w2.infrastructure.persistence.future_refresh_models import TeamXgMatchModel
from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayCheckpointPlanModel,
    MatchdayEndpointCaptureModel,
    MatchdayEndpointCapturePlanModel,
    MatchdayFixtureIdentityModel,
    MatchdayMarketObservationModel,
)
from w2.infrastructure.persistence.model_forecast_models import (
    ModelForecastCaptureDataVersionModel,
    ModelForecastCaptureModel,
    ModelForecastOutcomeModel,
    model_forecast_fixture_aliases,
)
from w2.infrastructure.persistence.models import ResultModel
from w2.infrastructure.persistence.outcome_ledger_models import OutcomeLedgerModel
from w2.lineups.intelligence import lineup_requirement
from w2.matchday.timezone import (
    BEIJING_TZ,
    BeijingOperationalDayPolicy,
    FixtureOperationalDateResolver,
    next_7_days_window,
    next_36_hours_window,
)
from w2.operations.leagues import run_top_five_audit
from w2.operations.release_evidence import build_release_identity
from w2.prematch.evaluation_slots import EvaluationSlotError, is_evaluation_slot
from w2.prematch.read_model_projection import (
    ANALYSIS_CARD_SHADOW_PREFIX,
    FrozenAnalysisError,
    validate_frozen_analysis_payload,
)
from w2.providers.quota import api_football_quota_policy, parse_int
from w2.settlement.settle import WIN_UNITS
from w2.tracking.forward_ledger_performance import (
    MIN_DECISIVE_SAMPLES_FOR_RATE,
    SAMPLE_TARGET,
)
from w2.tracking.performance_scoring import ece

MAX_PUBLIC_FIXTURES = 512
MODEL_FORECAST_LEAD_TIME_BUCKETS = (
    "LT_6H",
    "H6_TO_LT_24H",
    "D1_TO_D3",
    "GT_3D",
)
MODEL_FORECAST_MARKETS = ("ASIAN_HANDICAP", "TOTALS")


CHECKPOINT_OPPORTUNITY_SCOPE = "CHECKPOINT_EVALUATION_OPPORTUNITY_V2"
CHECKPOINT_OPPORTUNITY_SEMANTICS = "CHECKPOINT_EVALUATION_OPPORTUNITY"


def _opportunity_contract_defect(row: DynamicPrematchEvaluationModel) -> str | None:
    """Why a row claiming to be official is not usable, or None if it is.

    Only rows that assert ``official_funnel_eligible`` are judged here.  A row
    that makes the claim and then fails it is a writer defect, and reporting it
    as "no opportunity" would repeat the mistake this whole rework exists to
    undo: a failure rendered as absence.
    """

    if row.denominator_scope != CHECKPOINT_OPPORTUNITY_SCOPE:
        return "SCOPE_MISMATCH"
    if row.measurement_semantics != CHECKPOINT_OPPORTUNITY_SEMANTICS:
        return "SEMANTICS_MISMATCH"
    if row.market not in MODEL_FORECAST_MARKETS:
        return "MARKET_NOT_REGISTERED"
    # The odds-snapshot capture_id cannot stand in here: two model tracks
    # reading the same quote would collapse into one opportunity.
    if not row.model_forecast_capture_identity_hash:
        return "FORECAST_CAPTURE_IDENTITY_MISSING"
    policy = str(row.evaluation_policy_version or "")
    slot = str(row.evaluation_slot_id or "")
    if not policy:
        return "POLICY_VERSION_MISSING"
    if not slot:
        return "SLOT_MISSING"
    try:
        if not is_evaluation_slot(slot, policy_version=policy):
            return "SLOT_NOT_REGISTERED"
    except EvaluationSlotError:
        return "POLICY_NOT_REGISTERED"
    return None


def _model_forecast_market_evaluation_funnel(
    captures: Sequence[ModelForecastCaptureModel],
    evaluations: Sequence[DynamicPrematchEvaluationModel],
    superseded_evaluation_ids: set[str],
    opportunities: Sequence[DynamicPrematchOpportunityModel] | None = None,
) -> dict[str, Any]:
    """Rates come from opportunities that exist, never from ones inferred.

    The previous shape multiplied captures by markets and then read every
    fixture x market with no row as "all gates failed, entry not traversed".
    That turns silence into evidence: a fixture whose checkpoints have not come
    due yet is indistinguishable from one that genuinely failed mainline
    parsing.  With no opportunity writer in production the whole grid resolved
    that way, which would have published a 100%-model / 0%-everything funnel
    describing nothing.
    """

    current: dict[tuple[str, str, str, str], DynamicPrematchEvaluationModel] = {}
    opportunity_hashes = (
        {row.opportunity_identity_hash for row in opportunities}
        if opportunities is not None
        else None
    )
    defects: Counter[str] = Counter()
    for row in evaluations:
        if row.evaluation_id in superseded_evaluation_ids:
            continue
        if row.official_funnel_eligible is not True:
            # Legacy rows and ordinary dynamic evaluations were never
            # opportunities; excluding them silently is correct.
            continue
        if (
            opportunity_hashes is not None
            and row.opportunity_identity_hash not in opportunity_hashes
        ):
            defects["OPPORTUNITY_ROW_MISSING"] += 1
            continue
        defect = _opportunity_contract_defect(row)
        if defect is not None:
            defects[defect] += 1
            continue
        # One opportunity per slot x market; retries within a slot supersede
        # rather than accumulate, so the denominator counts chances, not tries.
        # Identity is the opportunity: the frozen model track, the policy that
        # scheduled it, the slot, and the market.  Anything coarser merges
        # tracks; anything keyed on the quote splits a slot across retries.
        key = (
            str(row.model_forecast_capture_identity_hash),
            str(row.evaluation_policy_version),
            str(row.evaluation_slot_id),
            row.market,
        )
        previous = current.get(key)
        if previous is None or (row.evaluated_at, row.evaluation_id) > (
            previous.evaluated_at,
            previous.evaluation_id,
        ):
            current[key] = row

    gate_names = (
        "model_ready",
        "mainline_parsed",
        "bookmaker_depth",
        "quote_fresh",
        "evaluated",
        "no_edge",
        "candidate",
    )
    counts = Counter({name: 0 for name in gate_names})
    first_failed: Counter[str] = Counter()
    recorded_at = 0
    for row in current.values():
        gates, blocker = _dynamic_gate_results(row)
        recorded_at += int(row.recorded_at is not None)
        counts.update(name for name in gate_names if gates[name])
        if blocker:
            first_failed[blocker] += 1

    if opportunities is not None:
        evaluated_opportunities = {
            str(row.opportunity_identity_hash)
            for row in current.values()
            if row.opportunity_identity_hash
        }
        for opportunity in opportunities:
            if opportunity.opportunity_identity_hash not in evaluated_opportunities:
                first_failed[str(opportunity.state)] += 1

    denominator = len(opportunities) if opportunities is not None else len(current)
    fixture_ids = {
        row.fixture_id.removeprefix("api_football:")
        for row in (opportunities if opportunities is not None else current.values())
    }
    # A broken official row is neither a measurement nor an absence.  Surfacing
    # it as INVALID keeps "the writer is wrong" distinguishable from "nothing has
    # happened yet".
    if defects:
        status = "INVALID"
    elif denominator > 0:
        status = "MEASURABLE"
    else:
        status = "NOT_MEASURABLE"
    measurable = status == "MEASURABLE"
    return {
        "scope": CHECKPOINT_OPPORTUNITY_SCOPE,
        "denominator_unit": "CHECKPOINT_EVALUATION_OPPORTUNITY_SLOT_X_MARKET",
        "measurement_status": status,
        "invalid_opportunity_row_count": sum(defects.values()),
        "invalid_opportunity_reasons": dict(sorted(defects.items())),
        "opportunity_count": denominator,
        "fixture_count": len(fixture_ids),
        "market_unit_count": denominator,
        "persisted_market_unit_count": denominator,
        "recorded_at_count": (
            sum(int(row.recorded_at is not None) for row in opportunities)
            if opportunities is not None
            else recorded_at
        ),
        "capture_count": len({row.fixture_id for row in captures}),
        "gate_counts": dict(counts) if measurable else {},
        # Null, not zeroes: a rate of 0.0 asserts the gate was tested and failed.
        "gate_rates": (
            {name: round(counts[name] / denominator, 6) for name in gate_names}
            if measurable
            else None
        ),
        "first_failed_gate_counts": dict(sorted(first_failed.items())),
    }


def _dynamic_gate_results(
    row: DynamicPrematchEvaluationModel,
) -> tuple[dict[str, bool], str | None]:
    """Only a real row has gate results.

    This used to accept None and answer "model ready, everything else failed,
    entry not traversed" -- turning a fixture whose checkpoints had not come due
    into a reported failure.  The type now forbids the call, so the shape cannot
    be resurrected by a future refactor.
    """

    empty = {
        "model_ready": True,
        "mainline_parsed": False,
        "bookmaker_depth": False,
        "quote_fresh": False,
        "evaluated": False,
        "no_edge": False,
        "candidate": False,
    }
    if isinstance(row.gate_results, dict):
        gates = {name: bool(row.gate_results.get(name)) for name in empty}
        return gates, row.first_failed_gate
    payload = row.payload if isinstance(row.payload, dict) else {}
    state = str(payload.get("state") or row.original_state)
    evaluated = state in {"ANALYSIS_PICK_ACTIVE", "NO_EDGE_CURRENT"}
    return {
        "model_ready": state != "NOT_READY_MODEL_INPUT",
        "mainline_parsed": payload.get("exact_line") is not None,
        "bookmaker_depth": False,
        "quote_fresh": state
        not in {
            "NOT_READY_SOURCE_ABSENT",
            "NOT_READY_QUOTE_INCOMPLETE",
            "STALE_PENDING_REFRESH",
        },
        "evaluated": evaluated,
        "no_edge": state == "NO_EDGE_CURRENT",
        "candidate": state == "ANALYSIS_PICK_ACTIVE",
    }, "LEGACY_GATE_ATTRIBUTION_UNAVAILABLE"


class SystemDegradedError(RuntimeError):
    """The authoritative read model cannot be read or validated."""

    code = "SYSTEM_DEGRADED"


@dataclass(frozen=True)
class Checkpoint:
    key: str
    source_hash: str
    created_at: datetime
    payload: dict[str, Any]


@dataclass(frozen=True)
class CompetitionIdentity:
    competition_id: str
    name: str
    scope_group: str


def _parse_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def _iso_or_none(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _collection_window(
    plans: list[MatchdayCheckpointPlanModel],
    satisfied_plan_ids: set[str],
    reference: datetime,
) -> tuple[MatchdayCheckpointPlanModel | None, str | None, bool]:
    ordered = sorted(plans, key=lambda plan: (_utc(plan.scheduled_at), plan.plan_id))
    due = [plan for plan in ordered if _utc(plan.scheduled_at) <= reference]
    future = [plan for plan in ordered if _utc(plan.scheduled_at) > reference]
    target = due[-1] if due and due[-1].plan_id not in satisfied_plan_ids else None
    cause = "AWAITING_COLLECTION" if target is not None else None
    if target is None and future:
        target = future[0]
        cause = "NOT_YET_DUE"
    overdue = bool(
        cause == "AWAITING_COLLECTION"
        and target is not None
        and reference > _utc(target.window_end)
    )
    return target, cause, overdue


def _checkpoint_metadata(row: Checkpoint) -> dict[str, Any]:
    return {
        "checkpoint_key": row.key,
        "source_hash": row.source_hash,
        "created_at": row.created_at.isoformat().replace("+00:00", "Z"),
    }


def _public_team_label_from_identity(
    *,
    fixture: MatchdayFixtureIdentityModel,
    side: Literal["home", "away"],
    canonical: Mapping[str, CanonicalTeamModel],
    reviewed_labels: Mapping[str, str] | None = None,
    pending_labels: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    provider_team_id = str(getattr(fixture, f"{side}_provider_team_id"))
    w2_team_id = getattr(fixture, f"{side}_w2_team_id")
    payload = fixture.payload if isinstance(fixture.payload, dict) else {}
    raw_provider_name = next(
        (
            str(value).strip()
            for key in (f"{side}_team_name", f"{side}_name")
            if (value := payload.get(key))
        ),
        None,
    )
    identity_status = str(fixture.team_identity_status or "").upper()
    if "AMBIGUOUS" in identity_status:
        state = "AMBIGUOUS"
    elif not w2_team_id or w2_team_id not in canonical:
        state = "IDENTITY_UNRESOLVED"
    else:
        configured_label = (reviewed_labels or {}).get(w2_team_id)
        chinese_name = (
            str(configured_label).strip()
            if configured_label
            and any("\u4e00" <= char <= "\u9fff" for char in str(configured_label))
            else None
        )
        if chinese_name:
            return {
                "display_name": chinese_name,
                "state": "CHINESE_LABEL_READY",
                "canonical_team_id": w2_team_id,
                "provider_team_id": provider_team_id,
                "raw_provider_name": raw_provider_name,
            }
        pending_label = (pending_labels or {}).get(w2_team_id)
        if pending_label:
            return {
                "display_name": str(pending_label).strip(),
                "state": "CHINESE_LABEL_PENDING_OWNER_REVIEW",
                "canonical_team_id": w2_team_id,
                "provider_team_id": provider_team_id,
                "raw_provider_name": raw_provider_name,
            }
        state = "CANONICAL_IDENTITY_READY_LABEL_MISSING"
    return {
        "display_name": None,
        "state": state,
        "canonical_team_id": str(w2_team_id) if w2_team_id else None,
        "provider_team_id": provider_team_id,
        "raw_provider_name": raw_provider_name,
    }


def _official_funnel_recommendations(
    evaluations: Sequence[DynamicPrematchEvaluationModel],
    opportunities: Sequence[DynamicPrematchOpportunityModel],
    fixtures: Mapping[str, MatchdayFixtureIdentityModel],
    results: Mapping[str, ResultModel],
    public_team_labels: Mapping[str, Mapping[str, Mapping[str, Any]]],
) -> list[dict[str, Any]]:
    """Project picks whose last official opportunity is still a candidate."""

    final_opportunities = _final_official_opportunities(opportunities)

    latest: dict[tuple[str, str], DynamicPrematchEvaluationModel] = {}
    for row in evaluations:
        payload = row.payload if isinstance(row.payload, dict) else {}
        if (
            row.official_funnel_eligible is not True
            or payload.get("state") != "ANALYSIS_PICK_ACTIVE"
        ):
            continue
        fixture_id = str(row.fixture_id).removeprefix("api_football:")
        key = (fixture_id, str(row.market))
        final = final_opportunities.get(key)
        if (
            final is None
            or final.state != "EVALUATED_CANDIDATE"
            or row.opportunity_identity_hash != final.opportunity_identity_hash
            or row.attempt_identity_hash != final.latest_attempt_identity_hash
        ):
            continue
        previous = latest.get(key)
        if previous is None or (row.evaluated_at, row.evaluation_id) > (
            previous.evaluated_at,
            previous.evaluation_id,
        ):
            latest[key] = row

    projected: list[dict[str, Any]] = []
    for (fixture_id, market), row in latest.items():
        payload = row.payload
        fixture = fixtures.get(fixture_id)
        canonical_fixture_id = (
            str(fixture.fixture_id) if fixture is not None else f"api_football:{fixture_id}"
        )
        result = results.get(canonical_fixture_id)
        line = str(payload["exact_line"])
        decimal_odds = Decimal(str(payload["decimal_odds"]))
        outcome = None
        profit_units = None
        if result is not None:
            if market == "ASIAN_HANDICAP":
                outcome = settle_asian_handicap(
                    result.home_goals,
                    result.away_goals,
                    str(row.selection),
                    Decimal(line),
                ).value
            elif market == "TOTALS":
                outcome = settle_total_goals(
                    result.home_goals + result.away_goals,
                    str(row.selection),
                    Decimal(line),
                ).value
            else:
                raise ValueError(f"unsupported official recommendation market {market}")
            units = WIN_UNITS[outcome]
            profit_units = units * (decimal_odds - 1) if units > 0 else units

        labels: dict[str, dict[str, Any]] = {}
        for side in ("home", "away"):
            team_label = dict(public_team_labels.get(fixture_id, {}).get(side, {}))
            if not team_label:
                team_label = {
                    "display_name": None,
                    "state": "IDENTITY_UNRESOLVED",
                    "canonical_team_id": None,
                    "provider_team_id": None,
                    "raw_provider_name": None,
                }
            teams = (
                fixture.payload.get("teams")
                if fixture is not None and isinstance(fixture.payload, dict)
                else None
            )
            team = teams.get(side) if isinstance(teams, dict) else None
            if not team_label.get("raw_provider_name") and isinstance(team, dict):
                team_label["raw_provider_name"] = str(team.get("name") or "").strip() or None
            labels[side] = team_label

        projected.append(
            {
                "evaluation_id": row.evaluation_id,
                "fixture_id": fixture_id,
                "evaluated_at": _iso_or_none(row.evaluated_at),
                "kickoff_utc": _iso_or_none(fixture.kickoff_utc) if fixture else None,
                "market": market,
                "selection": str(row.selection),
                "exact_line": line,
                "decimal_odds": float(decimal_odds),
                "home_team_label": labels["home"],
                "away_team_label": labels["away"],
                "score": (
                    f"{result.home_goals}-{result.away_goals}" if result is not None else None
                ),
                "settlement": outcome or "PENDING",
                "profit_units": float(profit_units) if profit_units is not None else None,
            }
        )
    return sorted(
        projected,
        key=lambda item: (
            str(item.get("kickoff_utc") or ""),
            str(item["fixture_id"]),
            str(item["market"]),
        ),
    )


def _final_official_opportunities(
    opportunities: Sequence[DynamicPrematchOpportunityModel],
) -> dict[tuple[str, str], DynamicPrematchOpportunityModel]:
    final_opportunities: dict[tuple[str, str], DynamicPrematchOpportunityModel] = {}
    for row in opportunities:
        fixture_id = str(row.fixture_id).removeprefix("api_football:")
        key = (fixture_id, str(row.market))
        previous = final_opportunities.get(key)
        if previous is None or (
            row.scheduled_checkpoint_at,
            row.recorded_at,
            row.opportunity_identity_hash,
        ) > (
            previous.scheduled_checkpoint_at,
            previous.recorded_at,
            previous.opportunity_identity_hash,
        ):
            final_opportunities[key] = row
    return final_opportunities


def _apply_repository_v4_authority(card: dict[str, Any]) -> dict[str, Any]:
    decision_value = card.get("recommendation_decision_v4")
    authority_missing = not isinstance(decision_value, dict) or not decision_value
    fallback_reason_code = str(card.get("reason_code") or "CURRENT_V4_AUTHORITY_MISSING")
    fallback_non_pick = card.get("non_pick")
    fallback_reason_human = (
        str(fallback_non_pick.get("reason_human") or "当前推荐缺少 V4 权威身份")
        if isinstance(fallback_non_pick, dict)
        else "当前推荐缺少 V4 权威身份"
    )
    if authority_missing:
        decision = build_recommendation_decision_v4(
            {
                "fixture_id": card.get("fixture_id"),
                "competition_id": card.get("competition_id"),
                "season": card.get("season"),
                "kickoff_utc": card.get("kickoff_utc"),
            }
        ).as_dict()
        card["recommendation_decision_v4"] = decision
    else:
        decision = cast(dict[str, Any], decision_value)
    card["recommendation_decision_v3_role"] = "HISTORY_ONLY"
    try:
        validate_decision_v4_identity(decision)
    except ValueError as exc:
        raise SystemDegradedError("RECOMMENDATION_DECISION_V4_INVALID") from exc
    outcome = str(decision.get("outcome") or "")
    tier = {
        RecommendationOutcomeV4.FORMAL_RECOMMEND.value: "RECOMMEND",
        RecommendationOutcomeV4.ANALYSIS_PICK.value: "ANALYSIS_PICK",
        RecommendationOutcomeV4.NO_EDGE.value: "SKIP",
        RecommendationOutcomeV4.NOT_READY.value: "NOT_READY",
    }.get(outcome)
    if tier is None:
        raise SystemDegradedError("RECOMMENDATION_DECISION_V4_OUTCOME_INVALID")
    selected = decision.get("selected_candidate")
    pick = (
        {
            "market": selected.get("market"),
            "selection": selected.get("selection"),
            "line": selected.get("exact_line"),
            "odds": selected.get("decimal_odds"),
            "fair_odds": selected.get("fair_odds"),
            "expected_value": selected.get("expected_value"),
            "uncertainty": selected.get("uncertainty"),
            "value_edge": selected.get("cashflow_price_edge"),
            "key_factors": ["同一权威候选五态现金流定价"],
            "risks": ["ANALYSIS_ONLY_FORMAL_DISABLED"] if tier == "ANALYSIS_PICK" else [],
            "invalidation": "EXACT_QUOTE_IDENTITY_OR_MODEL_INPUT_CHANGED",
            "disclaimer": "分析参考·非稳赢；production 动作需 RECOMMEND",
        }
        if isinstance(selected, dict) and tier in {"ANALYSIS_PICK", "RECOMMEND"}
        else None
    )
    if (tier in {"ANALYSIS_PICK", "RECOMMEND"}) != (pick is not None):
        raise SystemDegradedError("RECOMMENDATION_DECISION_V4_PICK_INVALID")
    reason_value = decision.get("reason")
    reason = reason_value if isinstance(reason_value, dict) else {}
    projected_reason_code = (
        fallback_reason_code if authority_missing else str(reason.get("code") or "")
    )
    projected_reason_human = (
        fallback_reason_human if authority_missing else str(reason.get("message") or "证据尚未就绪")
    )
    projected_non_pick = (
        None
        if pick is not None
        else {
            "reason_code": projected_reason_code or "NOT_READY",
            "reason_human": projected_reason_human,
            "action": "等待下一次权威证据刷新",
            "next_eval_at": None,
        }
    )
    contract_value = card.get("decision_contract")
    contract = dict(contract_value) if isinstance(contract_value, dict) else {}
    contract.update(
        {
            "decision_tier": tier,
            "data_status": "BLOCKED" if tier == "NOT_READY" else "READY",
            "outcome_tracked": pick is not None,
            "lock_eligible": False,
            "recommendation_id": None,
            "pick": pick,
            "non_pick": projected_non_pick,
            "reason_code": projected_reason_code,
            "action": "MONITOR" if pick is not None else "WAIT",
            "recommendation_authority": "RECOMMENDATION_DECISION_V4",
        }
    )
    if contract:
        contract["card_hash"] = compute_card_hash(contract)
        card["decision_contract"] = contract
    card.update(
        {
            "decision_tier": tier,
            "data_status": contract.get("data_status"),
            "outcome_tracked": pick is not None,
            "lock_eligible": False,
            "recommendation_id": None,
            "pick": pick,
            "non_pick": projected_non_pick,
            "reason_code": contract.get("reason_code"),
            "action": contract.get("action"),
            "card_hash": contract.get("card_hash"),
            "recommendation_decision_v3_role": "HISTORY_ONLY",
        }
    )
    return card


def _projection_is_system_degraded(card: dict[str, Any]) -> bool:
    health = card.get("projection_health")
    return isinstance(health, dict) and health.get("status") == "SYSTEM_DEGRADED"


def _performance_cohort_key(*, league: str | None, tier: str) -> str:
    if league and tier != "ALL":
        return f"performance:cohort:league-tier:{league}:{tier}"
    if league:
        return f"performance:cohort:league:{league}"
    if tier != "ALL":
        return f"performance:cohort:tier:{tier}"
    return "performance:cohort:all"


def _performance_tier_row(
    tier: str,
    window: PerformanceWindowProjection,
) -> dict[str, Any]:
    return {
        "tier": tier,
        "finished_result_count": window.finished_result_count,
        "scored_count": window.scored_count,
        "canonical_settled_count": window.canonical_settled_count,
        "canonical_hit_rate": window.canonical_hit_rate,
        "canonical_hit_rate_status": window.canonical_hit_rate_status,
        "clv_mean": window.clv_mean,
        "clv_positive_share": window.clv_positive_share,
    }


def _checkpoint_clv(window: PerformanceWindowProjection) -> dict[str, Any]:
    sample_count = window.clv_sample_count
    return {
        "sample_count": sample_count,
        "candidate_count": sample_count,
        "missing_count": max(window.canonical_settled_count - sample_count, 0),
        "median_decimal": window.clv_median,
        "positive_count": window.clv_positive_count,
        "negative_count": max(sample_count - window.clv_positive_count, 0),
        "push_count": 0,
        "line_changed_count": 0,
        "stale_closing_count": 0,
        "insufficient_snapshot_count": max(
            window.canonical_settled_count - sample_count,
            0,
        ),
        "method": window.clv_method,
    }


def _checkpoint_outcomes(window: PerformanceWindowProjection) -> dict[str, Any]:
    return {
        "settled_sample_count": window.canonical_settled_count,
        "hit_count": window.canonical_hit_count,
        "miss_count": window.canonical_miss_count,
        "push_count": window.canonical_push_count,
        "void_count": window.canonical_void_count,
        "decisive_count": window.canonical_decisive_count,
        "hit_rate": window.canonical_hit_rate,
    }


def _checkpoint_league_row(
    competition_id: str,
    cohort: PerformanceCohortProjection,
    identities: dict[str, CompetitionIdentity],
    *,
    checkpoint_key: str,
) -> dict[str, Any]:
    window = cohort.windows["90d"]
    identity = identities.get(competition_id)
    canonical_id = identity.competition_id if identity else ""
    canonical_name = identity.name if identity else ""
    return {
        "competition_id": canonical_id or competition_id,
        "canonical_competition_id": canonical_id or None,
        "competition_name": canonical_name or None,
        "source_league": competition_id,
        "source_aliases": [competition_id],
        "source_checkpoint_keys": [checkpoint_key],
        "scope_group": identity.scope_group if identity else "UNRESOLVED",
        "aggregation_status": "SOURCE_CHECKPOINT",
        "identity_status": "RESOLVED" if canonical_id and canonical_name else "UNRESOLVED",
        "league": canonical_id or competition_id,
        "processed_count": window.fixture_checkpoint_count,
        "eligible_count": window.canonical_settled_count,
        "excluded_count": max(
            window.fixture_checkpoint_count - window.canonical_settled_count,
            0,
        ),
        "decisive_count": window.canonical_decisive_count,
        "outcomes": _checkpoint_outcomes(window),
        "clv": _checkpoint_clv(window),
        "rate_status": (
            "AVAILABLE" if window.canonical_hit_rate_status == "AVAILABLE" else "INSUFFICIENT"
        ),
        "model_brier": window.model_brier,
        "model_log_loss": window.model_log_loss,
        "model_ece": window.model_ece,
    }


def _competition_identity_authority() -> dict[str, CompetitionIdentity]:
    """Read existing runtime identity authority; unresolved rows remain fail-closed."""
    try:
        entries = CompetitionRegistry().entries()
    except CompetitionRegistryError:
        return {}
    identities: dict[str, CompetitionIdentity] = {}
    for competition_id, entry in entries.items():
        name = str(entry.profile_payload.get("name") or competition_id)
        identity = CompetitionIdentity(
            competition_id=competition_id,
            name=name,
            scope_group=str(getattr(entry, "scope_group", "") or ""),
        )
        identities[competition_id] = identity
        provider_id = str(entry.provider_mapping.get("api_football_league_id") or "")
        if provider_id:
            identities[provider_id] = identity
    return identities


def _mean_fixture_metric(rows: Sequence[Mapping[str, Any]], field: str) -> float | None:
    values = [float(row[field]) for row in rows if isinstance(row.get(field), int | float)]
    return sum(values) / len(values) if values else None


def _fixture_observations(
    rows: Sequence[Mapping[str, Any]],
) -> list[tuple[tuple[float, float, float], int]]:
    outcomes = {"HOME": 0, "DRAW": 1, "AWAY": 2}
    observations: list[tuple[tuple[float, float, float], int]] = []
    for row in rows:
        raw = row.get("model_probabilities")
        actual = outcomes.get(str(row.get("actual_outcome") or "").upper())
        if not isinstance(raw, Sequence) or isinstance(raw, str | bytes) or actual is None:
            continue
        values = tuple(float(value) for value in raw if isinstance(value, int | float))
        if len(values) == 3:
            observations.append((values, actual))
    return observations


def _fixture_league_row(
    identity: CompetitionIdentity | None,
    rows: Sequence[Mapping[str, Any]],
    *,
    source_aliases: Sequence[str],
    source_checkpoint_keys: Sequence[str],
) -> dict[str, Any]:
    unique = {str(row.get("fixture_id") or ""): row for row in rows if row.get("fixture_id")}
    fixtures = list(unique.values())
    outcomes = Counter(
        str(row.get("canonical_settlement_outcome") or "").upper()
        for row in fixtures
        if str(row.get("canonical_settlement_outcome") or "").upper()
        in {"HIT", "MISS", "PUSH", "VOID"}
    )
    decisive = outcomes["HIT"] + outcomes["MISS"]
    canonical_id = identity.competition_id if identity else ""
    fallback = sorted(set(source_aliases))[0] if source_aliases else "UNKNOWN"
    return {
        "competition_id": canonical_id or fallback,
        "canonical_competition_id": canonical_id or None,
        "competition_name": identity.name if identity else None,
        "source_league": fallback,
        "source_aliases": sorted(set(source_aliases)),
        "source_checkpoint_keys": sorted(set(source_checkpoint_keys)),
        "scope_group": identity.scope_group if identity else "UNRESOLVED",
        "aggregation_status": "FIXTURE_RECONSTRUCTED",
        "identity_status": "RESOLVED" if identity else "UNRESOLVED",
        "league": canonical_id or fallback,
        "processed_count": len(fixtures),
        "eligible_count": sum(outcomes.values()),
        "excluded_count": max(len(fixtures) - sum(outcomes.values()), 0),
        "decisive_count": decisive,
        "outcomes": {
            "settled_sample_count": sum(outcomes.values()),
            "hit_count": outcomes["HIT"],
            "miss_count": outcomes["MISS"],
            "push_count": outcomes["PUSH"],
            "void_count": outcomes["VOID"],
            "decisive_count": decisive,
            "hit_rate": outcomes["HIT"] / decisive if decisive else None,
        },
        "clv": {},
        "rate_status": (
            "AVAILABLE" if decisive >= MIN_DECISIVE_SAMPLES_FOR_RATE else "INSUFFICIENT"
        ),
        "model_brier": _mean_fixture_metric(fixtures, "model_brier"),
        "model_log_loss": _mean_fixture_metric(fixtures, "model_log_loss"),
        "model_ece": ece(_fixture_observations(fixtures)),
    }


def _aggregation_conflict_row(
    identity: CompetitionIdentity | None,
    *,
    source_aliases: Sequence[str],
    source_checkpoint_keys: Sequence[str],
) -> dict[str, Any]:
    fallback = sorted(set(source_aliases))[0] if source_aliases else "UNKNOWN"
    canonical_id = identity.competition_id if identity else ""
    return {
        "competition_id": canonical_id or fallback,
        "canonical_competition_id": canonical_id or None,
        "competition_name": identity.name if identity else None,
        "source_league": fallback,
        "source_aliases": sorted(set(source_aliases)),
        "source_checkpoint_keys": sorted(set(source_checkpoint_keys)),
        "scope_group": identity.scope_group if identity else "UNRESOLVED",
        "aggregation_status": "CONFLICT",
        "identity_status": "RESOLVED" if identity else "UNRESOLVED",
        "league": canonical_id or fallback,
        "processed_count": 0,
        "eligible_count": 0,
        "excluded_count": 0,
        "decisive_count": 0,
        "outcomes": {
            "settled_sample_count": 0,
            "hit_count": 0,
            "miss_count": 0,
            "push_count": 0,
            "void_count": 0,
            "decisive_count": 0,
            "hit_rate": None,
        },
        "clv": {},
        "rate_status": "INSUFFICIENT",
        "model_brier": None,
        "model_log_loss": None,
        "model_ece": None,
    }


def _canonical_performance_rows(
    cohorts: Mapping[str, tuple[Checkpoint, PerformanceCohortProjection]],
    fixture_rows: Sequence[Checkpoint],
    identities: Mapping[str, CompetitionIdentity],
    *,
    anchor: datetime,
) -> list[dict[str, Any]]:
    prefix = "performance:cohort:league:"
    sources: dict[str, list[tuple[str, Checkpoint, PerformanceCohortProjection]]] = defaultdict(
        list
    )
    identity_by_group: dict[str, CompetitionIdentity | None] = {}
    for key, (checkpoint, cohort) in cohorts.items():
        if not key.startswith(prefix) or key.startswith("performance:cohort:league-tier:"):
            continue
        alias = key.removeprefix(prefix)
        identity = identities.get(alias)
        group = identity.competition_id if identity else f"UNRESOLVED:{alias}"
        sources[group].append((alias, checkpoint, cohort))
        identity_by_group[group] = identity

    fixtures: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    fixture_checkpoint_keys: dict[str, list[str]] = defaultdict(list)
    for checkpoint in fixture_rows:
        try:
            fixture = PerformanceFixtureProjection.model_validate(checkpoint.payload)
        except ValidationError:
            continue
        if not anchor - timedelta(days=90) <= fixture.kickoff_utc.astimezone(UTC) <= anchor:
            continue
        identity = identities.get(fixture.league)
        group = identity.competition_id if identity else f"UNRESOLVED:{fixture.league}"
        fixtures[group].append(fixture.model_dump())
        fixture_checkpoint_keys[group].append(checkpoint.key)
        identity_by_group[group] = identity

    result: list[dict[str, Any]] = []
    for group in sorted(set(sources) | set(fixtures)):
        source_rows = sources.get(group, [])
        aliases = [alias for alias, _, _ in source_rows]
        checkpoint_keys = [checkpoint.key for _, checkpoint, _ in source_rows]
        identity = identity_by_group.get(group)
        if fixtures.get(group):
            result.append(
                _fixture_league_row(
                    identity,
                    fixtures[group],
                    source_aliases=[
                        *aliases,
                        *(str(row.get("league") or "") for row in fixtures[group]),
                    ],
                    source_checkpoint_keys=[
                        *checkpoint_keys,
                        *fixture_checkpoint_keys[group],
                    ],
                )
            )
        elif len(source_rows) == 1:
            alias, checkpoint, cohort = source_rows[0]
            result.append(
                _checkpoint_league_row(
                    alias,
                    cohort,
                    dict(identities),
                    checkpoint_key=checkpoint.key,
                )
            )
        else:
            result.append(
                _aggregation_conflict_row(
                    identity,
                    source_aliases=aliases,
                    source_checkpoint_keys=checkpoint_keys,
                )
            )
    return result


def _checkpoint_probability(window: PerformanceWindowProjection) -> dict[str, Any]:
    status = (
        "AVAILABLE"
        if window.sample_progress_status == "TARGET_REACHED"
        else "SAMPLE_BUILDING"
        if window.scored_count
        else "INSUFFICIENT"
    )
    return {
        "status": status,
        "sample_count": window.scored_count,
        "model_brier": window.model_brier,
        "market_brier": window.market_brier,
        "model_minus_market_brier": window.model_minus_market_brier,
        "model_log_loss": window.model_log_loss,
        "market_log_loss": window.market_log_loss,
        "model_minus_market_log_loss": window.model_minus_market_log_loss,
        "model_ece": window.model_ece,
        "market_ece": window.market_ece,
        "model_reliability_bins": [row.model_dump() for row in window.model_reliability_bins],
        "market_reliability_bins": [row.model_dump() for row in window.market_reliability_bins],
    }


def _dashboard_forward_ledger_from_checkpoints(
    rows: list[Checkpoint],
    *,
    fixture_rows: Sequence[Checkpoint] = (),
) -> dict[str, Any] | None:
    """Adapt bounded performance checkpoints to the Dashboard ledger contract."""
    cohorts: dict[str, tuple[Checkpoint, PerformanceCohortProjection]] = {}
    try:
        for row in rows:
            cohorts[row.key] = (row, PerformanceCohortProjection.model_validate(row.payload))
    except ValidationError:
        return None
    selected = cohorts.get("performance:cohort:all")
    if selected is None:
        return None
    selected_row, global_cohort = selected
    window = global_cohort.windows["90d"]
    if global_cohort.checkpoint_key != selected_row.key or not selected_row.source_hash:
        return None
    identities = _competition_identity_authority()
    competitions = _canonical_performance_rows(
        cohorts,
        fixture_rows,
        identities,
        anchor=global_cohort.scoring_window_anchor.astimezone(UTC),
    )
    leagues = [
        row for row in competitions if row["scope_group"] in {"top_five", "national_leagues"}
    ]
    tournaments = [
        row for row in competitions if row["scope_group"] not in {"top_five", "national_leagues"}
    ]
    processed = window.fixture_checkpoint_count
    eligible = window.canonical_settled_count
    excluded = max(processed - eligible, 0)
    outcomes = _checkpoint_outcomes(window)
    clv = _checkpoint_clv(window)
    anchor = global_cohort.scoring_window_anchor.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return {
        "schema_version": "w2.dashboard_forward_ledger_projection.v1",
        "source": "performance_checkpoint",
        "sample_target": window.sample_target,
        "record_count": processed,
        "fixture_count": processed,
        "settled_sample_count": eligible,
        "hit_count": window.canonical_hit_count,
        "miss_count": window.canonical_miss_count,
        "push_count": window.canonical_push_count,
        "void_count": window.canonical_void_count,
        "hit_rate": window.canonical_hit_rate,
        "validation_fixture_count": processed,
        "validation_settled_fixture_count": processed,
        "validation_pending_fixture_count": 0,
        "validation_pending_status": {
            "waiting_finish_count": 0,
            "postponed_count": 0,
            "result_missing_count": 0,
            "settlement_error_count": 0,
            "details": [],
        },
        "outcomes_validation": outcomes,
        "outcomes_canonical": outcomes,
        "probability_validation": _checkpoint_probability(window),
        "performance_cohort": {
            "validation_count": processed,
            "processed_count": processed,
            "eligible_count": eligible,
            "excluded_count": excluded,
            "recovered_count": 0,
            "pending_count": 0,
            "outcomes": outcomes,
            "clv": clv,
            "by_league": leagues,
            "by_tournament": tournaments,
            "exclusions": [],
            "recoveries": [],
            "integrity_status": "PASS",
            "invariants": {
                "processed_equals_eligible_plus_excluded": processed == eligible + excluded,
                "eligible_equals_canonical_outcomes": eligible
                == window.canonical_hit_count
                + window.canonical_miss_count
                + window.canonical_push_count
                + window.canonical_void_count,
            },
        },
        "outcomes": outcomes,
        "outcomes_shadow": {
            "settled_sample_count": 0,
            "hit_count": 0,
            "miss_count": 0,
            "push_count": 0,
            "void_count": 0,
            "hit_rate": None,
        },
        "canonical_settled_fixture_count": eligible,
        "canonical_excluded_count": excluded,
        "canonical_excluded_by_reason": window.not_scorable_by_reason,
        "validation_excluded_count": excluded,
        "validation_excluded_by_reason": window.not_scorable_by_reason,
        "evidence_window": {
            "first_capture_at": None,
            "latest_capture_at": None,
            "latest_outcome_at": anchor,
        },
        "accumulation_label": f"历史评分 checkpoint {eligible}/{window.sample_target}",
        "clv": clv,
        "by_league": [],
        "by_league_validation": [],
        "mock_data": False,
        "checkpoint_metadata": _checkpoint_metadata(selected_row),
    }


class ReadModelRepository:
    """Single production read authority backed by ``read_model_checkpoint``."""

    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine

    def _database_engine(self) -> Engine:
        if self._engine is None:
            self._engine = create_engine()
        return self._engine

    def _dashboard_competition_ids(self) -> tuple[str, ...]:
        try:
            scope = load_league_whitelist_scope(CompetitionRegistry(engine=self._database_engine()))
        except CompetitionRegistryError as exc:
            raise SystemDegradedError("COMPETITION_WHITELIST_UNAVAILABLE") from exc
        if len(scope.all_whitelist) != 13:
            raise SystemDegradedError("COMPETITION_WHITELIST_INVALID")
        return scope.all_whitelist

    def checkpoints(self, prefix: str) -> list[Checkpoint]:
        try:
            with Session(self._database_engine()) as session:
                rows = session.scalars(
                    select(ReadModelCheckpointModel)
                    .where(ReadModelCheckpointModel.checkpoint_key.like(f"{prefix}%"))
                    .order_by(ReadModelCheckpointModel.checkpoint_key)
                ).all()
        except SQLAlchemyError as exc:
            raise SystemDegradedError("READ_MODEL_CHECKPOINT_QUERY_FAILED") from exc
        return [
            Checkpoint(
                key=row.checkpoint_key,
                source_hash=row.source_hash,
                created_at=row.created_at,
                payload=row.payload,
            )
            for row in rows
        ]

    def checkpoint(self, key: str) -> Checkpoint | None:
        try:
            with Session(self._database_engine()) as session:
                row = session.scalar(
                    select(ReadModelCheckpointModel).where(
                        ReadModelCheckpointModel.checkpoint_key == key
                    )
                )
        except SQLAlchemyError as exc:
            raise SystemDegradedError("READ_MODEL_CHECKPOINT_QUERY_FAILED") from exc
        if row is None:
            return None
        return Checkpoint(
            key=row.checkpoint_key,
            source_hash=row.source_hash,
            created_at=row.created_at,
            payload=row.payload,
        )

    def dashboard_latest_fixtures(self) -> list[dict[str, Any]]:
        fixtures: list[dict[str, Any]] = []
        for row in self.checkpoints(ANALYSIS_CARD_SHADOW_PREFIX):
            fixture_id = row.key.removeprefix(ANALYSIS_CARD_SHADOW_PREFIX)
            card = self._analysis_card_from_checkpoint(row, fixture_id)
            fixtures.append(self._dashboard_fixture_from_projection(card, row))
        return fixtures

    def analysis_checkpoint_count(self) -> int:
        try:
            with Session(self._database_engine()) as session:
                return int(
                    session.scalar(
                        select(func.count(ReadModelCheckpointModel.id)).where(
                            ReadModelCheckpointModel.checkpoint_key.like(
                                f"{ANALYSIS_CARD_SHADOW_PREFIX}%"
                            )
                        )
                    )
                    or 0
                )
        except SQLAlchemyError as exc:
            raise SystemDegradedError("READ_MODEL_CHECKPOINT_QUERY_FAILED") from exc

    def dashboard_fixtures_for_window(
        self,
        *,
        start: datetime | None,
        end: datetime | None,
        limit: int = MAX_PUBLIC_FIXTURES,
    ) -> list[dict[str, Any]]:
        """Read only checkpoint projections belonging to the requested window."""

        bounded = max(0, min(int(limit), MAX_PUBLIC_FIXTURES))
        if bounded == 0:
            return []
        competition_ids = self._dashboard_competition_ids()
        try:
            with Session(self._database_engine()) as session:
                checkpoint_identity = (
                    literal(ANALYSIS_CARD_SHADOW_PREFIX)
                    + MatchdayFixtureIdentityModel.provider_fixture_id
                )
                projection_query = (
                    select(
                        MatchdayFixtureIdentityModel,
                        ReadModelCheckpointModel,
                    )
                    .outerjoin(
                        ReadModelCheckpointModel,
                        ReadModelCheckpointModel.checkpoint_key == checkpoint_identity,
                    )
                    .where(
                        MatchdayFixtureIdentityModel.provider == "api_football",
                        MatchdayFixtureIdentityModel.competition_id.in_(competition_ids),
                    )
                )
                if start is not None:
                    projection_query = projection_query.where(
                        MatchdayFixtureIdentityModel.kickoff_utc >= start
                    )
                if end is not None:
                    projection_query = projection_query.where(
                        MatchdayFixtureIdentityModel.kickoff_utc < end
                    )
                projection_rows = list(
                    session.execute(
                        projection_query.order_by(
                            MatchdayFixtureIdentityModel.kickoff_utc,
                            MatchdayFixtureIdentityModel.provider_fixture_id,
                        ).limit(bounded)
                    )
                )
                identities = [row[0] for row in projection_rows]
                rows = [row[1] for row in projection_rows]
                w2_ids = {
                    value
                    for fixture in identities
                    for value in (fixture.home_w2_team_id, fixture.away_w2_team_id)
                    if value
                }
                canonical = (
                    {
                        row.w2_team_id: row
                        for row in session.scalars(
                            select(CanonicalTeamModel).where(
                                CanonicalTeamModel.w2_team_id.in_(w2_ids)
                            )
                        ).all()
                    }
                    if w2_ids
                    else {}
                )
        except SQLAlchemyError as exc:
            raise SystemDegradedError("READ_MODEL_CHECKPOINT_QUERY_FAILED") from exc

        reviewed_labels = reviewed_public_team_labels()
        pending_labels = pending_public_team_labels()
        fixtures: list[dict[str, Any]] = []
        for identity, model in zip(identities, rows, strict=True):
            fixture_id = str(identity.provider_fixture_id)
            if model is None:
                payload = identity.payload if isinstance(identity.payload, dict) else {}
                fixture = {
                    "fixture_id": fixture_id,
                    "competition_id": identity.competition_id,
                    "kickoff_utc": _iso_or_none(identity.kickoff_utc),
                    "status": identity.fixture_status,
                    "home_team_id": identity.home_provider_team_id,
                    "home_team_name": payload.get("home_team_name") or payload.get("home_name"),
                    "away_team_id": identity.away_provider_team_id,
                    "away_team_name": payload.get("away_team_name") or payload.get("away_name"),
                    "_analysis_card_projection": None,
                }
            else:
                row = Checkpoint(
                    key=model.checkpoint_key,
                    source_hash=model.source_hash,
                    created_at=model.created_at,
                    payload=model.payload,
                )
                card = self._analysis_card_from_checkpoint(row, fixture_id)
                fixture = self._dashboard_fixture_from_projection(card, row)
                fixture["_analysis_card_projection"] = card
            fixture["status"] = identity.fixture_status
            fixture["competition_id"] = identity.competition_id
            fixture["_public_team_labels"] = {
                "home": _public_team_label_from_identity(
                    fixture=identity,
                    side="home",
                    canonical=canonical,
                    reviewed_labels=reviewed_labels,
                    pending_labels=pending_labels,
                ),
                "away": _public_team_label_from_identity(
                    fixture=identity,
                    side="away",
                    canonical=canonical,
                    reviewed_labels=reviewed_labels,
                    pending_labels=pending_labels,
                ),
            }
            fixtures.append(fixture)
        return fixtures

    def dashboard_outcomes_for_fixtures(
        self,
        fixture_ids: Sequence[str],
    ) -> list[dict[str, Any]]:
        """Read persisted final scores for the requested dashboard fixtures."""

        requested = [str(value or "").strip() for value in fixture_ids]
        requested = [value for value in requested if value]
        if not requested:
            return []
        canonical_by_requested = {
            value: value if value.startswith("api_football:") else f"api_football:{value}"
            for value in requested
        }
        requested_by_canonical = {
            canonical: value for value, canonical in canonical_by_requested.items()
        }
        try:
            with Session(self._database_engine()) as session:
                rows = list(
                    session.scalars(
                        select(ResultModel).where(
                            ResultModel.fixture_id.in_(tuple(requested_by_canonical)),
                            func.upper(ResultModel.result_status).in_(
                                ("FT", "AET", "PEN", "FINAL")
                            ),
                        )
                    )
                )
        except SQLAlchemyError as exc:
            raise SystemDegradedError("DASHBOARD_OUTCOME_QUERY_FAILED") from exc
        by_requested = {
            requested_by_canonical[row.fixture_id]: {
                "fixture_id": requested_by_canonical[row.fixture_id],
                "result_status": row.result_status,
                "score": f"{row.home_goals}-{row.away_goals}",
            }
            for row in rows
            if row.fixture_id in requested_by_canonical
        }
        return [by_requested[value] for value in requested if value in by_requested]

    def dashboard_model_forecasts_for_fixtures(
        self,
        fixture_ids: Sequence[str],
    ) -> dict[str, dict[str, Any]]:
        """Read persisted model-forecast ledger facts without materializing anything."""

        requested = list(dict.fromkeys(str(value or "").strip() for value in fixture_ids))
        requested = [value for value in requested if value]
        aliases = {
            value: {
                value,
                value.removeprefix("api_football:"),
                f"api_football:{value.removeprefix('api_football:')}",
            }
            for value in requested
        }
        if not aliases:
            return {}
        all_aliases = tuple({alias for values in aliases.values() for alias in values})
        try:
            with Session(self._database_engine()) as session:
                captures = list(
                    session.scalars(
                        select(ModelForecastCaptureModel)
                        .where(ModelForecastCaptureModel.fixture_id.in_(all_aliases))
                        .order_by(ModelForecastCaptureModel.captured_at.desc())
                    )
                )
                capture_hashes = tuple(row.capture_identity_hash for row in captures)
                versions = (
                    list(
                        session.scalars(
                            select(ModelForecastCaptureDataVersionModel).where(
                                ModelForecastCaptureDataVersionModel.capture_identity_hash.in_(
                                    capture_hashes
                                )
                            )
                        )
                    )
                    if capture_hashes
                    else []
                )
                outcomes = (
                    list(
                        session.scalars(
                            select(ModelForecastOutcomeModel).where(
                                ModelForecastOutcomeModel.capture_identity_hash.in_(capture_hashes)
                            )
                        )
                    )
                    if capture_hashes
                    else []
                )
        except SQLAlchemyError as exc:
            raise SystemDegradedError("DASHBOARD_MODEL_FORECAST_QUERY_FAILED") from exc
        version_by_capture = {row.capture_identity_hash: row for row in versions}
        outcome_by_capture = {row.capture_identity_hash: row for row in outcomes}
        result: dict[str, dict[str, Any]] = {}
        for requested_id, requested_aliases in aliases.items():
            capture = next((row for row in captures if row.fixture_id in requested_aliases), None)
            if capture is None:
                result[requested_id] = {"state": "NOT_CAPTURED"}
                continue
            payload = capture.payload if isinstance(capture.payload, dict) else {}
            raw_xg_identity = payload.get("four_field_xg_identity")
            xg_identity = (
                cast(dict[str, Any], raw_xg_identity) if isinstance(raw_xg_identity, dict) else {}
            )
            raw_home_xg = xg_identity.get("home")
            home_xg = cast(dict[str, Any], raw_home_xg) if isinstance(raw_home_xg, dict) else {}
            raw_away_xg = xg_identity.get("away")
            away_xg = cast(dict[str, Any], raw_away_xg) if isinstance(raw_away_xg, dict) else {}
            outcome = outcome_by_capture.get(capture.capture_identity_hash)
            version = version_by_capture.get(capture.capture_identity_hash)
            result[requested_id] = {
                "state": "SETTLED" if outcome is not None else "CAPTURED",
                "capture_identity_hash": capture.capture_identity_hash,
                "captured_at": _iso_or_none(capture.captured_at),
                "lead_time_seconds": capture.lead_time_seconds,
                "lead_time_bucket": capture.lead_time_bucket,
                "capture_policy": payload.get("capture_policy", "FIRST_ELIGIBLE_FREEZE_IMMUTABLE"),
                "data_version": version.data_version if version else "LEGACY_UNVERSIONED",
                "team_xg_match_count": version.team_xg_match_count if version else None,
                "model_family": capture.model_family,
                "model_version": capture.model_version,
                "calibration_version": payload.get("calibration_version"),
                "calibration_status": payload.get("calibration_status"),
                "four_field_xg": {
                    "status": "READY",
                    "identity_hash": xg_identity.get("identity_hash")
                    or capture.four_field_xg_identity_hash,
                    "home_snapshot_identity": home_xg.get("snapshot_identity"),
                    "away_snapshot_identity": away_xg.get("snapshot_identity"),
                    "home_match_count": home_xg.get("match_count"),
                    "away_match_count": away_xg.get("match_count"),
                },
                "settled_at": _iso_or_none(outcome.settled_at) if outcome else None,
                "brier": outcome.brier if outcome else None,
                "log_loss": outcome.log_loss if outcome else None,
                "rps": outcome.rps if outcome else None,
            }
        return result

    def dashboard_dynamic_evaluations_for_fixtures(
        self,
        fixture_ids: Sequence[str],
    ) -> dict[str, dict[str, Any]]:
        """Read complete evaluation lifecycles through canonical fixture aliases."""

        requested = list(dict.fromkeys(str(value or "").strip() for value in fixture_ids))
        requested = [value for value in requested if value]
        aliases = {value: model_forecast_fixture_aliases(value) for value in requested}
        all_aliases = tuple({alias for values in aliases.values() for alias in values})
        if not all_aliases:
            return {}
        try:
            with Session(self._database_engine()) as session:
                rows = list(
                    session.scalars(
                        select(DynamicPrematchEvaluationModel)
                        .where(DynamicPrematchEvaluationModel.fixture_id.in_(all_aliases))
                        .order_by(DynamicPrematchEvaluationModel.evaluated_at)
                    )
                )
                opportunities = list(
                    session.scalars(
                        select(DynamicPrematchOpportunityModel)
                        .where(DynamicPrematchOpportunityModel.fixture_id.in_(all_aliases))
                        .order_by(
                            DynamicPrematchOpportunityModel.scheduled_checkpoint_at,
                            DynamicPrematchOpportunityModel.recorded_at,
                        )
                    )
                )
                supersessions = {
                    row.superseded_evaluation_id: row
                    for row in session.scalars(
                        select(DynamicPrematchSupersessionModel).where(
                            DynamicPrematchSupersessionModel.fixture_id.in_(all_aliases)
                        )
                    )
                }
        except SQLAlchemyError as exc:
            raise SystemDegradedError("DASHBOARD_DYNAMIC_EVALUATION_QUERY_FAILED") from exc
        by_fixture: dict[str, list[DynamicPrematchEvaluationModel]] = defaultdict(list)
        for evaluation_row in rows:
            by_fixture[evaluation_row.fixture_id].append(evaluation_row)
        opportunities_by_fixture: dict[str, list[DynamicPrematchOpportunityModel]] = defaultdict(
            list
        )
        for opportunity_row in opportunities:
            opportunities_by_fixture[opportunity_row.fixture_id].append(opportunity_row)
        result: dict[str, dict[str, Any]] = {}
        for fixture_id, fixture_aliases in aliases.items():
            versions = []
            opportunity_versions = []
            for alias in fixture_aliases:
                for evaluation_row in by_fixture[alias]:
                    payload = dict(evaluation_row.payload)
                    payload["original_state"] = evaluation_row.original_state
                    supersession = supersessions.get(evaluation_row.evaluation_id)
                    if supersession is not None:
                        payload["state"] = "SUPERSEDED"
                        payload["superseded_by_evaluation_id"] = (
                            supersession.superseded_by_evaluation_id
                        )
                        payload["supersession_reason"] = supersession.reason
                    versions.append(payload)
                for opportunity_row in opportunities_by_fixture[alias]:
                    payload = dict(opportunity_row.payload or {})
                    payload.update(
                        {
                            "opportunity_identity_hash": (
                                opportunity_row.opportunity_identity_hash
                            ),
                            "market": opportunity_row.market,
                            "evaluation_slot_id": opportunity_row.evaluation_slot_id,
                            "scheduled_checkpoint_at": _iso_or_none(
                                opportunity_row.scheduled_checkpoint_at
                            ),
                            "recorded_at": _iso_or_none(opportunity_row.recorded_at),
                            "evaluated_at": _iso_or_none(opportunity_row.evaluated_at),
                            "latest_attempt_identity_hash": (
                                opportunity_row.latest_attempt_identity_hash
                            ),
                            "state": opportunity_row.state,
                        }
                    )
                    opportunity_versions.append(payload)
            if versions or opportunity_versions:
                versions.sort(key=lambda item: str(item.get("evaluated_at") or ""))
                opportunity_versions.sort(
                    key=lambda item: (
                        str(item.get("scheduled_checkpoint_at") or ""),
                        str(item.get("recorded_at") or ""),
                    )
                )
                result[fixture_id] = {
                    "schema_version": "w2.dynamic_quote_ev_lifecycle.v1",
                    "fixture_id": fixture_id,
                    "versions": versions,
                    "current": [row for row in versions if row.get("state") != "SUPERSEDED"],
                    "opportunities": opportunity_versions,
                }
        return result

    def dashboard_model_forecast_validation_progress(self) -> dict[str, Any]:
        """Read the complete append-only model-forecast ledger as one projection."""

        try:
            with Session(self._database_engine()) as session:
                captures = list(session.scalars(select(ModelForecastCaptureModel)))
                versions = list(session.scalars(select(ModelForecastCaptureDataVersionModel)))
                outcomes = list(session.scalars(select(ModelForecastOutcomeModel)))
                dynamic_evaluations = list(session.scalars(select(DynamicPrematchEvaluationModel)))
                dynamic_opportunities = list(
                    session.scalars(select(DynamicPrematchOpportunityModel))
                )
                t30_plans = list(
                    session.scalars(
                        select(MatchdayCheckpointPlanModel).where(
                            MatchdayCheckpointPlanModel.checkpoint == "T-30m_VALIDATION_LOCK"
                        )
                    )
                )
                candidate_fixture_ids = {
                    str(row.fixture_id).removeprefix("api_football:")
                    for row in dynamic_evaluations
                    if row.official_funnel_eligible is True
                    and isinstance(row.payload, dict)
                    and row.payload.get("state") == "ANALYSIS_PICK_ACTIVE"
                }
                candidate_fixtures = list(
                    session.scalars(
                        select(MatchdayFixtureIdentityModel).where(
                            MatchdayFixtureIdentityModel.provider == "api_football",
                            MatchdayFixtureIdentityModel.provider_fixture_id.in_(
                                candidate_fixture_ids
                            ),
                        )
                    )
                )
                candidate_results = list(
                    session.scalars(
                        select(ResultModel).where(
                            ResultModel.fixture_id.in_(
                                [row.fixture_id for row in candidate_fixtures]
                            )
                        )
                    )
                )
                superseded_evaluation_ids = set(
                    session.scalars(
                        select(DynamicPrematchSupersessionModel.superseded_evaluation_id)
                    )
                )
                ready_team_ids = set(
                    session.scalars(
                        select(TeamXgMatchModel.team_id)
                        .group_by(TeamXgMatchModel.team_id)
                        .having(
                            func.count(func.distinct(TeamXgMatchModel.fixture_id)) >= MIN_XG_MATCHES
                        )
                    )
                )
                now = datetime.now(UTC)
                next_7d_ready_fixtures = session.scalar(
                    select(
                        func.count(func.distinct(MatchdayFixtureIdentityModel.fixture_id))
                    ).where(
                        MatchdayFixtureIdentityModel.provider == "api_football",
                        MatchdayFixtureIdentityModel.kickoff_utc >= now,
                        MatchdayFixtureIdentityModel.kickoff_utc < now + timedelta(days=7),
                        MatchdayFixtureIdentityModel.home_provider_team_id.in_(ready_team_ids),
                        MatchdayFixtureIdentityModel.away_provider_team_id.in_(ready_team_ids),
                    )
                )
                current_flow_capture_hashes = select(
                    OutcomeLedgerModel.capture_identity_hash
                ).where(
                    OutcomeLedgerModel.record_type == "capture",
                    OutcomeLedgerModel.source_artifact == "db:forward_outcome_ledger",
                    OutcomeLedgerModel.recommendation_scope.in_(("VALIDATION", "SHADOW")),
                    OutcomeLedgerModel.payload["checkpoint"].as_string() == "T-30m_VALIDATION_LOCK",
                )
                current_flow_candidate_count = session.scalar(
                    select(func.count(func.distinct(OutcomeLedgerModel.fixture_id))).where(
                        OutcomeLedgerModel.record_type == "capture",
                        OutcomeLedgerModel.source_artifact == "db:forward_outcome_ledger",
                        OutcomeLedgerModel.recommendation_scope.in_(("VALIDATION", "SHADOW")),
                        OutcomeLedgerModel.payload["checkpoint"].as_string()
                        == "T-30m_VALIDATION_LOCK",
                    )
                )
                current_flow_settled_count = session.scalar(
                    select(func.count(func.distinct(OutcomeLedgerModel.fixture_id))).where(
                        OutcomeLedgerModel.record_type == "outcome",
                        OutcomeLedgerModel.capture_identity_hash.in_(current_flow_capture_hashes),
                    )
                )
            candidate_team_labels = self.public_team_labels_for_fixtures(
                sorted(candidate_fixture_ids)
            )
        except SQLAlchemyError as exc:
            raise SystemDegradedError("DASHBOARD_MODEL_FORECAST_QUERY_FAILED") from exc
        settled_hashes = {row.capture_identity_hash for row in outcomes}
        market_evaluation_funnel = _model_forecast_market_evaluation_funnel(
            captures,
            dynamic_evaluations,
            superseded_evaluation_ids,
            dynamic_opportunities,
        )
        official_recommendations = _official_funnel_recommendations(
            dynamic_evaluations,
            dynamic_opportunities,
            {row.provider_fixture_id: row for row in candidate_fixtures},
            {row.fixture_id: row for row in candidate_results},
            candidate_team_labels,
        )
        ever_formed_candidate_count = len(
            {
                (str(row.fixture_id).removeprefix("api_football:"), str(row.market))
                for row in dynamic_evaluations
                if row.official_funnel_eligible is True
                and isinstance(row.payload, dict)
                and row.payload.get("state") == "ANALYSIS_PICK_ACTIVE"
            }
        )
        final_candidate_count = len(official_recommendations)
        t30_candidate_opportunities = [
            row
            for row in dynamic_opportunities
            if row.evaluation_slot_id == "T-30m_VALIDATION_LOCK"
            and row.state == "EVALUATED_CANDIDATE"
        ]
        captured_t30_plan_ids = {row.plan_id for row in t30_plans if row.status == "CAPTURED"}
        t30_evaluated_candidate_count = len(
            {
                (str(row.fixture_id).removeprefix("api_football:"), str(row.market))
                for row in t30_candidate_opportunities
            }
        )
        t30_confirmed_candidate_count = len(
            {
                (str(row.fixture_id).removeprefix("api_football:"), str(row.market))
                for row in t30_candidate_opportunities
                if row.checkpoint_plan_identity in captured_t30_plan_ids
            }
        )
        version_by_capture = {row.capture_identity_hash: row for row in versions}
        version_names = sorted(
            {
                (
                    version_by_capture[row.capture_identity_hash].data_version
                    if row.capture_identity_hash in version_by_capture
                    else "LEGACY_UNVERSIONED"
                )
                for row in captures
            }
        )
        return {
            "capture_count": len(captures),
            "settled_count": len(outcomes),
            "pending_count": len(captures) - len(outcomes),
            "sample_target": SAMPLE_TARGET,
            "current_flow_candidate_count": int(current_flow_candidate_count or 0),
            "current_flow_settled_count": int(current_flow_settled_count or 0),
            "ever_formed_candidate_count": ever_formed_candidate_count,
            "final_candidate_count": final_candidate_count,
            "invalidated_candidate_count": max(
                ever_formed_candidate_count - final_candidate_count, 0
            ),
            "t30_evaluated_candidate_count": t30_evaluated_candidate_count,
            "t30_confirmed_candidate_count": t30_confirmed_candidate_count,
            "min_xg_matches": MIN_XG_MATCHES,
            "xg_ready_team_count": len(ready_team_ids),
            "next_7d_xg_ready_fixture_count": int(next_7d_ready_fixtures or 0),
            "capture_policy": "FIRST_ELIGIBLE_FREEZE_IMMUTABLE",
            "market_evaluation_funnel": market_evaluation_funnel,
            "official_recommendations": official_recommendations,
            "lead_time_buckets": {
                bucket: {
                    "capture_count": sum(row.lead_time_bucket == bucket for row in captures),
                    "settled_count": sum(row.lead_time_bucket == bucket for row in outcomes),
                    "pending_count": sum(
                        row.lead_time_bucket == bucket
                        and row.capture_identity_hash not in settled_hashes
                        for row in captures
                    ),
                }
                for bucket in MODEL_FORECAST_LEAD_TIME_BUCKETS
            },
            "data_versions": {
                version_name: {
                    "team_xg_match_count": next(
                        (
                            version_by_capture[row.capture_identity_hash].team_xg_match_count
                            for row in captures
                            if row.capture_identity_hash in version_by_capture
                            and version_by_capture[row.capture_identity_hash].data_version
                            == version_name
                        ),
                        None,
                    ),
                    "capture_count": sum(
                        (
                            version_by_capture[row.capture_identity_hash].data_version
                            if row.capture_identity_hash in version_by_capture
                            else "LEGACY_UNVERSIONED"
                        )
                        == version_name
                        for row in captures
                    ),
                    "settled_count": sum(
                        (
                            version_by_capture[row.capture_identity_hash].data_version
                            if row.capture_identity_hash in version_by_capture
                            else "LEGACY_UNVERSIONED"
                        )
                        == version_name
                        and row.capture_identity_hash in settled_hashes
                        for row in captures
                    ),
                    "pending_count": sum(
                        (
                            version_by_capture[row.capture_identity_hash].data_version
                            if row.capture_identity_hash in version_by_capture
                            else "LEGACY_UNVERSIONED"
                        )
                        == version_name
                        and row.capture_identity_hash not in settled_hashes
                        for row in captures
                    ),
                    "lead_time_buckets": {
                        bucket: {
                            "capture_count": sum(
                                row.lead_time_bucket == bucket
                                and (
                                    version_by_capture[row.capture_identity_hash].data_version
                                    if row.capture_identity_hash in version_by_capture
                                    else "LEGACY_UNVERSIONED"
                                )
                                == version_name
                                for row in captures
                            ),
                            "settled_count": sum(
                                row.lead_time_bucket == bucket
                                and row.capture_identity_hash in settled_hashes
                                and (
                                    version_by_capture[row.capture_identity_hash].data_version
                                    if row.capture_identity_hash in version_by_capture
                                    else "LEGACY_UNVERSIONED"
                                )
                                == version_name
                                for row in captures
                            ),
                            "pending_count": sum(
                                row.lead_time_bucket == bucket
                                and row.capture_identity_hash not in settled_hashes
                                and (
                                    version_by_capture[row.capture_identity_hash].data_version
                                    if row.capture_identity_hash in version_by_capture
                                    else "LEGACY_UNVERSIONED"
                                )
                                == version_name
                                for row in captures
                            ),
                        }
                        for bucket in MODEL_FORECAST_LEAD_TIME_BUCKETS
                    },
                }
                for version_name in version_names
            },
        }

    def fixture_statuses_for_fixtures(self, fixture_ids: list[str]) -> dict[str, str]:
        provider_ids = {
            str(fixture_id or "").removeprefix("api_football:")
            for fixture_id in fixture_ids
            if str(fixture_id or "").strip()
        }
        if not provider_ids:
            return {}
        with Session(self._database_engine()) as session:
            rows = list(
                session.scalars(
                    select(MatchdayFixtureIdentityModel).where(
                        MatchdayFixtureIdentityModel.provider_fixture_id.in_(provider_ids)
                    )
                )
            )
        statuses: dict[str, str] = {}
        for row in rows:
            statuses[str(row.fixture_id)] = row.fixture_status
            statuses[str(row.provider_fixture_id)] = row.fixture_status
        return statuses

    def dashboard_fixture(self, fixture_id: str) -> dict[str, Any] | None:
        row = self.checkpoint(f"{ANALYSIS_CARD_SHADOW_PREFIX}{fixture_id}")
        if row is None:
            return None
        card = self._analysis_card_from_checkpoint(row, fixture_id)
        return self._dashboard_fixture_from_projection(card, row)

    def dashboard_provider(self) -> dict[str, Any] | None:
        row = self.checkpoint("dashboard:provider_status")
        return None if row is None else deepcopy(row.payload)

    def dashboard_data_health(self) -> dict[str, Any] | None:
        row = self.checkpoint("dashboard:data_health")
        return None if row is None else deepcopy(row.payload)

    def dashboard_forward_status(self) -> dict[str, Any] | None:
        row = self.checkpoint("dashboard:forward_status")
        return None if row is None else deepcopy(row.payload)

    def analysis_card_projection(self, fixture_id: str) -> dict[str, Any] | None:
        row = self.checkpoint(f"{ANALYSIS_CARD_SHADOW_PREFIX}{fixture_id}")
        if row is None:
            return None
        return self._analysis_card_from_checkpoint(row, fixture_id)

    def _analysis_card_from_checkpoint(
        self,
        row: Checkpoint,
        fixture_id: str,
    ) -> dict[str, Any]:
        try:
            artifact = validate_frozen_analysis_payload(fixture_id, row.payload)
        except FrozenAnalysisError as exc:
            raise SystemDegradedError("ANALYSIS_PROJECTION_INVALID") from exc
        if artifact.checkpoint_key != row.key or artifact.source_hash != row.source_hash:
            raise SystemDegradedError("ANALYSIS_PROJECTION_IDENTITY_MISMATCH")
        payload = deepcopy(artifact.payload)
        card = cast(dict[str, Any], deepcopy(payload["analysis_card"]))
        card["projection_health"] = {"status": "READY", "reason_code": None}
        card["read_model_projection"] = {
            "checkpoint_key": row.key,
            "projection_version": payload["projection_version"],
            "projection_hash": payload["projection_hash"],
            "source_hash": row.source_hash,
            "artifact_hash": artifact.artifact_hash,
            "source_event_type": payload["source_event_type"],
            "source_event_id": payload["source_event_id"],
            "source_event_hash": payload["source_event_hash"],
            "source_event_at": payload["source_event_at"],
            "last_projected_at": payload["last_projected_at"],
        }
        return card

    @staticmethod
    def _dashboard_fixture_from_projection(
        card: dict[str, Any],
        row: Checkpoint,
    ) -> dict[str, Any]:
        return {
            "fixture_id": str(card.get("fixture_id") or ""),
            "competition_id": card.get("competition_id"),
            "competition_name": card.get("competition_name"),
            "kickoff_utc": card.get("kickoff_utc"),
            "status": card.get("status"),
            "home_team_id": card.get("home_team_id"),
            "home_team_name": card.get("home_team_name") or card.get("home_name"),
            "away_team_id": card.get("away_team_id"),
            "away_team_name": card.get("away_team_name") or card.get("away_name"),
            "_read_model_checkpoint": _checkpoint_metadata(row),
        }

    def operation_payloads(self, name: str) -> list[dict[str, Any]]:
        return [
            {
                "key": row.key,
                "status": str(row.payload.get("status") or "NOT_READY"),
                "payload": deepcopy(row.payload),
            }
            for row in self.checkpoints(f"operations:{name}:")
        ]

    def release_counts(self) -> dict[str, int]:
        try:
            status = func.upper(
                ReadModelCheckpointModel.payload["analysis_card"]["status"].as_string()
            )
            with Session(self._database_engine()) as session:
                fixture_count, result_count = session.execute(
                    select(
                        func.count(ReadModelCheckpointModel.id),
                        func.count(ReadModelCheckpointModel.id).filter(
                            status.in_(FINISHED_STATUSES)
                        ),
                    ).where(
                        ReadModelCheckpointModel.checkpoint_key.like(
                            f"{ANALYSIS_CARD_SHADOW_PREFIX}%"
                        )
                    )
                ).one()
        except SQLAlchemyError as exc:
            raise SystemDegradedError("READ_MODEL_CHECKPOINT_QUERY_FAILED") from exc
        return {
            "read_model_fixture_count": int(fixture_count),
            "matchday_card_count": int(fixture_count),
            "future_fixture_count": int(fixture_count),
            "result_event_count": int(result_count),
        }

    def public_release_counts(self, *, limit: int = MAX_PUBLIC_FIXTURES) -> dict[str, int]:
        bounded = max(0, min(int(limit), MAX_PUBLIC_FIXTURES))
        fixtures = self.dashboard_latest_fixtures()[:bounded]
        return {
            "read_model_fixture_count": len(fixtures),
            "matchday_card_count": len(fixtures),
            "future_fixture_count": len(fixtures),
            "result_event_count": len(
                [
                    item
                    for item in fixtures
                    if normalize_match_status(item.get("status")) == "FINISHED"
                ]
            ),
        }

    def market_refresh_status_for_fixtures(
        self,
        fixture_ids: list[str],
        *,
        now: datetime | None = None,
    ) -> dict[str, str | None]:
        ids = {
            value if value.startswith("api_football:") else f"api_football:{value}"
            for fixture_id in fixture_ids
            if (value := str(fixture_id or "").strip())
        }
        if not ids:
            return {"odds_last_confirmed_at": None, "next_refresh_tick": None}
        reference = now or datetime.now(UTC)
        with Session(self._database_engine()) as session:
            odds_at = session.scalar(
                select(func.max(MatchdayMarketObservationModel.captured_at)).where(
                    MatchdayMarketObservationModel.fixture_id.in_(ids),
                    MatchdayMarketObservationModel.live.is_(False),
                )
            )
            next_tick = session.scalar(
                select(func.min(MatchdayCheckpointPlanModel.scheduled_at)).where(
                    MatchdayCheckpointPlanModel.fixture_id.in_(ids),
                    MatchdayCheckpointPlanModel.status == "PLANNED",
                    MatchdayCheckpointPlanModel.scheduled_at >= reference,
                )
            )
        return {
            "odds_last_confirmed_at": _iso_or_none(odds_at),
            "next_refresh_tick": _iso_or_none(next_tick),
        }

    def market_collection_status_for_fixtures(
        self,
        fixture_ids: list[str],
        *,
        now: datetime | None = None,
    ) -> dict[str, dict[str, Any]]:
        provider_ids = {
            str(fixture_id or "").removeprefix("api_football:")
            for fixture_id in fixture_ids
            if str(fixture_id or "").strip()
        }
        canonical_ids = {f"api_football:{fixture_id}" for fixture_id in provider_ids}
        if not canonical_ids:
            return {}
        reference = _utc(now or datetime.now(UTC))
        with Session(self._database_engine()) as session:
            captures = list(
                session.scalars(
                    select(MatchdayEndpointCaptureModel)
                    .where(
                        MatchdayEndpointCaptureModel.endpoint == "odds",
                        MatchdayEndpointCaptureModel.fixture_id.in_(canonical_ids),
                    )
                    .order_by(MatchdayEndpointCaptureModel.provider_captured_at.desc())
                )
            )
            observed_capture_ids = set(
                session.scalars(
                    select(MatchdayMarketObservationModel.capture_id).where(
                        MatchdayMarketObservationModel.fixture_id.in_(canonical_ids)
                    )
                )
            )
            plans = list(
                session.scalars(
                    select(MatchdayCheckpointPlanModel).where(
                        MatchdayCheckpointPlanModel.fixture_id.in_(canonical_ids),
                        MatchdayCheckpointPlanModel.test_only.is_(False),
                        MatchdayCheckpointPlanModel.namespace.is_(None),
                    )
                )
            )
            satisfied_plan_ids = set(
                session.scalars(
                    select(MatchdayEndpointCapturePlanModel.plan_id).where(
                        MatchdayEndpointCapturePlanModel.endpoint == "odds",
                        MatchdayEndpointCapturePlanModel.link_status == "LINKED",
                        MatchdayEndpointCapturePlanModel.capture_id.in_(observed_capture_ids),
                    )
                )
            )
            captured_lineup_ids = set(
                session.scalars(
                    select(MatchdayEndpointCaptureModel.capture_id).where(
                        MatchdayEndpointCaptureModel.endpoint == "lineups",
                        MatchdayEndpointCaptureModel.fixture_id.in_(canonical_ids),
                        MatchdayEndpointCaptureModel.capture_status == "CAPTURED",
                        MatchdayEndpointCaptureModel.response_count > 0,
                    )
                )
            )
            satisfied_lineup_plan_ids = set(
                session.scalars(
                    select(MatchdayEndpointCapturePlanModel.plan_id).where(
                        MatchdayEndpointCapturePlanModel.endpoint == "lineups",
                        MatchdayEndpointCapturePlanModel.link_status == "LINKED",
                        MatchdayEndpointCapturePlanModel.capture_id.in_(captured_lineup_ids),
                    )
                )
            )
        latest_capture: dict[str, MatchdayEndpointCaptureModel] = {}
        latest_snapshot: dict[str, MatchdayEndpointCaptureModel] = {}
        for capture in captures:
            if capture.fixture_id and capture.fixture_id not in latest_capture:
                latest_capture[capture.fixture_id] = capture
            if (
                capture.fixture_id
                and capture.capture_id in observed_capture_ids
                and capture.fixture_id not in latest_snapshot
            ):
                latest_snapshot[capture.fixture_id] = capture
        plans_by_fixture: dict[str, list[MatchdayCheckpointPlanModel]] = defaultdict(list)
        lineup_plans_by_fixture: dict[str, list[MatchdayCheckpointPlanModel]] = defaultdict(list)
        for plan in plans:
            endpoints = set(plan.endpoints or [])
            if "odds" in endpoints:
                plans_by_fixture[plan.fixture_id].append(plan)
            if "lineups" in endpoints:
                lineup_plans_by_fixture[plan.fixture_id].append(plan)
        result: dict[str, dict[str, Any]] = {}
        for canonical_id in canonical_ids:
            current_capture = latest_capture.get(canonical_id)
            current_snapshot = latest_snapshot.get(canonical_id)
            fixture_plans = plans_by_fixture.get(canonical_id, [])
            target, cause, overdue = _collection_window(
                fixture_plans, satisfied_plan_ids, reference
            )
            target_scheduled_at = _utc(target.scheduled_at) if target is not None else None
            target_window_end = _utc(target.window_end) if target is not None else None
            lineup_plans = lineup_plans_by_fixture.get(canonical_id, [])
            lineup_target, lineup_cause, lineup_overdue = _collection_window(
                lineup_plans, satisfied_lineup_plan_ids, reference
            )
            status = (
                "PROVIDER_EMPTY"
                if current_capture is not None and current_capture.response_count == 0
                else "MARKET_UNAVAILABLE"
                if current_capture is not None
                and current_capture.capture_id not in observed_capture_ids
                else "READY"
                if current_snapshot is not None
                else "WINDOW_DUE"
                if cause == "AWAITING_COLLECTION"
                else "WAITING_WINDOW"
                if cause == "NOT_YET_DUE"
                else "NOT_SCHEDULED"
            )
            payload = {
                "odds_status": status,
                "last_refresh_hint": _iso_or_none(
                    current_capture.provider_captured_at if current_capture is not None else None
                ),
                "market_collection": {
                    "latest_snapshot_at": _iso_or_none(
                        current_snapshot.provider_captured_at
                        if current_snapshot is not None
                        else None
                    ),
                    "latest_snapshot_checkpoint": (
                        current_snapshot.checkpoint if current_snapshot is not None else None
                    ),
                    "target_checkpoint": target.checkpoint if target is not None else None,
                    "scheduled_at": _iso_or_none(target_scheduled_at),
                    "window_end_at": _iso_or_none(target_window_end),
                    "overdue": overdue,
                    "public_semantics": {"scope": "MATCH", "cause": cause},
                },
            }
            if lineup_plans:
                payload["lineup_collection"] = {
                    "target_checkpoint": (
                        lineup_target.checkpoint if lineup_target is not None else None
                    ),
                    "scheduled_at": _iso_or_none(
                        _utc(lineup_target.scheduled_at) if lineup_target is not None else None
                    ),
                    "window_end_at": _iso_or_none(
                        _utc(lineup_target.window_end) if lineup_target is not None else None
                    ),
                    "overdue": lineup_overdue,
                    "public_semantics": {
                        "scope": "MATCH",
                        "cause": lineup_cause,
                    },
                }
            result[canonical_id] = payload
            result[canonical_id.removeprefix("api_football:")] = payload
        return result

    def canonical_competitions_for_fixtures(
        self,
        fixture_ids: list[str],
    ) -> dict[str, str]:
        normalized = {str(fixture_id or "").strip() for fixture_id in fixture_ids}
        normalized.discard("")
        if not normalized:
            return {}
        provider_ids = {value.removeprefix("api_football:") for value in normalized}
        canonical_ids = {f"api_football:{value}" for value in provider_ids}
        with Session(self._database_engine()) as session:
            rows = session.execute(
                select(
                    MatchdayFixtureIdentityModel.fixture_id,
                    MatchdayFixtureIdentityModel.provider_fixture_id,
                    MatchdayFixtureIdentityModel.competition_id,
                ).where(MatchdayFixtureIdentityModel.fixture_id.in_(canonical_ids))
            ).all()
        output: dict[str, str] = {}
        for fixture_id, provider_fixture_id, competition_id in rows:
            output[str(fixture_id)] = str(competition_id)
            output[str(provider_fixture_id)] = str(competition_id)
        return output

    def public_team_labels_for_fixtures(
        self,
        fixture_ids: list[str],
    ) -> dict[str, dict[str, dict[str, Any]]]:
        normalized = {str(fixture_id or "").strip() for fixture_id in fixture_ids}
        normalized.discard("")
        if not normalized:
            return {}
        provider_ids = {value.removeprefix("api_football:") for value in normalized}
        canonical_ids = {f"api_football:{value}" for value in provider_ids}
        with Session(self._database_engine()) as session:
            fixtures = session.scalars(
                select(MatchdayFixtureIdentityModel).where(
                    MatchdayFixtureIdentityModel.fixture_id.in_(canonical_ids)
                )
            ).all()
            w2_ids = {
                value
                for fixture in fixtures
                for value in (fixture.home_w2_team_id, fixture.away_w2_team_id)
                if value
            }
            canonical = {
                row.w2_team_id: row
                for row in session.scalars(
                    select(CanonicalTeamModel).where(CanonicalTeamModel.w2_team_id.in_(w2_ids))
                ).all()
            }
        reviewed_labels = reviewed_public_team_labels()
        pending_labels = pending_public_team_labels()
        output: dict[str, dict[str, dict[str, Any]]] = {}
        for fixture in fixtures:
            labels = {
                "home": _public_team_label_from_identity(
                    fixture=fixture,
                    side="home",
                    canonical=canonical,
                    reviewed_labels=reviewed_labels,
                    pending_labels=pending_labels,
                ),
                "away": _public_team_label_from_identity(
                    fixture=fixture,
                    side="away",
                    canonical=canonical,
                    reviewed_labels=reviewed_labels,
                    pending_labels=pending_labels,
                ),
            }
            output[str(fixture.fixture_id)] = labels
            output[str(fixture.provider_fixture_id)] = labels
        return output

    def persisted_date_strip(
        self,
        selected_date: date,
        *,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        start, _ = football_day_window(selected_date - timedelta(days=7))
        _, end = football_day_window(selected_date + timedelta(days=7))
        competition_ids = self._dashboard_competition_ids()
        with Session(self._database_engine()) as session:
            fixtures = list(
                session.scalars(
                    select(MatchdayFixtureIdentityModel).where(
                        MatchdayFixtureIdentityModel.provider == "api_football",
                        MatchdayFixtureIdentityModel.competition_id.in_(competition_ids),
                        MatchdayFixtureIdentityModel.kickoff_utc >= start,
                        MatchdayFixtureIdentityModel.kickoff_utc < end,
                    )
                )
            )
            fixture_ids = {row.fixture_id for row in fixtures}
            plans = (
                list(
                    session.scalars(
                        select(MatchdayCheckpointPlanModel).where(
                            MatchdayCheckpointPlanModel.fixture_id.in_(fixture_ids),
                            MatchdayCheckpointPlanModel.test_only.is_(False),
                        )
                    )
                )
                if fixture_ids
                else []
            )
            evidence_ids = (
                set(
                    session.scalars(
                        select(MatchdayMarketObservationModel.fixture_id)
                        .where(
                            MatchdayMarketObservationModel.fixture_id.in_(fixture_ids),
                            MatchdayMarketObservationModel.live.is_(False),
                        )
                        .distinct()
                    )
                )
                if fixture_ids
                else set()
            )
        return build_persisted_date_strip(
            selected_date,
            fixtures=(
                {
                    "fixture_id": row.fixture_id,
                    "competition_id": row.competition_id,
                    "kickoff_utc": row.kickoff_utc,
                    "fixture_status": row.fixture_status,
                }
                for row in fixtures
            ),
            odds_plans=(
                {
                    "fixture_id": row.fixture_id,
                    "scheduled_at": row.scheduled_at,
                    "endpoints": row.endpoints,
                }
                for row in plans
            ),
            market_evidence_fixture_ids=evidence_ids,
            as_of=now or datetime.now(UTC),
        )


class ReadModelService:
    def __init__(self, repository: ReadModelRepository | None = None) -> None:
        self.repository = repository or ReadModelRepository()
        self.day_policy = BeijingOperationalDayPolicy()
        self.date_resolver = FixtureOperationalDateResolver()
        self._dashboard_response_cache: dict[
            tuple[str, str, str, bool], tuple[float, dict[str, Any]]
        ] = {}

    def public_dashboard(self, **kwargs: Any) -> dict[str, Any]:
        return self.dashboard(**kwargs)

    def public_dashboard_summary(self, **kwargs: Any) -> dict[str, Any]:
        return self.dashboard_summary(**kwargs)

    def dashboard_outcomes_for_fixtures(
        self,
        fixture_ids: Sequence[str],
    ) -> list[dict[str, Any]]:
        return self.repository.dashboard_outcomes_for_fixtures(fixture_ids)

    def dashboard_model_forecasts_for_fixtures(
        self,
        fixture_ids: Sequence[str],
    ) -> dict[str, dict[str, Any]]:
        return self.repository.dashboard_model_forecasts_for_fixtures(fixture_ids)

    def dashboard_dynamic_evaluations_for_fixtures(
        self,
        fixture_ids: Sequence[str],
    ) -> dict[str, dict[str, Any]]:
        return self.repository.dashboard_dynamic_evaluations_for_fixtures(fixture_ids)

    def dashboard_model_forecast_validation_progress(self) -> dict[str, Any]:
        return self.repository.dashboard_model_forecast_validation_progress()

    def public_validation_summary(self, **kwargs: Any) -> dict[str, Any]:
        return self.validation_summary(**kwargs)

    def performance(
        self,
        *,
        window: Literal["7d", "30d", "90d"],
        league: str | None,
        tier: Literal["ALL", "STRICT", "ADVISORY"],
    ) -> dict[str, Any]:
        try:
            cohorts = {
                row.key: (
                    row,
                    PerformanceCohortProjection.model_validate(row.payload),
                )
                for row in self.repository.checkpoints("performance:cohort:")
            }
            fixtures = [
                PerformanceFixtureProjection.model_validate(row.payload)
                for row in self.repository.checkpoints("performance:fixture:")
            ]
            if not cohorts or not fixtures:
                raise SystemDegradedError("PERFORMANCE_PROJECTION_MISSING")
            selected_row, selected = cohorts[_performance_cohort_key(league=league, tier=tier)]
            strict = cohorts[_performance_cohort_key(league=league, tier="STRICT")][1]
            advisory = cohorts[_performance_cohort_key(league=league, tier="ADVISORY")][1]
            selected_window = selected.windows[window]
            strict_window = strict.windows[window]
            advisory_window = advisory.windows[window]
            if (
                selected.checkpoint_key != selected_row.key
                or not selected_row.source_hash
                or selected.scoring_window_anchor.tzinfo is None
            ):
                raise SystemDegradedError("PERFORMANCE_PROJECTION_IDENTITY_INVALID")
            lower = (
                selected.scoring_window_anchor
                - {
                    "7d": timedelta(days=7),
                    "30d": timedelta(days=30),
                    "90d": timedelta(days=90),
                }[window]
            )
            points = [
                {
                    "fixture_id": fixture.fixture_id,
                    "kickoff_utc": fixture.kickoff_utc,
                    "league": fixture.league,
                    "evaluation_tier": fixture.evaluation_tier,
                    "clv_decimal": fixture.clv_decimal,
                }
                for fixture in fixtures
                if fixture.status == "SCORED"
                and fixture.clv_status == "AVAILABLE"
                and fixture.clv_decimal is not None
                and fixture.kickoff_utc.tzinfo is not None
                and lower <= fixture.kickoff_utc <= selected.scoring_window_anchor
                and (league is None or fixture.league == league)
                and (tier == "ALL" or fixture.evaluation_tier == tier)
            ]
            points.sort(
                key=lambda row: (
                    cast(datetime, row["kickoff_utc"]),
                    str(row["fixture_id"]),
                )
            )
            response = PerformanceResponse.model_validate(
                {
                    "request_id": "validation-only",
                    "projection_version": selected.projection_version,
                    "scoring_window_anchor": selected.scoring_window_anchor,
                    "selected_window": window,
                    "selected_league": league,
                    "selected_tier": tier,
                    "clv": {
                        "clv_population": selected_window.clv_population,
                        "sample_count": selected_window.clv_sample_count,
                        "mean": selected_window.clv_mean,
                        "median": selected_window.clv_median,
                        "ci95": selected_window.clv_ci95,
                        "positive_count": selected_window.clv_positive_count,
                        "positive_share": selected_window.clv_positive_share,
                        "method": selected_window.clv_method,
                        "points": points,
                    },
                    "calibration": {
                        "scored_count": selected_window.scored_count,
                        "model_log_loss": selected_window.model_log_loss,
                        "market_log_loss": selected_window.market_log_loss,
                        "model_minus_market_log_loss": (
                            selected_window.model_minus_market_log_loss
                        ),
                        "model_ece": selected_window.model_ece,
                        "market_ece": selected_window.market_ece,
                        "model_reliability_bins": (selected_window.model_reliability_bins),
                        "market_reliability_bins": (selected_window.market_reliability_bins),
                        "paired_log_loss_bootstrap": (selected_window.paired_log_loss_bootstrap),
                    },
                    "tier_comparison": {
                        "STRICT": _performance_tier_row("STRICT", strict_window),
                        "ADVISORY": _performance_tier_row("ADVISORY", advisory_window),
                    },
                    "sample_progress": {
                        "current": selected_window.canonical_settled_count,
                        "target": selected_window.sample_target,
                        "ratio": selected_window.sample_progress,
                        "status": selected_window.sample_progress_status,
                    },
                    "coverage": {
                        "finished_result_count": (selected_window.finished_result_count),
                        "fixture_checkpoint_count": (selected_window.fixture_checkpoint_count),
                        "scored_count": selected_window.scored_count,
                        "not_scorable_count": (selected_window.not_scorable_count),
                        "blocked_count": selected_window.blocked_count,
                        "not_scorable_by_reason": (selected_window.not_scorable_by_reason),
                    },
                    "checkpoint_metadata": _checkpoint_metadata(selected_row),
                }
            )
            if len(response.clv.points) != response.clv.sample_count:
                raise SystemDegradedError("PERFORMANCE_CLV_POPULATION_MISMATCH")
            payload = response.model_dump()
        except (KeyError, ValidationError, TypeError, ValueError) as exc:
            raise SystemDegradedError("PERFORMANCE_PROJECTION_INVALID") from exc
        payload.pop("request_id")
        return payload

    def warm_dashboard_cache(self) -> None:
        # Startup must remain available to return an explicit 503 if the
        # checkpoint database is degraded; reads are warmed lazily.
        return

    def version(self) -> dict[str, Any]:
        counts = self.repository.release_counts()
        settings = get_settings()
        sha = os.getenv("W2_GIT_SHA", "UNKNOWN")
        return {
            "service": "w2-football-intelligence-engine",
            "environment": settings.environment.value,
            "api_git_sha": sha,
            "api_build_time": os.getenv("W2_BUILD_TIME"),
            "release_id": os.getenv("W2_RELEASE_ID") or sha,
            "data_profile": "real-db" if counts["read_model_fixture_count"] else "empty",
            "data_source": "read_model_checkpoint",
            "database_ready": True,
            "read_model_fixture_count": counts["read_model_fixture_count"],
            "matchday_card_count": counts["matchday_card_count"],
            "result_event_count": counts["result_event_count"],
            "release_identity": build_release_identity(settings),
            "capability_manifest": load_recommendation_capability_manifest().public_summary(),
            "generated_at": datetime.now(UTC),
        }

    def dashboard(
        self,
        *,
        target_date: str | None = None,
        window: str = "today",
        timezone: str = BEIJING_TZ,
        include_debug: bool = True,
    ) -> dict[str, Any]:
        requested_date = (
            date.fromisoformat(target_date)
            if target_date
            else default_football_day(datetime.now(UTC))
        )
        cache_key = (requested_date.isoformat(), window, timezone, include_debug)
        now_tick = monotonic()
        cached = self._dashboard_response_cache.get(cache_key)
        if cached is not None and now_tick - cached[0] <= 60:
            return deepcopy(cached[1])

        query_start: datetime | None
        query_end: datetime | None
        if window == "next36":
            query_start, query_end = next_36_hours_window()
        elif window == "next7":
            query_start, query_end = next_7_days_window()
        elif window == "future":
            query_start, _ = football_day_window(requested_date)
            query_end = None
        elif window == "all":
            query_start = query_end = None
        else:
            query_start, query_end = football_day_window(requested_date)
        window_reader = getattr(self.repository, "dashboard_fixtures_for_window", None)
        if callable(window_reader):
            batched_window_read = True
            fixtures = window_reader(
                start=query_start,
                end=query_end,
                limit=MAX_PUBLIC_FIXTURES,
            )
        else:
            batched_window_read = False
            fixtures = self.repository.dashboard_latest_fixtures()[:MAX_PUBLIC_FIXTURES]
        checkpoint_count_reader = getattr(self.repository, "analysis_checkpoint_count", None)
        fixture_checkpoint_count = (
            checkpoint_count_reader() if callable(checkpoint_count_reader) else len(fixtures)
        )
        analysis_projection_count = (
            sum(isinstance(item.get("_analysis_card_projection"), dict) for item in fixtures)
            if batched_window_read
            else len(fixtures)
        )
        canonical_competitions: dict[str, str] = {}
        public_team_labels: dict[str, dict[str, dict[str, Any]]] = {}
        if not batched_window_read:
            status_reader = getattr(self.repository, "fixture_statuses_for_fixtures", None)
            fixture_statuses = (
                status_reader([str(item.get("fixture_id") or "") for item in fixtures])
                if callable(status_reader)
                else {}
            )
            for item in fixtures:
                current_status = fixture_statuses.get(str(item.get("fixture_id") or ""))
                if current_status:
                    item["status"] = current_status
            identity_reader = getattr(
                self.repository,
                "canonical_competitions_for_fixtures",
                None,
            )
            canonical_competitions = (
                identity_reader([str(item.get("fixture_id") or "") for item in fixtures])
                if callable(identity_reader)
                else {}
            )
            team_label_reader = getattr(
                self.repository,
                "public_team_labels_for_fixtures",
                None,
            )
            public_team_labels = (
                team_label_reader([str(item.get("fixture_id") or "") for item in fixtures])
                if callable(team_label_reader)
                else {}
            )
        cards = [
            self._project_dashboard_card(
                item,
                canonical_competition_id=canonical_competitions.get(
                    str(item.get("fixture_id") or "")
                ),
                public_team_labels=public_team_labels.get(str(item.get("fixture_id") or ""), {}),
            )
            for item in fixtures
        ]
        selected = self._filter_dashboard_cards(cards, requested_date=requested_date, window=window)
        generated_at = datetime.now(UTC)
        collection_reader = getattr(
            self.repository,
            "market_collection_status_for_fixtures",
            None,
        )
        collection_status = (
            collection_reader(
                [str(card.get("fixture_id") or "") for card in selected],
                now=generated_at,
            )
            if callable(collection_reader)
            else {}
        )
        for card in selected:
            fixture_status = collection_status.get(str(card.get("fixture_id") or ""))
            if fixture_status:
                current_refresh = card.get("data_refresh")
                card["data_refresh"] = {
                    **(current_refresh if isinstance(current_refresh, dict) else {}),
                    **fixture_status,
                }
        recommendations = [
            card
            for card in selected
            if str(card.get("decision_tier") or "") in {"RECOMMEND", "ANALYSIS_PICK"}
        ]
        upcoming = [card for card in selected if card["status"] != "FINISHED"]
        finished = [card for card in selected if card["status"] == "FINISHED"]
        date_strip_reader = getattr(self.repository, "persisted_date_strip", None)
        date_strip = (
            date_strip_reader(requested_date, now=generated_at)
            if callable(date_strip_reader)
            else build_persisted_date_strip(
                requested_date,
                fixtures=(
                    {
                        "fixture_id": card.get("fixture_id"),
                        "competition_id": card.get("competition_id"),
                        "kickoff_utc": _parse_datetime(card.get("kickoff_utc")),
                        "fixture_status": card.get("status"),
                    }
                    for card in cards
                ),
                odds_plans=(),
                market_evidence_fixture_ids=set(),
                as_of=generated_at,
            )
        )
        start, end = football_day_window(requested_date)
        performance = dashboard_performance(selected)
        performance["round3_read_path"] = {
            "additional_query_count": 0,
            "fixture_count": len(selected),
            "provider_calls": 0,
            "source": "analysis_card_checkpoint",
        }
        checkpoint_reader = getattr(self.repository, "checkpoints", None)
        if callable(checkpoint_reader):
            forward_ledger = _dashboard_forward_ledger_from_checkpoints(
                checkpoint_reader("performance:cohort:"),
                fixture_rows=checkpoint_reader("performance:fixture:"),
            )
            if forward_ledger is not None:
                performance["forward_ledger"] = forward_ledger
        refresh_reader = getattr(self.repository, "market_refresh_status_for_fixtures", None)
        refresh_status = (
            refresh_reader([str(card.get("fixture_id") or "") for card in selected])
            if callable(refresh_reader)
            else {"odds_last_confirmed_at": None, "next_refresh_tick": None}
        )
        git_sha = os.getenv("W2_GIT_SHA") or "UNKNOWN"
        payload = {
            "generated_at": generated_at,
            "page_updated_at": generated_at,
            "odds_last_confirmed_at": refresh_status["odds_last_confirmed_at"]
            or self._latest_projection_time(selected, "source_event_at"),
            "next_refresh_tick": refresh_status["next_refresh_tick"],
            "date": requested_date.isoformat(),
            "selected_date": requested_date.isoformat(),
            "selected_football_day": requested_date.isoformat(),
            "selected_date_has_data": bool(selected),
            "next_available_date": next_available_date(requested_date, date_strip),
            "date_strip": date_strip,
            "football_day_timezone": str(FOOTBALL_DAY_TZ),
            "football_day_cutoff_hour": FOOTBALL_DAY_CUTOFF_HOUR,
            "football_day_start_utc": start.isoformat().replace("+00:00", "Z"),
            "football_day_end_utc": end.isoformat().replace("+00:00", "Z"),
            "timezone": timezone,
            "window": window,
            "data_profile": "real-db" if fixture_checkpoint_count else "empty",
            "data_source": "read_model_checkpoint",
            "version": {
                "api_git_sha": git_sha,
                "release_id": os.getenv("W2_RELEASE_ID") or git_sha,
                "read_authority": "read_model_checkpoint",
            },
            "debug": {
                "read_authority": "read_model_checkpoint",
                "fixture_checkpoint_count": fixture_checkpoint_count,
                "analysis_projection_count": analysis_projection_count,
                "system_degraded_count": len(
                    [card for card in cards if _projection_is_system_degraded(card)]
                ),
                "round3_read_path": performance["round3_read_path"],
            }
            if include_debug
            else {},
            "performance": performance,
            "recommendations": recommendations,
            "upcoming": upcoming,
            "finished": finished,
            "all": selected,
        }
        self._dashboard_response_cache[cache_key] = (now_tick, deepcopy(payload))
        return payload

    def _project_dashboard_card(
        self,
        fixture: dict[str, Any],
        *,
        canonical_competition_id: str | None = None,
        public_team_labels: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        fixture = deepcopy(fixture)
        has_embedded_analysis = "_analysis_card_projection" in fixture
        embedded_analysis = fixture.pop("_analysis_card_projection", None)
        embedded_team_labels = fixture.pop("_public_team_labels", None)
        fixture_id = str(fixture.get("fixture_id") or fixture.get("provider_fixture_id") or "")
        if not fixture_id:
            raise SystemDegradedError("DASHBOARD_FIXTURE_IDENTITY_MISSING")
        analysis = (
            embedded_analysis
            if isinstance(embedded_analysis, dict)
            else None
            if has_embedded_analysis
            else self.repository.analysis_card_projection(fixture_id)
        )
        resolved_team_labels = (
            embedded_team_labels
            if isinstance(embedded_team_labels, Mapping)
            else public_team_labels
        )
        card = (
            self._system_degraded_card(
                fixture_id,
                "ANALYSIS_PROJECTION_NOT_READY",
                competition_id=str(fixture.get("competition_id") or "") or None,
            )
            if analysis is None
            else analysis
        )
        merged = {
            **deepcopy(fixture),
            **deepcopy(card),
            "fixture_id": fixture_id,
            "kickoff_utc": fixture.get("kickoff_utc") or card.get("kickoff_utc"),
            "competition_id": canonical_competition_id
            or fixture.get("competition_id")
            or card.get("competition_id"),
            "competition_name": fixture.get("competition_name") or card.get("competition_name"),
            "home_team_id": fixture.get("home_team_id"),
            "home_team_name": fixture.get("home_team_name") or card.get("home_name"),
            "away_team_id": fixture.get("away_team_id"),
            "away_team_name": fixture.get("away_team_name") or card.get("away_name"),
            "home_team_label": dict((resolved_team_labels or {}).get("home", {})),
            "away_team_label": dict((resolved_team_labels or {}).get("away", {})),
            "status": normalize_match_status(fixture.get("status")),
            "raw_status": fixture.get("status"),
            "formal_recommendation": False,
            "candidate": False,
        }
        merged = _apply_repository_v4_authority(merged)
        decision = merged.get("recommendation_decision_v4")
        selected = (
            cast(dict[str, Any], decision).get("selected_candidate")
            if isinstance(decision, dict)
            else None
        )
        merged["recommendation"] = (
            {
                **cast(dict[str, Any], selected),
                "decision_tier": merged.get("decision_tier"),
                "formal_recommendation": merged.get("decision_tier") == "RECOMMEND",
            }
            if isinstance(selected, dict)
            and str(merged.get("decision_tier") or "") in {"RECOMMEND", "ANALYSIS_PICK"}
            else None
        )
        return merged

    def _system_degraded_card(
        self,
        fixture_id: str,
        blocker: str,
        *,
        competition_id: str | None = None,
    ) -> dict[str, Any]:
        identity_missing = not str(competition_id or "").strip()
        requirement = (
            lineup_requirement(str(competition_id)) if not identity_missing else "ADVISORY"
        )
        risks = ["LINEUP_UNOBSERVABLE"] if requirement == "ADVISORY" else []
        effective_blocker = "LINEUP_REQUIREMENT_IDENTITY_MISSING" if identity_missing else blocker
        return {
            "fixture_id": fixture_id,
            "decision": "SKIP",
            "decision_tier": "NOT_READY",
            "data_status": "BLOCKED",
            "lifecycle_status": "DRAFT",
            "outcome_tracked": False,
            "lock_eligible": False,
            "recommendation_id": None,
            "lineup_requirement": requirement,
            "risk_reason_codes": risks,
            "pick": None,
            "reason_code": effective_blocker,
            "action": "等待权威读模型投影",
            "next_eval_at": None,
            "current_odds": {},
            "market_probabilities": {},
            "markets": [],
            "candidate": False,
            "formal_recommendation": False,
            "non_pick": {
                "reason_code": effective_blocker,
                "reason_human": "权威读模型投影尚未就绪",
                "action": "等待权威读模型投影",
                "next_eval_at": None,
            },
            "decision_contract": {
                "decision_tier": "NOT_READY",
                "data_status": "BLOCKED",
                "lifecycle_status": "DRAFT",
                "outcome_tracked": False,
                "lock_eligible": False,
                "recommendation_id": None,
                "lineup_requirement": requirement,
                "risk_reason_codes": risks,
                "pick": None,
                "non_pick": {
                    "reason_code": effective_blocker,
                    "reason_human": "权威读模型投影尚未就绪",
                    "action": "等待权威读模型投影",
                    "next_eval_at": None,
                },
                "reason_code": effective_blocker,
                "action": "等待权威读模型投影",
                "next_eval_at": None,
            },
            "recommendation_decision_v3_role": "HISTORY_ONLY",
            "projection_health": {
                "status": "SYSTEM_DEGRADED",
                "reason_code": effective_blocker,
            },
            "read_model_projection": None,
        }

    def _filter_dashboard_cards(
        self,
        cards: list[dict[str, Any]],
        *,
        requested_date: date,
        window: str,
    ) -> list[dict[str, Any]]:
        if window == "all":
            return sorted(cards, key=lambda row: str(row.get("kickoff_utc") or ""))
        if window == "next36":
            start, end = next_36_hours_window()
            return [
                card
                for card in cards
                if (kickoff := _parse_datetime(card.get("kickoff_utc"))) is not None
                and start <= kickoff < end
            ]
        if window == "next7":
            start, end = next_7_days_window()
            return [
                card
                for card in cards
                if (kickoff := _parse_datetime(card.get("kickoff_utc"))) is not None
                and start <= kickoff < end
            ]
        if window == "future":
            start, _ = football_day_window(requested_date)
            return [
                card
                for card in cards
                if (kickoff := _parse_datetime(card.get("kickoff_utc"))) is not None
                and kickoff >= start
            ]
        if window == "results":
            return [
                card
                for card in cards
                if card.get("status") == "FINISHED"
                and self.day_policy.window_for_date(requested_date).contains(
                    cast(datetime, _parse_datetime(card.get("kickoff_utc")))
                )
            ]
        day_window = self.day_policy.window_for_date(requested_date)
        return [
            card
            for card in cards
            if (kickoff := _parse_datetime(card.get("kickoff_utc"))) is not None
            and day_window.contains(kickoff)
        ]

    def _latest_projection_time(self, cards: list[dict[str, Any]], field: str) -> str | None:
        values = [
            str(projection[field])
            for card in cards
            if isinstance((projection := card.get("read_model_projection")), dict)
            and projection.get(field)
        ]
        return max(values, default=None)

    def _next_available_date(self, requested_date: date, cards: list[dict[str, Any]]) -> str | None:
        candidates = []
        for card in cards:
            kickoff = _parse_datetime(card.get("kickoff_utc"))
            if kickoff is None:
                continue
            operational = self.date_resolver.operational_date(kickoff)
            if operational > requested_date:
                candidates.append(operational)
        return min(candidates).isoformat() if candidates else None

    def dashboard_summary(self, **kwargs: Any) -> dict[str, Any]:
        payload = self.dashboard(**kwargs)
        return {
            "generated_at": payload["generated_at"],
            "date": payload["date"],
            "timezone": payload["timezone"],
            "window": payload["window"],
            "data_profile": payload["data_profile"],
            "data_source": payload["data_source"],
            "version": payload["version"],
            "totals": {
                key: len(cast(list[Any], payload[key]))
                for key in ("recommendations", "upcoming", "finished", "all")
            },
            "performance": payload["performance"],
        }

    def validation_summary(self, **kwargs: Any) -> dict[str, Any]:
        payload = self.dashboard(**kwargs)
        return {
            "generated_at": payload["generated_at"],
            "date": payload["date"],
            "timezone": payload["timezone"],
            "window": payload["window"],
            "data_profile": payload["data_profile"],
            "data_source": payload["data_source"],
            "version": payload["version"],
            "validation": validation_summary(cast(dict[str, Any], payload["performance"])),
        }

    def formal_tracking_summary(self) -> dict[str, Any]:
        return {
            "generated_at": datetime.now(UTC),
            "status": "NOT_READY",
            "label": "READ_MODEL_CHECKPOINT_ONLY",
            "min_bucket_samples_for_rate": 20,
            "snapshot_count": 0,
            "settlement_count": 0,
            "sample_count": 0,
            "win_count": 0,
            "win_rate": None,
            "roi": None,
            "buckets": {},
            "not_a_formal_gate": True,
            "posthoc_only": True,
        }

    def fixtures(
        self,
        *,
        timezone: str,
        page: int,
        page_size: int,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        competition_id: str | None = None,
        status: str | None = None,
        team_id: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = [
            self._fixture_summary(row, timezone)
            for row in self.repository.dashboard_latest_fixtures()
        ]
        if date_from:
            rows = [row for row in rows if row["kickoff_utc"] >= date_from.astimezone(UTC)]
        if date_to:
            rows = [row for row in rows if row["kickoff_utc"] <= date_to.astimezone(UTC)]
        if competition_id:
            rows = [row for row in rows if row["competition_id"] == competition_id]
        if status:
            rows = [row for row in rows if row["status"] == status]
        if team_id:
            rows = [row for row in rows if team_id in {row["home_team_id"], row["away_team_id"]}]
        total = len(rows)
        start = (page - 1) * page_size
        return rows[start : start + page_size], total

    def matchday(self, *, target_date: str | None = None, **filters: Any) -> dict[str, Any]:
        requested = (
            date.fromisoformat(target_date)
            if target_date
            else default_football_day(datetime.now(UTC))
        )
        rows = self._filter_dashboard_cards(
            [
                self._project_dashboard_card(row)
                for row in self.repository.dashboard_latest_fixtures()
            ],
            requested_date=requested,
            window="today",
        )
        for key in ("competition_id", "status"):
            if filters.get(key):
                rows = [row for row in rows if str(row.get(key)) == str(filters[key])]
        if filters.get("research_grade"):
            rows = [row for row in rows if row.get("research_grade") == filters["research_grade"]]
        if filters.get("data_status"):
            rows = [row for row in rows if row.get("data_status") == filters["data_status"]]
        return {"date": requested.isoformat(), "total": len(rows), "items": rows}

    def matchday_next_36_hours(self, *, now_utc: datetime | None = None) -> dict[str, Any]:
        start, end = next_36_hours_window(now_utc)
        rows = [
            self._project_dashboard_card(row)
            for row in self.repository.dashboard_latest_fixtures()
            if (kickoff := _parse_datetime(row.get("kickoff_utc"))) is not None
            and start <= kickoff < end
        ]
        return {
            "view": "NEXT_36_HOURS",
            "timezone": BEIJING_TZ,
            "now_utc": start.isoformat().replace("+00:00", "Z"),
            "window_end_utc": end.isoformat().replace("+00:00", "Z"),
            "total": len(rows),
            "items": rows,
        }

    def matchday_coverage(self, *, target_date: str | None = None) -> dict[str, Any]:
        requested = (
            date.fromisoformat(target_date)
            if target_date
            else default_football_day(datetime.now(UTC))
        )
        window = self.day_policy.window_for_date(requested)
        rows = self.matchday(target_date=requested.isoformat())["items"]
        count = len(cast(list[Any], rows))
        return {
            "local_date": requested,
            "start_local": window.start_local,
            "end_local": window.end_local,
            "start_utc": window.start_utc,
            "end_utc": window.end_utc,
            "authoritative_count": count,
            "discovered_count": count,
            "eligible_count": count,
            "card_count": count,
            "read_model_count": count,
            "displayed_count": count,
            "missing_count": 0,
            "reason_distribution": {},
            "coverage_status": "READY" if count else "NOT_READY",
        }

    def fixture(self, fixture_id: str, timezone: str) -> dict[str, Any] | None:
        row = self.repository.dashboard_fixture(fixture_id)
        if row is None:
            return None
        summary = self._fixture_summary(row, timezone)
        analysis = self.repository.analysis_card_projection(fixture_id)
        return {
            **summary,
            "venue": row.get("venue"),
            "bookmaker_count": int(row.get("bookmaker_count") or 0),
            "market_coverage": dict(row.get("market_coverage") or {}),
            "forward_decision": str(row.get("decision_status") or "NOT_READY"),
            "provenance": dict(row.get("provenance") or {}),
            "risk_notes": list(row.get("risk_notes") or []),
            "primary_market": row.get("primary_market"),
            "primary_selection": row.get("primary_selection"),
            "primary_line": row.get("primary_line"),
            "primary_executable_odds": row.get("primary_executable_odds"),
            "primary_hong_kong_odds": row.get("primary_hong_kong_odds"),
            "primary_model_fair_odds": row.get("primary_model_fair_odds"),
            "primary_risk_adjusted_ev": row.get("primary_risk_adjusted_ev"),
            "research_grade": row.get("research_grade"),
            "ah_ladder": list(row.get("ah_ladder") or []),
            "ou_ladder": list(row.get("ou_ladder") or []),
            "all_market_ranking": list(row.get("all_market_ranking") or []),
            "one_x_two_ranking": list(row.get("one_x_two_ranking") or []),
            "btts_ranking": list(row.get("btts_ranking") or []),
            "secondary_market_direction": row.get("secondary_market_direction"),
            "source_snapshot_id": dict(row.get("provenance") or {}).get("snapshot_id"),
            "source_captured_at": _parse_datetime(row.get("captured_at")),
            "source_phase": row.get("phase"),
            "valuation_generated_at": _parse_datetime(row.get("valuation_generated_at")),
            "projector_generated_at": _parse_datetime(row.get("projector_generated_at")),
            "temporal_status": row.get("temporal_status"),
            "integrity_status": row.get("integrity_status"),
            "analysis_card": analysis
            if analysis is not None
            else self._system_degraded_card(
                fixture_id,
                "ANALYSIS_PROJECTION_NOT_READY",
                competition_id=str(row.get("competition_id") or "") or None,
            ),
        }

    def research_card(self, fixture_id: str) -> dict[str, Any] | None:
        return self.public_analysis_card_bounded(fixture_id)

    def public_analysis_card_bounded(
        self,
        fixture_id: str,
        *,
        evaluation_time: datetime | None = None,
        use_frozen_canary: bool = False,
    ) -> dict[str, Any] | None:
        del evaluation_time, use_frozen_canary
        projection = self.repository.analysis_card_projection(fixture_id)
        if projection is not None:
            return _apply_repository_v4_authority(projection)
        fixture = self.repository.dashboard_fixture(fixture_id) or {}
        return _apply_repository_v4_authority(
            self._system_degraded_card(
                fixture_id,
                "ANALYSIS_PROJECTION_NOT_READY",
                competition_id=str(fixture.get("competition_id") or "") or None,
            )
        )

    def odds_timeline(self, fixture_id: str) -> list[dict[str, Any]]:
        card = self.public_analysis_card_bounded(fixture_id)
        return list(card.get("odds_timeline") or []) if card else []

    def market_ranking(self, fixture_id: str) -> list[dict[str, Any]]:
        card = self.public_analysis_card_bounded(fixture_id)
        return list(card.get("all_market_ranking") or card.get("markets") or []) if card else []

    def integrity(self, fixture_id: str) -> dict[str, Any] | None:
        card = self.public_analysis_card_bounded(fixture_id)
        return (
            None if card is None else dict(card.get("integrity") or {"integrity_status": "UNKNOWN"})
        )

    def market_probabilities(self, fixture_id: str) -> dict[str, Any]:
        card = self.public_analysis_card_bounded(fixture_id)
        probabilities = dict(card.get("market_probabilities") or {}) if card else {}
        projection = dict(card.get("read_model_projection") or {}) if card else {}
        return {
            "probability_type": "market_fair_probability",
            "probabilities": probabilities,
            "source": "read_model_checkpoint",
            "as_of_time": _parse_datetime(projection.get("last_projected_at")),
            "quality": "READY" if probabilities else "NOT_READY",
        }

    def model_probabilities(self, fixture_id: str) -> dict[str, Any]:
        card = self.public_analysis_card_bounded(fixture_id)
        probabilities = dict(card.get("model_probabilities") or {}) if card else {}
        projection = dict(card.get("read_model_projection") or {}) if card else {}
        return {
            "probability_type": "independent_model_probability",
            "probabilities": probabilities,
            "source": "read_model_checkpoint",
            "as_of_time": _parse_datetime(projection.get("last_projected_at")),
            "quality": "READY" if probabilities else "NOT_READY",
            "calibrated": False,
        }

    def data_health(self) -> dict[str, Any]:
        payload = self.repository.dashboard_data_health()
        if payload is None:
            return {
                "stale_data_count": 0,
                "provider_status": "SYSTEM_DEGRADED",
                "forward_cycle_age_seconds": None,
                "gate4_progress": {
                    "status": "SYSTEM_DEGRADED",
                    "reason": "DATA_HEALTH_PROJECTION_NOT_READY",
                },
                "generated_at": datetime.now(UTC),
            }
        return {
            "stale_data_count": int(payload.get("stale_data_count") or 0),
            "provider_status": str(payload.get("provider_status") or "NOT_READY"),
            "forward_cycle_age_seconds": payload.get("forward_cycle_age_seconds"),
            "gate4_progress": dict(payload.get("gate4_progress") or {}),
            "generated_at": _parse_datetime(payload.get("generated_at")) or datetime.now(UTC),
        }

    def provider_status(self) -> dict[str, Any]:
        payload = self.repository.dashboard_provider()
        if payload is None:
            return {
                "provider": "api_football",
                "status": "SYSTEM_DEGRADED",
                "remaining_quota": None,
                "credential_status": "UNKNOWN",
                "last_request_status": None,
                "blockers": ["PROVIDER_STATUS_PROJECTION_NOT_READY"],
                "quota_policy": api_football_quota_policy(None),
            }
        quota = parse_int(payload.get("remaining_quota"))
        return {
            "provider": str(payload.get("provider") or "api_football"),
            "status": str(payload.get("status") or "NOT_READY"),
            "remaining_quota": quota,
            "credential_status": str(payload.get("credential_status") or "UNKNOWN"),
            "last_request_status": payload.get("last_request_status"),
            "blockers": list(payload.get("blockers") or []),
            "quota_policy": api_football_quota_policy(quota),
        }

    def forward_status(self) -> dict[str, Any]:
        payload = self.repository.dashboard_forward_status()
        return {
            "status": str((payload or {}).get("status") or "SYSTEM_DEGRADED"),
            "locks": int((payload or {}).get("locks") or 0),
            "market_comparable": int((payload or {}).get("market_comparable") or 0),
            "current_settled_n": int((payload or {}).get("current_settled_n") or 0),
            "target_n": int((payload or {}).get("target_n") or 50),
        }

    def operations_items(self, name: str) -> list[dict[str, Any]]:
        return self.repository.operation_payloads(name)

    def competition_operations_profile(self, competition_id: str) -> dict[str, Any] | None:
        try:
            entry = CompetitionRegistry().entries().get(competition_id)
        except CompetitionRegistryError as exc:
            raise SystemDegradedError("COMPETITION_REGISTRY_UNAVAILABLE") from exc
        return None if entry is None else deepcopy(entry.profile_payload)

    def leagues(self) -> list[dict[str, Any]]:
        try:
            readiness = cast(dict[str, Any], run_top_five_audit()["readiness"])
        except (KeyError, TypeError, ValueError) as exc:
            raise SystemDegradedError("LEAGUE_READ_MODEL_INVALID") from exc
        output = []
        for competition_id, payload in sorted(readiness.items()):
            audit = payload["audit"]
            seasons = list(audit["seasons"])
            output.append(
                {
                    "competition_id": competition_id,
                    "name": audit["name"],
                    "country": audit["country"],
                    "results_status": audit["market_state"]["RESULTS_READY"],
                    "market_status": {
                        "1X2": audit["market_state"]["MARKET_1X2_READY"],
                        "AH": audit["market_state"]["MARKET_AH_READY"],
                        "OU": audit["market_state"]["MARKET_OU_READY"],
                        "TIMELINE": audit["market_state"]["TIMELINE_READY"],
                    },
                    "latest_season": sorted(seasons)[-1] if seasons else None,
                    "blocker": (
                        "MANUAL_REVIEW_REQUIRED"
                        if payload["rollover"]["status"] == "MANUAL_REVIEW_REQUIRED"
                        else None
                    ),
                }
            )
        return output

    def league_readiness(self, competition_id: str) -> dict[str, Any] | None:
        try:
            readiness = cast(dict[str, Any], run_top_five_audit()["readiness"])
        except (KeyError, TypeError, ValueError) as exc:
            raise SystemDegradedError("LEAGUE_READ_MODEL_INVALID") from exc
        payload = readiness.get(competition_id)
        if payload is None:
            return None
        return {
            "competition_id": competition_id,
            "audit": payload["audit"],
            "rollover": payload["rollover"],
            "checklist": payload["checklist"],
            "model_scope_policy": payload["model_scope_policy"],
        }

    def world_cup_readiness(self) -> dict[str, Any]:
        return {
            "competition_id": "world_cup_2026",
            "profile_version": "v1",
            "fixture_coverage_count": len(self.repository.dashboard_latest_fixtures()),
            "data_coverage": {"status": "READ_MODEL_CHECKPOINT_ONLY"},
            "phase_count_per_fixture": 0,
            "gate_status": "PROVISIONAL_FORWARD_HOLDOUT_PENDING",
            "strategy_version": "NOT_AVAILABLE_GATE4",
            "production_deployment": "DISABLED",
            "shadow_runtime": "DISABLED_PENDING_GATE4",
            "blockers": [],
        }

    def league_onboarding(self) -> list[dict[str, Any]]:
        rows = []
        for league in self.leagues():
            readiness = self.league_readiness(str(league["competition_id"]))
            if readiness is not None:
                rows.append({"request_id": "", **readiness})
        return rows

    def operations_cycles(self) -> list[dict[str, Any]]:
        return [item["payload"] for item in self.operations_items("cycles")]

    def operations_latest(self) -> dict[str, Any]:
        rows = self.operations_cycles()
        return rows[-1] if rows else {"status": "NOT_READY"}

    def releases_readiness(self) -> dict[str, Any]:
        return {
            "approval_status": "NOT_READY",
            "production_release": "DISABLED",
            "dependency_blocker": "RELEASE_READ_MODEL_UNAVAILABLE",
        }

    def retention_status(self) -> dict[str, Any]:
        return {"status": "DRY_RUN_ONLY", "policy": {}}

    def gate5_preflight(self) -> dict[str, Any]:
        return {"gate5_result": "NO_RUN", "production_release": "DISABLED"}

    def w1_w2_shadow_comparison(self) -> dict[str, Any]:
        return {"status": "NOT_READY"}

    def _fixture_summary(self, item: dict[str, Any], timezone: str) -> dict[str, Any]:
        kickoff = _parse_datetime(item.get("kickoff_utc"))
        if kickoff is None:
            raise SystemDegradedError("DASHBOARD_FIXTURE_KICKOFF_INVALID")
        return {
            "fixture_id": str(item.get("fixture_id") or ""),
            "competition_id": str(item.get("competition_id") or ""),
            "competition_name": str(item.get("competition_name") or ""),
            "kickoff_utc": kickoff,
            "kickoff_beijing": kickoff.astimezone(self.day_policy.timezone).isoformat(),
            "operational_date_beijing": self.date_resolver.operational_date(kickoff).isoformat(),
            "kickoff_display": kickoff.astimezone(self.day_policy.timezone).strftime(
                "%Y-%m-%d %H:%M"
            ),
            "status": normalize_match_status(item.get("status")),
            "home_team_id": str(item.get("home_team_id") or ""),
            "home_team_name": item.get("home_team_name"),
            "away_team_id": str(item.get("away_team_id") or ""),
            "away_team_name": item.get("away_team_name"),
            "lifecycle_state": str(item.get("lifecycle_state") or "PREMATCH"),
            "data_state": str(item.get("data_status") or "NOT_READY"),
            "published_grade": item.get("research_grade"),
            "primary_market": item.get("primary_market"),
            "primary_line": item.get("primary_line"),
            "primary_odds": item.get("primary_executable_odds"),
            "last_captured": _parse_datetime(item.get("captured_at")),
        }
