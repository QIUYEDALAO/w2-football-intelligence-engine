from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

HISTORICAL_MODEL_REPLAY_ROW_SCHEMA = "w2.historical_model_replay_row.v1"
CALIBRATION_ARTIFACT_SCHEMA = "w2.calibration_artifact.v1"
CALIBRATION_MODE = "OFFLINE_SHADOW_ONLY"


@dataclass(frozen=True, kw_only=True)
class HistoricalModelReplayRowV1:
    schema_version: str
    fixture_id: str
    competition_id: str
    kickoff_utc: str
    as_of_utc: str
    checkpoint_policy: str
    code_sha: str
    model_version: str
    factor_registry_sha: str
    source_manifest_sha: str
    quote_identity_hash: str
    result_identity_hash: str
    market_baseline_hash: str
    calibration_version: str
    f5_status: str
    f5_fact_hashes: list[str]
    f8_status: str
    team_value_artifact_hashes: list[str]
    input_feature_hash: str
    model_settlement_distribution: dict[str, float]
    market_baseline_distribution: dict[str, float]
    selection: str
    line: str
    odds: str
    result: str
    clv: dict[str, Any]
    blockers: list[str]
    sample_natural_key: str
    row_hash: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, kw_only=True)
class CalibrationArtifactV1:
    schema_version: str
    status: str
    mode: str
    train_count: int
    validation_count: int
    holdout_count: int
    accepted_row_count: int
    rejected_row_count: int
    exclusion_report: dict[str, int]
    publicly_active: bool
    production_active: bool
    code_sha: str
    model_version: str
    factor_registry_sha: str
    historical_manifest_sha: str
    f5_manifest_sha: str
    f8_manifest_sha: str
    train_input_sha: str
    validation_input_sha: str
    holdout_input_sha: str
    parameters: dict[str, Any]
    metrics: dict[str, Any]
    evaluator_version: str
    review_status: str
    artifact_hash: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_historical_replay_row(row: Mapping[str, Any]) -> dict[str, Any]:
    blockers = _replay_blockers(row)
    payload: dict[str, Any] = {
        "schema_version": HISTORICAL_MODEL_REPLAY_ROW_SCHEMA,
        "fixture_id": _text(row.get("fixture_id")),
        "competition_id": _text(row.get("competition_id")),
        "kickoff_utc": _text(row.get("kickoff_utc")),
        "as_of_utc": _text(row.get("as_of_utc")),
        "checkpoint_policy": _text(row.get("checkpoint_policy")),
        "code_sha": _text(row.get("code_sha")),
        "model_version": _text(row.get("model_version")),
        "factor_registry_sha": _text(row.get("factor_registry_sha")),
        "source_manifest_sha": _text(row.get("source_manifest_sha")),
        "quote_identity_hash": _text(row.get("quote_identity_hash")),
        "result_identity_hash": _text(row.get("result_identity_hash")),
        "market_baseline_hash": _text(row.get("market_baseline_hash")),
        "calibration_version": _text(row.get("calibration_version")),
        "f5_status": _text(row.get("f5_status")),
        "f5_fact_hashes": _strings(row.get("f5_fact_hashes")),
        "f8_status": _text(row.get("f8_status")),
        "team_value_artifact_hashes": _strings(row.get("team_value_artifact_hashes")),
        "input_feature_hash": _hash(row.get("features") or {}),
        "model_settlement_distribution": _float_mapping(row.get("model_settlement_distribution")),
        "market_baseline_distribution": _float_mapping(row.get("market_baseline_distribution")),
        "selection": _text(row.get("selection")),
        "line": _text(row.get("line")),
        "odds": _text(row.get("odds")),
        "result": _text(row.get("result") or row.get("settlement_outcome")),
        "clv": {
            "entry_devig_probability": row.get("entry_devig_probability"),
            "closing_devig_probability": row.get("closing_devig_probability"),
            "closing_quote_identity_hash": row.get("closing_quote_identity_hash"),
            "closing_quote_captured_at": row.get("closing_quote_captured_at"),
            "closing_market": row.get("closing_market"),
            "closing_selection": row.get("closing_selection"),
            "closing_line": row.get("closing_line"),
        },
        "blockers": blockers,
        "sample_natural_key": _sample_natural_key(row),
    }
    payload["row_hash"] = _hash(payload)
    return HistoricalModelReplayRowV1(**payload).as_dict()


