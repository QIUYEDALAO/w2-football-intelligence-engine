"""Versioned factor lifecycle registry used by V3 projections."""

from __future__ import annotations

import json
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any

REGISTRY_SPECS = {
    "v1": (
        "w2.factor_registry.v1",
        Path("config/factors/factor_registry.v1.json"),
    ),
    "factor-model-v2": (
        "w2.factor_registry.factor-model-v2.v1",
        Path("config/factors/factor_registry.factor-model-v2.v1.json"),
    ),
}
VALID_LIFECYCLES = frozenset({"ACTIVE", "SHADOW", "EXPLANATION_ONLY", "GATE_ONLY", "RETIRED"})
V2_REQUIRED_FIELDS = frozenset(
    {
        "factor_id",
        "semantic_version",
        "lambda_channel",
        "raw_unit",
        "transform",
        "normalization_version",
        "minimum_sample",
        "missing_policy",
        "allowed_competitions",
        "numeric_effect_enabled",
    }
)
V2_LAMBDA_CHANNELS = frozenset({"NONE", "BASELINE", "RELATIVE", "TOTAL"})


@lru_cache(maxsize=2)
def load_factor_registry(version: str = "v1") -> dict[str, dict[str, Any]]:
    try:
        schema_version, relative_path = REGISTRY_SPECS[version]
    except KeyError as exc:
        raise ValueError("FACTOR_REGISTRY_VERSION_INVALID") from exc
    path = _registry_path(relative_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != schema_version:
        raise ValueError("FACTOR_REGISTRY_SCHEMA_INVALID")
    rows = payload.get("factors")
    if not isinstance(rows, list):
        raise ValueError("FACTOR_REGISTRY_FACTORS_INVALID")
    registry: dict[str, dict[str, Any]] = {}
    for raw in rows:
        if not isinstance(raw, Mapping):
            raise ValueError("FACTOR_REGISTRY_ENTRY_INVALID")
        factor_id = str(raw.get("factor_id") or "")
        lifecycle = str(raw.get("lifecycle") or "")
        roles = raw.get("roles")
        if not factor_id or factor_id in registry or lifecycle not in VALID_LIFECYCLES:
            raise ValueError("FACTOR_REGISTRY_ENTRY_CONFLICT")
        if not isinstance(roles, list) or not all(isinstance(role, str) for role in roles):
            raise ValueError("FACTOR_REGISTRY_ROLES_INVALID")
        if version == "factor-model-v2":
            if not V2_REQUIRED_FIELDS <= set(raw):
                raise ValueError("FACTOR_REGISTRY_V2_FIELDS_MISSING")
            if raw.get("numeric_effect_enabled") is not False:
                raise ValueError("FACTOR_REGISTRY_V2_NUMERIC_EFFECT_NOT_ADMITTED")
            if not isinstance(raw.get("allowed_competitions"), list):
                raise ValueError("FACTOR_REGISTRY_V2_COMPETITIONS_INVALID")
            if raw.get("lambda_channel") not in V2_LAMBDA_CHANNELS:
                raise ValueError("FACTOR_REGISTRY_V2_LAMBDA_CHANNEL_INVALID")
        registry[factor_id] = dict(raw)
    return registry


def factor_policy(factor_id: str) -> dict[str, Any]:
    entry = load_factor_registry().get(factor_id)
    if entry is None:
        return {
            "factor_id": factor_id,
            "lifecycle": "RETIRED",
            "independent_evidence_eligible": False,
            "numeric_effect_enabled": False,
            "roles": [],
        }
    return dict(entry)


def is_scoring_factor(factor_id: str) -> bool:
    entry = factor_policy(factor_id)
    return (
        entry.get("lifecycle") == "ACTIVE"
        and "SCORING" in entry.get("roles", [])
        and bool(entry.get("numeric_effect_enabled"))
    )


def _registry_path(relative_path: Path) -> Path:
    candidates = (
        Path.cwd() / relative_path,
        Path(__file__).resolve().parents[3] / relative_path,
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("FACTOR_REGISTRY_NOT_FOUND")
