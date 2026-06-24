from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/run_w2_gate3_baselight_odds_window_v3_resume.py"


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("gate3_baselight_v3_resume", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_resume_retries_newest_failed_window_before_advancing() -> None:
    module = load_script()
    state = {
        "date_windows": [
            {
                "window_start_utc": "2026-06-17T00:00:00Z",
                "window_end_utc": "2026-06-24T00:00:00Z",
                "status": "APPENDED",
            },
            {
                "window_start_utc": "2026-06-10T00:00:00Z",
                "window_end_utc": "2026-06-17T00:00:00Z",
                "status": "PENDING_OR_FAILED",
            },
        ]
    }

    assert module.derive_resume_start_date(state, None) == "2026-06-17"


def test_resume_advances_from_oldest_completed_window() -> None:
    module = load_script()
    state = {
        "date_windows": [
            {
                "window_start_utc": "2026-06-17T00:00:00Z",
                "window_end_utc": "2026-06-24T00:00:00Z",
                "status": "APPENDED",
            },
            {
                "window_start_utc": "2026-06-10T00:00:00Z",
                "window_end_utc": "2026-06-17T00:00:00Z",
                "status": "APPENDED",
            },
        ]
    }

    assert module.derive_resume_start_date(state, None) == "2026-06-10"
    assert module.derive_resume_start_date(state, "2025-01-01") == "2025-01-01"


def test_ranked_window_sql_is_bounded_and_deterministic() -> None:
    module = load_script()
    sql = module.build_ranked_odds_window_sql(
        datetime(2026, 6, 1, tzinfo=UTC),
        datetime(2026, 6, 8, tzinfo=UTC),
        9000,
        99,
    )

    assert "PARTITION BY match_id, bookmaker" in sql
    assert "bookmaker_row_rank <= 10" in sql
    assert "ORDER BY match_id, bookmaker, outcome, collected_at, odds" in sql
    assert "LIMIT 5000" in sql
