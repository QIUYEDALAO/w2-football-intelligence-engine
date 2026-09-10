"""F1R-B: capture identity for the sources a factor actually consumed.

A factor observation is only auditable if it can name the exact source records
that produced it, prove what those records contained, and prove when the source
observed each of them. This module builds that binding.

Three properties are load-bearing and each has a test:

1. *Order independence.* The consumed set is a set. Reading the same rows in a
   different order must produce the same capture identity, so records are
   sorted by their own id before hashing.
2. *Consumed-only sensitivity.* Changing the content, identity, version or
   observed time of any consumed record changes the capture hash, and therefore
   the observation identity. Changing a record the factor never consumed
   changes nothing, because it was never in the manifest.
3. *Synthetic is never silent.* A fixture record is marked in the record, in
   the capture id and in the manifest, and the production wiring refuses a
   manifest that carries one.

Hashing goes through `w2.domain.canonical_serialization` and `w2.canonical-json.v2`.
No second serializer and no second hash writer exists here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from w2.domain.canonical_serialization import (
    CURRENT_SERIALIZER_VERSION,
    HashDomain,
    canonical_sha256,
)

CAPTURE_CONTRACT = "w2.f1r_b_source_capture.v1"
SERIALIZER_VERSION = str(CURRENT_SERIALIZER_VERSION)
# The same domain the F1P contract reuses, for the same reason: no quant hash
# domain exists yet and adding one would edit a production module. The domain
# string is written into the preimage explicitly, so introducing a quant domain
# later is a visible identity change rather than a silent one.
HASH_DOMAIN = HashDomain.FUTURE_REFRESH_EVIDENCE

PRODUCTION_SET_PREFIX = "w2.consumed_source_set.v1"
SYNTHETIC_SET_PREFIX = "w2.synthetic_source_set.v1"

_HEX64 = frozenset("0123456789abcdef")


class CaptureIdentityError(ValueError):
    """A refusal, carrying the machine-readable code that caused it."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}:{detail}" if detail else code)
        self.code = code
        self.detail = detail


def require_hex64(value: object, *, field_name: str) -> str:
    """Lowercase 64-hex, or refuse. Uppercase is refused, not normalised."""
    if not isinstance(value, str) or not value:
        raise CaptureIdentityError("SOURCE_HASH_MISSING", field_name)
    if len(value) != 64:
        raise CaptureIdentityError("SOURCE_HASH_LENGTH_INVALID", f"{field_name}={len(value)}")
    if not set(value) <= _HEX64:
        raise CaptureIdentityError("SOURCE_HASH_NOT_LOWERCASE_HEX", f"{field_name}={value}")
    return value


def content_sha256(payload: Any) -> str:
    """Canonical hash of one source record's actually-consumed content."""
    return canonical_sha256(payload, domain=HASH_DOMAIN)


@dataclass(frozen=True, kw_only=True)
class ConsumedSourceRecord:
    """One production row a factor actually read.

    `observed_at_utc` is when the *source* observed the fact, never when the row
    was written and never the fixture kickoff. It is optional only because F3's
    evidence rule is a fixture event time rather than a source observation; a
    result-derived factor with a record missing it is refused upstream.
    """

    record_id: str
    content_sha256: str
    source_version: str
    observed_at_utc: str | None = None
    observed_time_semantics: str = "SOURCE_OBSERVED_AT"
    synthetic: bool = False

    def as_manifest_entry(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "content_sha256": self.content_sha256,
            "source_version": self.source_version,
            "observed_at_utc": self.observed_at_utc,
            "observed_time_semantics": self.observed_time_semantics,
            "synthetic": self.synthetic,
        }


@dataclass(frozen=True, kw_only=True)
class CaptureIdentity:
    """What one factor consumed, and the identity that binds it."""

    factor_id: str
    source_capture_id: str
    source_capture_sha256: str
    source_version: str
    record_ids: tuple[str, ...]
    observed_times: tuple[str, ...]
    synthetic: bool
    manifest: dict[str, Any]


def _validate(factor_id: str, records: list[ConsumedSourceRecord]) -> None:
    if not records:
        raise CaptureIdentityError("CONSUMED_SOURCE_SET_EMPTY", factor_id)
    seen: set[str] = set()
    for record in records:
        if not record.record_id.strip():
            raise CaptureIdentityError("SOURCE_RECORD_ID_MISSING", factor_id)
        if record.record_id in seen:
            raise CaptureIdentityError("SOURCE_RECORD_ID_DUPLICATE", record.record_id)
        seen.add(record.record_id)
        require_hex64(record.content_sha256,
                      field_name=f"{factor_id}:{record.record_id}.content_sha256")
        if not record.source_version.strip():
            raise CaptureIdentityError("SOURCE_VERSION_MISSING", record.record_id)


def capture_identity(
    factor_id: str, records: list[ConsumedSourceRecord]
) -> CaptureIdentity:
    """Bind a factor to the exact source set it consumed."""
    _validate(factor_id, records)
    ordered = sorted(records, key=lambda record: record.record_id)
    entries = [record.as_manifest_entry() for record in ordered]
    versions = sorted({record.source_version for record in ordered})
    synthetic = any(record.synthetic for record in ordered)

    manifest = {
        "contract": CAPTURE_CONTRACT,
        "hash_domain": str(HASH_DOMAIN),
        "serializer_version": SERIALIZER_VERSION,
        "factor_id": factor_id,
        "records": entries,
    }
    capture_sha256 = canonical_sha256(manifest, domain=HASH_DOMAIN)
    # The capture id names the consumed *set*. Its preimage is the record ids
    # alone, so it stays stable while content changes move only the content
    # hash, and it changes as soon as a different set of rows is read.
    set_digest = canonical_sha256(
        {
            "contract": CAPTURE_CONTRACT,
            "factor_id": factor_id,
            "record_ids": [record.record_id for record in ordered],
        },
        domain=HASH_DOMAIN,
    )
    prefix = SYNTHETIC_SET_PREFIX if synthetic else PRODUCTION_SET_PREFIX
    return CaptureIdentity(
        factor_id=factor_id,
        source_capture_id=f"{prefix}:{set_digest}",
        source_capture_sha256=capture_sha256,
        # One consumed set may legitimately span one source version only; a
        # mixed set is reported verbatim rather than collapsed to the newest.
        source_version=versions[0] if len(versions) == 1 else "MIXED:" + ",".join(versions),
        record_ids=tuple(record.record_id for record in ordered),
        observed_times=tuple(
            record.observed_at_utc for record in ordered
            if record.observed_at_utc is not None
        ),
        synthetic=synthetic,
        manifest=manifest,
    )
