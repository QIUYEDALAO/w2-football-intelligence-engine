import json

from scripts.run_f3_rest_level_screening import (
    MeasurementRow,
    _fold,
    _oof_probabilities,
    load_train_2024_records,
    rest_input_schema,
)


def test_loader_exposes_only_train_2024_and_no_rows(tmp_path):
    path = tmp_path / "mixed.json"
    path.write_text(
        json.dumps(
            [
                {"fixture_id": "train", "kickoff": "2024-05-01T00:00:00Z"},
                {"fixture_id": "validation", "kickoff": "2025-05-01T00:00:00Z"},
                {"fixture_id": "holdout", "kickoff": "2026-05-01T00:00:00Z"},
            ]
        ),
        encoding="utf-8",
    )

    loaded = load_train_2024_records(path)

    assert [row["fixture_id"] for row in loaded.records] == ["train"]
    assert loaded.audit["loaded_year_counts"] == {2024: 1}
    assert loaded.audit["exclusions"] == {"YEAR_NOT_2024_FORBIDDEN": 2}
    assert loaded.audit["assertions"]["trigger_count"] == 0


def test_rest_input_schema_returns_names_and_counts_only(tmp_path):
    path = tmp_path / "snapshot.json"
    path.write_text(
        json.dumps(
            [
                {
                    "target_fixture_id": "train",
                    "target_kickoff": "2024-05-01T00:00:00Z",
                    "factors": {
                        "F3_REST_FITNESS": {
                            "raw_value": 2,
                            "inputs": {"home_rest_days": 3, "away_rest_days": 5},
                        }
                    },
                }
            ]
        ),
        encoding="utf-8",
    )

    schema = rest_input_schema(load_train_2024_records(path))

    assert schema == {
        "factor_id": "F3_REST_FITNESS",
        "factor_count": 1,
        "factor_field_names": ["inputs", "raw_value"],
        "inputs_count": 1,
        "input_field_names": ["away_rest_days", "home_rest_days"],
    }


def test_oof_scoring_fits_each_fixture_outside_its_fold():
    fixture_ids: list[str] = []
    for fold in range(5):
        fixture_ids.extend(
            [
                f"fixture-{candidate}"
                for candidate in range(10_000)
                if _fold(f"fixture-{candidate}") == fold
            ][:4]
        )
    rows = [
        MeasurementRow(
            fixture_id=fixture_id,
            actual=("HOME", "DRAW", "AWAY")[index % 3],
            baseline_home=1.3,
            baseline_away=1.0,
            value=float(index % 7),
        )
        for index, fixture_id in enumerate(fixture_ids)
    ]

    baseline, candidate, fits = _oof_probabilities(rows)

    assert len(baseline) == len(candidate) == len(rows)
    assert {fit["fold"] for fit in fits} == set(range(5))
    assert sum(int(fit["held_out_count"]) for fit in fits) == len(rows)
