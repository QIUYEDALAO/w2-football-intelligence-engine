"""Independent oracle for W2 canonical serialization.

Authored from ADR-0019 and the v2 oracle vector schema only. This module never
imports the production serializer and never reuses its code. The JSON encoder
below is written from scratch so that expected bytes do not depend on a
language runtime's float formatter, decimal context or json module defaults.
"""

from __future__ import annotations

import base64
import hashlib
import struct
import unicodedata
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

V2 = "w2.canonical-json.v2"
V1 = "w2.canonical-json.v1"

# ADR-0019 names the five emitted tags; the oracle vector schema additionally
# requires an unemitted key such as "$w2_type" to be rejected, so the whole
# "$w2_" prefix namespace is treated as reserved.
RESERVED_TAG_PREFIX = "$w2_"
EMITTED_TAGS = (
    "$w2_float",
    "$w2_decimal",
    "$w2_date",
    "$w2_datetime",
    "$w2_bytes",
)

# Frozen v1 domain profiles (ADR-0019 legacy contract + SER-01 frozen inventory).
V1_PROFILES: dict[str, dict[str, Any]] = {
    "future_refresh.raw_payload": {"ensure_ascii": True, "allow_nan": True, "default": None},
    "stage7i_supervision.event": {"ensure_ascii": True, "allow_nan": True, "default": "str_utc"},
    "prematch_read_model.generic": {"ensure_ascii": False, "allow_nan": True, "default": "typed"},
    "eval_02b.pair_identity": {"ensure_ascii": False, "allow_nan": False, "default": None},
}

ESCAPES = {
    0x08: "\\b",
    0x09: "\\t",
    0x0A: "\\n",
    0x0C: "\\f",
    0x0D: "\\r",
}


class OracleError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class BootstrapSeed:
    payload: bytes
    seed_hash: str
    seed: int


def nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def encode_string(text: str, *, ensure_ascii: bool) -> str:
    out = ['"']
    for char in text:
        point = ord(char)
        if char == '"':
            out.append('\\"')
        elif char == "\\":
            out.append("\\\\")
        elif point in ESCAPES:
            out.append(ESCAPES[point])
        elif point < 0x20:
            out.append(f"\\u{point:04x}")
        elif ensure_ascii and point > 0x7E:
            if point > 0xFFFF:
                offset = point - 0x10000
                high = 0xD800 + (offset >> 10)
                low = 0xDC00 + (offset & 0x3FF)
                out.append(f"\\u{high:04x}\\u{low:04x}")
            else:
                out.append(f"\\u{point:04x}")
        else:
            out.append(char)
    out.append('"')
    return "".join(out)


def decimal_text(value: Decimal) -> str:
    """Exponent-free text derived from sign, coefficient digits and exponent."""
    sign, digits, exponent = value.as_tuple()
    if not isinstance(exponent, int):
        raise OracleError("NON_FINITE_DECIMAL")
    body = "".join(str(digit) for digit in digits)
    if exponent >= 0:
        integer, fraction = body + "0" * exponent, ""
    else:
        cut = len(body) + exponent
        if cut > 0:
            integer, fraction = body[:cut], body[cut:]
        else:
            integer, fraction = "", "0" * (-cut) + body
    fraction = fraction.rstrip("0")
    integer = integer.lstrip("0") or "0"
    text = f"{integer}.{fraction}" if fraction else integer
    if sign and text != "0":
        text = "-" + text
    return text


def float_hex(value: float) -> str:
    packed = struct.pack(">d", value)
    exponent = (packed[0] & 0x7F) << 4 | (packed[1] >> 4)
    mantissa = int.from_bytes(packed, "big") & ((1 << 52) - 1)
    if exponent == 0x7FF:
        raise OracleError("NON_FINITE_FLOAT")
    if exponent == 0 and mantissa == 0:
        return "0" * 16
    return packed.hex()


def datetime_text(value: datetime) -> str:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise OracleError("NAIVE_DATETIME")
    moment = value.astimezone(UTC)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond:06d}Z"


def _tagged(tag: str, text: str, *, ensure_ascii: bool) -> str:
    return "{" + encode_string(tag, ensure_ascii=ensure_ascii) + ":" + encode_string(
        text, ensure_ascii=ensure_ascii
    ) + "}"


def _utc_isoformat_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _legacy_default(value: object, profile: str) -> str | None:
    """Reproduce a frozen v1 default hook. Returns replacement text or None."""
    if profile == "typed":
        # ADR-0019 frozen read-model hook: Decimal and date keep str(); aware
        # datetime becomes UTC isoformat with "+00:00" replaced by "Z"; naive
        # datetime is rejected.
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, datetime):
            if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
                raise OracleError("NAIVE_DATETIME")
            return _utc_isoformat_z(value)
        if isinstance(value, date):
            return str(value)
        return None
    if profile == "str_utc":
        # ADR-0019 frozen Stage7I hook: aware datetime becomes UTC isoformat
        # with "Z"; every other unsupported object becomes str(value).
        if isinstance(value, datetime) and value.tzinfo is not None:
            return _utc_isoformat_z(value)
        return str(value)
    return None


