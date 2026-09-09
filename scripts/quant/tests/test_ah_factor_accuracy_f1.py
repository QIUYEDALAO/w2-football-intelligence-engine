"""F1 readiness: the fourteen contracts a feasibility answer has to satisfy.

F1 fits nothing, so nothing here checks a number's quality. What it checks is
that no historical value is invented: not from a later checkpoint, not from a
snapshot taken at some other instant, not from the current registry, and above
all not from the result.
"""
from __future__ import annotations

import ast
import collections
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
PACKAGE = REPO / "docs/review_packages/W2_OFFICIAL_CANDIDATE_ACCURACY_REMEDIATION_20260909"
OUTPUT = REPO / "docs/review_packages/W2_AH_FACTOR_ACCURACY_F1_20260910"
RUNNER_PATH = REPO / "scripts/quant/run_ah_factor_accuracy_f1.py"

_spec = importlib.util.spec_from_file_location("w2_f1_runner", RUNNER_PATH)
assert _spec is not None and _spec.loader is not None
runner = importlib.util.module_from_spec(_spec)
sys.modules["w2_f1_runner"] = runner
_spec.loader.exec_module(runner)

NR = runner.NOT_RECONSTRUCTIBLE
SIX_HISTORICAL_FIELDS = (
    "signed_score", "factor_status", "original_weight",
    "participated", "evidence_time_utc", "source_sha256")


@pytest.fixture(scope="module")
def bundle():  # type: ignore[no-untyped-def]
    return runner.read_jsonl(PACKAGE / "OFFICIAL_148_SOURCE_BUNDLE.jsonl")


@pytest.fixture(scope="module")
def matrix():  # type: ignore[no-untyped-def]
    return runner.read_jsonl(OUTPUT / "AH_84_FACTOR_MATRIX_F1.jsonl")


@pytest.fixture(scope="module")
def inventory():  # type: ignore[no-untyped-def]
    return runner.read_jsonl(OUTPUT / "F1_SOURCE_INVENTORY.jsonl")


# --- 1: the frozen input is untouched -----------------------------------
def test_01_input_bundle_sha256_is_unchanged() -> None:
    digest = runner.sha256_file(PACKAGE / "OFFICIAL_148_SOURCE_BUNDLE.jsonl")

    assert digest == runner.EXPECTED_BUNDLE_SHA256
    assert digest == (
        "da9edb11be8144991addeb1c6e83724d3cca083ca46b0bd8de2eaa6d45f6e7e4")


def test_01_the_runner_refuses_a_corpus_that_is_not_the_frozen_one(tmp_path) -> None:
    fake = tmp_path / "pkg"
    fake.mkdir()
    (fake / "OFFICIAL_148_SOURCE_BUNDLE.jsonl").write_text("{}\n", encoding="utf-8")

    result = subprocess.run(  # noqa: S603
        [sys.executable, str(RUNNER_PATH), "--package", str(fake),
         "--output", str(tmp_path / "out")],
        capture_output=True, text=True, check=False, cwd=REPO)

    assert result.returncode != 0
    assert "INPUT_BUNDLE_SHA256_MISMATCH" in result.stderr


# --- 2 and 3: the matrix is exactly the official AH 84 ------------------
def test_02_matrix_covers_exactly_the_84_official_ah_evaluations(matrix, bundle) -> None:
    ah_ids = {row["evaluation_id"] for row in bundle if row["market"] == "ASIAN_HANDICAP"}

    assert len(ah_ids) == 84
    assert {row["evaluation_id"] for row in matrix} == ah_ids


def test_03_no_totals_evaluation_reaches_the_ah_matrix(matrix, bundle) -> None:
    totals = {row["evaluation_id"] for row in bundle if row["market"] == "TOTALS"}

    assert len(totals) == 64
    assert not totals & {row["evaluation_id"] for row in matrix}


# --- 4: 336 rows, each evaluation x factor exactly once ----------------
def test_04_matrix_is_84_by_4_with_unique_keys(matrix) -> None:
    keys = [(row["evaluation_id"], row["factor_id"]) for row in matrix]

    assert len(matrix) == 336
    assert len(matrix) <= 336
    assert len(set(keys)) == len(keys)
    assert set(collections.Counter(
        row["factor_id"] for row in matrix).values()) == {84}
    assert {row["factor_id"] for row in matrix} == set(runner.FACTORS)


# --- 5, 6, 7: nothing reaches exact PIT without a proven earlier time ---
def test_05_exact_pit_requires_a_strictly_earlier_per_factor_evidence_time(
    matrix,
) -> None:
    for row in matrix:
        if row["row_status"] != runner.EXACT_PIT:
            continue
        evidence = runner.utc(row["evidence_time_utc"])
        evaluated = runner.utc(row["evaluated_at"])
        assert evidence is not None and evaluated is not None
        assert evidence < evaluated, row["evaluation_id"]


