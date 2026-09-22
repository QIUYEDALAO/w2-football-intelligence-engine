from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[2] / "scripts" / "quant" / "fit_track_b_output_calibration.py"
SPEC = importlib.util.spec_from_file_location("fit_track_b_output_calibration", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _row(*, competition: str, market: str, selection: str, probability: float, y: float, stamp: str) -> dict:
    return {
        "fixture_id": f"{competition}-{stamp}",
        "competition_id": competition,
        "market": market,
        "selection": selection,
        "model_probability": probability,
        "y": y,
        "evaluated_at": stamp,
    }


def test_pava_serializes_merged_block_max_x_as_right_edge() -> None:
    curve = MODULE.pava([0.10, 0.20, 0.30], [0.0, 1.0, 0.0])

    assert curve == [(0.10, 0.0), (0.30, 0.5)]
    # The merged block's max x is .30; a mean(x) knot at .25 would switch too early.
    assert MODULE.predict(curve, 0.20) == 0.5
    assert MODULE.predict(curve, 0.26) == 0.5
    assert MODULE.predict(curve, 0.30) == 0.5


def test_global_prior_is_partitioned_by_market_and_selection() -> None:
    rows = [
        _row(competition="a", market="TOTALS", selection="OVER", probability=0.4, y=1.0, stamp="01"),
        _row(competition="a", market="TOTALS", selection="UNDER", probability=0.4, y=0.0, stamp="02"),
        _row(competition="a", market="ASIAN_HANDICAP", selection="HOME", probability=0.4, y=1.0, stamp="03"),
        _row(competition="a", market="ASIAN_HANDICAP", selection="AWAY", probability=0.4, y=0.0, stamp="04"),
    ]

    global_curves, _ = MODULE._fit_hierarchical_maps(rows, 20.0)

    assert set(global_curves) == {
        ("TOTALS", "OVER"),
        ("TOTALS", "UNDER"),
        ("ASIAN_HANDICAP", "HOME"),
        ("ASIAN_HANDICAP", "AWAY"),
    }
    assert MODULE.predict(global_curves[("TOTALS", "OVER")], 0.4) == 1.0
    assert MODULE.predict(global_curves[("TOTALS", "UNDER")], 0.4) == 0.0


def test_cell_shrinkage_is_continuous_across_old_n20_boundary() -> None:
    row = _row(competition="a", market="TOTALS", selection="OVER", probability=0.5, y=1.0, stamp="01")
    global_curves = {("TOTALS", "OVER"): [(1.0, 0.25)]}
    cell_curves = {("TOTALS", "OVER", "a"): [(1.0, 0.75)]}

    p19 = MODULE._predict_hierarchical(row, global_curves, cell_curves, 20.0, 19)
    p20 = MODULE._predict_hierarchical(row, global_curves, cell_curves, 20.0, 20)

    assert p19 == 19 / 39 * 0.75 + 20 / 39 * 0.25
    assert p20 == 0.5
    assert abs(p20 - p19) < 0.01


def test_temporal_oof_candidate_pool_includes_raw_platt_and_isotonic() -> None:
    rows = []
    for i in range(25):
        rows.append(
            _row(
                competition="a" if i % 2 else "b",
                market="TOTALS",
                selection="OVER",
                probability=0.2 + i * 0.02,
                y=float(i % 3 != 0),
                stamp=f"{i:02d}",
            )
        )

    selected, diagnostics = MODULE._temporal_oof(rows, 20.0)

    assert selected[("TOTALS", "OVER")] in {"hierarchical_isotonic", "platt"}
    assert diagnostics[("TOTALS", "OVER")]["oof_rows"] == 20
    assert set(diagnostics[("TOTALS", "OVER")]["candidates"]) == {
        "raw",
        "hierarchical_isotonic",
        "platt",
    }
