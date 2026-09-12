"""F0 scope and evidence freeze: what the frozen 148 do and do not support.

F0 fits nothing. These tests check two things and only two: that the frozen
scope figures are exactly what the order fixed them at, and that no factor value
is ever invented -- not as a zero, not from the current registry, and above all
not from the result.
"""
from __future__ import annotations

import ast
import collections
import importlib.util
import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
PACKAGE = REPO / "docs/review_packages/W2_OFFICIAL_CANDIDATE_ACCURACY_REMEDIATION_20260909"
OUTPUT = REPO / "docs/review_packages/W2_AH_FACTOR_ACCURACY_F0_20260910"
RUNNER_PATH = REPO / "scripts/quant/run_ah_factor_accuracy_f0.py"
LABELS = Path(
    "/Users/liudehua/Desktop/W2文档/evidence/W2_OFFICIAL_148_RAW_20260909"
    "/_raw_official_recommendations.json")

_spec = importlib.util.spec_from_file_location("w2_f0_runner", RUNNER_PATH)
assert _spec is not None and _spec.loader is not None
runner = importlib.util.module_from_spec(_spec)
sys.modules["w2_f0_runner"] = runner
_spec.loader.exec_module(runner)

NR = runner.NOT_RECONSTRUCTIBLE


@pytest.fixture(scope="module")
def bundle():  # type: ignore[no-untyped-def]
    return runner.read_jsonl(PACKAGE / "OFFICIAL_148_SOURCE_BUNDLE.jsonl")


@pytest.fixture(scope="module")
def roster():  # type: ignore[no-untyped-def]
    return runner.read_jsonl(OUTPUT / "OFFICIAL_148_LOSS_WIN_ROSTER.jsonl")


@pytest.fixture(scope="module")
def matrix():  # type: ignore[no-untyped-def]
    return runner.read_jsonl(OUTPUT / "AH_84_FACTOR_MATRIX_READINESS.jsonl")


# --- the frozen scope figures -------------------------------------------
def test_input_bundle_has_exactly_148_rows(bundle) -> None:
    assert len(bundle) == 148
    assert len({row["evaluation_id"] for row in bundle}) == 148
    assert len({row["fixture_id"] for row in bundle}) == 111


def test_market_split_is_84_ah_and_64_totals(bundle) -> None:
    markets = collections.Counter(row["market"] for row in bundle)

    assert markets["ASIAN_HANDICAP"] == 84
    assert markets["TOTALS"] == 64
    assert sum(markets.values()) == 148


def test_settlement_layers_are_the_frozen_ones(bundle) -> None:
    settlements = collections.Counter(row["settlement"] for row in bundle)

    assert settlements["LOSS"] == 66
    assert settlements["HALF_LOSS"] == 8
    assert settlements["WIN"] == 55
    assert settlements["HALF_WIN"] == 6
    assert settlements["PUSH"] == 13
    assert sum(settlements.values()) == 148


def test_ah_settlement_layers_are_the_frozen_ones(bundle) -> None:
    ah = collections.Counter(
        row["settlement"] for row in bundle if row["market"] == "ASIAN_HANDICAP")

    assert ah["LOSS"] == 34
    assert ah["HALF_LOSS"] == 8
    assert ah["WIN"] == 32
    assert ah["HALF_WIN"] == 6
    assert ah["PUSH"] == 4
    assert sum(ah.values()) == 84


def test_total_profit_is_unchanged(bundle) -> None:
    assert sum(Decimal(str(row["profit_units"])) for row in bundle) == Decimal("-20.375")


def test_the_scope_check_actually_stops_on_a_mismatch(bundle) -> None:
    """The verifier has to fail on a wrong corpus, or it verifies nothing."""
    assert runner.verify_scope(bundle)["scope_verified"] is True

    short = runner.verify_scope(bundle[:-1])

    assert short["scope_verified"] is False
    assert "row_count" in short["frozen_figure_mismatches"]


# --- the roster ---------------------------------------------------------
def test_roster_covers_all_148_and_filters_cleanly(roster) -> None:
    assert len(roster) == 148
    counts = collections.Counter(row["settlement"] for row in roster)
    assert dict(counts) == {
        "LOSS": 66, "HALF_LOSS": 8, "WIN": 55, "HALF_WIN": 6, "PUSH": 13}
    assert sum(1 for row in roster if row["is_ah_factor_scope"]) == 84
    assert sum(1 for row in roster if not row["is_ah_factor_scope"]) == 64


