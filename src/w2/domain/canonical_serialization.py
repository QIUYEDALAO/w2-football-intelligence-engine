from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import struct
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any


class CanonicalErrorCode(StrEnum):
    UNSUPPORTED_SERIALIZER_VERSION = "UNSUPPORTED_SERIALIZER_VERSION"
    NON_FINITE_FLOAT = "NON_FINITE_FLOAT"
    NON_FINITE_DECIMAL = "NON_FINITE_DECIMAL"
    NAIVE_DATETIME = "NAIVE_DATETIME"
    NON_STRING_KEY = "NON_STRING_KEY"
    RESERVED_TAG = "RESERVED_TAG"
    UNICODE_KEY_COLLISION = "UNICODE_KEY_COLLISION"
    UNSUPPORTED_TYPE = "UNSUPPORTED_TYPE"
    LEGACY_DOMAIN_UNSUPPORTED = "LEGACY_DOMAIN_UNSUPPORTED"
    HISTORICAL_HASH_MISMATCH = "HISTORICAL_HASH_MISMATCH"
    BOOTSTRAP_CONTRACT_VERSION_REQUIRED = "BOOTSTRAP_CONTRACT_VERSION_REQUIRED"
    INVALID_PAIR_IDENTITY_HASH = "INVALID_PAIR_IDENTITY_HASH"


class CanonicalSerializationError(ValueError):
    """The value cannot be represented by the selected canonical contract."""

    def __init__(self, code: CanonicalErrorCode, message: str) -> None:
        self.code = code
        super().__init__(f"{code.value}: {message}")


class SerializerVersion(StrEnum):
    LEGACY_V1 = "w2.canonical-json.v1"
    V2 = "w2.canonical-json.v2"


CURRENT_SERIALIZER_VERSION = SerializerVersion.V2
HASH_DOMAIN_IN_PREIMAGE = False
SERIALIZER_VERSION_IN_PREIMAGE = False


class HashDomain(StrEnum):
    FUTURE_REFRESH_RAW_PAYLOAD = "future_refresh.raw_payload"
    FUTURE_REFRESH_ENDPOINT_CAPTURE = "future_refresh.endpoint_capture"
    FUTURE_REFRESH_MARKET_OBSERVATION = "future_refresh.market_observation"
    FUTURE_REFRESH_REQUEST_PARAMETERS = "future_refresh.request_parameters"
    FUTURE_REFRESH_LINEUP_EVENT = "future_refresh.lineup_event"
    FUTURE_REFRESH_FIXTURE_IDENTITY = "future_refresh.fixture_identity"
    FUTURE_REFRESH_EVIDENCE = "future_refresh.evidence"
    OUTCOME_LEDGER_PAYLOAD = "outcome_ledger.payload"
    OUTCOME_LEDGER_BUSINESS_KEY = "outcome_ledger.business_key"
    STAGE7I_LIFECYCLE_PAYLOAD = "stage7i_lifecycle.payload"
    STAGE7I_LIFECYCLE_EVENT = "stage7i_lifecycle.event"
    STAGE7I_SUPERVISION_EVENT = "stage7i_supervision.event"
    PREMATCH_READ_MODEL_GENERIC = "prematch_read_model.generic"
    PREMATCH_READ_MODEL_SOURCE_EVENT = "prematch_read_model.source_event"
    PREMATCH_READ_MODEL_FIXTURE_INPUT = "prematch_read_model.fixture_input"
    PREMATCH_READ_MODEL_OBSERVATION_INPUT = "prematch_read_model.observation_input"
    PREMATCH_READ_MODEL_QUOTE_IDENTITY = "prematch_read_model.quote_identity"
    PREMATCH_READ_MODEL_SIMULATION = "prematch_read_model.simulation"
    PREMATCH_READ_MODEL_ANALYSIS_EVIDENCE = "prematch_read_model.analysis_evidence"
    PREMATCH_READ_MODEL_ARTIFACT = "prematch_read_model.artifact"
    PREMATCH_READ_MODEL_SOURCE_MANIFEST = "prematch_read_model.source_manifest"
    PREMATCH_READ_MODEL_LINEUP_EVENT = "prematch_read_model.lineup_event"
    PREMATCH_READ_MODEL_PROJECTION = "prematch_read_model.projection"
    PREMATCH_READ_MODEL_READ_TIME = "prematch_read_model.read_time"
    PREMATCH_READ_MODEL_DYNAMIC_EVALUATION = "prematch_read_model.dynamic_evaluation"
    PREMATCH_READ_MODEL_SIMULATION_RECONCILIATION = (
        "prematch_read_model.simulation_reconciliation"
    )
    EVAL_02B_PAIR_IDENTITY = "eval_02b.pair_identity"
    EVAL_02B_BOOTSTRAP_SEED = "eval_02b.bootstrap_seed"


