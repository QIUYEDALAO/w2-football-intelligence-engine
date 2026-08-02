from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from w2.prematch.read_model_projection import ProjectionSourceEvent

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
FULL_GIT_SHA = re.compile(r"[0-9a-f]{40}")
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def parse_utc(value: str | None) -> datetime:
    if not value:
        return datetime.now(UTC)
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


@dataclass(frozen=True)
class ExactCodeIdentity:
    head: str
    tree: str
    execution_mode: str
    runtime_artifact_digest: str | None = None
    complete_checkout_manifest_sha256: str | None = None


_IGNORED_EXECUTABLE_SUFFIXES = {
    ".py",
    ".pyc",
    ".pyo",
    ".pth",
    ".so",
    ".dylib",
    ".sh",
    ".bash",
    ".zsh",
    ".js",
    ".mjs",
    ".cjs",
}


def _git_bytes(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT)


def _ignored_executable(path: Path) -> bool:
    if path.is_symlink() or path.suffix.lower() in _IGNORED_EXECUTABLE_SUFFIXES:
        return True
    try:
        return bool(path.stat().st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
    except OSError:
        return False


def exact_code_identity() -> ExactCodeIdentity:
    try:
        dirty = _git_bytes("status", "--porcelain=v1", "-z", "--untracked-files=all")
        ignored = _git_bytes("ls-files", "--others", "--ignored", "--exclude-standard", "-z")
        head = _git_bytes("rev-parse", "HEAD").decode().strip()
        tree = _git_bytes("rev-parse", "HEAD^{tree}").decode().strip()
        index_manifest = _git_bytes("ls-files", "-s", "-z")
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError("GATE_A_EXACT_CODE_IDENTITY_UNAVAILABLE") from exc
    if dirty:
        raise RuntimeError("GATE_A_COMPLETE_CHECKOUT_DIRTY_OR_UNTRACKED")
    ignored_paths = [ROOT / os.fsdecode(value) for value in ignored.split(b"\0") if value]
    if any(_ignored_executable(path) for path in ignored_paths):
        raise RuntimeError("GATE_A_IGNORED_EXECUTABLE_CONTENT_PRESENT")
    if FULL_GIT_SHA.fullmatch(head) is None or FULL_GIT_SHA.fullmatch(tree) is None:
        raise RuntimeError("GATE_A_EXACT_CODE_IDENTITY_UNAVAILABLE")
    manifest = hashlib.sha256(
        b"W2_COMPLETE_CLEAN_CHECKOUT_V1\0"
        + head.encode()
        + b"\0"
        + tree.encode()
        + b"\0"
        + index_manifest
    ).hexdigest()
    return ExactCodeIdentity(
        head=head,
        tree=tree,
        execution_mode="COMPLETE_CLEAN_CHECKOUT",
        complete_checkout_manifest_sha256=manifest,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run or plan the W2 prematch refresh task.",
    )
    parser.add_argument("--competition-id", default="world_cup_2026")
    parser.add_argument("--season", default="2026")
    parser.add_argument("--interval-seconds", type=int, default=900)
    parser.add_argument("--now-utc")
    parser.add_argument("--runtime-root", type=Path)
    parser.add_argument("--persistence", choices=("db", "file"))
    parser.add_argument("--authorization-file", type=Path)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually run the refresh task. Omit for a no-provider-call plan.",
    )
    return parser


def deterministic_time_bucket(now: datetime, interval_seconds: int) -> str:
    epoch = int(now.astimezone(UTC).timestamp())
    bucket = epoch - (epoch % interval_seconds)
    return datetime.fromtimestamp(bucket, tz=UTC).strftime("%Y%m%dT%H%M%SZ")


def planned_task_key(
    *,
    competition_id: str,
    season: str,
    now: datetime,
    interval_seconds: int,
) -> str:
    bucket = deterministic_time_bucket(now, interval_seconds)
    return f"future-refresh:{competition_id}:{season}:{bucket}"


def dry_run_payload(args: argparse.Namespace, *, now: datetime, key: str) -> dict[str, Any]:
    return {
        "status": "DRY_RUN",
        "would_execute": False,
        "provider_calls": False,
        "competition_id": args.competition_id,
        "season": args.season,
        "task_key": key,
        "task_id": f"{key}:manual",
        "runtime_root": str(args.runtime_root) if args.runtime_root else None,
        "persistence": args.persistence,
        "planned_at_utc": now.isoformat().replace("+00:00", "Z"),
        "candidate": False,
        "formal_recommendation": False,
        "beats_market": False,
    }