def encode(value: object, *, version: str, domain: str) -> str:
    if version == V2:
        return _encode_v2(value, ensure_ascii=False)
    if version == V1:
        profile = V1_PROFILES.get(domain)
        if profile is None:
            raise OracleError("LEGACY_DOMAIN_UNSUPPORTED")
        return _encode_v1(value, profile=profile)
    raise OracleError("UNSUPPORTED_SERIALIZER_VERSION")


def _sorted_entries(
    mapping: dict[Any, Any], *, normalize: bool, reserve_prefix: bool = True
) -> list[tuple[str, object]]:
    seen: dict[str, str] = {}
    entries: list[tuple[str, object]] = []
    for raw_key, item in mapping.items():
        if not isinstance(raw_key, str):
            raise OracleError("NON_STRING_KEY")
        key = nfc(raw_key) if normalize else raw_key
        if reserve_prefix and key.startswith(RESERVED_TAG_PREFIX):
            raise OracleError("RESERVED_TAG")
        if key in seen:
            raise OracleError("UNICODE_KEY_COLLISION")
        seen[key] = raw_key
        entries.append((key, item))
    entries.sort(key=lambda pair: [ord(char) for char in pair[0]])
    return entries


def _encode_v2(value: object, *, ensure_ascii: bool) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return _tagged("$w2_float", float_hex(value), ensure_ascii=ensure_ascii)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise OracleError("NON_FINITE_DECIMAL")
        return _tagged("$w2_decimal", decimal_text(value), ensure_ascii=ensure_ascii)
    if isinstance(value, datetime):
        return _tagged("$w2_datetime", datetime_text(value), ensure_ascii=ensure_ascii)
    if isinstance(value, date):
        return _tagged("$w2_date", value.isoformat(), ensure_ascii=ensure_ascii)
    if isinstance(value, bytes):
        text = base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")
        return _tagged("$w2_bytes", text, ensure_ascii=ensure_ascii)
    if isinstance(value, str):
        return encode_string(nfc(value), ensure_ascii=ensure_ascii)
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(
            _encode_v2(item, ensure_ascii=ensure_ascii) for item in value
        ) + "]"
    if isinstance(value, dict):
        parts = [
            encode_string(key, ensure_ascii=ensure_ascii)
            + ":"
            + _encode_v2(item, ensure_ascii=ensure_ascii)
            for key, item in _sorted_entries(value, normalize=True)
        ]
        return "{" + ",".join(parts) + "}"
    raise OracleError("UNSUPPORTED_TYPE")


def _encode_v1(value: object, *, profile: dict[str, Any]) -> str:
    ensure_ascii = bool(profile["ensure_ascii"])
    allow_nan = bool(profile["allow_nan"])
    hook = profile["default"]

    def emit(node: object) -> str:
        if node is None:
            return "null"
        if isinstance(node, bool):
            return "true" if node else "false"
        if isinstance(node, int):
            return str(node)
        if isinstance(node, float):
            if node != node or node in (float("inf"), float("-inf")):
                if not allow_nan:
                    raise OracleError("NON_FINITE_FLOAT")
                return "NaN" if node != node else ("Infinity" if node > 0 else "-Infinity")
            return repr(node)
        if isinstance(node, str):
            return encode_string(node, ensure_ascii=ensure_ascii)
        if isinstance(node, (list, tuple)):
            return "[" + ",".join(emit(item) for item in node) + "]"
        if isinstance(node, dict):
            parts = [
                encode_string(key, ensure_ascii=ensure_ascii) + ":" + emit(item)
                for key, item in _sorted_entries(
                    node, normalize=False, reserve_prefix=False
                )
            ]
            return "{" + ",".join(parts) + "}"
        replacement = _legacy_default(node, hook) if hook else None
        if replacement is None:
            raise OracleError("UNSUPPORTED_TYPE")
        return encode_string(replacement, ensure_ascii=ensure_ascii)

    return emit(value)


def canonical_bytes(value: object, *, version: str, domain: str) -> bytes:
    return encode(value, version=version, domain=domain).encode("utf-8")


def canonical_sha256(value: object, *, version: str, domain: str) -> str:
    return hashlib.sha256(canonical_bytes(value, version=version, domain=domain)).hexdigest()


def bootstrap_seed(contract_version: str, hashes: list[str]) -> BootstrapSeed:
    if not contract_version:
        raise OracleError("BOOTSTRAP_CONTRACT_VERSION_REQUIRED")
    for item in hashes:
        if len(item) != 64 or any(char not in "0123456789abcdef" for char in item):
            raise OracleError("INVALID_PAIR_IDENTITY_HASH")
    payload = canonical_bytes(
        {
            "contract_version": contract_version,
            "validation_pair_identity_hashes": sorted(hashes),
        },
        version=V2,
        domain="eval_02b.bootstrap_seed",
    )
    digest = hashlib.sha256(payload).hexdigest()
    return BootstrapSeed(
        payload=payload,
        seed_hash=digest,
        seed=int.from_bytes(bytes.fromhex(digest)[:8], "big", signed=False),
    )