def build_calibration_artifact(
    rows: Iterable[Mapping[str, Any]],
    *,
    code_sha: str,
    model_version: str,
    factor_registry_sha: str,
    historical_manifest_sha: str,
    f5_manifest_sha: str,
    f8_manifest_sha: str,
    evaluator_version: str,
    test_only: bool = False,
) -> dict[str, Any]:
    replay_rows: list[Mapping[str, Any]] = [
        build_historical_replay_row(dict(row)) for row in rows
    ]
    by_hash: dict[str, Mapping[str, Any]] = {}
    by_natural_key: dict[str, str] = {}
    conflicts: list[Mapping[str, Any]] = []
    for row in replay_rows:
        row_hash = str(row.get("row_hash") or "")
        natural_key = str(row.get("sample_natural_key") or "")
        existing_hash = by_natural_key.get(natural_key)
        if natural_key and existing_hash is not None and existing_hash != row_hash:
            conflicts.append(
                {
                    **row,
                    "blockers": [
                        *list(row.get("blockers") or []),
                        "REPLAY_SAMPLE_IDENTITY_CONFLICT",
                    ],
                }
            )
            continue
        if natural_key:
            by_natural_key[natural_key] = row_hash
        existing = by_hash.get(row_hash)
        if existing is None:
            by_hash[row_hash] = row
        elif existing != row:
            conflicts.append(
                {
                    **row,
                    "blockers": [
                        *list(row.get("blockers") or []),
                        "REPLAY_ROW_HASH_CONFLICT",
                    ],
                }
            )
    replay_rows = [*by_hash.values(), *conflicts]
    accepted_rows = [row for row in replay_rows if not row.get("blockers")]
    rejected_rows = [row for row in replay_rows if row.get("blockers")]
    splits = _split_counts(accepted_rows)
    status = "TEST_ONLY" if test_only and accepted_rows else "INSUFFICIENT_EVIDENCE"
    payload: dict[str, Any] = {
        "schema_version": CALIBRATION_ARTIFACT_SCHEMA,
        "status": status,
        "mode": CALIBRATION_MODE,
        "train_count": splits["train"],
        "validation_count": splits["validation"],
        "holdout_count": splits["holdout"],
        "accepted_row_count": len(accepted_rows),
        "rejected_row_count": len(rejected_rows),
        "exclusion_report": _exclusion_report(rejected_rows),
        "publicly_active": False,
        "production_active": False,
        "code_sha": code_sha,
        "model_version": model_version,
        "factor_registry_sha": factor_registry_sha,
        "historical_manifest_sha": historical_manifest_sha,
        "f5_manifest_sha": f5_manifest_sha,
        "f8_manifest_sha": f8_manifest_sha,
        "train_input_sha": _hash([row for row in accepted_rows if _split(row) == "train"]),
        "validation_input_sha": _hash(
            [row for row in accepted_rows if _split(row) == "validation"]
        ),
        "holdout_input_sha": _hash([row for row in accepted_rows if _split(row) == "holdout"]),
        "parameters": {},
        "metrics": {"test_only": test_only},
        "evaluator_version": evaluator_version,
        "review_status": "REVIEW_REQUIRED",
    }
    payload["artifact_hash"] = _hash(payload)
    return CalibrationArtifactV1(**payload).as_dict()