def test_every_roster_row_carries_the_required_fields(roster) -> None:
    required = {
        "evaluation_id", "fixture_id", "kickoff_utc", "home_team_label",
        "away_team_label", "market", "selection", "exact_line", "score",
        "settlement", "profit_units", "is_ah_factor_scope"}

    for row in roster:
        assert required <= set(row), row["evaluation_id"]
        assert row["home_team_label"] and row["away_team_label"]


def test_the_elche_real_sociedad_loss_is_present_and_exact(roster) -> None:
    row = next(row for row in roster if row["fixture_id"] == "1570366")

    assert row["kickoff_utc"] == "2026-09-07T19:30:00Z"
    assert row["home_team_label"] == "埃尔切"
    assert row["away_team_label"] == "皇家社会"
    assert (row["market"], row["selection"], str(row["exact_line"])) == (
        "ASIAN_HANDICAP", "HOME", "0.25")
    assert (row["score"], row["settlement"]) == ("2-3", "LOSS")
    assert row["is_ah_factor_scope"] is True


# --- the AH 84 factor matrix -------------------------------------------
def test_matrix_has_exactly_84_rows_one_per_ah_candidate(matrix, bundle) -> None:
    ah_ids = {row["evaluation_id"] for row in bundle if row["market"] == "ASIAN_HANDICAP"}

    assert len(matrix) == 84
    assert {row["evaluation_id"] for row in matrix} == ah_ids


def test_no_totals_row_reaches_the_factor_matrix(matrix, bundle) -> None:
    totals_ids = {row["evaluation_id"] for row in bundle if row["market"] == "TOTALS"}

    assert not totals_ids & {row["evaluation_id"] for row in matrix}
    assert len(totals_ids) == 64


@pytest.mark.parametrize("factor", ["f3", "f5", "f6", "f9"])
def test_every_missing_factor_cell_says_not_reconstructible(matrix, factor) -> None:
    for row in matrix:
        for suffix in ("score", "status", "weight", "participated",
                       "evidence_time", "source_hash"):
            assert row[f"{factor}_{suffix}"] == NR, (row["evaluation_id"], factor, suffix)


def test_a_missing_factor_is_never_written_as_zero(matrix) -> None:
    """Zero is a score. Absent is not a score. They must not be confused."""
    for row in matrix:
        for key, value in row.items():
            if any(part in key for part in ("score", "weight", "participated")):
                assert value not in (0, 0.0, "0", "0.0", False, None), (
                    row["evaluation_id"], key, value)


def test_every_row_is_classified_and_the_whole_matrix_is_not_reconstructible(
    matrix,
) -> None:
    allowed = {
        runner.EXACT_PIT_RECONSTRUCTIBLE,
        runner.SOURCE_ONLY_POST_CAPTURE,
        NR,
    }
    statuses = collections.Counter(row["matrix_row_status"] for row in matrix)

    assert set(statuses) <= allowed
    assert statuses[NR] == 84
    for row in matrix:
        assert row["not_estimable_reason"], row["evaluation_id"]


def test_the_frozen_evidence_really_holds_no_factor_identity() -> None:
    """The claim is about the evidence, so it is checked against the evidence."""
    manifest = runner.read_jsonl(PACKAGE / "OFFICIAL_148_MANIFEST.jsonl")

    for row in manifest:
        assert row["factor_disposition"] == "UNKNOWN_NOT_RECONSTRUCTIBLE"
        for key in ("factor_direction", "factor_weights", "factor_participants",
                    "factor_veto_code", "factor_verdict_identity",
                    "factor_absent_reasons"):
            assert row[key] == NR, (row["evaluation_id"], key)


def test_no_factor_value_can_be_derived_from_the_result() -> None:
    """A settlement-keyed factor value would be the leak this phase exists to stop."""
    tree = ast.parse(RUNNER_PATH.read_text(encoding="utf-8"))
    source = RUNNER_PATH.read_text(encoding="utf-8")

    factor_cells = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "factor_cells")

    # it takes the frozen row and nothing else -- no settlement, score or profit
    # parameter exists to key off
    assert {arg.arg for arg in factor_cells.args.args} == {"manifest_row"}

    # and it reads no field of that row at all: no subscript, no attribute, no
    # .get(). A factor value therefore cannot depend on anything in the row,
    # which is a stronger statement than "it does not read the result".
    reads = [
        node for node in ast.walk(factor_cells)
        if isinstance(node, ast.Subscript | ast.Attribute)
        and isinstance(getattr(node, "value", None), ast.Name)
        and node.value.id == "manifest_row"
    ]
    assert not reads, [ast.unparse(node) for node in reads]

    # every value it emits is the absence marker or a fixed factor name -- the
    # dict keys are field names, the values are what could carry a leaked number
    values = [
        node for dict_node in ast.walk(factor_cells)
        if isinstance(dict_node, ast.Dict)
        for node in dict_node.values
    ]
    assert values
    for node in values:
        rendered = ast.unparse(node)
        assert rendered in {"NOT_RECONSTRUCTIBLE", "FACTOR_NAMES[key]"}, rendered

    # and no current-registry weight is hard-coded anywhere in the runner
    for forbidden in ("0.3333", "0.1667", "33.33", "16.67", "0.10", "0.05"):
        assert forbidden not in source, forbidden


