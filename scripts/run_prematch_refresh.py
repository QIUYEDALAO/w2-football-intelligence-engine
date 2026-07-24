from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from w2.prematch.read_model_projection import ProjectionSourceEvent

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def parse_utc(value: str | None) -> datetime:
    if not value:
        return datetime.now(UTC)
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


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
    from w2.api.repository import ReadModelRepository, ReadModelService
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

    from w2.ingestion.future_refresh import run_future_refresh_task  # noqa: PLC0415

    audit = run_future_refresh_task(
        task_id=f"{key}:manual",
        key=key,
        queued_at=now,
        competition_id=args.competition_id,
        runtime_root=args.runtime_root,
        now=now,
        persistence=args.persistence,
        materialize_public_artifacts=(
            materialize_shadow_projection_events if args.persistence == "db" else None
        ),
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
    return 0 if audit.status in {"COMPLETED", "ALREADY_RUNNING"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
