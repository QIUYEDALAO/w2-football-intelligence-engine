import json

from scripts.run_f5_f1_f2_screening import load_screening_records


def test_loader_exposes_only_finished_burned_window_and_no_rows(tmp_path):
    path = tmp_path / "mixed.json"
    path.write_text(
        json.dumps(
            [
                {"fixture_id": "old", "kickoff": "2025-12-31T23:00:00Z", "status": "FT"},
                {"fixture_id": "kept", "kickoff": "2026-08-22T23:59:59Z", "status": "FT"},
                {"fixture_id": "open", "kickoff": "2026-08-22T10:00:00Z", "status": "NS"},
                {"fixture_id": "clean", "kickoff": "2026-08-23T00:00:00Z", "status": "FT"},
            ]
        ),
        encoding="utf-8",
    )

    loaded = load_screening_records(path, require_finished=True)

    assert [row["fixture_id"] for row in loaded.records] == ["kept"]
    assert loaded.audit["loaded_month_counts"] == {"2026-08": 1}
    assert loaded.audit["exclusions"] == {
        "AFTER_2026_08_22_FORBIDDEN": 1,
        "BEFORE_SCREENING_WINDOW": 1,
        "NOT_FINISHED": 1,
    }
    assert loaded.audit["assertions"]["trigger_count"] == 0
