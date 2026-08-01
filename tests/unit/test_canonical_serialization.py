from __future__ import annotations

import hashlib
import json
import math
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, localcontext

import pytest

from w2.domain.canonical_serialization import (
    CURRENT_SERIALIZER_VERSION,
    HASH_DOMAIN_IN_PREIMAGE,
    SERIALIZER_VERSION_IN_PREIMAGE,
    CanonicalErrorCode,
    CanonicalSerializationError,
    HashDomain,
    SerializerVersion,
    VersionedDigest,
    canonical_bytes,
    canonical_sha256,
    eval_02b_bootstrap_seed,
    prepare_hash_migration,
    verify_sha256,
    verify_versioned_digest,
)


def test_v2_is_utf8_sorted_compact_and_unicode_nfc() -> None:
    composed = {"主队": "上海海港", "name": "Café"}
    decomposed = {"主队": "上海海港", "name": "Cafe\u0301"}

    encoded = canonical_bytes(composed, domain=HashDomain.EVAL_02B_PAIR_IDENTITY)

    assert encoded == canonical_bytes(decomposed, domain=HashDomain.EVAL_02B_PAIR_IDENTITY)
    assert b" " not in encoded
    assert b"\\u" not in encoded
    assert encoded.decode("utf-8").startswith('{"name":')


def test_v2_orders_nfc_keys_by_unicode_code_point() -> None:
    encoded = canonical_bytes(
        {"\U00010000": "astral", "e\u0301": "nfc", "\ue000": "bmp"},
        domain=HashDomain.EVAL_02B_PAIR_IDENTITY,
    )

    assert encoded == '{"é":"nfc","\ue000":"bmp","\U00010000":"astral"}'.encode()


def test_v2_json_escaping_is_exact_and_non_ascii_stays_utf8() -> None:
    encoded = canonical_bytes(
        {
            "quote": '"',
            "backslash": "\\",
            "control": "\x00\b\t\n\f\r\x1f",
            "non_ascii": "上海é",
        },
        domain=HashDomain.EVAL_02B_PAIR_IDENTITY,
    )

    assert (
        encoded
        == (
            '{"backslash":"\\\\","control":"\\u0000\\b\\t\\n\\f\\r\\u001f",'
            '"non_ascii":"上海é","quote":"\\""}'
        ).encode()
    )


def test_v2_preserves_arbitrary_precision_integer() -> None:
    value = 10**80 + 1
    assert canonical_bytes(value, domain=HashDomain.EVAL_02B_PAIR_IDENTITY) == str(value).encode()


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_v2_rejects_non_finite_float(value: float) -> None:
    with pytest.raises(CanonicalSerializationError, match="NaN and Infinity") as error:
        canonical_bytes(value, domain=HashDomain.EVAL_02B_PAIR_IDENTITY)
    assert error.value.code is CanonicalErrorCode.NON_FINITE_FLOAT


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
        "float": {"$w2_float": "3ff0000000000000"},
        "int": 1,
        "negative_zero": {"$w2_float": "0000000000000000"},
    }


def test_decimal_is_exact_and_independent_of_decimal_context() -> None:
    values = (
        Decimal("123456789012345678901234567890.123400"),
        Decimal("0.0000000000000000000000000000123400"),
        Decimal("1E+100"),
    )
    outputs: list[list[bytes]] = []
    for precision in (5, 28, 50):
        with localcontext() as context:
            context.prec = precision
            outputs.append(
                [
                    canonical_bytes(value, domain=HashDomain.EVAL_02B_PAIR_IDENTITY)
                    for value in values
                ]
            )

    assert outputs[0] == outputs[1] == outputs[2]
    assert json.loads(outputs[0][0]) == {"$w2_decimal": "123456789012345678901234567890.1234"}
    assert json.loads(outputs[0][1]) == {"$w2_decimal": "0.00000000000000000000000000001234"}
    assert json.loads(outputs[0][2]) == {"$w2_decimal": "1" + "0" * 100}


