from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from scripts.check_w2_market_timeline import _artifact_paths

from w2.ingestion.market_timeline_refresh import run_market_timeline_refresh


def test_market_timeline_refresh_defaults_to_dry_run_and_no_provider_calls(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_w2_market_timeline_refresh.py",
            "--window",
            "next36",
            "--checkpoint",
            "auto",
            "--runtime-root",
            str(tmp_path),
            "--remaining-quota-override",
            "1",
            "--json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert payload["dry_run"] is True
    assert payload["write_artifacts"] is False
    assert payload["provider_calls"] == 0
    assert payload["quota_decision"]["allowed"] is False
    assert payload["quota_decision"]["reason"] in {
        "QUOTA_CRITICAL_CORE_ONLY",
        "BACKFILL_QUOTA_GUARD",
        "QUOTA_BELOW_RESERVE",
    }
    assert list(tmp_path.glob("*.json")) == []


def test_market_timeline_refresh_cli_respects_runtime_root_env(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_w2_market_timeline_refresh.py",
            "--window",
            "next36",
            "--checkpoint",
            "auto",
            "--remaining-quota-override",
            "1",
            "--json",
        ],
        check=True,
        capture_output=True,
        text=True,
        env={"W2_MARKET_TIMELINE_RUNTIME_ROOT": str(tmp_path)},
    )

    payload = json.loads(result.stdout)
    assert payload["runtime_root"] == str(tmp_path)
    assert payload["dry_run"] is True


def test_market_timeline_refresh_service_respects_max_fixtures_and_does_not_backfill(
    tmp_path: Path,
) -> None:
    class Repository:
        def fixture_payloads(self) -> list[dict[str, object]]:
            return [
                {"fixture": {"id": "fx1", "date": "2026-06-28T18:00:00Z"}},
                {"fixture": {"id": "fx2", "date": "2026-06-28T19:00:00Z"}},
            ]

        def future_market_observations_for_fixtures(
            self,
            fixture_ids: list[str],
        ) -> list[dict[str, object]]:
            return [
                {
                    "fixture_id": "fx1",
                    "captured_at": "2026-06-28T10:00:00Z",
                    "canonical_market": "ASIAN_HANDICAP",
                    "selection": "Home -0.25",
                    "line": "-0.25",
                    "decimal_odds": "1.94",
                    "bookmaker_id": "book-a",
                },
                {
                    "fixture_id": "fx1",
                    "captured_at": "2026-06-28T10:00:00Z",
                    "canonical_market": "ASIAN_HANDICAP",
                    "selection": "Away +0.25",
                    "line": "+0.25",
                    "decimal_odds": "1.97",
                    "bookmaker_id": "book-a",
                },
            ]

        def future_market_observations(self) -> list[dict[str, object]]:
            return []

    payload = run_market_timeline_refresh(
        checkpoint="auto",
        dry_run=False,
        write_artifacts=True,
        max_fixtures=1,
        runtime_root=tmp_path,
        remaining_quota_override="6774",
        repository=Repository(),
        now=datetime(2026, 6, 28, 12, 30, tzinfo=UTC),
    )

    assert payload["selected_fixtures"] == ["fx1"]
    assert payload["written"] == 1
    assert {item["checkpoint"] for item in payload["results"]} == {"opening"}
    assert "T-6h" not in {item["checkpoint"] for item in payload["results"]}


def test_market_timeline_refresh_enforces_quota_guard_before_write(
    tmp_path: Path,
) -> None:
    class Repository:
        def fixture_payloads(self) -> list[dict[str, object]]:
            raise AssertionError("blocked refresh must not load fixtures")

        def future_market_observations_for_fixtures(
            self,
            fixture_ids: list[str],
        ) -> list[dict[str, object]]:
            raise AssertionError("blocked refresh must not load observations")

        def future_market_observations(self) -> list[dict[str, object]]:
            raise AssertionError("blocked refresh must not load fallback observations")

    payload = run_market_timeline_refresh(
        checkpoint="auto",
        dry_run=False,
        write_artifacts=True,
        max_fixtures=10,
        runtime_root=tmp_path,
        remaining_quota_override="749",
        network_quota_required=True,
        repository=Repository(),
        now=datetime(2026, 6, 28, 12, 30, tzinfo=UTC),
    )

    assert payload["status"] == "BLOCKED"
    assert payload["blockers"] == ["QUOTA_CRITICAL_CORE_ONLY"]
    assert payload["written"] == 0
    assert payload["provider_calls"] == 0
    assert payload["snapshot_candidates"] == 0
    assert payload["results"] == []
    assert not any(tmp_path.glob("*.json"))