_READ_MODEL_DOMAINS = frozenset(
    domain for domain in HashDomain if domain.value.startswith("prematch_read_model.")
)
_ASCII_LEGACY_DOMAINS = frozenset(HashDomain) - _READ_MODEL_DOMAINS - {
    HashDomain.EVAL_02B_PAIR_IDENTITY,
    HashDomain.EVAL_02B_BOOTSTRAP_SEED,
    HashDomain.STAGE7I_SUPERVISION_EVENT,
}
_RESERVED_TAGS = frozenset(
    {"$w2_bytes", "$w2_date", "$w2_datetime", "$w2_decimal", "$w2_float"}
)


@dataclass(frozen=True)
class VersionedDigest:
    domain: HashDomain
    serializer_version: SerializerVersion
    sha256: str


@dataclass(frozen=True)
class HashMigration:
    historical: VersionedDigest
    replacement: VersionedDigest

    def rollback(self) -> VersionedDigest:
        return self.historical


def canonical_bytes(
    value: object,
    *,
    domain: HashDomain,
    version: SerializerVersion = CURRENT_SERIALIZER_VERSION,
) -> bytes:
    if version is SerializerVersion.LEGACY_V1:
        return _legacy_bytes(value, domain)
    if version is not SerializerVersion.V2:
        raise CanonicalSerializationError(
            CanonicalErrorCode.UNSUPPORTED_SERIALIZER_VERSION,
            f"unsupported serializer version: {version}",
        )
    normalized = _normalize_v2(value)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(
    value: object,
    *,
    domain: HashDomain,
    version: SerializerVersion = CURRENT_SERIALIZER_VERSION,
) -> str:
    return hashlib.sha256(canonical_bytes(value, domain=domain, version=version)).hexdigest()


def verify_sha256(
    value: object,
    expected: str,
    *,
    domain: HashDomain,
    declared_version: SerializerVersion | None,
) -> VersionedDigest | None:
    version = declared_version or SerializerVersion.LEGACY_V1
    actual = canonical_sha256(value, domain=domain, version=version)
    if not hmac.compare_digest(actual, expected):
        return None
    return VersionedDigest(domain=domain, serializer_version=version, sha256=actual)


def verify_versioned_digest(
    value: object,
    expected: VersionedDigest,
    *,
    domain: HashDomain,
    serializer_version: SerializerVersion,
) -> bool:
    """Verify digest metadata before verifying its metadata-independent preimage."""
    if expected.domain is not domain or expected.serializer_version is not serializer_version:
        return False
    actual = canonical_sha256(value, domain=domain, version=serializer_version)
    return hmac.compare_digest(actual, expected.sha256)


def prepare_hash_migration(
    value: object,
    historical_sha256: str,
    *,
    domain: HashDomain,
    historical_version: SerializerVersion = SerializerVersion.LEGACY_V1,
) -> HashMigration:
    historical = verify_sha256(
        value,
        historical_sha256,
        domain=domain,
        declared_version=historical_version,
    )
    if historical is None:
        raise CanonicalSerializationError(
            CanonicalErrorCode.HISTORICAL_HASH_MISMATCH,
            "historical hash does not match its declared version",
        )
    return HashMigration(
        historical=historical,
        replacement=VersionedDigest(
            domain=domain,
            serializer_version=SerializerVersion.V2,
            sha256=canonical_sha256(value, domain=domain),
        ),
    )


def eval_02b_bootstrap_seed(
    validation_pair_identity_hashes: Sequence[str],
    *,
    contract_version: str,
) -> int:
    if not contract_version.strip():
        raise CanonicalSerializationError(
            CanonicalErrorCode.BOOTSTRAP_CONTRACT_VERSION_REQUIRED,
            "bootstrap contract version is required",
        )
    if any(
        len(value) != 64 or any(character not in "0123456789abcdef" for character in value)
        for value in validation_pair_identity_hashes
    ):
        raise CanonicalSerializationError(
            CanonicalErrorCode.INVALID_PAIR_IDENTITY_HASH,
            "bootstrap pair identity hash is invalid",
        )
    payload = {
        "contract_version": contract_version,
        "validation_pair_identity_hashes": sorted(validation_pair_identity_hashes),
    }
    digest = bytes.fromhex(
        canonical_sha256(payload, domain=HashDomain.EVAL_02B_BOOTSTRAP_SEED)
    )
    return int.from_bytes(digest[:8], "big", signed=False)


