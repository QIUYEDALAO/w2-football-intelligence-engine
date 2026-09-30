"""Real Linux containers/PG rehearsal; synthetic upstream, no production access.

The recovery function is extracted verbatim from w2-release. Only the project
name and /opt/w2 paths are replaced to isolate this rehearsal. Docker/SSH are
never mocked. Each case owns its containers, volumes and PostgreSQL database.
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
BASE = "27698c9a53d2b2283ef1b5ac4b5ba61e65bad62e"


def run(args: list[str], *, cwd: Path = ROOT, check: bool = True) -> str:
    value = subprocess.run(args, cwd=cwd, check=False, capture_output=True, text=True)
    print(
        json.dumps(
            {
                "command": args,
                "cwd": str(cwd),
                "exit": value.returncode,
                "stdout": value.stdout,
                "stderr": value.stderr,
            }
        ),
        flush=True,
    )
    if check and value.returncode != 0:
        raise subprocess.CalledProcessError(value.returncode, args, value.stdout, value.stderr)
    return value.stdout.strip()


def wait_ready(url: str) -> dict:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            response = httpx.get(url, timeout=2, trust_env=False)
            if response.status_code == 200:
                return response.json()
        except (httpx.HTTPError, TimeoutError):
            pass
        time.sleep(1)
    raise AssertionError(f"READINESS_FAILED:{url}")


def context_copy(output: Path) -> None:
    files = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    files += (
        subprocess.check_output(
            ["git", "ls-files", "--others", "--exclude-standard", "-z"], cwd=ROOT
        )
        .decode()
        .split("\0")
    )
    (output / "SOURCE_FILES.json").write_text(json.dumps(sorted(set(files)), indent=2))
    for name in files:
        if not name or not (source := ROOT / name).is_file():
            continue
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    (output / ".dockerignore").write_text(".git\n.venv\n**/node_modules\n**/__pycache__\n")


def seed_positive(url: str, output: Path) -> dict:
    import sys

    import pytest

    sys.path.insert(0, str(ROOT))
    from tests import conftest
    from tests.integration.test_ah_ou_v9_system_pg import _build_chain

    from w2.prematch.analysis_calculator import ReadModelService

    conftest.pytest_configure()
    patch = pytest.MonkeyPatch()
    patch.setenv("W2_TEST_POSTGRES_URL", url)
    patch.setenv("W2_GIT_SHA", run(["git", "rev-parse", "HEAD"]))
    producer = _build_chain(output, patch, existing_database_url=url, environment="staging")
    repo, future, _, _ = next(producer)
    card = ReadModelService().public_analysis_card_bounded("1489404", use_frozen_canary=False)
    assert card["ah_ou_result"]["recording"]["status"] == "COMMITTED", card
    assert card["ah_ou_result"]["ah"]["selected"], card["ah_ou_result"]
    assert card["ah_ou_result"]["ou"]["selected"], card["ah_ou_result"]
    (output / "prematch-card.json").write_text(json.dumps(card, default=str, indent=2))
    from tests.integration.test_ah_ou_v11_postmatch_pg import _ft_capture

    _ft_capture(repo, future)
    producer.close()
    patch.undo()
    return future


def seed_partial_ft(url: str) -> dict:
    """Actual discovery/raw/capture producers on the unchanged 0076 schema."""
    import os
    from datetime import timedelta
    from types import SimpleNamespace

    from sqlalchemy import create_engine
    from tests.integration.test_ah_ou_v11_postmatch_pg import _ft_capture

    from w2.config import get_settings
    from w2.domain.canonical_serialization import HashDomain
    from w2.ingestion.future_refresh import sha256_payload
    from w2.matchday.intake_v2 import MatchdayCompetitionPolicy, fixture_discovery_from_payloads
    from w2.matchday.repository import MatchdayRuntimeRepository

    os.environ["W2_DATABASE_URL"] = url
    get_settings.cache_clear()
    engine = create_engine(url)
    at = datetime.now(UTC) - timedelta(hours=6)
    future = {
        "fixture": {
            "id": 1489404,
            "date": (at + timedelta(hours=3)).isoformat(),
            "status": {"short": "NS"},
        },
        "league": {"id": 113, "season": 2026},
        "teams": {"home": {"id": 10, "name": "H"}, "away": {"id": 20, "name": "A"}},
    }
    raw = {"response": [future]}
    sha = sha256_payload(raw, domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD)
    writer = MatchdayRuntimeRepository(engine=engine)
    writer.save_raw_payload(sha256=sha, endpoint="fixtures", captured_at=at, payload=raw)
    policy = MatchdayCompetitionPolicy(
        competition_id="allsvenskan",
        enabled=True,
        provider="api_football",
        provider_league_id="113",
        season="2026",
        discovery_horizon_hours=168,
        fixture_status_allowlist=("NS",),
        checkpoints=(),
        endpoint_matrix={},
        odds_max_age_seconds=1800,
        lineup_requirement="OPTIONAL",
        request_caps={},
        provider_allowlist=("fixtures",),
        feature_enrichment_policy={},
    )
    discovered = fixture_discovery_from_payloads(
        [future], policies={"allsvenskan": policy}, captured_at=at, source_payload_sha256=sha
    )["candidate_fixtures"]
    for row in discovered:
        row.update(fixture_status="NS", raw_payload_sha256=sha, payload=future)
    assert writer.insert_fixture_identities(discovered) == 1
    _ft_capture(SimpleNamespace(engine=engine), future)
    engine.dispose()
    return future


def case(root: Path, *, fault: str, candidate: str, old: str, web: str) -> dict:
    import yaml

    project = "w2-self-" + uuid.uuid4().hex[:10]
    path = root / fault
    path.mkdir()
    (path / "deploy").mkdir()
    (path / "shared").mkdir()
    template = yaml.safe_load((ROOT / "infra/compose/compose.staging.yml").read_text())
    template["name"] = project
    for service in template["services"].values():
        if service.get("restart") is False:
            service["restart"] = "no"
    template["services"]["api"]["ports"] = ["127.0.0.1::8000"]
    template["services"]["web"]["ports"] = ["127.0.0.1::8080"]
    template["services"]["postgres"]["ports"] = ["127.0.0.1::5432"]
    template["services"]["redis"]["ports"] = ["127.0.0.1::6379"]
    template["volumes"]["runtime-data"] = {}
    template["volumes"]["market-data"] = {}
    for name in ("api", "worker", "worker-heavy", "scheduler"):
        service = template["services"][name]
        service["volumes"] = [
            "runtime-data:/app/runtime",
            "market-data:/app/market_timeline_snapshots",
        ]
        service["environment"]["W2_PROVIDER_CALLS_DISABLED"] = "true"
        service["environment"]["W2_PROVIDER_SCHEDULER_ENABLED"] = "false"
        service["environment"]["W2_FORWARD_OUTCOME_LEDGER_ENABLED"] = "false"
    compose_file = path / "deploy/compose.staging.yml"
    compose_file.write_text(yaml.safe_dump(template, sort_keys=False))
    (path / "shared/.env").write_text(
        "POSTGRES_PASSWORD=placeholder_password\nW2_API_FOOTBALL_API_KEY=test-key\n"
    )
    release = path / "shared/release.env"
    candidate_env = path / "shared/candidate.env"
    release.write_text(f"W2_PYTHON_IMAGE={old}\nW2_WEB_IMAGE={web}\nW2_GIT_SHA={BASE}\n")
    source_sha = run(["git", "rev-parse", "HEAD"])
    candidate_env.write_text(
        f"W2_PYTHON_IMAGE={candidate}\nW2_WEB_IMAGE={web}\n"
        f"W2_GIT_SHA={source_sha}\nW2_RELEASE_ID={source_sha}\n"
    )
    compose = [
        "docker",
        "compose",
        "-p",
        project,
        "-f",
        str(compose_file),
        "--env-file",
        str(path / "shared/.env"),
        "--env-file",
        str(release),
    ]
    network = project + "_w2-staging"
    containers = [
        f"{project}-{name}-1"
        for name in ("postgres", "redis", "api", "worker", "worker-heavy", "scheduler", "web")
    ]
    try:
        run([*compose, "up", "-d", "postgres", "redis"])
        for _ in range(30):
            if run(
                ["docker", "exec", containers[0], "pg_isready", "-U", "w2_user"], check=False
            ).startswith("/var/run/postgresql:5432 - accepting"):
                break
            time.sleep(1)
        run(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                network,
                "-e",
                "W2_DATABASE_URL=postgresql+psycopg://w2_user:placeholder_password@postgres:5432/w2",
                "--entrypoint",
                "alembic",
                candidate,
                "upgrade",
                "0076_forward_review_evidence",
            ]
        )
        for volume in ("runtime-data", "market-data"):
            run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--user",
                    "root",
                    "-v",
                    f"{project}_{volume}:/mnt",
                    "--entrypoint",
                    "sh",
                    candidate,
                    "-c",
                    "chown 10001:10001 /mnt; chmod 750 /mnt",
                ]
            )
        run([*compose, "up", "-d", "api", "worker", "worker-heavy", "scheduler", "web"])
        pre_revision = run(
            [
                "docker",
                "exec",
                containers[0],
                "psql",
                "-XAt",
                "-U",
                "w2_user",
                "-d",
                "w2",
                "-c",
                "SELECT version_num FROM alembic_version",
            ]
        )
        assert pre_revision == "0076_forward_review_evidence"
        old_port = run([*compose, "port", "api", "8000"]).rsplit(":", 1)[1]
        old_ready = wait_ready(f"http://127.0.0.1:{old_port}/ready")
        assert old_ready["status"] == "READY", old_ready
        off_at = datetime.now(UTC).isoformat()
        run([*compose, "stop", "-t", "15", "scheduler", "worker", "worker-heavy", "api", "web"])
        legacy_digest = None
        ledger_query = [
            "docker",
            "exec",
            containers[0],
            "psql",
            "-XAt",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            "w2_user",
            "-d",
            "w2",
            "-c",
        ]
        if fault == "normal":
            # Production had this verified ORM table at revision 0076. Replay
            # that actual schema anomaly without stamping, deleting, or making
            # the legacy record eligible as a v3 decision.
            run(
                [
                    *ledger_query,
                    (ROOT / "tests/fixtures/ah_ou_0076_existing_ledger.sql").read_text(),
                ]
            )
            run(
                [
                    *ledger_query,
                    """
                INSERT INTO ah_ou_decision_ledger VALUES
                ('preexisting-ledger','legacy-fixture','ASIAN_HANDICAP','2026-09-28T18:00Z',
                 'm1','c1',repeat('a',64),'{}',repeat('a',64),repeat('a',64),
                 repeat('a',64),'old-source','H','A',true,'HOME','0.1',NULL,
                 '2026-09-28T18:00Z');
            """,
                ]
            )
            legacy_digest = run(
                [*ledger_query, "SELECT md5(to_jsonb(t)::text) FROM ah_ou_decision_ledger t"]
            )
            # Exact read-only observed production source shapes. This fault
            # construction runs only in this isolated replica. Unproven rows
            # must survive in archives without acquiring capture/FT proof.
            run(
                [
                    *ledger_query,
                    "DROP TABLE matchday_endpoint_captures CASCADE; "
                    "DROP TABLE results CASCADE; "
                    "CREATE TABLE matchday_endpoint_captures (capture_id varchar(64) "
                    "PRIMARY KEY, raw_payload_sha256 varchar(64) NOT NULL); "
                    "INSERT INTO matchday_endpoint_captures VALUES ('cap-1',repeat('a',64)); "
                    "CREATE TABLE results (fixture_id varchar(128) PRIMARY KEY, "
                    "home_goals integer, away_goals integer); "
                    "INSERT INTO results VALUES ('f1',2,1);",
                ]
            )
        head = run(
            ["docker", "run", "--rm", "--entrypoint", "alembic", candidate, "heads"]
        ).split()[0]
        if fault != "migration_failure":
            run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--network",
                    network,
                    "-e",
                    "W2_DATABASE_URL=postgresql+psycopg://w2_user:placeholder_password@postgres:5432/w2",
                    "--entrypoint",
                    "alembic",
                    candidate,
                    "upgrade",
                    "head",
                ]
            )
            if legacy_digest is not None:
                assert run(
                    [*ledger_query, "SELECT capture_id,raw_payload_sha256 FROM "
                     "w2_legacy_unproven_matchday_endpoint_captures_0076"]
                ) == "cap-1|" + "a" * 64
                assert run(
                    [*ledger_query, "SELECT fixture_id,home_goals,away_goals FROM "
                     "w2_legacy_unproven_results_0076"]
                ) == "f1|2|1"
                assert run(
                    [*ledger_query, "SELECT (SELECT count(*) FROM results), "
                     "(SELECT count(*) FROM matchday_endpoint_captures)"]
                ) == "0|0"
                after_digest = run(
                    [
                        *ledger_query,
                        """
                    SELECT md5((to_jsonb(t)-ARRAY[
                        'decision_contract','frozen_terms','terms_hash'])::text)
                    FROM ah_ou_decision_ledger t WHERE decision_id='preexisting-ledger'
                      AND decision_contract IS NULL AND frozen_terms IS NULL AND terms_hash IS NULL
                """,
                    ]
                )
                assert after_digest == legacy_digest
                (path / "preexisting-ledger-preservation.json").write_text(
                    json.dumps(
                        {
                            "schema_before": pre_revision,
                            "business_digest_before": legacy_digest,
                            "business_digest_after": after_digest,
                            "v3_upgrade": False,
                        },
                        indent=2,
                    )
                )
            pg_port = run([*compose, "port", "postgres", "5432"]).rsplit(":", 1)[1]
            future = seed_positive(
                f"postgresql+psycopg://w2_user:placeholder_password@127.0.0.1:{pg_port}/w2", path
            )
        else:
            pg_port = run([*compose, "port", "postgres", "5432"]).rsplit(":", 1)[1]
            future = seed_partial_ft(
                f"postgresql+psycopg://w2_user:placeholder_password@127.0.0.1:{pg_port}/w2"
            )
        if fault in {"normal", "readback_failure", "startup_failure"}:
            shutil.copy2(candidate_env, release)
            run(
                [
                    *compose,
                    "up",
                    "-d",
                    "--no-deps",
                    "--force-recreate",
                    "worker",
                    "worker-heavy",
                    "scheduler",
                    "api",
                    "web",
                ]
            )
        if fault != "migration_failure":
            run(
                [
                    "docker",
                    "exec",
                    containers[0],
                    "psql",
                    "-XAt",
                    "-U",
                    "w2_user",
                    "-d",
                    "w2",
                    "-c",
                    "SET ROLE quant_asof_reader_role; "
                    "SELECT count(*) FROM ah_ou_history_capture_sources",
                ]
            )
            denied = subprocess.run(
                [
                    "docker",
                    "exec",
                    containers[0],
                    "psql",
                    "-XAt",
                    "-U",
                    "w2_user",
                    "-d",
                    "w2",
                    "-c",
                    "SET ROLE quant_asof_reader_role; SELECT count(*) FROM results",
                ],
                capture_output=True,
                text=True,
            )
            print(
                json.dumps(
                    {
                        "set_role_result_denied_exit": denied.returncode,
                        "stdout": denied.stdout,
                        "stderr": denied.stderr,
                    }
                ),
                flush=True,
            )
            assert denied.returncode != 0 and "permission denied" in denied.stderr
        if fault == "normal":
            port = run([*compose, "port", "api", "8000"]).rsplit(":", 1)[1]
            ready = wait_ready(f"http://127.0.0.1:{port}/ready")
            assert ready["status"] == "READY", ready
        if fault == "migration_failure":
            # A genuine PG permission failure in the actual Alembic upgrade.
            run(
                [
                    "docker",
                    "exec",
                    containers[0],
                    "psql",
                    "-XAt",
                    "-U",
                    "w2_user",
                    "-d",
                    "w2",
                    "-c",
                    "CREATE ROLE migration_failure LOGIN PASSWORD 'placeholder_password'; "
                    "GRANT SELECT ON ALL TABLES IN SCHEMA public TO migration_failure;",
                ]
            )
            attempt = subprocess.run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--network",
                    network,
                    "-e",
                    "W2_DATABASE_URL=postgresql+psycopg://migration_failure:placeholder_password@postgres:5432/w2",
                    "--entrypoint",
                    "alembic",
                    candidate,
                    "upgrade",
                    "head",
                ],
                capture_output=True,
                text=True,
            )
            print(
                json.dumps(
                    {
                        "migration_failure_exit": attempt.returncode,
                        "stdout": attempt.stdout,
                        "stderr": attempt.stderr,
                    }
                ),
                flush=True,
            )
            assert attempt.returncode != 0 and "permission denied" in attempt.stderr.lower()
        if fault == "startup_failure":
            failure_override = path / "deploy/startup-failure.yml"
            failure_override.write_text(
                yaml.safe_dump(
                    {"services": {"worker": {"command": template["services"]["worker"]["command"]}}}
                )
            )
            run(
                [
                    *compose,
                    "-f",
                    str(failure_override),
                    "up",
                    "-d",
                    "--no-deps",
                    "--force-recreate",
                    "worker",
                ]
            )
            assert (
                run(["docker", "inspect", f"{project}-worker-1", "--format", "{{.State.Running}}"])
                == "true"
            )
            failure_override.write_text(
                yaml.safe_dump(
                    {
                        "services": {
                            "worker": {
                                "restart": "no",
                                "command": [
                                    "python",
                                    "-c",
                                    "raise RuntimeError('SYNTHETIC_STARTUP_FAILURE')",
                                ],
                            }
                        }
                    }
                )
            )
            run(
                [
                    *compose,
                    "-f",
                    str(failure_override),
                    "up",
                    "-d",
                    "--no-deps",
                    "--force-recreate",
                    "worker",
                ]
            )
            time.sleep(2)
            assert (
                run(["docker", "inspect", f"{project}-worker-1", "--format", "{{.State.ExitCode}}"])
                != "0"
            )
        if fault == "readback_failure":
            port = run([*compose, "port", "api", "8000"]).rsplit(":", 1)[1]
            port = run([*compose, "port", "api", "8000"]).rsplit(":", 1)[1]
            wait_ready(f"http://127.0.0.1:{port}/ready")
            version = httpx.get(f"http://127.0.0.1:{port}/v1/version", trust_env=False).json()
            assert version["release_id"] == source_sha, version
            failure_override = path / "deploy/readback-failure.yml"
            failure_override.write_text(
                yaml.safe_dump(
                    {"services": {"api": {"environment": {"W2_RELEASE_ID": source_sha}}}}
                )
            )
            run(
                [
                    *compose,
                    "-f",
                    str(failure_override),
                    "up",
                    "-d",
                    "--no-deps",
                    "--force-recreate",
                    "api",
                ]
            )
            port = run([*compose, "port", "api", "8000"]).rsplit(":", 1)[1]
            wait_ready(f"http://127.0.0.1:{port}/ready")
            assert (
                httpx.get(f"http://127.0.0.1:{port}/v1/version", trust_env=False).json()[
                    "release_id"
                ]
                == source_sha
            )
            failure_override.write_text(
                yaml.safe_dump(
                    {
                        "services": {
                            "api": {
                                "environment": {"W2_RELEASE_ID": "SYNTHETIC_WRONG_RELEASE"},
                            }
                        }
                    }
                )
            )
            run(
                [
                    *compose,
                    "-f",
                    str(failure_override),
                    "up",
                    "-d",
                    "--no-deps",
                    "--force-recreate",
                    "api",
                ]
            )
            port = run([*compose, "port", "api", "8000"]).rsplit(":", 1)[1]
            wait_ready(f"http://127.0.0.1:{port}/ready")
            version = httpx.get(f"http://127.0.0.1:{port}/v1/version", trust_env=False).json()
            assert version["release_id"] != source_sha, version
            print(json.dumps({"readback_rejected": version}), flush=True)
        if fault != "normal":
            source = (ROOT / "ops/host/w2-release").read_text()
            function = source[source.index("rollback() {") : source.index("\ntrap rollback EXIT")]
            function = function.replace("w2-staging", project).replace("/opt/w2", str(path))
            script = path / "rollback.sh"
            import shlex

            script.write_text(
                "set -euo pipefail\n"
                + "compose=("
                + " ".join(map(shlex.quote, compose))
                + ")\n"
                + f'Q() {{ docker exec {containers[0]} psql -XAt -U w2_user -d w2 -c "$1"; }}\n'
                + "ROLLBACK_NEEDED=1\nOLD_STOPPED=1\nOVERRIDE_SYNCED=0\noverride_backup=''\n"
                + f"pre_schema={pre_revision}\ntarget_head={head}\n"
                + f"py_ref={shlex.quote(candidate)}\nrelease_sha=REHEARSAL\n"
                + f"candidate={shlex.quote(str(candidate_env))}\n"
                + function
                + "\nrollback\n"
            )
            if platform.system() == "Linux":
                result = run(["bash", str(script)])
            else:
                result = run(
                    [
                        "docker",
                        "run",
                        "--rm",
                        "-v",
                        "/var/run/docker.sock:/var/run/docker.sock",
                        "-v",
                        f"{root}:{root}",
                        "docker:27-cli",
                        "sh",
                        "-c",
                        f"apk add --no-cache bash >/dev/null && bash {shlex.quote(str(script))}",
                    ]
                )
            assert "SAFE_PAUSE_COLLECTION_RESTORED" in result, result
            identity = json.loads(run([
                "python3", str(ROOT / "scripts/w2_safe_pause_identity.py"), "--project", project
            ]))
            assert identity["release_id"] == source_sha, identity
            assert identity["public_services_stopped"], identity
            (path / "safe-pause-resume-identity.json").write_text(json.dumps(identity, indent=2))
            for name in ("api", "web"):
                assert (
                    run(
                        [
                            "docker",
                            "inspect",
                            f"{project}-{name}-1",
                            "--format",
                            "{{.State.Running}}",
                        ]
                    )
                    == "false"
                )
        for name in ("worker", "worker-heavy", "scheduler"):
            assert (
                run(
                    [
                        "docker",
                        "inspect",
                        f"{project}-{name}-1",
                        "--format",
                        "{{.Config.Image}} {{.State.Running}}",
                    ]
                )
                == f"{candidate} true"
            )
        if future is not None:
            run(
                [
                    "docker",
                    "exec",
                    f"{project}-worker-1",
                    "python",
                    "-c",
                    """
