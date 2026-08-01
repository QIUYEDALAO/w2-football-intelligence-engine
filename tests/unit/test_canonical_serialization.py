from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from w2.domain.canonical_serialization import (
    CURRENT_SERIALIZER_VERSION,
    CanonicalSerializationError,
    HashDomain,
    SerializerVersion,
    canonical_bytes,
    canonical_sha256,
    eval_02b_bootstrap_seed,
    prepare_hash_migration,
    verify_sha256,
)


def test_v2_is_utf8_sorted_compact_and_unicode_nfc() -> None:
    composed = {"主队": "上海海港", "name": "Café"}
    decomposed = {"主队": "上海海港", "name": "Cafe\u0301"}

    encoded = canonical_bytes(composed, domain=HashDomain.EVAL_02B_PAIR_IDENTITY)

    assert encoded == canonical_bytes(
        decomposed, domain=HashDomain.EVAL_02B_PAIR_IDENTITY
    )
    assert b" " not in encoded
    assert b"\\u" not in encoded
    assert encoded.decode("utf-8").startswith('{"name":')


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_v2_rejects_non_finite_float(value: float) -> None:
    with pytest.raises(CanonicalSerializationError, match="NaN and Infinity"):
        canonical_bytes(value, domain=HashDomain.EVAL_02B_PAIR_IDENTITY)


@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("Infinity")])
def test_v2_rejects_non_finite_decimal(value: Decimal) -> None:
    with pytest.raises(CanonicalSerializationError, match="non-finite Decimal"):
        canonical_bytes(value, domain=HashDomain.EVAL_02B_PAIR_IDENTITY)


def test_v2_numbers_preserve_types_and_normalize_negative_zero() -> None:
    encoded = canonical_bytes(
        {"int": 1, "float": 1.0, "negative_zero": -0.0, "decimal": Decimal("1.2300")},
        domain=HashDomain.EVAL_02B_PAIR_IDENTITY,
    )
    value = json.loads(encoded)

    assert value == {
        "decimal": {"$w2_decimal": "1.23"},
        "float": {"$w2_float": "1"},
        "int": 1,
        "negative_zero": {"$w2_float": "0"},
    }


def test_v2_date_datetime_and_bytes_are_typed() -> None:
    encoded = canonical_bytes(
        {
            "bytes": b"\x00\xff",
            "date": date(2026, 8, 1),
            "datetime": datetime(
                2026, 8, 1, 10, 30, 15, 123456, tzinfo=timezone(timedelta(hours=8))
            ),
        },
        domain=HashDomain.EVAL_02B_PAIR_IDENTITY,
    )
    value = json.loads(encoded)

    assert value["bytes"] == {"$w2_bytes": "AP8"}
    assert value["date"] == {"$w2_date": "2026-08-01"}
    assert value["datetime"] == {"$w2_datetime": "2026-08-01T02:30:15.123456Z"}


@pytest.mark.parametrize(
    "value, message",
    [
        (datetime(2026, 8, 1), "naive datetime"),
        ({1: "value"}, "object keys must be strings"),
        ({"$w2_float": "1"}, "reserved canonical key"),
        ({"é": 1, "e\u0301": 2}, "duplicate key"),
        ({1, 2}, "unsupported canonical type"),
    ],
)
def test_v2_rejects_ambiguous_or_unsupported_values(value: object, message: str) -> None:
    with pytest.raises(CanonicalSerializationError, match=message):
        canonical_bytes(value, domain=HashDomain.EVAL_02B_PAIR_IDENTITY)


def test_legacy_profiles_reproduce_existing_bytes() -> None:
    payload = {"home_cn": "上海海港", "away_cn": "北京国安"}
    ascii_expected = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    utf8_expected = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")

    assert canonical_bytes(
        payload,
        domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD,
        version=SerializerVersion.LEGACY_V1,
    ) == ascii_expected
    assert canonical_bytes(
        payload,
        domain=HashDomain.PREMATCH_READ_MODEL_GENERIC,
        version=SerializerVersion.LEGACY_V1,
    ) == utf8_expected


def test_migration_and_rollback_preserve_historical_digest() -> None:
    payload = {"home_cn": "上海海港", "price": 1.25}
    historical = hashlib.sha256(
        json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
    ).hexdigest()

    migration = prepare_hash_migration(
        payload, historical, domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD
    )

    assert migration.historical.sha256 == historical
    assert migration.historical.serializer_version is SerializerVersion.LEGACY_V1
    assert migration.replacement.serializer_version is CURRENT_SERIALIZER_VERSION
    assert migration.rollback() == migration.historical
    assert payload == {"home_cn": "上海海港", "price": 1.25}


def test_missing_version_is_legacy_only_and_v2_is_explicit() -> None:
    payload = {"home_cn": "上海海港"}
    legacy = canonical_sha256(
        payload,
        domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD,
        version=SerializerVersion.LEGACY_V1,
    )
    current = canonical_sha256(payload, domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD)

    assert verify_sha256(
        payload,
        legacy,
        domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD,
        declared_version=None,
    ) is not None
    assert (
        verify_sha256(
            payload,
            current,
            domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD,
            declared_version=None,
        )
        is None
    )
    assert verify_sha256(
        payload,
        current,
        domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD,
        declared_version=SerializerVersion.V2,
    ) is not None


def test_bootstrap_seed_interface_is_order_independent() -> None:
    hashes = ["b" * 64, "a" * 64]

    first = eval_02b_bootstrap_seed(hashes, contract_version="w2.eval_02b_gate.v1")
    second = eval_02b_bootstrap_seed(
        list(reversed(hashes)), contract_version="w2.eval_02b_gate.v1"
    )

    assert first == second
    assert 0 <= first < 2**64


@pytest.mark.parametrize(
    "hashes, contract_version",
    [(["not-a-hash"], "w2.eval_02b_gate.v1"), (["a" * 64], ""), (["A" * 64], "v1")],
)
def test_bootstrap_seed_interface_rejects_invalid_identity(
    hashes: list[str], contract_version: str
) -> None:
    with pytest.raises(CanonicalSerializationError):
        eval_02b_bootstrap_seed(hashes, contract_version=contract_version)