def materialize_shadow_projection_events(
    events: list[ProjectionSourceEvent],
) -> list[str]:
    """Manual DB composition adapter with the worker's current-reader semantics."""
    from w2.prematch.analysis_calculator import ReadModelRepository, ReadModelService
    from w2.prematch.read_model_projection import (
        ScopedAnalysisRepository,
        materialize_projection_events,
    )

    repository = ReadModelRepository()

    def calculate(
        scoped_repository: ScopedAnalysisRepository,
        fixture_id: str,
        evaluated_at: datetime,
    ) -> dict[str, object] | None:
        return ReadModelService(
            repository=cast(ReadModelRepository, scoped_repository)
        ).public_analysis_card_bounded(
            fixture_id,
            evaluation_time=evaluated_at,
            use_frozen_canary=False,
        )

    return materialize_projection_events(
        events,
        repository=cast(ScopedAnalysisRepository, repository),
        calculate_analysis_card=calculate,
    )


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    now = parse_utc(args.now_utc)
    key = planned_task_key(
        competition_id=args.competition_id,
        season=args.season,
        now=now,
        interval_seconds=args.interval_seconds,
    )
    if not args.execute:
        print(json.dumps(dry_run_payload(args, now=now, key=key), ensure_ascii=False, indent=2))
        return 0

    if args.persistence != "db":
        parser.error("--execute requires explicit --persistence db")

    from w2.config import get_settings  # noqa: PLC0415
    from w2.ingestion.future_refresh import (  # noqa: PLC0415
        load_refresh_policy,
        run_future_refresh_task,
    )
    from w2.monitoring.readiness import schema_check  # noqa: PLC0415
    from w2.operations.gate_a import (  # noqa: PLC0415
        GateAError,
        GateARuntimeAuthorization,
        reserve_gate_a_run,
    )

    if args.authorization_file is None:
        parser.error("--execute requires --authorization-file")
    try:
        identity = exact_code_identity()
        policy = load_refresh_policy(competition_id=args.competition_id)
        if args.season != policy.season:
            raise GateAError("GATE_A_POLICY_SEASON_MISMATCH")
        authorization = GateARuntimeAuthorization.load(args.authorization_file)
        if authorization.fixture_scope_mode != "EXACT_FIXTURE_ID":
            raise GateAError("GATE_A_STAGED_CANARY_REQUIRED")
        authorization.validate_scope(
            competition_id=args.competition_id,
            season=args.season,
            policy_season=policy.season,
            policy_provider_league_id=policy.provider_league_id,
            policy_config_hash=policy.config_hash,
            persistence=args.persistence,
            task_key=key,
            fixture_id=authorization.fixture_id,
            exact_head=identity.head,
            exact_tree=identity.tree,
            execution_mode=identity.execution_mode,
            runtime_artifact_digest=identity.runtime_artifact_digest,
            complete_checkout_manifest_sha256=identity.complete_checkout_manifest_sha256,
            now=datetime.now(UTC),
        )
    except (GateAError, RuntimeError) as exc:
        parser.error(str(exc))
    schema_ready, schema_detail = schema_check(get_settings())
    if not schema_ready:
        parser.error(f"GATE_A_MIGRATION_HEAD_MISMATCH:{schema_detail}")
    reservation = reserve_gate_a_run(
        authorization,
        owner=f"manual:{hashlib.sha256(key.encode()).hexdigest()[:16]}",
        now=datetime.now(UTC),
    )

    audit = run_future_refresh_task(
        task_id=f"{key}:manual",
        key=key,
        queued_at=now,
        competition_id=args.competition_id,
        runtime_root=args.runtime_root,
        now=now,
        persistence=args.persistence,
        season=args.season,
        materialize_public_artifacts=materialize_shadow_projection_events,
        runtime_authorization=authorization,
        provider_call_reservation=reservation,
    )
    payload = {
        "status": audit.status,
        "task_id": audit.task_id,
        "task_key": audit.key,
        "result": {
            **audit.result,
            "candidate": False,
            "formal_recommendation": False,
            "beats_market": False,
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    if audit.status == "COMPLETED":
        return 0
    return 2 if audit.status == "ALREADY_RUNNING" else 1


if __name__ == "__main__":
    raise SystemExit(main())
