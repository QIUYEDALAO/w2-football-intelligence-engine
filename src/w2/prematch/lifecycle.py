from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

ACTIVE_DELTA_THRESHOLD = 0.05
ACTIVE_EV_THRESHOLD = 0.0
ACTIVE_EV_MINUS_SE_THRESHOLD = 0.0
LINEUP_CONFIRMED_CHECKPOINT = "LINEUP_CONFIRMED"
T30_VALIDATION_CHECKPOINT = "T-30m_VALIDATION_LOCK"
SOURCE_ABSENT_USER_MESSAGE = "当前采集窗口尚未取得完整盘口"
SOURCE_ABSENT_NEXT_ACTION = "等待下一次受控采集"


class DynamicEvaluationState(StrEnum):
    ANALYSIS_PICK_ACTIVE = "ANALYSIS_PICK_ACTIVE"
    NO_EDGE_CURRENT = "NO_EDGE_CURRENT"
    STALE_PENDING_REFRESH = "STALE_PENDING_REFRESH"
    LINEUP_READY_MARKET_REFRESH_PENDING = "LINEUP_READY_MARKET_REFRESH_PENDING"
    NOT_READY_SOURCE_ABSENT = "NOT_READY_SOURCE_ABSENT"
    NOT_READY_QUOTE_INCOMPLETE = "NOT_READY_QUOTE_INCOMPLETE"
    NOT_READY_MODEL_INPUT = "NOT_READY_MODEL_INPUT"
    SUPERSEDED = "SUPERSEDED"


@dataclass(frozen=True, kw_only=True)
class DynamicEvaluationInput:
    fixture_id: str
    market: str
    selection: str
    exact_line: float | None
    bookmaker_id: str | None
    capture_id: str | None
    quote_identity_hash: str | None
    model_input_hash: str | None
    evaluated_at: datetime
    checkpoint: str
    capture_at: datetime | None = None
    source_observations_present: bool = True
    exact_quote_complete: bool = True
    quote_fresh: bool = True
    model_ready: bool = True
    market_probability_ready: bool = True
    identity_conflict: bool = False
    model_probability: float | None = None
    market_probability: float | None = None
    expected_value: float | None = None
    ev_se: float | None = None
    decimal_odds: float | None = None
    lineup_input_hash: str | None = None
    lineup_confirmed_at: datetime | None = None
    post_lineup_quote: bool = False


@dataclass(frozen=True, kw_only=True)
class DynamicEvaluationVersion:
    evaluation_id: str
    identity_hash: str
    fixture_id: str
    market: str
    selection: str
    exact_line: float | None
    bookmaker_id: str | None
    capture_id: str | None
    quote_identity_hash: str | None
    model_input_hash: str | None
    lineup_input_hash: str | None
    checkpoint: str
    evaluated_at: datetime
    capture_at: datetime | None
    state: DynamicEvaluationState
    current_ev: float | None
    current_delta: float | None
    current_ev_minus_se: float | None
    required_ev: float
    required_delta: float
    required_ev_minus_se: float
    shortfall: dict[str, float]
    blockers: tuple[str, ...]
    user_message: str | None
    next_action: str | None
    supersedes_evaluation_id: str | None = None
    supersession_reason: str | None = None

    def as_dict(
        self,
        *,
        projected_state: DynamicEvaluationState | None = None,
        superseded_by_evaluation_id: str | None = None,
    ) -> dict[str, Any]:
        payload = asdict(self)
        payload["state"] = (projected_state or self.state).value
        payload["evaluated_at"] = _iso(self.evaluated_at)
        payload["capture_at"] = _iso(self.capture_at) if self.capture_at else None
        payload["blockers"] = list(self.blockers)
        payload["superseded_by_evaluation_id"] = superseded_by_evaluation_id
        payload["immutable"] = True
        payload["schema_version"] = "w2.dynamic_quote_evaluation.v1"
        return payload


@dataclass(frozen=True, kw_only=True)
class LineupConfirmedEvent:
    fixture_id: str
    captured_at: datetime
    lineup_input_hash: str
    home_starters: int
    away_starters: int
    home_lineup_identity_hash: str
    away_lineup_identity_hash: str
    checkpoint: str = LINEUP_CONFIRMED_CHECKPOINT

    def __post_init__(self) -> None:
        if self.home_starters != 11 or self.away_starters != 11:
            raise ValueError("STARTING_XI_INCOMPLETE")
        if not self.lineup_input_hash:
            raise ValueError("LINEUP_INPUT_HASH_MISSING")
        if not self.home_lineup_identity_hash or not self.away_lineup_identity_hash:
            raise ValueError("LINEUP_IDENTITY_HASH_MISSING")


