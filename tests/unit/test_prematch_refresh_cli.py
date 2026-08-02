from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from types import SimpleNamespace
from typing import Any

import pytest
import scripts.materialize_analysis_card_canary as canary_cli
import scripts.run_prematch_refresh as refresh_cli

from w2.operations.gate_a import GateAError
from w2.prematch.analysis_calculator import ReadModelService


class _Authorization:
    authorization_id = "test-authorization"
    fixture_id = "1489404"
    fixture_scope_mode = "EXACT_FIXTURE_ID"

    def validate_scope(self, **kwargs: Any) -> None:
        if kwargs["persistence"] != "db":
            raise GateAError("GATE_A_DB_PERSISTENCE_REQUIRED")


def _authorize_execute(monkeypatch: Any) -> object:
    authorization = _Authorization()
    reservation = object()
    monkeypatch.setattr(
        "w2.operations.gate_a.GateARuntimeAuthorization.load",
        lambda _path: authorization,
    )
    monkeypatch.setattr(
        "w2.operations.gate_a.reserve_gate_a_run",
        lambda *_args, **_kwargs: reservation,
    )
    monkeypatch.setattr(
        "w2.ingestion.future_refresh.load_refresh_policy",
        lambda **_kwargs: SimpleNamespace(
            season="2026",
            provider_league_id="1",
            config_hash="d" * 64,
        ),
    )
    monkeypatch.setattr("w2.monitoring.readiness.schema_check", lambda _settings: (True, "ok"))
    monkeypatch.setattr(
        refresh_cli,
        "exact_code_identity",
        lambda: refresh_cli.ExactCodeIdentity(
            head="a" * 40,
            tree="b" * 40,
            execution_mode="COMPLETE_CLEAN_CHECKOUT",
            complete_checkout_manifest_sha256="c" * 64,
        ),
    )
    return reservation


def test_prematch_refresh_defaults_to_no_provider_call_plan() -> None:
    completed = subprocess.run(
        [
            "python3",
            "scripts/run_prematch_refresh.py",
            "--competition-id",
            "world_cup_2026",
            "--season",
            "2026",
            "--now-utc",
            "2026-06-27T00:08:25Z",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)
    assert payload["status"] == "DRY_RUN"
    assert payload["would_execute"] is False
    assert payload["provider_calls"] is False
    assert payload["task_key"] == "future-refresh:world_cup_2026:2026:20260627T000000Z"
    assert payload["candidate"] is False
    assert payload["formal_recommendation"] is False
    assert payload["beats_market"] is False


def test_exact_code_identity_uses_clean_git_head_and_tree_not_environment(
    monkeypatch: Any,
) -> None:
    monkeypatch.setenv("W2_GIT_SHA", "c" * 40)

    index = b"100644 aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa 0\tsrc/w2/a.py\0"

    def git_output(*args: str) -> bytes:
        if args[0] == "status" or "--ignored" in args:
            return b""
        if args == ("rev-parse", "HEAD"):
            return ("a" * 40 + "\n").encode()
        if args == ("rev-parse", "HEAD^{tree}"):
            return ("b" * 40 + "\n").encode()
        assert args == ("ls-files", "-s", "-z")
        return index

    monkeypatch.setattr(refresh_cli, "_git_bytes", git_output)

    manifest = hashlib.sha256(
        b"W2_COMPLETE_CLEAN_CHECKOUT_V1\0"
        + ("a" * 40).encode()
        + b"\0"
        + ("b" * 40).encode()
        + b"\0"
        + index
    ).hexdigest()

    assert refresh_cli.exact_code_identity() == refresh_cli.ExactCodeIdentity(
        head="a" * 40,
        tree="b" * 40,
        execution_mode="COMPLETE_CLEAN_CHECKOUT",
        complete_checkout_manifest_sha256=manifest,
    )


def test_exact_code_identity_rejects_dirty_checkout(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        refresh_cli,
        "_git_bytes",
        lambda *_args: b" M src/w2/providers/control.py",
    )

    with pytest.raises(RuntimeError, match="GATE_A_COMPLETE_CHECKOUT_DIRTY_OR_UNTRACKED"):
        refresh_cli.exact_code_identity()


def test_exact_code_identity_rejects_ignored_executable(
    monkeypatch: Any,
    tmp_path: Any,
) -> None:
    ignored = tmp_path / "ignored.py"
    ignored.write_text("pass\n")
    monkeypatch.setattr(refresh_cli, "ROOT", tmp_path)

    def git_output(*args: str) -> bytes:
        if args[0] == "status":
            return b""
        if "--ignored" in args:
            return b"ignored.py\0"
        return b""

    monkeypatch.setattr(refresh_cli, "_git_bytes", git_output)
    with pytest.raises(RuntimeError, match="GATE_A_IGNORED_EXECUTABLE_CONTENT_PRESENT"):
        refresh_cli.exact_code_identity()


def test_prematch_refresh_execute_requires_explicit_authorization(
    monkeypatch: Any,
) -> None:
    calls = 0

    def run_future_refresh_task(**_kwargs: Any) -> SimpleNamespace:
        nonlocal calls
        calls += 1
        return SimpleNamespace()

    monkeypatch.setattr(
        "w2.ingestion.future_refresh.run_future_refresh_task",
        run_future_refresh_task,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_prematch_refresh.py", "--execute", "--persistence", "db"],
    )

    with pytest.raises(SystemExit):
        refresh_cli.main()
    assert calls == 0


def test_prematch_refresh_migration_mismatch_blocks_before_reservation_and_provider(
    monkeypatch: Any,
) -> None:
    calls = 0
    _authorize_execute(monkeypatch)

    def forbidden(*_args: Any, **_kwargs: Any) -> object:
        nonlocal calls
        calls += 1
        return object()

    monkeypatch.setattr(
        "w2.monitoring.readiness.schema_check",
        lambda _settings: (False, "database revision does not match code head"),
    )
    monkeypatch.setattr("w2.operations.gate_a.reserve_gate_a_run", forbidden)
    monkeypatch.setattr(
        "w2.ingestion.future_refresh.run_future_refresh_task",
        forbidden,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_prematch_refresh.py",
            "--execute",
            "--persistence",
            "db",
            "--authorization-file",
            "authorization.json",
        ],
    )

    with pytest.raises(SystemExit):
        refresh_cli.main()
    assert calls == 0


