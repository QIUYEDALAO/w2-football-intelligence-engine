"""F0 for AH-FACTOR-ACCURACY-V1: freeze the scope and state what the evidence supports.

Offline, read-only. Reads the frozen 148-candidate package plus one auxiliary file
used only for team display names, and writes the F0 deliverables. It performs no
network call, touches no database, and reconstructs nothing that the frozen
evidence does not already contain.

F0 does not fit, tune or search anything. Its whole job is to say, per row and
per factor, whether a point-in-time historical value exists at all.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

TASK_ID = "W2_AH_FACTOR_ACCURACY_F0_SCOPE_AND_EVIDENCE_FREEZE_20260910"
MAINLINE_ID = "AH-FACTOR-ACCURACY-V1"
AH = "ASIAN_HANDICAP"
TOTALS = "TOTALS"
FACTORS = ("f3", "f5", "f6", "f9")
FACTOR_NAMES = {
    "f3": "F3_REST_FITNESS",
    "f5": "F5_RECENT_AH_COVER",
    "f6": "F6_H2H",
    "f9": "F9_TRUE_XG",
}
NOT_RECONSTRUCTIBLE = "NOT_RECONSTRUCTIBLE"
EXACT_PIT_RECONSTRUCTIBLE = "EXACT_PIT_RECONSTRUCTIBLE"
SOURCE_ONLY_POST_CAPTURE = "SOURCE_ONLY_POST_CAPTURE"
FACTOR_MATRIX_NOT_RECONSTRUCTIBLE = "NOT_RECONSTRUCTIBLE_FROM_FROZEN_148"

EXPECTED_BUNDLE_SHA256 = (
    "da9edb11be8144991addeb1c6e83724d3cca083ca46b0bd8de2eaa6d45f6e7e4")
EXPECTED_LABELS_SHA256 = (
    "7e6bcbdc2baf4d8b255d8dbd79a907aa107d4536a642c13465b7828fd0b37110")

# Frozen by the F0 order and independently recomputed here; a mismatch stops F0.
EXPECTED_ROWS = 148
EXPECTED_FIXTURES = 111
EXPECTED_AH = 84
EXPECTED_TOTALS = 64
EXPECTED_PROFIT = Decimal("-20.375")
EXPECTED_SETTLEMENTS = {
    "LOSS": 66, "HALF_LOSS": 8, "WIN": 55, "HALF_WIN": 6, "PUSH": 13}
EXPECTED_AH_SETTLEMENTS = {
    "LOSS": 34, "HALF_LOSS": 8, "WIN": 32, "HALF_WIN": 6, "PUSH": 4}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(
                row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")


def team_labels(auxiliary: list[dict[str, Any]]) -> dict[str, tuple[str, str]]:
    """Display names only. These are labels for a human reading the roster.

    They are deliberately not returned in any form a model could consume: no
    ids, no provider names, no state flags -- just the two strings a person
    needs to recognise the match.
    """
    out: dict[str, tuple[str, str]] = {}
    for row in auxiliary:
        home = (row.get("home_team_label") or {}).get("display_name")
        away = (row.get("away_team_label") or {}).get("display_name")
        out[str(row["evaluation_id"])] = (
            str(home) if home else NOT_RECONSTRUCTIBLE,
            str(away) if away else NOT_RECONSTRUCTIBLE,
        )
    return out


def verify_scope(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Recompute every frozen F0 figure. Nothing downstream runs on a mismatch."""
    markets = collections.Counter(row["market"] for row in rows)
    settlements = collections.Counter(row["settlement"] for row in rows)
    ah_settlements = collections.Counter(
        row["settlement"] for row in rows if row["market"] == AH)
    totals_settlements = collections.Counter(
        row["settlement"] for row in rows if row["market"] == TOTALS)
    observed = {
        "row_count": len(rows),
        "distinct_fixture_count": len({row["fixture_id"] for row in rows}),
        "ah_count": markets[AH],
        "totals_count": markets[TOTALS],
        "total_profit_units": str(
            sum(Decimal(str(row["profit_units"])) for row in rows)),
        "settlement_counts": dict(sorted(settlements.items())),
        "ah_settlement_counts": dict(sorted(ah_settlements.items())),
        "totals_settlement_counts": dict(sorted(totals_settlements.items())),
        "ah_profit_units": str(sum(
            Decimal(str(row["profit_units"])) for row in rows if row["market"] == AH)),
        "totals_profit_units": str(sum(
            Decimal(str(row["profit_units"])) for row in rows
            if row["market"] == TOTALS)),
    }
    mismatches = []
    if observed["row_count"] != EXPECTED_ROWS:
        mismatches.append("row_count")
    if observed["distinct_fixture_count"] != EXPECTED_FIXTURES:
        mismatches.append("distinct_fixture_count")
    if observed["ah_count"] != EXPECTED_AH:
        mismatches.append("ah_count")
    if observed["totals_count"] != EXPECTED_TOTALS:
        mismatches.append("totals_count")
    if Decimal(observed["total_profit_units"]) != EXPECTED_PROFIT:
        mismatches.append("total_profit_units")
    if observed["settlement_counts"] != dict(sorted(EXPECTED_SETTLEMENTS.items())):
        mismatches.append("settlement_counts")
    if observed["ah_settlement_counts"] != dict(sorted(EXPECTED_AH_SETTLEMENTS.items())):
        mismatches.append("ah_settlement_counts")
    observed["frozen_figure_mismatches"] = mismatches
    observed["scope_verified"] = not mismatches
    return observed


