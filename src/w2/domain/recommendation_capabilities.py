from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "w2.recommendation_capabilities.v1"
REQUIRED_CAPABILITIES = frozenset(
    {
        "analysis_ah",
        "analysis_ou",
        "formal_ah",
        "formal_ou",
        "lineup_confirmation_gate",
        "lineup_identity_enrichment",
        "lineup_value_enrichment",
        "lineup_numeric_adjustment_ah",
        "lineup_numeric_adjustment_ou",
        "recommendation_lock",
        "official_performance_reporting",
        "production_recommendation",
    }
)


class CapabilityManifestError(ValueError):
    pass


class CapabilityImplementation(StrEnum):
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    CODE_PRESENT = "CODE_PRESENT"
    CONTRACT_VERIFIED = "CONTRACT_VERIFIED"
    LOCALLY_VERIFIED = "LOCALLY_VERIFIED"
    ISOLATED_RUNTIME_VERIFIED = "ISOLATED_RUNTIME_VERIFIED"
    STAGING_CANARY_PASSED = "STAGING_CANARY_PASSED"
    FEATURE_ENABLED = "FEATURE_ENABLED"
    PUBLICLY_AVAILABLE = "PUBLICLY_AVAILABLE"
    PRODUCTION_ENABLED = "PRODUCTION_ENABLED"


@dataclass(frozen=True, kw_only=True)
class RecommendationCapability:
    name: str
    implementation: CapabilityImplementation
    contract_verified: bool
    locally_verified: bool
    isolated_runtime_verified: bool
    staging_canary_passed: bool
    feature_enabled: bool
    publicly_available: bool
    production_enabled: bool
    market_scope: tuple[str, ...]
    evidence_status: str | None = None

    def public_dict(self) -> dict[str, Any]:
        return {
            "implementation": self.implementation.value,
            "contract_verified": self.contract_verified,
            "locally_verified": self.locally_verified,
            "isolated_runtime_verified": self.isolated_runtime_verified,
            "staging_canary_passed": self.staging_canary_passed,
            "feature_enabled": self.feature_enabled,
            "publicly_available": self.publicly_available,
            "production_enabled": self.production_enabled,
            "market_scope": list(self.market_scope),
            "evidence_status": self.evidence_status,
        }


@dataclass(frozen=True, kw_only=True)
class RecommendationCapabilityManifest:
    schema_version: str
    sha256: str
    capabilities: dict[str, RecommendationCapability]

    def capability(self, name: str) -> RecommendationCapability:
        try:
            return self.capabilities[name]
        except KeyError as exc:
            raise CapabilityManifestError(f"missing required capability: {name}") from exc

    def public_summary(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "sha256": self.sha256,
            "capabilities": {
                name: self.capabilities[name].public_dict() for name in sorted(self.capabilities)
            },
        }


def default_manifest_path() -> Path:
    return (
        Path(__file__).resolve().parents[3]
        / "config"
        / "capabilities"
        / "recommendation_capabilities.v1.json"
    )


def load_recommendation_capability_manifest(
    path: Path | None = None,
) -> RecommendationCapabilityManifest:
    resolved_path = path or default_manifest_path()
    try:
        raw = resolved_path.read_bytes()
    except OSError as exc:
        raise CapabilityManifestError(
            f"capability manifest is unavailable: {resolved_path}"
        ) from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CapabilityManifestError("capability manifest is not valid JSON") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        raise CapabilityManifestError("capability manifest schema is incompatible")
    raw_capabilities = payload.get("capabilities")
    if not isinstance(raw_capabilities, dict):
        raise CapabilityManifestError("capability manifest capabilities must be an object")
    if set(raw_capabilities) != REQUIRED_CAPABILITIES:
        missing = sorted(REQUIRED_CAPABILITIES - set(raw_capabilities))
        unknown = sorted(set(raw_capabilities) - REQUIRED_CAPABILITIES)
        raise CapabilityManifestError(
            f"capability manifest entries mismatch: missing={missing}, unknown={unknown}"
        )
    capabilities = {
        name: _capability_from_mapping(name, raw_capabilities[name])
        for name in sorted(REQUIRED_CAPABILITIES)
    }
    return RecommendationCapabilityManifest(
        schema_version=SCHEMA_VERSION,
        sha256=hashlib.sha256(raw).hexdigest(),
        capabilities=capabilities,
    )


def _capability_from_mapping(name: str, raw: object) -> RecommendationCapability:
    if not isinstance(raw, dict):
        raise CapabilityManifestError(f"capability {name} must be an object")
    try:
        implementation = CapabilityImplementation(str(raw["implementation"]))
        verified = {
            field: _required_bool(raw, field)
            for field in (
                "contract_verified",
                "locally_verified",
                "isolated_runtime_verified",
                "staging_canary_passed",
                "feature_enabled",
                "publicly_available",
                "production_enabled",
            )
        }
    except KeyError as exc:
        raise CapabilityManifestError(f"capability {name} is missing {exc.args[0]}") from exc
    except ValueError as exc:
        raise CapabilityManifestError(f"capability {name} has invalid implementation") from exc
    scope = raw.get("market_scope", [])
    if not isinstance(scope, list) or not all(isinstance(item, str) for item in scope):
        raise CapabilityManifestError(f"capability {name} market_scope must be a string list")
    if verified["publicly_available"] and not verified["feature_enabled"]:
        raise CapabilityManifestError(f"capability {name} is public while feature is disabled")
    if verified["production_enabled"] and not verified["publicly_available"]:
        raise CapabilityManifestError(f"capability {name} is production enabled while not public")
    if implementation is CapabilityImplementation.NOT_IMPLEMENTED and any(
        verified[field]
        for field in ("feature_enabled", "publicly_available", "production_enabled")
    ):
        raise CapabilityManifestError(f"unimplemented capability {name} cannot be enabled")
    evidence_status = raw.get("evidence_status")
    if evidence_status is not None and not isinstance(evidence_status, str):
        raise CapabilityManifestError(f"capability {name} evidence_status must be a string or null")
    return RecommendationCapability(
        name=name,
        implementation=implementation,
        market_scope=tuple(scope),
        evidence_status=evidence_status,
        **verified,
    )


def _required_bool(raw: dict[str, object], field: str) -> bool:
    value = raw[field]
    if not isinstance(value, bool):
        raise CapabilityManifestError(f"capability field {field} must be boolean")
    return value
