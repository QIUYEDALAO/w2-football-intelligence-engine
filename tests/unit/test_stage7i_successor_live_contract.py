from __future__ import annotations

import fcntl
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = sys.executable


def run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=ROOT, text=True, capture_output=True, check=False)


def write_json(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def fixture(fixture_id: str = "200001", kickoff: str = "2026-06-23T22:00:00Z") -> dict[str, object]:
    return {
        "fixture_id": fixture_id,
        "competition_id": "world_cup_2026",
        "status": "NS",
        "kickoff_utc": kickoff,
    }


def mapping(
    fixture_id: str = "200001",
    *,
    reliable: bool = True,
    conflict: bool = False,
    confidence: float = 0.95,
    evidence: bool = True,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "fixture_id": fixture_id,
        "provider": "api_football",
        "provider_fixture_id": "pf-200001",
        "home_provider_team_id": "home-1",
        "away_provider_team_id": "away-1",
        "source": "unit-test-mapping",
        "confidence": confidence,
        "reliable": reliable,
        "conflict": conflict,
    }
    if evidence:
        payload["evidence_sha256"] = "a" * 64
    return payload


def market(
    fixture_id: str = "200001",
    *,
    captured_at: str = "2026-06-23T09:50:00Z",
    bookmaker_count: int = 4,
    live: bool = False,
    suspended: bool = False,
    evidence: bool = True,
    freshness_limit_seconds: int = 3600,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "fixture_id": fixture_id,
        "market": "ONE_X_TWO",
        "captured_at_utc": captured_at,
        "bookmaker_count": bookmaker_count,
        "suspended": suspended,
        "live": live,
        "source": "unit-test-market",
        "provenance": {"snapshot_id": "snap-1"},
        "freshness_limit_seconds": freshness_limit_seconds,
    }
    if evidence:
        payload["evidence_sha256"] = "b" * 64
    return payload


def build_manifest(
    tmp_path: Path,
    *,
    fixtures: list[dict[str, object]] | None = None,
    mappings: list[dict[str, object]] | None = None,
    markets: list[dict[str, object]] | None = None,
    now: str = "2026-06-23T10:00:00Z",
) -> tuple[subprocess.CompletedProcess[str], Path]:
    fixture_path = write_json(
        tmp_path / "fixtures.json",
        {"items": [fixture()] if fixtures is None else fixtures},
    )
    mapping_path = write_json(
        tmp_path / "mappings.json",
        {"items": [mapping()] if mappings is None else mappings},
    )
    market_path = write_json(
        tmp_path / "markets.json",
        {"items": [market()] if markets is None else markets},
    )
    output = tmp_path / "manifest.json"
    result = run_cli(
        [
            PYTHON,
            "scripts/build_stage7i_successor_candidates.py",
            "--fixtures-input",
            str(fixture_path),
            "--mapping-input",
            str(mapping_path),
            "--market-input",
            str(market_path),
            "--now-utc",
            now,
            "--output",
            str(output),
            "--source-revision",
            "unit-test",
        ]
    )
    return result, output


def select_manifest(
    tmp_path: Path,
    manifest: Path,
    *,
    now: str = "2026-06-23T10:00:00Z",
    runtime_root: Path | None = None,
    lock_path: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    return run_cli(
        [
            PYTHON,
            "scripts/select_stage7i_successor.py",
            "--candidate-manifest",
            str(manifest),
            "--now-utc",
            now,
            "--runtime-root",
            str(runtime_root or tmp_path / "runtime"),
            "--global-lock-path",
            str(lock_path or tmp_path / "observer-global.lock"),
        ]
    )


def test_fixture_summary_is_not_candidate_manifest(tmp_path: Path) -> None:
    summary = write_json(tmp_path / "fixtures.json", {"items": [fixture()]})
    result = run_cli(
        [PYTHON, "scripts/select_stage7i_successor.py", "--input-json", str(summary)]
    )
    assert result.returncode == 1
    assert "candidate manifest" in result.stderr


def test_builder_creates_manifest_from_explicit_evidence(tmp_path: Path) -> None:
    result, output = build_manifest(tmp_path)
    assert result.returncode == 0, result.stderr
    payload = json.loads(output.read_text())
    assert payload["candidate"] is False
    assert payload["formal_recommendation"] is False
    assert payload["candidates"][0]["provider_mapping"]["evidence_sha256"]
    assert payload["candidates"][0]["market_observation"]["fresh"] is True


def test_builder_rejects_missing_and_conflicting_mapping(tmp_path: Path) -> None:
    _, output = build_manifest(tmp_path, mappings=[])
    payload = json.loads(output.read_text())
    assert payload["candidates"] == []
    assert "PROVIDER_MAPPING_MISSING" in payload["rejected_candidates"][0]["reasons"]

    _, output = build_manifest(tmp_path, mappings=[mapping(conflict=True)])
    payload = json.loads(output.read_text())
    assert "PROVIDER_MAPPING_CONFLICT" in payload["rejected_candidates"][0]["reasons"]

    _, output = build_manifest(tmp_path, mappings=[mapping(confidence=0.2)])
    payload = json.loads(output.read_text())
    assert (
        "PROVIDER_MAPPING_CONFIDENCE_INSUFFICIENT"
        in payload["rejected_candidates"][0]["reasons"]
    )


def test_builder_rejects_market_contract_failures(tmp_path: Path) -> None:
    cases = [
        ([], "MARKET_OBSERVATION_MISSING"),
        ([market(captured_at="2026-06-23T08:00:00Z")], "MARKET_STALE"),
        ([market(captured_at="2026-06-23T10:01:00Z")], "MARKET_CAPTURED_AT_NOT_BEFORE_SELECTION"),
        ([market(live=True)], "MARKET_LIVE"),
        ([market(suspended=True)], "MARKET_SUSPENDED"),
        ([market(bookmaker_count=0)], "MARKET_BOOKMAKER_COVERAGE_MISSING"),
    ]
    for markets, reason in cases:
        _, output = build_manifest(tmp_path, markets=markets)
        payload = json.loads(output.read_text())
        assert reason in payload["rejected_candidates"][0]["reasons"]


def test_selector_revalidates_freshness_and_evidence(tmp_path: Path) -> None:
    _, output = build_manifest(
        tmp_path,
        markets=[
            {
                **market(captured_at="2026-06-23T09:50:00Z", freshness_limit_seconds=60),
                "fresh": True,
            }
        ],
    )
    payload = json.loads(output.read_text())
    assert payload["candidates"] == []
    manifest = write_json(
        tmp_path / "forged.json",
        {
            "generated_at_utc": "2026-06-23T10:00:00Z",
            "source": "W2_STAGING_PROVIDER_DATA",
            "candidates": [
                {
                    "fixture_id": "200001",
                    "status": "NS",
                    "scheduled_kickoff_utc": "2026-06-23T22:00:00Z",
                    "provider_mapping": mapping(),
                    "market_observation": {**market(freshness_limit_seconds=60), "fresh": True},
                }
            ],
            "candidate": False,
            "formal_recommendation": False,
        },
    )
    result = select_manifest(tmp_path, manifest)
    assert result.returncode == 2
    assert "MARKET_STALE" in result.stdout


def test_selector_dry_run_does_not_create_absent_lock(tmp_path: Path) -> None:
    _, manifest = build_manifest(tmp_path)
    lock = tmp_path / "missing" / "observer-global.lock"
    result = select_manifest(tmp_path, manifest, lock_path=lock)
    assert result.returncode == 0, result.stderr
    assert not lock.exists()


def test_selector_rejects_held_global_lock(tmp_path: Path) -> None:
    _, manifest = build_manifest(tmp_path)
    lock = tmp_path / "observer-global.lock"
    lock.touch()
    with lock.open("r+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = select_manifest(tmp_path, manifest, lock_path=lock)
    assert result.returncode == 2
    assert "ACTIVE_GLOBAL_OBSERVER_LOCK" in result.stdout


def test_selector_rejects_live_legacy_pid_but_not_stale_pid(tmp_path: Path) -> None:
    _, manifest = build_manifest(tmp_path)
    runtime = tmp_path / "runtime" / "runs" / "run-1"
    runtime.mkdir(parents=True)
    (runtime / "observer.pid").write_text(str(99999999), encoding="utf-8")
    assert select_manifest(tmp_path, manifest, runtime_root=tmp_path / "runtime").returncode == 0

    process = subprocess.Popen(["sleep", "5"])
    try:
        (runtime / "observer.pid").write_text(str(process.pid), encoding="utf-8")
        result = select_manifest(tmp_path, manifest, runtime_root=tmp_path / "runtime")
        assert result.returncode == 2
        assert "ACTIVE_STAGE7I_OBSERVER" in result.stdout
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_selector_enforces_six_hour_window_and_url_policy(tmp_path: Path) -> None:
    _, early = build_manifest(tmp_path, fixtures=[fixture(kickoff="2026-06-23T12:00:00Z")])
    assert select_manifest(tmp_path, early).returncode == 2

    _, late = build_manifest(tmp_path, fixtures=[fixture(kickoff="2026-06-24T08:00:00Z")])
    assert select_manifest(tmp_path, late).returncode == 2

    result = run_cli([PYTHON, "scripts/select_stage7i_successor.py", "--api-base", "https://example.com"])
    assert result.returncode == 1