def test_prematch_refresh_policy_season_mismatch_blocks_before_authorization(
    monkeypatch: Any,
) -> None:
    calls = 0

    def forbidden(*_args: Any, **_kwargs: Any) -> object:
        nonlocal calls
        calls += 1
        return object()

    monkeypatch.setattr(
        refresh_cli,
        "exact_code_identity",
        lambda: refresh_cli.ExactCodeIdentity(
            head="a" * 40,
            tree="b" * 40,
            execution_mode="COMPLETE_CLEAN_CHECKOUT",
            complete_checkout_manifest_sha256="c" * 64,
        ),
    )
    monkeypatch.setattr(
        "w2.ingestion.future_refresh.load_refresh_policy",
        lambda **_kwargs: SimpleNamespace(season="2027"),
    )
    monkeypatch.setattr("w2.operations.gate_a.GateARuntimeAuthorization.load", forbidden)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_prematch_refresh.py",
            "--execute",
            "--persistence",
            "db",
            "--authorization-file",
            "authorization.json",
            "--season",
            "2026",
        ],
    )

    with pytest.raises(SystemExit):
        refresh_cli.main()
    assert calls == 0


def test_materialize_analysis_card_canary_executes_active_calculator_entry(
    monkeypatch: Any,
    capsys: Any,
) -> None:
    class Repository:
        def fixture_payload(self, fixture_id: str) -> dict[str, Any]:
            return {
                "fixture": {"id": fixture_id, "date": "2026-07-18T06:00:00Z"},
                "league": {"id": "league"},
                "teams": {
                    "home": {"id": "home"},
                    "away": {"id": "away"},
                },
            }

        def future_market_observations_for_fixtures(
            self,
            fixture_ids: list[str],
        ) -> list[dict[str, Any]]:
            return [{"fixture_id": fixture_ids[0], "capture_id": "capture-1"}]

    calls = 0

    def calculate(
        _self: ReadModelService,
        fixture_id: str,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {
            "fixture_id": fixture_id,
            "competition_id": "league",
            "market_candidates": {},
        }

    monkeypatch.setattr(canary_cli, "ReadModelRepository", Repository)
    monkeypatch.setattr(ReadModelService, "public_analysis_card_bounded", calculate)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "materialize_analysis_card_canary.py",
            "--fixture-id",
            "fixture-1",
            "--evaluated-at",
            "2026-07-18T05:00:00Z",
        ],
    )

    assert canary_cli.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert calls == 1
    assert payload["status"] == "DRY_RUN"
    assert payload["artifacts"][0]["checkpoint_key"] == ("analysis-card:frozen:v1:fixture-1")


