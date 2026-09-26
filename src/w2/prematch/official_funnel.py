"""Shared official-funnel recommendation projection.

This is the single authority for the ``赛后验证样本`` (post-match validation
sample) set: the fixture x market rows whose final opportunity carrying a real
evaluation is ``EVALUATED_CANDIDATE``.  Both the Dashboard recommendation table
(``validation.model_forecast.official_recommendations``) and the NOTIF-04
notification flows (② 验证样本最终确认 / ③ 每日结算) reuse this projection, so
the recommendation rows and the settlement rows can never drift apart.

The projection is read-only and behaviour-preserving for the Dashboard: it adds
``bookmaker_id``, ``quote_captured_at`` and ``current_ev`` from the same last
real evaluation row, which the notification flows need and the Dashboard simply
does not read.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from w2.domain.odds import settle_asian_handicap, settle_total_goals, split_quarter_line
from w2.identity.public_team_labels import (
    pending_public_team_labels,
    reviewed_public_team_labels,
)
from w2.infrastructure.persistence.dynamic_prematch_models import (
    DynamicPrematchEvaluationModel,
    DynamicPrematchOpportunityModel,
)
from w2.infrastructure.persistence.factor_model_models import CanonicalTeamModel
from w2.infrastructure.persistence.matchday_intake_models import MatchdayFixtureIdentityModel
from w2.infrastructure.persistence.models import ResultModel
from w2.prematch.lifecycle import (
    EVALUATED_OPPORTUNITY_STATES,
    evaluated_attempt_identities,
    final_official_opportunities,
)
from w2.settlement.settle import WIN_UNITS

logger = logging.getLogger(__name__)

CHECKPOINT_LABELS = {
    "T3_ODDS": "T-3h",
    "T60_ODDS_LINEUPS": "T-60m",
    "T45_ODDS": "T-45m",
    "T-30m_VALIDATION_LOCK": "T-30m",
    "T15_ODDS": "T-15m",
}

# Historical TOTALS rows remain in the append-only validation corpus, but they
# are evidence-only market views.  Keep this state explicit at the shared
# projection boundary so Dashboard and notification consumers cannot
# accidentally style them as recommendations.
MARKET_VIEW_DISPLAY_STATE = "MARKET_VIEW"
RECOMMENDATION_DISPLAY_STATE = "RECOMMENDATION"
TOTALS_DISPLAY_NOTICE = "市场观点展示 · 不作投注建议"


def official_funnel_recommendations(
    evaluations: Sequence[DynamicPrematchEvaluationModel],
    opportunities: Sequence[DynamicPrematchOpportunityModel],
    fixtures: Mapping[str, MatchdayFixtureIdentityModel],
    results: Mapping[str, ResultModel],
    public_team_labels: Mapping[str, Mapping[str, Mapping[str, Any]]],
    active_competitions: frozenset[str] | None = None,
) -> list[dict[str, Any]]:
    """Project picks whose last opportunity with a real evaluation is a candidate.

    A competition withdrawn from the whitelist keeps its rows -- the ledgers are
    append-only and the corpus is frozen against them -- but its picks stop
    counting towards the record, because the record is meant to describe the
    system as it currently stands.
    """

    evaluated_attempts = evaluated_attempt_identities(evaluations)
    final_opportunities = final_official_opportunities(
        opportunities, evaluated_attempts=evaluated_attempts
    )

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

    # 每个 (fixture_id, market) 第一次形成候选（ANALYSIS_PICK_ACTIVE）的档位，
    # 用于物化表的 first_checkpoint 列（最早候选评估的档位标签）。
    first_checkpoint_state: dict[tuple[str, str], tuple[datetime, str]] = {}
    for row in evaluations:
        payload = row.payload if isinstance(row.payload, dict) else {}
        if payload.get("state") != "ANALYSIS_PICK_ACTIVE":
            continue
        fixture_id = str(row.fixture_id).removeprefix("api_football:")
        key = (fixture_id, str(row.market))
        slot = str(getattr(row, "evaluation_slot_id", None) or "UNKNOWN_CHECKPOINT")
        label = CHECKPOINT_LABELS.get(slot, slot)
        current = first_checkpoint_state.get(key)
        if current is None or row.evaluated_at < current[0]:
            first_checkpoint_state[key] = (row.evaluated_at, label)

    projected: list[dict[str, Any]] = []
    for (fixture_id, market), row in latest.items():
        final = final_opportunities[(fixture_id, market)]
        payload = row.payload
        fixture = fixtures.get(fixture_id)
        if (
            active_competitions is not None
            and fixture is not None
            and str(fixture.competition_id) not in active_competitions
        ):
            continue
        canonical_fixture_id = (
            str(fixture.fixture_id) if fixture is not None else f"api_football:{fixture_id}"
        )
        result = results.get(canonical_fixture_id)
        final_checkpoint_label = CHECKPOINT_LABELS.get(
            str(getattr(final, "evaluation_slot_id", "UNKNOWN_CHECKPOINT")),
            str(getattr(final, "evaluation_slot_id", "UNKNOWN_CHECKPOINT")),
        )
        first_checkpoint = first_checkpoint_state.get((fixture_id, market), (None, None))[1]
        try:
            exact_line = Decimal(str(payload.get("exact_line")))
            if not exact_line.is_finite():
                raise ValueError("non-finite line")
            split_quarter_line(exact_line)
        except (InvalidOperation, TypeError, ValueError):
            logger.warning(
                "PROJECTION_SKIPPED_INVALID_LINE evaluation_id=%s fixture_id=%s market=%s",
                row.evaluation_id, fixture_id, market,
            )
            continue
        try:
            decimal_odds = Decimal(str(payload.get("decimal_odds")))
            if not decimal_odds.is_finite() or decimal_odds <= 1:
                raise ValueError("non-executable odds")
        except (InvalidOperation, TypeError, ValueError):
            logger.warning(
                "PROJECTION_SKIPPED_INVALID_ODDS evaluation_id=%s fixture_id=%s market=%s",
                row.evaluation_id, fixture_id, market,
            )
            continue
        line = str(payload.get("exact_line"))
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
                "display_state": (
                    MARKET_VIEW_DISPLAY_STATE
                    if market == "TOTALS"
                    else RECOMMENDATION_DISPLAY_STATE
                ),
                "display_notice": (
                    TOTALS_DISPLAY_NOTICE if market == "TOTALS" else None
                ),
                "selection": str(row.selection),
                "exact_line": line,
                "decimal_odds": float(decimal_odds),
                "bookmaker_id": payload.get("bookmaker_id"),
                "quote_captured_at": _iso_or_none(getattr(row, "capture_at", None)),
                "current_ev": payload.get("current_ev"),
                "home_team_label": labels["home"],
                "away_team_label": labels["away"],
                "score": (
                    f"{result.home_goals}-{result.away_goals}" if result is not None else None
                ),
                "settlement": outcome or "PENDING",
                "profit_units": float(profit_units) if profit_units is not None else None,
                "confirmed_checkpoint": final_checkpoint_label,
                "first_checkpoint": first_checkpoint,
                "final_checkpoint": final_checkpoint_label,
                "competition_id": (
                    str(getattr(fixture, "competition_id", ""))
                    if fixture is not None and getattr(fixture, "competition_id", None)
                    else None
                ),
                "calibration_identity": getattr(row, "evaluation_policy_version", None),
                "settled_at": (
                    _iso_or_none(getattr(result, "confirmed_at", None))
                    if result is not None
                    else None
                ),
                "later_unassessed_checkpoints": _later_unassessed_checkpoints(
                    opportunities,
                    fixture_id=fixture_id,
                    market=market,
                    after=final,
                    evaluated_attempts=evaluated_attempts,
                ),
            }
        )
        later = projected[-1]["later_unassessed_checkpoints"]
        projected[-1]["lifecycle_note_zh"] = (
            f"最终确认于 {projected[-1]['confirmed_checkpoint']}；"
            f"此后 {' / '.join(later)} 未产出评估，不影响该确认"
            if later
            else None
        )
    # 按北京开球时间倒序（最新在前）；同场让球(ASIAN_HANDICAP)在前、大小球(TOTALS)在后。
    # 市场顺序用 negated rank 纳入排序键，避免整体 reverse 连带反转同场市场顺序。
    market_rank = {"ASIAN_HANDICAP": 0, "TOTALS": 1}
    return sorted(
        projected,
        key=lambda item: (
            str(item.get("kickoff_utc") or ""),
            str(item["fixture_id"]),
            -market_rank.get(str(item["market"]), 99),
        ),
        reverse=True,
    )


def _later_unassessed_checkpoints(
    opportunities: Sequence[DynamicPrematchOpportunityModel],
    *,
    fixture_id: str,
    market: str,
    after: DynamicPrematchOpportunityModel,
    evaluated_attempts: set[tuple[str, str]],
) -> list[str]:
    after_order = (
        after.scheduled_checkpoint_at,
        after.recorded_at,
        after.opportunity_identity_hash,
    )
    rows = sorted(
        (
            row
            for row in opportunities
            if str(row.fixture_id).removeprefix("api_football:") == fixture_id
            and str(row.market) == market
            and (
                str(row.state) not in EVALUATED_OPPORTUNITY_STATES
                or (
                    str(row.opportunity_identity_hash),
                    str(row.latest_attempt_identity_hash),
                )
                not in evaluated_attempts
            )
            and (
                row.scheduled_checkpoint_at,
                row.recorded_at,
                row.opportunity_identity_hash,
            )
            > after_order
        ),
        key=lambda row: (
            row.scheduled_checkpoint_at,
            row.recorded_at,
            row.opportunity_identity_hash,
        ),
    )
    return list(
        dict.fromkeys(
            CHECKPOINT_LABELS.get(str(row.evaluation_slot_id), str(row.evaluation_slot_id))
            if getattr(row, "evaluation_slot_id", None)
            else "UNKNOWN_CHECKPOINT"
            for row in rows
        )
    )


def _iso_or_none(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def public_team_labels_for_fixtures(
    session: Session,
    fixtures: Sequence[MatchdayFixtureIdentityModel],
) -> dict[str, dict[str, dict[str, Any]]]:
    """Resolve the reviewed/pending public team labels for a set of fixtures.

    Mirrors the Dashboard recommendation table's label resolution so the
    notification flows render the same Chinese team names the Dashboard shows.
    """

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
