from __future__ import annotations

import json

import pytest

from w2.domain.canonical_serialization import canonical_bytes
from w2.ingestion.xg_retention import (
    XG_RETENTION_HASH_DOMAIN,
    XgRetentionError,
    XgRetentionHardeningService,
    _guarded_timestamp_updates,
    _restore_canonical_json,
    _state_hash,
)


def test_guarded_timestamp_repair_allows_only_registered_time_field() -> None:
    current = {"row-1": {"id": "row-1", "captured_at": "old", "xg_for": 1.2}}
    expected = {"row-1": {"id": "row-1", "captured_at": "raw", "xg_for": 1.2}}

    assert _guarded_timestamp_updates(
        current,
        expected,
        allowed_field="captured_at",
    ) == ["row-1"]


def test_guarded_timestamp_repair_rejects_value_drift() -> None:
    current = {"row-1": {"id": "row-1", "captured_at": "old", "xg_for": 1.2}}
    expected = {"row-1": {"id": "row-1", "captured_at": "raw", "xg_for": 2.1}}

    with pytest.raises(XgRetentionError, match="XG_RETENTION_NON_TIMESTAMP_DRIFT"):
        _guarded_timestamp_updates(
            current,
            expected,
            allowed_field="captured_at",
        )


def test_repair_apply_requires_backup_before_repository_access() -> None:
    service = XgRetentionHardeningService.__new__(XgRetentionHardeningService)

    with pytest.raises(XgRetentionError, match="XG_RETENTION_REPAIR_BACKUP_REQUIRED"):
        service.repair_derived_lineage(dry_run=False, write_db=True)


def test_repair_rejects_write_during_dry_run() -> None:
    service = XgRetentionHardeningService.__new__(XgRetentionHardeningService)

    with pytest.raises(XgRetentionError, match="write_db requires dry_run=false"):
        service.repair_derived_lineage(dry_run=True, write_db=True)


def test_backup_roundtrip_preserves_float_hash() -> None:
    state = {"rolling_xg_for": 1.25, "match_count": 4}

    restored = _restore_canonical_json(
        json.loads(canonical_bytes(state, domain=XG_RETENTION_HASH_DOMAIN))
    )

    assert _state_hash(restored) == _state_hash(state)