def test_prematch_refresh_execute_db_injects_shadow_composition_adapter(
    monkeypatch: Any,
    capsys: Any,
) -> None:
    captured: dict[str, Any] = {}
    reservation = _authorize_execute(monkeypatch)

    def run_future_refresh_task(**kwargs: Any) -> SimpleNamespace:
        captured.update(kwargs)
        return SimpleNamespace(
            status="COMPLETED",
            task_id=kwargs["task_id"],
            key=kwargs["key"],
            result={"provider_calls": 0},
        )

    monkeypatch.setattr(
        "w2.ingestion.future_refresh.run_future_refresh_task",
        run_future_refresh_task,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_prematch_refresh.py",
            "--execute",
            "--persistence",
            "db",
            "--authorization-file",
            "authorization.json",
            "--now-utc",
            "2026-07-18T05:00:00Z",
        ],
    )

    assert refresh_cli.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "COMPLETED"
    assert captured["persistence"] == "db"
    assert captured["provider_call_reservation"] is reservation
    assert (
        captured["materialize_public_artifacts"] is refresh_cli.materialize_shadow_projection_events
    )


def test_prematch_refresh_execute_requires_explicit_db_persistence(
    monkeypatch: Any,
) -> None:
    calls = 0

    def run_future_refresh_task(**_kwargs: Any) -> SimpleNamespace:
        nonlocal calls
        calls += 1
        return SimpleNamespace()

    monkeypatch.setattr(
        "w2.ingestion.future_refresh.run_future_refresh_task",
        run_future_refresh_task,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_prematch_refresh.py",
            "--execute",
            "--authorization-file",
            "authorization.json",
            "--now-utc",
            "2026-07-18T05:00:00Z",
        ],
    )

    with pytest.raises(SystemExit):
        refresh_cli.main()
    assert calls == 0


def test_prematch_refresh_execute_rejects_file_persistence_before_provider_call(
    monkeypatch: Any,
    capsys: Any,
) -> None:
    calls = 0

    def run_future_refresh_task(**kwargs: Any) -> SimpleNamespace:
        nonlocal calls
        calls += 1
        return SimpleNamespace(
            status="COMPLETED",
            task_id=kwargs["task_id"],
            key=kwargs["key"],
            result={"provider_calls": 0},
        )

    monkeypatch.setenv("W2_FUTURE_REFRESH_PERSISTENCE", "file")
    _authorize_execute(monkeypatch)
    monkeypatch.setattr(
        "w2.ingestion.future_refresh.run_future_refresh_task",
        run_future_refresh_task,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_prematch_refresh.py",
            "--execute",
            "--persistence",
            "file",
            "--authorization-file",
            "authorization.json",
            "--now-utc",
            "2026-07-18T05:00:00Z",
        ],
    )

    with pytest.raises(SystemExit):
        refresh_cli.main()
    assert calls == 0


def test_prematch_refresh_already_running_has_distinct_nonzero_exit(
    monkeypatch: Any,
    capsys: Any,
) -> None:
    _authorize_execute(monkeypatch)

    def run_future_refresh_task(**kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(
            status="ALREADY_RUNNING",
            task_id=kwargs["task_id"],
            key=kwargs["key"],
            result={},
        )

    monkeypatch.setattr(
        "w2.ingestion.future_refresh.run_future_refresh_task",
        run_future_refresh_task,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_prematch_refresh.py",
            "--execute",
            "--persistence",
            "db",
            "--authorization-file",
            "authorization.json",
        ],
    )

    assert refresh_cli.main() == 2
    assert json.loads(capsys.readouterr().out)["status"] == "ALREADY_RUNNING"
