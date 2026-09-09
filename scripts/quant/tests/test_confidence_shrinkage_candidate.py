"""GLOBAL_ROLLING_CONFIDENCE_SHRINKAGE_V1: the eighteen contracts it must hold.

The candidate is allowed to change how confident a distribution is. Everything
else -- the side, the line, the odds, the factor verdict, the settlement, the
recorded result, and above all what it was allowed to know when -- must come out
of the run exactly as it went in.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import math
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from w2.domain.five_state_pricing import (
    PROBABILITY_TOLERANCE,
    SettlementDistribution,
    expected_value,
)

REPO = Path(__file__).resolve().parents[3]
PACKAGE = REPO / "docs/review_packages/W2_OFFICIAL_CANDIDATE_ACCURACY_REMEDIATION_20260909"
RUNNER_PATH = REPO / "scripts/quant/run_official_candidate_accuracy_optimization.py"
CANDIDATE_PATH = REPO / "scripts/quant/official_candidate_confidence_shrinkage.py"


def _load(name: str, path: Path):  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# both live outside src/w2 and are loaded by path, so nothing in the production
# tree can import them even by accident
candidate = _load("w2_confidence_shrinkage_under_test", CANDIDATE_PATH)
runner = _load("w2_optimization_runner", RUNNER_PATH)

FLAT = {"WIN": 0.5, "HALF_WIN": 0.0, "PUSH": 0.05, "HALF_LOSS": 0.0, "LOSS": 0.45}


@pytest.fixture(scope="module")
def rows():  # type: ignore[no-untyped-def]
    return runner.load_rows(PACKAGE)


@pytest.fixture(scope="module")
def applied(rows):  # type: ignore[no-untyped-def]
    return candidate.apply_candidate(rows)


def _row(evaluation_id: str, *, evaluated_at: str, result_available_at: str | None,
         settlement: str = "WIN", market: str = "ASIAN_HANDICAP",
         fixture_id: str = "f1", dist: dict | None = None) -> dict:
    return {
        "evaluation_id": evaluation_id, "fixture_id": fixture_id, "market": market,
        "selection": "HOME", "exact_line": -0.25, "decimal_odds": 1.91,
        "kickoff_utc": evaluated_at, "evaluated_at": evaluated_at,
        "result_available_at": result_available_at, "settlement": settlement,
        "profit_units": "0.91", "dist": dict(dist or FLAT),
    }


# --- 1: the incumbent arm reproduces the frozen package exactly --------------
def test_01_incumbent_metrics_reproduce_the_frozen_package(applied) -> None:
    frozen = json.loads((PACKAGE / "CALIBRATION_COMPARISON.json").read_text())

    for segment in ("ALL_148", "FIRST_138", "LAST_10_INCIDENT_REPLAY"):
        records = runner.segments_of(applied)[segment]
        got = runner.model_metrics(records, "incumbent_dist")
        want = frozen["segments"][segment]["INCUMBENT"]
        assert got["rows"] == want["emitted"], segment
        assert got["five_state_log_loss"] == want["five_state_log_loss"], segment
        assert got["multiclass_brier"] == want["multiclass_brier"], segment
        assert got["calibration_error"] == want["calibration_error"], segment
        assert got["predicted_graded_rate"] == want["predicted_graded_rate"], segment


def test_01_the_corpus_itself_is_the_accepted_one(rows) -> None:
    assert len(rows) == 148
    assert len({row["fixture_id"] for row in rows}) == 111
    assert sum(Decimal(str(row["profit_units"])) for row in rows) == Decimal("-20.375")


# --- 2: only history that was authoritatively settled may train -------------
def test_02_training_uses_only_results_settled_before_evaluation(applied) -> None:
    ordered = sorted(applied, key=candidate.temporal_key)
    for index, row in enumerate(ordered):
        evaluated = candidate.utc(row["evaluated_at"])
        eligible = [
            other for other in ordered[:index]
            if candidate.is_training_evidence(other, row)
        ]
        assert row["training_rows"] == len(eligible)
        for other in eligible:
            assert candidate.utc(other["result_available_at"]) < evaluated
        # nothing at or after the cutoff, and nothing later in the corpus
        for later in ordered[index:]:
            assert not candidate.is_training_evidence(later, row) or (
                candidate.utc(later["result_available_at"]) < evaluated
            )


def test_02_a_future_result_is_never_training_evidence() -> None:
    subject = _row("s", evaluated_at="2026-08-20T12:00:00Z", result_available_at=None)

    assert candidate.is_training_evidence(
        _row("past", evaluated_at="2026-08-19T00:00:00Z",
             result_available_at="2026-08-19T20:00:00Z"), subject) is True
    assert candidate.is_training_evidence(
        _row("future", evaluated_at="2026-08-19T00:00:00Z",
             result_available_at="2026-08-20T20:00:00Z"), subject) is False
    assert candidate.is_training_evidence(
        _row("same", evaluated_at="2026-08-19T00:00:00Z",
             result_available_at="2026-08-20T12:00:00Z"), subject) is False


def test_02_the_global_fit_pools_markets_but_not_time() -> None:
    """Unlike the incumbent, a TOTALS result may train an AH row -- if it is past."""
    ah = _row("ah", evaluated_at="2026-08-20T12:00:00Z", result_available_at=None)
    totals_past = _row("t", evaluated_at="2026-08-19T00:00:00Z", market="TOTALS",
                       result_available_at="2026-08-19T20:00:00Z")
    totals_future = _row("t2", evaluated_at="2026-08-19T00:00:00Z", market="TOTALS",
                         result_available_at="2026-08-21T20:00:00Z")

    assert candidate.is_training_evidence(totals_past, ah) is True
    assert candidate.is_training_evidence(totals_future, ah) is False


# --- 3 and 4: timestamp spellings, and failing closed on nonsense -----------
@pytest.mark.parametrize(("value", "expected"), [
    ("2026-08-20 02:36:31.442008+00", "2026-08-20T02:36:31.442008+00:00"),
    ("2026-08-20T02:36:31.442008Z", "2026-08-20T02:36:31.442008+00:00"),
    ("2026-08-20T02:36:31.442008+00:00", "2026-08-20T02:36:31.442008+00:00"),
    ("2026-08-20T11:36:31.442008+09:00", "2026-08-20T02:36:31.442008+00:00"),
    ("2026-08-19T21:36:31.442008-05:00", "2026-08-20T02:36:31.442008+00:00"),
    ("2026-08-20 02:36:31.442008", "2026-08-20T02:36:31.442008+00:00"),
])
def test_03_every_spelling_normalises_to_one_utc_instant(value, expected) -> None:
    parsed = candidate.utc(value)

    assert parsed is not None and parsed.tzinfo is not None
    assert parsed.isoformat() == expected


def test_03_space_and_T_spellings_are_not_compared_as_text() -> None:
    available = "2026-08-20 02:36:31.442008+00"
    evaluated = "2026-08-20T00:22:32.149069Z"

    assert str(available) < str(evaluated), "text comparison would admit this"
    assert candidate.utc(available) > candidate.utc(evaluated)
    assert candidate.is_training_evidence(
        _row("o", evaluated_at="2026-08-01T00:00:00Z", result_available_at=available),
        _row("s", evaluated_at=evaluated, result_available_at=None)) is False


@pytest.mark.parametrize("value", [None, "", "   ", "not-a-timestamp", "2026-13-45"])
def test_04_an_unusable_timestamp_fails_closed(value) -> None:
    assert candidate.utc(value) is None
    assert candidate.is_training_evidence(
        _row("o", evaluated_at="2026-08-01T00:00:00Z", result_available_at=value),
        _row("s", evaluated_at="2026-08-20T00:00:00Z", result_available_at=None)) is False
    assert candidate.is_training_evidence(
        _row("o", evaluated_at="2026-08-01T00:00:00Z",
             result_available_at="2026-08-02T00:00:00Z"),
        _row("s", evaluated_at=value, result_available_at=None)) is False


# --- 5: below the training floor the temperature is neutral ----------------
@pytest.mark.parametrize("count", [0, 1, 19])
def test_05_below_the_training_floor_the_temperature_is_one(count) -> None:
    training = [{"dist": FLAT, "settlement": "LOSS"} for _ in range(count)]

    assert candidate.fit_global_temperature(training) == 1.00


OVERCONFIDENT = {"WIN": 0.90, "HALF_WIN": 0.0, "PUSH": 0.02,
                 "HALF_LOSS": 0.0, "LOSS": 0.08}


def test_05_at_the_floor_the_search_actually_runs() -> None:
    """Nineteen rows is neutral by rule; the twentieth lets the fit move.

    The training set has to be one shrinking actually helps -- confident on WIN
    and wrong -- otherwise 1.00 is simply the right answer and the test would
    pass without the search ever mattering.
    """
    training = [{"dist": OVERCONFIDENT, "settlement": "LOSS"} for _ in range(20)]

    assert candidate.fit_global_temperature(training[:19]) == 1.00
    assert len(training) == candidate.MIN_TRAINING_ROWS
    assert candidate.fit_global_temperature(training) > 1.00


def test_05_a_well_calibrated_training_set_stays_at_neutral() -> None:
    """The search is not biased upward: it only shrinks when shrinking pays."""
    training = [{"dist": FLAT, "settlement": "LOSS"} for _ in range(40)]

    assert candidate.fit_global_temperature(training) == 1.00


def test_05_the_first_records_of_the_corpus_sit_at_neutral(applied) -> None:
    ordered = sorted(applied, key=candidate.temporal_key)
    for row in ordered:
        if row["training_rows"] < candidate.MIN_TRAINING_ROWS:
            assert row["temperature"] == 1.00


# --- 6: the grid is frozen at 1.00 to 2.00 ---------------------------------
def test_06_the_grid_is_exactly_one_to_two_step_one_hundredth() -> None:
    assert candidate.T_GRID[0] == 1.00
    assert candidate.T_GRID[-1] == 2.00
    assert len(candidate.T_GRID) == 101
    assert candidate.T_GRID == tuple(sorted(candidate.T_GRID))
    steps = {
        round(b - a, 10)
        for a, b in zip(candidate.T_GRID, candidate.T_GRID[1:], strict=False)
    }
    assert steps == {0.01}


def test_06_no_fitted_temperature_escapes_the_grid(applied) -> None:
    grid = set(candidate.T_GRID)

    for row in applied:
        assert row["temperature"] in grid
        assert 1.00 <= row["temperature"] <= 2.00


def test_06_the_grid_ceiling_is_not_binding(applied) -> None:
    """A run pinned at 2.00 would mean the frozen grid chose the answer."""
    assert not [row for row in applied if row["temperature"] == 2.00]


# --- 7: the tie-break is a function of the training set, not of walk order --
def test_07_ties_resolve_to_the_temperature_nearest_one() -> None:
    uniform = {state: 0.2 for state in candidate.STATES}
    training = [{"dist": uniform, "settlement": "WIN"} for _ in range(40)]

    # a uniform distribution is unchanged by temperature, so every T ties on the
    # log-loss term and only the penalty separates them
    assert candidate.fit_global_temperature(training) == 1.00


def test_07_the_fit_does_not_depend_on_training_order() -> None:
    training = [
        {"dist": {"WIN": 0.7, "HALF_WIN": 0.0, "PUSH": 0.05,
                  "HALF_LOSS": 0.0, "LOSS": 0.25},
         "settlement": "LOSS" if index % 3 else "WIN"}
        for index in range(60)
    ]

    forward = candidate.fit_global_temperature(training)
    backward = candidate.fit_global_temperature(list(reversed(training)))

    assert forward == backward


# --- 8: the tempered distribution keeps the 1e-9 contract ------------------
@pytest.mark.parametrize("dist", [
    FLAT,
    {"WIN": 0.9, "HALF_WIN": 0.02, "PUSH": 0.03, "HALF_LOSS": 0.02, "LOSS": 0.03},
    {"WIN": 0.001, "HALF_WIN": 0.0, "PUSH": 0.0, "HALF_LOSS": 0.0, "LOSS": 0.999},
])
def test_08_every_temperature_keeps_the_1e9_probability_contract(dist) -> None:
    assert PROBABILITY_TOLERANCE == Decimal("1e-9")
    for temperature in candidate.T_GRID:
        tempered = candidate.temper(dist, temperature)
        assert abs(sum(tempered.values()) - 1.0) < 1e-9
        frozen = candidate.frozen_distribution(tempered)
        total = sum(
            (getattr(frozen, name) for name in frozen.__dataclass_fields__), Decimal(0))
        assert abs(total - 1) <= PROBABILITY_TOLERANCE


def test_08_a_distribution_that_misses_the_contract_is_refused(applied) -> None:
    with pytest.raises(ValueError, match="CALIBRATED_DISTRIBUTION_FAILED_1E9_CONTRACT"):
        candidate.frozen_distribution(
            {"WIN": 0.5, "HALF_WIN": 0.0, "PUSH": 0.0, "HALF_LOSS": 0.0, "LOSS": 0.0})
    for row in applied:
        assert abs(sum(row["candidate_dist"].values()) - 1.0) < 1e-9


def test_08_the_transform_is_the_specified_one() -> None:
    dist = {"WIN": 0.6, "HALF_WIN": 0.1, "PUSH": 0.05, "HALF_LOSS": 0.05, "LOSS": 0.2}
    temperature = 1.37

    got = candidate.temper(dist, temperature)

    raw = {
        state: math.exp(math.log(max(dist[state], 1e-12)) / temperature)
        for state in candidate.STATES
    }
    total = sum(raw.values())
    for state in candidate.STATES:
        assert got[state] == pytest.approx(raw[state] / total, abs=1e-12)


# --- 9: EV comes from the canonical Decimal authority ----------------------
def test_09_expected_value_matches_the_canonical_authority(applied) -> None:
    for row in applied[:20]:
        tempered = row["candidate_dist"]
        expected = float(expected_value(
            Decimal(str(row["decimal_odds"])),
            SettlementDistribution(
                full_win_probability=Decimal(str(tempered["WIN"])),
                half_win_probability=Decimal(str(tempered["HALF_WIN"])),
                push_probability=Decimal(str(tempered["PUSH"])),
                half_loss_probability=Decimal(str(tempered["HALF_LOSS"])),
                full_loss_probability=Decimal(str(tempered["LOSS"])),
            ).normalized()))
        assert candidate.canonical_expected_value(row["decimal_odds"], tempered) == expected


def test_09_no_second_ev_or_settlement_formula_is_defined() -> None:
    for path in _task_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        defined = {
            node.name for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        }
        assert not {name for name in defined if name in {"expected_value", "settle",
                                                         "settlement", "grade_bet"}}
    tree = ast.parse(CANDIDATE_PATH.read_text(encoding="utf-8"))
    sources = {
        node.module for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and any(alias.name == "expected_value" for alias in node.names)
    }
    assert sources == {"w2.domain.five_state_pricing"}


# --- 10: everything except confidence comes out unchanged -----------------
def test_10_direction_line_odds_factor_and_result_are_untouched(rows, applied) -> None:
    before = {row["evaluation_id"]: row for row in rows}

    assert len(applied) == len(rows)
    for row in applied:
        original = before[row["evaluation_id"]]
        for field in ("market", "selection", "exact_line", "decimal_odds",
                      "settlement", "profit_units", "factor_disposition",
                      "lineup_status", "cashflow_price_edge", "ev_minus_se",
                      "result_available_at", "evaluated_at"):
            assert row[field] == original[field], field
        assert row["incumbent_dist"] == original["dist"]


def test_10_the_candidate_only_softens_never_sharpens(applied) -> None:
    """T >= 1 by construction, so no calibrated peak may exceed the original."""
    for row in applied:
        if row["temperature"] == 1.00:
            assert row["candidate_dist"] == pytest.approx(row["incumbent_dist"])
            continue
        assert max(row["candidate_dist"].values()) < max(row["incumbent_dist"].values())


# --- 11: a missing cashflow edge is absent evidence, never a decision -----
def test_11_a_missing_cashflow_edge_is_not_estimable(rows) -> None:
    missing = [row for row in rows if row["cashflow_price_edge"] is None]

    assert len(missing) == 133
    for row in missing:
        assert runner.not_estimable_reason(row) == (
            candidate.NOT_ESTIMABLE_MISSING_CASHFLOW_EDGE)


def test_11_the_recommendation_layer_counts_them_out_not_in(applied) -> None:
    summary = runner.recommendation_layer(applied, "candidate_dist", len(applied))

    assert summary["not_estimable_reason_counts"] == {
        candidate.NOT_ESTIMABLE_MISSING_CASHFLOW_EDGE: 133}
    assert summary["estimable_rows"] == 15
    assert summary["candidate_emitted"] + summary["candidate_blocked"] == 15
    assert summary["coverage_of_estimable"] is not None


def test_11_no_cashflow_edge_is_ever_inferred_from_the_price(rows) -> None:
    source = (RUNNER_PATH).read_text(encoding="utf-8")

    assert "cashflow_price_edge" in source
    for guess in ("1 / ", "1.0 / ", "implied_", "from_odds", "or 0.05", "or 0.0"):
        assert f"cashflow_price_edge{guess}" not in source
    for row in rows:
        if row["cashflow_price_edge"] is None:
            assert row["cashflow_edge_provenance"] == (
                candidate.NOT_ESTIMABLE_MISSING_CASHFLOW_EDGE)


# --- 12: the last ten never choose a parameter ---------------------------
def test_12_the_last_ten_results_cannot_change_any_earlier_temperature(rows) -> None:
    baseline = {
        row["evaluation_id"]: row["temperature"]
        for row in candidate.apply_candidate(rows)
    }
    ordered = sorted(rows, key=candidate.temporal_key)
    tail = {row["evaluation_id"] for row in ordered[-10:]}
    # flip every outcome in the incident-replay window; nothing earlier may move
    mutated = [
        {**row, "settlement": ("LOSS" if row["settlement"] != "LOSS" else "WIN")}
        if row["evaluation_id"] in tail else row
        for row in rows
    ]

    after = {
        row["evaluation_id"]: row["temperature"]
        for row in candidate.apply_candidate(mutated)
    }

    head = [row["evaluation_id"] for row in ordered[:-10]]
    assert [baseline[key] for key in head] == [after[key] for key in head]


def test_12_no_record_is_trained_on_its_own_result(applied) -> None:
    for row in applied:
        assert candidate.is_training_evidence(row, row) is False


# --- 13: the whole run is deterministic ---------------------------------
def test_13_two_runs_of_the_pipeline_agree_in_process(rows) -> None:
    first = candidate.apply_candidate(rows)
    second = candidate.apply_candidate(list(reversed(rows)))

    assert [row["evaluation_id"] for row in first] == [
        row["evaluation_id"] for row in second]
    assert [row["temperature"] for row in first] == [
        row["temperature"] for row in second]


def test_13_the_bootstrap_is_seeded_and_repeatable(applied) -> None:
    first = runner.calibration_bootstrap(applied, "candidate_dist", 12345)
    second = runner.calibration_bootstrap(applied, "candidate_dist", 12345)

    assert first == second


# --- 14: the frozen input is exactly the accepted one -------------------
def test_14_the_source_bundle_is_the_accepted_one() -> None:
    digest = runner.sha256_file(PACKAGE / "OFFICIAL_148_SOURCE_BUNDLE.jsonl")

    assert digest == (
        "da9edb11be8144991addeb1c6e83724d3cca083ca46b0bd8de2eaa6d45f6e7e4")


def test_14_the_input_package_still_verifies_against_its_own_hashes() -> None:
    result = subprocess.run(  # noqa: S603
        ["/usr/bin/shasum", "-a", "256", "-c", "HASHES.sha256"],
        cwd=PACKAGE, capture_output=True, text=True, check=False)

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count(": OK") == 13


# --- 15-18: the boundaries this task must not cross --------------------
def _task_sources() -> list[Path]:
    return [CANDIDATE_PATH, RUNNER_PATH]


def test_15_nothing_in_this_task_can_reach_a_provider_or_the_network() -> None:
    banned = {"requests", "httpx", "urllib", "urllib3", "http", "socket", "aiohttp",
              "w2.providers", "w2.ingestion"}
    for path in _task_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in banned, (path, alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".")[0]
                assert root not in banned, (path, node.module)
                assert not node.module.startswith("w2.providers"), path
                assert not node.module.startswith("w2.ingestion"), path


def test_16_nothing_in_this_task_can_reach_a_database() -> None:
    banned = {"sqlalchemy", "psycopg", "psycopg2", "alembic"}
    for path in _task_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = (
                [alias.name for alias in node.names] if isinstance(node, ast.Import)
                else [node.module or ""] if isinstance(node, ast.ImportFrom)
                else []
            )
            for name in names:
                assert name.split(".")[0] not in banned, (path, name)
        source = path.read_text(encoding="utf-8")
        for statement in ("insert into", "update ", "delete from", "session.add"):
            assert statement not in source.lower(), (path, statement)


def test_17_this_task_does_not_import_or_touch_the_production_chain() -> None:
    forbidden_prefixes = ("w2.prematch", "w2.strategy", "w2.api", "w2.dashboard",
                          "w2.scheduler", "w2.operations")
    for path in _task_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith(forbidden_prefixes), (
                    path, node.module)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith(forbidden_prefixes), (
                        path, alias.name)


def test_17_the_production_chain_never_imports_this_candidate() -> None:
    """One direction is not enough: production must not reach in either.

    The candidate lives outside src/w2 entirely, so there is no module path
    production could import even if someone tried.
    """
    hits = subprocess.run(  # noqa: S603
        ["/usr/bin/grep", "-rl", "confidence_shrinkage", str(REPO / "src/w2")],
        capture_output=True, text=True, check=False)

    assert not hits.stdout.strip(), hits.stdout
    assert not (REPO / "src/w2/quant_research").exists()


def test_18_no_obsidian_or_desktop_path_is_referenced() -> None:
    for path in _task_sources():
        source = path.read_text(encoding="utf-8")
        for marker in ("Obsidian", "/Users/", "W2文档", "Desktop"):
            assert marker not in source, (path, marker)
