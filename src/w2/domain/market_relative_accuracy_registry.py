"""Append-only, evidence-bound market-relative accuracy grants.

The shipped ledger is empty. This module provides a future grant path; it does
not infer a grant from calibration status or retrospective results. Grants are
immutable. An identity change starts a new cohort and requires a new grant.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from w2.domain.admission_contract import ECONOMIC_ADMISSION_CONTRACT_VERSION
from w2.domain.canonical_serialization import HashDomain, canonical_sha256

LEDGER_SCHEMA_VERSION = "w2.market_relative_accuracy_ledger.v1"
VALIDATED_VERDICT = "MARKET_RELATIVE_ACCURACY_VALIDATED"
DEFAULT_LEDGER_PATH = Path(__file__).with_name("market_relative_accuracy_ledger.jsonl")
DEFAULT_REPOSITORY_ROOT = Path(__file__).parents[3]
MIN_SETTLED_FIXTURES_PER_MARKET = 1500
EARLIEST_EVALUATION_AT = datetime(2027, 6, 1, tzinfo=UTC)
_HASH_DOMAIN = HashDomain.PREMATCH_READ_MODEL_GENERIC
_MARKETS = frozenset({"ASIAN_HANDICAP", "TOTALS"})
_EVALUATION_POLICY_VERSION = "candidate-eval.v2"
_SCORING_CONTRACT_VERSION = "w2.market_relative_accuracy.scalar_settlement_brier.v1"
_REQUIRED_FIELDS = frozenset(
    {
        "ledger_schema_version",
        "admission_identity",
        "model_identity",
        "calibration_identity",
        "market",
        "evaluation_policy_version",
        "economic_admission_contract_version",
        "scoring_contract_version",
        "preregistration_document_path",
        "preregistration_document_sha256",
        "cohort_sha256",
        "sample_size",
        "fixture_count",
        "evaluation_window_start",
        "evaluation_window_end",
        "metrics",
        "code_revision",
        "config_sha256",
        "verdict",
        "evaluated_at",
        "granted_at",
        "granter",
    }
)


class MarketRelativeAccuracyRegistryError(ValueError):
    """A grant or ledger record violates the frozen forward contract."""


def admission_identity(
    *,
    model_identity: str,
    calibration_identity: str,
    market: str,
    evaluation_policy_version: str,
    economic_admission_contract_version: str,
    scoring_contract_version: str,
) -> str:
    """Return the exact identity to which one market grant applies."""
    values = {
        "model_identity": _text("model_identity", model_identity),
        "calibration_identity": _sha256("calibration_identity", calibration_identity),
        "market": _market(market),
        "evaluation_policy_version": _text("evaluation_policy_version", evaluation_policy_version),
        "economic_admission_contract_version": _text(
            "economic_admission_contract_version", economic_admission_contract_version
        ),
        "scoring_contract_version": _text("scoring_contract_version", scoring_contract_version),
    }
    if values["evaluation_policy_version"] != _EVALUATION_POLICY_VERSION:
        raise MarketRelativeAccuracyRegistryError("evaluation policy is not preregistered")
    if values["economic_admission_contract_version"] != ECONOMIC_ADMISSION_CONTRACT_VERSION:
        raise MarketRelativeAccuracyRegistryError(
            "economic admission contract is not preregistered"
        )
    if values["scoring_contract_version"] != _SCORING_CONTRACT_VERSION:
        raise MarketRelativeAccuracyRegistryError("scoring contract is not preregistered")
    return canonical_sha256(values, domain=_HASH_DOMAIN)


def lookup_market_relative_accuracy_verdict(
    *,
    model_identity: str,
    calibration_identity: str,
    market: str,
    evaluation_policy_version: str,
    economic_admission_contract_version: str,
    scoring_contract_version: str,
    ledger_path: Path | None = None,
) -> str | None:
    """Return an exact-identity grant, or ``None`` when no grant exists."""
    identity = admission_identity(
        model_identity=model_identity,
        calibration_identity=calibration_identity,
        market=market,
        evaluation_policy_version=evaluation_policy_version,
        economic_admission_contract_version=economic_admission_contract_version,
        scoring_contract_version=scoring_contract_version,
    )
    verdict = None
    for record in _read(ledger_path or DEFAULT_LEDGER_PATH):
        _validate(record)
        if record["admission_identity"] == identity:
            if verdict is not None:
                raise MarketRelativeAccuracyRegistryError(
                    "ledger contains duplicate admission identity"
                )
            verdict = str(record["verdict"])
    return verdict


def validate_market_relative_accuracy_ledger(
    *,
    ledger_path: Path | None = None,
    repository_root: Path | None = None,
) -> int:
    """Validate the shipped ledger from a source checkout or CI only."""
    root = repository_root or DEFAULT_REPOSITORY_ROOT
    if repository_root is None and not (root / "pyproject.toml").is_file():
        raise MarketRelativeAccuracyRegistryError(
            "default repository root unavailable; validation requires source checkout or CI"
        )
    records = _read(ledger_path or DEFAULT_LEDGER_PATH)
    identities: set[str] = set()
    for record in records:
        _validate(record)
        identity = str(record["admission_identity"])
        if identity in identities:
            raise MarketRelativeAccuracyRegistryError(
                "ledger contains duplicate admission identity"
            )
        identities.add(identity)
        _verify_document(
            record["preregistration_document_path"],
            record["preregistration_document_sha256"],
            root,
        )
    return len(records)


def register_market_relative_accuracy(
    *,
    model_identity: str,
    calibration_identity: str,
    market: str,
    evaluation_policy_version: str,
    economic_admission_contract_version: str,
    scoring_contract_version: str,
    preregistration_document_path: str,
    preregistration_document_sha256: str,
    cohort_sha256: str,
    sample_size: int,
    fixture_count: int,
    evaluation_window_start: str,
    evaluation_window_end: str,
    metrics: Mapping[str, Any],
    code_revision: str,
    config_sha256: str,
    verdict: str,
    evaluated_at: str,
    granted_at: str,
    granter: str,
    ledger_path: Path = DEFAULT_LEDGER_PATH,
    repository_root: Path = DEFAULT_REPOSITORY_ROOT,
) -> dict[str, Any]:
    """Validate every field and protocol gate before one append."""
    relative = _verify_document(
        preregistration_document_path,
        preregistration_document_sha256,
        repository_root,
    )
    record: dict[str, Any] = {
        "ledger_schema_version": LEDGER_SCHEMA_VERSION,
        "admission_identity": admission_identity(
            model_identity=model_identity,
            calibration_identity=calibration_identity,
            market=market,
            evaluation_policy_version=evaluation_policy_version,
            economic_admission_contract_version=economic_admission_contract_version,
            scoring_contract_version=scoring_contract_version,
        ),
        "model_identity": model_identity,
        "calibration_identity": calibration_identity,
        "market": market,
        "evaluation_policy_version": evaluation_policy_version,
        "economic_admission_contract_version": economic_admission_contract_version,
        "scoring_contract_version": scoring_contract_version,
        "preregistration_document_path": relative.as_posix(),
        "preregistration_document_sha256": preregistration_document_sha256,
        "cohort_sha256": cohort_sha256,
        "sample_size": sample_size,
        "fixture_count": fixture_count,
        "evaluation_window_start": evaluation_window_start,
        "evaluation_window_end": evaluation_window_end,
        "metrics": dict(metrics),
        "code_revision": code_revision,
        "config_sha256": config_sha256,
        "verdict": verdict,
        "evaluated_at": evaluated_at,
        "granted_at": granted_at,
        "granter": granter,
    }
    _validate(record)
    line = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a+", encoding="utf-8") as ledger:
        fcntl.flock(ledger.fileno(), fcntl.LOCK_EX)
        ledger.seek(0)
        for existing_line in ledger:
            if existing_line.strip():
                existing = _decode(existing_line)
                _validate(existing)
                _verify_document(
                    existing["preregistration_document_path"],
                    existing["preregistration_document_sha256"],
                    repository_root,
                )
                if existing["admission_identity"] == record["admission_identity"]:
                    raise MarketRelativeAccuracyRegistryError(
                        "admission identity already has an immutable grant"
                    )
        ledger.write(line)
        ledger.flush()
        os.fsync(ledger.fileno())
    return record


def _validate(record: Mapping[str, Any]) -> None:
    missing = sorted(_REQUIRED_FIELDS - record.keys())
    if missing:
        raise MarketRelativeAccuracyRegistryError(f"missing evidence fields: {', '.join(missing)}")
    if record["ledger_schema_version"] != LEDGER_SCHEMA_VERSION:
        raise MarketRelativeAccuracyRegistryError("unsupported ledger schema version")
    expected = admission_identity(
        model_identity=record["model_identity"],
        calibration_identity=record["calibration_identity"],
        market=record["market"],
        evaluation_policy_version=record["evaluation_policy_version"],
        economic_admission_contract_version=record["economic_admission_contract_version"],
        scoring_contract_version=record["scoring_contract_version"],
    )
    if record["admission_identity"] != expected:
        raise MarketRelativeAccuracyRegistryError("admission identity mismatch")
    if record["verdict"] != VALIDATED_VERDICT:
        raise MarketRelativeAccuracyRegistryError("verdict is not validated")
    _relative_path(record["preregistration_document_path"])
    for field in ("preregistration_document_sha256", "cohort_sha256", "config_sha256"):
        _sha256(field, record[field])
    _hex("code_revision", record["code_revision"], 40)
    sample_size = _positive_int("sample_size", record["sample_size"])
    fixture_count = _positive_int("fixture_count", record["fixture_count"])
    if fixture_count < MIN_SETTLED_FIXTURES_PER_MARKET:
        raise MarketRelativeAccuracyRegistryError("fixture_count below preregistered minimum")
    if sample_size < fixture_count:
        raise MarketRelativeAccuracyRegistryError("sample_size must cover fixture_count")
    start = _datetime("evaluation_window_start", record["evaluation_window_start"])
    end = _datetime("evaluation_window_end", record["evaluation_window_end"])
    if start > end:
        raise MarketRelativeAccuracyRegistryError("evaluation window start exceeds end")
    evaluated_at = _datetime("evaluated_at", record["evaluated_at"])
    if evaluated_at < EARLIEST_EVALUATION_AT:
        raise MarketRelativeAccuracyRegistryError("evaluated_at precedes preregistered date")
    if evaluated_at < start:
        raise MarketRelativeAccuracyRegistryError("evaluated_at precedes evaluation window start")
    granted_at = _datetime("granted_at", record["granted_at"])
    if granted_at < evaluated_at:
        raise MarketRelativeAccuracyRegistryError("granted_at precedes evaluated_at")
    metrics = record["metrics"]
    if not isinstance(metrics, Mapping):
        raise MarketRelativeAccuracyRegistryError("metrics must be an object")
    for field in ("model_minus_market_brier", "one_sided_95pct_upper_bound"):
        value = metrics.get(field)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise MarketRelativeAccuracyRegistryError(f"metrics.{field} must be finite")
    if float(metrics["one_sided_95pct_upper_bound"]) > 0:
        raise MarketRelativeAccuracyRegistryError("market-relative accuracy pass rule failed")
    upper_bounds = metrics.get("all_market_one_sided_95pct_upper_bounds")
    fixture_counts = metrics.get("all_market_fixture_counts")
    if not isinstance(upper_bounds, Mapping) or set(upper_bounds) != _MARKETS:
        raise MarketRelativeAccuracyRegistryError("both market upper bounds are required")
    if not isinstance(fixture_counts, Mapping) or set(fixture_counts) != _MARKETS:
        raise MarketRelativeAccuracyRegistryError("both market fixture counts are required")
    for market in _MARKETS:
        upper = upper_bounds[market]
        if (
            isinstance(upper, bool)
            or not isinstance(upper, (int, float))
            or not math.isfinite(upper)
            or upper > 0
        ):
            raise MarketRelativeAccuracyRegistryError("both markets must pass")
        _positive_int(f"all_market_fixture_counts.{market}", fixture_counts[market])
        if fixture_counts[market] < MIN_SETTLED_FIXTURES_PER_MARKET:
            raise MarketRelativeAccuracyRegistryError("both markets must meet sample minimum")
    canonical_sha256(dict(metrics), domain=_HASH_DOMAIN)
    _text("granter", record["granter"])


def _read(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [_decode(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _decode(line: str) -> dict[str, Any]:
    try:
        value = json.loads(line)
    except json.JSONDecodeError as error:
        raise MarketRelativeAccuracyRegistryError("ledger contains invalid JSON") from error
    if not isinstance(value, dict):
        raise MarketRelativeAccuracyRegistryError("ledger record must be an object")
    return value


def _verify_document(path: object, digest: object, root: Path) -> PurePosixPath:
    relative = _relative_path(path)
    expected = _sha256("preregistration_document_sha256", digest)
    document = root / relative
    if not document.is_file():
        raise MarketRelativeAccuracyRegistryError("preregistration document does not exist")
    if hashlib.sha256(document.read_bytes()).hexdigest() != expected:
        raise MarketRelativeAccuracyRegistryError("preregistration document digest mismatch")
    return relative


def _relative_path(value: object) -> PurePosixPath:
    path = PurePosixPath(_text("preregistration_document_path", value))
    if path.is_absolute() or ".." in path.parts:
        raise MarketRelativeAccuracyRegistryError(
            "preregistration path must be repository-relative"
        )
    return path


def _market(value: object) -> str:
    market = _text("market", value)
    if market not in _MARKETS:
        raise MarketRelativeAccuracyRegistryError("market is unsupported")
    return market


def _positive_int(field: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise MarketRelativeAccuracyRegistryError(f"{field} must be a positive integer")
    return value


def _datetime(field: str, value: object) -> datetime:
    text = _text(field, value)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise MarketRelativeAccuracyRegistryError(f"{field} must be ISO-8601") from error
    if parsed.tzinfo is None:
        raise MarketRelativeAccuracyRegistryError(f"{field} must include timezone")
    return parsed.astimezone(UTC)


def _sha256(field: str, value: object) -> str:
    return _hex(field, value, 64)


def _hex(field: str, value: object, length: int) -> str:
    text = _text(field, value)
    if len(text) != length or any(character not in "0123456789abcdef" for character in text):
        raise MarketRelativeAccuracyRegistryError(
            f"{field} must be {length} lowercase hexadecimal characters"
        )
    return text


def _text(field: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MarketRelativeAccuracyRegistryError(f"{field} must be non-empty text")
    return value