@dataclass(frozen=True, kw_only=True)
class LockSnapshotResult:
    status: str
    snapshot: dict[str, Any] | None
    eligible_count: int
    rejected: tuple[dict[str, str], ...]
    checkpoint: str = T30_VALIDATION_CHECKPOINT


def classify_evaluation(value: DynamicEvaluationInput) -> DynamicEvaluationVersion:
    evaluated_at = _aware_utc(value.evaluated_at, field="evaluated_at")
    capture_at = (
        _aware_utc(value.capture_at, field="capture_at") if value.capture_at is not None else None
    )
    lineup_confirmed_at = (
        _aware_utc(value.lineup_confirmed_at, field="lineup_confirmed_at")
        if value.lineup_confirmed_at is not None
        else None
    )
    blockers: list[str] = []
    user_message: str | None = None
    next_action: str | None = None

    delta = (
        float(value.model_probability) - float(value.market_probability)
        if value.model_probability is not None and value.market_probability is not None
        else None
    )
    ev = float(value.expected_value) if value.expected_value is not None else None
    ev_se = float(value.ev_se) if value.ev_se is not None else None
    ev_minus_se = ev - ev_se if ev is not None and ev_se is not None else None

    if not value.source_observations_present:
        state = DynamicEvaluationState.NOT_READY_SOURCE_ABSENT
        blockers.append("SOURCE_OBSERVATIONS_ABSENT")
        user_message = SOURCE_ABSENT_USER_MESSAGE
        next_action = SOURCE_ABSENT_NEXT_ACTION
    elif value.identity_conflict:
        state = DynamicEvaluationState.NOT_READY_QUOTE_INCOMPLETE
        blockers.append("QUOTE_IDENTITY_CONFLICT")
    elif not value.exact_quote_complete or not value.quote_identity_hash:
        state = DynamicEvaluationState.NOT_READY_QUOTE_INCOMPLETE
        blockers.append("PAIR_INCOMPLETE")
    elif lineup_confirmed_at is not None and (
        capture_at is None
        or capture_at < lineup_confirmed_at
        or not value.post_lineup_quote
        or not value.lineup_input_hash
    ):
        state = DynamicEvaluationState.LINEUP_READY_MARKET_REFRESH_PENDING
        blockers.append("POST_LINEUP_FRESH_QUOTE_PENDING")
    elif not value.quote_fresh:
        state = DynamicEvaluationState.STALE_PENDING_REFRESH
        blockers.append("CURRENT_QUOTE_STALE")
    elif not value.model_ready or not value.market_probability_ready or not value.model_input_hash:
        state = DynamicEvaluationState.NOT_READY_MODEL_INPUT
        blockers.append("MODEL_OR_DEVIG_NOT_READY")
    elif ev is None or delta is None or ev_minus_se is None:
        state = DynamicEvaluationState.NOT_READY_MODEL_INPUT
        blockers.append("EV_EVIDENCE_INCOMPLETE")
    elif (
        ev > ACTIVE_EV_THRESHOLD
        and delta >= ACTIVE_DELTA_THRESHOLD
        and ev_minus_se > ACTIVE_EV_MINUS_SE_THRESHOLD
    ):
        state = DynamicEvaluationState.ANALYSIS_PICK_ACTIVE
    else:
        state = DynamicEvaluationState.NO_EDGE_CURRENT
        if ev <= ACTIVE_EV_THRESHOLD:
            blockers.append("EV_NOT_POSITIVE")
        if delta < ACTIVE_DELTA_THRESHOLD:
            blockers.append("DELTA_BELOW_THRESHOLD")
        if ev_minus_se <= ACTIVE_EV_MINUS_SE_THRESHOLD:
            blockers.append("EV_MINUS_SE_NOT_POSITIVE")

    shortfall = {
        "ev": round(max(ACTIVE_EV_THRESHOLD - ev, 0.0), 6) if ev is not None else 0.0,
        "delta": round(max(ACTIVE_DELTA_THRESHOLD - delta, 0.0), 6)
        if delta is not None
        else 0.0,
        "ev_minus_se": round(max(ACTIVE_EV_MINUS_SE_THRESHOLD - ev_minus_se, 0.0), 6)
        if ev_minus_se is not None
        else 0.0,
    }
    identity_payload = {
        "fixture_id": value.fixture_id,
        "market": value.market,
        "selection": value.selection,
        "exact_line": value.exact_line,
        "bookmaker_id": value.bookmaker_id,
        "capture_id": value.capture_id,
        "quote_identity_hash": value.quote_identity_hash,
        "model_input_hash": value.model_input_hash,
        "lineup_input_hash": value.lineup_input_hash,
        "checkpoint": value.checkpoint,
        "capture_at": _iso(capture_at) if capture_at else None,
    }
    identity_hash = _hash(identity_payload)
    return DynamicEvaluationVersion(
        evaluation_id=f"dqe-{identity_hash}",
        identity_hash=identity_hash,
        fixture_id=str(value.fixture_id),
        market=str(value.market),
        selection=str(value.selection),
        exact_line=float(value.exact_line) if value.exact_line is not None else None,
        bookmaker_id=str(value.bookmaker_id) if value.bookmaker_id else None,
        capture_id=str(value.capture_id) if value.capture_id else None,
        quote_identity_hash=str(value.quote_identity_hash) if value.quote_identity_hash else None,
        model_input_hash=str(value.model_input_hash) if value.model_input_hash else None,
        lineup_input_hash=str(value.lineup_input_hash) if value.lineup_input_hash else None,
        checkpoint=str(value.checkpoint),
        evaluated_at=evaluated_at,
        capture_at=capture_at,
        state=state,
        current_ev=round(ev, 6) if ev is not None else None,
        current_delta=round(delta, 6) if delta is not None else None,
        current_ev_minus_se=round(ev_minus_se, 6) if ev_minus_se is not None else None,
        required_ev=ACTIVE_EV_THRESHOLD,
        required_delta=ACTIVE_DELTA_THRESHOLD,
        required_ev_minus_se=ACTIVE_EV_MINUS_SE_THRESHOLD,
        shortfall=shortfall,
        blockers=tuple(blockers),
        user_message=user_message,
        next_action=next_action,
    )


