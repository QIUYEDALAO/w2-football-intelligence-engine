from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_recovery_entry_is_fail_closed_and_audited() -> None:
    source = (ROOT / "scripts/reenable_competition_after_xg_recovery.py").read_text()

    assert "MIN_COVERAGE_PERCENT = 70.0" in source
    assert "MAX_NEWEST_XG_AGE = timedelta(days=7)" in source
    assert 'MatchdayCheckpointPlanModel.status == "SKIPPED_POLICY"' in source
    assert "MatchdayCheckpointPlanModel.window_end > current" in source
    assert "COMPETITION_DISABLED_NO_XG_COVERAGE" in source
    assert '"action": "REENABLE_AFTER_XG_RECOVERY"' in source


def test_xg_refresh_reads_dynamic_enabled_scope() -> None:
    source = (ROOT / "ops/host/w2-xg-refresh").read_text()

    assert "SELECT competition_id FROM league_season" in source
    assert "(payload->>'enabled')::boolean IS TRUE" in source
    assert "chinese_super_league allsvenskan" not in source
