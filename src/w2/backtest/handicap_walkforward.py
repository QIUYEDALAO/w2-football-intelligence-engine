from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from w2.backtest.s2_gate import S2GateEvidence, s2_walkforward_shadow_status
from w2.ingestion.market_timeline import DEFAULT_TIMELINE_DIR, find_lock_snapshot, parse_utc

HANDICAP_WALKFORWARD_VERSION = "w2.handicap_walkforward.v1"


@dataclass(frozen=True, kw_only=True)
class RealWalkForwardInputs:
    from_date: date | None = None
    to_date: date | None = None
    timeline_root: Path = DEFAULT_TIMELINE_DIR
    fixture_rows: list[dict[str, Any]] | None = None


def build_real_handicap_walkforward_report(inputs: RealWalkForwardInputs) -> dict[str, Any]:
    fixtures = _fixture_rows(inputs)
    samples: list[dict[str, Any]] = []
    exclusion_counts: dict[str, int] = {}
    for fixture in fixtures:
        fixture_id = str(fixture.get("fixture_id") or "")
        kickoff = parse_utc(fixture.get("kickoff_utc"))
        if not fixture_id or kickoff is None:
            continue
        if not _inside_date_window(kickoff, inputs.from_date, inputs.to_date):
            continue
        lock = find_lock_snapshot(root=inputs.timeline_root, fixture_id=fixture_id, kickoff=kickoff)
        exclusions: list[str] = []
        if lock is None:
            exclusions.append("MISSING_AS_OF")
        if fixture.get("final_result") is None:
            exclusions.append("MISSING_FINAL_RESULT")
        if fixture.get("fair_ah") is None:
            exclusions.append("MISSING_FAIR_AH")
        if fixture.get("settlement_outcome") is None:
            exclusions.append("MISSING_SETTLEMENT")
        included = not exclusions
        for reason in exclusions:
            exclusion_counts[reason] = exclusion_counts.get(reason, 0) + 1
        samples.append(
            {
                "fixture_id": fixture_id,
                "kickoff_utc": kickoff.isoformat().replace("+00:00", "Z"),
                "sample_included": included,
                "exclusion_reasons": exclusions,
                "asof_market_snapshot_id": lock.get("source_hash") if lock else None,
                "market_ah": lock.get("line") if lock else None,
                "devig_method": fixture.get("devig_method")
                or ("LOCKED_MARKET_RAW" if lock else None),
                "settlement_outcome": fixture.get("settlement_outcome"),
            }
        )
    included_count = sum(1 for sample in samples if sample["sample_included"])
    gate = s2_walkforward_shadow_status(
        S2GateEvidence(
            covered_settled_sample=included_count,
            noise_separated_advantage=False,
            time_split_passed=False,
            holdout_replicated=False,
            forward_shadow_passed=False,
        )
    )
    blockers = list(exclusion_counts)
    if included_count < 200:
        blockers.append("INSUFFICIENT_VALIDATED_SAMPLES")
    blockers = list(dict.fromkeys(blockers))
    return {
        "report_version": HANDICAP_WALKFORWARD_VERSION,
        "report_type": "S2_HANDICAP_WALK_FORWARD_REAL",
        "mode": "real",
        "data_source": "MARKET_TIMELINE_LOCK_SNAPSHOTS",
        "authoritative": bool(samples),
        "samples": included_count,
        "covered_settled_sample": included_count,
        "beats_market": False,
        "formal_enabled": False,
        "candidate_enabled": False,
        "blockers": blockers,
        "sample": {
            "candidate_total": len(samples),
            "included": included_count,
            "exclusion_counts": exclusion_counts,
            "rows": samples,
        },
        "s2_gate": gate,
        "gate": gate,
        "calibration": {
            "calibration_version": "UNVALIDATED",
            "beats_market": False,
            "formal_enabled": False,
            "candidate_enabled": False,
        },
    }


def _fixture_rows(inputs: RealWalkForwardInputs) -> list[dict[str, Any]]:
    if inputs.fixture_rows is not None:
        return inputs.fixture_rows
    rows: list[dict[str, Any]] = []
    try:
        paths = sorted(inputs.timeline_root.glob("*.json"))
    except OSError:
        return []
    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        fixture_id = str(payload.get("fixture_id") or path.stem)
        kickoff = payload.get("kickoff_utc")
        rows.append({"fixture_id": fixture_id, "kickoff_utc": kickoff})
    return rows


def _inside_date_window(
    kickoff: datetime,
    from_date: date | None,
    to_date: date | None,
) -> bool:
    kickoff_date = kickoff.astimezone(UTC).date()
    if from_date is not None and kickoff_date < from_date:
        return False
    if to_date is not None and kickoff_date > to_date:
        return False
    return True
