from __future__ import annotations

from scripts.check_staging_disk_capacity import capacity_status


def test_staging_disk_capacity_thresholds() -> None:
    assert capacity_status(79) == ("PASS", 0)
    assert capacity_status(80) == ("WARN", 0)
    assert capacity_status(89) == ("WARN", 0)
    assert capacity_status(90) == ("BLOCKED", 2)
