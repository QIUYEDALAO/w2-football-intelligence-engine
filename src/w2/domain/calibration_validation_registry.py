"""Evidence-bound, append-only calibration validation registry."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from datetime import UTC, date, datetime, time
from pathlib import Path, PurePosixPath
from typing import Any

from w2.domain.calibration_authority import RECOMMENDATION_VALIDATED_STATUSES
from w2.domain.canonical_serialization import HashDomain, canonical_sha256

LEDGER_SCHEMA_VERSION = "w2.calibration_validation_ledger.v1"
DEFAULT_LEDGER_PATH = Path(__file__).with_name("calibration_validation_ledger.jsonl")
DEFAULT_REPOSITORY_ROOT = Path(__file__).parents[3]
_CANONICAL_HASH_DOMAIN = HashDomain.PREMATCH_READ_MODEL_GENERIC

_REQUIRED_RECORD_FIELDS = frozenset(
    {
        "ledger_schema_version",
        "calibration_identity",
        "calibration_version",
        "params",
        "preregistration_document_path",
        "preregistration_document_sha256",
        "cohort_sha256",
        "sample_size",
        "evaluation_window_start",
        "evaluation_window_end",
        "evaluated_at",
        "out_of_fold_metrics",
        "code_revision",
        "config_sha256",
        "verdict",
        "granted_at",
        "granter",
    }
)


class CalibrationValidationRegistryError(ValueError):
    """A calibration grant or ledger record violates the registry contract."""


def calibration_identity(*, calibration_version: str, params: object) -> str:
    """Return the stable identity of one versioned, complete parameter snapshot."""
    version = _required_text("calibration_version", calibration_version)
    return canonical_sha256(
        {"calibration_version": version, "params": _params_snapshot(params)},
        domain=_CANONICAL_HASH_DOMAIN,
    )


def lookup_calibration_verdict(
    *,
    calibration_version: str,
    params: object,
    ledger_path: Path | None = None,
) -> str | None:
    """Return the latest valid grant for the exact identity, or ``None``."""
    identity = calibration_identity(calibration_version=calibration_version, params=params)
    verdict: str | None = None
    for record in _read_records(ledger_path or DEFAULT_LEDGER_PATH):
        _validate_record(record)
        if record["calibration_identity"] == identity:
            verdict = str(record["verdict"])
    return verdict


def validate_calibration_ledger(
    *,
    ledger_path: Path | None = None,
    repository_root: Path = DEFAULT_REPOSITORY_ROOT,
) -> int:
    """Validate every record and its repository-owned preregistration document."""
    records = _read_records(ledger_path or DEFAULT_LEDGER_PATH)
    for record in records:
        _validate_record(record)
        _verify_preregistration_document(
            path=record["preregistration_document_path"],
            expected_sha256=record["preregistration_document_sha256"],
            repository_root=repository_root,
        )
    return len(records)


def register_calibration_validation(
    *,
    calibration_version: str,
    params: object,
    preregistration_document_path: str,
    preregistration_document_sha256: str,
    cohort_sha256: str,
    sample_size: int,
    evaluation_window_start: str,
    evaluation_window_end: str,
    evaluated_at: str,
    out_of_fold_metrics: Mapping[str, Any],
    code_revision: str,
    config_sha256: str,
    verdict: str,
    granted_at: str,
    granter: str,
    ledger_path: Path = DEFAULT_LEDGER_PATH,
    repository_root: Path = DEFAULT_REPOSITORY_ROOT,
) -> dict[str, Any]:
    """Validate all evidence, then append exactly one immutable grant record."""
    if not is_dataclass(params) or isinstance(params, type):
        raise CalibrationValidationRegistryError("params must be a dataclass instance")
    expected_preregistration_sha256 = _required_sha256(
        "preregistration_document_sha256", preregistration_document_sha256
    )
    relative_preregistration = _verify_preregistration_document(
        path=preregistration_document_path,
        expected_sha256=expected_preregistration_sha256,
        repository_root=repository_root,
    )

    params_snapshot = _params_snapshot(params)
    record: dict[str, Any] = {
        "ledger_schema_version": LEDGER_SCHEMA_VERSION,
        "calibration_identity": calibration_identity(
            calibration_version=calibration_version, params=params_snapshot
        ),
        "calibration_version": calibration_version,
        "params": params_snapshot,
        "preregistration_document_path": relative_preregistration.as_posix(),
        "preregistration_document_sha256": expected_preregistration_sha256,
        "cohort_sha256": cohort_sha256,
        "sample_size": sample_size,
        "evaluation_window_start": evaluation_window_start,
        "evaluation_window_end": evaluation_window_end,
        "evaluated_at": evaluated_at,
        "out_of_fold_metrics": dict(out_of_fold_metrics),
        "code_revision": code_revision,
        "config_sha256": config_sha256,
        "verdict": verdict,
        "granted_at": granted_at,
        "granter": granter,
    }
    _validate_record(record)

    line = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a+", encoding="utf-8") as ledger:
        fcntl.flock(ledger.fileno(), fcntl.LOCK_EX)
        ledger.seek(0)
        for existing_line in ledger:
            if existing_line.strip():
                existing = _decode_record(existing_line)
                _validate_record(existing)
                _verify_preregistration_document(
                    path=existing["preregistration_document_path"],
                    expected_sha256=existing["preregistration_document_sha256"],
                    repository_root=repository_root,
                )
        ledger.write(line)
        ledger.flush()
        os.fsync(ledger.fileno())
    return record


def _params_snapshot(params: object) -> dict[str, Any]:
    if is_dataclass(params) and not isinstance(params, type):
        value = asdict(params)
    elif isinstance(params, Mapping):
        value = dict(params)
    else:
        raise CalibrationValidationRegistryError("params must be a dataclass or mapping")
    if not value or any(not isinstance(key, str) or not key for key in value):
        raise CalibrationValidationRegistryError("params must be a non-empty string-keyed snapshot")
    canonical_sha256(value, domain=_CANONICAL_HASH_DOMAIN)
    return value


def _read_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [_decode_record(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _decode_record(line: str) -> dict[str, Any]:
    try:
        value = json.loads(line)
    except json.JSONDecodeError as error:
        raise CalibrationValidationRegistryError("ledger contains invalid JSON") from error
    if not isinstance(value, dict):
        raise CalibrationValidationRegistryError("ledger record must be a JSON object")
    return value


def _validate_record(record: Mapping[str, Any]) -> None:
    missing = sorted(_REQUIRED_RECORD_FIELDS - record.keys())
    if missing:
        raise CalibrationValidationRegistryError(f"missing evidence fields: {', '.join(missing)}")
    if record["ledger_schema_version"] != LEDGER_SCHEMA_VERSION:
        raise CalibrationValidationRegistryError("unsupported ledger schema version")
    version = _required_text("calibration_version", record["calibration_version"])
    expected_identity = calibration_identity(calibration_version=version, params=record["params"])
    if record["calibration_identity"] != expected_identity:
        raise CalibrationValidationRegistryError("calibration identity mismatch")
    if record["verdict"] not in RECOMMENDATION_VALIDATED_STATUSES:
        raise CalibrationValidationRegistryError("verdict is not a validated calibration status")
    _repository_relative_path(record["preregistration_document_path"])
    for field in (
        "preregistration_document_sha256",
        "cohort_sha256",
        "config_sha256",
    ):
        _required_sha256(field, record[field])
    _required_hex("code_revision", record["code_revision"], length=40)
    if isinstance(record["sample_size"], bool) or not isinstance(record["sample_size"], int):
        raise CalibrationValidationRegistryError("sample_size must be a positive integer")
    if record["sample_size"] <= 0:
        raise CalibrationValidationRegistryError("sample_size must be a positive integer")
    start = _iso_window_boundary("evaluation_window_start", record["evaluation_window_start"])
    end = _iso_window_boundary("evaluation_window_end", record["evaluation_window_end"])
    if start > end:
        raise CalibrationValidationRegistryError("evaluation window start must not exceed end")
    _iso_datetime("evaluated_at", record["evaluated_at"])
    _iso_datetime("granted_at", record["granted_at"])
    metrics = record["out_of_fold_metrics"]
    if not isinstance(metrics, Mapping) or not metrics:
        raise CalibrationValidationRegistryError("out_of_fold_metrics must be non-empty")
    canonical_sha256(dict(metrics), domain=_CANONICAL_HASH_DOMAIN)
    _required_text("granter", record["granter"])


def _required_text(field: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CalibrationValidationRegistryError(f"{field} must be non-empty text")
    return value


def _required_sha256(field: str, value: object) -> str:
    return _required_hex(field, value, length=64)


def _required_hex(field: str, value: object, *, length: int) -> str:
    text = _required_text(field, value)
    if len(text) != length or any(character not in "0123456789abcdef" for character in text):
        raise CalibrationValidationRegistryError(
            f"{field} must be {length} lowercase hexadecimal characters"
        )
    return text


def _iso_datetime(field: str, value: object) -> datetime:
    text = _required_text(field, value)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise CalibrationValidationRegistryError(f"{field} must be an ISO-8601 datetime") from error
    if parsed.tzinfo is None:
        raise CalibrationValidationRegistryError(f"{field} must include a timezone")
    return parsed


def _iso_window_boundary(field: str, value: object) -> datetime:
    text = _required_text(field, value)
    try:
        parsed_date = date.fromisoformat(text)
    except ValueError:
        return _iso_datetime(field, text)
    return datetime.combine(parsed_date, time.min, tzinfo=UTC)


def _repository_relative_path(value: object) -> PurePosixPath:
    text = _required_text("preregistration_document_path", value)
    path = PurePosixPath(text)
    if path.is_absolute() or ".." in path.parts:
        raise CalibrationValidationRegistryError(
            "preregistration_document_path must be repository-relative"
        )
    return path


def _verify_preregistration_document(
    *, path: object, expected_sha256: object, repository_root: Path
) -> PurePosixPath:
    relative = _repository_relative_path(path)
    document = repository_root / relative
    expected = _required_sha256("preregistration_document_sha256", expected_sha256)
    if not document.is_file():
        raise CalibrationValidationRegistryError("preregistration document does not exist")
    if hashlib.sha256(document.read_bytes()).hexdigest() != expected:
        raise CalibrationValidationRegistryError("preregistration document digest mismatch")
    return relative
