from __future__ import annotations

import json
import math
import random
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Any

SAMPLE_TARGET = 200
SETTLED_OUTCOMES = {
    "HIT": "hit",
    "WIN": "hit",
    "HALF_WIN": "hit",
    "MISS": "miss",
    "LOSS": "miss",
    "HALF_LOSS": "miss",
    "PUSH": "push",
    "VOID": "void",
}


def forward_ledger_performance(
    runtime_root: Path,
    *,
    sample_target: int = SAMPLE_TARGET,
    now: datetime | None = None,
) -> dict[str, Any]:
    resolved_now = (now or datetime.now(UTC)).astimezone(UTC)
    root = runtime_root / "forward_outcome_ledger"
    records = list(load_forward_ledger_records(root))
    captures = [record for record in records if _record_type(record) == "capture"]
    candidates, excluded = _validation_candidates(captures)
    validation_rows, settlement_excluded = _validation_settlements(records, candidates)
    excluded.update(settlement_excluded)
    official_rows = _scoped_outcomes(records, "OFFICIAL")
    shadow_rows = _scoped_outcomes(records, "SHADOW")
    validation_counts = _counts_for_rows(validation_rows)
    official_counts = _counts_for_rows(official_rows)
    shadow_counts = _counts_for_rows(shadow_rows)
    canonical_rows, canonical_excluded = _canonical_rows(validation_rows, candidates, captures)
    calibration = _calibration_summary(canonical_rows, candidates)
    clv_rows = _clv_rows(records, key_fn=_clv_key)
    clv_shadow_rows = _clv_rows(records, key_fn=_clv_shadow_key)
    clv_values = _clv_values(clv_rows)
    clv_shadow_values = _clv_values(clv_shadow_rows)
    fixture_ids = {
        _text(record.get("fixture_id")) for record in records if _text(record.get("fixture_id"))
    }
    pending_status = _pending_status_summary(
        runtime_root,
        candidates=candidates,
        settled=validation_rows,
        now=resolved_now,
    )
    return {
        "schema_version": "w2.forward_ledger_performance.v2",
        "source": "runtime/forward_outcome_ledger",
        "sample_target": sample_target,
        "record_count": len(records),
        "fixture_count": len(fixture_ids),
        "validation_fixture_count": len(candidates),
        "validation_market_pick_count": _validation_market_pick_count(candidates),
        "validation_settled_fixture_count": len(validation_rows),
        "validation_pending_fixture_count": max(0, len(candidates) - len(validation_rows)),
        "validation_pending_status": pending_status,
        "outcomes_validation": _outcome_summary(validation_counts),
        "outcomes": _outcome_summary(official_counts),
        "outcomes_shadow": _outcome_summary(shadow_counts),
        "settled_sample_count": sum(official_counts.values()),
        "hit_count": official_counts["hit"],
        "miss_count": official_counts["miss"],
        "push_count": official_counts["push"],
        "void_count": official_counts["void"],
        "hit_rate": _hit_rate(official_counts),
        "canonical_settled_fixture_count": len(canonical_rows),
        "canonical_excluded_count": len(canonical_excluded),
        "canonical_excluded_by_reason": _reason_counts(canonical_excluded),
        "validation_excluded_count": len(excluded),
        "validation_excluded_by_reason": _reason_counts(excluded),
        "accumulation_label": _accumulation_label(len(canonical_rows), sample_target),
        "evidence_window": _evidence_window(records),
        "coverage": _coverage_summary(captures, candidates, validation_rows),
        "calibration": calibration,
        "clv": _clv_summary(
            clv_values,
            clv_rows,
            method="entry_minus_closing_decimal_odds_same_line",
        ),
        "clv_shadow": _clv_summary(
            clv_shadow_values,
            clv_shadow_rows,
            method="shadow_pick_entry_minus_closing_same_line; not_displayed_direction",
        ),
        "accrual_note": (
            "shadow CLV 为积累期证据流,用于未来按预注册规则放行 direction_allowed;非展示战绩"
        ),
        "by_league": _league_rows(
            records,
            clv_rows,
            clv_shadow_rows,
            outcome_counts_by_league(validation_rows, side="pick"),
            outcome_counts_by_league(shadow_rows, side="shadow_pick"),
        ),
        "by_league_market": _league_market_rows(candidates, validation_rows),
        "provider_calls": 0,
        "db_reads": 0,
        "db_writes": 0,
        "mock_data": False,
    }


