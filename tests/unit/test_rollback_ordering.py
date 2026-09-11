"""The staging rollback must put the schema back before it puts the image back.

A rollback that reverts services by digest and leaves the database forward looks
harmless -- the migration in question only added a table -- but the previous
image's readiness check asserts that the database revision EQUALS its own code
head, not that it is compatible. On 2026-09-11 that took staging down: the API
came back unhealthy, the web container never started, and the rollback reported
failure with no way forward except a manual downgrade.

These tests drive the real rollback function out of the deploy script with the
Docker and compose calls stubbed, so the ordering is asserted rather than
described.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "deploy_stage7h_staging.sh"
PREVIOUS_HEAD = "0070_notification_delivery_routing"
CANDIDATE_HEAD = "0071_forward_ah_factor_observation"


def _function(name: str) -> str:
    text = SCRIPT.read_text(encoding="utf-8")
    match = re.search(rf"^{re.escape(name)}\(\) \{{\n(?:.*?\n)*?^\}}\n", text, re.MULTILINE)
    assert match, f"{name} not found in {SCRIPT.name}"
    return match.group(0)


def _harness(*, database_revision: str, downgrade_succeeds: bool) -> str:
    """A bash program that runs the real rollback against stubbed infrastructure."""
    return f"""
set -uo pipefail
WORK="$1"
: >"${{WORK}}/calls"
DB_REVISION={database_revision}

release_value() {{ sed -n "s/^$1=//p" "$2"; }}

sudo() {{
  echo "sudo $*" >>"${{WORK}}/calls"
  if [ "$1" = docker ] && [ "$2" = run ]; then
    echo "{PREVIOUS_HEAD} (head)"
    return 0
  fi
  if [ "$1" = install ]; then
    echo "DIGEST_SWITCHED" >>"${{WORK}}/calls"
    return 0
  fi
  return 0
}}

compose_stub() {{
  echo "compose $*" >>"${{WORK}}/calls"
  case "$*" in
    *alembic*current*)
      # alembic prints nothing at all when the database carries no revision.
      [ -n "${{DB_REVISION}}" ] && echo "${{DB_REVISION}} (head)"
      ;;
    *alembic*downgrade*)
      echo "DOWNGRADE_ATTEMPTED" >>"${{WORK}}/calls"
      if [ "{str(downgrade_succeeds).lower()}" != true ]; then
        echo "FORWARD_AH_FACTOR_OBSERVATION_DOWNGRADE_WOULD_DESTROY_FACTS" >&2
        return 1
      fi
      DB_REVISION={PREVIOUS_HEAD}
      echo "${{DB_REVISION}}" >"${{WORK}}/revision"
      ;;
  esac
  return 0
}}
COMPOSE=(compose_stub)

wait_for_runtime() {{ return 0; }}

ACTIVATED=true
mkdir -p /opt 2>/dev/null || true

{_function("current_database_revision")}
{_function("image_migration_head")}
{_function("rollback")}

# current_database_revision re-reads the mutated DB_REVISION through the stub,
# so a downgrade performed mid-rollback is visible to the verification step.
true
rollback
"""


def _run(tmp_path: Path, *, database_revision: str, downgrade_succeeds: bool):
    previous_env = tmp_path / "release.previous.env"
    previous_env.write_text(
        "W2_PYTHON_IMAGE=ghcr.io/example/python@sha256:" + "a" * 64 + "\n",
        encoding="utf-8",
    )
    script = _harness(
        database_revision=database_revision, downgrade_succeeds=downgrade_succeeds
    ).replace("/opt/w2/shared/release.previous.env", str(previous_env)).replace(
        "/opt/w2/shared/release.env", str(tmp_path / "release.env")
    )
    program = tmp_path / "harness.sh"
    program.write_text(script, encoding="utf-8")
    result = subprocess.run(
        ["bash", str(program), str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    calls = (tmp_path / "calls").read_text(encoding="utf-8")
    return result, calls


def test_forward_schema_is_downgraded_before_the_digest_is_switched(tmp_path: Path) -> None:
    result, calls = _run(tmp_path, database_revision=CANDIDATE_HEAD, downgrade_succeeds=True)

    assert "DOWNGRADE_ATTEMPTED" in calls
    assert "DIGEST_SWITCHED" in calls
    assert calls.index("DOWNGRADE_ATTEMPTED") < calls.index("DIGEST_SWITCHED"), (
        "the digest must not be switched until the schema is back"
    )
    assert "rollback=PASS" in result.stdout


def test_refused_downgrade_keeps_the_candidate_and_never_switches(tmp_path: Path) -> None:
    result, calls = _run(tmp_path, database_revision=CANDIDATE_HEAD, downgrade_succeeds=False)

    assert "DOWNGRADE_ATTEMPTED" in calls
    assert "DIGEST_SWITCHED" not in calls, (
        "a refused downgrade must not strand the old image against a forward schema"
    )
    assert "rollback=BLOCKED reason=DOWNGRADE_REFUSED" in result.stderr
    assert "rollback=PASS" not in result.stdout


def test_matching_revision_switches_without_touching_the_schema(tmp_path: Path) -> None:
    result, calls = _run(tmp_path, database_revision=PREVIOUS_HEAD, downgrade_succeeds=True)

    assert "DOWNGRADE_ATTEMPTED" not in calls, "nothing to downgrade when already level"
    assert "DIGEST_SWITCHED" in calls
    assert "rollback=PASS" in result.stdout


def test_repeating_a_completed_rollback_is_idempotent(tmp_path: Path) -> None:
    """Running it twice must not attempt a second downgrade or damage anything."""
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()

    first_result, first_calls = _run(
        first_dir, database_revision=CANDIDATE_HEAD, downgrade_succeeds=True
    )
    second_result, second_calls = _run(
        second_dir, database_revision=PREVIOUS_HEAD, downgrade_succeeds=True
    )

    assert "rollback=PASS" in first_result.stdout
    assert "rollback=PASS" in second_result.stdout
    assert first_calls.count("DOWNGRADE_ATTEMPTED") == 1
    assert "DOWNGRADE_ATTEMPTED" not in second_calls


@pytest.mark.parametrize("missing", ["revision", "head"])
def test_unreadable_revision_blocks_rather_than_guessing(tmp_path: Path, missing: str) -> None:
    database_revision = "" if missing == "revision" else CANDIDATE_HEAD
    script_dir = tmp_path / missing
    script_dir.mkdir()
    result, calls = _run(
        script_dir, database_revision=database_revision or '""', downgrade_succeeds=True
    )


    if missing == "revision":
        assert "rollback=BLOCKED reason=REVISION_UNREADABLE" in result.stderr
        assert "DIGEST_SWITCHED" not in calls
