from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from w2.infrastructure.persistence.dynamic_prematch_models import (
    DynamicPrematchEvaluationModel,
    LineupConfirmedEventModel,
)
from w2.infrastructure.persistence.matchday_intake_models import MatchdayFixtureIdentityModel
from w2.prematch.lifecycle import (
    DYNAMIC_EVALUATION_V2_SCHEMA,
    EVAL_02B_DISTRIBUTION_TOLERANCE,
    SETTLEMENT_STATE_ORDER,
    DynamicEvaluationState,
)
from w2.strategy.market_selector import SELECTABLE_MARKETS

PAIR_PROJECTOR_SCHEMA = "w2.eval_02b_exact_pair_projection.v1"
_ELIGIBLE_STATES = {
    DynamicEvaluationState.ANALYSIS_PICK_ACTIVE.value,
    DynamicEvaluationState.NO_EDGE_CURRENT.value,
}


@dataclass(frozen=True, kw_only=True)
class ExactPairIdentity:
    canonical_fixture_id: str
    competition_id: str
    season_id: str
    provider_id: str
    bookmaker_id: str
    market: str
    selection: str
    exact_line: float
    pre_evaluation_id: str
    post_evaluation_id: str

    def as_dict(self) -> dict[str, object]:
        return {
            "canonical_fixture_id": self.canonical_fixture_id,
            "competition_id": self.competition_id,
            "season_id": self.season_id,
            "provider_id": self.provider_id,
            "bookmaker_id": self.bookmaker_id,
            "market": self.market,
            "selection": self.selection,
            "exact_line": self.exact_line,
            "pre_evaluation_id": self.pre_evaluation_id,
            "post_evaluation_id": self.post_evaluation_id,
        }

    @property
    def identity_hash(self) -> str:
        return _canonical_sha256(self.as_dict())


@dataclass(frozen=True, kw_only=True)
class ExactPrePostPair:
    identity: ExactPairIdentity
    identity_hash: str
    kickoff_at: datetime
    lineup_confirmed_at: datetime
    pre_evaluated_at: datetime
    pre_capture_at: datetime
    post_evaluated_at: datetime
    post_capture_at: datetime
    lineup_input_hash: str
    pre_capture_id: str
    post_capture_id: str
    pre_quote_identity_hash: str
    post_quote_identity_hash: str
    baseline_distribution: dict[str, float]
    candidate_distribution: dict[str, float]


@dataclass(frozen=True, kw_only=True)
class PairProjectionExclusion:
    fixture_id: str
    market: str | None
    reason: str


@dataclass(frozen=True, kw_only=True)
class ExactPairProjection:
    schema_version: str
    pairs: tuple[ExactPrePostPair, ...]
    exclusions: tuple[PairProjectionExclusion, ...]


@dataclass(frozen=True, kw_only=True)
class _EligibleEvaluation:
    evaluation_id: str
    provider_id: str
    bookmaker_id: str
    market: str
    selection: str
    exact_line: float
    capture_id: str
    quote_identity_hash: str
    lineup_input_hash: str | None
    evaluated_at: datetime
    capture_at: datetime
    distribution: dict[str, float]

    @property
    def quote_scope(self) -> tuple[str, str, str, str, float]:
        return (
            self.provider_id,
            self.bookmaker_id,
            self.market,
            self.selection,
            self.exact_line,
        )


