from __future__ import annotations

import subprocess
from copy import deepcopy
from pathlib import Path

from scripts.check_w2_acceptance import run_acceptance

FIXTURE = Path("tests/fixtures/w2_acceptance/acceptance_day_view.json")


def test_acceptance_checker_returns_pass_on_fixture() -> None:
    result = run_acceptance(fixture_path=FIXTURE)

    assert result["status"] == "PASS"
    assert result["provider_calls"] == 0
    assert result["db_reads"] == 0
    assert result["db_writes"] == 0


def test_boss_5s_test_passes() -> None:
    result = run_acceptance(fixture_path=FIXTURE)

    assert result["boss_5s_test"]["status"] == "PASS"
    assert result["boss_5s_test"]["lock_eligible"] == 0
    assert result["boss_5s_test"]["analysis_pick"] == 1
    assert result["boss_5s_test"]["not_ready"] == 1


def test_latest_acceptance_fixture_does_not_use_lineups_as_watch_blocker() -> None:
    payload = _fixture_payload()
    watch = next(card for card in payload["cards"] if card["decision_tier"] == "WATCH")

    assert watch["reason_code"] == "MODEL_FAIR_LINE_UNAVAILABLE"
    assert watch["non_pick"]["reason_code"] == "MODEL_FAIR_LINE_UNAVAILABLE"
    assert "首发为可选增强" in watch["one_liner"]


def test_lifecycle_status_open_fails_contract(tmp_path: Path) -> None:
    payload = _fixture_payload()
    payload["cards"][0]["lifecycle_status"] = "OPEN"
    path = _write_fixture(tmp_path, payload)

    result = run_acceptance(fixture_path=path)

    assert result["status"] == "FAIL"
    assert any("INVALID_LIFECYCLE_STATUS:OPEN" in item for item in result["blockers"])


def test_invalid_decision_tier_fails_contract(tmp_path: Path) -> None:
    payload = _fixture_payload()
    payload["cards"][0]["decision_tier"] = "BAD_TIER"
    path = _write_fixture(tmp_path, payload)

    result = run_acceptance(fixture_path=path)

    assert result["status"] == "FAIL"
    assert any("INVALID_DECISION_TIER:BAD_TIER" in item for item in result["blockers"])


def test_invalid_data_status_fails_contract(tmp_path: Path) -> None:
    payload = _fixture_payload()
    payload["cards"][0]["data_status"] = "BAD_STATUS"
    path = _write_fixture(tmp_path, payload)

    result = run_acceptance(fixture_path=path)

    assert result["status"] == "FAIL"
    assert any("INVALID_DATA_STATUS:BAD_STATUS" in item for item in result["blockers"])


def test_missing_lifecycle_status_fails_contract(tmp_path: Path) -> None:
    payload = _fixture_payload()
    payload["cards"][0].pop("lifecycle_status")
    path = _write_fixture(tmp_path, payload)

    result = run_acceptance(fixture_path=path)

    assert result["status"] == "FAIL"
    assert any("MISSING_LIFECYCLE_STATUS" in item for item in result["blockers"])