def _validation_candidates(
    captures: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Mapping[str, Any]], dict[str, str]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for record in captures:
        if _capture_scope(record) != "VALIDATION":
            continue
        fixture_id = _text(record.get("fixture_id"))
        if fixture_id:
            grouped[fixture_id].append(record)
    candidates: dict[str, Mapping[str, Any]] = {}
    excluded: dict[str, str] = {}
    for fixture_id, items in grouped.items():
        ordered = sorted(
            items,
            key=lambda item: (
                _parse_time(item.get("captured_at")) or datetime.max.replace(tzinfo=UTC)
            ),
        )
        complete = [item for item in ordered if _validation_capture_issue(item) is None]
        if not complete:
            excluded[fixture_id] = _validation_capture_issue(ordered[0]) or "INCOMPLETE_CAPTURE"
            continue
        signatures = {_recommendation_signature(item) for item in complete}
        if None in signatures or len(signatures) != 1:
            excluded[fixture_id] = "RECOMMENDATION_IDENTITY_CONFLICT"
            continue
        fixture_signatures = {_fixture_signature(item) for item in complete}
        if None in fixture_signatures or len(fixture_signatures) != 1:
            excluded[fixture_id] = "FIXTURE_IDENTITY_CONFLICT"
            continue
        candidates[fixture_id] = complete[0]
    return candidates, excluded


def _validation_capture_issue(record: Mapping[str, Any]) -> str | None:
    identity = _fixture_identity(record)
    required = (
        "fixture_id",
        "kickoff_utc",
        "competition",
        "home_team_name",
        "away_team_name",
    )
    for key in required:
        if not _text(identity.get(key)):
            return f"MISSING_{key.upper()}"
    if not _text(record.get("captured_at")):
        return "MISSING_CAPTURED_AT"
    if not _text(record.get("card_hash")):
        return "MISSING_CARD_HASH"
    pick = record.get("pick")
    if not isinstance(pick, Mapping):
        return "MISSING_PICK"
    market = _text(pick.get("market"))
    selection = _text(pick.get("selection"))
    if market not in {"ASIAN_HANDICAP", "TOTALS"} or not selection:
        return "INVALID_PICK_IDENTITY"
    if _quote(record, market, selection) is None:
        return "MISSING_ENTRY_QUOTE"
    return None


def _capture_scope(record: Mapping[str, Any]) -> str:
    explicit = _text(record.get("recommendation_scope")).upper()
    if explicit in {"OFFICIAL", "VALIDATION", "SHADOW", "NONE"}:
        return explicit
    tier = _text(record.get("decision_tier")).upper()
    if tier == "RECOMMEND" and record.get("lock_eligible") is True:
        return "OFFICIAL"
    if tier == "ANALYSIS_PICK" and record.get("outcome_tracked") is True:
        return "VALIDATION"
    if isinstance(record.get("shadow_pick"), Mapping):
        return "SHADOW"
    return "NONE"


def _fixture_identity(record: Mapping[str, Any]) -> dict[str, Any]:
    nested = record.get("fixture_identity")
    identity = nested if isinstance(nested, Mapping) else record
    return {
        "fixture_id": identity.get("fixture_id") or record.get("fixture_id"),
        "kickoff_utc": identity.get("kickoff_utc") or record.get("kickoff_utc"),
        "competition": identity.get("competition_id")
        or identity.get("competition_name")
        or record.get("competition_id")
        or record.get("competition_name"),
        "home_team_name": identity.get("home_team_name") or record.get("home_team_name"),
        "away_team_name": identity.get("away_team_name") or record.get("away_team_name"),
    }


def _fixture_signature(record: Mapping[str, Any]) -> tuple[str, ...] | None:
    identity = _fixture_identity(record)
    values = tuple(
        _text(identity.get(key))
        for key in ("fixture_id", "kickoff_utc", "competition", "home_team_name", "away_team_name")
    )
    return values if all(values) else None


def _recommendation_signature(record: Mapping[str, Any]) -> tuple[str, str, str] | None:
    pick = record.get("pick")
    if not isinstance(pick, Mapping):
        return None
    market = _text(pick.get("market"))
    selection = _text(pick.get("selection"))
    quote = _quote(record, market, selection)
    if not market or not selection or quote is None:
        return None
    return (market, selection, quote[0])