@pytest.mark.parametrize(
    "value, expected",
    [
        (0.0, "0000000000000000"),
        (-0.0, "0000000000000000"),
        (0.1, "3fb999999999999a"),
        (float.fromhex("0x0.0000000000001p-1022"), "0000000000000001"),
        (sys.float_info.max, "7fefffffffffffff"),
        (math.nextafter(1.0, 2.0), "3ff0000000000001"),
        (10.0, "4024000000000000"),
    ],
)
def test_float_uses_big_endian_binary64(value: float, expected: str) -> None:
    encoded = canonical_bytes(value, domain=HashDomain.EVAL_02B_PAIR_IDENTITY)
    assert json.loads(encoded) == {"$w2_float": expected}


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

    assert (
        canonical_bytes(
            payload,
            domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD,
            version=SerializerVersion.LEGACY_V1,
        )
        == ascii_expected
    )
    assert (
        canonical_bytes(
            payload,
            domain=HashDomain.PREMATCH_READ_MODEL_GENERIC,
            version=SerializerVersion.LEGACY_V1,
        )
        == utf8_expected
    )


def test_migration_and_rollback_preserve_historical_digest() -> None:
    payload = {"home_cn": "上海海港", "price": 1.25}
    historical_sha256 = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
            "utf-8"
        )
    ).hexdigest()
    historical = VersionedDigest(
        domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD,
        serializer_version=SerializerVersion.LEGACY_V1,
        sha256=historical_sha256,
    )

    migration = prepare_hash_migration(
        payload, historical, domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD
    )

    assert migration.historical == historical
    assert migration.historical.serializer_version is SerializerVersion.LEGACY_V1
    assert migration.replacement.serializer_version is CURRENT_SERIALIZER_VERSION
    assert migration.rollback() == migration.historical
    assert payload == {"home_cn": "上海海港", "price": 1.25}


@pytest.mark.parametrize(
    "stored_domain, stored_version",
    [
        (HashDomain.OUTCOME_LEDGER_PAYLOAD, SerializerVersion.LEGACY_V1),
        (HashDomain.FUTURE_REFRESH_RAW_PAYLOAD, SerializerVersion.V2),
    ],
)
def test_migration_rejects_stored_metadata_mismatch_without_overwrite(
    stored_domain: HashDomain, stored_version: SerializerVersion
) -> None:
    payload = {"home_cn": "上海海港"}
    stored = VersionedDigest(
        domain=stored_domain,
        serializer_version=stored_version,
        sha256="a" * 64,
    )

    with pytest.raises(CanonicalSerializationError) as error:
        prepare_hash_migration(
            payload,
            stored,
            domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD,
        )

    assert error.value.code is CanonicalErrorCode.HISTORICAL_METADATA_MISMATCH
    assert stored.sha256 == "a" * 64


def test_missing_version_is_legacy_only_and_v2_is_explicit() -> None:
    payload = {"home_cn": "上海海港"}
    legacy = canonical_sha256(
        payload,
        domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD,
        version=SerializerVersion.LEGACY_V1,
    )
    current = canonical_sha256(payload, domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD)

    assert (
        verify_sha256(
            payload,
            legacy,
            domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD,
            declared_version=None,
        )
        is not None
    )
    assert (
        verify_sha256(
            payload,
            current,
            domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD,
            declared_version=None,
        )
        is None
    )
    assert (
        verify_sha256(
            payload,
            current,
            domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD,
            declared_version=SerializerVersion.V2,
        )
        is not None
    )


def test_hash_domain_and_version_are_validated_metadata_not_preimage() -> None:
    payload = {"value": "same canonical bytes"}
    pair = VersionedDigest(
        domain=HashDomain.EVAL_02B_PAIR_IDENTITY,
        serializer_version=SerializerVersion.V2,
        sha256=canonical_sha256(payload, domain=HashDomain.EVAL_02B_PAIR_IDENTITY),
    )

    assert HASH_DOMAIN_IN_PREIMAGE is False
    assert SERIALIZER_VERSION_IN_PREIMAGE is False
    assert pair.sha256 == canonical_sha256(payload, domain=HashDomain.EVAL_02B_BOOTSTRAP_SEED)
    assert verify_versioned_digest(
        payload,
        pair,
        domain=HashDomain.EVAL_02B_PAIR_IDENTITY,
        serializer_version=SerializerVersion.V2,
    )
    assert not verify_versioned_digest(
        payload,
        pair,
        domain=HashDomain.EVAL_02B_BOOTSTRAP_SEED,
        serializer_version=SerializerVersion.V2,
    )


def test_bootstrap_seed_interface_is_order_independent() -> None:
    hashes = ["b" * 64, "a" * 64]

    first = eval_02b_bootstrap_seed(hashes, contract_version="w2.eval_02b_gate.v1")
    second = eval_02b_bootstrap_seed(list(reversed(hashes)), contract_version="w2.eval_02b_gate.v1")

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