def roster_rows(
    rows: list[dict[str, Any]], labels: dict[str, tuple[str, str]]
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        home, away = labels.get(
            str(row["evaluation_id"]), (NOT_RECONSTRUCTIBLE, NOT_RECONSTRUCTIBLE))
        out.append({
            "evaluation_id": row["evaluation_id"],
            "fixture_id": row["fixture_id"],
            "kickoff_utc": row["kickoff_utc"],
            "home_team_label": home,
            "away_team_label": away,
            "market": row["market"],
            "selection": row["selection"],
            "exact_line": row["exact_line"],
            "score": row["score"],
            "settlement": row["settlement"],
            "profit_units": row["profit_units"],
            # AH only. TOTALS is out of four-factor direction scope by decision,
            # not by data availability, so it is marked rather than dropped.
            "is_ah_factor_scope": row["market"] == AH,
        })
    out.sort(key=lambda row: (str(row["kickoff_utc"]), str(row["evaluation_id"])))
    return out


def factor_cells(manifest_row: dict[str, Any]) -> dict[str, Any]:
    """One factor's six cells, taken only from what the frozen row actually holds.

    Every frozen row carries the literal string NOT_RECONSTRUCTIBLE for the
    factor fields, because the production evaluation payload never persisted a
    factor verdict and the analysis card is a read-time projection with no
    table. So there is nothing to read, and nothing is invented: no zero, no
    current-registry weight standing in for a historical one, no direction
    inferred from the result.
    """
    cells: dict[str, Any] = {}
    for key in FACTORS:
        cells.update({
            f"{key}_factor_id": FACTOR_NAMES[key],
            f"{key}_score": NOT_RECONSTRUCTIBLE,
            f"{key}_status": NOT_RECONSTRUCTIBLE,
            f"{key}_weight": NOT_RECONSTRUCTIBLE,
            f"{key}_participated": NOT_RECONSTRUCTIBLE,
            f"{key}_evidence_time": NOT_RECONSTRUCTIBLE,
            f"{key}_source_hash": NOT_RECONSTRUCTIBLE,
        })
    _ = manifest_row
    return cells


def matrix_rows(
    bundle: list[dict[str, Any]], manifest: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    by_id = {str(row["evaluation_id"]): row for row in manifest}
    out: list[dict[str, Any]] = []
    for row in bundle:
        if row["market"] != AH:
            continue
        manifest_row = by_id.get(str(row["evaluation_id"]))
        if manifest_row is None:
            raise ValueError(f"MANIFEST_ROW_MISSING:{row['evaluation_id']}")
        cells = factor_cells(manifest_row)
        reconstructible = [
            key for key in FACTORS if cells[f"{key}_score"] != NOT_RECONSTRUCTIBLE
        ]
        status = (
            EXACT_PIT_RECONSTRUCTIBLE if len(reconstructible) == len(FACTORS)
            else SOURCE_ONLY_POST_CAPTURE if reconstructible
            else NOT_RECONSTRUCTIBLE
        )
        out.append({
            "evaluation_id": row["evaluation_id"],
            "fixture_id": row["fixture_id"],
            "kickoff_utc": row["kickoff_utc"],
            "evaluated_at": row["evaluated_at"],
            "original_selection": row["selection"],
            "exact_line": row["exact_line"],
            "score": row["score"],
            "settlement": row["settlement"],
            **cells,
            "matrix_row_status": status,
            "not_estimable_reason": (
                None if status == EXACT_PIT_RECONSTRUCTIBLE
                else str(manifest_row.get("factor_not_reconstructible_reason")
                         or NOT_RECONSTRUCTIBLE)
            ),
            "factor_disposition_in_frozen_evidence": manifest_row.get(
                "factor_disposition"),
            "factor_verdict_identity_in_frozen_evidence": manifest_row.get(
                "factor_verdict_identity"),
        })
    out.sort(key=lambda row: (str(row["kickoff_utc"]), str(row["evaluation_id"])))
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    package, output = args.package, args.output
    output.mkdir(parents=True, exist_ok=True)

    bundle_path = package / "OFFICIAL_148_SOURCE_BUNDLE.jsonl"
    manifest_path = package / "OFFICIAL_148_MANIFEST.jsonl"
    bundle_sha = sha256_file(bundle_path)
    labels_sha = sha256_file(args.labels)
    if bundle_sha != EXPECTED_BUNDLE_SHA256:
        raise ValueError(f"INPUT_BUNDLE_SHA256_MISMATCH:{bundle_sha}")
    if labels_sha != EXPECTED_LABELS_SHA256:
        raise ValueError(f"LABEL_SOURCE_SHA256_MISMATCH:{labels_sha}")

    bundle = read_jsonl(bundle_path)
    manifest = read_jsonl(manifest_path)
    auxiliary = json.loads(args.labels.read_text(encoding="utf-8"))

    scope = verify_scope(bundle)
    if not scope["scope_verified"]:
        raise ValueError(f"F0_SCOPE_MISMATCH:{scope['frozen_figure_mismatches']}")

    roster = roster_rows(bundle, team_labels(auxiliary))
    matrix = matrix_rows(bundle, manifest)
    unlabelled = [
        row["evaluation_id"] for row in roster
        if row["home_team_label"] == NOT_RECONSTRUCTIBLE
    ]
    statuses = collections.Counter(row["matrix_row_status"] for row in matrix)
    factor_matrix_status = (
        FACTOR_MATRIX_NOT_RECONSTRUCTIBLE
        if statuses[NOT_RECONSTRUCTIBLE] == len(matrix)
        else "PARTIALLY_RECONSTRUCTIBLE"
    )
    weight_calibration_status = (
        "BLOCKED_BY_FACTOR_MATRIX"
        if factor_matrix_status == FACTOR_MATRIX_NOT_RECONSTRUCTIBLE
        else "NOT_STARTED"
    )
    final_state = (
        "F0_ACCEPTED_F1_BLOCKED_BY_MATRIX"
        if weight_calibration_status == "BLOCKED_BY_FACTOR_MATRIX"
        else "F0_ACCEPTED_F1_READY"
    )

    write_jsonl(output / "OFFICIAL_148_LOSS_WIN_ROSTER.jsonl", roster)
    write_jsonl(output / "AH_84_FACTOR_MATRIX_READINESS.jsonl", matrix)

    result = {
        "schema_version": "w2.ah_factor_accuracy_f0_result.v1",
        "task_id": TASK_ID,
        "mainline_id": MAINLINE_ID,
        "current_phase": "F0",
        "next_phase": "F1",
        "base_commit": "15bc23cb937cbac7843017d442db813639869f16",
        "input_bundle_sha256": bundle_sha,
        "auxiliary_label_source_sha256": labels_sha,
        "auxiliary_label_source_role": "TEAM_DISPLAY_NAME_ONLY_NOT_A_MODEL_INPUT",
        "row_count": scope["row_count"],
        "distinct_fixture_count": scope["distinct_fixture_count"],
        "ah_count": scope["ah_count"],
        "totals_count": scope["totals_count"],
        "total_profit_units": scope["total_profit_units"],
        "ah_profit_units": scope["ah_profit_units"],
        "totals_profit_units": scope["totals_profit_units"],
        "settlement_counts": scope["settlement_counts"],
        "ah_settlement_counts": scope["ah_settlement_counts"],
        "totals_settlement_counts": scope["totals_settlement_counts"],
        "roster_rows": len(roster),
        "roster_rows_without_team_label": len(unlabelled),
        "ah_factor_scope_rows": sum(1 for row in roster if row["is_ah_factor_scope"]),
        "totals_out_of_factor_scope_rows": sum(
            1 for row in roster if not row["is_ah_factor_scope"]),
        "matrix_rows": len(matrix),
        "matrix_row_status_counts": dict(sorted(statuses.items())),
        "factor_matrix_status": factor_matrix_status,
        "f5_source_status": "NOT_INGESTED_POST_EVENT_SOURCE_NOT_PIT_PROVABLE",
        "weight_calibration_status": weight_calibration_status,
        "provider_calls": 0,
        "public_http_fetch": 0,
        "production_db_reads": 0,
        "production_db_writes": 0,
        "deployment_executed": False,
        "obsidian_writes": 0,
        "github_push": 0,
        "final_state": final_state,
    }
    (output / "F0_RESULT.json").write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8")
    print(json.dumps({
        "final_state": final_state,
        "factor_matrix_status": factor_matrix_status,
        "weight_calibration_status": weight_calibration_status,
        "roster_rows": len(roster),
        "matrix_rows": len(matrix),
        "matrix_row_status_counts": dict(sorted(statuses.items())),
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
