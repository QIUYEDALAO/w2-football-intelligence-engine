"""F1 for AH-FACTOR-ACCURACY-V1: can the historical AH factor matrix be rebuilt?

Offline, read-only. This is a feasibility investigation, not a fitting task. It
registers every candidate source it found, states per source what it does and
does not carry, and emits the 84 x 4 matrix with each cell classified by what
the evidence actually supports.

Nothing here fills a missing value. A cell with no provable historical value
says so; a snapshot taken at some other instant is reported in its own clearly
named columns so it can never be mistaken for the value at evaluation.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

TASK_ID = "W2_AH_FACTOR_ACCURACY_F1_READINESS_20260910"
MAINLINE_ID = "AH-FACTOR-ACCURACY-V1"
PARENT_COMMIT = "f5dd9c23cf90cd836139bacbde559421f6dd59a2"
AH = "ASIAN_HANDICAP"
FACTORS = ("F3_REST_FITNESS", "F5_RECENT_AH_COVER", "F6_H2H", "F9_TRUE_XG")
EXPECTED_BUNDLE_SHA256 = (
    "da9edb11be8144991addeb1c6e83724d3cca083ca46b0bd8de2eaa6d45f6e7e4")

EXACT_PIT = "EXACT_PIT_RECONSTRUCTIBLE"
POST_CAPTURE = "SOURCE_ONLY_POST_CAPTURE"
NOT_RECONSTRUCTIBLE = "NOT_RECONSTRUCTIBLE"
INVENTORY_NAME = "F1_SOURCE_INVENTORY.jsonl"
MATRIX_NAME = "AH_84_FACTOR_MATRIX_F1.jsonl"

# Why a cell cannot be an exact historical value. Each is a fact established in
# F1_REPORT.md, not a judgement call made here.
REASON_NO_SOURCE = "NO_SOURCE_HOLDS_A_PRE_EVALUATION_FACTOR_VALUE_FOR_THIS_ROW"
REASON_POST_CAPTURE = "ONLY_SOURCE_WAS_CAPTURED_AT_OR_AFTER_EVALUATED_AT"
REASON_UNBOUND_SNAPSHOT = (
    "SNAPSHOT_PRECEDES_EVALUATED_AT_BUT_IS_A_DIFFERENT_OBSERVATION_INSTANT_"
    "WITH_NO_PER_FACTOR_EVIDENCE_TIME_AND_NO_EVALUATION_IDENTITY_BINDING")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def utc(value: object) -> datetime | None:
    """Parse to aware UTC, or None. Timestamps are never compared as text."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


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


def _stamp_from_name(name: str) -> datetime | None:
    """The capture instant these archives encode in their own filenames."""
    found = re.search(r"(\d{8})T(\d{6})Z", name)
    if not found:
        return None
    day, clock = found.groups()
    return utc(
        f"{day[:4]}-{day[4:6]}-{day[6:8]}T{clock[:2]}:{clock[2:4]}:{clock[4:6]}Z")


def _cards(node: Any):  # type: ignore[no-untyped-def]
    if isinstance(node, dict):
        if "factor_score" in node and "fixture_id" in node:
            yield node
        for value in node.values():
            yield from _cards(value)
    elif isinstance(node, list):
        for value in node:
            yield from _cards(value)


def _records(path: Path):  # type: ignore[no-untyped-def]
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix == ".jsonl":
        for line in text.splitlines():
            if line.strip():
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
        return
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError:
        return
    yield from (loaded if isinstance(loaded, list) else [loaded])


