"""Reserved item-level scope contract; runtime readers remain kickoff-based."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from typing import Any

from w2.domain.canonical_serialization import HashDomain, canonical_sha256

RAW_FIXTURE_SCOPE_POLICY_VERSION = "w2.raw_fixture_scope.v1"


class RawFixtureScope(StrEnum):
    LIVE_DISCOVERY = "LIVE_DISCOVERY"
    HISTORICAL_TRAINING = "HISTORICAL_TRAINING"
    CONTROLLED_AUDIT = "CONTROLLED_AUDIT"


def raw_fixture_request_identity(*, endpoint: str, params: Mapping[str, Any]) -> str:
    return canonical_sha256(
        {
            "endpoint": str(endpoint),
            "parameters": {str(key): str(value) for key, value in sorted(params.items())},
        },
        domain=HashDomain.FUTURE_REFRESH_REQUEST_PARAMETERS,
    )


def raw_fixture_scope_membership_contract(
    *,
    raw_payload_sha256: str,
    provider_fixture_id: str,
    source_scope: RawFixtureScope | str,
    request_identity: str,
    classified_at: datetime,
    provider_league_id: str | None = None,
    kickoff_utc: datetime | None = None,
    scope_policy_version: str = RAW_FIXTURE_SCOPE_POLICY_VERSION,
) -> dict[str, Any]:
    scope = RawFixtureScope(str(source_scope))
    identity = {
        "raw_payload_sha256": str(raw_payload_sha256),
        "provider_fixture_id": str(provider_fixture_id),
        "scope_policy_version": str(scope_policy_version),
    }
    return {
        **identity,
        "source_scope": scope.value,
        "request_identity": str(request_identity),
        "classified_at": classified_at,
        "provider_league_id": provider_league_id,
        "kickoff_utc": kickoff_utc,
        "membership_hash": canonical_sha256(
            identity,
            domain=HashDomain.FUTURE_REFRESH_EVIDENCE,
        ),
    }