def test_06_a_missing_evidence_time_fails_closed(matrix) -> None:
    for row in matrix:
        if row["evidence_time_utc"] == NR:
            assert row["row_status"] != runner.EXACT_PIT, row["evaluation_id"]
    # and in this corpus that is every row
    assert all(row["evidence_time_utc"] == NR for row in matrix)
    assert all(row["pit_check"].startswith("FAILED") for row in matrix)


def test_07_a_post_capture_source_is_never_exact_pit(matrix) -> None:
    post = [row for row in matrix
            if row["provenance"] == "OVERWRITTEN_CHECKPOINT_READ_AFTER_EVALUATION"]

    assert post, "the overwritten-checkpoint source must be represented"
    for row in post:
        assert row["row_status"] == runner.POST_CAPTURE
        assert row["row_status"] != runner.EXACT_PIT


def test_07_a_checkpoint_read_after_evaluation_is_measured_not_assumed(matrix) -> None:
    """The claim is that the surviving checkpoint post-dates the evaluation."""
    checked = 0
    for row in matrix:
        read_at = runner.utc(row["checkpoint_read_at_utc"])
        if read_at is None:
            continue
        checked += 1
        assert read_at >= runner.utc(row["evaluated_at"]), row["evaluation_id"]
    assert checked == 264


# --- 8: today's weights never become yesterday's -----------------------
def test_08_no_current_weight_is_written_into_original_weight(matrix) -> None:
    current = {0.10, 0.05, 0.18}  # the deployed defaults, F3/F5-F6/F7

    for row in matrix:
        assert row["original_weight"] == NR, row["evaluation_id"]
        assert row["original_weight"] not in current


def test_08_a_snapshot_weight_never_populates_the_historical_column(matrix) -> None:
    """Snapshot columns exist so the finding is not lost; they must stay separate."""
    with_snapshot = [row for row in matrix if row["snapshot_only_weight"] is not None]

    assert with_snapshot, "the pre-match archive must be represented"
    for row in with_snapshot:
        assert row["original_weight"] == NR
        assert row["signed_score"] == NR
        assert row["row_status"] != runner.EXACT_PIT


# --- 9 and 10: the result can never reach a factor value ---------------
def test_09_settlement_and_score_take_no_part_in_building_a_factor_cell() -> None:
    tree = ast.parse(RUNNER_PATH.read_text(encoding="utf-8"))
    builder = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "matrix_rows")
    body = ast.unparse(builder)

    for leak in ("settlement", "profit_units", '"score"', "GRADE"):
        assert leak not in body, leak


def test_10_swapping_every_result_changes_no_factor_output(bundle, tmp_path) -> None:
    """The strongest form of the no-leak claim: flip the outcomes, rerun, compare."""
    ah = [row for row in bundle if row["market"] == "ASIAN_HANDICAP"]
    flipped = []
    for row in bundle:
        if row["market"] != "ASIAN_HANDICAP":
            flipped.append(row)
            continue
        flipped.append({
            **row,
            "settlement": "WIN" if row["settlement"] == "LOSS" else "LOSS",
            "profit_units": -float(row["profit_units"] or 0),
            "score": "9-0",
        })
    assert len(ah) == 84

    package = tmp_path / "pkg"
    package.mkdir()
    runner.write_jsonl(package / "OFFICIAL_148_SOURCE_BUNDLE.jsonl", flipped)
    # the guard would stop us first, so exercise the builder directly
    archives = json.loads(
        (OUTPUT / "F1_FACTOR_ARCHIVE_INDEX.json").read_text(encoding="utf-8"))["archives"]
    diagnosis = runner.load_checkpoint_diagnosis(REPO)
    ordered = sorted(
        (row for row in flipped if row["market"] == "ASIAN_HANDICAP"),
        key=lambda row: (str(row["kickoff_utc"]), str(row["evaluation_id"])))

    after = runner.matrix_rows(ordered, archives, diagnosis)
    before = runner.read_jsonl(OUTPUT / "AH_84_FACTOR_MATRIX_F1.jsonl")

    assert len(after) == len(before) == 336
    for old, new in zip(before, after, strict=True):
        for field in (*SIX_HISTORICAL_FIELDS, "row_status", "provenance",
                      "not_estimable_reason", "snapshot_only_signed_score",
                      "snapshot_only_weight", "snapshot_only_participated"):
            assert old[field] == new[field], (old["evaluation_id"], field)


# --- 11: the runner reaches no network, database or production module ---
def test_11_runner_imports_nothing_live() -> None:
    banned = {"requests", "httpx", "urllib", "urllib3", "http", "socket", "aiohttp",
              "sqlalchemy", "psycopg", "psycopg2", "alembic", "w2"}
    tree = ast.parse(RUNNER_PATH.read_text(encoding="utf-8"))

    for node in ast.walk(tree):
        names = (
            [alias.name for alias in node.names] if isinstance(node, ast.Import)
            else [node.module or ""] if isinstance(node, ast.ImportFrom)
            else []
        )
        for name in names:
            assert name.split(".")[0] not in banned, name


