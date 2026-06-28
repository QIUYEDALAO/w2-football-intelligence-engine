from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from w2.backtest.s2_gate import S2_MIN_COVERED_SETTLED_SAMPLE
from w2.calibration.handicap import HandicapCalibrationInput, build_handicap_calibration
from w2.markets.devig import DevigMethod, devig
from w2.settlement.settle import LockedPrediction, MatchResult, settle_prediction, stable_hash

REPORT_SCHEMA_VERSION = "w2.handicap_walkforward_report.v1"
REPORT_DATASET_VERSION = "w2.handicap_walkforward.dataset.v1"

EXCLUSION_MISSING_AS_OF = "MISSING_AS_OF"
EXCLUSION_POST_KICKOFF_ODDS = "POST_KICKOFF_ODDS"
EXCLUSION_MISSING_MARKET_LINE = "MISSING_MARKET_LINE"
EXCLUSION_MISSING_DEVIG_ODDS = "MISSING_DEVIG_ODDS"
EXCLUSION_MISSING_FAIR_AH = "MISSING_FAIR_AH"
EXCLUSION_MISSING_RESULT = "MISSING_RESULT"
EXCLUSION_VOID_SETTLEMENT = "VOID_SETTLEMENT"
EXCLUSION_DEMO_DATA = "DEMO_DATA"
EXCLUSION_NON_AUTHORITATIVE = "NON_AUTHORITATIVE_SOURCE"


@dataclass(frozen=True, kw_only=True)
class WalkForwardInputs:
    mode: str
    rows: list[dict[str, Any]]
    data_source: str
    date_from: date | None = None
    date_to: date | None = None
    min_samples: int = S2_MIN_COVERED_SETTLED_SAMPLE
    include_rows: bool = True
    generated_at: datetime | None = None


def build_handicap_walkforward_report(inputs: WalkForwardInputs) -> dict[str, Any]:
    generated_at = (inputs.generated_at or datetime.now(UTC)).astimezone(UTC)
    source_is_demo = _is_demo_source(inputs.data_source)
    authoritative = inputs.mode == "real" and not source_is_demo and bool(inputs.rows)
    authoritative_reason = _authoritative_reason(
        mode=inputs.mode,
        source_is_demo=source_is_demo,
        has_rows=bool(inputs.rows),
    )
    normalized_rows = [
        _evaluate_row(
            raw,
            report_authoritative=authoritative,
            data_source=inputs.data_source,
            generated_at=generated_at,
        )
        for raw in _filter_date_range(inputs.rows, inputs.date_from, inputs.date_to)
    ]
    sample = _sample_summary(normalized_rows)
    included_rows = [row for row in normalized_rows if row["sample_included"] is True]
    metrics = _metrics(normalized_rows, included_rows)
    split_checks = _split_checks(included_rows, min_samples=inputs.min_samples)
    s2_gate = _s2_gate(
        sample_size=len(included_rows),
        split_checks=split_checks,
        min_samples=inputs.min_samples,
    )
    calibration = build_handicap_calibration(
        HandicapCalibrationInput(
            sample_size=len(included_rows),
            all_validation_checks_passed=all(
                bool(value.get("passed")) for value in split_checks.values()
            )
            and s2_gate["devig_market_advantage"],
            included_rows=included_rows,
            generated_at=generated_at,
            n_min=inputs.min_samples,
        )
    )
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": _iso(generated_at),
        "data_source": inputs.data_source,
        "authoritative": authoritative,
        "authoritative_reason": authoritative_reason,
        "dataset_version": REPORT_DATASET_VERSION,
        "sample": sample,
        "market_policy": {
            "as_of_required": True,
            "locked_market_snapshot_required": True,
            "devig_required": True,
            "no_post_kickoff_odds": True,
        },
        "settlement_policy": {
            "asian_handicap": True,
            "push_excluded_from_win_rate": True,
            "void_excluded_from_sample": True,
            "half_win_loss_supported": True,
        },
        "splits": split_checks,
        "metrics": metrics,
        "s2_gate": s2_gate,
        "calibration": calibration,
        "rows": normalized_rows if inputs.include_rows else [],
    }


def load_rows_from_source_root(source_root: Path | None) -> list[dict[str, Any]]:
    if source_root is None:
        return []
    paths: list[Path]
    if source_root.is_file():
        paths = [source_root]
    elif source_root.exists():
        paths = sorted(
            [
                *source_root.rglob("*walkforward*.json"),
                *source_root.rglob("*forward_shadow*.json"),
                *source_root.rglob("*dashboard*.json"),
            ]
        )
    else:
        return []
    rows: list[dict[str, Any]] = []
    for path in paths:
        if not path.is_file():
            continue
        rows.extend(_rows_from_json(path))
    return rows