class DynamicEvaluationLedger:
    """In-memory append-only projection used by DB and artifact adapters.

    Evaluation rows never change. Supersession is a separate relation projected
    at read time, so old business conclusions become ``SUPERSEDED`` without
    rewriting their original evidence.
    """

    def __init__(self, versions: Sequence[DynamicEvaluationVersion] = ()) -> None:
        self._versions: list[DynamicEvaluationVersion] = []
        self._by_identity: dict[str, DynamicEvaluationVersion] = {}
        self._superseded_by: dict[str, str] = {}
        self._supersession_reason: dict[str, str] = {}
        for version in versions:
            self.append(version)

    def append(
        self,
        value: DynamicEvaluationInput | DynamicEvaluationVersion,
        *,
        supersession_reason: str = "NEW_CAPTURE_OR_MODEL_INPUT",
    ) -> DynamicEvaluationVersion:
        candidate = (
            classify_evaluation(value) if isinstance(value, DynamicEvaluationInput) else value
        )
        existing = self._by_identity.get(candidate.identity_hash)
        if existing is not None:
            return existing
        previous = self.current_for(candidate.fixture_id, candidate.market)
        if previous is not None:
            candidate = DynamicEvaluationVersion(
                **{
                    **asdict(candidate),
                    "supersedes_evaluation_id": previous.evaluation_id,
                    "supersession_reason": supersession_reason,
                }
            )
            self._superseded_by[previous.evaluation_id] = candidate.evaluation_id
            self._supersession_reason[previous.evaluation_id] = supersession_reason
        self._versions.append(candidate)
        self._by_identity[candidate.identity_hash] = candidate
        return candidate

    def confirm_lineup(self, event: LineupConfirmedEvent) -> None:
        for version in list(self._versions):
            if (
                version.fixture_id != event.fixture_id
                or version.evaluation_id in self._superseded_by
            ):
                continue
            marker_hash = _hash(
                {
                    "event": LINEUP_CONFIRMED_CHECKPOINT,
                    "fixture_id": event.fixture_id,
                    "lineup_input_hash": event.lineup_input_hash,
                    "market": version.market,
                }
            )
            marker = DynamicEvaluationVersion(
                evaluation_id=f"dqe-{marker_hash}",
                identity_hash=marker_hash,
                fixture_id=version.fixture_id,
                market=version.market,
                selection=version.selection,
                exact_line=version.exact_line,
                bookmaker_id=None,
                capture_id=None,
                quote_identity_hash=None,
                model_input_hash=None,
                lineup_input_hash=event.lineup_input_hash,
                checkpoint=LINEUP_CONFIRMED_CHECKPOINT,
                evaluated_at=_aware_utc(event.captured_at, field="captured_at"),
                capture_at=None,
                state=DynamicEvaluationState.LINEUP_READY_MARKET_REFRESH_PENDING,
                current_ev=None,
                current_delta=None,
                current_ev_minus_se=None,
                required_ev=ACTIVE_EV_THRESHOLD,
                required_delta=ACTIVE_DELTA_THRESHOLD,
                required_ev_minus_se=ACTIVE_EV_MINUS_SE_THRESHOLD,
                shortfall={"ev": 0.0, "delta": 0.0, "ev_minus_se": 0.0},
                blockers=("POST_LINEUP_FRESH_QUOTE_PENDING",),
                user_message=None,
                next_action="立即执行首发后的受控赔率刷新",
            )
            self.append(marker, supersession_reason="LINEUP_INPUT_SUPERSEDED")

    def current_for(self, fixture_id: str, market: str) -> DynamicEvaluationVersion | None:
        for version in reversed(self._versions):
            if (
                version.fixture_id == fixture_id
                and version.market == market
                and version.evaluation_id not in self._superseded_by
            ):
                return version
        return None

    def as_dict(self) -> dict[str, Any]:
        versions = []
        for version in self._versions:
            superseded_by = self._superseded_by.get(version.evaluation_id)
            payload = version.as_dict(
                projected_state=(DynamicEvaluationState.SUPERSEDED if superseded_by else None),
                superseded_by_evaluation_id=superseded_by,
            )
            if superseded_by:
                payload["supersession_reason"] = self._supersession_reason[version.evaluation_id]
            versions.append(payload)
        return {
            "schema_version": "w2.dynamic_quote_ev_lifecycle.v1",
            "versions": versions,
            "current_evaluation_ids": [
                version.evaluation_id
                for version in self._versions
                if version.evaluation_id not in self._superseded_by
            ],
        }


