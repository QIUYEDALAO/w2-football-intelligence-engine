from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

FORBIDDEN_PRODUCTION_TERMS = ("fake", "example", "test")
REQUIRED_ITEM_FIELDS = (
    "team_id",
    "squad_value_eur",
    "observed_at",
    "source_system",
    "source_url",
    "currency",
    "reviewed_by",
)
REQUIRED_POLICY_TERMS = ("no scraping", "no credentials", "no market-derived values")


@dataclass(frozen=True)
class ValidationSummary:
    ok: bool
    mapped_teams: int
    unmapped_teams: int
    duplicate_team_ids: list[str]
    errors: list[str]
    warnings: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "mapped_teams": self.mapped_teams,
            "unmapped_teams": self.unmapped_teams,
            "duplicate_team_ids": self.duplicate_team_ids,
            "errors": self.errors,
            "warnings": self.warnings,
        }


def load_mapping(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"mapping unreadable: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("mapping root must be an object")
    return payload


def load_team_ids(path: Path) -> set[str]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return {
            str(row.get("team_id") or "")
            for row in csv.DictReader(handle)
            if str(row.get("team_id") or "")
        }


def validate_mapping(
    mapping: dict[str, Any],
    *,
    known_team_ids: set[str],
    as_of: datetime,
) -> ValidationSummary:
    errors: list[str] = []
    warnings: list[str] = []
    duplicate_team_ids: list[str] = []
    for key in ("version", "source_policy", "items"):
        if key not in mapping:
            errors.append(f"missing top-level field: {key}")
    source_policy = str(mapping.get("source_policy") or "")
    policy_lower = source_policy.lower()
    for term in REQUIRED_POLICY_TERMS:
        if term not in policy_lower:
            errors.append(f"source_policy must include: {term}")
    raw_items = mapping.get("items")
    if not isinstance(raw_items, list):
        errors.append("items must be a list")
        raw_items = []

    seen: set[str] = set()
    mapped_ids: set[str] = set()
    for index, item in enumerate(raw_items):
        prefix = f"items[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue
        for field in REQUIRED_ITEM_FIELDS:
            if item.get(field) in {None, ""}:
                errors.append(f"{prefix}.{field} is required")
        team_id = str(item.get("team_id") or "")
        if team_id:
            if team_id in seen:
                duplicate_team_ids.append(team_id)
                errors.append(f"{prefix}.team_id duplicate: {team_id}")
            seen.add(team_id)
            mapped_ids.add(team_id)
            if known_team_ids and team_id not in known_team_ids:
                errors.append(f"{prefix}.team_id not in exported team ids: {team_id}")
        _validate_value(item, prefix=prefix, errors=errors)
        _validate_observed_at(item, prefix=prefix, as_of=as_of, errors=errors)
        _validate_source_url(item, prefix=prefix, errors=errors)
        _validate_confidence(item, prefix=prefix, errors=errors)
        _validate_no_forbidden_terms(item, prefix=prefix, errors=errors)

    unmapped = len(known_team_ids - mapped_ids) if known_team_ids else 0
    if not raw_items:
        warnings.append(
            f"mapped_teams=0; unmapped_teams={unmapped}; F8 will remain MAPPING_MISSING"
        )
    elif unmapped:
        warnings.append(f"{unmapped} teams remain unmapped")
    return ValidationSummary(
        ok=not errors,
        mapped_teams=len(mapped_ids),
        unmapped_teams=unmapped,
        duplicate_team_ids=sorted(set(duplicate_team_ids)),
        errors=errors,
        warnings=warnings,
    )


def _validate_value(item: dict[str, Any], *, prefix: str, errors: list[str]) -> None:
    raw_value = item.get("squad_value_eur")
    if raw_value is None:
        errors.append(f"{prefix}.squad_value_eur must be numeric")
        return
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        errors.append(f"{prefix}.squad_value_eur must be numeric")
        return
    if value <= 0:
        errors.append(f"{prefix}.squad_value_eur must be positive")
    if str(item.get("currency") or "") != "EUR":
        errors.append(f"{prefix}.currency must be EUR")


def _validate_observed_at(
    item: dict[str, Any],
    *,
    prefix: str,
    as_of: datetime,
    errors: list[str],
) -> None:
    raw = str(item.get("observed_at") or "")
    try:
        observed = _parse_datetime(raw)
    except ValueError:
        errors.append(f"{prefix}.observed_at must be ISO datetime")
        return
    if observed > as_of:
        errors.append(f"{prefix}.observed_at is after as-of")


def _validate_source_url(item: dict[str, Any], *, prefix: str, errors: list[str]) -> None:
    url = str(item.get("source_url") or "")
    if not re.match(r"^https?://[^\s]+$", url):
        errors.append(f"{prefix}.source_url must be an http/https URL")
    if not str(item.get("source_system") or ""):
        errors.append(f"{prefix}.source_system is required")
    if not str(item.get("reviewed_by") or ""):
        errors.append(f"{prefix}.reviewed_by is required")


def _validate_confidence(item: dict[str, Any], *, prefix: str, errors: list[str]) -> None:
    if "confidence" not in item:
        return
    raw_confidence = item.get("confidence")
    if raw_confidence is None:
        errors.append(f"{prefix}.confidence must be numeric")
        return
    try:
        confidence = float(raw_confidence)
    except (TypeError, ValueError):
        errors.append(f"{prefix}.confidence must be numeric")
        return
    if not 0 <= confidence <= 1:
        errors.append(f"{prefix}.confidence must be between 0 and 1")


def _validate_no_forbidden_terms(
    item: dict[str, Any],
    *,
    prefix: str,
    errors: list[str],
) -> None:
    text = json.dumps(item, ensure_ascii=False).lower()
    for term in FORBIDDEN_PRODUCTION_TERMS:
        if term in text:
            errors.append(f"{prefix} contains forbidden production term: {term}")


def _parse_datetime(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError(value)
    return parsed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate reviewed W2 team value mapping.")
    parser.add_argument("--mapping", required=True, type=Path)
    parser.add_argument("--team-ids", required=True, type=Path)
    parser.add_argument("--as-of", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        as_of = _parse_datetime(str(args.as_of))
        mapping = load_mapping(args.mapping)
        known_team_ids = load_team_ids(args.team_ids)
        summary = validate_mapping(mapping, known_team_ids=known_team_ids, as_of=as_of)
    except (OSError, ValueError) as exc:
        summary = ValidationSummary(
            ok=False,
            mapped_teams=0,
            unmapped_teams=0,
            duplicate_team_ids=[],
            errors=[str(exc)],
            warnings=[],
        )
    print(json.dumps(summary.as_dict(), ensure_ascii=False, indent=2))
    return 0 if summary.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