def test_market_timeline_refresh_local_materialization_ignores_low_network_quota(
    tmp_path: Path,
) -> None:
    class Repository:
        def fixture_payloads(self) -> list[dict[str, object]]:
            return [{"fixture": {"id": "fx1", "date": "2026-06-28T18:00:00Z"}}]

        def future_market_observations_for_fixtures(
            self,
            fixture_ids: list[str],
        ) -> list[dict[str, object]]:
            return [
                {
                    "fixture_id": "fx1",
                    "captured_at": "2026-06-28T10:00:00Z",
                    "canonical_market": "ASIAN_HANDICAP",
                    "selection": "Home -0.25",
                    "line": "-0.25",
                    "decimal_odds": "1.94",
                    "bookmaker_id": "book-a",
                },
                {
                    "fixture_id": "fx1",
                    "captured_at": "2026-06-28T10:00:00Z",
                    "canonical_market": "ASIAN_HANDICAP",
                    "selection": "Away +0.25",
                    "line": "+0.25",
                    "decimal_odds": "1.97",
                    "bookmaker_id": "book-a",
                },
            ]

        def future_market_observations(self) -> list[dict[str, object]]:
            return []

    payload = run_market_timeline_refresh(
        checkpoint="auto",
        dry_run=False,
        write_artifacts=True,
        runtime_root=tmp_path,
        remaining_quota_override="0",
        repository=Repository(),
        now=datetime(2026, 6, 28, 12, 30, tzinfo=UTC),
    )

    assert payload["status"] == "PASS"
    assert payload["network_quota_required"] is False
    assert payload["written"] == 1
    assert payload["provider_calls"] == 0
    assert any(item.get("status") == "WRITTEN" for item in payload["results"])
    assert any(tmp_path.glob("*.json"))


def test_market_timeline_refresh_reports_stale_lock_reason_without_lock_artifact(
    tmp_path: Path,
) -> None:
    class Repository:
        def fixture_payloads(self) -> list[dict[str, object]]:
            return [{"fixture": {"id": "fx1", "date": "2026-06-28T19:00:00Z"}}]

        def future_market_observations_for_fixtures(
            self,
            fixture_ids: list[str],
        ) -> list[dict[str, object]]:
            return [
                {
                    "fixture_id": "fx1",
                    "captured_at": "2026-06-28T12:41:41Z",
                    "canonical_market": "ASIAN_HANDICAP",
                    "selection": "Home +0.5",
                    "line": "+0.5",
                    "decimal_odds": "2.0",
                    "bookmaker_id": "book-a",
                },
                {
                    "fixture_id": "fx1",
                    "captured_at": "2026-06-28T12:41:41Z",
                    "canonical_market": "ASIAN_HANDICAP",
                    "selection": "Away +0.5",
                    "line": "+0.5",
                    "decimal_odds": "1.9",
                    "bookmaker_id": "book-a",
                },
            ]

        def future_market_observations(self) -> list[dict[str, object]]:
            return []

    payload = run_market_timeline_refresh(
        checkpoint="lock",
        dry_run=False,
        write_artifacts=True,
        runtime_root=tmp_path,
        remaining_quota_override="UNKNOWN",
        repository=Repository(),
        now=datetime(2026, 6, 28, 18, 30, tzinfo=UTC),
    )

    assert payload["status"] == "PASS"
    assert payload["network_quota_required"] is False
    assert payload["provider_calls"] == 0
    assert payload["written"] == 0
    assert payload["freshness_rejections"] == 1
    assert any(
        item.get("reason") == "NO_FRESH_LOCK_OBSERVATION"
        for item in payload["results"]
        if item.get("market") == "ASIAN_HANDICAP"
    )
    assert not any(tmp_path.glob("*.json"))


def test_market_timeline_checker_warns_missing_lock_without_failing(tmp_path: Path) -> None:
    artifact = tmp_path / "fx1.json"
    artifact.write_text(
        json.dumps(
            {
                "schema_version": "w2.market_timeline.v1",
                "fixture_id": "fx1",
                "kickoff_utc": "2026-06-28T12:00:00Z",
                "snapshots": [
                    {
                        "schema_version": "w2.market_timeline.v1",
                        "fixture_id": "fx1",
                        "checkpoint": "T-1h",
                        "market": "ASIAN_HANDICAP",
                        "as_of": "2026-06-28T10:50:00Z",
                        "kickoff_utc": "2026-06-28T12:00:00Z",
                        "line": -0.25,
                        "home_price": 1.94,
                        "away_price": 1.97,
                        "bookmaker_count": 1,
                        "source_hash": "hash",
                        "immutable": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/check_w2_market_timeline.py",
            "--runtime-root",
            str(tmp_path),
            "--json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert payload["status"] == "PASS"
    assert payload["errors"] == {}
    assert payload["warnings"] == {"fx1.json": ["MISSING_AH_LOCK_SNAPSHOT"]}


def test_market_timeline_checker_respects_runtime_root_env(tmp_path: Path) -> None:
    artifact = tmp_path / "fx1.json"
    artifact.write_text(
        json.dumps(
            {
                "schema_version": "w2.market_timeline.v1",
                "fixture_id": "fx1",
                "kickoff_utc": "2026-06-28T12:00:00Z",
                "snapshots": [],
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/check_w2_market_timeline.py",
            "--json",
        ],
        check=True,
        capture_output=True,
        text=True,
        env={"W2_MARKET_TIMELINE_RUNTIME_ROOT": str(tmp_path)},
    )

    payload = json.loads(result.stdout)
    assert payload["artifact_count"] == 1


def test_market_timeline_checker_skips_unreadable_runtime_root() -> None:
    class UnreadableRoot:
        def exists(self) -> bool:
            return True

        def glob(self, pattern: str) -> list[Path]:
            raise PermissionError("blocked")

    assert _artifact_paths(UnreadableRoot()) == []  # type: ignore[arg-type]