def test_boss_5s_required_text_only_in_details_fails(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import scripts.check_w2_acceptance as acceptance

    monkeypatch.setattr(
        acceptance,
        "render_boss_dashboard_l1_html",
        lambda _day_view: (
            "<main><header>正式可锁 分析推荐 未就绪 下一次刷新 "
            "2026-07-05T01:30:00Z RECOMMEND-only</header>"
            "<details>MODEL_FAIR_LINE_UNAVAILABLE MARKET_UNAVAILABLE 主要未出原因</details></main>"
        ),
    )
    monkeypatch.setattr(
        acceptance,
        "build_boss_dashboard_l1",
        lambda _day_view: {
            "environment": "staging",
            "counts": {"lock_eligible": 0, "analysis_pick": 1, "not_ready": 1},
            "freshness": {"next_refresh_tick": "2026-07-05T01:30:00Z"},
        },
    )

    result = acceptance._boss_5s_test({})

    assert result["status"] == "FAIL"
    assert "MISSING_TEXT:MODEL_FAIR_LINE_UNAVAILABLE" in result["blockers"]
    assert "MISSING_REASON_SUMMARY" in result["blockers"]


def test_forbidden_raw_debug_fails(tmp_path: Path) -> None:
    payload = _fixture_payload()
    payload["cards"][0]["one_liner"] = "raw_payload should stay out of boss first screen"
    path = _write_fixture(tmp_path, payload)

    result = run_acceptance(fixture_path=path)

    assert result["status"] == "FAIL"
    assert any("RAW_DEBUG_LEAK:raw_payload" in item for item in result["blockers"])


def test_missing_environment_policy_fails(tmp_path: Path) -> None:
    payload = _fixture_payload()
    payload.pop("environment_policy")
    path = _write_fixture(tmp_path, payload)

    result = run_acceptance(fixture_path=path)

    assert result["status"] == "FAIL"
    assert any("MISSING_ENVIRONMENT_POLICY" in item for item in result["blockers"])


def test_analysis_pick_without_non_certain_copy_fails(tmp_path: Path) -> None:
    payload = _fixture_payload()
    payload["cards"][0]["pick"]["disclaimer"] = "分析参考；production 动作需 RECOMMEND"
    path = _write_fixture(tmp_path, payload)

    result = run_acceptance(fixture_path=path)

    assert result["status"] == "FAIL"
    assert any(
        "ANALYSIS_PICK_MISSING_NON_CERTAIN_DISCLAIMER" in item
        for item in result["blockers"]
    )


def test_refresh_safety_rejects_forbidden_endpoint(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import scripts.check_w2_acceptance as acceptance

    original = acceptance._matchday_payload

    def poisoned_payload() -> dict[str, object]:
        payload = original()
        refresh = payload["refresh_plan_summary"]  # type: ignore[index]
        refresh["endpoint_allowlist"] = [  # type: ignore[index]
            "status",
            "fixtures",
            "odds",
            "lineups",
            "statistics",
        ]
        return payload

    monkeypatch.setattr(acceptance, "_matchday_payload", poisoned_payload)

    result = acceptance.run_acceptance(fixture_path=FIXTURE)

    assert result["status"] == "FAIL"
    assert any("FORBIDDEN_ENDPOINT_IN_ALLOWLIST" in item for item in result["blockers"])


def test_matchday_and_replay_smoke_remain_side_effect_free() -> None:
    result = run_acceptance(fixture_path=FIXTURE)

    matchday = result["matchday_dry_run_acceptance"]
    replay = result["replay_acceptance"]
    assert matchday["provider_calls"] == 0
    assert matchday["db_writes"] == 0
    assert matchday["would_enqueue"] is False
    assert replay["provider_calls"] == 0
    assert replay["db_reads"] == 0
    assert replay["db_writes"] == 0


def test_no_stage16_files_exist() -> None:
    result = run_acceptance(fixture_path=FIXTURE)

    assert result["stage16_guard"]["status"] == "PASS"
    assert result["stage16_guard"]["tracked_stage16_files"] == []


def test_tracked_stage16_files_fail(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import scripts.check_w2_acceptance as acceptance

    def fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=["git", "ls-files"],
            returncode=0,
            stdout="scripts/check_w2_stage16.py\n",
            stderr="",
        )

    monkeypatch.setattr(acceptance.subprocess, "run", fake_run)

    result = acceptance._stage16_guard()

    assert result["status"] == "FAIL"
    assert result["tracked_stage16_files"] == ["scripts/check_w2_stage16.py"]
    assert "STAGE16_FILE:scripts/check_w2_stage16.py" in result["blockers"]


def test_no_tracked_stage16_files_pass(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import scripts.check_w2_acceptance as acceptance

    def fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=["git", "ls-files"],
            returncode=0,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr(acceptance.subprocess, "run", fake_run)

    result = acceptance._stage16_guard()

    assert result["status"] == "PASS"
    assert result["tracked_stage16_files"] == []


def test_untracked_tmp_stage16_file_does_not_fail(tmp_path: Path) -> None:
    (tmp_path / "scratch_stage16_note.txt").write_text("not tracked", encoding="utf-8")

    result = run_acceptance(fixture_path=FIXTURE)

    assert result["stage16_guard"]["status"] == "PASS"


def _fixture_payload() -> dict[str, object]:
    import json

    with FIXTURE.open(encoding="utf-8") as handle:
        return deepcopy(json.load(handle))


def _write_fixture(tmp_path: Path, payload: dict[str, object]) -> Path:
    import json

    path = tmp_path / "acceptance_day_view.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path
