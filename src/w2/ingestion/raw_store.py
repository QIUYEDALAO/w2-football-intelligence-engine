from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any

from w2.domain.entities import RawPayloadReference


def canonical_payload_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def payload_sha256(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_payload_bytes(payload)).hexdigest()


@dataclass(frozen=True)
class StoredPayload:
    reference: RawPayloadReference
    payload: MappingProxyType[str, Any]


class RawPayloadStore:
    def __init__(self) -> None:
        self._records: dict[tuple[str, str, str], StoredPayload] = {}

    def save(
        self,
        *,
        provider: str,
        endpoint: str,
        payload: dict[str, Any],
        captured_at: datetime,
    ) -> StoredPayload:
        digest = payload_sha256(payload)
        object_uri = f"raw://{provider}/{endpoint}/{digest}.json"
        key = (provider, object_uri, digest)
        existing = self._records.get(key)
        if existing is not None:
            return existing
        reference = RawPayloadReference(
            provider=provider,
            object_uri=object_uri,
            sha256=digest,
            captured_at=captured_at,
            immutable=True,
        )
        stored = StoredPayload(reference=reference, payload=MappingProxyType(dict(payload)))
        self._records[key] = stored
        return stored

    def count(self) -> int:
        return len(self._records)
