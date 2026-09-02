import json

import pytest
from scripts.run_factor_incremental_info_measure import (
    load_measurement_records,
    schema_and_counts,
)


def test_loader_filters_before_exposing_records_and_reports_assertions(tmp_path):
    path = tmp_path / "mixed.json"
    path.write_text(
        json.dumps(
            {
                "rows": [
                    {"fixture_id": "train", "kickoff": "2024-05-01T00:00:00Z", "goals": 1},
                    {"fixture_id": "validation", "kickoff": "2025-05-01T00:00:00Z", "goals": 2},
                    {"fixture_id": "holdout", "kickoff": "2026-05-01T00:00:00Z", "goals": 3},
                    {"fixture_id": "future", "kickoff": "2027-05-01T00:00:00Z", "goals": None},
                ]
            }
        ),
        encoding="utf-8",
    )

    loaded = load_measurement_records(path, records_key="rows")

    assert [row["fixture_id"] for row in loaded.records] == ["train", "validation"]
    assert schema_and_counts(loaded) == {
        "field_names": ["fixture_id", "goals", "kickoff"],
        "source_year_counts": {2024: 1, 2025: 1, 2026: 1, 2027: 1},
        "loaded_year_counts": {2024: 1, 2025: 1},
        "assertions": {"year_2026": 0, "year_2027": 0, "burned_penaltyblog": 0, "trigger_count": 0},
    }


def test_loader_rejects_burned_penaltyblog_season_even_with_allowed_date(tmp_path):
    path = tmp_path / "burned.json"
    path.write_text(
        json.dumps({"rows": [{"kickoff": "2024-05-01T00:00:00Z", "season": "2016/17"}]}),
        encoding="utf-8",
    )

    with pytest.raises(AssertionError, match="BURNED_PENALTYBLOG_SEASON_PRESENT_AFTER_LOAD"):
        load_measurement_records(path, records_key="rows")