def project_exact_eval_02b_pairs(engine: Engine) -> ExactPairProjection:
    """Derive exact immutable Pre/Post pairs without writing or running the gate."""
    with Session(engine) as session:
        fixtures = {
            row.fixture_id: row
            for row in session.scalars(
                select(MatchdayFixtureIdentityModel).order_by(
                    MatchdayFixtureIdentityModel.fixture_id
                )
            )
        }
        events: dict[str, list[LineupConfirmedEventModel]] = {}
        for event_row in session.scalars(
            select(LineupConfirmedEventModel).order_by(
                LineupConfirmedEventModel.fixture_id,
                LineupConfirmedEventModel.captured_at,
                LineupConfirmedEventModel.event_id,
            )
        ):
            events.setdefault(event_row.fixture_id, []).append(event_row)
        evaluations: dict[str, list[DynamicPrematchEvaluationModel]] = {}
        for evaluation_row in session.scalars(
            select(DynamicPrematchEvaluationModel).order_by(
                DynamicPrematchEvaluationModel.fixture_id,
                DynamicPrematchEvaluationModel.market,
                DynamicPrematchEvaluationModel.evaluated_at,
                DynamicPrematchEvaluationModel.evaluation_id,
            )
        ):
            evaluations.setdefault(evaluation_row.fixture_id, []).append(evaluation_row)

    pairs: list[ExactPrePostPair] = []
    exclusions: list[PairProjectionExclusion] = []
    fixture_ids = sorted(set(events) | set(evaluations))
    for fixture_id in fixture_ids:
        fixture = fixtures.get(fixture_id)
        if fixture is None:
            exclusions.append(
                PairProjectionExclusion(
                    fixture_id=fixture_id,
                    market=None,
                    reason="BLOCKED_FIXTURE_IDENTITY_MISSING",
                )
            )
            continue
        fixture_events = events.get(fixture_id, [])
        if not fixture_events:
            exclusions.append(
                PairProjectionExclusion(
                    fixture_id=fixture_id,
                    market=None,
                    reason="BLOCKED_LINEUP_EVENT_MISSING",
                )
            )
            continue
        if len(fixture_events) != 1:
            exclusions.append(
                PairProjectionExclusion(
                    fixture_id=fixture_id,
                    market=None,
                    reason="BLOCKED_LINEUP_EVENT_CONFLICT",
                )
            )
            continue
        event = fixture_events[0]
        if not _event_matches_fixture(event, fixture):
            exclusions.append(
                PairProjectionExclusion(
                    fixture_id=fixture_id,
                    market=None,
                    reason="BLOCKED_LINEUP_EVENT_CONFLICT",
                )
            )
            continue

        by_market: dict[str, list[_EligibleEvaluation]] = {}
        for evaluation_row in evaluations.get(fixture_id, []):
            evaluation = _eligible_evaluation(evaluation_row, fixture)
            if evaluation is not None:
                by_market.setdefault(evaluation.market, []).append(evaluation)
        observed_markets = sorted({row.market for row in evaluations.get(fixture_id, [])})
        for market in observed_markets:
            candidates = by_market.get(market, [])
            pair = _pair_market(fixture, event, candidates)
            if pair is None:
                exclusions.append(
                    PairProjectionExclusion(
                        fixture_id=fixture_id,
                        market=market,
                        reason="BLOCKED_EXACT_PRE_POST_PAIR_MISSING_OR_AMBIGUOUS",
                    )
                )
            else:
                pairs.append(pair)
    return ExactPairProjection(
        schema_version=PAIR_PROJECTOR_SCHEMA,
        pairs=tuple(
            sorted(
                pairs,
                key=lambda pair: (
                    pair.kickoff_at,
                    pair.identity.canonical_fixture_id,
                    pair.identity.market,
                ),
            )
        ),
        exclusions=tuple(exclusions),
    )


def _event_matches_fixture(
    event: LineupConfirmedEventModel,
    fixture: MatchdayFixtureIdentityModel,
) -> bool:
    payload = event.payload
    payload_captured_at = _payload_time(payload.get("captured_at"))
    return bool(
        payload.get("schema_version") == "w2.lineup_confirmed_event.v2"
        and payload.get("fixture_id") == fixture.fixture_id
        and payload.get("competition_id") == fixture.competition_id
        and payload.get("season") == fixture.season
        and payload.get("lineup_input_hash") == event.lineup_input_hash
        and payload.get("checkpoint") == event.checkpoint == "LINEUP_CONFIRMED"
        and payload_captured_at == _utc(event.captured_at)
        and _utc(event.captured_at) < _utc(fixture.kickoff_utc)
    )


def _eligible_evaluation(
    row: DynamicPrematchEvaluationModel,
    fixture: MatchdayFixtureIdentityModel,
) -> _EligibleEvaluation | None:
    payload = row.payload
    if (
        payload.get("schema_version") != DYNAMIC_EVALUATION_V2_SCHEMA
        or row.original_state not in _ELIGIBLE_STATES
        or row.market not in SELECTABLE_MARKETS
        or payload.get("fixture_id") != fixture.fixture_id
        or payload.get("market") != row.market
        or payload.get("selection") != row.selection
        or payload.get("capture_id") != row.capture_id
        or payload.get("quote_identity_hash") != row.quote_identity_hash
        or payload.get("lineup_input_hash") != row.lineup_input_hash
        or payload.get("competition_id") != fixture.competition_id
        or payload.get("season") != fixture.season
        or payload.get("provider") != fixture.provider
    ):
        return None
    required = (
        payload.get("bookmaker_id"),
        payload.get("capture_id"),
        payload.get("quote_identity_hash"),
        payload.get("market"),
        payload.get("selection"),
    )
    if any(value is None or not str(value).strip() for value in required):
        return None
    exact_line = _finite_float(payload.get("exact_line"))
    capture_at = _payload_time(payload.get("capture_at"))
    evaluated_at = _payload_time(payload.get("evaluated_at"))
    distribution = _distribution(payload.get("model_settlement_distribution"))
    if (
        exact_line is None
        or capture_at is None
        or evaluated_at is None
        or distribution is None
        or row.capture_at is None
        or capture_at != _utc(row.capture_at)
        or evaluated_at != _utc(row.evaluated_at)
    ):
        return None
    return _EligibleEvaluation(
        evaluation_id=row.evaluation_id,
        provider_id=fixture.provider,
        bookmaker_id=str(payload["bookmaker_id"]),
        market=str(payload["market"]),
        selection=str(payload["selection"]),
        exact_line=exact_line,
        capture_id=str(payload["capture_id"]),
        quote_identity_hash=str(payload["quote_identity_hash"]),
        lineup_input_hash=(
            str(payload["lineup_input_hash"]) if payload.get("lineup_input_hash") else None
        ),
        evaluated_at=evaluated_at,
        capture_at=capture_at,
        distribution=distribution,
    )


