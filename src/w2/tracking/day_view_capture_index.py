from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from w2.api.singleflight_cache import SingleFlightCache
from w2.models.fair_market_estimate import SNAPSHOT_SCHEMA_V2, verify_estimate_snapshot
from w2.tracking.frozen_capture_identity import (
    audit_capture_id,
    capture_content_hash,
    capture_estimate_identity,
)
from w2.tracking.frozen_capture_lookup import frozen_ledger_fingerprint

DAY_VIEW_CAPTURE_PROJECTION_VERSION = "w2.day_view_capture_summary.v2"
MAX_DAY_VIEW_CAPTURE_SUMMARY_BYTES = 24 * 1024


@dataclass(frozen=True)
class DayViewCaptureSummary:
    fixture_id: str
    captured_at: str
    kickoff_utc: str | None
    capture_hash: str
    decision_tier: str
    data_status: str
    lifecycle_status: str
    outcome_tracked: bool
    lock_eligible: bool
    recommendation_id: str | None
    reason_code: str | None
    primary_blocker: str | None
    primary_blocker_layer: str | None
    action: str | None
    next_eval_at: str | None
    provider_budget_status: str | None
    pick: Mapping[str, Any] | None
    non_pick: Mapping[str, Any] | None
    current_odds: Mapping[str, Any]
    analysis_readiness: Mapping[str, Any]
    data_refresh: Mapping[str, Any]
    compact_provenance: Mapping[str, Any]
    direction_scorelines: tuple[Mapping[str, Any], ...]
    scoreline_readiness: Mapping[str, Any]
    audit_estimate_id: str | None
    source: str
    audit_capture_id: str | None = None
    audit_identity_status: str = "BLOCKED"
    audit_blocker: str | None = None
    audit_available: bool = False
    historical_compatibility: bool = False

    def as_card_fields(self) -> dict[str, Any]:
        value = asdict(self)
        value["audit_capture_hash"] = value.pop("capture_hash")
        value["scoreline_picks"] = value.pop("direction_scorelines")
        return value


@dataclass(frozen=True)
class DayViewCaptureIndex:
    schema_version: str
    ledger_fingerprint: str
    summaries: Mapping[str, DayViewCaptureSummary]
    source_status: str
    corruption_count: int
    scanned_file_count: int
    scanned_record_count: int


_cache: SingleFlightCache[tuple[str, str, str, int, int], DayViewCaptureIndex] = SingleFlightCache(
    max_entries=4
)


def clear_day_view_capture_index_cache() -> None:
    _cache.clear()


def build_day_view_capture_index(
    runtime_root: Path,
    *,
    max_fixtures: int = 20_000,
    max_line_bytes: int = 4 * 1024 * 1024,
) -> DayViewCaptureIndex:
    root = runtime_root.resolve()
    fingerprint = frozen_ledger_fingerprint(root)
    key = (
        str(root),
        fingerprint,
        DAY_VIEW_CAPTURE_PROJECTION_VERSION,
        max_fixtures,
        max_line_bytes,
    )
    return _cache.get_or_compute(
        key,
        ttl_seconds=5 * 60,
        compute=lambda: _scan(root, fingerprint, max_fixtures, max_line_bytes),
    )


def _scan(
    root: Path,
    fingerprint: str,
    max_fixtures: int,
    max_line_bytes: int,
) -> DayViewCaptureIndex:
    directory = root / "forward_outcome_ledger"
    if not directory.is_dir():
        directory = root
    files = tuple(sorted(directory.glob("*.jsonl")))
    latest: dict[str, tuple[tuple[str, str], DayViewCaptureSummary]] = {}
    corruption_count = 0
    scanned_record_count = 0
    source_status = "PASS" if files else "MISSING"
    try:
        for path in files:
            with path.open("rb") as handle:
                for raw_line in handle:
                    if not raw_line.strip():
                        continue
                    if len(raw_line) > max_line_bytes:
                        return _blocked(fingerprint, files, scanned_record_count, corruption_count)
                    scanned_record_count += 1
                    try:
                        record = json.loads(raw_line)
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        corruption_count += 1
                        source_status = "DEGRADED"
                        continue
                    if (
                        not isinstance(record, dict)
                        or str(record.get("record_type") or "capture") != "capture"
                    ):
                        continue
                    summary = _summary_from_capture(record)
                    if summary is None:
                        continue
                    order = (summary.captured_at, summary.capture_hash)
                    previous = latest.get(summary.fixture_id)
                    if previous is None or order > previous[0]:
                        latest[summary.fixture_id] = (order, summary)
                        if len(latest) > max_fixtures:
                            return _blocked(
                                fingerprint, files, scanned_record_count, corruption_count
                            )
    except OSError:
        source_status = "ERROR"
    return DayViewCaptureIndex(
        schema_version=DAY_VIEW_CAPTURE_PROJECTION_VERSION,
        ledger_fingerprint=fingerprint,
        summaries={fixture_id: item[1] for fixture_id, item in latest.items()},
        source_status=source_status,
        corruption_count=corruption_count,
        scanned_file_count=len(files),
        scanned_record_count=scanned_record_count,
    )