def _validation_settlements(
    records: Sequence[Mapping[str, Any]],
    candidates: Mapping[str, Mapping[str, Any]],
) -> tuple[list[Mapping[str, Any]], dict[str, str]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        if _record_type(record) != "outcome" or _outcome_side(record) != "pick":
            continue
        fixture_id = _text(record.get("fixture_id"))
        candidate = candidates.get(fixture_id)
        if candidate is None:
            continue
        scope = _text(record.get("recommendation_scope")).upper()
        if scope not in {"", "UNSCOPED", "VALIDATION"}:
            continue
        signature = _recommendation_signature(candidate)
        if signature is None:
            continue
        if (_text(record.get("market")), _text(record.get("selection"))) != signature[:2]:
            continue
        grouped[fixture_id].append(record)
    settled: list[Mapping[str, Any]] = []
    excluded: dict[str, str] = {}
    for fixture_id, items in grouped.items():
        outcomes = {_outcome(item) for item in items if _outcome(item)}
        if len(outcomes) != 1:
            excluded[fixture_id] = "SETTLEMENT_CONFLICT"
            continue
        settled.append(sorted(items, key=lambda item: _text(item.get("settled_at")))[0])
    return settled, excluded


def _scoped_outcomes(records: Sequence[Mapping[str, Any]], scope: str) -> list[Mapping[str, Any]]:
    grouped: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        if _record_type(record) != "outcome":
            continue
        actual = _text(record.get("recommendation_scope")).upper()
        if scope == "SHADOW" and _outcome_side(record) == "shadow_pick":
            actual = "SHADOW"
        if actual != scope:
            continue
        grouped[
            (
                _text(record.get("fixture_id")),
                _text(record.get("market")),
                _text(record.get("selection")),
            )
        ].append(record)
    rows: list[Mapping[str, Any]] = []
    for items in grouped.values():
        outcomes = {_outcome(item) for item in items if _outcome(item)}
        if len(outcomes) == 1:
            rows.append(sorted(items, key=lambda item: _text(item.get("settled_at")))[0])
    return rows


def _counts_for_rows(rows: Sequence[Mapping[str, Any]]) -> defaultdict[str, int]:
    counts: defaultdict[str, int] = defaultdict(int)
    for row in rows:
        bucket = SETTLED_OUTCOMES.get(_outcome(row))
        if bucket:
            counts[bucket] += 1
    return counts


def _canonical_rows(
    settled: Sequence[Mapping[str, Any]],
    candidates: Mapping[str, Mapping[str, Any]],
    captures: Sequence[Mapping[str, Any]],
) -> tuple[list[Mapping[str, Any]], dict[str, str]]:
    rows: list[Mapping[str, Any]] = []
    excluded: dict[str, str] = {}
    for outcome in settled:
        fixture_id = _text(outcome.get("fixture_id"))
        capture = candidates[fixture_id]
        related_captures = [
            item
            for item in captures
            if _text(item.get("fixture_id")) == fixture_id and _capture_scope(item) == "VALIDATION"
        ]
        reason = _canonical_issue(capture, outcome, related_captures)
        if reason:
            excluded[fixture_id] = reason
        else:
            rows.append(outcome)
    return rows, excluded


def _canonical_issue(
    capture: Mapping[str, Any],
    outcome: Mapping[str, Any],
    related_captures: Sequence[Mapping[str, Any]],
) -> str | None:
    schema = _text(capture.get("schema_version"))
    if schema == "w2.forward_outcome_ledger.v3":
        capture_hash = _text(capture.get("capture_identity_hash"))
        if not capture_hash or _text(outcome.get("capture_identity_hash")) != capture_hash:
            return "CAPTURE_OUTCOME_IDENTITY_MISMATCH"
        artifact = capture.get("artifact_provenance")
        if not isinstance(artifact, Mapping) or not _text(artifact.get("artifact_hash")):
            return "MISSING_ARTIFACT_IDENTITY"
        quote = capture.get("quote_provenance")
        if not isinstance(quote, Mapping) or not _complete_quote_provenance(quote):
            return "MISSING_QUOTE_PROVENANCE"
    elif schema in {
        "w2.forward_outcome_ledger.v1",
        "w2.forward_outcome_ledger.v2",
    }:
        legacy_issue = _legacy_capture_link_issue(capture, outcome, related_captures)
        if legacy_issue:
            return legacy_issue
    else:
        return "UNSUPPORTED_SCHEMA"
    score = outcome.get("final_score")
    if (
        not isinstance(score, Mapping)
        or _number(score.get("home")) is None
        or _number(score.get("away")) is None
    ):
        return "MISSING_SETTLED_SCORE"
    return None


def _legacy_capture_link_issue(
    capture: Mapping[str, Any],
    outcome: Mapping[str, Any],
    related_captures: Sequence[Mapping[str, Any]],
) -> str | None:
    source_hash = _text(outcome.get("source_capture_hash"))
    source_captured_at = _parse_time(outcome.get("source_captured_at"))
    matches = [
        item
        for item in related_captures
        if source_hash
        and source_hash
        in {
            _text(item.get("card_hash")),
            _text(item.get("evidence_hash")),
        }
        and source_captured_at is not None
        and source_captured_at == _parse_time(item.get("captured_at"))
    ]
    if not matches:
        return "LEGACY_CAPTURE_LINK_MISSING"
    if len(matches) != 1:
        return "LEGACY_CAPTURE_LINK_AMBIGUOUS"
    linked = matches[0]
    if _fixture_signature(linked) != _fixture_signature(capture):
        return "LEGACY_FIXTURE_IDENTITY_MISMATCH"
    if _recommendation_signature(linked) != _recommendation_signature(capture):
        return "LEGACY_RECOMMENDATION_IDENTITY_MISMATCH"
    if _fixture_signature(linked) is None or _recommendation_signature(linked) is None:
        return "LEGACY_IDENTITY_INCOMPLETE"
    return None


def _complete_quote_provenance(value: Mapping[str, Any]) -> bool:
    markets = value.get("markets")
    if not isinstance(markets, Mapping):
        return False
    for item in markets.values():
        if not isinstance(item, Mapping):
            continue
        if (
            _text(item.get("identity_status")).upper() == "COMPLETE"
            and _text(item.get("freshness_status")).upper() == "COMPLETE"
            and _text(item.get("captured_at"))
        ):
            return True
    return False


def _probability_vector(record: Mapping[str, Any], key: str) -> tuple[float, float, float] | None:
    identity = record.get("probability_identity")
    if not isinstance(identity, Mapping):
        return None
    raw_value = identity.get(key)
    if not isinstance(raw_value, Mapping):
        return None
    raw: Mapping[str, Any] = raw_value
    one_x_two = raw.get("one_x_two")
    if isinstance(one_x_two, Mapping):
        probabilities = one_x_two.get("probabilities")
        raw = probabilities if isinstance(probabilities, Mapping) else one_x_two
    values = tuple(_number(raw.get(name)) for name in ("HOME", "DRAW", "AWAY"))
    if any(value is None for value in values):
        return None
    vector = tuple(float(value) for value in values if value is not None)
    if len(vector) != 3 or any(value <= 0 or value >= 1 for value in vector):
        return None
    total = sum(vector)
    if abs(total - 1.0) > 0.02:
        return None
    return tuple(value / total for value in vector)  # type: ignore[return-value]


def _calibration_summary(
    rows: Sequence[Mapping[str, Any]], candidates: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    observations: list[tuple[tuple[float, float, float], int]] = []
    paired: list[tuple[float, float]] = []
    roi_units: list[float] = []
    for outcome in rows:
        capture = candidates[_text(outcome.get("fixture_id"))]
        market = _probability_vector(capture, "market_probabilities")
        score = outcome.get("final_score")
        if market is None or not isinstance(score, Mapping):
            continue
        home = int(float(score["home"]))
        away = int(float(score["away"]))
        actual = 0 if home > away else (1 if home == away else 2)
        observations.append((market, actual))
        model = _probability_vector(capture, "model_probabilities")
        if model is not None:
            paired.append((_log_loss(model, actual), _log_loss(market, actual)))
        roi = _roi_unit(outcome)
        if roi is not None:
            roi_units.append(roi)
    if not observations:
        return {
            "sample_count": 0,
            "log_loss": None,
            "multiclass_brier": None,
            "rps": None,
            "ece": None,
            "research_roi": None,
            "paired_bootstrap": {"status": "INSUFFICIENT", "sample_count": 0},
        }
    return {
        "sample_count": len(observations),
        "log_loss": sum(_log_loss(prob, actual) for prob, actual in observations)
        / len(observations),
        "multiclass_brier": sum(_brier(prob, actual) for prob, actual in observations)
        / len(observations),
        "rps": sum(_rps(prob, actual) for prob, actual in observations) / len(observations),
        "ece": _ece(observations),
        "research_roi": round(sum(roi_units) / len(roi_units), 12) if roi_units else None,
        "paired_bootstrap": _paired_bootstrap(paired),
    }


def _log_loss(probabilities: tuple[float, float, float], actual: int) -> float:
    return -math.log(max(probabilities[actual], 1e-15))


def _brier(probabilities: tuple[float, float, float], actual: int) -> float:
    return sum(
        (value - (1.0 if index == actual else 0.0)) ** 2
        for index, value in enumerate(probabilities)
    )


def _rps(probabilities: tuple[float, float, float], actual: int) -> float:
    observed = (1.0 if actual == 0 else 0.0, 1.0 if actual <= 1 else 0.0)
    forecast = (probabilities[0], probabilities[0] + probabilities[1])
    return sum((left - right) ** 2 for left, right in zip(forecast, observed, strict=True)) / 2


def _ece(observations: Sequence[tuple[tuple[float, float, float], int]]) -> float:
    buckets: dict[int, list[tuple[float, bool]]] = defaultdict(list)
    for probabilities, actual in observations:
        confidence = max(probabilities)
        predicted = probabilities.index(confidence)
        buckets[min(9, int(confidence * 10))].append((confidence, predicted == actual))
    total = len(observations)
    return sum(
        len(items)
        / total
        * abs(
            sum(conf for conf, _ in items) / len(items) - sum(hit for _, hit in items) / len(items)
        )
        for items in buckets.values()
    )


def _paired_bootstrap(pairs: Sequence[tuple[float, float]]) -> dict[str, Any]:
    if len(pairs) < 2:
        return {"status": "INSUFFICIENT", "sample_count": len(pairs)}
    rng = random.Random(7)  # noqa: S311 - deterministic evaluation, not security
    deltas: list[float] = []
    for _ in range(1000):
        sample = [pairs[rng.randrange(len(pairs))] for _ in pairs]
        deltas.append(sum(model - market for model, market in sample) / len(sample))
    deltas.sort()
    return {
        "status": "AVAILABLE",
        "sample_count": len(pairs),
        "metric": "model_minus_market_log_loss",
        "delta": sum(model - market for model, market in pairs) / len(pairs),
        "ci95": [deltas[24], deltas[974]],
        "iterations": 1000,
        "seed": 7,
    }


def _roi_unit(outcome: Mapping[str, Any]) -> float | None:
    price = _number(outcome.get("entry_price"))
    result = _outcome(outcome)
    if price is None:
        return None
    if result in {"WIN", "HIT"}:
        return price - 1
    if result == "HALF_WIN":
        return (price - 1) / 2
    if result in {"LOSS", "MISS"}:
        return -1.0
    if result == "HALF_LOSS":
        return -0.5
    if result in {"PUSH", "VOID"}:
        return 0.0
    return None


def _reason_counts(excluded: Mapping[str, str]) -> dict[str, int]:
    counts: defaultdict[str, int] = defaultdict(int)
    for reason in excluded.values():
        counts[reason] += 1
    return dict(sorted(counts.items()))


def _evidence_window(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    captures = sorted(
        _text(record.get("captured_at")) for record in records if _text(record.get("captured_at"))
    )
    outcomes = sorted(
        _text(record.get("settled_at")) for record in records if _text(record.get("settled_at"))
    )
    return {
        "first_capture_at": captures[0] if captures else None,
        "latest_capture_at": captures[-1] if captures else None,
        "latest_outcome_at": outcomes[-1] if outcomes else None,
    }


def _coverage_summary(
    captures: Sequence[Mapping[str, Any]],
    candidates: Mapping[str, Mapping[str, Any]],
    settled: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    fixture_ids = {
        _text(record.get("fixture_id")) for record in captures if _text(record.get("fixture_id"))
    }
    stale = {
        _text(record.get("fixture_id"))
        for record in captures
        if _text(record.get("data_status")).upper() == "STALE"
    }
    return {
        "captured_fixture_count": len(fixture_ids),
        "validation_coverage": len(candidates) / len(fixture_ids) if fixture_ids else 0.0,
        "settlement_coverage": len(settled) / len(candidates) if candidates else 0.0,
        "stale_fixture_count": len(stale),
        "stale_rate": len(stale) / len(fixture_ids) if fixture_ids else 0.0,
    }


def _league_market_rows(
    candidates: Mapping[str, Mapping[str, Any]], settled: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    settled_ids = {_text(item.get("fixture_id")) for item in settled}
    grouped: dict[tuple[str, str], list[str]] = defaultdict(list)
    for fixture_id, record in candidates.items():
        pick = record.get("pick")
        market = _text(pick.get("market")) if isinstance(pick, Mapping) else "UNKNOWN"
        grouped[(_league_key(record), market)].append(fixture_id)
    return [
        {
            "league": league,
            "market": market,
            "validation_fixture_count": len(ids),
            "validation_settled_fixture_count": len(set(ids) & settled_ids),
        }
        for (league, market), ids in sorted(grouped.items())
    ]


def _validation_market_pick_count(
    candidates: Mapping[str, Mapping[str, Any]],
) -> int:
    count = 0
    for record in candidates.values():
        if isinstance(record.get("pick"), Mapping):
            count += 1
        secondary = record.get("secondary_picks")
        if isinstance(secondary, Sequence) and not isinstance(secondary, str | bytes | bytearray):
            count += min(1, sum(isinstance(item, Mapping) for item in secondary))
    return count


def _pending_status_summary(
    runtime_root: Path,
    *,
    candidates: Mapping[str, Mapping[str, Any]],
    settled: Sequence[Mapping[str, Any]],
    now: datetime,
) -> dict[str, Any]:
    settled_ids = {_text(row.get("fixture_id")) for row in settled}
    pending_ids = set(candidates) - settled_ids
    state_path = runtime_root / "forward_outcome_result_refresh_state.json"
    try:
        state_payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        state_payload = {}
    states = state_payload.get("fixtures") if isinstance(state_payload, Mapping) else {}
    if not isinstance(states, Mapping):
        states = {}
    counts = {
        "waiting_finish_count": 0,
        "postponed_count": 0,
        "result_missing_count": 0,
        "settlement_error_count": 0,
    }
    details: list[dict[str, Any]] = []
    for fixture_id in sorted(pending_ids):
        capture = candidates[fixture_id]
        kickoff = _parse_time(capture.get("kickoff_utc"))
        state = states.get(fixture_id)
        state = state if isinstance(state, Mapping) else {}
        provider_status = _text(state.get("status")).upper()
        if provider_status == "PST":
            category = "POSTPONED"
            counts["postponed_count"] += 1
        elif kickoff is not None and now < kickoff + timedelta(hours=3):
            category = "WAITING_FINISH"
            counts["waiting_finish_count"] += 1
        elif provider_status == "RESULT_MISSING":
            category = "RESULT_MISSING"
            counts["result_missing_count"] += 1
        else:
            category = "SETTLEMENT_BACKLOG"
            counts["settlement_error_count"] += 1
        details.append(
            {
                "fixture_id": fixture_id,
                "category": category,
                "last_checked_at_utc": state.get("checked_at_utc"),
                "next_check_at_utc": state.get("next_check_at_utc"),
            }
        )
    return {**counts, "details": details}


def load_forward_ledger_records(root: Path) -> Iterable[dict[str, Any]]:
    if not root.exists():
        return []
    records: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.jsonl")):
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    records.append(payload)
    return records


def _outcome_counts(
    records: Sequence[Mapping[str, Any]],
    *,
    side: str,
) -> defaultdict[str, int]:
    counts: defaultdict[str, int] = defaultdict(int)
    for record in records:
        if _outcome_side(record) != side:
            continue
        bucket = SETTLED_OUTCOMES.get(_outcome(record))
        if bucket:
            counts[bucket] += 1
    return counts


def outcome_counts_by_league(
    records: Sequence[Mapping[str, Any]],
    *,
    side: str = "pick",
) -> dict[str, defaultdict[str, int]]:
    by_league: dict[str, defaultdict[str, int]] = defaultdict(lambda: defaultdict(int))
    for record in records:
        if _outcome_side(record) != side:
            continue
        bucket = SETTLED_OUTCOMES.get(_outcome(record))
        if bucket:
            by_league[_league_key(record)][bucket] += 1
    return by_league


def _outcome_summary(counts: Mapping[str, int]) -> dict[str, Any]:
    return {
        "settled_sample_count": sum(counts.values()),
        "hit_count": int(counts.get("hit", 0)),
        "miss_count": int(counts.get("miss", 0)),
        "push_count": int(counts.get("push", 0)),
        "void_count": int(counts.get("void", 0)),
        "hit_rate": _hit_rate(counts),
    }


def _clv_values(rows: Sequence[Mapping[str, Any]]) -> list[float]:
    return [
        float(row["clv_decimal"]) for row in rows if isinstance(row.get("clv_decimal"), int | float)
    ]


def _clv_summary(
    values: Sequence[float],
    rows: Sequence[Mapping[str, Any]],
    *,
    method: str,
) -> dict[str, Any]:
    return {
        "sample_count": len(values),
        "median_decimal": median(values) if values else None,
        "positive_count": len([value for value in values if value > 0]),
        "negative_count": len([value for value in values if value < 0]),
        "push_count": len([value for value in values if value == 0]),
        "line_changed_count": len([row for row in rows if row.get("line_changed") is True]),
        "method": method,
    }


def _clv_rows(
    records: Sequence[Mapping[str, Any]],
    *,
    key_fn: Any,
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        key = key_fn(record)
        if key is not None:
            grouped[key].append(record)

    rows: list[dict[str, Any]] = []
    for (fixture_id, market, selection), items in grouped.items():
        ordered = sorted(
            items,
            key=lambda item: (
                _parse_time(item.get("captured_at")) or datetime.min.replace(tzinfo=UTC)
            ),
        )
        if len(ordered) < 2:
            continue
        entry = _entry_record(ordered)
        closing = _closing_record(ordered)
        entry_quote = _quote(entry, market, selection)
        closing_quote = _quote(closing, market, selection)
        if entry_quote is None or closing_quote is None:
            continue
        entry_line, entry_price = entry_quote
        closing_line, closing_price = closing_quote
        line_changed = entry_line != closing_line
        rows.append(
            {
                "fixture_id": fixture_id,
                "league": _league_key(entry),
                "market": market,
                "selection": selection,
                "entry_captured_at": _text(entry.get("captured_at")),
                "closing_captured_at": _text(closing.get("captured_at")),
                "line_changed": line_changed,
                "clv_decimal": None if line_changed else round(entry_price - closing_price, 6),
            }
        )
    return rows


def _entry_record(records: list[Mapping[str, Any]]) -> Mapping[str, Any]:
    for record in records:
        kickoff = _parse_time(record.get("kickoff_utc"))
        captured = _parse_time(record.get("captured_at"))
        if kickoff and captured and (kickoff - captured).total_seconds() >= 23 * 3600:
            return record
    return records[0]


def _closing_record(records: list[Mapping[str, Any]]) -> Mapping[str, Any]:
    before_kickoff = [
        record
        for record in records
        if (kickoff := _parse_time(record.get("kickoff_utc")))
        and (captured := _parse_time(record.get("captured_at")))
        and captured <= kickoff
    ]
    return before_kickoff[-1] if before_kickoff else records[-1]


def _clv_key(record: Mapping[str, Any]) -> tuple[str, str, str] | None:
    if _record_type(record) != "capture":
        return None
    fixture_id = _text(record.get("fixture_id"))
    pick = record.get("pick")
    if not fixture_id or not isinstance(pick, Mapping):
        return None
    market = _text(pick.get("market"))
    selection = _text(pick.get("selection"))
    if market not in {"ASIAN_HANDICAP", "TOTALS"} or not selection:
        return None
    return (fixture_id, market, selection)


def _clv_shadow_key(record: Mapping[str, Any]) -> tuple[str, str, str] | None:
    if _record_type(record) != "capture":
        return None
    fixture_id = _text(record.get("fixture_id"))
    shadow_pick = record.get("shadow_pick")
    if not fixture_id or not isinstance(shadow_pick, Mapping):
        return None
    market = _text(shadow_pick.get("market"))
    selection = _text(shadow_pick.get("selection"))
    if market not in {"ASIAN_HANDICAP"} or not selection:
        return None
    return (fixture_id, market, selection)


def _quote(record: Mapping[str, Any], market: str, selection: str) -> tuple[str, float] | None:
    odds = record.get("current_odds")
    if not isinstance(odds, Mapping):
        return None
    if market == "ASIAN_HANDICAP":
        ah = odds.get("ah")
        if not isinstance(ah, Mapping):
            return None
        if selection == "HOME_AH":
            return _line_price(ah.get("home_line"), ah.get("home_price"))
        if selection == "AWAY_AH":
            return _line_price(ah.get("away_line"), ah.get("away_price"))
    if market == "TOTALS":
        ou = odds.get("ou")
        if not isinstance(ou, Mapping):
            return None
        if selection == "OVER":
            return _line_price(ou.get("line"), ou.get("over_price"))
        if selection == "UNDER":
            return _line_price(ou.get("line"), ou.get("under_price"))
    return None


def _line_price(line: Any, price: Any) -> tuple[str, float] | None:
    value = _number(price)
    if value is None:
        return None
    return (_text(line), value)


def _league_rows(
    records: Sequence[Mapping[str, Any]],
    clv_rows: Sequence[Mapping[str, Any]],
    clv_shadow_rows: Sequence[Mapping[str, Any]],
    league_outcomes: dict[str, defaultdict[str, int]],
    league_shadow_outcomes: dict[str, defaultdict[str, int]],
) -> list[dict[str, Any]]:
    league_records: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        league_records[_league_key(record)].append(record)
    clv_by_league: dict[str, list[float]] = defaultdict(list)
    for row in clv_rows:
        value = row.get("clv_decimal")
        if isinstance(value, int | float):
            clv_by_league[_text(row.get("league"))].append(value)
    clv_shadow_by_league: dict[str, list[float]] = defaultdict(list)
    for row in clv_shadow_rows:
        value = row.get("clv_decimal")
        if isinstance(value, int | float):
            clv_shadow_by_league[_text(row.get("league"))].append(value)
    rows: list[dict[str, Any]] = []
    for league, items in league_records.items():
        outcomes = league_outcomes.get(league, defaultdict(int))
        shadow_outcomes = league_shadow_outcomes.get(league, defaultdict(int))
        values = clv_by_league.get(league, [])
        shadow_values = clv_shadow_by_league.get(league, [])
        fixture_ids = {
            _text(item.get("fixture_id")) for item in items if _text(item.get("fixture_id"))
        }
        rows.append(
            {
                "league": league,
                "record_count": len(items),
                "fixture_count": len(fixture_ids),
                "settled_sample_count": sum(outcomes.values()),
                "hit_count": outcomes["hit"],
                "miss_count": outcomes["miss"],
                "push_count": outcomes["push"],
                "void_count": outcomes["void"],
                "hit_rate": _hit_rate(outcomes),
                "shadow_settled_sample_count": sum(shadow_outcomes.values()),
                "shadow_hit_count": shadow_outcomes["hit"],
                "shadow_miss_count": shadow_outcomes["miss"],
                "shadow_push_count": shadow_outcomes["push"],
                "shadow_void_count": shadow_outcomes["void"],
                "shadow_hit_rate": _hit_rate(shadow_outcomes),
                "clv_sample_count": len(values),
                "clv_median_decimal": median(values) if values else None,
                "clv_shadow_sample_count": len(shadow_values),
                "clv_shadow_median_decimal": median(shadow_values) if shadow_values else None,
            }
        )
    return sorted(rows, key=lambda row: (-int(row["record_count"]), str(row["league"])))


def _league_key(record: Mapping[str, Any]) -> str:
    return _text(record.get("competition_name")) or _text(record.get("competition_id")) or "UNKNOWN"


def _outcome(record: Mapping[str, Any]) -> str:
    for key in ("settlement_outcome", "outcome", "result_outcome"):
        value = _text(record.get(key)).upper()
        if value:
            return value
    validation = record.get("validation")
    if isinstance(validation, Mapping):
        return _text(validation.get("settlement")).upper()
    settlement = record.get("settlement")
    if isinstance(settlement, Mapping):
        return _text(settlement.get("outcome") or settlement.get("settlement")).upper()
    return ""


def _outcome_side(record: Mapping[str, Any]) -> str:
    side = _text(record.get("settled_side"))
    if side in {"pick", "shadow_pick"}:
        return side
    if _outcome(record):
        return "pick"
    return ""


def _record_type(record: Mapping[str, Any]) -> str:
    return _text(record.get("record_type") or "capture")


def _hit_rate(counts: Mapping[str, int]) -> float | None:
    denominator = int(counts.get("hit", 0)) + int(counts.get("miss", 0))
    if not denominator:
        return None
    return int(counts.get("hit", 0)) / denominator


def _accumulation_label(record_count: int, sample_target: int) -> str:
    if record_count < sample_target:
        return f"积累中 {record_count}/{sample_target}"
    return f"已达样本底线 {record_count}/{sample_target}"


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _number(value: Any) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
