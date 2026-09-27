"""One-way shadow evidence binding for newly persisted evaluation rows only."""

from __future__ import annotations

import logging
import math
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from w2.domain.canonical_serialization import (
    CURRENT_SERIALIZER_VERSION,
    HashDomain,
    SerializerVersion,
    _canonical_hash,
    canonical_sha256,
    canonical_sha256 as serialize_canonical_sha256,
)
from w2.domain.odds import settle_asian_handicap, settle_total_goals
from w2.domain.profit import (
    FROZEN_FADE_DELTA,
    REBATE_FORMULA_VERSION,
    REBATE_RATE,
    track_d_binary_cashflow,
    track_d_fair_probability,
)
from w2.infrastructure.persistence.forward_evidence_models import (
    ForwardClockModel,
    RecommendationReviewLedgerModel,
)
from w2.infrastructure.persistence.matchday_intake_models import MatchdayMarketObservationModel
from w2.infrastructure.persistence.model_forecast_models import ModelForecastCaptureModel
from w2.infrastructure.persistence.models import ResultModel
from w2.prematch.lifecycle import PRODUCER_INPUT_PROVENANCE_SCHEMA, SETTLEMENT_STATE_ORDER
from w2.tracking.model_forecast_ledger import (
    MODEL_FAMILY,
    MODEL_FORECAST_CAPTURE_HASH_DOMAIN,
    MODEL_FORECAST_INPUT_MANIFEST_HASH_DOMAIN,
)

TRACK_D_FADE = "TRACK_D_FADE"
VALIDATION_SIGNAL = "VALIDATION_SIGNAL"
VALIDATION_SIGNAL_WATERMARK = "验证期信号 · 非正式推荐 · 不计入档位"
CLOCK_ID = "candidate-c-r0-forward-v1"
T0 = datetime(2026, 9, 25, 8, 46, 32, tzinfo=UTC)
PREREG_SHA256 = "13b897871a37011b3647f860b819a9299a76f81d5af00be5eb2acf2142671a0f"
INPUT_VERSION = "w2.forward_evidence_input.v1"
_LOG = logging.getLogger(__name__)


def register_forward_clock(
    session: Session,
    *,
    started_at: datetime,
    code_revision: str,
    model_identity: str = "candidate-eval.v2",
) -> ForwardClockModel:
    """Explicit one-time registration; a repeat may only confirm identical fields."""
    if started_at.tzinfo is None or started_at.astimezone(UTC) < T0:
        raise ValueError("FORWARD_CLOCK_BEFORE_T0")
    if len(code_revision) != 40 or any(c not in "0123456789abcdef" for c in code_revision):
        raise ValueError("FORWARD_CLOCK_REVISION_INVALID")
    proposed = {
        "started_at": started_at.astimezone(UTC),
        "code_revision": code_revision,
        "model_identity": model_identity,
        "preregistration_sha256": PREREG_SHA256,
        "input_version": INPUT_VERSION,
    }
    existing = session.get(ForwardClockModel, CLOCK_ID)
    if existing is not None:
        if any(getattr(existing, key) != value for key, value in proposed.items()):
            raise ValueError("FORWARD_CLOCK_ALREADY_STARTED")
        return existing
    row = ForwardClockModel(clock_id=CLOCK_ID, **proposed)
    session.add(row)
    session.flush()
    return row


