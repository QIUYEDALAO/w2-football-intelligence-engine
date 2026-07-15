from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from w2.tracking.canonical_identity import performance_key

_SCOPES = {"VALIDATION", "OFFICIAL", "SHADOW"}
_MARKETS = {"ASIAN_HANDICAP", "TOTALS"}
_SELECTIONS = {
    "ASIAN_HANDICAP": {"HOME_AH", "AWAY_AH"},
    "TOTALS": {"OVER", "UNDER"},
}


@dataclass(frozen=True)
class CanonicalOutcomeProjection:
    raw_outcomes: tuple[Mapping[str, Any], ...]
    canonical_outcomes: tuple[Mapping[str, Any], ...]
    audit_only_outcomes: tuple[Mapping[str, Any], ...]
    unmatched_identity_outcomes: tuple[Mapping[str, Any], ...]
    conflicting_outcomes: tuple[Mapping[str, Any], ...]
    duplicate_outcomes: tuple[Mapping[str, Any], ...]
    metrics: Mapping[str, Any]


def legacy_performance_candidates(
    records: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Select the last usable prematch compatibility capture per performance key."""
    candidates = _all_legacy_performance_candidates(records)
    winners: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for candidate in candidates:
        key = performance_key(candidate)
        current = winners.get(key)
        order = (
            _parse_time(candidate.get("captured_at"))
            or datetime.min.replace(tzinfo=UTC),
            str(candidate.get("capture_hash") or ""),
        )
        if current is None or order > (
            _parse_time(current.get("captured_at"))
            or datetime.min.replace(tzinfo=UTC),
            str(current.get("capture_hash") or ""),
        ):
            winners[key] = candidate
    return tuple(winners[key] for key in sorted(winners))


def _all_legacy_performance_candidates(
    records: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    candidates: list[dict[str, Any]] = []
    for record in records:
        if str(record.get("record_type") or "capture") != "capture":
            continue
        captured_at = _parse_time(record.get("captured_at"))
        kickoff = _parse_time(record.get("kickoff_utc"))
        if captured_at is None or kickoff is None or captured_at >= kickoff:
            continue
        if record.get("live") is True or str(record.get("fixture_status") or "").upper() in {
            "LIVE",
            "1H",
            "HT",
            "2H",
            "ET",
            "P",
            "BT",
        }:
            continue
        fixture_id = str(record.get("fixture_id") or "")
        if not fixture_id:
            continue
        pick = record.get("pick")
        if isinstance(pick, Mapping):
            scope = _record_scope(record)
            candidates.extend(
                _legacy_candidate_rows(
                    record,
                    (pick,),
                    fixture_id=fixture_id,
                    scope=scope,
                    default_strategy=(
                        "LEGACY_VALIDATION_V1"
                        if scope == "VALIDATION"
                        else "LEGACY_OFFICIAL_V1"
                    ),
                )
            )
        shadows = record.get("shadow_picks")
        shadow_rows: Sequence[object] = (
            shadows
            if isinstance(shadows, Sequence)
            and not isinstance(shadows, (str, bytes, bytearray))
            else ()
        )
        shadow = record.get("shadow_pick")
        if isinstance(shadow, Mapping):
            shadow_rows = (*shadow_rows, shadow)
        candidates.extend(
            _legacy_candidate_rows(
                record,
                (item for item in shadow_rows if isinstance(item, Mapping)),
                fixture_id=fixture_id,
                scope="SHADOW",
                default_strategy="WIDE_SHADOW_V1",
            )
        )

    return tuple(candidates)


def project_canonical_outcomes(
    records: Sequence[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
) -> CanonicalOutcomeProjection:
    """Project immutable raw/audit rows into one outcome per performance key."""
    raw_outcomes = tuple(
        dict(record)
        for record in records
        if str(record.get("record_type") or "capture") == "outcome"
    )
    captures_by_hash, captures_by_pick = _capture_indexes(records)
    normalized = [
        _normalize_outcome(row, captures_by_hash)
        for row in raw_outcomes
    ]
    unique_rows, exact_duplicate_rows = _separate_exact_duplicates(
        normalized,
        raw_outcomes,
        captures_by_hash,
        captures_by_pick,
    )

    all_corrected = tuple(
        dict(candidate)
        for candidate in candidates
        if candidate.get("exclusion_reason") is None
    )
    corrected = tuple(
        candidate
        for candidate in all_corrected
        if candidate.get("canonical_candidate") is True
    )
    corrected_key_counts = Counter(performance_key(candidate) for candidate in corrected)
    canonical_candidate_nonunique_count = sum(
        1 for count in corrected_key_counts.values() if count > 1
    )
    all_compatibility = _all_legacy_performance_candidates(records)
    winner_keys = {performance_key(row) for row in legacy_performance_candidates(records)}
    compatibility = tuple(
        max(
            (row for row in all_compatibility if performance_key(row) == key),
            key=lambda item: (
                _parse_time(item.get("captured_at")) or datetime.min.replace(tzinfo=UTC),
                str(item.get("capture_hash") or ""),
            ),
        )
        for key in sorted(winner_keys)
        if any(performance_key(row) == key for row in all_compatibility)
    )

    matched: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    audit_only: list[dict[str, Any]] = [
        {**row, "audit_only": True, "audit_reason": "RAW_EXACT_DUPLICATE"}
        for row in exact_duplicate_rows
    ]
    unmatched_identity: list[dict[str, Any]] = []
    historical_incomplete: list[dict[str, Any]] = []
    identity_matched_count = 0
    identity_decision_surfaces: set[tuple[str, str, str]] = set()
    cross_track_count = 0

    for outcome in unique_rows:
        if _complete_identity(outcome):
            candidate = _match_corrected(outcome, corrected)
            if candidate is None:
                if _matches_noncanonical_corrected(outcome, all_corrected):
                    audit_only.append(
                        {
                            **outcome,
                            "audit_only": True,
                            "audit_reason": "NON_CANONICAL_CAPTURE",
                        }
                    )
                    continue
                row = {
                    **outcome,
                    "audit_only": True,
                    "audit_reason": "IDENTITY_AWARE_OUTCOME_UNMATCHED",
                }
                unmatched_identity.append(row)
                audit_only.append(row)
                continue
            identity_matched_count += 1
            if str(candidate.get("recommendation_scope") or "") != "SHADOW":
                identity_decision_surfaces.add(performance_key(candidate)[:3])
            matched[performance_key(candidate)].append(
                _bound_outcome(outcome, candidate, corrected=True, match_type="IDENTITY_AWARE")
            )
            continue

        if _has_partial_identity(outcome):
            row = {
                **outcome,
                "audit_only": True,
                "audit_reason": "HISTORICAL_INCOMPLETE_IDENTITY",
            }
            historical_incomplete.append(row)
            audit_only.append(row)
            continue

        candidate = _match_legacy(outcome, compatibility)
        if candidate is None:
            reason = (
                "NON_CANONICAL_SELECTION"
                if _has_legacy_surface(outcome, compatibility)
                else "LEGACY_OUTCOME_UNMATCHED"
            )
            audit_only.append({**outcome, "audit_only": True, "audit_reason": reason})
            continue
        if not _same_track(outcome, candidate):
            cross_track_count += 1
            audit_only.append(
                {**outcome, "audit_only": True, "audit_reason": "CROSS_TRACK_MATCH_REJECTED"}
            )
            continue
        matched[performance_key(candidate)].append(
            _bound_outcome(outcome, candidate, corrected=False, match_type="LEGACY_COMPATIBILITY")
        )

    canonical: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    conflict_key_count = 0
    for key, outcomes in sorted(matched.items()):
        if key[:3] in identity_decision_surfaces and not any(
            item.get("match_type") == "IDENTITY_AWARE" for item in outcomes
        ):
            for item in outcomes:
                audit_only.append(
                    {
                        **item,
                        "audit_only": True,
                        "audit_reason": "SUPERSEDED_BY_IDENTITY_AWARE_OUTCOME",
                    }
                )
            continue
        settlement_states = {str(item.get("settlement_outcome") or "") for item in outcomes}
        if len(settlement_states) != 1:
            conflict_key_count += 1
            for item in outcomes:
                row = {
                    **item,
                    "audit_only": True,
                    "audit_reason": "OUTCOME_CONFLICT",
                    "conflict_performance_key": list(key),
                }
                conflicts.append(row)
                audit_only.append(row)
            continue
        winner = max(outcomes, key=_outcome_priority)
        canonical.append({**winner, "audit_only": False, "canonical_outcome": True})
        for item in outcomes:
            if item is winner:
                continue
            row = {
                **item,
                "audit_only": True,
                "audit_reason": "DUPLICATE_CANONICAL_OUTCOME",
                "duplicate_of": _audit_hash(winner),
            }
            duplicates.append(row)
            audit_only.append(row)

    canonical_keys = [tuple(row.get("canonical_performance_key") or ()) for row in canonical]
    canonical_duplicate_count = len(canonical_keys) - len(set(canonical_keys))
    blocked = bool(
        conflict_key_count
        or canonical_duplicate_count
        or unmatched_identity
        or cross_track_count
        or canonical_candidate_nonunique_count
    )
    compatibility_count = sum(row.get("compatibility_only") is True for row in canonical)
    status = (
        "BLOCKED"
        if blocked
        else "PASS_WITH_LEGACY_AUDIT"
        if compatibility_count or audit_only
        else "PASS"
    )
    metrics = {
        "status": status,
        "raw_outcome_row_count": len(raw_outcomes),
        "canonical_outcome_count": len(canonical),
        "audit_only_outcome_count": len(raw_outcomes) - len(canonical),
        "duplicate_audit_row_count": len(duplicates),
        "raw_exact_duplicate_count": len(exact_duplicate_rows),
        "outcome_conflict_count": conflict_key_count,
        "identity_aware_matched_count": identity_matched_count,
        "identity_aware_unmatched_count": len(unmatched_identity),
        "historical_incomplete_identity_count": len(historical_incomplete),
        "canonical_duplicate_count": canonical_duplicate_count,
        "canonical_candidate_nonunique_count": canonical_candidate_nonunique_count,
        "cross_track_contamination_count": cross_track_count,
        "historical_compatibility_outcome_count": compatibility_count,
        "corrected_outcome_count": len(canonical) - compatibility_count,
    }
    return CanonicalOutcomeProjection(
        raw_outcomes=raw_outcomes,
        canonical_outcomes=tuple(canonical),
        audit_only_outcomes=tuple(audit_only),
        unmatched_identity_outcomes=tuple(unmatched_identity),
        conflicting_outcomes=tuple(conflicts),
        duplicate_outcomes=tuple(duplicates),
        metrics=metrics,
    )


def _legacy_candidate_rows(
    record: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]] | Any,
    *,
    fixture_id: str,
    scope: str,
    default_strategy: str,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in rows:
        market = str(row.get("market") or "")
        selection = str(row.get("selection") or "")
        if market not in _MARKETS or selection not in _SELECTIONS[market]:
            continue
        output.append(
            {
                **dict(record),
                "fixture_id": fixture_id,
                "market": market,
                "selection": selection,
                "recommendation_scope": scope,
                "strategy_version": str(
                    row.get("strategy_version")
                    or record.get("strategy_version")
                    or default_strategy
                ),
                "capture_hash": str(
                    record.get("capture_hash")
                    or record.get("evidence_hash")
                    or record.get("card_hash")
                    or ""
                ),
                "compatibility_only": True,
                "evidence_eligible": False,
                "corrected_evidence": False,
                "canonical_candidate": True,
                "audit_only": False,
            }
        )
    return output


def _capture_indexes(
    records: Sequence[Mapping[str, Any]],
) -> tuple[
    dict[str, Mapping[str, Any]],
    dict[tuple[str, str, str], list[Mapping[str, Any]]],
]:
    by_hash: dict[str, Mapping[str, Any]] = {}
    by_pick: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        if str(record.get("record_type") or "capture") != "capture":
            continue
        for field in ("evidence_hash", "card_hash"):
            if value := str(record.get(field) or ""):
                by_hash[value] = record
        pick = record.get("pick")
        if isinstance(pick, Mapping):
            key = (
                str(record.get("fixture_id") or ""),
                str(pick.get("market") or ""),
                str(pick.get("selection") or ""),
            )
            by_pick[key].append(record)
    return by_hash, by_pick


def _normalize_outcome(
    outcome: Mapping[str, Any],
    captures_by_hash: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    row = dict(outcome)
    explicit = str(row.get("recommendation_scope") or "").upper()
    if explicit not in {"OFFICIAL", "VALIDATION"}:
        if str(row.get("settled_side") or "") == "shadow_pick":
            explicit = "SHADOW"
        else:
            source_ref = str(
                row.get("source_capture_hash") or row.get("card_hash") or ""
            )
            source = captures_by_hash.get(source_ref)
            explicit = _record_scope(source) if source is not None else "VALIDATION"
        row["recommendation_scope"] = explicit
    row["audit_hash"] = _audit_hash(row)
    return row


def _separate_exact_duplicates(
    outcomes: Sequence[dict[str, Any]],
    raw_outcomes: Sequence[Mapping[str, Any]],
    captures_by_hash: Mapping[str, Mapping[str, Any]],
    captures_by_pick: Mapping[tuple[str, str, str], Sequence[Mapping[str, Any]]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    unique: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for outcome, raw_outcome in zip(outcomes, raw_outcomes, strict=True):
        identity = _legacy_dedup_identity(
            raw_outcome,
            captures_by_hash,
            captures_by_pick,
        )
        if identity in seen:
            duplicates.append(outcome)
        else:
            seen.add(identity)
            unique.append(outcome)
    return unique, duplicates


def _legacy_dedup_identity(
    outcome: Mapping[str, Any],
    captures_by_hash: Mapping[str, Mapping[str, Any]],
    captures_by_pick: Mapping[tuple[str, str, str], Sequence[Mapping[str, Any]]],
) -> str:
    row = dict(outcome)
    explicit = str(row.get("recommendation_scope") or "").upper()
    if explicit not in {"OFFICIAL", "VALIDATION"}:
        source_ref = str(row.get("source_capture_hash") or row.get("card_hash") or "")
        source = captures_by_hash.get(source_ref)
        if source is None:
            key = (
                str(row.get("fixture_id") or ""),
                str(row.get("market") or ""),
                str(row.get("selection") or ""),
            )
            source = max(
                captures_by_pick.get(key, ()),
                key=lambda item: (
                    _parse_time(item.get("captured_at"))
                    or datetime.min.replace(tzinfo=UTC)
                ),
                default=None,
            )
        if source is not None:
            row["recommendation_scope"] = _legacy_scope(source)
            row.setdefault("source_capture_hash", source.get("evidence_hash"))
    row["recommendation_scope"] = _legacy_scope(row)
    return _outcome_event_identity(row)


def _outcome_event_identity(outcome: Mapping[str, Any]) -> str:
    identity = {
        "fixture_id": outcome.get("fixture_id"),
        "settled_side": outcome.get("settled_side"),
        "recommendation_scope": outcome.get("recommendation_scope"),
        "market": outcome.get("market"),
        "selection": outcome.get("selection"),
        "strategy_version": outcome.get("strategy_version") or "LEGACY_UNVERSIONED",
        "estimate_id": outcome.get("estimate_id") or "LEGACY_ESTIMATE",
        "quote_id": outcome.get("quote_id") or "LEGACY_QUOTE",
        "source_capture_hash": outcome.get("source_capture_hash")
        or outcome.get("card_hash")
        or "LEGACY_UNSCOPED",
        "settlement_outcome": outcome.get("settlement_outcome") or outcome.get("outcome"),
    }
    return _audit_hash(identity)


def _match_corrected(
    outcome: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    compatible = [
        candidate
        for candidate in candidates
        if _complete_identity_matches(outcome, candidate)
    ]
    source_hash = str(outcome.get("source_capture_hash") or "")
    if source_hash:
        exact = [
            candidate
            for candidate in compatible
            if candidate.get("capture_hash") == source_hash
        ]
        return exact[0] if len(exact) == 1 else None
    return compatible[0] if len(compatible) == 1 else None


def _matches_noncanonical_corrected(
    outcome: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
) -> bool:
    source_hash = str(outcome.get("source_capture_hash") or "")
    if not source_hash:
        return False
    return any(
        candidate.get("canonical_candidate") is not True
        and str(candidate.get("capture_hash") or "") == source_hash
        and _complete_identity_matches(outcome, candidate)
        for candidate in candidates
    )


def _match_legacy(
    outcome: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    matches = [
        candidate
        for candidate in candidates
        if str(candidate.get("fixture_id") or "") == str(outcome.get("fixture_id") or "")
        and str(candidate.get("market") or "") == str(outcome.get("market") or "")
        and str(candidate.get("selection") or "") == str(outcome.get("selection") or "")
        and _same_track(outcome, candidate)
    ]
    return max(
        matches,
        key=lambda item: (
            _parse_time(item.get("captured_at")) or datetime.min.replace(tzinfo=UTC),
            str(item.get("capture_hash") or ""),
        ),
        default=None,
    )


def _has_legacy_surface(
    outcome: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
) -> bool:
    return any(
        str(candidate.get("fixture_id") or "") == str(outcome.get("fixture_id") or "")
        and str(candidate.get("market") or "") == str(outcome.get("market") or "")
        and _same_track(outcome, candidate)
        for candidate in candidates
    )


def _complete_identity_matches(
    outcome: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> bool:
    return all(
        str(outcome.get(field) or "") == str(candidate.get(field) or "")
        for field in (
            "fixture_id",
            "market",
            "selection",
            "recommendation_scope",
            "strategy_version",
            "estimate_id",
            "quote_id",
        )
    )


def _same_track(outcome: Mapping[str, Any], candidate: Mapping[str, Any]) -> bool:
    outcome_scope = str(outcome.get("recommendation_scope") or "")
    candidate_scope = str(candidate.get("recommendation_scope") or "")
    if outcome_scope != candidate_scope:
        return False
    side = str(outcome.get("settled_side") or "")
    return side == "shadow_pick" if candidate_scope == "SHADOW" else side == "pick"


def _bound_outcome(
    outcome: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    corrected: bool,
    match_type: str,
) -> dict[str, Any]:
    key = performance_key(candidate)
    return {
        **dict(outcome),
        "recommendation_scope": key[2],
        "strategy_version": key[3],
        "source_capture_hash": outcome.get("source_capture_hash")
        or candidate.get("capture_hash"),
        "estimate_id": outcome.get("estimate_id") or candidate.get("estimate_id"),
        "quote_id": outcome.get("quote_id") or candidate.get("quote_id"),
        "canonical_performance_key": list(key),
        "compatibility_only": not corrected,
        "historical_compatibility": not corrected,
        "not_corrected_evidence": not corrected,
        "corrected_evidence": corrected,
        "match_type": match_type,
    }


def _outcome_priority(outcome: Mapping[str, Any]) -> tuple[int, int, int, datetime, str]:
    return (
        int(outcome.get("match_type") == "IDENTITY_AWARE"),
        int(bool(outcome.get("source_capture_hash"))),
        int(str(outcome.get("recommendation_scope") or "") in _SCOPES),
        _parse_time(outcome.get("settled_at")) or datetime.min.replace(tzinfo=UTC),
        _audit_hash(outcome),
    )


def _complete_identity(outcome: Mapping[str, Any]) -> bool:
    return all(outcome.get(field) for field in ("strategy_version", "estimate_id", "quote_id"))


def _has_partial_identity(outcome: Mapping[str, Any]) -> bool:
    return any(outcome.get(field) for field in ("strategy_version", "estimate_id", "quote_id"))


def _record_scope(record: Mapping[str, Any]) -> str:
    explicit = str(record.get("recommendation_scope") or "").upper()
    if explicit in _SCOPES:
        return explicit
    if str(record.get("decision_tier") or "").upper() == "ANALYSIS_PICK":
        return "VALIDATION"
    return "OFFICIAL"


def _legacy_scope(record: Mapping[str, Any]) -> str:
    explicit = str(record.get("recommendation_scope") or "").upper()
    if explicit in {"OFFICIAL", "VALIDATION"}:
        return explicit
    if str(record.get("decision_tier") or "").upper() == "ANALYSIS_PICK":
        return "VALIDATION"
    return "OFFICIAL"


def _audit_hash(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _parse_time(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
