from __future__ import annotations

import fcntl
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = sys.executable
EXPECTED_HEAD = "0017_create_stage9a_shadow_strategy"
FUTURE_KICKOFF_UTC = "2099-06-24T12:00:00Z"

OBSERVER_SPEC = importlib.util.spec_from_file_location(
    "run_stage7i_observer",
    ROOT / "scripts/run_stage7i_observer.py",
)
assert OBSERVER_SPEC is not None and OBSERVER_SPEC.loader is not None
OBSERVER = importlib.util.module_from_spec(OBSERVER_SPEC)
OBSERVER_SPEC.loader.exec_module(OBSERVER)


def run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=ROOT, text=True, capture_output=True, check=False)


def write_json(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_observer_migration_head_parser_accepts_typed_alembic_fields(tmp_path: Path) -> None:
    versions = tmp_path / "migrations" / "versions"
    versions.mkdir(parents=True)
    (versions / "0001_base.py").write_text(
        'revision: str = "0001_base"\n'
        "down_revision: str | None = None\n",
        encoding="utf-8",
    )
    (versions / "0002_head.py").write_text(
        'revision: str = "0017_create_stage9a_shadow_strategy"\n'
        'down_revision: str | None = "0001_base"\n',
        encoding="utf-8",
    )

    assert OBSERVER.migration_heads(tmp_path) == [EXPECTED_HEAD]


def candidate(
    fixture_id: str,
    kickoff: str = FUTURE_KICKOFF_UTC,
    *,
    status: str = "NS",
    reliable: bool = True,
    conflict: bool = False,
    fresh: bool = True,
    captured_at: str = "2026-06-23T10:00:00Z",
    bookmaker_count: int = 4,
) -> dict[str, object]:
    return {
        "fixture_id": fixture_id,
        "status": status,
        "scheduled_kickoff_utc": kickoff,
        "provider_mapping": {
            "reliable": reliable,
            "conflict": conflict,
            "source": "unit-test",
            "evidence_sha256": "a" * 64,
        },
        "market_observation": {
            "market": "ONE_X_TWO",
            "captured_at_utc": captured_at,
            "source": "unit-test",
            "provenance": {"fixture_id": fixture_id},
            "freshness_limit_seconds": 3600,
            "evidence_sha256": "b" * 64,
            "fresh": fresh,
            "bookmaker_count": bookmaker_count,
        },
    }


def selection_payload(fixture_id: str = "200001") -> dict[str, object]:
    return {
        "generated_at_utc": "2026-06-23T10:00:00Z",
        "source": "W2_STAGING_PROVIDER_DATA",
        "policy": {},
        "candidates": [candidate(fixture_id)],
        "selected_fixture": candidate(fixture_id),
        "rejected_candidates": [],
        "candidate": False,
        "formal_recommendation": False,
    }


def bootstrap_payload(tmp_path: Path, fixture_id: str = "200001") -> dict[str, object]:
    selection = write_json(tmp_path / "selection.json", selection_payload(fixture_id))
    return {
        "status": "IN_PROGRESS",
        "fixture_id": fixture_id,
        "scheduled_kickoff_utc": FUTURE_KICKOFF_UTC,
        "observer_started_at_utc": "2026-06-23T10:01:00Z",
        "baseline_revision": "abc123",
        "expected_alembic_head": EXPECTED_HEAD,
        "observer_id": "stage7i-test",
        "runtime_dir": str(tmp_path),
        "global_lock_path": "/opt/w2/shared/runtime/stage7i/observer-global.lock",
        "selection_json_path": str(selection),
        "selection_sha256": "abc",
        "candidate": False,
        "formal_recommendation": False,
        "gate5_eligible": False,
        "evidence_classification": "FORWARD_OBSERVATION",
        "initial_sample": {
            "fixture_id": fixture_id,
            "captured_at_utc": "2026-06-23T10:01:01Z",
            "candidate": False,
            "formal_recommendation": False,
        },
    }


def test_run01_archive_validates_only_in_archive_mode() -> None:
    archive = ROOT / "reports/W2_STAGE7I_OBSERVATION_START.json"
    ok = run_cli([PYTHON, "scripts/check_w2_stage7i.py", "--mode", "archive", str(archive)])
    assert ok.returncode == 0, ok.stderr

    blocked = run_cli([PYTHON, "scripts/check_w2_stage7i.py", "--mode", "final", str(archive)])
    assert blocked.returncode != 0


def test_bootstrap_accepts_dynamic_successor_fixture_ids(tmp_path: Path) -> None:
    for fixture_id in ["200001", "200002"]:
        start = write_json(
            tmp_path / f"start-{fixture_id}.json",
            bootstrap_payload(tmp_path, fixture_id),
        )
        result = run_cli(
            [
                PYTHON,
                "scripts/check_w2_stage7i.py",
                "--mode",
                "bootstrap",
                "--expected-fixture-id",
                fixture_id,
                str(start),
            ]
        )
        assert result.returncode == 0, result.stderr


def test_bootstrap_accepts_legacy_start_without_runtime_dir(tmp_path: Path) -> None:
    payload = bootstrap_payload(tmp_path, "200001")
    payload.pop("runtime_dir")
    start = write_json(tmp_path / "legacy-start.json", payload)

    result = run_cli(
        [
            PYTHON,
            "scripts/check_w2_stage7i.py",
            "--mode",
            "bootstrap",
            "--expected-fixture-id",
            "200001",
            str(start),
        ]
    )

    assert result.returncode == 0, result.stderr


def test_bootstrap_rejects_archived_fixture_and_bad_flags(tmp_path: Path) -> None:
    start_payload = bootstrap_payload(tmp_path, "1489401")
    start = write_json(tmp_path / "start.json", start_payload)
    result = run_cli([PYTHON, "scripts/check_w2_stage7i.py", "--mode", "bootstrap", str(start)])
    assert result.returncode != 0

    start_payload = bootstrap_payload(tmp_path, "200001")
    start_payload["candidate"] = True
    start = write_json(tmp_path / "candidate.json", start_payload)
    result = run_cli([PYTHON, "scripts/check_w2_stage7i.py", "--mode", "bootstrap", str(start)])
    assert result.returncode != 0

    start_payload = bootstrap_payload(tmp_path, "200001")
    start_payload["formal_recommendation"] = True
    start = write_json(tmp_path / "formal.json", start_payload)
    result = run_cli([PYTHON, "scripts/check_w2_stage7i.py", "--mode", "bootstrap", str(start)])
    assert result.returncode != 0


def test_bootstrap_rejects_selection_mismatch_and_claimed_actuals(tmp_path: Path) -> None:
    start_payload = bootstrap_payload(tmp_path, "200001")
    start_payload["fixture_id"] = "200099"
    start = write_json(tmp_path / "mismatch.json", start_payload)
    result = run_cli([PYTHON, "scripts/check_w2_stage7i.py", "--mode", "bootstrap", str(start)])
    assert result.returncode != 0

    start_payload = bootstrap_payload(tmp_path, "200001")
    start_payload["actual_kickoff_utc"] = "2026-06-24T12:00:00Z"
    start = write_json(tmp_path / "actual.json", start_payload)
    result = run_cli([PYTHON, "scripts/check_w2_stage7i.py", "--mode", "bootstrap", str(start)])
    assert result.returncode != 0


def test_final_rejects_duplicate_time_reversal_and_bad_closing(tmp_path: Path) -> None:
    final_payload: dict[str, object] = {
        "status": "COMPLETED",
        "fixture_id": "200001",
        "observer_started_at_utc": "2026-06-23T10:00:00Z",
        "completed_at_utc": "2026-06-24T10:01:00Z",
        "stable_revision": True,
        "actual_kickoff_utc": "2026-06-24T09:00:00Z",
        "closing_observation_utc": "2026-06-24T08:50:00Z",
        "candidate": False,
        "formal_recommendation": False,
        "forward_retrospective_separated": True,
        "settlement_evaluation_legal": True,
        "final_shadow_db_audit": "PASS",
        "evidence_events": [
            {
                "event_id": "f1",
                "fixture_id": "200001",
                "evidence_category": "FORWARD",
                "event_time_utc": "2026-06-24T08:50:00Z",
                "candidate": False,
                "formal_recommendation": False,
            },
            {
                "event_id": "r1",
                "fixture_id": "200001",
                "evidence_category": "RETROSPECTIVE",
                "event_time_utc": "2026-06-24T10:00:00Z",
                "candidate": False,
                "formal_recommendation": False,
            },
        ],
    }
    ok = write_json(tmp_path / "final.json", final_payload)
    result = run_cli([PYTHON, "scripts/check_w2_stage7i.py", "--mode", "final", str(ok)])
    assert result.returncode == 0, result.stderr

    bad = dict(final_payload)
    bad["closing_observation_utc"] = "2026-06-24T09:00:00Z"
    path = write_json(tmp_path / "bad-closing.json", bad)
    assert (
        run_cli([PYTHON, "scripts/check_w2_stage7i.py", "--mode", "final", str(path)]).returncode
        != 0
    )

    bad = dict(final_payload)
    bad["evidence_events"] = [
        final_payload["evidence_events"][0],  # type: ignore[index]
        final_payload["evidence_events"][0],  # type: ignore[index]
    ]
    path = write_json(tmp_path / "duplicate.json", bad)
    assert (
        run_cli([PYTHON, "scripts/check_w2_stage7i.py", "--mode", "final", str(path)]).returncode
        != 0
    )

    bad = dict(final_payload)
    bad["evidence_events"] = list(reversed(final_payload["evidence_events"]))  # type: ignore[arg-type]
    path = write_json(tmp_path / "reversal.json", bad)
    assert (
        run_cli([PYTHON, "scripts/check_w2_stage7i.py", "--mode", "final", str(path)]).returncode
        != 0
    )


def test_selector_rejects_invalid_candidates_and_non_localhost(tmp_path: Path) -> None:
    input_path = write_json(
        tmp_path / "fixtures.json",
        {
            "source": "W2_STAGING_PROVIDER_DATA",
            "candidates": [
                candidate("1489401"),
                candidate("200001", kickoff="2026-06-23T10:10:00Z"),
                candidate("200002", reliable=False),
                candidate("200003", fresh=False),
                candidate("200004", captured_at="2026-06-23T10:01:00Z"),
            ],
            "candidate": False,
            "formal_recommendation": False,
        },
    )
    result = run_cli(
        [
            PYTHON,
            "scripts/select_stage7i_successor.py",
            "--input-json",
            str(input_path),
            "--global-lock-path",
            str(tmp_path / "observer-global.lock"),
            "--now-utc",
            "2026-06-23T10:00:00Z",
        ]
    )
    assert result.returncode == 2
    assert "NO_ELIGIBLE_SUCCESSOR_FIXTURE" in result.stdout

    result = run_cli([PYTHON, "scripts/select_stage7i_successor.py", "--api-base", "https://example.com"])
    assert result.returncode == 1


def test_selector_sorts_deterministically(tmp_path: Path) -> None:
    input_path = write_json(
        tmp_path / "fixtures.json",
        {
            "source": "W2_STAGING_PROVIDER_DATA",
            "candidates": [
                candidate(
                    "200002",
                    kickoff="2026-06-23T22:00:00Z",
                    captured_at="2026-06-23T09:55:00Z",
                    bookmaker_count=3,
                ),
                candidate(
                    "200001",
                    kickoff="2026-06-23T22:00:00Z",
                    captured_at="2026-06-23T09:59:00Z",
                    bookmaker_count=2,
                ),
            ],
            "candidate": False,
            "formal_recommendation": False,
        },
    )
    result = run_cli(
        [
            PYTHON,
            "scripts/select_stage7i_successor.py",
            "--input-json",
            str(input_path),
            "--global-lock-path",
            str(tmp_path / "observer-global.lock"),
            "--now-utc",
            "2026-06-23T10:00:00Z",
        ]
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["selected_fixture"]["fixture_id"] == "200001"


def test_selector_detects_active_global_lock(tmp_path: Path) -> None:
    input_path = write_json(
        tmp_path / "fixtures.json",
        {
            "source": "W2_STAGING_PROVIDER_DATA",
            "candidates": [candidate("200001", kickoff="2026-06-23T22:00:00Z")],
            "candidate": False,
            "formal_recommendation": False,
        },
    )
    lock_path = tmp_path / "observer-global.lock"
    with lock_path.open("w", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = run_cli(
            [
                PYTHON,
                "scripts/select_stage7i_successor.py",
                "--input-json",
                str(input_path),
                "--global-lock-path",
                str(lock_path),
                "--now-utc",
                "2026-06-23T10:00:00Z",
            ]
        )
    assert result.returncode == 2
    assert "ACTIVE_GLOBAL_OBSERVER_LOCK" in result.stdout


def test_observer_once_writes_fixture_specific_state_and_global_lock(tmp_path: Path) -> None:
    current = tmp_path / "current"
    versions = current / "migrations/versions"
    versions.mkdir(parents=True)
    (current / "DEPLOYMENT_REVISION").write_text("abc123\n", encoding="utf-8")
    (versions / "0017.py").write_text(
        f"revision = '{EXPECTED_HEAD}'\ndown_revision = None\n",
        encoding="utf-8",
    )
    selection = write_json(tmp_path / "selection.json", selection_payload("200001"))
    runtime = tmp_path / "runtime"
    lock = tmp_path / "observer-global.lock"
    result = run_cli(
        [
            PYTHON,
            "scripts/run_stage7i_observer.py",
            "--runtime-dir",
            str(runtime),
            "--current-dir",
            str(current),
            "--fixture-id",
            "200001",
            "--scheduled-kickoff-utc",
            FUTURE_KICKOFF_UTC,
            "--baseline-revision",
            "abc123",
            "--expected-alembic-head",
            EXPECTED_HEAD,
            "--selection-json",
            str(selection),
            "--global-lock-path",
            str(lock),
            "--once",
        ]
    )
    assert result.returncode == 0, result.stderr
    start = json.loads((runtime / "start.json").read_text())
    assert start["fixture_id"] == "200001"
    assert start["global_lock_path"] == str(lock)
    assert start["expected_alembic_head"] == EXPECTED_HEAD
    assert start["candidate"] is False
    assert start["formal_recommendation"] is False


def test_observer_rejects_alembic_head_mismatch(tmp_path: Path) -> None:
    current = tmp_path / "current"
    versions = current / "migrations/versions"
    versions.mkdir(parents=True)
    (current / "DEPLOYMENT_REVISION").write_text("abc123\n", encoding="utf-8")
    (versions / "0016.py").write_text(
        "revision = 'old_head'\ndown_revision = None\n",
        encoding="utf-8",
    )
    selection = write_json(tmp_path / "selection.json", selection_payload("200001"))
    result = run_cli(
        [
            PYTHON,
            "scripts/run_stage7i_observer.py",
            "--runtime-dir",
            str(tmp_path / "runtime"),
            "--current-dir",
            str(current),
            "--fixture-id",
            "200001",
            "--scheduled-kickoff-utc",
            "2026-06-24T12:00:00Z",
            "--baseline-revision",
            "abc123",
            "--expected-alembic-head",
            EXPECTED_HEAD,
            "--selection-json",
            str(selection),
            "--global-lock-path",
            str(tmp_path / "observer-global.lock"),
            "--once",
        ]
    )
    assert result.returncode != 0
