from __future__ import annotations

from scripts.run_factor_v2_gate1_ablation import _depth_strata, _gate_checks


def _tracks(*, b2_log_loss: float, b2_rps: float, b2_ece: float) -> dict[str, object]:
    return {
        "B0_SAME_ENGINE_XG": {"log_loss": 1.0, "rps": 0.2, "ece": 0.02},
        "B2_FACTOR_V2": {
            "log_loss": b2_log_loss,
            "rps": b2_rps,
            "ece": b2_ece,
        },
    }


def test_depth_strata_use_input_depth_only_and_cover_every_fixture() -> None:
    rows = [
        {"fixture_id": str(index), "visible_history_rows": index}
        for index in range(1, 10)
    ]

    strata = _depth_strata(rows)

    assert set(strata) == {"LOW", "MIDDLE", "HIGH"}
    assert sum(len(row["fixture_ids"]) for row in strata.values()) == len(rows)
    assert strata["LOW"]["fixture_ids"] == ["1", "2", "3"]


def test_gate_fails_when_ece_worsens_even_if_discrimination_improves() -> None:
    coverage = {
        split: {"b0_scorable_rate": 0.97} for split in ("VALIDATION", "HOLDOUT")
    }
    global_metrics = {
        split: _tracks(b2_log_loss=0.98, b2_rps=0.19, b2_ece=0.03)
        for split in ("VALIDATION", "HOLDOUT")
    }
    strata = {
        split: {
            name: {
                "fixture_count": 10,
                "metrics": _tracks(b2_log_loss=0.98, b2_rps=0.19, b2_ece=0.03),
            }
            for name in ("LOW", "MIDDLE", "HIGH")
        }
        for split in ("VALIDATION", "HOLDOUT")
    }

    checks = _gate_checks(
        coverage_by_split=coverage,
        metrics_by_split=global_metrics,
        strata_by_split=strata,
        leakage_violation_count=0,
        deterministic=True,
    )

    ece_checks = [row for row in checks if "ECE_NOT_WORSE" in row["check"]]
    assert len(ece_checks) == 2
    assert all(row["pass"] is False for row in ece_checks)
