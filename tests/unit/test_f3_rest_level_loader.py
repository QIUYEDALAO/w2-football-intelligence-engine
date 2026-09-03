import json

from scripts.run_f3_rest_level_screening import load_train_2024_records


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