def _blocked(
    fingerprint: str,
    files: tuple[Path, ...],
    scanned_record_count: int,
    corruption_count: int,
) -> DayViewCaptureIndex:
    return DayViewCaptureIndex(
        schema_version=DAY_VIEW_CAPTURE_PROJECTION_VERSION,
        ledger_fingerprint=fingerprint,
        summaries={},
        source_status="BLOCKED",
        corruption_count=corruption_count,
        scanned_file_count=len(files),
        scanned_record_count=scanned_record_count,
    )


def _summary_from_capture(capture: Mapping[str, Any]) -> DayViewCaptureSummary | None:
    fixture_id = _text(capture.get("fixture_id"))
    captured_at = _text(capture.get("captured_at"))
    kickoff_utc = _optional_text(capture.get("kickoff_utc"))
    if not fixture_id or not captured_at:
        return None
    if kickoff_utc and captured_at >= kickoff_utc:
        return None
    status = _text(capture.get("status")).upper()
    if status in {"LIVE", "1H", "HT", "2H", "ET", "FT", "AET", "PEN"}:
        return None
    capture_hash = capture_content_hash(capture)
    if not capture_hash:
        return None
    pick = _allow_mapping(
        capture.get("pick"),
        ("market", "selection", "line", "odds", "fair_line", "estimate_id", "model_basis_id"),
    )
    estimate_identity = capture_estimate_identity(capture)
    estimate_id = estimate_identity.estimate_id
    capture_id = audit_capture_id(capture)
    audit_available = bool(
        capture_id
        and capture_hash
        and estimate_id
        and estimate_identity.status == "PASS"
    )
    raw_snapshots = capture.get("fair_market_estimate_snapshots")
    snapshots = (
        raw_snapshots
        if isinstance(raw_snapshots, Sequence)
        and not isinstance(raw_snapshots, str | bytes | bytearray)
        else ()
    )
    historical_compatibility = any(
        isinstance(snapshot, Mapping)
        and snapshot.get("schema_version") != SNAPSHOT_SCHEMA_V2
        and verify_estimate_snapshot(snapshot)
        for snapshot in snapshots
    )
    provenance = _compact_provenance(capture, estimate_id=estimate_id, pick=pick)
    scorelines = _direction_scorelines(capture)
    summary = DayViewCaptureSummary(
        fixture_id=fixture_id,
        captured_at=captured_at,
        kickoff_utc=kickoff_utc,
        capture_hash=capture_hash,
        decision_tier=_text(capture.get("decision_tier"), "NOT_READY"),
        data_status=_text(capture.get("data_status"), "BLOCKED"),
        lifecycle_status=_text(capture.get("lifecycle_status"), "DRAFT"),
        outcome_tracked=capture.get("outcome_tracked") is True,
        lock_eligible=capture.get("lock_eligible") is True,
        recommendation_id=_optional_text(capture.get("recommendation_id")),
        reason_code=_optional_text(capture.get("reason_code")),
        primary_blocker=_optional_text(capture.get("primary_blocker")),
        primary_blocker_layer=_optional_text(capture.get("primary_blocker_layer")),
        action=_optional_text(capture.get("action")),
        next_eval_at=_optional_text(capture.get("next_eval_at")),
        provider_budget_status=_optional_text(capture.get("provider_budget_status")),
        pick=pick or None,
        non_pick=_allow_mapping(
            capture.get("non_pick"), ("reason_code", "reason_human", "action", "next_eval_at")
        )
        or None,
        current_odds=_allow_mapping(
            capture.get("current_odds"), ("ah", "ou", "one_x_two", "source", "captured_at")
        ),
        analysis_readiness=_allow_mapping(
            capture.get("analysis_readiness"),
            ("status", "blockers", "first_blocker", "all_blockers"),
        ),
        data_refresh=_allow_mapping(
            capture.get("data_refresh"),
            (
                "status",
                "odds_status",
                "lineups_status",
                "xg_status",
                "last_refresh",
                "next_refresh_tick",
            ),
        ),
        compact_provenance=provenance,
        direction_scorelines=scorelines,
        scoreline_readiness=_allow_mapping(
            capture.get("scoreline_readiness"), ("status", "source", "reason")
        ),
        audit_estimate_id=estimate_id,
        source="frozen_forward_capture",
        audit_capture_id=capture_id,
        audit_identity_status="PASS" if audit_available else "BLOCKED",
        audit_blocker=None if audit_available else estimate_identity.blocker,
        audit_available=audit_available,
        historical_compatibility=historical_compatibility,
    )
    if _json_size(summary.as_card_fields()) <= MAX_DAY_VIEW_CAPTURE_SUMMARY_BYTES:
        return summary
    return DayViewCaptureSummary(
        fixture_id=fixture_id,
        captured_at=captured_at,
        kickoff_utc=kickoff_utc,
        capture_hash=capture_hash,
        decision_tier="NOT_READY",
        data_status="BLOCKED",
        lifecycle_status=summary.lifecycle_status,
        outcome_tracked=False,
        lock_eligible=False,
        recommendation_id=None,
        reason_code="L1_CAPTURE_SUMMARY_TOO_LARGE",
        primary_blocker="L1_CAPTURE_SUMMARY_TOO_LARGE",
        primary_blocker_layer="DECISION_CAPTURE",
        action="打开审计详情核查",
        next_eval_at=None,
        provider_budget_status=summary.provider_budget_status,
        pick=None,
        non_pick={"reason_code": "L1_CAPTURE_SUMMARY_TOO_LARGE"},
        current_odds={},
        analysis_readiness={"status": "BLOCKED", "blockers": ["L1_CAPTURE_SUMMARY_TOO_LARGE"]},
        data_refresh={},
        compact_provenance={},
        direction_scorelines=(),
        scoreline_readiness={"status": "BLOCKED"},
        audit_estimate_id=estimate_id,
        source="frozen_forward_capture",
        audit_capture_id=capture_id,
        audit_identity_status="BLOCKED",
        audit_blocker="L1_CAPTURE_SUMMARY_TOO_LARGE",
        audit_available=False,
    )