def _replay_blockers(row: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    kickoff = _parse(row.get("kickoff_utc"))
    as_of = _parse(row.get("as_of_utc"))
    entry_captured_at = _parse(row.get("entry_captured_at"))
    if kickoff is None or as_of is None:
        blockers.append("INVALID_REPLAY_TIMESTAMP")
    elif as_of >= kickoff:
        blockers.append("ASOF_NOT_STRICTLY_PREMATCH")
    if kickoff is None or entry_captured_at is None:
        blockers.append("INVALID_ENTRY_TIMESTAMP")
    elif entry_captured_at >= kickoff:
        blockers.append("ENTRY_NOT_STRICTLY_PREMATCH")
    if row.get("f5_status") != "READY" or row.get("f5_proxy") is True:
        blockers.append("F5_PROXY_OR_NOT_READY")
    if not _strings(row.get("f5_fact_hashes")):
        blockers.append("F5_MANIFEST_MISSING")
    if row.get("f8_status") != "READY":
        blockers.append("F8_INCOMPLETE")
    if not _strings(row.get("team_value_artifact_hashes")):
        blockers.append("F8_ARTIFACT_MISSING")
    if row.get("future_valuation") is True:
        blockers.append("FUTURE_VALUATION")
    if row.get("market_baseline_status") != "READY":
        blockers.append("MISSING_MARKET_BASELINE")
    if row.get("mixed_quote_batch") is True:
        blockers.append("MIXED_QUOTE_BATCH")
    if not _text(row.get("source_manifest_sha")):
        blockers.append("MISSING_SOURCE_HASH")
    for key in (
        "model_version",
        "calibration_version",
        "factor_registry_sha",
        "market_baseline_hash",
    ):
        if not _text(row.get(key)):
            blockers.append(f"MISSING_{key.upper()}")
    for key in ("sample_natural_key", "selection", "line", "odds", "entry_captured_at"):
        if not _text(row.get(key)):
            blockers.append(f"MISSING_{key.upper()}")
    if not _complete_probability(row.get("model_settlement_distribution")):
        blockers.append("MISSING_MODEL_SETTLEMENT_DISTRIBUTION")
    if not _complete_probability(row.get("market_baseline_distribution")):
        blockers.append("MISSING_MARKET_BASELINE_DISTRIBUTION")
    if not _text(row.get("quote_identity_hash")):
        blockers.append("MISSING_QUOTE_IDENTITY")
    if not _text(row.get("result_identity_hash")):
        blockers.append("MISSING_RESULT_IDENTITY")
    closing_time = _parse(row.get("closing_quote_captured_at"))
    if closing_time is None:
        blockers.append("INVALID_CLOSING_TIME")
    if not _text(row.get("closing_quote_identity_hash")):
        blockers.append("MISSING_CLOSING_QUOTE_IDENTITY")
    for key in ("closing_market", "closing_selection", "closing_line", "closing_devig_probability"):
        if row.get(key) in {None, ""}:
            blockers.append(f"MISSING_{key.upper()}")
    if _text(row.get("closing_market")) and _text(row.get("market")):
        if _text(row.get("closing_market")) != _text(row.get("market")):
            blockers.append("CLOSING_MARKET_MISMATCH")
    if _text(row.get("closing_selection")) and _text(row.get("selection")):
        if _text(row.get("closing_selection")) != _text(row.get("selection")):
            blockers.append("CLOSING_SELECTION_MISMATCH")
    if _text(row.get("closing_line")) and _text(row.get("line")):
        if _text(row.get("closing_line")) != _text(row.get("line")):
            blockers.append("CLOSING_LINE_MISMATCH")
    if row.get("identity_conflict") is True:
        blockers.append("IDENTITY_CONFLICT")
    return blockers


def _sample_natural_key(row: Mapping[str, Any]) -> str:
    supplied = _text(row.get("sample_natural_key"))
    if supplied:
        return supplied
    return _hash(
        {
            "fixture_id": row.get("fixture_id"),
            "market": row.get("market"),
            "selection": row.get("selection"),
            "line": row.get("line"),
            "as_of_utc": row.get("as_of_utc"),
        }
    )


def _split_counts(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    return {
        name: sum(1 for row in rows if _split(row) == name)
        for name in ("train", "validation", "holdout")
    }


def _split(row: Mapping[str, Any]) -> str:
    kickoff = _parse(row.get("kickoff_utc"))
    if kickoff is None:
        return "invalid"
    if kickoff <= datetime(2024, 12, 31, 23, 59, 59, tzinfo=UTC):
        return "train"
    if kickoff <= datetime(2025, 12, 31, 23, 59, 59, tzinfo=UTC):
        return "validation"
    return "holdout"


def _exclusion_report(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        blockers = row.get("blockers")
        if not isinstance(blockers, list):
            continue
        for blocker in blockers:
            key = str(blocker)
            counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _parse(value: object) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)
    except (TypeError, ValueError):
        return None


def _float_mapping(value: object) -> dict[str, float]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): float(item) for key, item in value.items()}


def _complete_probability(value: object) -> bool:
    if not isinstance(value, Mapping):
        return False
    required = {"WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "LOSS"}
    if set(value) != required:
        return False
    try:
        numbers = [float(value[key]) for key in required]
    except (TypeError, ValueError):
        return False
    return all(0 <= item <= 1 for item in numbers) and abs(sum(numbers) - 1) <= 0.000001


def _strings(value: object) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def _text(value: object) -> str:
    return str(value) if value not in {None, ""} else ""


def _hash(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(encoded.encode()).hexdigest()