def _legacy_bytes(value: object, domain: HashDomain) -> bytes:
    if domain in _READ_MODEL_DOMAINS:
        default = _legacy_read_model_default
        ensure_ascii = False
        allow_nan = True
    elif domain is HashDomain.EVAL_02B_PAIR_IDENTITY:
        default = None
        ensure_ascii = False
        allow_nan = False
    elif domain is HashDomain.STAGE7I_SUPERVISION_EVENT:
        default = _legacy_stage7i_supervision_default
        ensure_ascii = True
        allow_nan = True
    elif domain in _ASCII_LEGACY_DOMAINS:
        default = None
        ensure_ascii = True
        allow_nan = True
    else:
        raise CanonicalSerializationError(
            CanonicalErrorCode.LEGACY_DOMAIN_UNSUPPORTED,
            f"no legacy profile for domain: {domain}",
        )
    return json.dumps(
        value,
        ensure_ascii=ensure_ascii,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=allow_nan,
        default=default,
    ).encode("utf-8")


def _legacy_read_model_default(value: object) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise CanonicalSerializationError(
                CanonicalErrorCode.NAIVE_DATETIME,
                "naive datetime rejected from frozen artifact",
            )
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, date | Decimal):
        return str(value)
    raise TypeError(f"unsupported frozen artifact value: {type(value).__name__}")


def _legacy_stage7i_supervision_default(value: object) -> str:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return str(value)


def _normalize_v2(value: object) -> Any:
    if value is None or isinstance(value, bool | int):
        return value
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CanonicalSerializationError(
                CanonicalErrorCode.NON_FINITE_FLOAT,
                "NaN and Infinity are forbidden",
            )
        if value == 0.0:
            value = 0.0
        return {"$w2_float": struct.pack(">d", value).hex()}
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise CanonicalSerializationError(
                CanonicalErrorCode.NON_FINITE_DECIMAL,
                "non-finite Decimal is forbidden",
            )
        return {"$w2_decimal": _decimal_text(value)}
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise CanonicalSerializationError(
                CanonicalErrorCode.NAIVE_DATETIME,
                "naive datetime is forbidden",
            )
        utc = value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
        return {"$w2_datetime": utc}
    if isinstance(value, date):
        return {"$w2_date": value.isoformat()}
    if isinstance(value, bytes):
        encoded = base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")
        return {"$w2_bytes": encoded}
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonicalSerializationError(
                    CanonicalErrorCode.NON_STRING_KEY,
                    "object keys must be strings",
                )
            normalized_key = unicodedata.normalize("NFC", key)
            if normalized_key in _RESERVED_TAGS:
                raise CanonicalSerializationError(
                    CanonicalErrorCode.RESERVED_TAG,
                    f"reserved canonical key: {normalized_key}",
                )
            if normalized_key in normalized:
                raise CanonicalSerializationError(
                    CanonicalErrorCode.UNICODE_KEY_COLLISION,
                    "Unicode normalization produced a duplicate key",
                )
            normalized[normalized_key] = _normalize_v2(item)
        return normalized
    if isinstance(value, list | tuple):
        return [_normalize_v2(item) for item in value]
    raise CanonicalSerializationError(
        CanonicalErrorCode.UNSUPPORTED_TYPE,
        f"unsupported canonical type: {type(value).__name__}",
    )


def _decimal_text(value: Decimal) -> str:
    if value.is_zero():
        return "0"
    sign, digits, exponent = value.as_tuple()
    if not isinstance(exponent, int):
        raise CanonicalSerializationError(
            CanonicalErrorCode.NON_FINITE_DECIMAL,
            "non-finite Decimal is forbidden",
        )
    coefficient = list(digits)
    while coefficient[-1] == 0:
        coefficient.pop()
        exponent += 1
    text = "".join(str(digit) for digit in coefficient)
    if exponent >= 0:
        text += "0" * exponent
    else:
        point = len(text) + exponent
        text = (
            f"{text[:point]}.{text[point:]}"
            if point > 0
            else f"0.{('0' * -point)}{text}"
        )
    return f"-{text}" if sign else text