# --- determinism and input integrity ------------------------------------
def _run(output: Path) -> None:
    result = subprocess.run(  # noqa: S603
        [sys.executable, str(RUNNER_PATH), "--package", str(PACKAGE),
         "--labels", str(LABELS), "--output", str(output)],
        capture_output=True, text=True, check=False, cwd=REPO)
    assert result.returncode == 0, result.stdout + result.stderr


def test_two_runs_are_byte_identical(tmp_path) -> None:
    first, second = tmp_path / "a", tmp_path / "b"

    _run(first)
    _run(second)

    for name in ("OFFICIAL_148_LOSS_WIN_ROSTER.jsonl",
                 "AH_84_FACTOR_MATRIX_READINESS.jsonl", "F0_RESULT.json"):
        assert (first / name).read_bytes() == (second / name).read_bytes(), name
        assert (first / name).read_bytes() == (OUTPUT / name).read_bytes(), name


def test_the_input_bundle_hash_is_unchanged_by_running_f0(tmp_path) -> None:
    bundle_path = PACKAGE / "OFFICIAL_148_SOURCE_BUNDLE.jsonl"
    before = runner.sha256_file(bundle_path)

    _run(tmp_path / "c")

    assert runner.sha256_file(bundle_path) == before
    assert before == runner.EXPECTED_BUNDLE_SHA256


def test_the_input_package_still_verifies_against_its_own_hashes() -> None:
    result = subprocess.run(  # noqa: S603
        ["/usr/bin/shasum", "-a", "256", "-c", "HASHES.sha256"],
        cwd=PACKAGE, capture_output=True, text=True, check=False)

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count(": OK") == 13


def test_f0_result_records_the_blocked_terminal_state() -> None:
    result = json.loads((OUTPUT / "F0_RESULT.json").read_text(encoding="utf-8"))

    assert result["factor_matrix_status"] == "NOT_RECONSTRUCTIBLE_FROM_FROZEN_148"
    assert result["weight_calibration_status"] == "BLOCKED_BY_FACTOR_MATRIX"
    assert result["final_state"] == "F0_ACCEPTED_F1_BLOCKED_BY_MATRIX"
    assert result["final_state"] != "MODEL_CANDIDATE_READY"
    assert (result["row_count"], result["ah_count"], result["totals_count"]) == (
        148, 84, 64)
    assert result["provider_calls"] == 0
    assert result["production_db_reads"] == 0
    assert result["production_db_writes"] == 0
    assert result["deployment_executed"] is False
    assert result["obsidian_writes"] == 0


# --- boundaries ---------------------------------------------------------
def test_f0_makes_no_network_call_and_touches_no_database() -> None:
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


def test_f0_does_not_write_anywhere_but_its_own_output_directory() -> None:
    source = RUNNER_PATH.read_text(encoding="utf-8")

    assert source.count("write_text") == 1
    assert source.count(".open(\"w\"") == 1
    for forbidden in ("Obsidian", "/Users/", "W2文档", "Desktop"):
        assert forbidden not in source, forbidden


def test_f0_touches_no_production_path() -> None:
    """F0 reaches no production path -- by where its files are and by import.

    This used to read the whole working tree's `git status`, which made it a
    claim about *every* task sharing the checkout rather than about F0: any
    later task that legitimately has to edit a production file would fail a
    guard named after F0. The claim it was making is narrower, and is made
    directly here -- none of F0's deliverables sits under a production path, and
    nothing in production imports the F0 runner.
    """
    deliverables = (
        RUNNER_PATH,
        OUTPUT / "F0_RESULT.json",
        Path(__file__).resolve(),
    )
    for path in deliverables:
        relative = path.relative_to(REPO).as_posix()
        for prefix in (
            "src/w2/prematch/",
            "src/w2/strategy/",
            "src/w2/domain/",
            "src/w2/pricing/",
            "migrations/",
        ):
            assert not relative.startswith(prefix), relative
    hits = subprocess.run(  # noqa: S603
        ["/usr/bin/grep", "-rl", RUNNER_PATH.stem, str(REPO / "src/w2")],
        capture_output=True, text=True, check=False)

    assert not hits.stdout.strip(), hits.stdout
