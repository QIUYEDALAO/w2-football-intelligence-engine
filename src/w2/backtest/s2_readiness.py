from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from w2.backtest.s2_gate import S2GateEvidence, s2_walkforward_shadow_status

S2_READINESS_VERSION = "w2.s2.readiness.v1"


@dataclass(frozen=True, kw_only=True)
class S2ReadinessInputs:
    features_path: Path | None = None
    labels_path: Path | None = None
    data_source: str = "UNSPECIFIED"
    requested_authoritative: bool = False


def build_s2_readiness_report(inputs: S2ReadinessInputs) -> dict[str, Any]:
    feature_rows = _read_json_rows(inputs.features_path)
    label_rows = _read_json_rows(inputs.labels_path)
    data_source = _data_source(inputs)
    synthetic = _contains_synthetic_data(feature_rows, label_rows)
    demo = _is_demo_source(inputs.features_path) or _is_demo_source(inputs.labels_path)
    authoritative = bool(inputs.requested_authoritative and not synthetic and not demo)
    covered_sample = _covered_settled_ah_sample(feature_rows, label_rows) if authoritative else 0
    blockers = _blockers(
        authoritative=authoritative,
        requested_authoritative=inputs.requested_authoritative,
        synthetic=synthetic,
        demo=demo,
        feature_rows=feature_rows,
        label_rows=label_rows,
        covered_sample=covered_sample,
    )
    gate = s2_walkforward_shadow_status(
        S2GateEvidence(
            covered_settled_sample=covered_sample,
            noise_separated_advantage=False,
            time_split_passed=False,
            holdout_replicated=False,
            forward_shadow_passed=False,
        )
    )
    return {
        "report_version": S2_READINESS_VERSION,
        "report_type": "S2_HANDICAP_WALK_FORWARD_READINESS",
        "data_source": data_source,
        "authoritative": authoritative,
        "samples": covered_sample,
        "covered_settled_sample": covered_sample,
        "feature_row_count": len(feature_rows),
        "label_row_count": len(label_rows),
        "fixture_count": len(
            {str(row.get("fixture_id")) for row in feature_rows if row.get("fixture_id")}
        ),
        "beats_market": False,
        "formal_enabled": False,
        "candidate_enabled": False,
        "blockers": blockers,
        "gate": gate,
        "dashboard_publishable": False,
        "card_publishable": False,
    }


def _read_json_rows(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    if not path.exists():
        raise FileNotFoundError(path)
    if path.suffix == ".jsonl":
        rows: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                value = json.loads(line)
                if isinstance(value, dict):
                    rows.append(value)
        return rows
    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        row_items = value.get("items") or value.get("rows") or value.get("samples")
        if isinstance(row_items, list):
            return [item for item in row_items if isinstance(item, dict)]
        return [value]
    return []


def _data_source(inputs: S2ReadinessInputs) -> str:
    if inputs.data_source != "UNSPECIFIED":
        return inputs.data_source
    if inputs.features_path is None and inputs.labels_path is None:
        return "NO_ASOF_ARTIFACT"
    paths = [str(path) for path in (inputs.features_path, inputs.labels_path) if path is not None]
    return ",".join(paths)


def _is_demo_source(path: Path | None) -> bool:
    if path is None:
        return False
    normalized = path.as_posix()
    return "fixtures/stage5_demo" in normalized or "stage5_demo" in normalized


def _contains_synthetic_data(
    feature_rows: list[dict[str, Any]],
    label_rows: list[dict[str, Any]],
) -> bool:
    for row in [*feature_rows, *label_rows]:
        provenance = row.get("provenance")
        if isinstance(provenance, dict) and provenance.get("synthetic") is True:
            return True
        if row.get("synthetic") is True:
            return True
    return False


def _covered_settled_ah_sample(
    feature_rows: list[dict[str, Any]],
    label_rows: list[dict[str, Any]],
) -> int:
    settled = {
        str(row.get("fixture_id"))
        for row in label_rows
        if row.get("fixture_id") and str(row.get("result_status") or "").upper() == "FINAL"
    }
    covered: set[str] = set()
    for row in feature_rows:
        fixture_id = str(row.get("fixture_id") or "")
        if fixture_id not in settled:
            continue
        odds = row.get("odds_snapshot")
        markets = odds.get("markets") if isinstance(odds, dict) else None
        if isinstance(markets, list) and "ASIAN_HANDICAP" in {str(item) for item in markets}:
            covered.add(fixture_id)
    return len(covered)


def _blockers(
    *,
    authoritative: bool,
    requested_authoritative: bool,
    synthetic: bool,
    demo: bool,
    feature_rows: list[dict[str, Any]],
    label_rows: list[dict[str, Any]],
    covered_sample: int,
) -> list[str]:
    blockers: list[str] = []
    if not feature_rows or not label_rows:
        blockers.append("MISSING_ASOF_FEATURE_OR_LABEL_ARTIFACT")
    if demo:
        blockers.append("DEMO_DATA_NOT_AUTHORITATIVE")
    if synthetic:
        blockers.append("SYNTHETIC_DATA_NOT_AUTHORITATIVE")
    if requested_authoritative and not authoritative:
        blockers.append("AUTHORITATIVE_REQUEST_REJECTED")
    if not authoritative:
        blockers.append("NON_AUTHORITATIVE_REPORT")
    if covered_sample < 200:
        blockers.append("INSUFFICIENT_VALIDATED_SAMPLES")
    return list(dict.fromkeys(blockers))
