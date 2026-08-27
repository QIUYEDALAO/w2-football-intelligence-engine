from __future__ import annotations

from scripts.check_factor_v2_forward_prereg_amendment import check, self_test


def test_successor_preregistration_is_frozen_before_first_row() -> None:
    assert check()["status"] == "PASS"


def test_successor_preregistration_mutants_fail_closed() -> None:
    assert self_test() == {"status": "PASS", "mutants_caught": 5}
