from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from statistics import median
from typing import Any

from w2.domain.enums import SettlementOutcome
from w2.domain.odds import settle_asian_handicap, settle_total_goals
from w2.markets.asian_handicap_mainline import select_canonical_ah_mainline
from w2.markets.devig import DevigMethod, devig
from w2.markets.settlement_probability import effective_settlement_probability
from w2.markets.totals_mainline import select_canonical_totals_mainline
from w2.strategy.simulate import score_matrix_from_simulation

SUPPORTED_MARKETS = ("ASIAN_HANDICAP", "TOTALS")
MOVEMENT_STATUSES = (
    "INSUFFICIENT",
    "STABLE",
    "PRICE_MOVEMENT",
    "LINE_MOVEMENT",
    "LINE_AND_PRICE_MOVEMENT",
)
MODEL_LAB_STATUSES = (
    "MODEL_NOT_READY",
    "MARKET_NOT_READY",
    "INSUFFICIENT_BOOKMAKER_DEPTH",
    "COMPARABLE_WITHIN_MARKET_RANGE",
    "MODEL_OUTSIDE_MARKET_RANGE",
)
EVIDENCE_REASON_CODES = (
    "SYNTHETIC_EVIDENCE",
    "RAW_PAYLOAD_MISSING",
    "ENDPOINT_CAPTURE_MISSING",
    "FIXTURE_IDENTITY_MISSING",
    "OUT_OF_RUNTIME_WHITELIST",
    "UNSUPPORTED_MARKET",
    "INVALID_LINE",
    "INVALID_PRICE",
    "IDENTITY_CONFLICT",
    "DUPLICATE_CONFLICTING_OBSERVATION",
    "LIVE_OR_SUSPENDED",
    "POST_KICKOFF_OBSERVATION",
)

_SIDES = {
    "ASIAN_HANDICAP": ("HOME", "AWAY"),
    "TOTALS": ("OVER", "UNDER"),
}

PHASE_0_5_FROZEN_CONTEXT = {
    "protocol": "W2_PHASE_0_5_AH_OU_EDGE_EXISTENCE_PROTOCOL_V1_RC3",
    "final_verdict": "NO_EDGE",
    "v_continuation_gate": "FAIL",
    "ou_close_best_predictive_lift": -0.0000758,
    "ah_close_best_predictive_lift": -0.0006467,
    "ou_pre_best_frozen_selections": 7566,
    "ou_pre_best_frozen_strategy_roi": "-5.32%",
    "historical_incremental_edge": "NOT_PROVEN",
    "h_result_access": "PERMANENTLY_CLOSED",
    "reexecuted": False,
}


def build_round3_intelligence(
    observations: Sequence[Mapping[str, Any]],
    *,
    fixture_id: str,
    competition_id: str,
    kickoff_utc: datetime,
    simulation: Mapping[str, Any] | None,
    as_of: datetime,
    freshness_seconds: int = 3600,
) -> dict[str, Any]:
    """Build the read-only Round-3 market and model diagnostics."""
    canonical_fixture_id = _canonical_fixture_id(fixture_id)
    kickoff = _utc(kickoff_utc)
    reference = _utc(as_of)
    accepted, rejected = eligible_observations(
        observations,
        fixture_id=canonical_fixture_id,
        competition_id=competition_id,
        kickoff_utc=kickoff,
    )
    markets = {
        market: _market_radar(
            accepted,
            market=market,
            fixture_id=canonical_fixture_id,
            kickoff_utc=kickoff,
            as_of=reference,
            freshness_seconds=freshness_seconds,
        )
        for market in SUPPORTED_MARKETS
    }
    radar = {
        "schema_version": "w2.market-radar.v1",
        "authority": "REAL_PERSISTED_MARKET_EVIDENCE",
        "fixture_id": fixture_id,
        "competition_id": competition_id,
        "supported_markets": list(SUPPORTED_MARKETS),
        "evidence": {
            "accepted_observation_count": len(accepted),
            "rejected_observation_count": sum(rejected.values()),
            "rejected_by_reason": rejected,
            "eligibility_reason_codes": list(EVIDENCE_REASON_CODES),
        },
        "statistical_anomaly": {
            "calibration_status": "NOT_CALIBRATED",
            "detected": False,
        },
        "markets": markets,
    }
    model_markets = {
        market: _model_lab_market(markets[market], market=market, simulation=simulation)
        for market in SUPPORTED_MARKETS
    }
    model_lab = {
        "schema_version": "w2.model-lab.v1",
        "authority": "DIAGNOSTIC_ONLY",
        "fixture_id": fixture_id,
        "competition_id": competition_id,
        "diagnostic_semantics": {
            "market_range": "OBSERVED_REFERENCE_ENVELOPE",
            "outside_range": "INVESTIGATE_MODEL_DATA_CALIBRATION_AND_MARKET_IDENTITY",
            "action_authority": "NONE",
        },
        "historical_validation": dict(PHASE_0_5_FROZEN_CONTEXT),
        "markets": model_markets,
    }
    return {"market_radar": radar, "model_lab": model_lab}