def _pair_market(
    fixture: MatchdayFixtureIdentityModel,
    event: LineupConfirmedEventModel,
    evaluations: list[_EligibleEvaluation],
) -> ExactPrePostPair | None:
    event_at = _utc(event.captured_at)
    groups: dict[tuple[str, str, str, str, float], list[_EligibleEvaluation]] = {}
    for evaluation in evaluations:
        groups.setdefault(evaluation.quote_scope, []).append(evaluation)
    candidates: list[tuple[_EligibleEvaluation, _EligibleEvaluation]] = []
    for scoped_rows in groups.values():
        pre_rows = [
            row
            for row in scoped_rows
            if row.lineup_input_hash is None
            and row.capture_at < event_at
            and row.evaluated_at < event_at
        ]
        post_rows = [
            row
            for row in scoped_rows
            if row.lineup_input_hash == event.lineup_input_hash and row.capture_at >= event_at
        ]
        if pre_rows and post_rows:
            candidates.append(
                (
                    max(
                        pre_rows,
                        key=lambda row: (
                            row.evaluated_at,
                            row.capture_at,
                            row.evaluation_id,
                        ),
                    ),
                    min(
                        post_rows,
                        key=lambda row: (
                            row.capture_at,
                            row.evaluated_at,
                            row.evaluation_id,
                        ),
                    ),
                )
            )
    if len(candidates) != 1:
        return None
    chosen_pre, chosen_post = candidates[0]
    identity = ExactPairIdentity(
        canonical_fixture_id=fixture.fixture_id,
        competition_id=fixture.competition_id,
        season_id=fixture.season,
        provider_id=chosen_pre.provider_id,
        bookmaker_id=chosen_pre.bookmaker_id,
        market=chosen_pre.market,
        selection=chosen_pre.selection,
        exact_line=chosen_pre.exact_line,
        pre_evaluation_id=chosen_pre.evaluation_id,
        post_evaluation_id=chosen_post.evaluation_id,
    )
    return ExactPrePostPair(
        identity=identity,
        identity_hash=identity.identity_hash,
        kickoff_at=_utc(fixture.kickoff_utc),
        lineup_confirmed_at=event_at,
        pre_evaluated_at=chosen_pre.evaluated_at,
        pre_capture_at=chosen_pre.capture_at,
        post_evaluated_at=chosen_post.evaluated_at,
        post_capture_at=chosen_post.capture_at,
        lineup_input_hash=event.lineup_input_hash,
        pre_capture_id=chosen_pre.capture_id,
        post_capture_id=chosen_post.capture_id,
        pre_quote_identity_hash=chosen_pre.quote_identity_hash,
        post_quote_identity_hash=chosen_post.quote_identity_hash,
        baseline_distribution=chosen_pre.distribution,
        candidate_distribution=chosen_post.distribution,
    )


def _distribution(value: object) -> dict[str, float] | None:
    if not isinstance(value, dict) or set(value) != set(SETTLEMENT_STATE_ORDER):
        return None
    try:
        result = {state: float(value[state]) for state in SETTLEMENT_STATE_ORDER}
    except (TypeError, ValueError):
        return None
    if any(not math.isfinite(item) or item < 0 for item in result.values()):
        return None
    if abs(sum(result.values()) - 1.0) > EVAL_02B_DISTRIBUTION_TOLERANCE:
        return None
    return result


def _finite_float(value: object) -> float | None:
    if not isinstance(value, (str, int, float)):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _payload_time(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return _utc(value)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)
    except (TypeError, ValueError):
        return None


def _utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