def _finite(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if math.isfinite(parsed) else None


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _parse_utc(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _aware_dt(value: datetime | None) -> datetime | None:
    """Restore UTC on SQLite read-back; production PostgreSQL already returns aware."""
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _xg_as_of_upper_bound(capture: Any) -> datetime | None:
    """Newest xG snapshot observation time the capture actually consumed.

    The producer's ``model_input_available_at`` must equal this upper bound of
    the four-field xG identities it bound into the capture -- the verifiable
    source reference for "model input was available no later than forecast".

    R5-01: BOTH sides must carry a legal source object with a legal timezone-aware
    ``as_of``. Missing one side or an unparseable/naive time is a source failure,
    never a silent fallback to the surviving side's max.
    """
    xg_identity = (capture.payload or {}).get("four_field_xg_identity")
    if not isinstance(xg_identity, dict):
        return None
    observed: list[datetime] = []
    for side in ("home", "away"):
        side_identity = xg_identity.get(side)
        if not isinstance(side_identity, dict):
            return None
        parsed = _parse_utc(side_identity.get("as_of"))
        if parsed is None:
            return None
        observed.append(parsed)
    return max(observed)


def _xg_component_upper_bound(capture: Any) -> datetime | None:
    """Newest xG component observation time the capture actually consumed.

    R6-03: a snapshot's self-reported ``as_of`` is not enough. Each component's
    ``captured_at`` must be at-or-before the snapshot ``as_of`` (snapshot
    self-consistency), and the returned upper bound is the newest component time
    so the caller can prove every component was available before the forecast.
    A missing side, missing component set, or an unparseable/naive component
    time fails closed with ``None``.
    """
    xg_identity = (capture.payload or {}).get("four_field_xg_identity")
    if not isinstance(xg_identity, dict):
        return None
    component_times: list[datetime] = []
    for side in ("home", "away"):
        side_identity = xg_identity.get(side)
        if not isinstance(side_identity, dict):
            return None
        snapshot_as_of = _parse_utc(side_identity.get("as_of"))
        if snapshot_as_of is None:
            return None
        components = side_identity.get("component_team_xg_matches")
        if not isinstance(components, list) or not components:
            return None
        side_times: list[datetime] = []
        for component in components:
            if not isinstance(component, dict):
                return None
            captured_at = _parse_utc(component.get("captured_at"))
            if captured_at is None:
                return None
            side_times.append(captured_at)
        side_upper = max(side_times)
        # The snapshot cannot claim an as_of earlier than the components it
        # actually consumed -- that would be a self-inconsistent source.
        if side_upper > snapshot_as_of:
            return None
        component_times.append(side_upper)
    return max(component_times)


def _score_matrix_from_payload(
    payload: dict[str, Any] | None,
) -> dict[tuple[int, int], float] | None:
    """从 capture payload 的 score_matrix_distribution 还原原始 score matrix。

    解析转换前拒绝坏行、重复格、非整数/负比分、非法概率，不 int 截断、
    不跳过坏行、不覆盖重复格。任何一行不合法即整体拒绝（返回 None）。
    """
    distribution = (payload or {}).get("score_matrix_distribution")
    if not isinstance(distribution, list):
        return None
    matrix: dict[tuple[int, int], float] = {}
    for row in distribution:
        if not isinstance(row, dict):
            return None
        home = row.get("home_goals")
        away = row.get("away_goals")
        probability = row.get("probability")
        if not isinstance(home, int) or isinstance(home, bool) or home < 0:
            return None
        if not isinstance(away, int) or isinstance(away, bool) or away < 0:
            return None
        if not isinstance(probability, (int, float)) or isinstance(probability, bool):
            return None
        probability = float(probability)
        if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
            return None
        if (home, away) in matrix:
            return None
        matrix[(home, away)] = probability
    return matrix


def _five_state_from_score_matrix(
    matrix: dict[tuple[int, int], float],
    market: str,
    selection: str,
    line: Decimal,
) -> dict[str, float] | None:
    """从原始 score matrix 独立重算该 market/selection/line 的五态分布。"""
    if market not in {"ASIAN_HANDICAP", "TOTALS"}:
        return None
    values = {state: 0.0 for state in SETTLEMENT_STATE_ORDER}
    for (home, away), probability in matrix.items():
        outcome = (
            settle_asian_handicap(home, away, selection, line).value
            if market == "ASIAN_HANDICAP"
            else settle_total_goals(home + away, selection, line).value
        )
        values[outcome] += probability
    return {state: round(values[state], 12) for state in SETTLEMENT_STATE_ORDER}


def _five_state_close(left: dict[str, float], right: dict[str, float]) -> bool:
    """五态一致性（1e-9 精度），独立 oracle 不与写入侧共用实现。"""
    if set(left) != set(right) or set(left) != set(SETTLEMENT_STATE_ORDER):
        return False
    return all(
        math.isfinite(left[state])
        and math.isfinite(right[state])
        and abs(left[state] - right[state]) <= 1e-9
        for state in SETTLEMENT_STATE_ORDER
    )


def _is_hex64(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        c in "0123456789abcdef" for c in value
    )


def _matrix_valid(matrix: dict[tuple[int, int], float]) -> bool:
    """矩阵行合法：非负整数比分、有限非负概率、质量合计约 1。"""
    total = 0.0
    for (home, away), probability in matrix.items():
        if not isinstance(home, int) or not isinstance(away, int) or home < 0 or away < 0:
            return False
        if not math.isfinite(probability) or probability < 0:
            return False
        total += probability
    return abs(total - 1.0) <= 1e-6


def _pair(
    session: Session,
    version: Any,
) -> tuple[list[MatchdayMarketObservationModel], str | None]:
    if not version.capture_id or version.exact_line is None:
        return [], "QUOTE_PAIR_MISSING"
    rows = session.scalars(
        select(MatchdayMarketObservationModel).where(
            MatchdayMarketObservationModel.provider_fixture_id
            == version.fixture_id.removeprefix("api_football:"),
            MatchdayMarketObservationModel.capture_id == version.capture_id,
            MatchdayMarketObservationModel.canonical_market == version.market,
            MatchdayMarketObservationModel.bookmaker_id == "4",
            MatchdayMarketObservationModel.suspended.is_(False),
            MatchdayMarketObservationModel.live.is_(False),
        )
    ).all()
    wanted = ("HOME", "AWAY") if version.market == "ASIAN_HANDICAP" else ("OVER", "UNDER")
    try:
        line = Decimal(str(version.exact_line))
    except (InvalidOperation, TypeError, ValueError):
        return [], "QUOTE_PAIR_MISSING"
    selected: list[MatchdayMarketObservationModel] = []
    for side in wanted:
        expected = (
            -line if version.market == "ASIAN_HANDICAP" and side != version.selection else line
        )
        matches = []
        for row in rows:
            try:
                matches_line = row.line is not None and abs(
                    Decimal(row.line) - expected
                ) <= Decimal("0.01")
            except (InvalidOperation, TypeError, ValueError):
                matches_line = False
            if (
                row.canonical_selection == side
                and matches_line
                and (_finite(row.decimal_odds) or 0) > 1
            ):
                matches.append(row)
        if len(matches) != 1:
            return [], "QUOTE_PAIR_MISMATCH"
        selected.append(matches[0])
    if (
        selected[0].bookmaker_id != selected[1].bookmaker_id
        or selected[0].captured_at != selected[1].captured_at
    ):
        return [], "QUOTE_PAIR_MISMATCH"
    selected_quote = next(
        (row for row in selected if row.canonical_selection == version.selection), None
    )
    if (
        selected_quote is None
        or not version.quote_identity_hash
        or version.capture_at != _aware_dt(selected_quote.captured_at)
        or _finite(version.decimal_odds) != _finite(selected_quote.decimal_odds)
    ):
        return [], "QUOTE_PAIR_MISMATCH"
    return selected, None


def build_track_d_validation_signal_in_session(
    session: Session, version: Any,
) -> dict[str, Any] | None:
    """Bind an UNDER evaluation to a captured, executable OVER channel quote.

    Pinnacle is the market probability anchor only. Its price can never be
    substituted for the channel price, including when the selected bookmaker
    itself is Pinnacle.
    """
    clock = session.get(ForwardClockModel, CLOCK_ID)
    signal_config = getattr(version, "track_d_validation_signal", None) or {}
    source_selection = str(signal_config.get("source_selection") or version.selection)
    if (
        clock is None
        or version.evaluated_at < clock.started_at
        or version.evaluation_policy_version != clock.model_identity
        or version.market != "TOTALS"
        or source_selection != "UNDER"
        or version.state.value not in {"ANALYSIS_PICK_ACTIVE", "NO_EDGE_CURRENT"}
        or not version.capture_id
        or not version.bookmaker_id
        or version.bookmaker_id == "4"
        or version.exact_line is None
        or not version.quote_identity_hash
    ):
        return None
    capture = (
        session.get(ModelForecastCaptureModel, version.model_forecast_capture_identity_hash)
        if version.model_forecast_capture_identity_hash else None
    )
    if (
        capture is None
        or capture.fixture_id != version.fixture_id
        or capture.captured_at is None
        or capture.kickoff_utc is None
        or capture.captured_at.tzinfo is None
        or capture.kickoff_utc.tzinfo is None
        or not capture.captured_at <= version.evaluated_at < capture.kickoff_utc
    ):
        return None
    observations = session.scalars(
        select(MatchdayMarketObservationModel).where(
            MatchdayMarketObservationModel.provider_fixture_id
            == version.fixture_id.removeprefix("api_football:"),
            MatchdayMarketObservationModel.capture_id == version.capture_id,
            MatchdayMarketObservationModel.canonical_market == "TOTALS",
            MatchdayMarketObservationModel.bookmaker_id.in_((version.bookmaker_id, "4")),
            MatchdayMarketObservationModel.suspended.is_(False),
            MatchdayMarketObservationModel.live.is_(False),
        )
    ).all()
    try:
        line = Decimal(str(version.exact_line))
    except (InvalidOperation, TypeError, ValueError):
        return None

    def quote(bookmaker: str, side: str) -> MatchdayMarketObservationModel | None:
        matches = []
        for row in observations:
            try:
                same_line = row.line is not None and Decimal(str(row.line)) == line
            except (InvalidOperation, TypeError, ValueError):
                same_line = False
            if (
                row.bookmaker_id == bookmaker
                and row.canonical_selection == side
                and same_line
                and (_finite(row.decimal_odds) or 0) > 1
                and row.captured_at is not None
                and row.captured_at <= version.evaluated_at
            ):
                matches.append(row)
        return matches[0] if len(matches) == 1 else None

    channel_under = quote(version.bookmaker_id, "UNDER")
    channel_over = quote(version.bookmaker_id, "OVER")
    pinnacle_over = quote("4", "OVER")
    pinnacle_under = quote("4", "UNDER")
    if not all((channel_under, channel_over, pinnacle_over, pinnacle_under)):
        return None
    assert channel_under and channel_over and pinnacle_over and pinnacle_under
    if (
        channel_under.captured_at != version.capture_at
        or _finite(channel_under.decimal_odds) != _finite(version.decimal_odds)
        or channel_over.captured_at != channel_under.captured_at
        or pinnacle_over.captured_at != pinnacle_under.captured_at
    ):
        return None
    market_odds = {
        "OVER": float(pinnacle_over.decimal_odds),
        "UNDER": float(pinnacle_under.decimal_odds),
    }
    try:
        p_over = track_d_fair_probability(market_odds, "OVER")
        p_fade = min(0.99, max(0.01, p_over + FROZEN_FADE_DELTA))
        channel_odds = float(channel_over.decimal_odds)
        fade_ev = track_d_binary_cashflow(p_fade, channel_odds)
    except (ValueError, KeyError):
        return None
    source_distribution = version.model_settlement_distribution or {}
    probabilities = [_finite(source_distribution.get(state)) for state in (
        "WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "LOSS",
    )]
    if (
        any(value is None or not 0.0 <= value <= 1.0 for value in probabilities)
        or abs(sum(value for value in probabilities if value is not None) - 1.0) > 1e-9
    ):
        return None
    loss = _finite(source_distribution.get("LOSS"))
    half_loss = _finite(source_distribution.get("HALF_LOSS"))
    if loss is None or half_loss is None:
        return None
    model_over_probability = loss + 0.5 * half_loss
    _assert_track_d_fade_not_intent_gated(market_odds, p_fade)
    return {
        "selection": "OVER",
        "line": str(line),
        "channel_odds": channel_odds,
        "channel_bookmaker_id": version.bookmaker_id,
        "channel_quote_identity": channel_over.observation_id,
        "channel_quote_captured_at": channel_over.captured_at.isoformat(),
        "pinnacle_odds": market_odds,
        "pinnacle_quote_observation_ids": [
            pinnacle_over.observation_id, pinnacle_under.observation_id,
        ],
        "pinnacle_quote_captured_at": pinnacle_over.captured_at.isoformat(),
        "pinnacle_quote_identity": canonical_sha256(
            {
                "schema_version": "w2.forward_quote_pair.v1",
                "observation_ids": [pinnacle_over.observation_id, pinnacle_under.observation_id],
            },
            domain=HashDomain.PREMATCH_READ_MODEL_GENERIC,
        ),
        "model_reference_probability": model_over_probability,
        "fade_probability": p_fade,
        "fade_delta": FROZEN_FADE_DELTA,
        "fade_ev_channel_with_rebate": fade_ev,
    }


def _assert_track_d_fade_not_intent_gated(
    pinnacle_odds: dict[str, float], fade_probability: float,
) -> None:
    """Production-path tripwire (PR-4): the Track D fade is Pinnacle-anchored.

    The fade probability must be the frozen Pinnacle de-vig plus
    ``FROZEN_FADE_DELTA`` formula.  Any other probability source (in particular
    the OU intent gate, which emits zero positive recommendations) is forbidden;
    this keeps the fade path mutually exclusive with the intent gate.
    """
    expected = min(
        0.99,
        max(0.01, track_d_fair_probability(pinnacle_odds, "OVER") + FROZEN_FADE_DELTA),
    )
    if fade_probability != expected:
        raise AssertionError("TRACK_D_FADE_MUST_USE_PINNACLE_ANCHOR_NOT_INTENT_GATE")


def append_forward_evidence_in_session(
    session: Session,
    version: Any,
    *,
    _event_type: str = "EVALUATION_SNAPSHOT",
) -> RecommendationReviewLedgerModel | None:
    """Append an evaluation event iff an explicit clock exists and the row is new.

    Missing/invalid provenance becomes PIT_UNPROVABLE evidence, never a fabricated
    time or coefficient. This function has no recommendation output.
    """
    clock = session.get(ForwardClockModel, CLOCK_ID)
    # SQLite drops tzinfo on read; production PostgreSQL keeps it aware. Restore
    # UTC before any aware/naive comparison so the same check holds on both.
    if clock is not None and clock.started_at.tzinfo is None:
        clock.started_at = clock.started_at.replace(tzinfo=UTC)
    if clock is None or version.evaluated_at < clock.started_at:
        return None
    if version.evaluation_policy_version != clock.model_identity:
        return None
    capture = (
        session.get(ModelForecastCaptureModel, version.model_forecast_capture_identity_hash)
        if version.model_forecast_capture_identity_hash
        else None
    )
    fade_requested = bool(getattr(version, "track_d_validation_signal", None))
    fade = build_track_d_validation_signal_in_session(session, version) if fade_requested else None
    quotes, pair_error = ([], None) if fade is not None else _pair(session, version)
    simulation = (
        ((capture.payload.get("simulation_replay") or {}).get("simulation") or {})
        if capture and isinstance(capture.payload, dict)
        else {}
    )
    calibration = simulation.get("calibration") if isinstance(simulation, dict) else None
    params = calibration.get("params") if isinstance(calibration, dict) else None
    lambda_home = _finite(simulation.get("lambda_home")) if isinstance(simulation, dict) else None
    lambda_away = _finite(simulation.get("lambda_away")) if isinstance(simulation, dict) else None
    rho = _finite(params.get("dixon_coles_rho")) if isinstance(params, dict) else None
    input_hash = calibration.get("simulation_input_hash") if isinstance(calibration, dict) else None
    kickoff = capture.kickoff_utc if capture else None
    forecast_at = capture.captured_at if capture else None
    if kickoff is not None and kickoff.tzinfo is None:
        kickoff = kickoff.replace(tzinfo=UTC)
    if forecast_at is not None and forecast_at.tzinfo is None:
        forecast_at = forecast_at.replace(tzinfo=UTC)
    quote_at = (
        datetime.fromisoformat(fade["channel_quote_captured_at"])
        if fade is not None else _aware_dt(quotes[0].captured_at) if quotes else None
    )
    market_quote_at = (
        datetime.fromisoformat(fade["pinnacle_quote_captured_at"])
        if fade is not None else quote_at
    )
    times = (forecast_at, quote_at, market_quote_at, kickoff)
    pit_ok = (
        all(value is not None and value.tzinfo is not None for value in times)
        and forecast_at <= version.evaluated_at < kickoff
        and quote_at <= version.evaluated_at
        and market_quote_at <= version.evaluated_at
        and version.evaluated_at >= clock.started_at
    )
    reasons = []
    if not pit_ok:
        reasons.append("PIT_UNPROVABLE")
    if pair_error:
        reasons.append(pair_error)
    if fade_requested and fade is None:
        reasons.append("TRACK_D_CHANNEL_OR_MARKET_QUOTE_UNPROVABLE")
    if any(value is None for value in (lambda_home, lambda_away, rho)) or not input_hash:
        reasons.append("MODEL_PARAMETER_UNPROVABLE")
    # A：producer 实际输入证据 —— 必填合法 64hex，且版本化 provenance 可独立复算。
    # 非空不等于正确，"合法 64hex" 也不等于内容正确；provenance 携带 model_input_hash
    # 的 preimage 组件（simulation/analysis_evidence digest + lineup + scoreline contract），
    # 据此复算 model_input_hash，任一不自洽即显式拒绝。
    provenance = getattr(version, "producer_input_provenance", None)
    if not getattr(version, "model_input_hash", None):
        reasons.append("MISSING_PRODUCER_INPUT")
    elif not _is_hex64(version.model_input_hash):
        reasons.append("INVALID_PRODUCER_INPUT_HASH")
    if not isinstance(provenance, dict):
        reasons.append("MISSING_PRODUCER_INPUT_PROVENANCE")
    elif provenance.get("schema_version") != PRODUCER_INPUT_PROVENANCE_SCHEMA:
        reasons.append("INVALID_PRODUCER_INPUT_PROVENANCE")
    elif version.model_input_hash:
        # R4-03: a missing component digest is not the same as null -- the
        # producer must have emitted every digest it consumed. Absorbing an
        # absent digest via .get(None) and still recomputing would let a
        # deleted component pass as self-consistent.
        if "simulation_digest" not in provenance:
            reasons.append("MISSING_PRODUCER_SIMULATION_DIGEST")
        if "analysis_evidence_digest" not in provenance:
            reasons.append("MISSING_PRODUCER_ANALYSIS_EVIDENCE_DIGEST")
        model_input_identity = {
            "simulation": provenance.get("simulation_digest"),
            "analysis_evidence": provenance.get("analysis_evidence_digest"),
            "lineup_input_hash": provenance.get("lineup_input_hash"),
        }
        if "scoreline_projection_contract_version" in provenance:
            model_input_identity["scoreline_projection_contract_version"] = provenance[
                "scoreline_projection_contract_version"
            ]
        if canonical_sha256(
            model_input_identity,
            domain=HashDomain.PREMATCH_READ_MODEL_DYNAMIC_EVALUATION,
        ) != version.model_input_hash:
            reasons.append("PRODUCER_INPUT_HASH_MISMATCH")
    if (
        capture is None
        or capture.fixture_id != version.fixture_id
        or not version.calibration_identity
    ):
        reasons.append("MODEL_IDENTITY_UNPROVABLE")
    if capture is not None:
        if capture.model_family != MODEL_FAMILY:
            reasons.append("MODEL_FAMILY_MISMATCH")
        # R1 真实来源贯通：producer 的模型版本/完整矩阵身份与 capture 显式对照，
        # 不依赖 identity_hash 回溯的隐含保证。
        if getattr(version, "model_version", None) != capture.model_version:
            reasons.append("MODEL_VERSION_MISMATCH")
        if getattr(version, "score_matrix_hash", None) != capture.score_matrix_hash:
            reasons.append("SCORE_MATRIX_HASH_MISMATCH")
        # R3 完整性：64hex 仅格式检查；用现有 canonical 合同真实重算 payload /
        # identity / manifest / 完整矩阵，任一不自洽即显式拒绝。
        payload = capture.payload if isinstance(capture.payload, dict) else {}
        if not _is_hex64(getattr(capture, "capture_identity_hash", None)):
            reasons.append("INVALID_CAPTURE_HASH")
        else:
            identity_payload = {
                key: value for key, value in payload.items() if key != "capture_identity_hash"
            }
            if capture.capture_identity_hash != canonical_sha256(
                identity_payload, domain=MODEL_FORECAST_CAPTURE_HASH_DOMAIN
            ):
                reasons.append("CAPTURE_IDENTITY_MISMATCH")
        if not _is_hex64(getattr(capture, "payload_sha256", None)):
            reasons.append("INVALID_PAYLOAD_HASH")
        elif capture.payload_sha256 != canonical_sha256(
            payload, domain=MODEL_FORECAST_CAPTURE_HASH_DOMAIN
        ):
            reasons.append("PAYLOAD_HASH_MISMATCH")
        manifest = payload.get("model_input_manifest")
        if not manifest:
            reasons.append("MISSING_MODEL_INPUT_MANIFEST")
        elif not _is_hex64(getattr(capture, "model_input_manifest_hash", None)):
            reasons.append("INVALID_MANIFEST_HASH")
        elif capture.model_input_manifest_hash != canonical_sha256(
            manifest, domain=MODEL_FORECAST_INPUT_MANIFEST_HASH_DOMAIN
        ):
            reasons.append("MANIFEST_HASH_MISMATCH")
        if not _is_hex64(getattr(capture, "score_matrix_hash", None)):
            reasons.append("INVALID_SCORE_MATRIX_HASH")
        elif capture.score_matrix_hash != _canonical_hash(
            payload.get("score_matrix_distribution")
        ):
            reasons.append("CAPTURE_SCORE_MATRIX_HASH_MISMATCH")
        simulation = (
            (payload.get("simulation_replay") or {}).get("simulation") or {}
            if isinstance(payload.get("simulation_replay"), dict)
            else {}
        )
        if capture.model_version != simulation.get("model_version"):
            reasons.append("MODEL_VERSION_MISMATCH")
        # 交叉核验（A-R3-01）：producer 的 simulation digest 必须等于 capture 的
        # simulation 同域重算；producer 输入/报价时间逐项满足 PIT。
        if (
            isinstance(provenance, dict)
            and provenance.get("schema_version") == PRODUCER_INPUT_PROVENANCE_SCHEMA
        ):
            # R5: the producer's simulation digest is computed by the frozen
            # materializer through read_model_projection.canonical_sha256, which
            # serializes under LEGACY_V1 (the frozen artifact identity contract).
            # Recompute the capture's simulation under the same version so the two
            # agree; V2 serialization would falsely reject every real chain.
            if provenance.get("simulation_digest") != serialize_canonical_sha256(
                simulation,
                domain=HashDomain.PREMATCH_READ_MODEL_SIMULATION,
                version=SerializerVersion.LEGACY_V1,
            ):
                reasons.append("PRODUCER_SIMULATION_MISMATCH")
            # R4-03: the provenance lineup identity must agree with the evaluation's
            # own lineup identity. Non-post-lineup null must equal null.
            if provenance.get("lineup_input_hash") != getattr(
                version, "lineup_input_hash", None
            ):
                reasons.append("PRODUCER_LINEUP_MISMATCH")
            # R6-02: the analysis evidence digest is the CURRENT quote's analysis
            # digest, and must be a legal 64-hex (null / fabricated / equal-empty
            # strings never pass). It is recomputed from the actual analysis
            # evidence content carried on this evaluation's provenance -- never
            # read from the shadow checkpoint, which is written after this
            # evaluation and can be replaced by a later quote (R6-01). Tampering
            # with the content without rehashing therefore fails here.
            analysis_digest = provenance.get("analysis_evidence_digest")
            if not _is_hex64(analysis_digest):
                reasons.append("INVALID_PRODUCER_ANALYSIS_EVIDENCE_DIGEST")
            elif "analysis_evidence" not in provenance:
                reasons.append("MISSING_PRODUCER_ANALYSIS_EVIDENCE_CONTENT")
            elif not isinstance(provenance.get("analysis_evidence"), dict):
                reasons.append("INVALID_PRODUCER_ANALYSIS_EVIDENCE_CONTENT")
            else:
                # R6: the materializer computes analysis_evidence_sha256 through
                # read_model_projection.canonical_sha256 (LEGACY_V1), so recompute
                # the content under the same serialization version.
                recomputed_analysis_digest = serialize_canonical_sha256(
                    provenance["analysis_evidence"],
                    domain=HashDomain.PREMATCH_READ_MODEL_ANALYSIS_EVIDENCE,
                    version=SerializerVersion.LEGACY_V1,
                )
                if analysis_digest != recomputed_analysis_digest:
                    reasons.append("PRODUCER_ANALYSIS_EVIDENCE_MISMATCH")
            model_input_at = _parse_utc(provenance.get("model_input_available_at"))
            quote_available_at = _parse_utc(provenance.get("quote_available_at"))
            if (
                model_input_at is None
                or quote_available_at is None
                or forecast_at is None
                or model_input_at > forecast_at
                or quote_available_at > version.evaluated_at
            ):
                reasons.append("PRODUCER_INPUT_TIME_UNPROVABLE")
            # R4-01: the model input availability is a source fact -- the newest
            # xG snapshot observation time -- not a back-filled capture time. It
            # must equal the capture's xG as-of upper bound (verifiable reference).
            xg_upper_bound = _xg_as_of_upper_bound(capture)
            if xg_upper_bound is None or model_input_at is None or model_input_at != xg_upper_bound:
                reasons.append("PRODUCER_INPUT_SOURCE_MISMATCH")
            # R6-03: the snapshot self-reported as_of is not enough -- every xG
            # component actually consumed must be provably available before the
            # forecast, and the snapshot as_of must not predate its components.
            component_upper = _xg_component_upper_bound(capture)
            if component_upper is None:
                reasons.append("PRODUCER_INPUT_COMPONENT_SOURCE_MISMATCH")
            elif forecast_at is not None and component_upper > forecast_at:
                reasons.append("PRODUCER_INPUT_COMPONENT_FUTURE")
        matrix = _score_matrix_from_payload(payload)
        if version.model_settlement_distribution is None:
            reasons.append("MISSING_SETTLEMENT_DISTRIBUTION")
        elif not matrix or not _matrix_valid(matrix):
            reasons.append("INVALID_SCORE_MATRIX")
        else:
            try:
                line = Decimal(str(version.exact_line))
            except (InvalidOperation, TypeError, ValueError):
                line = None
            if line is not None:
                # fade 以原 UNDER 方向核验源五态（派生 OVER 另按旧冻结合同计算）。
                source_selection = str(
                    (getattr(version, "track_d_validation_signal", None) or {}).get(
                        "source_selection"
                    )
                    or version.selection
                )
                expected = _five_state_from_score_matrix(
                    matrix, version.market, source_selection, line
                )
                if expected is not None and not _five_state_close(
                    version.model_settlement_distribution, expected
                ):
                    reasons.append("SETTLEMENT_DISTRIBUTION_MISMATCH")
    quote_ids = (
        fade["pinnacle_quote_observation_ids"]
        if fade is not None else [row.observation_id for row in quotes]
    )
    quote_pair_identity = (
        canonical_sha256(
            {"schema_version": "w2.forward_quote_pair.v1", "observation_ids": quote_ids},
            domain=HashDomain.PREMATCH_READ_MODEL_GENERIC,
        )
        if quote_ids
        else None
    )
    fade_valid = fade is not None and not reasons
    signal_config = getattr(version, "track_d_validation_signal", None) or {}
    source_selection = str(signal_config.get("source_selection") or version.selection)
    payload = {
        "schema_version": "w2.recommendation_review_ledger.evaluation.v1",
        "event_type": _event_type,
        "evaluation_id": version.evaluation_id,
        "derived_from_evaluation_id": version.evaluation_id,
        "decision_version": version.evaluation_policy_version,
        "calibration_identity": version.calibration_identity,
        "market_quote_identity": (
            fade["pinnacle_quote_identity"]
            if (fade is not None and fade_valid)
            else version.quote_identity_hash
        ),
        "source_quote_identity": version.quote_identity_hash,
        "quote_pair_identity": quote_pair_identity,
        "quote_observation_ids": quote_ids,
        "candidate_kind": (
            TRACK_D_FADE
            if fade_valid
            else
            "OFFICIAL_RECOMMENDATION"
            if version.market != "TOTALS" and version.state.value == "ANALYSIS_PICK_ACTIVE"
            else "NO_EDGE_DISPLAY"
            if version.state.value == "NO_EDGE_CURRENT"
            else "FACTOR_GATE_BLOCKED"
            if version.state.value == "BLOCKED_BY_FACTOR"
            else "EVALUATION_ONLY"
        ),
        "original_selection": source_selection,
        "display_state": (
            VALIDATION_SIGNAL if fade_valid else version.state.value
        ),
        "watermark": (
            VALIDATION_SIGNAL_WATERMARK if fade_valid else None
        ),
        "official_recommendation": False if fade_requested else (
            version.market != "TOTALS" and version.state.value == "ANALYSIS_PICK_ACTIVE"
        ),
        "track_d_validation_signal": fade if fade_valid else None,
        "factor_gate_state": version.factor_decision_status,
        "fixture_id": version.fixture_id,
        "competition_id": getattr(version, "competition_id", None),
        "market": version.market,
        "evaluated_at": version.evaluated_at.isoformat(),
        "captured_at": _iso(quote_at),
        "channel_quote_captured_at": _iso(quote_at) if fade else None,
        "pinnacle_quote_captured_at": _iso(market_quote_at) if fade else None,
        "forecast_captured_at": _iso(forecast_at),
        "first_quote_captured_at": _iso(market_quote_at) if quote_ids else None,
        "second_quote_captured_at": _iso(market_quote_at) if quote_ids else None,
        "first_quote_selection": (
            "OVER" if fade is not None
            else quotes[0].canonical_selection if quotes else None
        ),
        "second_quote_selection": (
            "UNDER" if fade is not None
            else quotes[1].canonical_selection if quotes else None
        ),
        "kickoff_utc": kickoff.isoformat() if kickoff else None,
        "lambda_home": lambda_home,
        "lambda_away": lambda_away,
        "rho": rho,
        "model_input_identity": input_hash,
        "five_state_distribution": version.model_settlement_distribution,
        "forecast_capture_identity": version.model_forecast_capture_identity_hash,
        "model_forecast_manifest_hash": capture.model_input_manifest_hash if capture else None,
        "evaluation_identity_hash": version.identity_hash,
        "selection": "OVER" if fade_valid else version.selection,
        "exact_line": str(version.exact_line) if version.exact_line is not None else None,
        "channel_quote_identity": fade["channel_quote_identity"] if fade else None,
        "pinnacle_quote_identity": fade["pinnacle_quote_identity"] if fade else None,
        "decimal_odds_channel": fade["channel_odds"] if fade else None,
        "decimal_odds_pinnacle": fade["pinnacle_odds"]["OVER"] if fade else None,
        "channel_bookmaker_id": fade["channel_bookmaker_id"] if fade else None,
        "model_reference_probability": (
            fade["model_reference_probability"] if fade else None
        ),
        "fade_probability": fade["fade_probability"] if fade else None,
        "fade_delta": FROZEN_FADE_DELTA if fade else None,
        "pit_status": "PROVABLE" if not reasons else "PIT_UNPROVABLE",
        "exclusion_reasons": reasons,
        "code_revision": clock.code_revision,
        "input_version": clock.input_version,
        "preregistration_sha256": clock.preregistration_sha256,
        "serialization_version": CURRENT_SERIALIZER_VERSION.value,
    }
    digest = canonical_sha256(payload, domain=HashDomain.PREMATCH_READ_MODEL_GENERIC)
    existing = session.get(RecommendationReviewLedgerModel, digest)
    if existing is not None:
        if existing.payload_sha256 != digest or existing.payload != payload:
            raise ValueError("FORWARD_EVIDENCE_IDENTITY_CONFLICT")
        return existing
    row = RecommendationReviewLedgerModel(
        review_event_id=digest,
        evaluation_id=version.evaluation_id,
        event_type=_event_type,
        evaluated_at=version.evaluated_at,
        pit_status=payload["pit_status"],
        payload=payload,
        payload_sha256=digest,
        created_at=datetime.now(UTC),
    )
    session.add(row)
    session.flush()
    return row


def record_shadow_evidence_in_session(
    session: Session, version: Any,
) -> RecommendationReviewLedgerModel | None:
    """Keep the shadow writer outside recommendation transaction correctness.

    A savepoint rolls back a writer failure without removing the original
    evaluation. The Dashboard counts missing ledger rows as write gaps, and
    the exception is logged with the evaluation identity for investigation.
    """
    original_written = False
    fade_row: RecommendationReviewLedgerModel | None = None
    try:
        with session.begin_nested():
            append_forward_evidence_in_session(session, version)
            original_written = True
    except Exception:
        _LOG.exception("FORWARD_EVIDENCE_WRITE_FAILED evaluation_id=%s", version.evaluation_id)
    if original_written and (
        version.market == "TOTALS"
        and version.selection == "UNDER"
        and version.state.value in {"ANALYSIS_PICK_ACTIVE", "NO_EDGE_CURRENT"}
    ):
        try:
            with session.begin_nested():
                fade_version = replace(
                    version,
                    selection="OVER",
                    track_d_validation_signal={
                        "candidate_kind": TRACK_D_FADE,
                        "source_selection": "UNDER",
                    },
                )
                fade_row = append_forward_evidence_in_session(
                    session, fade_version, _event_type="DECISION_SNAPSHOT"
                )
        except Exception:
            _LOG.exception("TRACK_D_EVIDENCE_WRITE_FAILED evaluation_id=%s", version.evaluation_id)
    if fade_row is not None and fade_row.payload.get("candidate_kind") == TRACK_D_FADE:
        return fade_row
    return None


def append_validation_signal_settlement_in_session(
    session: Session,
    *,
    evaluation_id: str,
    settlement: str,
    profit_units_channel: float,
    settled_at: datetime,
    home_goals: int | None = None,
    away_goals: int | None = None,
) -> RecommendationReviewLedgerModel:
    """Append settlement facts for a fade signal using channel price + rebate."""
    original = session.scalar(
        select(RecommendationReviewLedgerModel).where(
            RecommendationReviewLedgerModel.evaluation_id == evaluation_id,
            RecommendationReviewLedgerModel.event_type == "DECISION_SNAPSHOT",
        )
    )
    if original is None or (original.payload or {}).get("candidate_kind") != TRACK_D_FADE:
        raise ValueError("TRACK_D_SETTLEMENT_SOURCE_NOT_FOUND")
    source = original.payload or {}
    rebate = abs(float(profit_units_channel)) * float(REBATE_RATE)
    payload = {
        "schema_version": "w2.recommendation_review_ledger.settlement.v1",
        "event_type": "SETTLEMENT_OBSERVED",
        "evaluation_id": evaluation_id,
        "derived_from_evaluation_id": evaluation_id,
        "market_quote_identity": source.get("market_quote_identity"),
        "channel_quote_identity": source.get("channel_quote_identity"),
        "evaluated_at": source.get("evaluated_at"),
        "captured_at": source.get("first_quote_captured_at"),
        "kickoff_utc": source.get("kickoff_utc"),
        "selection": "OVER",
        "market": source.get("market"),
        "exact_line": source.get("exact_line"),
        "decimal_odds_channel": source.get("decimal_odds_channel"),
        "candidate_kind": TRACK_D_FADE,
        "display_state": VALIDATION_SIGNAL,
        "watermark": VALIDATION_SIGNAL_WATERMARK,
        "settlement": settlement,
        "home_goals": home_goals,
        "away_goals": away_goals,
        "profit_units_channel": profit_units_channel,
        "rebate_units_channel": rebate,
        "profit_units_channel_with_rebate": profit_units_channel + rebate,
        "rebate_formula_version": REBATE_FORMULA_VERSION,
        "settlement_observed_at": settled_at.isoformat(),
    }
    digest = canonical_sha256(payload, domain=HashDomain.PREMATCH_READ_MODEL_GENERIC)
    existing = session.get(RecommendationReviewLedgerModel, digest)
    if existing is not None:
        if existing.payload_sha256 != digest or existing.payload != payload:
            raise ValueError("TRACK_D_SETTLEMENT_IDENTITY_CONFLICT")
        return existing
    row = RecommendationReviewLedgerModel(
        review_event_id=digest,
        evaluation_id=evaluation_id,
        event_type="SETTLEMENT_OBSERVED",
        evaluated_at=settled_at,
        pit_status="PROVABLE",
        payload=payload,
        payload_sha256=digest,
        created_at=datetime.now(UTC),
    )
    session.add(row)
    session.flush()
    return row


def settle_track_d_validation_signals_in_session(
    session: Session, *, now: datetime,
) -> dict[str, int]:
    """Append immutable settlement events once authoritative results exist."""
    snapshots = list(
        session.scalars(
            select(RecommendationReviewLedgerModel).where(
                RecommendationReviewLedgerModel.event_type == "DECISION_SNAPSHOT",
            )
        )
    )
    settled_ids = {
        row.evaluation_id
        for row in session.scalars(
            select(RecommendationReviewLedgerModel).where(
                RecommendationReviewLedgerModel.event_type == "SETTLEMENT_OBSERVED",
                RecommendationReviewLedgerModel.payload["candidate_kind"].as_string()
                == TRACK_D_FADE,
            )
        )
    }
    fixture_ids = {
        str((row.payload or {}).get("fixture_id") or "")
        for row in snapshots
        if (row.payload or {}).get("candidate_kind") == TRACK_D_FADE
        and row.pit_status == "PROVABLE"
        and row.evaluation_id not in settled_ids
    }
    if not fixture_ids:
        return {"signals": 0, "settled": 0}
    canonical_ids = set(fixture_ids) | {f"api_football:{value}" for value in fixture_ids}
    results = {
        str(result.fixture_id): result
        for result in session.scalars(
            select(ResultModel).where(ResultModel.fixture_id.in_(canonical_ids))
        )
    }
    settled = 0
    signals = 0
    units = {"WIN": 1.0, "HALF_WIN": 0.5, "PUSH": 0.0, "HALF_LOSS": -0.5, "LOSS": -1.0}
    for row in snapshots:
        payload = row.payload or {}
        if (
            payload.get("candidate_kind") != TRACK_D_FADE
            or row.pit_status != "PROVABLE"
            or row.evaluation_id in settled_ids
        ):
            continue
        signals += 1
        fixture_id = str(payload.get("fixture_id") or "")
        result = results.get(fixture_id) or results.get(f"api_football:{fixture_id}")
        odds = _finite(payload.get("decimal_odds_channel"))
        line = payload.get("exact_line")
        if result is None or odds is None or line is None:
            continue
        kickoff_text = payload.get("kickoff_utc")
        kickoff = datetime.fromisoformat(str(kickoff_text)) if kickoff_text else None
        confirmed_at = result.confirmed_at
        if (
            kickoff is None
            or kickoff.tzinfo is None
            or confirmed_at is None
            or result.result_status not in {"FT", "AET", "PEN"}
            or confirmed_at.replace(tzinfo=confirmed_at.tzinfo or UTC) > now
            or confirmed_at.replace(tzinfo=confirmed_at.tzinfo or UTC) < kickoff
        ):
            continue
        try:
            outcome = settle_total_goals(
                result.home_goals + result.away_goals, "OVER", Decimal(str(line))
            ).value
            unit = units[outcome]
            profit = unit * (odds - 1.0) if unit > 0 else unit
            append_validation_signal_settlement_in_session(
                session,
                evaluation_id=row.evaluation_id,
                settlement=outcome,
                profit_units_channel=profit,
                settled_at=confirmed_at.replace(tzinfo=confirmed_at.tzinfo or UTC),
                home_goals=result.home_goals,
                away_goals=result.away_goals,
            )
            settled += 1
        except (InvalidOperation, TypeError, ValueError, KeyError):
            _LOG.exception("TRACK_D_SETTLEMENT_WRITE_FAILED evaluation_id=%s", row.evaluation_id)
    return {"signals": signals, "settled": settled}