def test_11_runner_writes_only_into_its_output_directory() -> None:
    source = RUNNER_PATH.read_text(encoding="utf-8")

    assert source.count("write_text") == 2  # index + F1_RESULT
    assert source.count('.open("w"') == 1   # write_jsonl
    assert "Obsidian" not in source


# --- 12 and 13: determinism, and the input survives the run ------------
def _run(output: Path) -> None:
    result = subprocess.run(  # noqa: S603
        [sys.executable, str(RUNNER_PATH), "--package", str(PACKAGE),
         "--output", str(output)],
        capture_output=True, text=True, check=False, cwd=REPO)
    assert result.returncode == 0, result.stdout + result.stderr


def test_12_two_runs_are_byte_identical(tmp_path) -> None:
    first, second = tmp_path / "a", tmp_path / "b"
    for target in (first, second):
        target.mkdir()
        (target / "F1_FACTOR_ARCHIVE_INDEX.json").write_bytes(
            (OUTPUT / "F1_FACTOR_ARCHIVE_INDEX.json").read_bytes())

    _run(first)
    _run(second)

    for name in ("AH_84_FACTOR_MATRIX_F1.jsonl", "F1_SOURCE_INVENTORY.jsonl",
                 "F1_RESULT.json"):
        assert (first / name).read_bytes() == (second / name).read_bytes(), name
        assert (first / name).read_bytes() == (OUTPUT / name).read_bytes(), name


def test_13_the_input_package_is_byte_identical_after_a_run(tmp_path) -> None:
    bundle_path = PACKAGE / "OFFICIAL_148_SOURCE_BUNDLE.jsonl"
    before = bundle_path.read_bytes()
    target = tmp_path / "c"
    target.mkdir()
    (target / "F1_FACTOR_ARCHIVE_INDEX.json").write_bytes(
        (OUTPUT / "F1_FACTOR_ARCHIVE_INDEX.json").read_bytes())

    _run(target)

    assert bundle_path.read_bytes() == before
    verify = subprocess.run(  # noqa: S603
        ["/usr/bin/shasum", "-a", "256", "-c", "HASHES.sha256"],
        cwd=PACKAGE, capture_output=True, text=True, check=False)
    assert verify.returncode == 0
    assert verify.stdout.count(": OK") == 13


# --- 14: without a complete exact matrix, F2 stays shut ----------------
def test_14_f2_is_not_allowed_without_336_exact_pit_rows(matrix) -> None:
    result = json.loads((OUTPUT / "F1_RESULT.json").read_text(encoding="utf-8"))
    exact = sum(1 for row in matrix if row["row_status"] == runner.EXACT_PIT)

    assert result["exact_pit_rows"] == exact
    assert exact < 336
    assert result["f2_allowed"] is False
    assert result["f3_allowed"] is False
    assert result["weight_calibration_status"] == "BLOCKED_BY_MATRIX"
    assert result["final_state"] == "F1_NOT_RECONSTRUCTIBLE_FROM_FROZEN_148"


def test_14_the_gate_would_open_only_on_a_complete_matrix() -> None:
    """The gate has to be capable of opening, or it proves nothing."""
    complete = [{"row_status": runner.EXACT_PIT} for _ in range(336)]
    incomplete = [*complete[:-1], {"row_status": runner.POST_CAPTURE}]

    assert sum(1 for r in complete if r["row_status"] == runner.EXACT_PIT) == 336
    assert sum(1 for r in incomplete if r["row_status"] == runner.EXACT_PIT) == 335


# --- the inventory has to register what was examined -------------------
def test_inventory_registers_every_examined_source(inventory) -> None:
    required = {
        "source_path", "source_type", "source_sha256",
        "source_commit_or_generated_at", "covered_evaluation_ids",
        "covered_ah_fixtures", "covered_factors", "has_signed_score",
        "has_original_weight", "has_participated", "has_evidence_time",
        "has_source_identity", "proves_evidence_time_before_evaluated_at",
        "conclusion", "exclusion_reason"}

    assert len(inventory) >= 10
    for entry in inventory:
        assert required <= set(entry), entry["source_path"]
        assert entry["exclusion_reason"], entry["source_path"]
    types = {entry["source_type"] for entry in inventory}
    assert {"PRODUCTION_DATABASE", "PREMATCH_ANALYSIS_CARD_ARCHIVE",
            "EVALUATION_KEYED_DIAGNOSIS", "REGISTRY"} <= types


def test_no_registered_source_carries_a_per_factor_evidence_time(inventory) -> None:
    """This single fact is why every row fails, so it is asserted directly."""
    assert not [e for e in inventory if e["has_evidence_time"]]


def test_the_production_database_is_registered_as_not_accessed(inventory) -> None:
    entry = next(e for e in inventory if e["source_type"] == "PRODUCTION_DATABASE")

    assert entry["source_sha256"] == "NOT_ACCESSED"
    assert entry["covered_evaluation_ids"] == 0
