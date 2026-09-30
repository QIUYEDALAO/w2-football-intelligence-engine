"""Read-only identity for resuming a release from its verified safe pause.

An unreachable API alone is never permission to switch. Both public services
must be stopped and all three live collectors must be the same immutable,
unmodified, explicitly paused release with a supported database revision.
"""

import argparse
import json
import re
import subprocess
from datetime import UTC, datetime


def run(command):
    result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode:
        if "SAFE_PAUSE_SCHEMA_UNSUPPORTED" in result.stderr:
            raise RuntimeError("SAFE_PAUSE_SCHEMA_UNSUPPORTED")
        raise RuntimeError("SAFE_PAUSE_IDENTITY_COMMAND_FAILED:" + command[1])
    return result.stdout.strip()


SOURCE = """import hashlib,pathlib
base=pathlib.Path("/app")
h=hashlib.sha256()
for p in sorted(p for p in base.rglob("*.py") if "__pycache__" not in p.parts and p.is_file()):
 h.update(p.relative_to(base).as_posix().encode());h.update(b"\\0");h.update(p.read_bytes());h.update(b"\\0")
print(h.hexdigest())"""


def inspect(name):
    return json.loads(run(["docker", "inspect", name]))[0]


def read_identity(project="w2-staging"):
    if not re.fullmatch(r"[a-z0-9-]+", project):
        raise RuntimeError("SAFE_PAUSE_PROJECT_INVALID")
    for name in ("api", "web"):
        if inspect(project + "-" + name + "-1")["State"]["Running"]:
            raise RuntimeError("SAFE_PAUSE_PUBLIC_SERVICE_RUNNING:" + name)
    proof = {}
    identities = set()
    for name in ("worker", "worker-heavy", "scheduler"):
        container = project + "-" + name + "-1"
        actual = inspect(container)
        env = dict(value.split("=", 1) for value in actual["Config"]["Env"])
        if not actual["State"]["Running"] or env.get("W2_CURRENT_RECOMMENDATIONS_PAUSED") != "true":
            raise RuntimeError("SAFE_PAUSE_COLLECTOR_NOT_PAUSED:" + name)
        image = inspect(actual["Image"])
        sha = image["Config"]["Labels"].get("org.opencontainers.image.revision", "")
        if (
            not re.fullmatch(r"[0-9a-f]{40}", sha)
            or env.get("W2_GIT_SHA") != sha
            or env.get("W2_RELEASE_ID") != sha
        ):
            raise RuntimeError("SAFE_PAUSE_RELEASE_IDENTITY_CONFLICT:" + name)
        frozen = run(
            ["docker", "run", "--rm", "--entrypoint", "python", actual["Image"], "-c", SOURCE]
        )
        live = run(["docker", "exec", container, "python", "-c", SOURCE])
        if frozen != live or not re.fullmatch(r"[0-9a-f]{64}", live):
            raise RuntimeError("SAFE_PAUSE_SOURCE_DRIFT:" + name)
        identities.add((sha, actual["Image"]))
        proof[name] = {
            "sha": sha,
            "image_id": actual["Image"],
            "source_sha256": live,
            "paused": True,
        }
    if len(identities) != 1:
        raise RuntimeError("SAFE_PAUSE_COLLECTOR_SET_CONFLICT")
    sha, image_id = next(iter(identities))
    revision = run(
        [
            "docker",
            "exec",
            project + "-postgres-1",
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
    run(
        [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "python",
            image_id,
            "-c",
            """
import sys
from alembic.config import Config
from alembic.script import ScriptDirectory
s=ScriptDirectory.from_config(Config("/app/alembic.ini"))
allowed={r.revision for r in s.walk_revisions(
 base="0076_forward_review_evidence",head=s.get_current_head())}
assert sys.argv[1] in allowed, "SAFE_PAUSE_SCHEMA_UNSUPPORTED"
""",
            revision,
        ]
    )
    return {
        "schema_version": "w2.safe_pause_identity.v1",
        "release_id": sha,
        "database_revision": revision,
        "collectors": proof,
        "public_services_stopped": True,
    }


def dashboard_baseline():
    """Only the existing fixture read path; no current recommendation consumer."""
    from w2.api.repository import ReadModelRepository, ReadModelService
    from w2.dashboard.date_window import default_football_day, football_day_window
    from w2.infrastructure.database import create_engine

    engine = create_engine().execution_options(
        isolation_level="REPEATABLE READ", postgresql_readonly=True
    )
    repository = ReadModelRepository(engine=engine)
    day = default_football_day(datetime.now(UTC))
    start, end = football_day_window(day)
    fixtures = repository.dashboard_fixtures_for_window(start=start, end=end)
    matches = ReadModelService(repository)._filter_dashboard_cards(
        fixtures, requested_date=day, window="today"
    )
    engine.dispose()
    return {
        "schema_version": "w2.release_fixture_baseline.v1",
        "source": "readonly_dashboard_fixture_repository",
        "football_day_start_utc": start.isoformat().replace("+00:00", "Z"),
        "matches": [{"fixture_id": row["fixture_id"]} for row in matches],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default="w2-staging")
    parser.add_argument("--dashboard-baseline", action="store_true")
    args = parser.parse_args()
    result = dashboard_baseline() if args.dashboard_baseline else read_identity(args.project)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