def _compact_provenance(
    capture: Mapping[str, Any], *, estimate_id: str | None, pick: Mapping[str, Any]
) -> dict[str, Any]:
    snapshots = capture.get("fair_market_estimate_snapshots")
    if not isinstance(snapshots, list):
        return {}
    market = _optional_text(pick.get("market"))
    selected = next(
        (
            row
            for row in snapshots
            if isinstance(row, Mapping)
            and estimate_id
            and _optional_text(row.get("estimate_id")) == estimate_id
        ),
        None,
    )
    if selected is None:
        selected = next(
            (
                row
                for row in snapshots
                if isinstance(row, Mapping)
                and market
                and _optional_text(row.get("market")) == market
            ),
            None,
        )
    if not isinstance(selected, Mapping):
        return {}
    raw_model = selected.get("model_context")
    model: Mapping[str, Any] = raw_model if isinstance(raw_model, Mapping) else {}
    raw_integrity = selected.get("integrity")
    integrity: Mapping[str, Any] = raw_integrity if isinstance(raw_integrity, Mapping) else {}
    return {
        key: value
        for key, value in {
            "estimate_id": _optional_text(selected.get("estimate_id")),
            "model_basis_id": _optional_text(selected.get("model_basis_id")),
            "market": _optional_text(selected.get("market")),
            "schema_version": _optional_text(
                selected.get("schema_version") or selected.get("schema")
            ),
            "status": _optional_text(selected.get("status")),
            "integrity_status": _optional_text(
                selected.get("integrity_status") or integrity.get("status")
            ),
            "semantic_status": _optional_text(selected.get("semantic_status")),
            "artifact_hash": _optional_text(
                selected.get("artifact_hash") or model.get("artifact_hash")
            ),
            "artifact_id": _optional_text(
                selected.get("artifact_id")
                or model.get("artifact_id")
                or model.get("artifact_hash")
            ),
            "artifact_version": _optional_text(
                selected.get("artifact_version") or model.get("artifact_version")
            ),
            "feature_as_of": _optional_text(
                selected.get("feature_as_of") or model.get("feature_as_of")
            ),
        }.items()
        if value is not None
    }


def _direction_scorelines(capture: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    reference = capture.get("scoreline_reference")
    candidates: Any = (
        reference.get("top_scorelines")
        if isinstance(reference, Mapping)
        else capture.get("scoreline_picks")
    )
    if not isinstance(candidates, list):
        return ()
    result: list[dict[str, Any]] = []
    for item in candidates:
        if not isinstance(item, Mapping):
            continue
        scoreline = _optional_text(item.get("scoreline"))
        if scoreline:
            result.append(
                {
                    key: item[key]
                    for key in ("scoreline", "probability", "probability_type")
                    if key in item
                }
            )
        if len(result) == 3:
            break
    return tuple(result)


def _allow_mapping(value: Any, allowed: tuple[str, ...]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {key: value[key] for key in allowed if key in value}


def _json_size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str).encode())


def _text(value: Any, default: str = "") -> str:
    text = str(value).strip() if value is not None else ""
    return text or default


def _optional_text(value: Any) -> str | None:
    text = _text(value)
    return text or None