def load_rows_from_read_model() -> list[dict[str, Any]]:
    try:
        from w2.api.repository import ReadModelRepository, ReadModelService
    except Exception:
        return []
    try:
        service = ReadModelService(repository=ReadModelRepository())
        payload = service.dashboard(window="all", include_debug=True)
    except Exception:
        return []
    cards = payload.get("all") if isinstance(payload, dict) else []
    if not isinstance(cards, list):
        return []
    return [card for card in cards if isinstance(card, dict)]


def dry_run_report(*, include_rows: bool = True) -> dict[str, Any]:
    return build_handicap_walkforward_report(
        WalkForwardInputs(
            mode="dry-run",
            rows=[],
            data_source="DRY_RUN_NO_ASOF_ARTIFACT",
            include_rows=include_rows,
        )
    )


def _rows_from_json(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("rows", "items", "all", "samples"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [payload]
    return []


def _filter_date_range(
    rows: list[dict[str, Any]],
    date_from: date | None,
    date_to: date | None,
) -> list[dict[str, Any]]:
    if date_from is None and date_to is None:
        return rows
    filtered: list[dict[str, Any]] = []
    for row in rows:
        kickoff = _parse_datetime(_first(row, "kickoff_utc", "kickoff_at"))
        if kickoff is None:
            filtered.append(row)
            continue
        kickoff_date = kickoff.date()
        if date_from is not None and kickoff_date < date_from:
            continue
        if date_to is not None and kickoff_date > date_to:
            continue
        filtered.append(row)
    return filtered


def _evaluate_row(
    raw: dict[str, Any],
    *,
    report_authoritative: bool,
    data_source: str,
    generated_at: datetime,
) -> dict[str, Any]:
    fixture_id = str(_first(raw, "fixture_id", "id") or "")
    kickoff = _parse_datetime(_first(raw, "kickoff_utc", "kickoff_at"))
    as_of = _parse_datetime(_first(raw, "as_of", "locked_at", "captured_at"))
    market = _market_fields(raw)
    result = _result_fields(raw)
    row_source = str(raw.get("data_source") or data_source)
    pricing = raw.get("pricing_shadow") if isinstance(raw.get("pricing_shadow"), dict) else {}
    row = {
        "fixture_id": fixture_id,
        "kickoff_utc": _iso(kickoff) if kickoff else None,
        "as_of": _iso(as_of) if as_of else None,
        "home_team": _first(raw, "home_team", "home_team_name"),
        "away_team": _first(raw, "away_team", "away_team_name"),
        "model_version": _first(pricing, "model_version") or raw.get("model_version"),
        "calibration_version": "UNVALIDATED",
        "pricing_shadow_status": _first(pricing, "status") or raw.get("pricing_shadow_status"),
        "fair_ah": _float_or_none(_first(pricing, "fair_ah") if pricing else raw.get("fair_ah")),
        "market_ah": market["market_ah"],
        "edge_ah": _float_or_none(_first(pricing, "edge_ah") if pricing else raw.get("edge_ah")),
        "market_odds_home": market["market_odds_home"],
        "market_odds_away": market["market_odds_away"],
        "devig_method": None,
        "locked_market_snapshot_id": market["snapshot_id"],
        "final_score": result["final_score"],
        "settlement_outcome": None,
        "sample_included": False,
        "win_included": False,
        "exclusion_reason": None,
        "data_source": row_source,
        "authoritative": report_authoritative and not _is_demo_source(row_source),
        "score_delta": raw.get("score_delta"),
    }
    reason = _first_exclusion_reason(row, kickoff=kickoff, as_of=as_of)
    if reason is not None:
        row["exclusion_reason"] = reason
        return row
    devig_result = devig(
        {
            "HOME": Decimal(str(row["market_odds_home"])),
            "AWAY": Decimal(str(row["market_odds_away"])),
        },
        DevigMethod.PROPORTIONAL,
    )
    selection = _selection_from_row(row)
    prediction = LockedPrediction(
        fixture_id=fixture_id,
        market="ASIAN_HANDICAP",
        selection=selection,
        line=str(row["market_ah"]),
        locked_decimal_odds=Decimal(str(row[f"market_odds_{selection.lower()}"])),
        model_probability=Decimal("0.5"),
        locked_at=as_of or generated_at,
        prediction_hash=stable_hash({"fixture_id": fixture_id, "as_of": row["as_of"]}),
        asof_market_snapshot_id=str(row["locked_market_snapshot_id"]),
        devig_method=DevigMethod.PROPORTIONAL.value,
        market_baseline_probability=Decimal(str(devig_result.probabilities[selection])),
    )
    result_model = MatchResult(
        fixture_id=fixture_id,
        home_goals_90=int(result["home_goals"]),
        away_goals_90=int(result["away_goals"]),
        final_at=generated_at,
        result_status=str(result["result_status"] or "FINAL"),
    )
    settled = settle_prediction(
        prediction,
        result_model,
        closing_decimal_odds=None,
        evaluated_at=generated_at,
    )
    row["devig_method"] = DevigMethod.PROPORTIONAL.value
    row["settlement_outcome"] = settled.outcome
    if settled.outcome == "VOID":
        row["exclusion_reason"] = EXCLUSION_VOID_SETTLEMENT
        return row
    row["sample_included"] = True
    row["win_included"] = settled.win_included
    return row


def _market_fields(raw: dict[str, Any]) -> dict[str, Any]:
    raw_odds = raw.get("current_odds")
    odds = raw_odds if isinstance(raw_odds, dict) else {}
    raw_ah = odds.get("asian_handicap")
    ah = raw_ah if isinstance(raw_ah, dict) else {}
    pricing = raw.get("pricing_shadow")
    pricing_shadow = pricing if isinstance(pricing, dict) else {}
    return {
        "market_ah": _float_or_none(
            _first(raw, "market_ah")
            or _first(ah, "line", "balanced_line")
            or _first(pricing_shadow, "market_ah")
        ),
        "market_odds_home": _float_or_none(
            _first(raw, "market_odds_home")
            or _nested(ah, "side_prices", "home")
            or _nested(ah, "side_prices", "HOME")
        ),
        "market_odds_away": _float_or_none(
            _first(raw, "market_odds_away")
            or _nested(ah, "side_prices", "away")
            or _nested(ah, "side_prices", "AWAY")
        ),
        "snapshot_id": _first(raw, "locked_market_snapshot_id", "asof_market_snapshot_id")
        or _first(pricing_shadow, "asof_market_snapshot_id"),
    }


def _result_fields(raw: dict[str, Any]) -> dict[str, Any]:
    raw_result = raw.get("result")
    result_payload = raw_result if isinstance(raw_result, dict) else {}
    final_score = _first(raw, "final_score") or result_payload.get("final_score")
    home_goals = (
        _first(raw, "home_goals", "home_goals_90") or result_payload.get("home_goals")
    )
    away_goals = (
        _first(raw, "away_goals", "away_goals_90") or result_payload.get("away_goals")
    )
    if (home_goals is None or away_goals is None) and isinstance(final_score, str):
        parts = final_score.replace(":", "-").split("-")
        if len(parts) == 2:
            home_goals = _int_or_none(parts[0])
            away_goals = _int_or_none(parts[1])
    if home_goals is not None and away_goals is not None:
        final_score = f"{int(home_goals)}-{int(away_goals)}"
    return {
        "home_goals": _int_or_none(home_goals),
        "away_goals": _int_or_none(away_goals),
        "final_score": final_score,
        "result_status": _first(raw, "result_status", "status") or result_payload.get("status"),
    }


def _first_exclusion_reason(
    row: dict[str, Any],
    *,
    kickoff: datetime | None,
    as_of: datetime | None,
) -> str | None:
    if _is_demo_source(str(row.get("data_source") or "")):
        return EXCLUSION_DEMO_DATA
    if row.get("authoritative") is not True:
        return EXCLUSION_NON_AUTHORITATIVE
    if as_of is None:
        return EXCLUSION_MISSING_AS_OF
    if kickoff is not None and as_of >= kickoff:
        return EXCLUSION_POST_KICKOFF_ODDS
    if row.get("market_ah") is None or not row.get("locked_market_snapshot_id"):
        return EXCLUSION_MISSING_MARKET_LINE
    if row.get("market_odds_home") is None or row.get("market_odds_away") is None:
        return EXCLUSION_MISSING_DEVIG_ODDS
    if row.get("fair_ah") is None:
        return EXCLUSION_MISSING_FAIR_AH
    if row.get("final_score") is None:
        return EXCLUSION_MISSING_RESULT
    return None


def _sample_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    reasons = Counter(
        str(row.get("exclusion_reason")) for row in rows if row.get("exclusion_reason")
    )
    return {
        "total": len(rows),
        "eligible": len([row for row in rows if row.get("authoritative") is True]),
        "settled": len([row for row in rows if row.get("settlement_outcome") is not None]),
        "included": len([row for row in rows if row.get("sample_included") is True]),
        "excluded": len([row for row in rows if row.get("sample_included") is not True]),
        "exclusion_reasons": dict(sorted(reasons.items())),
    }


def _metrics(rows: list[dict[str, Any]], included_rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not included_rows:
        void_count = len([row for row in rows if row.get("settlement_outcome") == "VOID"])
        return {
            "sample_size": 0,
            "win_rate": None,
            "push_rate": None,
            "void_rate": None if not rows else void_count / len(rows),
            "avg_edge": None,
            "devig_market_advantage": None,
            "confidence_interval": None,
        }
    wins = len([row for row in included_rows if row.get("win_included") is True])
    pushes = len([row for row in included_rows if row.get("settlement_outcome") == "PUSH"])
    edges = [float(row["edge_ah"]) for row in included_rows if row.get("edge_ah") is not None]
    win_rate = wins / len(included_rows)
    return {
        "sample_size": len(included_rows),
        "win_rate": win_rate,
        "push_rate": pushes / len(included_rows),
        "void_rate": 0.0,
        "avg_edge": sum(edges) / len(edges) if edges else None,
        "devig_market_advantage": None,
        "confidence_interval": _wilson_interval(wins, len(included_rows)),
    }


def _split_checks(
    included_rows: list[dict[str, Any]],
    *,
    min_samples: int,
) -> dict[str, dict[str, Any]]:
    sample_size = len(included_rows)
    enough = sample_size >= min_samples
    return {
        "time_split": {"passed": enough, "sample_size": sample_size},
        "holdout": {"passed": enough, "sample_size": sample_size},
        "forward_shadow": {"passed": enough, "sample_size": sample_size},
    }


def _s2_gate(
    *,
    sample_size: int,
    split_checks: dict[str, dict[str, Any]],
    min_samples: int,
) -> dict[str, Any]:
    sample_minimum = sample_size >= min_samples
    all_pass = (
        sample_minimum
        and all(bool(value.get("passed")) for value in split_checks.values())
        and False
    )
    reason = "FORMAL_GATE_DISABLED_IN_WAVE" if all_pass else "INSUFFICIENT_VALIDATED_SAMPLES"
    return {
        "n_min": min_samples,
        "sample_minimum": sample_minimum,
        "devig_market_advantage": False,
        "time_split": bool(split_checks["time_split"].get("passed")),
        "holdout_replication": bool(split_checks["holdout"].get("passed")),
        "forward_shadow": bool(split_checks["forward_shadow"].get("passed")),
        "beats_market": False,
        "formal_enabled": False,
        "candidate_enabled": False,
        "reason": reason,
    }


def _selection_from_row(row: dict[str, Any]) -> str:
    fair = float(row["fair_ah"])
    market = float(row["market_ah"])
    return "HOME" if fair < market else "AWAY"


def _authoritative_reason(*, mode: str, source_is_demo: bool, has_rows: bool) -> str:
    if mode == "demo" or source_is_demo:
        return "DEMO_DATA_NOT_AUTHORITATIVE"
    if mode == "dry-run":
        return "DRY_RUN_NOT_AUTHORITATIVE"
    if not has_rows:
        return "NO_REAL_ASOF_ROWS_FOUND"
    return "REAL_ASOF_SOURCE"


def _is_demo_source(source: str) -> bool:
    lowered = source.lower()
    return "stage5_demo" in lowered or "demo" in lowered


def _wilson_interval(wins: int, total: int) -> dict[str, float]:
    if total == 0:
        return {"low": 0.0, "high": 0.0}
    z = 1.96
    p = wins / total
    denominator = 1 + z * z / total
    centre = p + z * z / (2 * total)
    margin = z * ((p * (1 - p) + z * z / (4 * total)) / total) ** 0.5
    return {
        "low": max(0.0, (centre - margin) / denominator),
        "high": min(1.0, (centre + margin) / denominator),
    }


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _first(row: Any, *keys: str) -> Any:
    if not isinstance(row, dict):
        return None
    for key in keys:
        value = row.get(key)
        if value is not None:
            return value
    return None


def _nested(row: Any, key: str, nested_key: str) -> Any:
    value = row.get(key) if isinstance(row, dict) else None
    if isinstance(value, dict):
        return value.get(nested_key)
    return None


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