def scan_factor_archives(root: Path, ah_fixtures: set[str]) -> list[dict[str, Any]]:
    """Register every local archive that holds a factor_score for an AH fixture."""
    entries: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in {".json", ".jsonl"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "factor_score" not in text:
            continue
        captured = _stamp_from_name(path.name)
        observations: list[dict[str, Any]] = []
        # whether any card here binds to a dynamic evaluation identity; none do,
        # and the inventory records that as the reason no cell can be exact
        bound_to_evaluation = False
        for record in _records(path):
            for card in _cards(record):
                fixture_id = str(card.get("fixture_id"))
                if fixture_id not in ah_fixtures:
                    continue
                score = card.get("factor_score") or {}
                if "dqe-" in json.dumps(card.get("dynamic_prematch") or {}):
                    bound_to_evaluation = True
                participants = {
                    str(item.get("feature_id")): item
                    for item in (score.get("participants") or [])
                }
                absent = {
                    str(item.get("feature_id")): item
                    for item in (score.get("absent") or [])
                }
                observations.append({
                    "fixture_id": fixture_id,
                    "participants": participants,
                    "absent": absent,
                    "direction": score.get("direction"),
                    "weight_sum_used": score.get("weight_sum_used"),
                    "factor_veto": card.get("factor_veto"),
                })
        if not observations:
            continue
        entries.append({
            "source_path": str(path),
            "source_sha256": sha256_file(path),
            "captured_at_utc": captured.isoformat() if captured else None,
            "bound_to_evaluation_identity": bound_to_evaluation,
            "observations": observations,
        })
    return entries


def best_observation(
    archives: list[dict[str, Any]], fixture_id: str, evaluated_at: datetime
) -> tuple[dict[str, Any] | None, str]:
    """The latest archived observation strictly before evaluated_at, if any.

    Returns the observation and how it stands relative to the evaluation. A
    later capture is reported as post-capture rather than silently used.
    """
    before: list[tuple[datetime, dict[str, Any], dict[str, Any]]] = []
    after: list[tuple[datetime, dict[str, Any], dict[str, Any]]] = []
    for entry in archives:
        captured = utc(entry["captured_at_utc"])
        if captured is None:
            continue
        for observation in entry["observations"]:
            if observation["fixture_id"] != fixture_id:
                continue
            (before if captured < evaluated_at else after).append(
                (captured, entry, observation))
    if before:
        captured, entry, observation = max(before, key=lambda item: item[0])
        return (
            {**observation, "captured_at_utc": captured.isoformat(),
             "source_path": entry["source_path"],
             "source_sha256": entry["source_sha256"],
             "gap_hours": round(
                 (evaluated_at - captured).total_seconds() / 3600, 3)},
            "PRE_EVALUATION_SNAPSHOT",
        )
    if after:
        captured, entry, observation = min(after, key=lambda item: item[0])
        return (
            {**observation, "captured_at_utc": captured.isoformat(),
             "source_path": entry["source_path"],
             "source_sha256": entry["source_sha256"],
             "gap_hours": round(
                 (evaluated_at - captured).total_seconds() / 3600, 3)},
            "POST_EVALUATION_CAPTURE",
        )
    return None, "NO_ARCHIVE"


DIAGNOSIS_RELATIVE = Path(
    "docs/review_packages/V1_RECALIBRATION_EVIDENCE_01"
) / "SETTLED_CANDIDATE_INPUT_DIAGNOSIS.json"


def load_checkpoint_diagnosis(repo: Path) -> dict[str, dict[str, Any]]:
    """The one source that is keyed by our own evaluation_id.

    It carries a per-factor status block, but from `read_model_checkpoint`,
    which holds a single row per fixture and is overwritten on every
    re-projection. Its own `created_at` therefore describes a later refresh,
    not the state at evaluated_at, and it carries no weight, no participation
    and no per-factor evidence time.
    """
    path = repo / DIAGNOSIS_RELATIVE
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    digest = sha256_file(path)
    out: dict[str, dict[str, Any]] = {}
    for row in payload.get("rows") or []:
        checkpoint = row.get("latest_checkpoint_non_authoritative") or {}
        out[str(row.get("evaluation_id"))] = {
            "source_path": str(DIAGNOSIS_RELATIVE),
            "source_sha256": digest,
            "checkpoint_created_at": checkpoint.get("created_at"),
            "factor_status": checkpoint.get("factor_status") or {},
        }
    return out


def _checkpoint_status(checkpoint: dict[str, Any] | None, factor_id: str) -> str | None:
    if checkpoint is None:
        return None
    cell = checkpoint["factor_status"].get(factor_id) or {}
    return cell.get("status")


def matrix_rows(
    ah: list[dict[str, Any]],
    archives: list[dict[str, Any]],
    diagnosis: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for candidate in ah:
        evaluated_at = utc(candidate["evaluated_at"])
        assert evaluated_at is not None
        observation, stance = best_observation(
            archives, candidate["fixture_id"], evaluated_at)
        for factor_id in FACTORS:
            # Nothing in any source supplies a per-factor evidence time or an
            # evaluation-identity binding, so no cell can be an exact value.
            checkpoint = (diagnosis or {}).get(candidate["evaluation_id"])
            if checkpoint is not None:
                # A source keyed by this very evaluation exists, but the
                # checkpoint it read had already been overwritten by a later
                # projection, so it describes a state after evaluated_at. That
                # is the strongest provenance available and it is post-capture.
                status, reason = POST_CAPTURE, REASON_POST_CAPTURE
            elif observation is not None and stance == "POST_EVALUATION_CAPTURE":
                status, reason = POST_CAPTURE, REASON_POST_CAPTURE
            elif observation is not None:
                status, reason = NOT_RECONSTRUCTIBLE, REASON_UNBOUND_SNAPSHOT
            else:
                status, reason = NOT_RECONSTRUCTIBLE, REASON_NO_SOURCE
            snapshot: dict[str, Any] = {
                "snapshot_only_signed_score": None,
                "snapshot_only_weight": None,
                "snapshot_only_status": None,
                "snapshot_only_participated": None,
                "snapshot_capture_utc": None,
                "snapshot_gap_hours": None,
                "snapshot_stance": stance,
            }
            if observation is not None:
                participant = observation["participants"].get(factor_id)
                absent = observation["absent"].get(factor_id)
                snapshot.update({
                    # deliberately named snapshot_only_*: these are values from
                    # another instant, never the value used at evaluated_at
                    "snapshot_only_signed_score": (
                        participant.get("magnitude") if participant else None),
                    "snapshot_only_weight": (
                        participant.get("weight") if participant
                        else (absent or {}).get("weight")),
                    "snapshot_only_status": (
                        "PARTICIPATED" if participant
                        else (absent or {}).get("status")),
                    "snapshot_only_participated": bool(participant),
                    "snapshot_capture_utc": observation["captured_at_utc"],
                    "snapshot_gap_hours": observation["gap_hours"],
                })
            rows.append({
                "evaluation_id": candidate["evaluation_id"],
                "fixture_id": candidate["fixture_id"],
                "kickoff_utc": candidate["kickoff_utc"],
                "evaluated_at": candidate["evaluated_at"],
                "factor_id": factor_id,
                # the six historical fields F1 had to find. None was found.
                "signed_score": NOT_RECONSTRUCTIBLE,
                "factor_status": NOT_RECONSTRUCTIBLE,
                "original_weight": NOT_RECONSTRUCTIBLE,
                "participated": NOT_RECONSTRUCTIBLE,
                "evidence_time_utc": NOT_RECONSTRUCTIBLE,
                "source_path": (
                    checkpoint["source_path"] if checkpoint
                    else observation["source_path"] if observation
                    else NOT_RECONSTRUCTIBLE),
                "source_sha256": (
                    checkpoint["source_sha256"] if checkpoint
                    else observation["source_sha256"] if observation
                    else NOT_RECONSTRUCTIBLE),
                "provenance": (
                    "OVERWRITTEN_CHECKPOINT_READ_AFTER_EVALUATION" if checkpoint
                    else stance),
                "checkpoint_status_after_evaluation": _checkpoint_status(
                    checkpoint, factor_id),
                "checkpoint_read_at_utc": (
                    checkpoint["checkpoint_created_at"] if checkpoint else None),
                "pit_check": "FAILED_NO_PER_FACTOR_EVIDENCE_TIME",
                "row_status": status,
                "not_estimable_reason": reason,
                **snapshot,
            })
    rows.sort(key=lambda row: (str(row["kickoff_utc"]), str(row["evaluation_id"]),
                               str(row["factor_id"])))
    return rows


# Every candidate source examined, whether or not it survived. `covers` is
# measured against the AH 84, never asserted.
IN_REPO_SOURCES = (
    ("docs/review_packages/W2_OFFICIAL_CANDIDATE_ACCURACY_REMEDIATION_20260909"
     "/OFFICIAL_148_SOURCE_BUNDLE.jsonl", "FROZEN_CORPUS",
     "The candidate corpus itself. Carries no factor field of any kind.",
     "NO_FACTOR_FIELDS_PRESENT"),
    ("docs/review_packages/W2_OFFICIAL_CANDIDATE_ACCURACY_REMEDIATION_20260909"
     "/OFFICIAL_148_MANIFEST.jsonl", "FROZEN_CORPUS",
     "Carries factor_* keys, every one of them the literal NOT_RECONSTRUCTIBLE.",
     "FACTOR_FIELDS_PRESENT_BUT_ALL_MARKED_NOT_RECONSTRUCTIBLE"),
    ("docs/review_packages/V1_RECALIBRATION_EVIDENCE_01"
     "/SETTLED_CANDIDATE_INPUT_DIAGNOSIS.json", "EVALUATION_KEYED_DIAGNOSIS",
     "Keyed by our evaluation_id; per-factor status from read_model_checkpoint, "
     "whose single row per fixture had already been overwritten by a later "
     "projection. No score, no weight, no participation, no evidence time.",
     "POST_CAPTURE_STATUS_ONLY"),
    ("docs/review_packages/V1_RECALIBRATION_EVIDENCE_01"
     "/SETTLED_CANDIDATE_DIRECTION_RESCORE.json", "EVALUATION_KEYED_DIAGNOSIS",
     "Direction rescore over the same candidates. Contains no factor identifier "
     "at all; it rescore from model and market, not from factors.",
     "NO_FACTOR_FIELDS_PRESENT"),
    ("config/factors/factor_registry.v1.json", "REGISTRY",
     "Factor lifecycle, roles and market applicability. Carries no numeric "
     "weight and no per-match value.",
     "REGISTRY_METADATA_ONLY_NO_PER_MATCH_VALUE"),
    ("docs/review_packages/SC21_FACTOR_INPUT_CHAIN"
     "/SC21_FACTOR_ROLE_AUTHORITY_MATRIX.json", "REGISTRY",
     "Factor role authority. No per-match value.",
     "REGISTRY_METADATA_ONLY_NO_PER_MATCH_VALUE"),
    ("src/w2/features/team_factors.py", "SOURCE_CODE_DEFAULT",
     "F3/F5/F6 weight defaults as code constants, unchanged since 2026-07-25, "
     "before every one of the 148 evaluations. This is the declared default, "
     "not proof of the weight actually applied to any given evaluation.",
     "DEFAULT_WEIGHT_ONLY_NOT_APPLIED_WEIGHT"),
    ("src/w2/features/live_factors.py", "SOURCE_CODE_DEFAULT",
     "F9 weight default, same standing as above.",
     "DEFAULT_WEIGHT_ONLY_NOT_APPLIED_WEIGHT"),
)


def _any_non_null_factor_score(
    diagnosis: dict[str, dict[str, Any]], ah_ids: set[str]
) -> bool:
    """Whether the checkpoint diagnosis actually carries any of the four scores."""
    for evaluation_id, entry in diagnosis.items():
        if evaluation_id not in ah_ids:
            continue
        for factor_id in FACTORS:
            if (entry["factor_status"].get(factor_id) or {}).get("score") is not None:
                return True
    return False


def inventory_rows(
    repo: Path, archives: list[dict[str, Any]], ah: list[dict[str, Any]],
    diagnosis: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    ah_ids = {row["evaluation_id"] for row in ah}
    ah_fixtures = {row["fixture_id"] for row in ah}
    rows: list[dict[str, Any]] = []

    def entry(**fields: Any) -> dict[str, Any]:
        base = {
            "covered_evaluation_ids": 0, "covered_ah_fixtures": 0,
            "covered_factors": [], "has_signed_score": False,
            "has_original_weight": False, "has_participated": False,
            "has_evidence_time": False, "has_source_identity": False,
            "proves_evidence_time_before_evaluated_at": False,
        }
        base.update(fields)
        return base

    for path_text, source_type, conclusion, exclusion in IN_REPO_SOURCES:
        path = repo / path_text
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        covered = sum(1 for i in ah_ids if i in text)
        rows.append(entry(
            source_path=path_text, source_type=source_type,
            source_sha256=sha256_file(path),
            source_commit_or_generated_at="IN_GIT_AT_PARENT_COMMIT",
            covered_evaluation_ids=covered,
            covered_ah_fixtures=sum(1 for f in ah_fixtures if f in text),
            covered_factors=[f for f in FACTORS if f in text],
            # measured, not inferred from the schema: the diagnosis has a score
            # key for every factor and every one of those values is null
            has_signed_score=(
                source_type == "EVALUATION_KEYED_DIAGNOSIS"
                and _any_non_null_factor_score(diagnosis, ah_ids)),
            has_original_weight=source_type == "SOURCE_CODE_DEFAULT",
            has_source_identity=source_type == "EVALUATION_KEYED_DIAGNOSIS",
            proves_evidence_time_before_evaluated_at=(
                source_type == "SOURCE_CODE_DEFAULT"),
            conclusion=conclusion, exclusion_reason=exclusion,
        ))

    for archive in archives:
        fixtures = {o["fixture_id"] for o in archive["observations"]}
        factors = sorted({
            fid for o in archive["observations"]
            for fid in list(o["participants"]) + list(o["absent"])
            if fid in FACTORS
        })
        rows.append(entry(
            source_path=archive["source_path"],
            source_type="PREMATCH_ANALYSIS_CARD_ARCHIVE",
            source_sha256=archive["source_sha256"],
            source_commit_or_generated_at=archive["captured_at_utc"],
            covered_evaluation_ids=0,
            covered_ah_fixtures=len(fixtures),
            covered_factors=factors,
            has_signed_score=True, has_original_weight=True,
            has_participated=True, has_evidence_time=False,
            has_source_identity=archive["bound_to_evaluation_identity"],
            proves_evidence_time_before_evaluated_at=False,
            conclusion=(
                "A real pre-match factor_score with signed magnitude, weight and "
                "participation, but only a file-level capture instant, no "
                "per-factor evidence time, and no dynamic-evaluation binding."),
            exclusion_reason="UNBOUND_SNAPSHOT_NO_PER_FACTOR_EVIDENCE_TIME",
        ))

    rows.append(entry(
        source_path="<production PostgreSQL>", source_type="PRODUCTION_DATABASE",
        source_sha256="NOT_ACCESSED", source_commit_or_generated_at="NOT_ACCESSED",
        conclusion=(
            "Not accessed. This order sets PRODUCTION_DB_READS = 0. Independently, "
            "read_model_checkpoint holds one row per checkpoint_key and is "
            "overwritten in place, so the pre-match factor_score for these "
            "fixtures no longer exists there to be read."),
        exclusion_reason="FORBIDDEN_BY_ORDER_AND_OVERWRITTEN_BY_DESIGN",
    ))
    rows.append(entry(
        source_path="W2-workspaces/*/.local/w2.db", source_type="LOCAL_SQLITE",
        source_sha256=(
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
        source_commit_or_generated_at="EMPTY_FILE",
        conclusion="Seven local development databases, all zero bytes, no tables.",
        exclusion_reason="EMPTY_NO_ROWS",
    ))
    rows.sort(key=lambda row: (row["source_type"], row["source_path"]))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    # Provenance only: rebuilds the committed archive index from the local
    # evidence tree. The assessment itself runs from the committed index.
    parser.add_argument("--scan", type=Path, default=None)
    args = parser.parse_args()
    output = args.output
    output.mkdir(parents=True, exist_ok=True)

    bundle_path = args.package / "OFFICIAL_148_SOURCE_BUNDLE.jsonl"
    bundle_sha = sha256_file(bundle_path)
    if bundle_sha != EXPECTED_BUNDLE_SHA256:
        raise ValueError(f"INPUT_BUNDLE_SHA256_MISMATCH:{bundle_sha}")
    bundle = read_jsonl(bundle_path)
    ah = sorted(
        (row for row in bundle if row["market"] == AH),
        key=lambda row: (str(row["kickoff_utc"]), str(row["evaluation_id"])))
    if len(ah) != 84:
        raise ValueError(f"AH_ROW_COUNT_UNEXPECTED:{len(ah)}")
    ah_fixtures = {row["fixture_id"] for row in ah}

    index_path = output / "F1_FACTOR_ARCHIVE_INDEX.json"
    if args.scan is not None:
        archives = scan_factor_archives(args.scan, ah_fixtures)
        index_path.write_text(
            json.dumps({"schema_version": "w2.f1_factor_archive_index.v1",
                        "archives": archives},
                       ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8")
    archives = json.loads(index_path.read_text(encoding="utf-8"))["archives"]

    diagnosis = load_checkpoint_diagnosis(Path(__file__).resolve().parents[2])
    rows = matrix_rows(ah, archives, diagnosis)
    repo = Path(__file__).resolve().parents[2]
    inventory = inventory_rows(repo, archives, ah, diagnosis)
    write_jsonl(output / INVENTORY_NAME, inventory)
    statuses = collections.Counter(row["row_status"] for row in rows)
    exact = statuses[EXACT_PIT]
    final_state = (
        "F1_MATRIX_READY_FOR_F2" if exact == 336
        else "F1_PARTIAL_SOURCE_NOT_SUFFICIENT" if exact
        else "F1_NOT_RECONSTRUCTIBLE_FROM_FROZEN_148"
    )
    write_jsonl(output / MATRIX_NAME, rows)

    result = {
        "schema_version": "w2.ah_factor_accuracy_f1_result.v1",
        "task_id": TASK_ID,
        "mainline_id": MAINLINE_ID,
        "parent_commit": PARENT_COMMIT,
        "input_bundle_sha256": bundle_sha,
        "ah_rows": len(ah),
        "factor_count": len(FACTORS),
        "matrix_rows": len(rows),
        "exact_pit_rows": exact,
        "post_capture_rows": statuses[POST_CAPTURE],
        "not_reconstructible_rows": statuses[NOT_RECONSTRUCTIBLE],
        "row_status_counts": dict(sorted(statuses.items())),
        "ah_fixtures_with_any_registered_source": len({
            row["fixture_id"] for row in rows
            if row["source_path"] != NOT_RECONSTRUCTIBLE}),
        "ah_fixtures_with_a_prematch_factor_archive": len({
            row["fixture_id"] for row in rows
            if row["snapshot_capture_utc"] is not None}),
        "ah_fixtures_total": len(ah_fixtures),
        "source_count": len(inventory),
        "ah_rows_with_evaluation_keyed_checkpoint_source": len(
            {row["evaluation_id"] for row in rows
             if row["checkpoint_read_at_utc"] is not None}),
        "f2_allowed": exact == 336,
        "f3_allowed": exact == 336,
        "weight_calibration_status": (
            "READY" if exact == 336 else "BLOCKED_BY_MATRIX"),
        "provider_calls": 0,
        "public_http_fetch": 0,
        "production_db_reads": 0,
        "production_db_writes": 0,
        "deployment_executed": False,
        "obsidian_writes": 0,
        "final_state": final_state,
    }
    (output / "F1_RESULT.json").write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8")
    print(json.dumps({
        "final_state": final_state,
        "matrix_rows": len(rows),
        "row_status_counts": dict(sorted(statuses.items())),
        "ah_fixtures_with_any_registered_source": (
            result["ah_fixtures_with_any_registered_source"]),
        "ah_fixtures_with_a_prematch_factor_archive": (
            result["ah_fixtures_with_a_prematch_factor_archive"]),
        "f2_allowed": result["f2_allowed"],
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