def eligible_observations(
    observations: Sequence[Mapping[str, Any]],
    *,
    fixture_id: str,
    competition_id: str,
    kickoff_utc: datetime,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Apply the explicit real-evidence contract without silent coercion."""
    rejected: dict[str, int] = {}
    accepted: list[dict[str, Any]] = []
    signatures: dict[str, tuple[str, ...]] = {}
    conflicts: set[str] = set()
    for source in observations:
        row = dict(source)
        observation_id = _text(row.get("observation_id"))
        signature = tuple(
            _text(row.get(key))
            for key in (
                "fixture_id",
                "competition_id",
                "capture_id",
                "bookmaker_id",
                "canonical_market",
                "canonical_selection",
                "line",
                "decimal_odds",
                "captured_at",
                "raw_payload_sha256",
            )
        )
        if (
            observation_id
            and observation_id in signatures
            and signatures[observation_id] != signature
        ):
            conflicts.add(observation_id)
        elif observation_id:
            signatures[observation_id] = signature
        accepted.append(row)

    filtered: list[dict[str, Any]] = []
    for row in accepted:
        reason = _ineligibility_reason(
            row,
            fixture_id=fixture_id,
            competition_id=competition_id,
            kickoff_utc=kickoff_utc,
            conflicting_ids=conflicts,
        )
        if reason:
            rejected[reason] = rejected.get(reason, 0) + 1
        else:
            filtered.append(row)
    return filtered, dict(sorted(rejected.items()))


def _ineligibility_reason(
    row: Mapping[str, Any],
    *,
    fixture_id: str,
    competition_id: str,
    kickoff_utc: datetime,
    conflicting_ids: set[str],
) -> str | None:
    source_markers = " ".join(
        _text(row.get(key)).lower() for key in ("provider", "source_revision", "raw_storage_uri")
    )
    if row.get("synthetic") is True or any(
        marker in source_markers for marker in ("synthetic", "fixture://", "test-only")
    ):
        return "SYNTHETIC_EVIDENCE"
    if not row.get("raw_lineage_present") or not _text(row.get("raw_payload_sha256")):
        return "RAW_PAYLOAD_MISSING"
    if not row.get("capture_lineage_present") or not _text(row.get("capture_id")):
        return "ENDPOINT_CAPTURE_MISSING"
    if not row.get("fixture_identity_present"):
        return "FIXTURE_IDENTITY_MISSING"
    if row.get("runtime_whitelist_member") is not True:
        return "OUT_OF_RUNTIME_WHITELIST"
    market = _text(row.get("canonical_market")).upper()
    if market not in SUPPORTED_MARKETS:
        return "UNSUPPORTED_MARKET"
    if _decimal(row.get("line")) is None:
        return "INVALID_LINE"
    price = _decimal(row.get("decimal_odds"))
    if price is None or price <= 1:
        return "INVALID_PRICE"
    if (
        _text(row.get("fixture_id")) != fixture_id
        or _text(row.get("competition_id")) != competition_id
        or row.get("identity_conflict") is True
        or row.get("capture_identity_conflict") is True
    ):
        return "IDENTITY_CONFLICT"
    if _text(row.get("observation_id")) in conflicting_ids:
        return "DUPLICATE_CONFLICTING_OBSERVATION"
    if row.get("live") is True or row.get("suspended") is True:
        return "LIVE_OR_SUSPENDED"
    captured_at = _datetime(row.get("captured_at"))
    if captured_at is None or captured_at >= kickoff_utc:
        return "POST_KICKOFF_OBSERVATION"
    return None


def _market_radar(
    observations: Sequence[dict[str, Any]],
    *,
    market: str,
    fixture_id: str,
    kickoff_utc: datetime,
    as_of: datetime,
    freshness_seconds: int,
) -> dict[str, Any]:
    scoped = [row for row in observations if _text(row.get("canonical_market")).upper() == market]
    captures: dict[tuple[str, datetime], list[dict[str, Any]]] = {}
    for row in scoped:
        captured_at = _datetime(row.get("captured_at"))
        if captured_at is not None:
            captures.setdefault((_text(row.get("capture_id")), captured_at), []).append(row)
    snapshots = [
        snapshot
        for capture_key, rows in sorted(captures.items(), key=lambda item: item[0][1])
        if (
            snapshot := _snapshot(
                rows,
                market=market,
                fixture_id=fixture_id,
                kickoff_utc=kickoff_utc,
                captured_at=capture_key[1],
                capture_id=capture_key[0],
                as_of=as_of,
                freshness_seconds=freshness_seconds,
            )
        )
        is not None
    ]
    history = [
        _movement(previous, current)
        for previous, current in zip(snapshots, snapshots[1:], strict=False)
    ]
    current = snapshots[-1] if snapshots else None
    timeline_status = (
        "INSUFFICIENT_NO_TIMELINE_EVIDENCE"
        if not snapshots
        else "INSUFFICIENT_SINGLE_SNAPSHOT"
        if len(snapshots) == 1
        else "MOVEMENT_COMPARISON_ELIGIBLE"
    )
    line_counts: dict[str, int] = {}
    for snapshot in snapshots:
        line = _text(snapshot.get("canonical_line"))
        line_counts[line] = line_counts.get(line, 0) + 1
    latest_movement = history[-1] if history else _insufficient_movement(timeline_status)
    return {
        "status": "READY" if current else "INSUFFICIENT",
        "market": market,
        "current": current,
        "snapshot_count": len(snapshots),
        "observation_count": sum(int(item["observation_count"]) for item in snapshots),
        "timeline": {
            "status": timeline_status,
            "valid_snapshot_count": len(snapshots),
            "distinct_captured_at_count": len({str(item["captured_at"]) for item in snapshots}),
            "earliest_captured_at": snapshots[0]["captured_at"] if snapshots else None,
            "latest_captured_at": snapshots[-1]["captured_at"] if snapshots else None,
            "same_line_comparable_snapshot_count": max(line_counts.values(), default=0),
            "raw_payload_lineage_complete": bool(snapshots),
            "endpoint_capture_lineage_complete": bool(snapshots),
            "points": [
                {
                    "capture_id": item["capture_id"],
                    "captured_at": item["captured_at"],
                    "canonical_line": item["canonical_line"],
                    "bookmaker_count": item["bookmaker_count"],
                    "prices": item["prices"],
                    "probabilities": item["probabilities"],
                }
                for item in snapshots
            ],
        },
        "movement": latest_movement,
        "movement_history": history,
    }


def _snapshot(
    rows: list[dict[str, Any]],
    *,
    market: str,
    fixture_id: str,
    kickoff_utc: datetime,
    captured_at: datetime,
    capture_id: str,
    as_of: datetime,
    freshness_seconds: int,
) -> dict[str, Any] | None:
    canonical = (
        select_canonical_ah_mainline(
            rows,
            fixture_id=fixture_id,
            target=captured_at,
            kickoff=kickoff_utc,
        )
        if market == "ASIAN_HANDICAP"
        else select_canonical_totals_mainline(
            rows,
            fixture_id=fixture_id,
            target=captured_at,
            kickoff=kickoff_utc,
        )
    )
    if canonical.status != "READY" or canonical.line is None:
        return None
    pairs = _bookmaker_pairs(rows, market=market, line=canonical.line)
    if not pairs:
        return None
    sides = _SIDES[market]
    distributions = {side: [float(pair["probabilities"][side]) for pair in pairs] for side in sides}
    prices = {side: [float(pair["prices"][side]) for pair in pairs] for side in sides}
    overrounds = [float(pair["overround"]) for pair in pairs]
    age_seconds = max(0, int((as_of - captured_at).total_seconds()))
    freshness_status = "COMPLETE" if age_seconds <= freshness_seconds else "STALE"
    return {
        "capture_id": capture_id,
        "captured_at": _iso(captured_at),
        "canonical_line": _format_decimal(canonical.line),
        "freshness": {
            "status": freshness_status,
            "age_seconds": age_seconds,
            "max_age_seconds": freshness_seconds,
        },
        "bookmaker_count": len(pairs),
        "bookmakers": pairs,
        "prices": {
            side: {
                "median": _rounded(median(values)),
                "min": _rounded(min(values)),
                "max": _rounded(max(values)),
            }
            for side, values in prices.items()
        },
        "probabilities": {
            side: {
                "median": _rounded(median(values)),
                "min": _rounded(min(values)),
                "max": _rounded(max(values)),
            }
            for side, values in distributions.items()
        },
        "overround": {
            "median": _rounded(median(overrounds)),
            "min": _rounded(min(overrounds)),
            "max": _rounded(max(overrounds)),
            "percentiles_status": "AVAILABLE" if len(overrounds) >= 4 else "INSUFFICIENT",
            "p25": _rounded(_percentile(overrounds, 0.25)) if len(overrounds) >= 4 else None,
            "p75": _rounded(_percentile(overrounds, 0.75)) if len(overrounds) >= 4 else None,
        },
        "observation_count": len(pairs) * 2,
        "lineage": {
            "capture_ids": [capture_id],
            "observation_ids": sorted(
                observation_id for pair in pairs for observation_id in pair["observation_ids"]
            ),
            "raw_payload_sha256": sorted(
                {payload_id for pair in pairs for payload_id in pair["raw_payload_sha256"]}
            ),
            "fixture_identity": fixture_id,
        },
    }


def _bookmaker_pairs(
    rows: Sequence[dict[str, Any]], *, market: str, line: Decimal
) -> list[dict[str, Any]]:
    sides = _SIDES[market]
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for row in rows:
        side = _text(row.get("canonical_selection")).upper()
        row_line = _decimal(row.get("line"))
        bookmaker = _text(row.get("bookmaker_id"))
        if side not in sides or row_line is None or not bookmaker:
            continue
        line_matches = (
            row_line == line if market == "TOTALS" or side == "HOME" else row_line in {line, -line}
        )
        if line_matches:
            grouped.setdefault(bookmaker, {}).setdefault(side, []).append(row)
    pairs: list[dict[str, Any]] = []
    for bookmaker, by_side in sorted(grouped.items()):
        if any(len(by_side.get(side, [])) != 1 for side in sides):
            continue
        selected = {side: by_side[side][0] for side in sides}
        odds = {side: Decimal(_text(selected[side]["decimal_odds"])) for side in sides}
        result = devig(odds, DevigMethod.PROPORTIONAL)
        pairs.append(
            {
                "bookmaker_id": bookmaker,
                "bookmaker_name": _text(selected[sides[0]].get("bookmaker_name"), bookmaker),
                "prices": {side: float(odds[side]) for side in sides},
                "probabilities": {side: _rounded(result.probabilities[side]) for side in sides},
                "overround": _rounded(result.overround),
                "observation_ids": sorted(
                    _text(selected[side].get("observation_id")) for side in sides
                ),
                "raw_payload_sha256": sorted(
                    {_text(selected[side].get("raw_payload_sha256")) for side in sides}
                ),
            }
        )
    return pairs


def _movement(previous: Mapping[str, Any], current: Mapping[str, Any]) -> dict[str, Any]:
    previous_line = _decimal(previous.get("canonical_line"))
    current_line = _decimal(current.get("canonical_line"))
    line_delta = (
        current_line - previous_line
        if current_line is not None and previous_line is not None
        else Decimal("0")
    )
    market = "ASIAN_HANDICAP" if "HOME" in _mapping(current.get("prices")) else "TOTALS"
    sides = _SIDES[market]
    price_delta = {side: _delta(previous, current, "prices", side) for side in sides}
    probability_delta = {side: _delta(previous, current, "probabilities", side) for side in sides}
    price_changed = any(value != 0 for value in price_delta.values())
    line_changed = line_delta != 0
    status = (
        "LINE_AND_PRICE_MOVEMENT"
        if line_changed and price_changed
        else "LINE_MOVEMENT"
        if line_changed
        else "PRICE_MOVEMENT"
        if price_changed
        else "STABLE"
    )
    return {
        "status": status,
        "from_captured_at": previous.get("captured_at"),
        "to_captured_at": current.get("captured_at"),
        "line_delta": _format_decimal(line_delta),
        "price_delta": price_delta,
        "probability_delta": probability_delta,
    }


def _model_lab_market(
    radar: Mapping[str, Any], *, market: str, simulation: Mapping[str, Any] | None
) -> dict[str, Any]:
    current = _mapping(radar.get("current"))
    freshness = _mapping(current.get("freshness"))
    bookmaker_count = int(current.get("bookmaker_count") or 0)
    if not current or freshness.get("status") != "COMPLETE":
        return _model_not_ready("MARKET_NOT_READY", market, bookmaker_count, simulation)
    if bookmaker_count < 3:
        return _model_not_ready("INSUFFICIENT_BOOKMAKER_DEPTH", market, bookmaker_count, simulation)
    model_blockers = _model_blockers(simulation)
    if model_blockers:
        return _model_not_ready(
            "MODEL_NOT_READY", market, bookmaker_count, simulation, blockers=model_blockers
        )
    assert simulation is not None
    matrix = score_matrix_from_simulation(dict(simulation))
    if not matrix:
        return _model_not_ready(
            "MODEL_NOT_READY",
            market,
            bookmaker_count,
            simulation,
            blockers=["MODEL_SCORE_MATRIX_UNAVAILABLE"],
        )
    line = _decimal(current.get("canonical_line"))
    if line is None:
        return _model_not_ready("MARKET_NOT_READY", market, bookmaker_count, simulation)
    diagnostics = []
    market_probabilities = _mapping(current.get("probabilities"))
    for side in _SIDES[market]:
        distribution = _settlement_distribution(matrix, market=market, selection=side, line=line)
        model_probability = effective_settlement_probability(distribution)
        market_side = _mapping(market_probabilities.get(side))
        market_median = _number(market_side.get("median"))
        market_min = _number(market_side.get("min"))
        market_max = _number(market_side.get("max"))
        if None in {model_probability, market_median, market_min, market_max}:
            return _model_not_ready("MARKET_NOT_READY", market, bookmaker_count, simulation)
        assert model_probability is not None
        assert market_median is not None and market_min is not None and market_max is not None
        outside_distance = (
            model_probability - market_max
            if model_probability > market_max
            else model_probability - market_min
            if model_probability < market_min
            else 0.0
        )
        diagnostics.append(
            {
                "selection": side,
                "market_probability_median": _rounded(market_median),
                "market_probability_min": _rounded(market_min),
                "market_probability_max": _rounded(market_max),
                "model_effective_settlement_probability": _rounded(model_probability),
                "model_minus_market_median": _rounded(model_probability - market_median),
                "distance_outside_market_range": _rounded(outside_distance),
                "settlement_distribution": distribution,
            }
        )
    status = (
        "MODEL_OUTSIDE_MARKET_RANGE"
        if any(item["distance_outside_market_range"] != 0 for item in diagnostics)
        else "COMPARABLE_WITHIN_MARKET_RANGE"
    )
    return {
        "status": status,
        "market": market,
        "canonical_line": current.get("canonical_line"),
        "quote_identity_status": "COMPLETE",
        "freshness_status": "COMPLETE",
        "bookmaker_count": bookmaker_count,
        "model_version": simulation.get("model_version"),
        "calibration_version": simulation.get("calibration_version"),
        "calibration_status": simulation.get("calibration_status"),
        "diagnostics": diagnostics,
        "blockers": [],
    }


def _model_not_ready(
    status: str,
    market: str,
    bookmaker_count: int,
    simulation: Mapping[str, Any] | None,
    *,
    blockers: list[str] | None = None,
) -> dict[str, Any]:
    source = simulation or {}
    return {
        "status": status,
        "market": market,
        "canonical_line": None,
        "quote_identity_status": "INCOMPLETE" if status == "MARKET_NOT_READY" else "COMPLETE",
        "freshness_status": "INCOMPLETE" if status == "MARKET_NOT_READY" else "COMPLETE",
        "bookmaker_count": bookmaker_count,
        "model_version": source.get("model_version"),
        "calibration_version": source.get("calibration_version"),
        "calibration_status": source.get("calibration_status"),
        "diagnostics": [],
        "blockers": blockers or [status],
    }


def _model_blockers(simulation: Mapping[str, Any] | None) -> list[str]:
    if not simulation or simulation.get("status") != "READY":
        return ["MODEL_SIMULATION_NOT_READY"]
    blockers = []
    if not _text(simulation.get("model_version")):
        blockers.append("MODEL_VERSION_MISSING")
    if not _text(simulation.get("calibration_version")):
        blockers.append("MODEL_CALIBRATION_VERSION_MISSING")
    if _text(simulation.get("calibration_status")).upper() not in {
        "READY",
        "PRODUCTION_VALIDATED",
        "APPROVED_VALIDATED",
    }:
        blockers.append("MODEL_CALIBRATION_NOT_READY")
    return blockers


def _settlement_distribution(
    matrix: Mapping[tuple[int, int], float],
    *,
    market: str,
    selection: str,
    line: Decimal,
) -> dict[str, float]:
    totals = {outcome.value: Decimal("0") for outcome in SettlementOutcome}
    for (home, away), probability in matrix.items():
        outcome = (
            settle_asian_handicap(home, away, selection, line)
            if market == "ASIAN_HANDICAP"
            else settle_total_goals(home + away, selection, line)
        )
        totals[outcome.value] += Decimal(str(probability))
    total = sum(totals.values(), Decimal("0"))
    return {
        outcome: float((value / total).quantize(Decimal("0.000001")))
        for outcome, value in totals.items()
    }


def _insufficient_movement(reason_code: str) -> dict[str, Any]:
    return {
        "status": "INSUFFICIENT",
        "reason_code": reason_code,
        "from_captured_at": None,
        "to_captured_at": None,
        "line_delta": None,
        "price_delta": None,
        "probability_delta": None,
    }


def _delta(previous: Mapping[str, Any], current: Mapping[str, Any], group: str, side: str) -> float:
    before = _number(_mapping(_mapping(previous.get(group)).get(side)).get("median")) or 0.0
    after = _number(_mapping(_mapping(current.get(group)).get(side)).get("median")) or 0.0
    return _rounded(after - before)


def _percentile(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _canonical_fixture_id(value: str) -> str:
    return value if value.startswith("api_football:") else f"api_football:{value}"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def _decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value)) if value is not None and str(value).strip() else None
    except (InvalidOperation, ValueError):
        return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return _utc(value)
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return _utc(parsed) if parsed.tzinfo is not None else None


def _utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _iso(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _format_decimal(value: Decimal) -> str:
    normalized = value.normalize()
    return (
        str(int(normalized)) if normalized == normalized.to_integral() else format(normalized, "f")
    )


def _rounded(value: float) -> float:
    return round(float(value), 6)