def select_t30_validation_snapshot(
    snapshots: Sequence[Mapping[str, Any]],
    *,
    kickoff: datetime,
    tolerance_minutes: int = 5,
) -> LockSnapshotResult:
    kickoff_utc = _aware_utc(kickoff, field="kickoff")
    target = kickoff_utc - timedelta(minutes=30)
    tolerance = timedelta(minutes=max(int(tolerance_minutes), 0))
    eligible: list[tuple[float, datetime, dict[str, Any]]] = []
    rejected: list[dict[str, str]] = []
    for raw in snapshots:
        snapshot = dict(raw)
        capture_at = _parse_datetime(snapshot.get("capture_at") or snapshot.get("captured_at"))
        reason: str | None = None
        if capture_at is None:
            reason = "CAPTURE_TIME_MISSING"
        elif capture_at > kickoff_utc:
            reason = "POST_KICKOFF_REJECTED"
        elif abs(capture_at - target) > tolerance:
            reason = "OUTSIDE_T30_WINDOW"
        elif not bool(snapshot.get("exact_quote_complete", snapshot.get("quote_complete", False))):
            reason = "PAIR_INCOMPLETE"
        elif not bool(snapshot.get("quote_fresh", snapshot.get("fresh", False))):
            reason = "QUOTE_NOT_FRESH"
        elif not bool(snapshot.get("model_inputs_frozen", False)):
            reason = "MODEL_INPUTS_NOT_FROZEN"
        if reason is not None:
            rejected.append(
                {
                    "capture_id": str(snapshot.get("capture_id") or ""),
                    "reason": reason,
                }
            )
            continue
        assert capture_at is not None
        eligible.append((abs((capture_at - target).total_seconds()), capture_at, snapshot))
    if not eligible:
        return LockSnapshotResult(
            status="LOCK_SNAPSHOT_UNAVAILABLE",
            snapshot=None,
            eligible_count=0,
            rejected=tuple(rejected),
        )
    # Time proximity is the only selector. EV and price are deliberately absent
    # from the ordering, preventing retrospective best-price selection.
    eligible.sort(key=lambda item: (item[0], item[1], str(item[2].get("capture_id") or "")))
    selected = dict(eligible[0][2])
    selected["checkpoint"] = T30_VALIDATION_CHECKPOINT
    selected["validation_target_at"] = _iso(target)
    selected["validation_window_minutes"] = tolerance_minutes
    selected["validation_active"] = True
    return LockSnapshotResult(
        status="READY",
        snapshot=selected,
        eligible_count=len(eligible),
        rejected=tuple(rejected),
    )


def _hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=lambda value: _iso(value) if isinstance(value, datetime) else str(value),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _aware_utc(value: datetime, *, field: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{field.upper()}_MUST_BE_TIMEZONE_AWARE")
    return value.astimezone(UTC)


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return _aware_utc(value, field="capture_at")
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return _aware_utc(parsed, field="capture_at")
