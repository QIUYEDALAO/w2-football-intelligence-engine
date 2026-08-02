from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from scripts.run_prematch_refresh import planned_task_key
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from tests.unit.test_gate_a_offline import (
    PUBLIC_KEY,
    PUBLIC_KEY_SHA256,
    TRUSTED_KEYS,
    authorization_payload,
)

from w2.competitions.seed import seed_competition_runtime_authority
from w2.config import get_settings
from w2.infrastructure.database import Base
from w2.infrastructure.database import create_engine as w2_create_engine
from w2.ingestion.future_refresh import run_staged_gate_a_canary_task
from w2.operations.gate_a import GateARuntimeAuthorization, reserve_gate_a_run
from w2.prematch.repository import project_exact_eval_02b_pairs
from w2.providers.api_football import LiveApiFootballResponse

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ID = "1489404"


class _FakeProviderHandler(BaseHTTPRequestHandler):
    requests: list[str] = []
    kickoff_at: datetime

    def do_GET(self) -> None:  # noqa: N802
        type(self).requests.append(self.path)
        payload = self._payload()
        encoded = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("x-ratelimit-requests-remaining", "7000")
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _payload(self) -> dict[str, Any]:
        if self.path == "/status":
            return {"response": {"requests": {"remaining": 7000}}}
        if self.path.startswith("/fixtures?id="):
            return {
                "response": [
                    {
                        "fixture": {
                            "id": int(FIXTURE_ID),
                            "date": self.kickoff_at.isoformat(),
                            "status": {"short": "NS"},
                        },
                        "league": {"id": 1, "season": 2026},
                        "teams": {"home": {"id": 10}, "away": {"id": 20}},
                    }
                ]
            }
        if self.path.startswith("/odds?fixture="):
            return {
                "response": [
                    {
                        "fixture": {"id": int(FIXTURE_ID)},
                        "bookmakers": [
                            {
                                "id": 1,
                                "name": "Fake Book",
                                "bets": [
                                    {
                                        "id": 4,
                                        "name": "Asian Handicap",
                                        "values": [
                                            {"value": "Home -0.5", "odd": "1.91"},
                                            {"value": "Away +0.5", "odd": "1.93"},
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ]
            }
        if self.path.startswith("/fixtures/lineups?fixture="):
            return {"response": [_lineup(10, 100), _lineup(20, 200)]}
        raise AssertionError(self.path)


def _lineup(team_id: int, offset: int) -> dict[str, Any]:
    return {
        "team": {"id": team_id},
        "formation": "4-3-3",
        "startXI": [
            {"player": {"id": offset + index, "name": f"P{offset + index}"}} for index in range(11)
        ],
        "substitutes": [],
    }


def test_actual_cli_fake_provider_staged_canary_from_fresh_postgres(
    tmp_path: Path,
) -> None:
    source_url = os.environ.get("W2_TEST_POSTGRES_URL")
    if not source_url:
        pytest.skip("W2_TEST_POSTGRES_URL is required for staged CLI E2E")
    database_name = f"w2_staged_{uuid4().hex[:12]}"
    source = make_url(source_url)
    admin_url = source.set(database="postgres")
    database_url_text = source_url.replace(
        f"/{source.database}", f"/{database_name}", 1
    )
    with create_engine(admin_url, isolation_level="AUTOCOMMIT").connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    server = HTTPServer(("127.0.0.1", 0), _FakeProviderHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        now = datetime.now(UTC).replace(microsecond=0)
        _FakeProviderHandler.requests = []
        _FakeProviderHandler.kickoff_at = now + timedelta(hours=7)
        env = os.environ.copy()
        env.update(
            {
                "W2_DATABASE_URL": database_url_text,
                "W2_ENVIRONMENT": "test",
                "W2_PROVIDER_CALLS_DISABLED": "false",
                "W2_PROVIDER_ENDPOINT_ALLOWLIST": "status,fixtures,odds,lineups",
                "W2_PROVIDER_HTTP_MAX_ATTEMPTS": "1",
                "W2_API_FOOTBALL_API_KEY": "offline-fake-only",
                "W2_RUNTIME_ARTIFACT_DIGEST": "sha256:" + "d" * 64,
            }
        )
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=ROOT,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        tree = subprocess.check_output(
            ["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, text=True
        ).strip()
        task_key = planned_task_key(
            competition_id="world_cup_2026",
            season="2026",
            now=now,
            interval_seconds=900,
        )
        authorization = authorization_payload(
            authorization_id=f"offline-staged-{uuid4().hex}",
            task_key=task_key,
            fixture_id=FIXTURE_ID,
            exact_head=head,
            exact_tree=tree,
            execution_mode="IMMUTABLE_IMAGE",
            runtime_artifact_digest="sha256:" + "d" * 64,
            complete_checkout_manifest_sha256=None,
            issued_at=(now - timedelta(minutes=1)).isoformat(),
            expires_at=(now + timedelta(minutes=30)).isoformat(),
        )
        authorization_path = tmp_path / "authorization.json"
        authorization_path.write_text(json.dumps(authorization), encoding="utf-8")
        trust_path = tmp_path / "trust.json"
        trust_path.write_text(
            json.dumps(
                {
                    "schema_version": "w2.gate-a-authorization-trust.v1",
                    "trusted_ed25519_keys": {
                        "test-independent-key": {
                            "public_key_base64": PUBLIC_KEY,
                            "public_key_sha256": PUBLIC_KEY_SHA256,
                            "custody_status": "INDEPENDENT_SIGNER_CONFIRMED",
                            "authorization_enabled": True,
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        evidence_path = tmp_path / "evidence.json"
        result = subprocess.run(
            [
                sys.executable,
                "scripts/run_gate_a_staged_canary.py",
                "--authorization-file",
                str(authorization_path),
                "--fixture-id",
                FIXTURE_ID,
                "--season",
                "2026",
                "--persistence",
                "db",
                "--now-utc",
                now.isoformat(),
                "--evidence-output",
                str(evidence_path),
                "--offline-fake-provider-base-url",
                f"http://127.0.0.1:{server.server_port}",
                "--offline-trust-store",
                str(trust_path),
            ],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        assert {key: value["delta"] for key, value in evidence["artifact_counts"].items()} == {
            "provider_calls": 5,
            "raw_payload": 4,
            "endpoint_capture": 5,
            "lineup_event": 1,
            "dynamic_evaluation_v2": 2,
            "five_state_snapshot": 2,
            "exact_pair": 1,
            "bootstrap_seed_evidence": 1,
        }
        assert [path.split("?", 1)[0] for path in _FakeProviderHandler.requests] == [
            "/status",
            "/fixtures",
            "/odds",
            "/fixtures/lineups",
            "/odds",
        ]
    finally:
        server.shutdown()
        thread.join(timeout=5)
        with create_engine(admin_url, isolation_level="AUTOCOMMIT").connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)'))


class _SequenceClient:
    def __init__(self, now: datetime, scenario: str = "success") -> None:
        self.now = now
        self.scenario = scenario
        self.calls: list[str] = []
        self.odds_calls = 0

    def request_live(self, endpoint: str, params: dict[str, str]) -> LiveApiFootballResponse:
        self.calls.append(endpoint)
        if self.scenario == "pre_failure" and endpoint == "odds":
            raise TimeoutError("injected")
        payload = self._payload(endpoint, params)
        return LiveApiFootballResponse(
            endpoint=endpoint,
            params=params,
            status_code=200,
            elapsed_ms=1,
            payload=payload,
            headers={"x-ratelimit-requests-remaining": "7000"},
            captured_at=self.now + timedelta(seconds=len(self.calls)),
        )

    def _payload(self, endpoint: str, params: dict[str, str]) -> dict[str, Any]:
        if endpoint == "status":
            return {"response": {"requests": {"remaining": 7000}}}
        if endpoint == "fixtures":
            return {
                "response": [
                    {
                        "fixture": {
                            "id": int(FIXTURE_ID),
                            "date": (self.now + timedelta(hours=7)).isoformat(),
                            "status": {"short": "NS"},
                        },
                        "league": {"id": 1, "season": 2026},
                        "teams": {"home": {"id": 10}, "away": {"id": 20}},
                    }
                ]
            }
        if endpoint == "lineups":
            return (
                {"response": []}
                if self.scenario == "empty_lineups"
                else {"response": [_lineup(10, 100), _lineup(20, 200)]}
            )
        if endpoint == "odds":
            self.odds_calls += 1
            if self.scenario == "missing_post" and self.odds_calls == 2:
                return {"response": []}
            line = "-0.75" if self.scenario == "line_changed" and self.odds_calls == 2 else "-0.5"
            away_line = "+0.75" if line == "-0.75" else "+0.5"
            return {
                "response": [
                    {
                        "fixture": {"id": int(params["fixture"])},
                        "bookmakers": [
                            {
                                "id": 1,
                                "name": "Fake Book",
                                "bets": [
                                    {
                                        "id": 4,
                                        "name": "Asian Handicap",
                                        "values": [
                                            {"value": f"Home {line}", "odd": "1.91"},
                                            {"value": f"Away {away_line}", "odd": "1.93"},
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ]
            }
        raise AssertionError(endpoint)


def _run_sqlite_staged(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    scenario: str,
) -> tuple[Any, _SequenceClient, int]:
    now = datetime.now(UTC)
    database_url = f"sqlite+pysqlite:///{tmp_path / f'{scenario}.db'}"
    monkeypatch.setenv("W2_DATABASE_URL", database_url)
    monkeypatch.setenv("W2_ENVIRONMENT", "test")
    monkeypatch.setenv("W2_PROVIDER_CALLS_DISABLED", "false")
    monkeypatch.setenv("W2_PROVIDER_ENDPOINT_ALLOWLIST", "status,fixtures,odds,lineups")
    monkeypatch.setenv("W2_PROVIDER_HTTP_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("W2_GIT_SHA", "a" * 40)
    get_settings.cache_clear()
    engine = w2_create_engine()
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        seed_competition_runtime_authority(
            connection,
            config_root=ROOT / "config",
            environment="test",
            updated_by="staged-negative-test",
        )
    authorization = GateARuntimeAuthorization.from_mapping(
        authorization_payload(
            authorization_id=f"staged-{scenario}",
            task_key=f"staged:{scenario}",
            fixture_id=FIXTURE_ID,
        ),
        trusted_public_keys=TRUSTED_KEYS,
    )
    reservation = reserve_gate_a_run(authorization, owner="test", now=now - timedelta(seconds=1))
    client = _SequenceClient(now, scenario)
    audit = run_staged_gate_a_canary_task(
        task_id=f"task-{scenario}",
        key=authorization.task_key,
        queued_at=now,
        competition_id="world_cup_2026",
        season="2026",
        fixture_id=FIXTURE_ID,
        runtime_authorization=authorization,
        provider_call_reservation=reservation,
        now=now,
        client=client,
    )
    pair_count = len(project_exact_eval_02b_pairs(engine).pairs)
    get_settings.cache_clear()
    return audit, client, pair_count


@pytest.mark.parametrize(
    ("scenario", "expected_calls"),
    [("missing_post", 5), ("empty_lineups", 4), ("pre_failure", 3)],
)
def test_failed_stage_stops_without_retry_or_pair(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    scenario: str,
    expected_calls: int,
) -> None:
    audit, client, pair_count = _run_sqlite_staged(monkeypatch, tmp_path, scenario)
    assert audit.status == "BLOCKED"
    assert len(client.calls) == expected_calls
    assert pair_count == 0


def test_changed_exact_line_cannot_form_pair(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    audit, client, pair_count = _run_sqlite_staged(monkeypatch, tmp_path, "line_changed")
    assert audit.status == "COMPLETED"
    assert client.calls == ["status", "fixtures", "odds", "lineups", "odds"]
    assert pair_count == 0