from apps.worker.celery_app import celery_app
r=celery_app.send_task('w2.result_materialize', kwargs={'fixture_ids':['api_football:1489404']})
v=r.get(timeout=60); print(v)
assert v['status'] in {'PASS','BLOCKED'}, v
if v['status']=='BLOCKED':
 assert v['result']['validation_samples']['v3']['reason']=='V3_POSTMATCH_SCHEMA_UNAVAILABLE', v
""",
                ]
            )
            db_sql = (
                "SELECT count(*), sum(net_units::numeric) FROM ah_ou_v3_settlement"
                if fault != "migration_failure"
                else "SELECT count(*), min(home_goals), min(away_goals) FROM results"
            )
            db = run(
                [
                    "docker",
                    "exec",
                    containers[0],
                    "psql",
                    "-XAt",
                    "-U",
                    "w2_user",
                    "-d",
                    "w2",
                    "-c",
                    db_sql,
                ]
            )
            assert db == ("2|1.15" if fault != "migration_failure" else "1|2|1"), db
            if fault != "migration_failure":
                run(
                    [
                        "docker",
                        "exec",
                        f"{project}-worker-heavy-1",
                        "python",
                        "-c",
                        """
import uuid
from datetime import UTC,datetime
from apps.worker.celery_app import celery_app
from w2.tracking.outcome_ledger_runtime import OutcomeLedgerRuntimeRepository
tid=str(uuid.uuid4())
d=OutcomeLedgerRuntimeRepository().prepare_dispatch(now=datetime.now(UTC),task_id=tid)
assert d.status=='QUEUED', d
r=celery_app.send_task('w2.forward_outcome_ledger', kwargs={'window':'next7'}, task_id=tid)
v=r.get(timeout=60);print(v);assert v['status']!='BLOCKED',v
assert v['result']['validation_samples']['v3']['idempotent']==2,v
""",
                    ]
                )
            if fault == "normal":
                from w2.dashboard.date_window import football_day_for_kickoff

                day = football_day_for_kickoff(datetime.fromisoformat(future["fixture"]["date"]))
                home = httpx.get(
                    f"http://127.0.0.1:{port}/v1/dashboard/intelligence-workspace/list",
                    params={"date": day.isoformat()},
                    trust_env=False,
                )
                assert home.status_code == 200, home.text
                assert len(home.json()["today_recommendations"]) == 2, home.text
                assert home.json()["performance_summary"]["total_profit_units"] == 1.15, home.text
                (path / "postmatch-home.json").write_text(home.text)
                validation = httpx.get(
                    f"http://127.0.0.1:{port}/v1/dashboard/intelligence-workspace/validation",
                    trust_env=False,
                )
                assert validation.status_code == 200, validation.text
                current = validation.json()["ah_ou_v3"]
                assert current["selected"] == 2, current
                assert len(current["rows"]) == 2, current
                assert all(row["fixture_id"] == "1489404" for row in current["rows"]), current
                (path / "postmatch-validation.json").write_text(validation.text)
                import hashlib
                import runpy

                tool = runpy.run_path(str(ROOT / "scripts/w2_runtime_source_recovery.py"))
                capture = tool["capture"]
                # Only this owned replica's attack channel uses root. The service
                # keeps its normal unprivileged user throughout the rehearsal.
                source_write = ["docker", "exec", "--user", "0", f"{project}-api-1", "python", "-c"]
                unchanged_source = (
                    "from pathlib import Path;"
                    "Path('/app/source_drift_probe.py').write_text('# isolated control\\n')"
                )
                run([*source_write, unchanged_source])
                proof = capture(source_sha, path / "source-proof-noop", project)
                record = json.loads(proof.read_text())
                entry = record["services"]["api"]
                keys = ("image", "image_head", "container_head", "image_hash", "container_hash")
                command = [
                    "docker",
                    "run",
                    "--rm",
                    "--user",
                    "0",
                    "-v",
                    f"{proof.parent}:/evidence:ro",
                    "--entrypoint",
                    "python",
                    candidate,
                    "/app/scripts/w2_runtime_source_recovery.py",
                    "verify",
                    "--manifest",
                    "/evidence/" + proof.name,
                    "--sha256",
                    hashlib.sha256(proof.read_bytes()).hexdigest(),
                    "--target",
                    source_sha,
                    "--service",
                    "api",
                    "--database-revision",
                    head,
                ]
                run([*command, *[entry[k] for k in keys]])
                run([*source_write, unchanged_source])
                noop_hash = run(
                    ["docker", "exec", f"{project}-api-1", "python", "-c", tool["FINGERPRINT"]]
                )
                assert noop_hash == entry["container_hash"]
                run([*command, *[entry[k] for k in keys[:-1]], noop_hash])
                run(
                    [
                        *source_write,
                        "from pathlib import Path;"
                        "Path('/app/source_drift_probe.py').write_text('# isolated drift\\n')",
                    ]
                )
                changed_hash = run(
                    ["docker", "exec", f"{project}-api-1", "python", "-c", tool["FINGERPRINT"]]
                )
                attacked = subprocess.run(
                    [*command, *[entry[k] for k in keys[:-1]], changed_hash],
                    capture_output=True,
                    text=True,
                )
                print(
                    json.dumps(
                        {
                            "source_drift_attack_exit": attacked.returncode,
                            "stdout": attacked.stdout,
                            "stderr": attacked.stderr,
                        }
                    ),
                    flush=True,
                )
                assert (
                    attacked.returncode != 0
                    and "RECOVERY_CURRENT_SOURCE_CONFLICT" in attacked.stderr
                )
                changed = capture(source_sha, path / "source-proof-drift", project)
                entry = json.loads(changed.read_text())["services"]["api"]
                command[command.index(str(proof.parent) + ":/evidence:ro")] = (
                    str(changed.parent) + ":/evidence:ro"
                )
                command[command.index(hashlib.sha256(proof.read_bytes()).hexdigest())] = (
                    hashlib.sha256(changed.read_bytes()).hexdigest()
                )
                run([*command, *[entry[k] for k in keys]])

        return {
            "case": fault,
            "old_off_at": off_at,
            "schema_before": pre_revision,
            "target_head": head,
            "collector_candidate": candidate,
            "ft_settlement": "2|1.15"
            if fault != "migration_failure"
            else "FT_PERSISTED_V3_SCHEMA_BLOCKED",
            "production_modified": False,
            "real_provider_calls": 0,
        }
    finally:
        run([*compose, "logs", "--no-color"], check=False)
        run([*compose, "down", "--volumes"], check=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--candidate-image")
    parser.add_argument("--old-image")
    parser.add_argument("--web-image")
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    sha = run(["git", "rev-parse", "HEAD"])
    candidate = args.candidate_image or f"w2-self-candidate:{sha}"
    old = args.old_image or f"w2-self-old:{BASE}"
    web = args.web_image or f"w2-self-web:{sha}"
    if not args.candidate_image:
        context = root / "candidate-source"
        context.mkdir()
        context_copy(context)
        run(
            [
                "docker",
                "build",
                "-f",
                "Dockerfile.python",
                "--build-arg",
                f"W2_GIT_SHA={sha}",
                "-t",
                candidate,
                str(context),
            ],
            cwd=context,
        )
        run(
            [
                "docker",
                "build",
                "-f",
                "Dockerfile.web",
                "--build-arg",
                f"VITE_GIT_SHA={sha}",
                "-t",
                web,
                str(context),
            ],
            cwd=context,
        )
    if not args.old_image:
        archive = root / "old.tar"
        run(["git", "archive", "--output", str(archive), BASE])
        context = root / "historical-source"
        context.mkdir()
        run(["tar", "-xf", str(archive), "-C", str(context)])
        run(
            [
                "docker",
                "build",
                "-f",
                "Dockerfile.python",
                "--build-arg",
                f"W2_GIT_SHA={BASE}",
                "-t",
                old,
                str(context),
            ],
            cwd=context,
        )
    outcomes = [
        case(root, fault=fault, candidate=candidate, old=old, web=web)
        for fault in ("normal", "migration_failure", "startup_failure", "readback_failure")
    ]
    (root / "RESULTS.json").write_text(json.dumps({"source_sha": sha, "cases": outcomes}, indent=2))
    print(json.dumps({"status": "PASS", "source_sha": sha, "cases": outcomes}))


if __name__ == "__main__":
    main()
